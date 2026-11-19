"""Single-app office settings, stored locally with strict file permissions.

Gmail requires one authorization credential from its owner; BlueSeer startup,
database installation and local API are managed by El Grande.
"""
import html
import imaplib
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request

HOME_CONFIG=Path.home()/".config"/"el-grande"/"desk.env"
EDITABLE=("ABD_OWNER_REPORT_TO","ABD_IMAP_USER","ABD_IMAP_APP_PASSWORD",
          "ABD_BANK_NAME","ABD_BANK_LABEL","ABD_BANK_LAST4","ABD_BLUESEER_PAYMENT_BANK")
DEFAULT_OWNER="isaiztomey7@gmail.com"
DEFAULT_BUSINESS="allbydevoll@gmail.com"

def existing():
    values={}
    if HOME_CONFIG.exists():
        for line in HOME_CONFIG.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key,value=line.split("=",1)
                values[key]=value
    return values

def save(payload):
    """Update email fields in protected service file without destroying ERP config."""
    old=existing()
    updates={}
    for key in EDITABLE:
        if key not in payload:continue
        v=str(payload[key]).strip()
        if key=="ABD_IMAP_APP_PASSWORD":
            v=v.replace(" ","") if v else old.get(key,"")
        elif key=="ABD_BANK_LAST4":
            if v and not re.fullmatch(r"[0-9]{4}",v):
                raise ValueError("Enter only the last four account digits")
        elif key=="ABD_BLUESEER_PAYMENT_BANK":
            v=v.upper()
            if not re.fullmatch(r"[A-Z0-9_-]{1,20}",v):
                raise ValueError("Enter a valid accounting bank code")
        elif key in ("ABD_BANK_NAME","ABD_BANK_LABEL"):
            if len(v)>100:raise ValueError("Bank name or nickname is too long")
        if any(c in v for c in ("\r","\n","'","\"","\\","%")):
            raise ValueError("Invalid characters in settings")
        if len(v)>320:raise ValueError("Setting too long")
        updates[key]=v
    owner=updates.get("ABD_OWNER_REPORT_TO",old.get("ABD_OWNER_REPORT_TO",DEFAULT_OWNER))
    business=updates.get("ABD_IMAP_USER",old.get("ABD_IMAP_USER",DEFAULT_BUSINESS))
    for address in (owner,business):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",address):
            raise ValueError("Enter a valid email address")
    old.update(updates)
    old["ABD_OWNER_REPORT_TO"]=owner
    old["ABD_IMAP_USER"]=business
    old["ABD_REPORT_SMTP_USER"]=business
    # The same authorized business Gmail credential is used for incoming
    # service requests and outgoing completed-job notifications.
    old["ABD_REPORT_SMTP_APP_PASSWORD"]=old.get("ABD_IMAP_APP_PASSWORD","")
    old["ABD_BLUESEER_ENABLE_LIVE_INVOICES"]="yes"
    HOME_CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(HOME_CONFIG.parent,0o700)
    # Atomic replacement with restrictive permissions to avoid truncated settings
    fd,tmp=tempfile.mkstemp(prefix=".desk-",dir=HOME_CONFIG.parent)
    try:
        with os.fdopen(fd,"w") as out:
            for k,v in sorted(old.items()):
                if not re.fullmatch(r"[A-Z][A-Z0-9_]*",k):
                    raise ValueError("Invalid settings name")
                if any(c in v for c in ("\r","\n","'","\"","\\","%")):
                    raise ValueError("Invalid settings value")
                out.write(k+"="+v+"\n")
        os.chmod(tmp,0o600)
        os.replace(tmp,HOME_CONFIG)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    for key in ("ABD_OWNER_REPORT_TO","ABD_IMAP_USER","ABD_IMAP_APP_PASSWORD",
                "ABD_REPORT_SMTP_USER","ABD_REPORT_SMTP_APP_PASSWORD",
                "ABD_BANK_NAME","ABD_BANK_LABEL","ABD_BANK_LAST4",
                "ABD_BLUESEER_PAYMENT_BANK"):
        os.environ[key]=old.get(key,"")
    return old

