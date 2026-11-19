"""Auditable cash and bank register: cash-first, offline, stdlib-only.

Amounts in integer cents. Customer receipts are reflected once, corrections
have compensating entries, and transfers never create income or expense.
A connected bank's reported balance is stored separately from this register.
"""
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
import re

DDL="""
CREATE TABLE IF NOT EXISTS money_accounts(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('cash','bank')),
 opening_cents INTEGER NOT NULL DEFAULT 0,
 provider TEXT NOT NULL DEFAULT '',
 provider_account_id TEXT NOT NULL DEFAULT '',
 provider_item_id TEXT NOT NULL DEFAULT '',
 official_balance_cents INTEGER,
 official_balance_at TEXT NOT NULL DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS money_accounts_provider_id ON money_accounts(provider,provider_account_id)
 WHERE provider<>'' AND provider_account_id<>'';
CREATE TABLE IF NOT EXISTS money_entries(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_id INTEGER NOT NULL REFERENCES money_accounts(id),
 entry_date TEXT NOT NULL,
 amount_cents INTEGER NOT NULL,
 category TEXT NOT NULL,
 memo TEXT NOT NULL DEFAULT '',
 reference TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'manual',
 source_key TEXT,
 created_at TEXT NOT NULL,
 reversal_of INTEGER REFERENCES money_entries(id),
 UNIQUE(source,source_key)
);
CREATE INDEX IF NOT EXISTS money_entries_order ON money_entries(account_id,entry_date,id);
CREATE TABLE IF NOT EXISTS bank_feed(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_id INTEGER NOT NULL REFERENCES money_accounts(id),
 provider TEXT NOT NULL,
 external_id TEXT NOT NULL,
 entry_date TEXT NOT NULL,
 amount_cents INTEGER NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 pending INTEGER NOT NULL DEFAULT 0,
 linked_entry_id INTEGER REFERENCES money_entries(id),
 imported_at TEXT NOT NULL,
 UNIQUE(provider,external_id)
);
"""
# An immutable snapshot of the physical count and the recorded cashbook balance.
# Counting cash never changes the register, customer payments or native BlueSeer.
CASH_COUNT_DDL="""
CREATE TABLE IF NOT EXISTS cash_counts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_id INTEGER NOT NULL REFERENCES money_accounts(id),
 count_date TEXT NOT NULL,
 counted_cents INTEGER NOT NULL CHECK(counted_cents >= 0),
 expected_cents INTEGER NOT NULL,
 variance_cents INTEGER NOT NULL,
 notes TEXT NOT NULL DEFAULT '',
 recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cash_counts_recent ON cash_counts(account_id,id DESC);
"""
def cash_accounts(con):
    return con.execute("""SELECT a.*,
       a.opening_cents+COALESCE((SELECT SUM(amount_cents) FROM money_entries
           WHERE account_id=a.id),0) AS balance_cents
       FROM money_accounts a WHERE a.kind='cash' AND a.active=1
       ORDER BY a.id""").fetchall()
def record_cash_count(con,payload):
    account_id=int(payload.get("account_id",0))
    account=con.execute("""SELECT a.id,a.opening_cents+COALESCE(
      (SELECT SUM(e.amount_cents) FROM money_entries e WHERE e.account_id=a.id),0
      ) AS balance_cents FROM money_accounts a
      WHERE a.id=? AND a.kind='cash' AND a.active=1""",(account_id,)).fetchone()
    if account is None:raise ValueError("Select a cash account")
    counted=cents(payload.get("counted_amount",""))
    if counted<0:raise ValueError("Cash count cannot be negative")
    counted_date=valid_date(payload.get("count_date"))
    notes=str(payload.get("notes","")).strip()
    if len(notes)>300:raise ValueError("Cash count notes are too long")
    expected=int(account["balance_cents"])
    variance=counted-expected
    cursor=con.execute("""INSERT INTO cash_counts
       (account_id,count_date,counted_cents,expected_cents,variance_cents,notes,recorded_at)
       VALUES (?,?,?,?,?,?,?)""",
       (account_id,counted_date,counted,expected,variance,notes,utc()))
    return cursor.lastrowid,variance
def recent_cash_counts(con,limit=30):
    return con.execute("""SELECT c.*,a.name AS account_name FROM cash_counts c
      JOIN money_accounts a ON a.id=c.account_id
      ORDER BY c.id DESC LIMIT ?""",(limit,)).fetchall()

