"""Live El Grande dashboard panels; all figures originate in local shop records."""
import html
from datetime import date,datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import customer_payments
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
def render(rows,db,amounts,calendar_month="",edit_appointment=""):
    today=date.today()
    opened=[r for r in rows if not r["finalized_at"] and r["status"]!="cancelled"]
    active=next((r for r in opened if r["status"] in ("in_progress","approved")),None)
    if active is None and opened:active=opened[0]
    today_completed=[r for r in rows if r["finalized_at"] and local_day(r["finalized_at"])==today]
    billed=sum((amounts(r)["basis"] for r in today_completed),Decimal("0"))
    parent=sum((amounts(r)["parent"] for r in today_completed),Decimal("0"))
    with db() as con:
        payments=con.execute("""SELECT applied FROM customer_payments
               WHERE paid_on=? AND voided_at IS NULL""",(today.isoformat(),)).fetchall()
        paid=sum((Decimal(str(x["applied"])) for x in payments),Decimal("0"))
        accounts=bank_ledger.accounts(con)
        cash=sum(int(x["balance_cents"]) for x in accounts if x["kind"]=="cash")
        bank=sum(int(x["balance_cents"]) for x in accounts if x["kind"]=="bank")
        outstanding=sum((max(Decimal("0"),customer_payments.balance(con,r["id"])["due"])
                      for r in rows if r["finalized_at"]),Decimal("0"))
        activity=con.execute("""SELECT e.timestamp,e.event,e.detail,t.customer
                    FROM events e LEFT JOIN tickets t ON t.id=e.ticket_id
                    ORDER BY e.id DESC LIMIT 5""").fetchall()
        counts=bank_ledger.recent_cash_counts(con,1)
    if active:
        fields=[("Customer",active["customer"] or "Not entered"),
                ("Vehicle",active["machine"] or "Not entered"),
                ("Service",active["service"] or active["problem"] or "Not entered"),
                ("Status",active["status"].replace("_"," ").title()),
                ("Received",local_day(active["received_at"]) or "—")]
        current='<div class="overview-rows">'+''.join(
                '<strong>'+e(k)+'</strong><span>'+e(v)+'</span>' for k,v in fields
                )+'</div><p><a href="#ticket-'+str(active["id"])+'">View job</a></p>'
    else:current='<p>No active jobs. New customer requests appear here.</p>'
    glance=pair_rows([("Jobs (total)",len(rows)),
       ("Jobs (open)",len(opened)),
       ("Jobs (completed)",sum(bool(r["finalized_at"]) for r in rows)),
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
    if counts:
        latest=counts[0]
        delta=Decimal(latest["variance_cents"])/100
        actions.append((local_day(latest["recorded_at"]) or date.min,
                        "Safe count recorded — "+money(Decimal(latest["counted_cents"])/100)+
                        " (difference "+format(delta,"+,.2f")+")"))
    actions.sort(key=lambda row:row[0],reverse=True)
    recent='<ul class="dashboard-activity">'+''.join('<li>'+text+'</li>' for _,text in actions[:6])+'</ul>' if actions else '<p>No recent activity.</p>'
    return ('<div id="dashboard" class="dashboard-overview">'
        '<section class="panel"><h2>Current Job</h2>'+current+'</section>'
        '<section class="panel"><h2>Today at a Glance</h2>'+glance+'</section>'
        +job_calendar.render(db,rows,calendar_month,edit_appointment)+
        '<section class="panel"><h2>Financial Summary</h2>'+financial+'</section>'
        '<section class="panel"><h2>Recent Activity</h2>'+recent+'</section>'
        '</div>')