def save_bank(payload):
    """Record the bank's display details and optional BlueSeer ledger code.

    Full account or routing numbers are deliberately not requested: the
    bundled ERP identifies its accounting bank by bank code, not credentials.
    """
    keys=("ABD_BANK_NAME","ABD_BANK_LABEL","ABD_BANK_LAST4",
          "ABD_BLUESEER_PAYMENT_BANK")
    updates={key:payload[key] for key in keys if key in payload}
    if not updates:raise ValueError("No bank settings supplied")
    code=str(updates.get("ABD_BLUESEER_PAYMENT_BANK",
                         existing().get("ABD_BLUESEER_PAYMENT_BANK","BK"))).strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{1,20}",code):
        raise ValueError("Invalid accounting bank code")
    # The native API uses a configured BlueSeer bank record, never the
    # customer's routing or account number, to post its AR receipts.
    import blue_bridge
    if os.getenv("ABD_BLUESEER_CONNECTED")=="yes":
        bank=blue_bridge.BlueSeerClient().call("dataServFIN","getBankMstr",key=code)
        if not isinstance(bank,dict) or bank.get("id")!=code or not bank.get("account"):
            raise ValueError("That accounting bank code is not configured in BlueSeer")
    updates["ABD_BLUESEER_PAYMENT_BANK"]=code
    return save(updates)

def test_gmail(email=None,credential=None):
    username=email or os.getenv("ABD_IMAP_USER","")
    secret=credential or os.getenv("ABD_IMAP_APP_PASSWORD","")
    if not username or not secret:raise ValueError("Connect the business Gmail account first")
    client=imaplib.IMAP4_SSL("imap.gmail.com",timeout=15)
    try:
        client.login(username,secret.replace(" ",""))
    finally:
        try:client.logout()
        except Exception:pass
    return True

def local_erp_running():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8088/bsapi/authServ",timeout=2) as response:
            return response.status in (200,401)
    except urllib.error.HTTPError as e:return e.code==401
    except (OSError,ValueError):return False

