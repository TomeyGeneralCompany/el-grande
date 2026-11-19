"""Background synchronization of completed shop jobs into native BlueSeer records.

Transaction ordering:
  1. Local completed job is committed and never lost on ERP outage.
  2. Deterministic customer code is created or verified through native API.
  3. Native service order is posted/verified using a deterministic order number.
  4. Only then is local blue_sync marked synced.

No automatic GL invoice or customer message is sent here.
"""
import json
import logging
import os
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import blue_bridge
import customer_bridge

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
            # The native ERP source documents must match actual customer billing.
            if Decimal(str(amount["total"]))!=Decimal(str(amount["basis"])):
                raise ValueError("Actual invoice and job estimate differ; review before ERP order")
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
            con.execute("UPDATE erp_jobs SET state='synced',updated_at=?,last_error='' WHERE ticket_id=?",
                        (utc(),ticket_id))
            con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                        (ticket_id,utc(),"blueseer_service_order",key))
        return 1
    except Exception as err:
        # Do not discard a finalized job. API responses may have succeeded
        # remotely even if a response was lost; retry checks native records.
        reason=str(err)[:300]
        state="needs_review" if isinstance(err,ValueError) else "failed"
        backoff=min(3600,60*(2**min(attempts,6)))
        retry=(datetime.now(timezone.utc)+timedelta(seconds=backoff)).isoformat(timespec="seconds")
        with database() as con:
            con.execute("""UPDATE erp_jobs SET state=?,next_attempt_at=?,updated_at=?,last_error=?
                         WHERE ticket_id=?""",(state,retry,utc(),reason,ticket_id))
        LOG.warning("ERP sync deferred for job %s: %s",ticket_id,reason)
        return 0
