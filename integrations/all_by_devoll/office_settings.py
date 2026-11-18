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
EDITABLE=("ABD_OWNER_REPORT_TO","ABD_IMAP_USER","ABD_IMAP_APP_PASSWORD")
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
    if not old.get("ABD_BLUESEER_ENABLE_LIVE_INVOICES"):
        old["ABD_BLUESEER_ENABLE_LIVE_INVOICES"]="no"
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
    for key in ("ABD_OWNER_REPORT_TO","ABD_IMAP_USER","ABD_IMAP_APP_PASSWORD","ABD_REPORT_SMTP_USER"):
        os.environ[key]=old.get(key,"")
    return old

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
        "saved":"Email settings saved.",
        "connected":"Gmail login successful.",
        "failed":"Gmail login could not be verified.",
    }.get(status,"")
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Settings | All by Devoll</title>
<style>:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5f7f6;color:#193634;font:15px/1.5 system-ui,sans-serif}header{background:#123f3e;color:white;padding:22px max(24px,calc((100% - 800px)/2));font-weight:700;font-size:20px}main{max-width:800px;margin:26px auto;padding:0 20px}a{color:#176961}h1{font-size:25px}section{background:white;border:1px solid #dce6e2;border-radius:14px;padding:25px;margin:17px 0}label{display:block;font-weight:600;font-size:13px;margin:14px 0 5px}input{display:block;width:100%;border:1px solid #cbd8d5;border-radius:8px;padding:11px;font:inherit}button{background:#176961;color:white;border:0;border-radius:8px;padding:11px 17px;cursor:pointer;font-weight:700;margin-top:16px}.muted{color:#647876}.notice{padding:12px;background:#e5f1ed;border-radius:8px}.actions{display:flex;gap:10px;flex-wrap:wrap}.actions form{display:inline-block}p{line-height:1.6}</style></head><body>
<header>ALL BY DEVOLL</header><main><a href="/">← Back to jobs</a><h1>Settings</h1>""" + (
        '<p class="notice">'+escape(status_text)+'</p>' if status_text else ""
    )+"""
<section><h2>Business email</h2><form method="post" action="/settings/save">
<label>Business Gmail address<input name="ABD_IMAP_USER" type="email" required value=\""""+escape(settings.get("ABD_IMAP_USER",DEFAULT_BUSINESS))+""""></label>
<label>Email completed-job reports to<input name="ABD_OWNER_REPORT_TO" type="email" required value=\""""+escape(settings.get("ABD_OWNER_REPORT_TO",DEFAULT_OWNER))+""""></label>
<label>Gmail app password<input name="ABD_IMAP_APP_PASSWORD" type="password" autocomplete="new-password" placeholder=\""""+("Saved — leave blank to keep" if settings.get("ABD_IMAP_APP_PASSWORD") else "Paste Gmail app password")+""""></label>
<p class="muted">This is the only Google authorization needed for automatic website requests and owner reports. You can <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">open Google's app-password page</a> while signed into the business Gmail account. You may need to enable Google's two-step verification first.</p>
<button type="submit">Save email connection</button></form><form method="post" action="/settings/test-gmail"><button type="submit">Test Gmail connection</button></form></section>
<section><h2>Accounting</h2>
<p>BlueSeer is bundled with El Grande and starts on this computer automatically.</p><p><strong>Local BlueSeer service: """+("Running" if local_erp_running() else "Not responding")+"""</strong></p>
<p class="muted">The shop can record jobs and invoices locally. Native BlueSeer accounting posting is kept off until the shop's accounts and item records are validated, so no unverified financial transactions are created.</p>
</section></main></body></html>"""
