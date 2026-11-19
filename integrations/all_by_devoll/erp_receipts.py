"""Apply El Grande customer receipts to the corresponding native BlueSeer AR invoice.

Native dataServFAR.addArTransaction('ARPayment') updates the invoice's open
balance and posts a corresponding native GL transaction. Every local receipt
has a deterministic ERP payment number. Once a remote call begins, its outcome
is never blindly replayed: read-back/reconciliation precedes any further work.
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import blue_bridge

LOG=logging.getLogger("el-grande.ar-payments")
DDL="""
CREATE TABLE IF NOT EXISTS erp_receipts (
 payment_id INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('payment','reversal')),
 state TEXT NOT NULL DEFAULT 'queued',
 number TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(payment_id,kind)
);
"""
AR_FIELDS=("ar_id","ar_nbr","ar_cust","ar_amt","ar_base_amt","ar_type",
           "ar_curr","ar_base_curr","ar_ref","ar_rmks","ar_entdate",
           "ar_effdate","ar_paiddate","ar_acct","ar_cc","ar_status","ar_bank",
           "ar_site","ar_amt_tax","ar_base_amt_tax","ar_amt_disc",
           "ar_base_amt_disc","ar_open_amt","ar_applied","ar_terms",
           "ar_tax_code","ar_invdate","ar_duedate","ar_discdate",
           "ar_reverse","ar_termsdisc_amt","ar_termsdisc_pct",
           "ar_termsdisc_days")
ARD_FIELDS=("ard_nbr","ard_line","ard_cust","ard_ref","ard_date",
            "ard_amt","ard_amt_tax","ard_base_amt","ard_base_amt_tax",
            "ard_curr","ard_base_curr","ard_acct","ard_cc","ard_deduction")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def number(payment_id,kind):
    pid=int(payment_id)
    if not 0<pid<100000000:raise ValueError("Payment number outside native ERP reserved range")
    return str((700000000 if kind=="payment" else 600000000)+pid)

def init_queue(con):
    con.executescript(DDL)
    # Migrate previously recorded cash/check payments so older jobs receive the
    # same native AR accounting treatment without new operator input.
    con.execute("""INSERT OR IGNORE INTO erp_receipts(payment_id,kind,number,updated_at)
      SELECT id,'payment', CAST(700000000+id AS TEXT), ? FROM customer_payments
      WHERE id>0 AND id<100000000 AND voided_at IS NULL""",(now(),))
    # Voided payments that never reached native AR need no accounting entry.
    # Voided payments already posted are reversed using a separate transaction.
    con.execute("""INSERT OR IGNORE INTO erp_receipts(payment_id,kind,number,updated_at)
      SELECT p.id,'reversal',CAST(600000000+p.id AS TEXT),?
      FROM customer_payments p JOIN erp_receipts r ON r.payment_id=p.id
      WHERE p.voided_at IS NOT NULL AND r.kind='payment' AND r.state='posted'""",(now(),))
    con.execute("""UPDATE erp_receipts SET state='cancelled',updated_at=?
       WHERE kind='payment' AND state='queued'
       AND payment_id IN (SELECT id FROM customer_payments WHERE voided_at IS NOT NULL)""",(now(),))

def queue_payment(con,payment_id):
    con.execute("""INSERT OR IGNORE INTO erp_receipts(payment_id,kind,number,updated_at)
                   VALUES (?,'payment',?,?)""",
                (payment_id,number(payment_id,"payment"),now()))

def queue_void(con,payment_id):
    original=con.execute("""SELECT state FROM erp_receipts
                         WHERE payment_id=? AND kind='payment'""",(payment_id,)).fetchone()
    if original and original["state"]=="queued":
        con.execute("""UPDATE erp_receipts SET state='cancelled',updated_at=?
          WHERE payment_id=? AND kind='payment'""",(now(),payment_id))
    elif original and original["state"]=="posted":
        con.execute("""INSERT OR IGNORE INTO erp_receipts
          (payment_id,kind,number,updated_at) VALUES (?,'reversal',?,?)""",
          (payment_id,number(payment_id,"reversal"),now()))
    # posting/needs_review stays in reconciliation state and is never replayed.

def native_ar(client,key):
    result=client.call("dataServFAR","getARMstrSet",param1=str(key))
    if not isinstance(result,dict):raise blue_bridge.BridgeError("Invalid native AR lookup")
    ar=result.get("ar")
    if not isinstance(ar,dict) or str(ar.get("ar_nbr") or "")!=str(key):
        return None,None
    return ar,result.get("ard") or []

def as_money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))

def check_record(client,reference,customer,invoice_no,value,required=False):
    master,details=native_ar(client,reference)
    if master is None:
        if required:raise blue_bridge.BridgeError("Native AR payment was not confirmed")
        return False
    if master.get("ar_type")!="P" or master.get("ar_cust")!=customer:
        raise blue_bridge.BridgeError("Native AR payment reference belongs to another transaction")
    applied=sum((as_money(x.get("ard_amt")) for x in details
                if str(x.get("ard_ref"))==str(invoice_no)),Decimal("0"))
    if applied!=value or len(details)!=1:
        raise blue_bridge.BridgeError("Native AR payment details do not reconcile")
    return True

def post(client,receipt,invoice_no,invoice_customer,bank_code,kind):
    amount=as_money(receipt["applied"])
    if amount<=0:raise ValueError("Receipt must be positive")
    if kind=="reversal":amount=-amount
    payment_no=number(receipt["id"],kind)
    source,details=native_ar(client,invoice_no)
    if source is None:raise ValueError("Native BlueSeer customer invoice is missing")
    if source.get("ar_type")!="I" or source.get("ar_cust")!=invoice_customer:
        raise ValueError("Native invoice/customer mismatch")
    if source.get("ar_curr")!="USD":raise ValueError("Native invoice currency is not USD")
    if source.get("ar_status") not in ("o","c"):
        raise ValueError("Native invoice state is invalid")
    if as_money(source.get("ar_amt"))<=0:
        raise ValueError("Native customer invoice does not contain a positive bill")
    if check_record(client,payment_no,invoice_customer,invoice_no,amount):
        return payment_no
    open_amount=as_money(source.get("ar_open_amt"))
    if kind=="payment" and (open_amount<amount or source.get("ar_status")!="o"):
        raise ValueError("Native invoice outstanding balance does not cover this receipt")
    if kind=="reversal" and source.get("ar_status") not in ("o","c"):
        raise ValueError("Native invoice cannot be reversed")
    bank=client.call("dataServFIN","getBankMstr",key=bank_code)
    if not isinstance(bank,dict) or bank.get("id")!=bank_code or not bank.get("account"):
        raise ValueError("BlueSeer payment account is not configured")
    customer=client.get("dataServCUS","getCustMstr",invoice_customer)
    if not isinstance(customer,dict) or customer.get("cm_code")!=invoice_customer or not customer.get("cm_ar_acct"):
        raise ValueError("Native customer AR account is not configured")
    dated=receipt["paid_on"]
    ref=(receipt["reference"] or ("Cash" if receipt["method"]=="cash" else receipt["method"]))[:100]
    header=blue_bridge.record(AR_FIELDS,
       ar_id=None,ar_nbr=payment_no,ar_cust=invoice_customer,ar_amt=float(amount),
       ar_base_amt=float(amount),ar_type="P",ar_curr="USD",ar_base_curr="USD",
       ar_ref=ref,ar_rmks="All by Devoll receipt "+str(receipt["id"])+(" void" if kind=="reversal" else ""),
       ar_entdate=dated,ar_effdate=dated,ar_paiddate=dated,
       ar_acct=customer["cm_ar_acct"],ar_cc=customer.get("cm_ar_cc") or "",
       ar_status="c",ar_bank=bank_code,ar_site=os.environ["ABD_BLUESEER_SITE"],
       ar_amt_tax=0.0,ar_base_amt_tax=0.0,ar_amt_disc=0.0,
       ar_base_amt_disc=0.0,ar_open_amt=0.0,ar_applied="0",
       ar_terms="",ar_tax_code="",ar_invdate="",ar_duedate="",ar_discdate="",
       ar_reverse="0",ar_termsdisc_amt=0.0,ar_termsdisc_pct=0.0,ar_termsdisc_days=0)
    detail=blue_bridge.record(ARD_FIELDS,
       ard_nbr=payment_no,ard_line=1,ard_cust=invoice_customer,
       ard_ref=invoice_no,ard_date=dated,ard_amt=float(amount),
       ard_amt_tax=0.0,ard_base_amt=float(amount),ard_base_amt_tax=0.0,
       ard_curr="USD",ard_base_curr="USD",
       ard_acct=customer["cm_ar_acct"],ard_cc=customer.get("cm_ar_cc") or "",
       ard_deduction=0.0)
    client.post("dataServFAR","addArTransaction",
                "ARPayment=_="+json.dumps([detail])+"=_="+json.dumps(header))
    check_record(client,payment_no,invoice_customer,invoice_no,amount,required=True)
    return payment_no

def process_once(db):
    if not os.getenv("ABD_BLUESEER_CONNECTED")=="yes":
        return 0
    with db() as con:
        init_queue(con)
        item=con.execute("""SELECT q.payment_id,q.kind,q.state,q.number,
                       p.ticket_id,p.applied,p.method,p.paid_on,p.reference,p.voided_at,
                       b.record_number AS invoice_no,b.state AS invoice_state,
                       t.blue_customer AS customer
                       FROM erp_receipts q
                       JOIN customer_payments p ON p.id=q.payment_id
                       JOIN tickets t ON t.id=p.ticket_id
                       LEFT JOIN blue_sync b ON b.ticket_id=p.ticket_id AND b.kind='invoice'
                       WHERE q.state IN ('queued','posting','needs_review')
                         AND b.state='posted'
                       ORDER BY q.payment_id,CASE WHEN q.kind='payment' THEN 0 ELSE 1 END
                       LIMIT 1""").fetchone()
        if not item:return 0
        payment_id,kind=item["payment_id"],item["kind"]
        if kind=="reversal":
            prior=con.execute("""SELECT state FROM erp_receipts
                              WHERE payment_id=? AND kind='payment'""",(payment_id,)).fetchone()
            if not prior or prior["state"]!="posted":return 0
        if kind=="payment" and item["voided_at"] and item["state"]=="queued":
            queue_void(con,payment_id)
            return 0
        con.execute("""UPDATE erp_receipts SET state='posting',
           attempts=attempts+1,updated_at=? WHERE payment_id=? AND kind=?""",
           (now(),payment_id,kind)) if item["state"]=="queued" else None
    try:
        client=blue_bridge.BlueSeerClient()
        amount=as_money(item["applied"])*(Decimal("-1") if kind=="reversal" else Decimal("1"))
        if item["state"]!="queued":
            if not check_record(client,item["number"],item["customer"],item["invoice_no"],amount):
                with db() as con:
                    con.execute("""UPDATE erp_receipts SET state='needs_review',
                     last_error='Native payment not found after an interrupted post',
                     updated_at=? WHERE payment_id=? AND kind=?""",(now(),payment_id,kind))
                return 0
        else:
            post(client,item,item["invoice_no"],item["customer"],
                 os.getenv("ABD_BLUESEER_PAYMENT_BANK","BK"),kind)
        with db() as con:
            con.execute("""UPDATE erp_receipts SET state='posted',last_error='',updated_at=?
                     WHERE payment_id=? AND kind=?""",(now(),payment_id,kind))
            con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                        (item["ticket_id"],now(),"blueseer_payment_"+kind,item["number"]))
            if kind=="payment" and item["voided_at"]:
                queue_void(con,payment_id)
        return 1
    except Exception as exc:
        with db() as con:
            con.execute("""UPDATE erp_receipts SET state='needs_review',last_error=?,
                      updated_at=? WHERE payment_id=? AND kind=?""",
                      (str(exc)[:250],now(),payment_id,kind))
        LOG.warning("Native AR payment %s needs reconciliation: %s",item["number"],exc)
        return 0
