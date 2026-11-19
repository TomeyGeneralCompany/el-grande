"""Single-app office settings, stored locally with strict file permissions.

Gmail credentials and bank display details stay on the workstation.
"""
import html
import imaplib
import os
from pathlib import Path
import re
import tempfile

HOME_CONFIG=Path.home()/".config"/"el-grande"/"desk.env"
EDITABLE=("ABD_OWNER_REPORT_TO","ABD_IMAP_USER","ABD_IMAP_APP_PASSWORD",
          "ABD_BANK_NAME","ABD_BANK_LABEL","ABD_BANK_LAST4")
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
                "ABD_BANK_NAME","ABD_BANK_LABEL","ABD_BANK_LAST4"):
        os.environ[key]=old.get(key,"")
    return old

def save_bank(payload):
    updates = {key:payload[key] for key in ("ABD_BANK_NAME","ABD_BANK_LABEL","ABD_BANK_LAST4") if key in payload}
    if not updates:raise ValueError("No bank settings supplied")
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

def page(settings,status):
    import bank_connect
    import mavis_theme
    provider_configured,provider_environment=bank_connect.ready()
    provider_options="".join('<option value="'+key+'"'+(' selected' if provider_environment==key else '')+'>'+label+'</option>' for key,label in (
       ("sandbox","Sandbox (testing)"),("development","Development"),("production","Production (real banks)")))
    escape=lambda v:html.escape(str(v or ""),quote=True)
    status_text={
        "saved":"Gmail connection settings saved.",
        "connected":"Gmail login successful.",
        "failed":"Gmail login could not be verified.",
        "bank-saved":"Bank information saved.",
        "bank-failed":"Bank information could not be saved. Check the bank name and last four digits.",
        "plaid-saved":"Bank connection provider is configured.",
        "plaid-failed":"Bank connection needs valid provider credentials. You can still use the money ledger.",
    }.get(status,"")
    gmail_saved=bool(settings.get("ABD_IMAP_APP_PASSWORD"))
    bank_saved=bool(settings.get("ABD_BANK_NAME") or settings.get("ABD_BANK_LABEL"))
    gmail_label=("Gmail configured" if gmail_saved else "Add Gmail connection")
    bank_label=("Edit bank account" if bank_saved else "Add bank account")
    bank_display=escape(settings.get("ABD_BANK_NAME",""))
    if settings.get("ABD_BANK_LAST4"):
        bank_display+=(" •••• "+escape(settings["ABD_BANK_LAST4"]))
    page_html = """<!doctype html><html lang="en"><head><meta charset="utf-8">
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
select{display:block;width:100%;padding:11px;border:1px solid #cbd8d5;border-radius:8px}input{display:block;width:100%;border:1px solid #cbd8d5;border-radius:8px;padding:11px;font:inherit}
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

<p class="hint">No routing number or online banking password is required. This saves the bank account identity for office records; it is not an online bank sign-in.</p>
<button type="submit">Save bank account</button></form></details></section>
<section><h2>Connect to your bank</h2>
<p class="muted">Link an actual financial institution, view balances, and import money in and out. Existing manual cashbook entries remain available.</p>
"""+('<p><strong>Bank provider configured ('+escape(provider_environment)+')</strong></p>' if provider_configured else "")+"""
<details class="details"><summary>"""+("Edit connection" if provider_configured else "Set up bank connection")+"""</summary>
<form method="post" action="/bank/provider-settings">
<label>Plaid client ID<input name="client_id" type="text" autocomplete="off" placeholder="Provided by Plaid" maxlength="128"></label>
<label>Plaid secret<input name="secret" type="password" autocomplete="new-password" maxlength="256" placeholder="Enter secret, or leave blank to keep it"></label>
<label>Connection environment<select name="environment">
"""+provider_options+"""
</select></label><p class="hint">This connector needs a Plaid developer account. The bank password is entered only in the bank's authorization flow, never here.</p>
<button type="submit">Save provider connection</button></form></details>
<p><a href="/bank">Open money ledger and bank connections</a></p>
</section>
<section><h2>Records</h2>
<p><a href="/reports/legacy.csv">Download imported accounting and transaction history</a></p>
</section></main></body></html>"""
    return page_html.replace("</style>","</style><style>"+mavis_theme.CSS+"</style>")
