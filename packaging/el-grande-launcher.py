#!/usr/bin/env python3
"""Graphical first-run configuration and launcher. No terminal required."""
import os
from pathlib import Path
import secrets
import subprocess
import sqlite3
import shutil
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.request
import webbrowser

APP=Path("/opt/el-grande")
ENV=Path.home()/".config"/"el-grande"/"desk.env"
DATA=Path.home()/".local"/"share"/"el-grande"
URL="http://127.0.0.1:8765"

def read_env():
    vals={}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k,v=line.split("=",1);vals[k]=v
    return vals

def write_env(values):
    ENV.parent.mkdir(parents=True,exist_ok=True)
    ENV.parent.chmod(0o700)
    keep=read_env()
    keep.update(values)
    # systemd environment file: do not allow newlines/quotes/control characters.
    for k,v in keep.items():
        if not k.replace("_","").isalnum() or any(c in v for c in ("\n","\r","\"","'","\\","%")):
            raise ValueError("Invalid configuration characters")
    ENV.write_text("".join(f"{k}={v}\n" for k,v in sorted(keep.items())))
    ENV.chmod(0o600)

def service(*args):
    return subprocess.run(["systemctl","--user",*args],capture_output=True,text=True,timeout=20)

def prepare_local_data():
    DATA.mkdir(parents=True,exist_ok=True)
    DATA.chmod(0o700)
    (DATA / "data").mkdir(exist_ok=True)
    (DATA / "data").chmod(0o700)
    local_db=DATA / "data" / "tickets.sqlite3"
    if not local_db.exists():
        # Migrate any tickets from the earlier developer checkout.
        old=Path.home() / "Applications" / "el-grande" / "integrations" / "all_by_devoll" / "data" / "tickets.sqlite3"
        if old.exists():
            with sqlite3.connect(old) as source, sqlite3.connect(local_db) as dest:
                source.backup(dest)
    java_data=DATA / "blueseer"
    java_data.mkdir(exist_ok=True)
    java_data.chmod(0o700)
    db_target=java_data / "data"
    template=APP / "java" / "data-template"
    if not db_target.exists() and template.is_dir():
        shutil.copytree(template,db_target)
    cfg=java_data / "bs.cfg"
    if not cfg.exists():
        cfg.write_text(
            "DBTYPE=sqlite\nDB=data/en/bsdb.db\nUSER=bs_user\n"
            "PASS=bspasswd\nIP=localhost\nPORT=3306\n"
            "DRIVER=org.sqlite.JDBC\nLANGUAGE=en\nCOUNTRY=US\n"
        )
        cfg.chmod(0o600)

def ensure_first_run_defaults():
    # A brand-new install should open the shop directly. Email authorization
    # is offered in Settings when convenient, not as a startup obstacle.
    if ENV.exists():return
    prepare_local_data()
    write_env({
        "ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
        "ABD_IMAP_USER":"allbydevoll@gmail.com",
        "ABD_IMAP_APP_PASSWORD":"",
        "ABD_BLUESEER_URL":"http://127.0.0.1:8088/bsapi",
        "ABD_BLUESEER_ENABLE_LIVE_INVOICES":"no",
        "ABD_DB":str(DATA / "data" / "tickets.sqlite3"),
        "ABD_BIND":"127.0.0.1",
        "ABD_DASHBOARD_PASSWORD":""
    })

def try_dashboard():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/",timeout=2) as r:
            return r.status in (200,401)
    except Exception:
        # urllib raises HTTPError for BasicAuth challenge; that means service exists.
        try:
            import urllib.error
            with urllib.request.urlopen(URL,timeout=2):pass
        except urllib.error.HTTPError as e:
            return e.code==401
        except Exception:pass
        return False

def open_dashboard():
    # The installed El Grande app owns both the job desk and ERP runtime.
    # The mechanic never needs to launch BlueSeer as a separate program.
    try:
        prepare_local_data()
    except OSError as err:
        messagebox.showerror("El Grande storage",str(err))
        return
    service("daemon-reload")
    api=service("enable","--now","el-grande-api.service")
    if api.returncode:
        messagebox.showwarning("Accounting","BlueSeer could not start automatically. "
                               "The shop dashboard will still open.")
    # Authenticate to our already-bundled BlueSeer engine and register the
    # actual shop service items. Do not require operator terminal instructions.
    bootstrap=APP / "integrations" / "all_by_devoll" / "erp_bootstrap.py"
    if bootstrap.exists():
        try:
            prepared=subprocess.run(
                ["/usr/bin/python3",str(bootstrap)],capture_output=True,
                text=True,timeout=35)
            if prepared.returncode==0:
                # Job Desk can pick up confirmed native API credentials only
                # after a service restart; no tickets are deleted.
                service("restart","el-grande-desk.service")
        except (OSError,subprocess.TimeoutExpired):
            pass
    if try_dashboard():
        webbrowser.open(URL)
        return
    res=service("enable","--now","el-grande-desk.service")
    if res.returncode:
        messagebox.showerror("El Grande startup",res.stderr.strip() or "Could not start the service.")
        return
    webbrowser.open(URL)