def page(settings,status):
    escape=lambda v:html.escape(str(v or ""),quote=True)
    status_text={
        "saved":"Gmail connection settings saved.",
        "connected":"Gmail login successful.",
        "failed":"Gmail login could not be verified.",
        "bank-saved":"Bank information saved.",
        "bank-failed":"Bank information could not be saved. Check the accounting bank code.",
    }.get(status,"")
    connected=(settings.get("ABD_BLUESEER_CONNECTED")=="yes" and local_erp_running())
    erp_caption=("BlueSeer connected" if connected else
                 "BlueSeer setup incomplete" if not local_erp_running() else
                 "Local BlueSeer is running")
    gmail_saved=bool(settings.get("ABD_IMAP_APP_PASSWORD"))
    bank_saved=bool(settings.get("ABD_BANK_NAME") or settings.get("ABD_BANK_LABEL"))
    gmail_label=("Gmail configured" if gmail_saved else "Add Gmail connection")
    bank_label=("Edit bank account" if bank_saved else "Add bank account")
    bank_display=escape(settings.get("ABD_BANK_NAME",""))
    if settings.get("ABD_BANK_LAST4"):
        bank_display+=(" •••• "+escape(settings["ABD_BANK_LAST4"]))
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Settings | All by Devoll</title>
<style>
:root{color-scheme:light}
*{box-sizing:border-box}body{margin:0;background:#f5f7f6;color:#193634;font:15px/1.5 system-ui,sans-serif}
header{background:#123f3e;color:white;padding:22px max(24px,calc((100% - 800px)/2));font-weight:700;font-size:20px}
main{max-width:800px;margin:26px auto;padding:0 20px}a{color:#176961}
h1{font-size:25px}h2{font-size:19px;margin:0}
section{background:white;border:1px solid #dce6e2;border-radius:14px;padding:25px;margin:17px 0}
label{display:block;font-weight:600;font-size:13px;margin:14px 0 5px}
input{display:block;width:100%;border:1px solid #cbd8d5;border-radius:8px;padding:11px;font:inherit}
button{background:#176961;color:white;border:0;border-radius:8px;padding:11px 17px;cursor:pointer;font-weight:700;margin-top:16px}
.muted{color:#647876}.notice{padding:12px;background:#e5f1ed;border-radius:8px}
p{line-height:1.6}.details{margin-top:10px}.details summary{cursor:pointer;padding:12px 16px;background:#176961;
border-radius:9px;color:white;font-weight:700;list-style:none;display:inline-block}
.details summary:focus-visible{outline:3px solid #e3ac40;outline-offset:3px}
.details[open] summary{margin-bottom:14px}.hint{font-size:13px;color:#647876}
</style></head><body>
<header>ALL BY DEVOLL</header><main><a href="/">← Back to jobs</a><h1>Settings</h1>""" + (
        '<p class="notice">'+escape(status_text)+'</p>' if status_text else ""
    )+"""
<section><h2>Business Gmail</h2>
<p class="muted">Import customer requests and send completed-job reports. Optional; the shop works without Gmail.</p>
<details class="details"><summary>"""+escape(gmail_label)+"""</summary>
<form method="post" action="/settings/save">
<label>Business Gmail address<input name="ABD_IMAP_USER" type="email" required value=\""""+escape(settings.get("ABD_IMAP_USER",DEFAULT_BUSINESS))+""""></label>
<label>Send completed-job reports to<input name="ABD_OWNER_REPORT_TO" type="email" required value=\""""+escape(settings.get("ABD_OWNER_REPORT_TO",DEFAULT_OWNER))+""""></label>
<label>Gmail app password<input name="ABD_IMAP_APP_PASSWORD" type="password" autocomplete="new-password" placeholder=\""""+("Saved — leave blank to keep" if gmail_saved else "Paste Gmail app password")+""""></label>
<p class="hint">Use a Google app password, not the normal Gmail password. <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">Google app passwords</a></p>
<button type="submit">Save Gmail connection</button></form>
<form method="post" action="/settings/test-gmail"><button type="submit">Test Gmail connection</button></form>
</details></section>
<section><h2>Bank account</h2>
<p class="muted">Keep the business bank's identifying details with the office settings.</p>
"""+('<p><strong>'+bank_display+'</strong></p>' if bank_saved else "")+"""
<details class="details"><summary>"""+escape(bank_label)+"""</summary>
<form method="post" action="/settings/save-bank">
<label>Bank name<input name="ABD_BANK_NAME" type="text" maxlength="100" value=\""""+escape(settings.get("ABD_BANK_NAME",""))+""""></label>
<label>Account nickname<input name="ABD_BANK_LABEL" type="text" maxlength="100" placeholder="Business checking" value=\""""+escape(settings.get("ABD_BANK_LABEL",""))+""""></label>
<label>Last four digits of account number<input name="ABD_BANK_LAST4" type="text" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" placeholder="1234" value=\""""+escape(settings.get("ABD_BANK_LAST4",""))+""""></label>
<details><summary>Advanced accounting settings</summary>
<label>BlueSeer bank ledger code<input name="ABD_BLUESEER_PAYMENT_BANK" type="text" maxlength="20" value=\""""+escape(settings.get("ABD_BLUESEER_PAYMENT_BANK","BK"))+""""></label>
<p class="hint">Use a bank code already configured in BlueSeer. The default is BK.</p>
</details>
<p class="hint">No routing number or online banking password is required. This saves the bank account identity for office records; it is not an online bank sign-in.</p>
<button type="submit">Save bank account</button></form></details></section>
<section><h2>Accounting</h2>
<p><strong>"""+escape(erp_caption)+"""</strong></p>
<p class="muted">Invoices and recorded payments synchronize with the bundled BlueSeer accounting engine automatically. No terminal setup is required for routine use.</p>
</section></main></body></html>"""
