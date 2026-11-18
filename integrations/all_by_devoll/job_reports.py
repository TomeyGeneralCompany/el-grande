"""Completion records and owner notification for the All by Devoll job desk.

No customer email is sent. Delivery uses authenticated SMTP from the business
mailbox and an explicitly configured owner-report destination.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
import os
import smtplib
import ssl
from urllib.parse import urlencode

DDL = """
CREATE TABLE IF NOT EXISTS job_completions (
 ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),
 work_performed TEXT NOT NULL,
 started_at TEXT NOT NULL DEFAULT '',
 finished_at TEXT NOT NULL DEFAULT '',
 actual_hours TEXT NOT NULL,
 actual_labor_cost TEXT NOT NULL,
 actual_parts_cost TEXT NOT NULL,
 actual_other_cost TEXT NOT NULL,
 actual_invoice TEXT NOT NULL,
 completed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_reports (
 ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),
 state TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,
 sent_at TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT ''
);
"""
CENT=Decimal(".01")
def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def decimal(value,*,max_value="100000000"):
    try: d=Decimal(str(value))
    except (InvalidOperation,TypeError) as exc:raise ValueError("Invalid job amount") from exc
    if not d.is_finite() or d<0 or d>Decimal(max_value):
        raise ValueError("Job amount out of range")
    return d.quantize(CENT,rounding=ROUND_HALF_UP)

def validate(data):
    work=str(data.get("work_performed","")).strip()
    if not work or len(work)>8000:
        raise ValueError("A work-performed description is required (max 8,000 characters)")
    amounts={k:decimal(data.get(k,"0"),max_value="10000" if k=="actual_hours" else "100000000")
             for k in ("actual_hours","actual_labor_cost","actual_parts_cost","actual_other_cost","actual_invoice")}
    start=str(data.get("started_at","")).strip()
    finish=str(data.get("finished_at","")).strip()
    for value in (start,finish):
        if value:
            try:datetime.fromisoformat(value)
            except ValueError as exc:raise ValueError("Enter a valid date and time") from exc
    if start and finish and datetime.fromisoformat(start)>datetime.fromisoformat(finish):
        raise ValueError("Job finish time cannot precede start time")
    return dict(work_performed=work,started_at=start,finished_at=finish,**{k:str(v) for k,v in amounts.items()})

def save_completion(con,ticket_id,data):
    record=validate(data)
    prior=con.execute("SELECT id,finalized_at FROM tickets WHERE id=?",(ticket_id,)).fetchone()
    if not prior:raise LookupError("Ticket not found")
    if prior["finalized_at"]:raise ValueError("Finalized job is locked")
    now=utc()
    con.execute("""INSERT INTO job_completions(
        ticket_id,work_performed,started_at,finished_at,actual_hours,
        actual_labor_cost,actual_parts_cost,actual_other_cost,actual_invoice,completed_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ticket_id) DO UPDATE SET
        work_performed=excluded.work_performed,started_at=excluded.started_at,
        finished_at=excluded.finished_at,actual_hours=excluded.actual_hours,
        actual_labor_cost=excluded.actual_labor_cost,actual_parts_cost=excluded.actual_parts_cost,
        actual_other_cost=excluded.actual_other_cost,actual_invoice=excluded.actual_invoice,
        completed_at=excluded.completed_at""",
        (ticket_id,*(record[k] for k in ("work_performed","started_at","finished_at",
         "actual_hours","actual_labor_cost","actual_parts_cost","actual_other_cost","actual_invoice")),now))
    con.execute("UPDATE tickets SET updated_at=?,status='completed' WHERE id=?",(now,ticket_id))
    con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                (ticket_id,now,"completion_recorded","Operator entered actual job details"))
    return record

def queue_report(con,ticket_id):
    con.execute("""INSERT INTO owner_reports(ticket_id,state) VALUES(?,'pending')
        ON CONFLICT(ticket_id) DO NOTHING""",(ticket_id,))

def report_text(ticket,record,settlement):
    def money(n):return f"\${Decimal(str(n)):,.2f}"
    def h(label,value):return f"{label}: {value}"
    lines=[
        "ALL BY DEVOLL — COMPLETED JOB REPORT",
        "Internal notification to Tomey General Company",
        h("Ticket",f"ABD-{ticket['id']:06d}"),
        h("Customer",ticket["customer"]),
        h("Phone",ticket["phone"]),
        h("Service",ticket["service"]),
        h("Vehicle/equipment",ticket["machine"]),
        h("Job location",ticket["location"]),
        h("Work completed",record["work_performed"]),
        h("Started",record["started_at"] or "Not recorded"),
        h("Finished",record["finished_at"] or "Not recorded"),
        h("Actual hours worked",record["actual_hours"]),
        h("Actual labor COST (operator expense)",money(record["actual_labor_cost"])),
        h("Actual parts COST (operator expense)",money(record["actual_parts_cost"])),
        h("Other actual expenses",money(record["actual_other_cost"])),
        h("FINAL CUSTOMER INVOICE",money(record["actual_invoice"])),
        h("Tomey General 15% OFF THE TOP",money(settlement["parent"])),
        h("Operator 85% BEFORE EXPENSES",money(settlement["operator"])),
        h("Operator remainder after recorded costs",
          money(Decimal(str(settlement["operator"]))-
                sum(Decimal(str(record[k])) for k in ("actual_labor_cost","actual_parts_cost","actual_other_cost")))),
        h("Date finalized",ticket["finalized_at"]),
        "The 15% applies to the entire final customer bill BEFORE any expense.",
        "Payment status is operator-recorded, not bank-verified.",
    ]
    return "\n".join(lines)

def send_report(destination,subject,body):
    user=os.getenv("ABD_REPORT_SMTP_USER") or os.getenv("ABD_IMAP_USER","")
    password=os.getenv("ABD_REPORT_SMTP_APP_PASSWORD") or os.getenv("ABD_IMAP_APP_PASSWORD","")
    if not user or not password:
        raise RuntimeError("Configure business Gmail credentials for owner reports")
    msg=EmailMessage()
    msg["From"]=user
    msg["To"]=destination
    msg["Subject"]=subject
    msg.set_content(body)
    host=os.getenv("ABD_REPORT_SMTP_HOST","smtp.gmail.com")
    if host not in ("smtp.gmail.com",):
        raise RuntimeError("Only the configured Gmail SMTP service is supported")
    with smtplib.SMTP_SSL(host,465,context=ssl.create_default_context(),timeout=25) as server:
        server.login(user,password)
        server.send_message(msg)

def process_pending(database,math_fn,send_fn=send_report,limit=10):
    destination=os.getenv("ABD_OWNER_REPORT_TO","").strip()
    if not destination or "@" not in destination or "\n" in destination or "\r" in destination:
        return 0
    with database() as con:
        candidates=con.execute("""SELECT ticket_id FROM owner_reports
                    WHERE state IN ('pending','failed') AND attempts<10
                    ORDER BY ticket_id LIMIT ?""",(limit,)).fetchall()
    sent=0
    for item in candidates:
        ident=item["ticket_id"]
        with database() as con:
            # Claim each report; no concurrent worker should pick it up.
            claimed=con.execute("""UPDATE owner_reports SET state='sending',attempts=attempts+1
                        WHERE ticket_id=? AND state IN ('pending','failed')""",(ident,)).rowcount
            if not claimed:continue
            ticket=con.execute("SELECT * FROM tickets WHERE id=?",(ident,)).fetchone()
            record=con.execute("SELECT * FROM job_completions WHERE ticket_id=?",(ident,)).fetchone()
        if not ticket or not record or not ticket["finalized_at"]:
            with database() as con:
                con.execute("UPDATE owner_reports SET state='failed',last_error='Missing finalized job' WHERE ticket_id=?",(ident,))
            continue
        subject=f"All by Devoll completed job ABD-{ident:06d}"
        try:
            send_fn(destination,subject,report_text(ticket,record,math_fn(ticket)))
        except Exception as exc:
            with database() as con:
                con.execute("UPDATE owner_reports SET state='failed',last_error=? WHERE ticket_id=?",
                            (str(exc)[:300],ident))
        else:
            with database() as con:
                con.execute("UPDATE owner_reports SET state='sent',sent_at=?,last_error='' WHERE ticket_id=?",
                            (utc(),ident))
                con.execute("INSERT INTO events(ticket_id,timestamp,event,detail) VALUES(?,?,?,?)",
                            (ident,utc(),"owner_report_sent",destination))
            sent+=1
    return sent

def google_search_link(part_query,vehicle=""):
    """Explicit operator Google lookup, not an unverifiable scraped price."""
    q=" ".join([str(vehicle).strip(),str(part_query).strip(),"replacement part price"]).strip()
    if not q or len(q)>400:raise ValueError("Search term required (up to 400 characters)")
    return "https://www.google.com/search?"+urlencode({"q":q})
