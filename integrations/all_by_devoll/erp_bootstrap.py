#!/usr/bin/env python3
"""Bind the packaged local BlueSeer SQLite ERP to the El Grande job desk.

Runs after the bundled Java API starts. Does not initialize a second database,
does not replace existing accounting data, and never posts AR/GL invoices.
All write operations to BlueSeer go through its native authenticated API.
"""
import os
import re
import secrets
import sqlite3
import sys
from datetime import date
from pathlib import Path
import urllib.error

import blue_bridge

ERP_DB=Path(os.getenv("ABD_BOOTSTRAP_DB",str(Path.home()/".local"/"share"/"el-grande"/"blueseer"/"data"/"en"/"bsdb.db")))
ENV=Path(os.getenv("ABD_BOOTSTRAP_ENV",str(Path.home()/".config"/"el-grande"/"desk.env")))
SERVICE_ITEMS={
    "ABD_BLUESEER_LABOR_ITEM":("ABD-LABOR","All by Devoll mechanic labor"),
    "ABD_BLUESEER_PARTS_ITEM":("ABD-PARTS","All by Devoll service parts"),
    "ABD_BLUESEER_TRAVEL_ITEM":("ABD-TRAVEL","All by Devoll mobile travel"),
    "ABD_BLUESEER_MISC_ITEM":("ABD-OTHER","All by Devoll other charges"),
}
API=os.getenv("ABD_BLUESEER_URL","http://127.0.0.1:8088/bsapi")

def read_env(path=ENV):
    result={}
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k,v=line.split("=",1)
                result[k]=v
    return result

def first_column(con,table):
    cols=con.execute('PRAGMA table_info("'+table+'")').fetchall()
    if not cols:raise ValueError("BlueSeer table unavailable: "+table)
    return '"'+cols[0][1].replace('"','""')+'"'

def has_value(con,table,value):
    col=first_column(con,table)
    return bool(con.execute(f'SELECT 1 FROM "{table}" WHERE {col}=? LIMIT 1',(value,)).fetchone())

def first_value(con,table):
    col=first_column(con,table)
    row=con.execute(f'SELECT {col} FROM "{table}" ORDER BY {col} LIMIT 1').fetchone()
    return str(row[0]) if row and row[0] is not None else ""

def discover_database(path=ERP_DB):
    if not path.is_file():raise ValueError("Bundled BlueSeer database is missing")
    with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=5) as con:
        ok=con.execute("PRAGMA quick_check").fetchone()[0]
        if ok!="ok":raise ValueError("BlueSeer database integrity check failed")
        required=("user_mstr","site_mstr","ac_mstr","cust_term","item_mstr")
        for table in required:first_column(con,table)
        site="1000" if has_value(con,"site_mstr","1000") else first_value(con,"site_mstr")
        ar="20000000" if has_value(con,"ac_mstr","20000000") else ""
        terms="N30" if has_value(con,"cust_term","N30") else (
            "N00" if has_value(con,"cust_term","N00") else first_value(con,"cust_term"))
        if not site or not ar or not terms:
            raise ValueError("BlueSeer business site, AR account or terms are not configured")
        if not has_value(con,"user_mstr","admin"):
            raise ValueError("Packaged default ERP administrator is not present; use existing credentials")
        return {"site":site,"ar_account":ar,"terms":terms}

