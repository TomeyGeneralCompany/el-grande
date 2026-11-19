"""Background synchronization of completed shop jobs into native BlueSeer records.

Transaction ordering:
  1. Local completed job is committed and never lost on ERP outage.
  2. Deterministic customer code is created or verified through native API.
  3. Native service order is posted/verified using a deterministic order number.
  4. Only then is local blue_sync marked synced.

Native invoice/AR/GL entries are posted on completion; receipts are applied
automatically by erp_receipts after the invoice is confirmed.
"""
import json
import logging
import os
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import blue_bridge
import customer_bridge
import invoice_bridge

LOG=logging.getLogger("el-grande.erp")
DDL="""
CREATE TABLE IF NOT EXISTS erp_jobs (
 ticket_id INTEGER PRIMARY KEY,
 state TEXT NOT NULL DEFAULT 'queued',
 attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT ''
);
"""
def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def enqueue(con,ticket_id):
    con.execute("""INSERT OR IGNORE INTO erp_jobs
     (ticket_id,state,attempts,next_attempt_at,updated_at)
     VALUES (?,'queued',0,'',?)""",(ticket_id,utc()))

def eligible():
    return os.getenv("ABD_BLUESEER_CONNECTED")=="yes" and all(
        os.getenv(key) for key in blue_bridge.REQUIRED)

def process_once(database,calculate):
    if not eligible():return 0
    now=utc()
    with database() as con:
        # Recover an interrupted worker rather than silently losing a job.
        old=(datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat(timespec="seconds")
        con.execute("""UPDATE erp_jobs SET state='failed',next_attempt_at=''
             WHERE state='processing' AND updated_at<?""",(old,))
        queued=con.execute("""SELECT ticket_id,attempts FROM erp_jobs
            WHERE state IN ('queued','failed') AND next_attempt_at<=?
            ORDER BY ticket_id LIMIT 1""",(now,)).fetchone()
        if queued is None:return 0
        ticket_id=int(queued["ticket_id"])
        attempts=int(queued["attempts"])+1
        con.execute("""UPDATE erp_jobs SET state='processing',
             attempts=?,updated_at=? WHERE ticket_id=?""",(attempts,now,ticket_id))
    try:
        with database() as con:
            row=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
            if not row or not row["finalized_at"]:
                raise ValueError("Job is not finalized")
            amount=calculate(row)
            # The finalized customer bill is authoritative. Native order and
            # invoice lines are both built from this amount, not draft prices.
            if Decimal(str(amount["basis"]))<=0:
                raise ValueError("A zero-dollar completed job has no invoice to post")
        client=blue_bridge.BlueSeerClient()
        customer= row["blue_customer"]
        if not customer:
            customer,kind=customer_bridge.upsert_customer(row,client)
            with database() as con:
                con.execute("UPDATE tickets SET blue_customer=?,blue_ship_to=? WHERE id=?",
                            (customer,customer,ticket_id))
                con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                            (ticket_id,utc(),"blueseer_customer_"+kind,customer))
                row=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        key,kind=blue_bridge.submit_service_order(row,amount,client)
        with database() as con:
            con.execute("""INSERT INTO blue_sync(ticket_id,kind,record_number,state,updated_at,detail)
             VALUES (?,'service_order',?,'synced',?,?)
             ON CONFLICT(ticket_id,kind) DO UPDATE SET
             record_number=excluded.record_number,state='synced',
             updated_at=excluded.updated_at,detail=excluded.detail""",
             (ticket_id,key,utc(),kind))
            con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                        (ticket_id,utc(),"blueseer_service_order",key))
            # This row acts as a durable commit barrier. An interrupted or
            # ambiguous native invoice cannot be automatically re-posted.
            prior=con.execute("SELECT record_number,state FROM blue_sync WHERE ticket_id=? AND kind='invoice'",
                              (ticket_id,)).fetchone()
            if prior:
                if prior["state"]=="posted":
                    con.execute("UPDATE erp_jobs SET state='posted',updated_at=?,last_error='' WHERE ticket_id=?",
                                (utc(),ticket_id))
                    return 1
                con.execute("UPDATE erp_jobs SET state='needs_review',updated_at=?,last_error=? WHERE ticket_id=?",
                            (utc(),"Previous invoice outcome requires native reconciliation",ticket_id))
                return 0
        # Reserve a native shipment number then commit that reservation locally
        # *before* transmitting any invoice data to the ERP.
        native_id=invoice_bridge.reserve_native_shipment_number(client)
        with database() as con:
            con.execute("""INSERT INTO blue_sync(ticket_id,kind,record_number,state,updated_at,detail)
                         VALUES (?, 'invoice', ?, 'reserved', ?, 'Automatic final-bill invoice')
                         """,(ticket_id,native_id,utc()))
        try:
            invoice_bridge.post_native_invoice(row,amount,native_id,client)
        except Exception:
            with database() as con:
                con.execute("""UPDATE blue_sync SET state='unknown',updated_at=?,
                             detail='Native invoice outcome requires reconciliation' 
                             WHERE ticket_id=? AND kind='invoice'""",(utc(),ticket_id))
            raise
        with database() as con:
            con.execute("""UPDATE blue_sync SET state='posted',updated_at=?,
                          detail='Native invoice / AR-GL confirmed' 
                          WHERE ticket_id=? AND kind='invoice'""",(utc(),ticket_id))
            con.execute("UPDATE erp_jobs SET state='posted',updated_at=?,last_error='' WHERE ticket_id=?",
                        (utc(),ticket_id))
            con.execute("UPDATE tickets SET status='invoiced',updated_at=? WHERE id=? AND status!='paid'",
                        (utc(),ticket_id))
            con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                        (ticket_id,utc(),"blueseer_native_invoice",native_id))
        return 1
    except Exception as err:
        # Do not discard a finalized job. API responses may have succeeded
        # remotely even if a response was lost; retry checks native records.
        reason=str(err)[:300]
        # A reserved/unknown invoice can never be automatically replayed:
        # BlueSeer may have received the original commit despite an error.
        with database() as con:
            inv=con.execute("SELECT state FROM blue_sync WHERE ticket_id=? AND kind='invoice'",
                            (ticket_id,)).fetchone()
        state=("needs_review" if (inv and inv["state"]!="posted") or
               isinstance(err,ValueError) else "failed")
        backoff=min(3600,60*(2**min(attempts,6)))
        retry=(datetime.now(timezone.utc)+timedelta(seconds=backoff)).isoformat(timespec="seconds")
        with database() as con:
            con.execute("""UPDATE erp_jobs SET state=?,next_attempt_at=?,updated_at=?,last_error=?
                         WHERE ticket_id=?""",(state,retry,utc(),reason,ticket_id))
        LOG.warning("ERP sync deferred for job %s: %s",ticket_id,reason)
        return 0
