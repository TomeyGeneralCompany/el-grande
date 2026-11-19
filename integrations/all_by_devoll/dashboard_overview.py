"""Live El Grande dashboard panels; all figures originate in local shop records."""
import html
from datetime import date,datetime
from decimal import Decimal
from itertools import groupby
from zoneinfo import ZoneInfo
import bank_ledger
import job_calendar

def e(x):return html.escape(str(x if x is not None else ""),quote=True)
def money(value):return "$"+format(Decimal(value),",.2f")
def local_day(value):
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo:dt=dt.astimezone(ZoneInfo("America/Detroit"))
        return dt.date()
    except (ValueError,TypeError):return None
def pair_rows(rows):
    return '<div class="overview-rows overview-money-grid">'+''.join(
       '<strong>'+e(a)+'</strong><span class="overview-money">'+e(b)+'</span>'
       for a,b in rows)+'</div>'
def render(con, amounts, calendar_month="", edit_appointment=""):
    today=job_calendar.today()
    counts=con.execute("""SELECT COUNT(*) AS total,
        COUNT(*) FILTER (WHERE COALESCE(finalized_at,'')='' AND status!='cancelled') AS open,
        COUNT(*) FILTER (WHERE COALESCE(finalized_at,'')='' AND status NOT IN ('cancelled','paid')) AS pending,
        COUNT(*) FILTER (WHERE COALESCE(finalized_at,'')!='') AS completed,
        COUNT(*) FILTER (WHERE status IN ('in_progress','approved')) AS active_work,
        COUNT(*) FILTER (WHERE status='new') AS new
        FROM tickets""").fetchone()
    active=con.execute("""SELECT id,customer,machine,service,problem,status,received_at
        FROM tickets WHERE COALESCE(finalized_at,'')='' AND status!='cancelled'
        ORDER BY (status IN ('in_progress','approved')) DESC,id DESC LIMIT 1""").fetchone()
    payments=con.execute("""SELECT applied,method FROM customer_payments
        WHERE paid_on=? AND voided_at IS NULL""",(today.isoformat(),))
    paid=daily_cash=Decimal("0")
    for payment in payments:
        value=Decimal(payment["applied"])
        paid+=value
        if payment["method"]=="cash":
            daily_cash+=value
    # Decimal strings remain exact, including historical records. Stream each
    # ticket's payment rows via one query and clamp overpayments per invoice.
    ledger=con.execute("""SELECT t.id,t.finalized_at,t.bill_total,t.labor_hours,t.labor_rate,
        t.parts_charge,t.travel_charge,t.extra_charge,t.parts_cost,p.applied
        FROM tickets t LEFT JOIN customer_payments p
        ON p.ticket_id=t.id AND p.voided_at IS NULL
        WHERE COALESCE(t.finalized_at,'')!='' ORDER BY t.id""")
    outstanding=billed=parent=Decimal("0")
    for _, entries in groupby(ledger, key=lambda row: row["id"]):
        first=next(entries)
        received=Decimal(first["applied"] or "0")
        received+=sum((Decimal(entry["applied"]) for entry in entries),Decimal("0"))
        outstanding+=max(Decimal("0"),Decimal(first["bill_total"] or "0")-received)
        if local_day(first["finalized_at"])==today:
            value=amounts(first)
            billed+=value["basis"]
            parent+=value["parent"]
    accounts=bank_ledger.accounts(con)
    cash=sum(int(x["balance_cents"]) for x in accounts if x["kind"]=="cash")
    bank=sum(int(x["balance_cents"]) for x in accounts if x["kind"]=="bank")
    activity=con.execute("""SELECT e.timestamp,e.event,e.detail,t.customer
        FROM events e LEFT JOIN tickets t ON t.id=e.ticket_id
        ORDER BY e.id DESC LIMIT 5""").fetchall()
    recent_counts=bank_ledger.recent_cash_counts(con,1)
    metrics=[("Open jobs",counts["pending"]),("New requests",counts["new"]),
             ("Active work",counts["active_work"]),("Completed jobs",counts["completed"]),
             ("Cash received today",money(daily_cash))]
    if active:
        fields=[("Customer",active["customer"] or "Not entered"),
                ("Vehicle",active["machine"] or "Not entered"),
                ("Service",active["service"] or active["problem"] or "Not entered"),
                ("Status",active["status"].replace("_"," ").title()),
                ("Received",local_day(active["received_at"]) or "—")]
        current='<div class="overview-rows">'+''.join(
                '<strong>'+e(k)+'</strong><span>'+e(v)+'</span>' for k,v in fields
                )+'</div><p><a href="/ticket/'+str(active["id"])+'">View job</a></p>'
    else:current='<p>No active jobs. New customer requests appear here.</p>'
    glance=pair_rows([("Jobs (total)",counts["total"]),
       ("Jobs (open)",counts["open"]),
       ("Jobs (completed)",counts["completed"]),
       ("Invoiced today",money(billed)),("Paid today",money(paid)),
       ("Tomey General (15%)",money(parent)),
       ("Operator (85%)",money(billed-parent))])
    financial=pair_rows([("Cash (safe)",money(Decimal(cash)/100)),
       ("Bank (recorded)",money(Decimal(bank)/100)),
       ("Total recorded funds",money(Decimal(cash+bank)/100)),
       ("Unpaid customer invoices",money(outstanding))])
    actions=[]
    for event in activity:
        name=str(event["event"] or "").replace("_"," ").capitalize()
        description=str(event["detail"] or "")[:140]
        customer=str(event["customer"] or "")
        actions.append((local_day(event["timestamp"]) or date.min,
              e(name)+(" — "+e(customer) if customer else "")+
                      (" — "+e(description) if description else "")))
    if recent_counts:
        latest=recent_counts[0]
        delta=Decimal(latest["variance_cents"])/100
        actions.append((local_day(latest["recorded_at"]) or date.min,
                        "Safe count recorded — "+money(Decimal(latest["counted_cents"])/100)+
                        " (difference "+format(delta,"+,.2f")+")"))
    actions.sort(key=lambda row:row[0],reverse=True)
    recent='<ul class="dashboard-activity">'+''.join('<li>'+text+'</li>' for _,text in actions[:6])+'</ul>' if actions else '<p>No recent activity.</p>'
    return ('<div id="dashboard" class="dashboard-overview">'
        '<section class="panel"><h2>Current Job</h2>'+current+'</section>'
        '<section class="panel"><h2>Today at a Glance</h2>'+glance+'</section>'
        +job_calendar.render(con,calendar_month,edit_appointment)+
        '<section class="panel"><h2>Financial Summary</h2>'+financial+'</section>'
        '<section class="panel"><h2>Recent Activity</h2>'+recent+'</section>'
        '</div>'), metrics