def ensure_seed_account_password(db_path,env_path,settings,user):
    """Repair a fresh demo account stored unencoded in the upstream seed DB.

    BlueSeer's Java PassWord('1',...) subtracts 222 from each stored
    character. The shipped seed sometimes contains plain 'admin', which the
    native API therefore can never authenticate. Do not touch modified users.
    """
    chosen=settings.get("ABD_BLUESEER_PASSWORD","").strip()
    if chosen:return chosen
    with sqlite3.connect(str(db_path),timeout=8) as con:
        row=con.execute("SELECT user_passwd FROM user_mstr WHERE user_id=?",(user,)).fetchone()
        if row is None:raise ValueError("BlueSeer user not present")
        if user=="admin" and row[0]=="admin":
            chosen=secrets.token_urlsafe(24)
            encoded="".join(chr(ord(c)+222) for c in chosen)
            con.execute("""UPDATE user_mstr SET user_passwd=?
                  WHERE user_id=? AND user_passwd='admin'""",(encoded,user))
            settings["ABD_BLUESEER_PASSWORD"]=chosen
            # Persist the generated credential before authentication, so an
            # interrupted setup cannot orphan the only usable local account.
            write_env(env_path,settings)
            return chosen
    return "admin"

def allow_loopback_api_user(db_path,username):
    """Permit only this workstation's API caller in BlueSeer's own user IP ACL.

    The existing seeded ERP account can be valid while login is denied because
    usr_meta has no 127.0.0.1 access record. Never allow remote clients.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}",username):
        raise ValueError("Invalid local ERP account")
    with sqlite3.connect(str(db_path),timeout=8) as con:
        actual={c[1] for c in con.execute('PRAGMA table_info("usr_meta")')}
        keys={"usrm_id","usrm_type","usrm_key","usrm_value"}
        if not keys.issubset(actual):
            raise ValueError("BlueSeer user access table is not available")
        prior=con.execute("""SELECT 1 FROM usr_meta
           WHERE usrm_id=? AND usrm_type=? AND usrm_key=? AND usrm_value=? LIMIT 1""",
           ("access","ip",username,"127.0.0.1")).fetchone()
        if prior:return False
        con.execute("""INSERT INTO usr_meta(usrm_id,usrm_type,usrm_key,usrm_value)
           VALUES (?,?,?,?)""",("access","ip",username,"127.0.0.1"))
        return True

def service_item_payload(code,description,site):
    from datetime import date
    # Native Java record fields (invData.item_mstr), not a direct DB table mutation.
    names="""it_item it_desc it_lotsize it_sell_price it_pur_price it_ovh_cost
       it_out_cost it_mtl_cost it_code it_type it_group it_prodline
       it_drawing it_rev it_custrev it_wh it_loc it_site it_comments
       it_status it_uom it_net_wt it_ship_wt it_cont it_contqty
       it_leadtime it_safestock it_minordqty it_mrp it_sched it_plan
       it_wf it_taxcode it_createdate it_expire it_expiredays
       it_phantom it_label""".split()
    r=blue_bridge.record(names,
        it_item=code,it_desc=description,it_site=site,
        it_type="S",it_code="S",it_group="SERVICE",
        it_prodline="9999",it_status="ACTIVE",it_uom="EA",
        it_sell_price=0.0,it_pur_price=0.0,it_lotsize=1,
        it_createdate=date.today().isoformat())
    for key in ("it_lotsize","it_contqty","it_leadtime","it_expiredays"):
        r[key]=int(r[key] or 0)
    for key in ("it_sell_price","it_pur_price","it_ovh_cost","it_out_cost",
      "it_mtl_cost","it_net_wt","it_ship_wt","it_safestock","it_minordqty"):
        r[key]=float(r[key] or 0)
    return r

def configure_shop_site(client,site):
    """Replace the untouched upstream sample business label, not user data."""
    import json
    current=client.get("dataServADM","getSiteMstr",site)
    if not isinstance(current,dict) or current.get("site_site")!=site:
        raise ValueError("BlueSeer site cannot be read")
    if current.get("site_desc")=="All by Devoll":
        return "existing"
    if current.get("site_desc")!="MFG Company":
        return "unchanged"  # A configured business is never overwritten.
    current=dict(current)
    current.update(site_desc="All by Devoll",
                   site_city="Manistee",site_state="MI",site_country="USA")
    client.post("dataServADM","updateSiteMstr",json.dumps(current))
    latest=client.get("dataServADM","getSiteMstr",site)
    if not isinstance(latest,dict) or latest.get("site_desc")!="All by Devoll":
        raise ValueError("BlueSeer did not confirm the shop business name")
    return "updated"

def ensure_service_item(client,code,description,site):
    existing=client.get("dataServINV","getItemMstr",code)
    if isinstance(existing,dict) and existing.get("it_item")==code:
        if existing.get("it_desc")!=description or existing.get("it_site")!=site:
            raise ValueError("BlueSeer already has a different item using "+code)
        return "existing"
    import json
    client.post("dataServINV","addItemMstr",json.dumps(service_item_payload(code,description,site)))
    existing=client.get("dataServINV","getItemMstr",code)
    if not isinstance(existing,dict) or existing.get("it_item")!=code:
        raise ValueError("BlueSeer did not confirm newly created item "+code)
    return "created"

def write_env(path,values):
    import tempfile
    path.parent.mkdir(parents=True,exist_ok=True)
    os.chmod(path.parent,0o700)
    for k,v in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*",k) or any(x in str(v) for x in ("\n","\r","'","\"","\\","%")):
            raise ValueError("Invalid local ERP configuration")
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".erp-",text=True)
    try:
        with os.fdopen(fd,"w") as f:
            for k,v in sorted(values.items()):f.write(k+"="+str(v)+"\n")
        os.chmod(tmp,0o600)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def configure(path=ERP_DB,envpath=ENV,client_factory=blue_bridge.BlueSeerClient):
    settings=read_env(envpath)
    discovery=discover_database(path)
    user=settings.get("ABD_BLUESEER_USER") or "admin"
    password=ensure_seed_account_password(path,envpath,settings,user)
    # The local Java API checks both password and an explicit usr_meta IP
    # ACL. This is a *loopback-only* workstation; never allow remote IPs.
    allow_loopback_api_user(path,user)
    client=client_factory(base=API,user=user,password=password)
    client.authenticate()
    site=settings.get("ABD_BLUESEER_SITE") or discovery["site"]
    if site!=discovery["site"]:
        with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True) as con:
            if not has_value(con,"site_mstr",site):
                raise ValueError("Existing BlueSeer site code does not exist")
    configure_shop_site(client,site)
    for envkey,(code,description) in SERVICE_ITEMS.items():
        desired=settings.get(envkey) or code
        if desired!=code:
            existing=client.get("dataServINV","getItemMstr",desired)
            if not isinstance(existing,dict) or existing.get("it_item")!=desired:
                raise ValueError("Configured BlueSeer item missing: "+desired)
        else:
            ensure_service_item(client,code,description,site)
        settings[envkey]=desired
    settings.update({
        "ABD_BLUESEER_URL":API,
        "ABD_BLUESEER_USER":user,
        "ABD_BLUESEER_PASSWORD":password,
        "ABD_BLUESEER_SITE":site,
        "ABD_BLUESEER_AR_ACCOUNT":settings.get("ABD_BLUESEER_AR_ACCOUNT") or discovery["ar_account"],
        "ABD_BLUESEER_TERMS":settings.get("ABD_BLUESEER_TERMS") or discovery["terms"],
        "ABD_BLUESEER_CURRENCY":"USD",
        # Never auto-authorize live AR/GL posting from a sample database.
        "ABD_BLUESEER_ENABLE_LIVE_INVOICES":"no",
        "ABD_BLUESEER_CONNECTED":"yes",
    })
    write_env(envpath,settings)
    return {"connected":True,"site":site,"items":list(SERVICE_ITEMS)}

def main():
    try:
        details=configure()
    except (OSError,ValueError,sqlite3.Error,blue_bridge.BridgeError,urllib.error.URLError) as err:
        # Do not print passwords or any credential material.
        print("BlueSeer integration is not yet ready: "+str(err).replace("admin","[account]")[:300])
        return 1
    print("BlueSeer authenticated and shop service items installed via native API.")
    return 0

if __name__=="__main__":sys.exit(main())