def utc():return datetime.now(timezone.utc).isoformat(timespec="seconds")
def cents(value,positive=False):
    try:d=Decimal(str(value).strip())
    except (InvalidOperation,ValueError):raise ValueError("Enter a valid dollar amount")
    if not d.is_finite() or d.as_tuple().exponent < -2 or abs(d)>Decimal("100000000"):
        raise ValueError("Enter a valid dollar amount to the nearest cent")
    n=int(d*100)
    if positive and n<=0:raise ValueError("Amount must be greater than zero")
    return n
def amount(c):return f"{Decimal(int(c))/Decimal(100):,.2f}"
def valid_date(raw):
    try:d=date.fromisoformat(str(raw or date.today().isoformat()))
    except ValueError:raise ValueError("Enter a valid transaction date")
    if d>date.today():raise ValueError("Transaction date cannot be in the future")
    return d.isoformat()
def init(con):
    con.executescript(DDL + CASH_COUNT_DDL)
    con.execute("INSERT OR IGNORE INTO money_accounts(name,kind) VALUES('Cash','cash')")
    con.execute("INSERT OR IGNORE INTO money_accounts(name,kind) VALUES('Business bank','bank')")
    # Existing customer receipts from older El Grande versions are brought in
    # exactly once. The register is not a second AR/invoice posting mechanism.
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='customer_payments'").fetchone():
        for p in con.execute("""SELECT id,paid_on,method,applied,reference,voided_at
                                 FROM customer_payments ORDER BY id""").fetchall():
            import_payment(con,p)
def accounts(con):
    return con.execute("""SELECT a.*,(a.opening_cents+COALESCE(
       (SELECT SUM(e.amount_cents) FROM money_entries e WHERE e.account_id=a.id),0
       )) AS balance_cents FROM money_accounts a WHERE active=1 ORDER BY
        CASE a.kind WHEN 'cash' THEN 0 ELSE 1 END,a.id""").fetchall()
def entry(con,account_id,date_text,amount_cents,category,memo="",reference="",
          source="manual",source_key=None,reversal_of=None):
    a=con.execute("SELECT id FROM money_accounts WHERE id=? AND active=1",(account_id,)).fetchone()
    if not a:raise ValueError("Select an existing account")
    if not amount_cents:raise ValueError("Amount must be nonzero")
    if not re.fullmatch(r"[a-z0-9_]{2,36}",category):
        raise ValueError("Invalid category")
    if len(str(memo))>300 or len(str(reference))>100:
        raise ValueError("Description is too long")
    return con.execute("""INSERT INTO money_entries
      (account_id,entry_date,amount_cents,category,memo,reference,source,source_key,created_at,reversal_of)
      VALUES (?,?,?,?,?,?,?,?,?,?)""",
      (account_id,valid_date(date_text),amount_cents,category,
       str(memo),str(reference),source,source_key,utc(),reversal_of)).lastrowid
def record(con,data):
    account_id=int(data.get("account_id",0))
    direction=str(data.get("direction","")).strip()
    if direction not in ("in","out"):raise ValueError("Choose money in or money out")
    n=cents(data.get("amount",""),positive=True)
    if direction=="out":n=-n
    category="manual_income" if n>0 else "manual_expense"
    return entry(con,account_id,data.get("entry_date"),n,category,
                 data.get("memo",""),data.get("reference",""))
def transfer(con,data):
    source=int(data.get("from_account",0))
    dest=int(data.get("to_account",0))
    if source==dest:raise ValueError("Choose two different accounts")
    n=cents(data.get("amount"),positive=True)
    stamp=utc()
    memo=str(data.get("memo",""))[:300]
    when=valid_date(data.get("entry_date"))
    # Both sides are committed in the same SQLite transaction.
    sent=entry(con,source,when,-n,"transfer_out",memo,source="manual")
    received=entry(con,dest,when,n,"transfer_in",memo,source="manual")
    return sent,received
def account_for_payment(con,method):
    kind="cash" if method=="cash" else "bank"
    a=con.execute("""SELECT id FROM money_accounts WHERE kind=? AND active=1
                   ORDER BY CASE WHEN provider='' THEN 0 ELSE 1 END,id LIMIT 1""",(kind,)).fetchone()
    if not a:raise ValueError("No account available for customer payment")
    return a["id"]
