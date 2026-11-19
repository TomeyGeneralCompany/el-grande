"""Plaid Link bank authentication, account balances and transaction import.

No user banking password passes through El Grande. Link handles institution
authentication. App-level Plaid API credentials and access tokens are saved
only in local owner-readable files. Read-only product: transactions.
"""
import json
import threading
import os
import secrets
import tempfile
import urllib.request
import urllib.error
from datetime import datetime,timezone
from pathlib import Path
from decimal import Decimal
import bank_ledger
import mavis_theme

DIRECTORIES={"sandbox":"https://sandbox.plaid.com",
             "development":"https://development.plaid.com",
             "production":"https://production.plaid.com"}
SETTINGS=Path.home()/".config"/"el-grande"/"plaid.json"
DATA=Path.home()/".config"/"el-grande"/"plaid-accounts.json"

def protected_read(path):
    try:return json.loads(path.read_text())
    except FileNotFoundError:return {}
def protected_write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(path.parent,0o700)
    fd,temp=tempfile.mkstemp(prefix=".bank-",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as out:json.dump(payload,out)
        os.chmod(temp,0o600)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
def setup(data):
    old=protected_read(SETTINGS)
    env=str(data.get("environment") or old.get("environment") or "sandbox").strip()
    if env not in DIRECTORIES:raise ValueError("Select a valid bank connection environment")
    client_id=str(data.get("client_id") or old.get("client_id") or "").strip()
    secret=str(data.get("secret") or old.get("secret") or "").strip()
    if len(client_id)>128 or len(secret)>256 or any(x in client_id+secret for x in ("\n","\r")):
        raise ValueError("Invalid connection credentials")
    if not client_id or not secret:raise ValueError("Enter the Plaid client ID and secret")
    protected_write(SETTINGS,{"environment":env,"client_id":client_id,"secret":secret})
    return {"configured":True,"environment":env}
def ready():
    p=protected_read(SETTINGS)
    return bool(p.get("client_id") and p.get("secret")),p.get("environment","sandbox")
def request(route,payload,settings=None):
    p=settings or protected_read(SETTINGS)
    env=p.get("environment","sandbox")
    if env not in DIRECTORIES:raise ValueError("Invalid bank API environment")
    if not p.get("client_id") or not p.get("secret"):
        raise ValueError("Add bank connection credentials in Settings")
    body=json.dumps({"client_id":p["client_id"],"secret":p["secret"],**payload}).encode()
    req=urllib.request.Request(DIRECTORIES[env]+route,body,
        {"Content-Type":"application/json","Accept":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            result=json.loads(response.read(1024*1024))
    except urllib.error.HTTPError as exc:
        # API errors can contain detail but never echo credentials.
        raise ValueError("Bank provider rejected the request (HTTP "+str(exc.code)+")") from exc
    except (urllib.error.URLError,TimeoutError) as exc:
        raise ValueError("Could not reach the bank connection service") from exc
    if not isinstance(result,dict):raise ValueError("Invalid response from bank connector")
    return result
def link_token():
    return request("/link/token/create",{
        "client_name":"El Grande — All by Devoll",
        "language":"en","country_codes":["US"],"products":["transactions"],
        "user":{"client_user_id":"el-grande-local-operator"},
    })["link_token"]
def exchange(public_token,con):
    if not public_token or not isinstance(public_token,str) or len(public_token)>800:
        raise ValueError("Invalid bank authorization token")
    item=request("/item/public_token/exchange",{"public_token":public_token})
    token,item_id=item["access_token"],item["item_id"]
    acc=request("/accounts/get",{"access_token":token}).get("accounts",[])
    if not acc:raise ValueError("No supported accounts returned from the bank")
    saved=protected_read(DATA)
    saved[item_id]={"access_token":token}
    protected_write(DATA,saved)
    chosen=[]
    for account in acc:
        remote=str(account["account_id"])
        display=str(account.get("name") or "Connected bank account")[:80]
        suffix=str(account.get("mask") or "")[-4:]
        label=display+(" •••• "+suffix if suffix else "")
        existing=con.execute("""SELECT id FROM money_accounts WHERE provider='plaid'
             AND provider_account_id=?""",(remote,)).fetchone()
        money=account.get("balances") or {}
        balance=money.get("current")
        amount_cents=bank_ledger.cents(balance) if balance is not None else None
        if existing:
            aid=existing["id"]
            con.execute("""UPDATE money_accounts SET name=?,provider_item_id=?,
              official_balance_cents=?,official_balance_at=?,active=1 WHERE id=?""",
              (label,item_id,amount_cents,bank_ledger.utc(),aid))
        else:
            aid=con.execute("""INSERT INTO money_accounts(name,kind,provider,provider_account_id,
             provider_item_id,official_balance_cents,official_balance_at)
             VALUES (?,'bank','plaid',?,?,?,?)""",
             (label,remote,item_id,amount_cents,bank_ledger.utc())).lastrowid
        chosen.append(aid)
    return chosen
_sync_lock=threading.Lock()
def sync(con):
    with _sync_lock:
        return _sync(con)
def _sync(con):
    items=protected_read(DATA)
    count=0
    for item_id,details in items.items():
        token=details.get("access_token")
        if not token:continue
        acc=request("/accounts/get",{"access_token":token}).get("accounts",[])
        by_id={}
        for account in acc:
            current=(account.get("balances") or {}).get("current")
            existing=con.execute("""SELECT id FROM money_accounts
             WHERE provider='plaid' AND provider_account_id=? AND provider_item_id=?""",
             (account.get("account_id"),item_id)).fetchone()
            if not existing:continue
            by_id[account["account_id"]]=existing["id"]
            if current is not None:
                con.execute("""UPDATE money_accounts SET official_balance_cents=?,
                     official_balance_at=? WHERE id=?""",
                     (bank_ledger.cents(current),bank_ledger.utc(),existing["id"]))
        # Persist cursor separately, only after a complete successful batch.
        cursors=protected_read(SETTINGS)
        cursor=(cursors.get("cursors") or {}).get(item_id)
        original=cursor
        added=[];modified=[];removed=[]
        for _ in range(100):
            payload={"access_token":token,"count":100}
            if cursor:payload["cursor"]=cursor
            response=request("/transactions/sync",payload)
            added+=response.get("added",[])
            modified+=response.get("modified",[])
            removed+=response.get("removed",[])
            cursor=response["next_cursor"]
            if not response.get("has_more"):break
        else:raise ValueError("Bank transaction synchronization exceeded page limit")
        for transaction in added+modified:
            aid=by_id.get(transaction.get("account_id"))
            if aid:
                bank_ledger.imported(con,aid,"plaid",transaction)
                count+=1
        for removed_item in removed:
            con.execute("DELETE FROM bank_feed WHERE provider='plaid' AND external_id=?",
                        (removed_item.get("transaction_id"),))
        cursors.setdefault("cursors",{})[item_id]=cursor
        protected_write(SETTINGS,cursors)
    return count
def connection_page(token,nonce):
    # Tokens and code are only on the localhost page. No banking secrets are
    # rendered. Plaid Link performs actual institution authentication.
    import html
    token_js=json.dumps(token).replace("<","\\u003c")
    connection_html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect a bank | El Grande</title></head>
<body style="font:16px system-ui;max-width:600px;margin:50px auto;padding:20px">
<a href="/bank">Back to Money</a><h1>Connect your bank</h1>
<p>Choose your institution and sign in through Plaid's secure bank connection. El Grande never receives your bank password.</p>
<button id="connect" style="padding:14px 24px">Choose bank</button><p id="message"></p>
<script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
<script nonce='"""+html.escape(nonce,quote=True)+"""'>
const handler=Plaid.create({
 token:"""+token_js+""",
 onSuccess:async(publicToken)=>{
  document.getElementById("message").textContent="Linking account...";
  const data=new URLSearchParams({public_token:publicToken});
  try{
   const response=await fetch("/bank/exchange",{method:"POST",body:data,
    headers:{"Content-Type":"application/x-www-form-urlencoded"}});
   if(!response.ok)throw new Error("Bank connection could not be saved");
   location.href="/bank?status=connected";
  }catch(err){document.getElementById("message").textContent=err.message;}
 },
 onExit:()=>{document.getElementById("message").textContent="Bank connection closed";}
});
document.getElementById("connect").addEventListener("click",()=>handler.open());
</script></body></html>"""
    return connection_html.replace("</head>","<style>"+mavis_theme.CSS+"</style></head>")