def configure():
    env=read_env()
    root=tk.Tk()
    root.title("El Grande — Office Setup")
    root.geometry("630x540")
    root.minsize(570,530)
    frm=ttk.Frame(root,padding=20)
    frm.pack(fill="both",expand=True)
    ttk.Label(frm,text="EL GRANDE",font=("Sans",20,"bold")).pack(anchor="w")
    ttk.Label(frm,text="All by Devoll · Office connections and setup").pack(anchor="w",pady=(0,12))
    notebook=ttk.Notebook(frm)
    notebook.pack(fill="both",expand=True)
    general=ttk.Frame(notebook,padding=15)
    accounting=ttk.Frame(notebook,padding=15)
    codes=ttk.Frame(notebook,padding=15)
    notebook.add(general,text="Office & Email")
    notebook.add(accounting,text="ERP Connection")
    notebook.add(codes,text="Accounting Codes")
    vars_={}
    def field(parent,key,title,default="",secret=False):
        ttk.Label(parent,text=title).pack(anchor="w",pady=(7,2))
        var=tk.StringVar(value=env.get(key,default))
        ttk.Entry(parent,textvariable=var,width=66,show="*" if secret else "").pack(fill="x")
        vars_[key]=var
    ttk.Label(general,text="Job Desk",font=("Sans",13,"bold")).pack(anchor="w")
    ttk.Label(general,text="The local dashboard opens directly, with no separate login.").pack(anchor="w")
    field(general,"ABD_OWNER_REPORT_TO","Email completed-job reports to","isaiztomey7@gmail.com")
    field(general,"ABD_IMAP_USER","Business inbox","allbydevoll@gmail.com")
    field(general,"ABD_IMAP_APP_PASSWORD","Google app password for the business inbox",secret=True)
    ttk.Label(general,text="Email is optional for the initial trial. Job reports go to the owner address above.",
              wraplength=530).pack(anchor="w",pady=10)
    def test_business_mail():
        import imaplib
        username=vars_["ABD_IMAP_USER"].get().strip()
        password=vars_["ABD_IMAP_APP_PASSWORD"].get().strip().replace(" ","")
        if not username or not password:
            messagebox.showinfo("Email connection","Enter the business Gmail address and app password first.")
            return
        client=None
        try:
            client=imaplib.IMAP4_SSL("imap.gmail.com",timeout=12)
            client.login(username,password)
        except (OSError,imaplib.IMAP4.error) as err:
            messagebox.showerror("Business email","Gmail login could not be verified: "+str(err)[:260])
        else:
            messagebox.showinfo("Business email","Business inbox login succeeded. New website tickets can be imported after saving these settings.")
        finally:
            if client is not None:
                try:client.logout()
                except Exception:pass
    ttk.Button(general,text="Test business Gmail connection",command=test_business_mail).pack(anchor="w")
    ttk.Label(accounting,text="Connect the bundled BlueSeer ERP",font=("Sans",13,"bold")).pack(anchor="w")
    ttk.Label(accounting,text="Business accounting requires the actual BlueSeer user, account and item codes. "
              "Leave these blank until they are configured.",wraplength=530).pack(anchor="w",pady=(0,8))
    field(accounting,"ABD_BLUESEER_USER","BlueSeer user name")
    field(accounting,"ABD_BLUESEER_PASSWORD","BlueSeer password",secret=True)
    ttk.Label(codes,text="Business accounting codes",font=("Sans",13,"bold")).pack(anchor="w")
    ttk.Label(codes,text="Use the actual site, account, terms and service item codes configured in BlueSeer.",
              wraplength=530).pack(anchor="w",pady=(0,10))
    field(codes,"ABD_BLUESEER_SITE","BlueSeer business site code")
    field(codes,"ABD_BLUESEER_AR_ACCOUNT","Accounts receivable account code")
    field(codes,"ABD_BLUESEER_TERMS","Customer payment terms code")
    field(codes,"ABD_BLUESEER_LABOR_ITEM","Labor service item code")
    field(codes,"ABD_BLUESEER_PARTS_ITEM","Parts service item code")
    field(codes,"ABD_BLUESEER_TRAVEL_ITEM","Travel service item (optional)")
    def check_service():
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen("http://127.0.0.1:8088/bsapi/authServ",timeout=2):
                pass
        except urllib.error.HTTPError as err:
            if err.code==401:
                messagebox.showinfo("BlueSeer running","The local BlueSeer API is responding. "
                                    "The business account and item codes must still be configured.")
                return
            messagebox.showerror("BlueSeer response","The API returned HTTP "+str(err.code))
            return
        except OSError as err:
            messagebox.showerror("BlueSeer not running","The local API is not responding:\n"+str(err))
            return
        messagebox.showinfo("BlueSeer","The local API responded.")
    def check_login():
        user=vars_["ABD_BLUESEER_USER"].get().strip()
        password=vars_["ABD_BLUESEER_PASSWORD"].get().strip()
        if not user or not password:
            messagebox.showinfo("BlueSeer login","Enter a BlueSeer username and password first.")
            return
        try:
            import sys
            app_dir=APP/"integrations"/"all_by_devoll"
            if str(app_dir) not in sys.path:sys.path.insert(0,str(app_dir))
            import blue_bridge
            client=blue_bridge.BlueSeerClient(
                base="http://127.0.0.1:8088/bsapi",user=user,password=password)
            client.authenticate()
        except Exception as err:
            messagebox.showerror("BlueSeer login", "Authentication could not be verified: "+str(err)[:250])
        else:
            messagebox.showinfo("BlueSeer login","BlueSeer accepted these credentials. "
                                "Financial transactions still require valid site, accounts and service items.")
    row=ttk.Frame(accounting)
    row.pack(anchor="w",pady=10)
    ttk.Button(row,text="Check local ERP service",command=check_service).pack(side="left",padx=(0,8))
    ttk.Button(row,text="Test BlueSeer login",command=check_login).pack(side="left")
    ttk.Label(accounting,text="Invoice posting stays disabled until tested.",wraplength=530).pack(anchor="w")
    def save():
        vals={k:v.get().strip() for k,v in vars_.items()}
        recipient=vals["ABD_OWNER_REPORT_TO"]
        if "@" not in recipient or recipient.count("@")!=1:
            messagebox.showerror("Email","Enter a valid owner report address.")
            notebook.select(general)
            return
        vals["ABD_BLUESEER_ENABLE_LIVE_INVOICES"]="no"
        vals["ABD_BIND"]="127.0.0.1"
        vals["ABD_DASHBOARD_PASSWORD"]=""
        vals["ABD_DB"]=str(DATA/"data"/"tickets.sqlite3")
        vals["ABD_BLUESEER_URL"]="http://127.0.0.1:8088/bsapi"
        vals["ABD_BLUESEER_CURRENCY"]="USD"
        vals["ABD_IMAP_APP_PASSWORD"]=vals["ABD_IMAP_APP_PASSWORD"].replace(" ","")
        vals["ABD_REPORT_SMTP_USER"]=vals["ABD_IMAP_USER"] if vals["ABD_IMAP_APP_PASSWORD"] else ""
        try:
            service("disable","--now","all-by-devoll-desk.service")
            prepare_local_data()
            write_env(vals)
            service("daemon-reload")
            desk=service("enable","--now","el-grande-desk.service")
            if desk.returncode:
                raise RuntimeError(desk.stderr.strip() or "Could not start the job desk")
            # Changes to environment variables require a restart of an already running service.
            desk=service("restart","el-grande-desk.service")
            if desk.returncode:
                raise RuntimeError(desk.stderr.strip() or "Could not restart job desk")
            api=service("enable","--now","el-grande-api.service")
            if api.returncode:
                messagebox.showwarning("Accounting","Shop desk started. BlueSeer API could not start: "+
                                       (api.stderr.strip()[:220] or "Check the ERP setup."))
        except (OSError,ValueError,RuntimeError) as err:
            messagebox.showerror("Setup couldn't finish",str(err))
            return
        root.destroy()
        webbrowser.open(URL)
    buttons=ttk.Frame(frm)
    buttons.pack(fill="x",pady=(13,0))
    ttk.Label(buttons,text="Your shop stays on this computer.").pack(side="left")
    ttk.Button(buttons,text="Save settings & Open Job Desk",command=save).pack(side="right")
    root.mainloop()

def main():
    if "--setup" in sys.argv:
        # Compatibility for installations already using the old setup icon.
        configure()
    else:
        ensure_first_run_defaults()
        open_dashboard()

if __name__=="__main__":
    main()
