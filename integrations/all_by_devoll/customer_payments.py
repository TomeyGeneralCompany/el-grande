"""Cash-first, append-only manual customer payment ledger for All by Devoll.

The final invoice is authoritative. Payments update the local cashbook.
Corrections are void entries, never deletion or rewriting.
"""
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
import bank_ledger

CENT=Decimal("0.01")
METHODS=("cash","check","card","bank_transfer","other")
DDL="""
CREATE TABLE IF NOT EXISTS customer_payments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 paid_on TEXT NOT NULL,
 method TEXT NOT NULL,
 tendered TEXT NOT NULL,
 applied TEXT NOT NULL,
 change_given TEXT NOT NULL,
 reference TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',
 recorded_at TEXT NOT NULL,
 voided_at TEXT,
 void_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS customer_payments_ticket_idx
 ON customer_payments(ticket_id,id);
"""
def money(value):
    try:
        n=Decimal(str(value).strip())
    except (InvalidOperation,ValueError):
        raise ValueError("Enter a valid payment amount")
    if not n.is_finite() or n<=0 or n>Decimal("100000000"):
        raise ValueError("Payment must be more than zero")
    if n.quantize(CENT,rounding=ROUND_HALF_UP)!=n:
        raise ValueError("Payment amount cannot have fractions of a cent")
    return n.quantize(CENT)
def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
def payments(con,ticket_id):
    return con.execute("""SELECT * FROM customer_payments
                          WHERE ticket_id=? ORDER BY id DESC""",(ticket_id,)).fetchall()
def balance(con,ticket_id):
    job=con.execute("SELECT bill_total,finalized_at FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not job:raise LookupError("Job does not exist")
    if not job["finalized_at"]:return {"invoice":Decimal("0"),"received":Decimal("0"),"due":Decimal("0")}
    total=Decimal(str(job["bill_total"]))
    rows=con.execute("""SELECT applied FROM customer_payments
                    WHERE ticket_id=? AND voided_at IS NULL""",(ticket_id,)).fetchall()
    received=sum((Decimal(str(r["applied"])) for r in rows),Decimal("0"))
    return {"invoice":total,"received":received,"due":total-received}
def _refresh_status(con,ticket_id):
    money_state=balance(con,ticket_id)
    if money_state["due"]==0 and money_state["invoice"]>0:
        status="paid"
    else:
        status="completed"
    con.execute("UPDATE tickets SET status=?,updated_at=? WHERE id=?",(status,utc(),ticket_id))
    return money_state
def record(con,ticket_id,data):
    job=con.execute("SELECT id,finalized_at FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not job:raise LookupError("Job does not exist")
    if not job["finalized_at"]:raise ValueError("Complete the job and enter the final bill before recording payment")
    method=str(data.get("method","cash") or "cash").strip()
    if method not in METHODS:raise ValueError("Select a valid payment method")
    tendered=money(data.get("amount_received",""))
    paid_on=str(data.get("paid_on","") or date.today().isoformat()).strip()
    try:
        actual=date.fromisoformat(paid_on)
    except ValueError as exc:raise ValueError("Enter a valid payment date") from exc
    if actual>date.today():raise ValueError("Payment date cannot be in the future")
    reference=str(data.get("reference","")).strip()
    notes=str(data.get("notes","")).strip()
    if len(reference)>100 or len(notes)>500 or any(x in reference for x in ("\n","\r")):
        raise ValueError("Payment reference or notes are too long")
    current=balance(con,ticket_id)
    if current["due"]<=0:raise ValueError("Invoice has already been paid in full")
    if method!="cash" and tendered>current["due"]:
        raise ValueError("Non-cash payment cannot exceed the outstanding balance")
    applied=min(tendered,current["due"])
    change=tendered-applied
    now=utc()
    cursor=con.execute("""INSERT INTO customer_payments
      (ticket_id,paid_on,method,tendered,applied,change_given,reference,notes,recorded_at)
      VALUES (?,?,?,?,?,?,?,?,?)""",
      (ticket_id,paid_on,method,str(tendered),str(applied),str(change),
       reference,notes,now))
    con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
       (ticket_id,now,"payment_recorded",
        "Payment #"+str(cursor.lastrowid)+": "+method+"; applied $"+str(applied)+
        "; change $"+str(change)+"; on "+paid_on))
    p=con.execute("SELECT * FROM customer_payments WHERE id=?",(cursor.lastrowid,)).fetchone()
    bank_ledger.import_payment(con,p)
    state=_refresh_status(con,ticket_id)
    return cursor.lastrowid,state
def void(con,ticket_id,payment_id,reason):
    reason=str(reason or "").strip()
    if len(reason)<4 or len(reason)>500:raise ValueError("Enter a reason (4–500 characters) for voiding this entry")
    row=con.execute("""SELECT id,voided_at FROM customer_payments
        WHERE id=? AND ticket_id=?""",(payment_id,ticket_id)).fetchone()
    if not row:raise LookupError("Payment not found")
    if row["voided_at"]:raise ValueError("Payment has already been voided")
    now=utc()
    con.execute("""UPDATE customer_payments
      SET voided_at=?,void_reason=? WHERE id=?""",(now,reason,payment_id))
    con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                (ticket_id,now,"payment_voided","Payment #"+str(payment_id)+": "+reason))
    p=con.execute('SELECT * FROM customer_payments WHERE id=?',(payment_id,)).fetchone()
    bank_ledger.import_payment(con,p)
    return _refresh_status(con,ticket_id)