def import_payment(con,p):
    # Payments are recorded as receipts; voiding introduces a compensating
    # entry instead of erasing original cashbook history.
    pid=int(p["id"])
    acc=account_for_payment(con,p["method"])
    amt=cents(p["applied"])
    if amt<=0:return
    key=f"customer-{pid}"
    existing=con.execute("SELECT id FROM money_entries WHERE source='customer' AND source_key=?",(key,)).fetchone()
    if not existing:
        entry(con,acc,p["paid_on"],amt,"customer_receipt",
              f"Customer payment #{pid}",p["reference"] or "",
              "customer",key)
    if p["voided_at"]:
        orig=con.execute("SELECT id,account_id,amount_cents FROM money_entries WHERE source='customer' AND source_key=?",(key,)).fetchone()
        reversed_key=f"customer-void-{pid}"
        if orig:
            entry(con,orig["account_id"],p["voided_at"][:10],
                  -int(orig["amount_cents"]),"customer_correction",
                  f"Voided customer payment #{pid}",source="customer",
                  source_key=reversed_key,reversal_of=orig["id"])
def recent_entries(con,limit=120):
    return con.execute("""SELECT e.*,a.name account_name FROM money_entries e
      JOIN money_accounts a ON a.id=e.account_id
      ORDER BY e.entry_date DESC,e.id DESC LIMIT ?""",(limit,)).fetchall()
def rename_account(con,account_id,label):
    label=str(label).strip()
    if not label or len(label)>80:raise ValueError("Enter an account name (up to 80 characters)")
    row=con.execute("SELECT id FROM money_accounts WHERE id=?",(account_id,)).fetchone()
    if not row:raise ValueError("Account not found")
    con.execute("UPDATE money_accounts SET name=? WHERE id=?",(label,account_id))
def new_account(con,label):
    label=str(label).strip()
    if not label or len(label)>80:raise ValueError("Enter a name for the account")
    return con.execute("INSERT INTO money_accounts(name,kind) VALUES(?,'bank')",(label,)).lastrowid
def imported(con,account_id,provider,transaction):
    ext=str(transaction.get("transaction_id") or "")
    if not ext or len(ext)>180:raise ValueError("Invalid provider transaction ID")
    raw=transaction.get("amount",0)
    # Plaid uses positive numbers for outflows, negative for inflows.
    n=-cents(raw)
    label=str(transaction.get("merchant_name") or transaction.get("name") or "")[:300]
    when=str(transaction.get("date") or "")
    valid_date(when)
    con.execute("""INSERT INTO bank_feed
       (account_id,provider,external_id,entry_date,amount_cents,description,pending,imported_at)
       VALUES (?,?,?,?,?,?,?,?)
       ON CONFLICT(provider,external_id) DO UPDATE SET
       entry_date=excluded.entry_date,amount_cents=excluded.amount_cents,
       description=excluded.description,pending=excluded.pending""",
       (account_id,provider,ext,when,n,label,int(bool(transaction.get("pending"))),utc()))
def feed(con,account_id,limit=100):
    return con.execute("""SELECT * FROM bank_feed WHERE account_id=?
       ORDER BY entry_date DESC,id DESC LIMIT ?""",(account_id,limit)).fetchall()

def feed_record(con,feed_id):
    item=con.execute("SELECT * FROM bank_feed WHERE id=?",(feed_id,)).fetchone()
    if not item:raise LookupError("Imported bank transaction not found")
    if item["linked_entry_id"]:raise ValueError("This bank transaction is already recorded")
    # Pending transactions may disappear or change; wait for a finalized record.
    if item["pending"]:raise ValueError("Wait until the bank transaction is posted")
    n=int(item["amount_cents"])
    if not n:raise ValueError("Zero dollar transaction")
    id_=entry(con,int(item["account_id"]),item["entry_date"],n,
              "bank_receipt" if n>0 else "bank_expense",item["description"],
              source="bank_import",source_key=item["external_id"])
    con.execute("UPDATE bank_feed SET linked_entry_id=? WHERE id=?",(id_,feed_id))
    return id_
def feed_match(con,feed_id,entry_id):
    item=con.execute("SELECT * FROM bank_feed WHERE id=?",(feed_id,)).fetchone()
    target=con.execute("SELECT * FROM money_entries WHERE id=?",(entry_id,)).fetchone()
    if not item or not target:raise LookupError("Imported bank activity or register entry not found")
    if item["linked_entry_id"]:raise ValueError("That bank transaction is already matched")
    if item["pending"]:raise ValueError("Wait until the bank posts this transaction")
    if item["account_id"]!=target["account_id"] or item["amount_cents"]!=target["amount_cents"]:
        raise ValueError("The selected register entry must match account and amount")
    prior=con.execute("SELECT id FROM bank_feed WHERE linked_entry_id=?",(entry_id,)).fetchone()
    if prior:raise ValueError("This register entry already has a bank match")
    con.execute("UPDATE bank_feed SET linked_entry_id=? WHERE id=?",(entry_id,feed_id))
    return entry_id
