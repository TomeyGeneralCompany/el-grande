"""Self-contained local money register page; native HTML, no frontend build."""
import html
import bank_ledger
from datetime import date
from decimal import Decimal

def e(x):return html.escape(str(x if x is not None else ""),quote=True)
def page(con,provider_ready=False,status=""):
    rows=bank_ledger.accounts(con)
    entries=bank_ledger.recent_entries(con)
    feed=con.execute("""SELECT f.*,a.name account_name
          FROM bank_feed f JOIN money_accounts a ON a.id=f.account_id
          ORDER BY f.entry_date DESC,f.id DESC LIMIT 50""").fetchall()
    total=sum((int(a["balance_cents"]) for a in rows),0)
    options="".join('<option value="'+str(a["id"])+'">'+e(a["name"])+"</option>" for a in rows)
    deposits="".join('<option value="'+str(a["id"])+'">'+e(a["name"])+"</option>" for a in rows)
    message={"recorded":"Entry recorded.","transferred":"Transfer recorded.",
      "connected":"Bank connected. Balances and imported transactions are available.",
      "synced":"Bank balances and transactions refreshed.",
      "matched":"Imported transaction matched to a register entry.",
      "added":"Bank transaction recorded in register.",
      "account":"Account added.","error":"Bank operation could not be completed."}.get(status,"")
    content=['''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Money | El Grande</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f5f7f6;color:#193634;font:15px/1.5 system-ui,sans-serif}
header{background:#123f3e;color:white;padding:20px max(20px,calc((100% - 1000px)/2));font-weight:bold;font-size:20px}
main{max-width:1000px;margin:20px auto;padding:0 18px}a{color:#176961}
section{background:#fff;border:1px solid #dce6e2;border-radius:14px;padding:20px;margin:15px 0}
h1{font-size:25px}h2{font-size:19px;margin:0 0 10px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.cards section{margin:0}.val{font-size:23px;font-weight:700}.muted{color:#647876;font-size:13px}
label{display:block;margin:8px 0;font-weight:600}input,select{width:100%;padding:9px;border:1px solid #cbd8d5;border-radius:8px;font:inherit}
button,.button{background:#176961;color:white;border:0;border-radius:8px;padding:10px 14px;cursor:pointer;font-weight:700;display:inline-block;text-decoration:none}
form{margin:10px 0}.forms{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-bottom:1px solid #e4ece9;vertical-align:top}
.wrap{overflow:auto}.notice{padding:12px;border-radius:8px;background:#e5f1ed}
</style></head><body><header>ALL BY DEVOLL — MONEY</header><main>
<a href="/">← Jobs</a> · <a href="/settings">Settings</a>
<h1>Money in &amp; out</h1>
<p class="muted">Record customer receipts, expenses and deposits without terminal commands. Your local register works even if no bank is connected.</p>''']
    if message:content.append('<p class="notice">'+e(message)+'</p>')
    content.append('<div class="cards">')
    for a in rows:
        content.append('<section><h2>'+e(a["name"])+'</h2>'
          +'<div class="val">$'+bank_ledger.amount(a["balance_cents"])+'</div>'
          +'<p class="muted">Recorded register balance</p>')
        if a["official_balance_cents"] is not None:
            content.append('<div>Bank-reported: <strong>$'+bank_ledger.amount(a["official_balance_cents"])+'</strong></div>'
             +'<p class="muted">As reported '+e(a["official_balance_at"])+'</p>')
        content.append('</section>')
    content.append('</div><section><h2>Record money</h2><div class="forms"><form method="post" action="/bank/entry">'
      +'<h3>Money received or spent</h3><label>Account<select name="account_id">'+options+'</select></label>'
      +'<label>Type<select name="direction"><option value="in">Money in</option><option value="out">Money out</option></select></label>'
      +'<label>Amount ($)<input name="amount" type="number" step=".01" min=".01" required></label>'
      +'<label>Date<input name="entry_date" type="date" value="'+date.today().isoformat()+'" required></label>'
      +'<label>Description<input name="memo" maxlength="300"></label>'
      +'<label>Reference (optional)<input name="reference" maxlength="100"></label>'
      +'<button type="submit">Save transaction</button></form>'
      +'<form method="post" action="/bank/transfer"><h3>Transfer / cash deposit</h3>'
      +'<p class="muted">Record a movement between your cash and bank accounts, including cash deposited.</p>'
      +'<label>From account<select name="from_account">'+options+'</select></label>'
      +'<label>To account<select name="to_account">'+deposits+'</select></label>'
      +'<label>Amount ($)<input name="amount" type="number" min=".01" step=".01" required></label>'
      +'<label>Date<input name="entry_date" type="date" value="'+date.today().isoformat()+'" required></label>'
      +'<label>Note<input name="memo" maxlength="300"></label>'
      +'<button type="submit">Record transfer</button></form></div></section>')
    content.append('<section><h2>Bank connection</h2>')
    if provider_ready:
        content.append('<a class="button" href="/bank/connect">Connect another bank</a> '
          +'<form method="post" action="/bank/sync" style="display:inline"><button>Refresh bank balances &amp; activity</button></form>')
    else:
        content.append('<p>To connect an institution, enter the bank connection credentials in <a href="/settings">Settings</a>.'
        'You can use the ledger without connecting a bank.</p>')
    content.append('<form method="post" action="/bank/account"><h3>Add register account</h3>'
        '<label>Account name<input name="name" maxlength="80" placeholder="Business checking" required></label>'
        '<button>Add account</button></form></section>')
    content.append('<section><h2>Recent money movements</h2><div class="wrap"><table>'
      '<thead><tr><th>Date</th><th>Account</th><th>Description</th><th>Money in / out</th><th>Source</th></tr></thead><tbody>')
    for item in entries:
        amt=int(item["amount_cents"])
        content.append('<tr><td>'+e(item["entry_date"])+'</td><td>'+e(item["account_name"])
         +'</td><td>'+e(item["memo"] or item["category"])+'</td>'
         +'<td>'+('+' if amt>0 else '−')+'$'+bank_ledger.amount(abs(amt))+'</td>'
         +'<td>'+e(item["source"])+'</td></tr>')
    content.append('</tbody></table></div></section>')
    if feed:
        content.append('<section><h2>Imported bank activity</h2>'
          '<p class="muted">Bank activity is kept alongside the register. Match a transaction to an existing entry, or add it to your register once.</p>'
          '<div class="wrap"><table><thead><tr><th>Date</th><th>Account</th><th>Description</th><th>Amount</th><th>Register</th></tr></thead><tbody>')
        for item in feed:
            val=int(item["amount_cents"])
            content.append('<tr><td>'+e(item["entry_date"])+'</td><td>'+e(item["account_name"])
              +'</td><td>'+e(item["description"])+'</td><td>'+('+' if val>0 else '−')+'$'+bank_ledger.amount(abs(val))+'</td><td>')
            if item["linked_entry_id"]:
                content.append('Recorded #'+str(item["linked_entry_id"]))
            else:
                content.append('<form method="post" action="/bank/feed-add"><input type="hidden" name="feed_id" value="'+str(item["id"])+'">'
                  '<button>Add to register</button></form>'
                  '<form method="post" action="/bank/feed-match">'
                  '<input type="hidden" name="feed_id" value="'+str(item["id"])+'">'
                  '<label>Match entry #<input type="number" min="1" name="entry_id" required></label>'
                  '<button>Match</button></form>')
            content.append('</td></tr>')
        content.append('</tbody></table></div></section>')
    content.append('</main></body></html>')
    return "".join(content)
