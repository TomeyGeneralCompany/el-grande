"""Clean, operator-first HTML for the All by Devoll service desk.

Internal settlement remains a backend/accounting concern, not an operator banner.
No third-party assets, scripts, fonts, analytics, or CDN dependencies.
"""
import html
import os
from collections import Counter
from decimal import Decimal
from urllib.parse import urlencode

import mavis_theme
import job_reports
import customer_payments
from datetime import date

def esc(value):
    return html.escape(str(value if value is not None else ""),quote=True)

CSS=r"""
:root{--ink:#172b2c;--muted:#617478;--bg:#f5f7f6;--surface:#fff;--line:#e2e8e6;--forest:#123f3e;--teal:#116a65;--gold:#c8a35e;--pale:#e7f3ef;--danger:#a65325}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}
a{color:var(--teal);text-decoration:none}a:hover{text-decoration:underline}
header{background:var(--forest);color:white}header .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:86px}
.wrap{max-width:1240px;margin:auto;padding:0 24px}
.brand{display:flex;align-items:center;gap:14px}.mark{width:48px;height:48px;border:2px solid var(--gold);border-radius:13px;display:grid;place-items:center;color:var(--gold);font:bold 17px Georgia,serif}
.brand strong{display:block;letter-spacing:.05em;font-size:21px}.brand small{color:#c0d6d3;font-size:12px}
.topmeta{font-size:13px;color:#c5d7d4}.topmeta a{color:#fff;border:1px solid #8ca7a2;border-radius:8px;padding:10px 13px;display:inline-block;margin-left:12px}
nav{background:white;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}
nav .wrap{display:flex;align-items:center;gap:26px;overflow:auto;white-space:nowrap;height:52px}
nav a{font-weight:600;font-size:13px;color:#516768}nav a:hover{color:var(--teal)}
main{max-width:1240px;margin:30px auto 80px;padding:0 24px}
.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.11em;font-weight:800;color:var(--teal);margin:0 0 5px}
h1{font-size:29px;line-height:1.18;margin:0 0 7px;letter-spacing:-.03em}
h2{font-size:20px;letter-spacing:-.02em;margin:0}h3{font-size:16px;margin:0 0 12px}
.intro{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:24px}.muted{color:var(--muted)}.intro p{margin:0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px;margin-bottom:24px}
.metric{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 19px}
.metric label{margin:0;color:var(--muted);font-size:12px}.metric strong{display:block;font-size:27px;letter-spacing:-.04em;margin-top:5px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0}
.panelhead{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:16px}
.small{font-size:13px}.action{background:var(--teal);color:white!important;border:0;display:inline-block;border-radius:9px;padding:10px 15px;font:600 13px system-ui;cursor:pointer;text-decoration:none}
.action:hover{background:#0d514d;text-decoration:none}.action.secondary{background:#eef3f1;color:var(--forest)!important}
.action.danger{background:#835d31}.action:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #9ccbc2;outline-offset:2px}
label{display:block;font-size:13px;font-weight:650;margin:9px 0 4px}
input,textarea,select{width:100%;min-width:0;padding:10px 11px;font:inherit;color:var(--ink);border:1px solid #cbd8d5;border-radius:8px;background:white}
textarea{min-height:92px;resize:vertical}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.fields>*{min-width:0}
.footactions{display:flex;flex-wrap:wrap;align-items:center;gap:9px;margin-top:16px}
.ticket{border:1px solid var(--line);border-radius:12px;margin:12px 0;background:white;overflow:hidden}
.ticket[open]{border-color:#b3d0c6;box-shadow:0 6px 22px #133e3810}
.ticket>summary{display:flex;align-items:center;justify-content:space-between;gap:14px;cursor:pointer;list-style:none;padding:17px 19px}
.ticket>summary::-webkit-details-marker{display:none}.jobleft{display:flex;gap:14px;align-items:center;min-width:0}
.jobid{background:#eef3f1;color:#456866;font-size:12px;font-weight:800;border-radius:8px;padding:10px 9px;white-space:nowrap}
.jobname{display:block;font-size:16px;font-weight:750}.subline{display:block;color:var(--muted);font-size:12px;margin-top:3px}
.jobright{display:flex;align-items:center;gap:16px}.pill{font-size:11px;font-weight:750;letter-spacing:.01em;padding:6px 9px;border-radius:30px;background:#edf3f0;color:#3d6560;white-space:nowrap}
.pill.done{background:#e2f2e9;color:#24714b}.pill.alert{background:#fff0e3;color:#915723}
.chev{color:#6d8985;font-size:18px}.ticket[open] .chev{transform:rotate(180deg)}
.jobbody{padding:0 20px 22px;border-top:1px solid var(--line)}
.jobinfo{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;padding:16px 0}.jobinfo span{color:var(--muted);display:block;font-size:12px}.jobinfo b{display:block;font-size:14px;overflow-wrap:anywhere}
.working{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(260px,1fr);gap:16px}
.worksection{border:1px solid var(--line);border-radius:11px;padding:18px;margin-top:15px;min-width:0}
.worksection>h3{display:flex;justify-content:space-between}
.worksection p{margin:7px 0;font-size:13px}
.price{background:var(--pale);border:1px solid #c4ddd3;padding:16px;border-radius:10px;margin:13px 0}
.price strong{font-size:25px;display:block;letter-spacing:-.04em}.price span{font-size:12px;color:#557369}
.inlineform{display:flex;gap:9px;align-items:end;flex-wrap:wrap}.inlineform label{flex:1;min-width:115px}
.links{display:flex;gap:12px;flex-wrap:wrap;margin:11px 0}.links a{font-weight:650;font-size:13px}
.minisection{margin-top:16px;border-top:1px solid var(--line);padding-top:14px}
details.inner{margin:12px 0;border-top:1px solid var(--line);padding-top:12px}details.inner summary{font-size:13px;color:var(--teal);font-weight:700;cursor:pointer}
.list{padding-left:18px;margin:8px 0}.list li{margin:6px 0;font-size:13px}
.ai{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f6;border-radius:8px;padding:11px;font-size:12px;max-height:320px;overflow:auto}
.statusbar{display:flex;flex-wrap:wrap;gap:11px}.status-item{font-size:12px;display:flex;gap:7px;align-items:center;background:#f6f8f7;border:1px solid var(--line);padding:8px 11px;border-radius:8px}
.dot{width:8px;height:8px;border-radius:100%;background:#d59d59;flex:none}.dot.good{background:#32976e}.dot.bad{background:#c46e54}
.empty{padding:25px;text-align:center;background:#f7faf8;border-radius:10px;color:var(--muted)}
.catalog{margin:8px 0}.catalog li{padding:7px 0;border-bottom:1px solid var(--line)}
footer{border-top:1px solid var(--line);padding:20px 0;color:var(--muted);font-size:12px}
@media(max-width:840px){.cards{grid-template-columns:repeat(2,1fr)}.working{grid-template-columns:1fr}.topmeta{display:none}}
@media(max-width:560px){.wrap,main{padding-left:14px;padding-right:14px}.cards{gap:8px}.metric{padding:14px}.metric strong{font-size:24px}
.intro{display:block}.intro .action{margin-top:15px}.panel{padding:14px}.ticket>summary{padding:12px}.jobid{display:none}.jobright{gap:8px}.jobname{font-size:14px}.subline{max-width:190px}
nav .wrap{gap:18px}.jobbody{padding:0 12px 14px}}
"""

CSS += mavis_theme.CSS

def field(name, title, value="",kind="text",required=False,placeholder="",step=None):
    stepattr= ' step="'+esc(step)+'"' if step else ""
    minattr=' min="0"' if kind=="number" else ""
    req=" required" if required else ""
    return ('<label>'+esc(title)+'<input name="'+esc(name)+'" type="'+kind+'" value="'+
            esc(value)+'" placeholder="'+esc(placeholder)+'"'+stepattr+minattr+req+'></label>')

def button(text,css="action"):
    return '<button type="submit" class="'+esc(css)+'">'+esc(text)+'</button>'

def postform(url,caption,css="action"):
    return '<form method="post" action="'+esc(url)+'">'+button(caption,css)+'</form>'

def state_name(s):
    return str(s).replace("_"," ").title()

def connection_status(config,erp):
    if config["mailbox"]:
        mail=('Business inbox configured','good')
    else:mail=('Business inbox not connected','')
    if config["report"]:
        report=('Owner reports configured','good')
    else:report=('Owner reports not connected','')
    if erp["running"] and erp["configured"]:
        erptext=('BlueSeer responding · settings entered','good')
    elif erp["running"]:
        erptext=('BlueSeer responding · setup needed','')
    else:
        erptext=('BlueSeer not responding','bad')
    return '<div class="statusbar">'+''.join(
        '<div class="status-item"><span class="dot '+col+'"></span>'+esc(text)+'</div>'
        for text,col in (mail,report,erptext))+'</div>'

def render(rows,catalog,db,amounts,system=None):
    system=system or {}
    counts=Counter(r["status"] for r in rows)
    pending=sum(1 for r in rows if not r["finalized_at"] and r["status"] not in ("cancelled","paid"))
    complete=sum(1 for r in rows if r["finalized_at"])
    inprogress=counts["in_progress"]+counts["approved"]
    new=counts["new"]
    config={"mailbox":system.get("mailbox",False),"report":system.get("report",False)}
    erp=system.get("erp",{"running":False,"configured":False})
    with db() as con:
        today_cash=con.execute("""SELECT applied FROM customer_payments
            WHERE method='cash' AND paid_on=? AND voided_at IS NULL""",
            (date.today().isoformat(),)).fetchall()
    daily_cash=sum((Decimal(x["applied"]) for x in today_cash),Decimal("0"))
    metrics=[("Open jobs",pending),("New requests",new),("Active work",inprogress),
             ("Completed jobs",complete),("Cash received today","$"+format(daily_cash,",.2f"))]
    stats=''.join('<div class="metric"><label>'+name+'</label><strong>'+str(value)+'</strong></div>' for name,value in metrics)
    items=[]
    for ticket in rows:
        n=int(ticket["id"])
        a=amounts(ticket)
        done=bool(ticket["finalized_at"])
        with db() as con:
            attached=con.execute("SELECT * FROM ticket_parts WHERE ticket_id=? ORDER BY supplier,sku",(n,)).fetchall()
            sync=con.execute("SELECT kind,state,record_number FROM blue_sync WHERE ticket_id=?",(n,)).fetchall()
            completed=con.execute("SELECT * FROM job_completions WHERE ticket_id=?",(n,)).fetchone()
            owner=con.execute("SELECT state FROM owner_reports WHERE ticket_id=?",(n,)).fetchone()
            native=con.execute("SELECT state,last_error FROM erp_jobs WHERE ticket_id=?",(n,)).fetchone()
            receipts=customer_payments.payments(con,n) if done else []
            paid_state=customer_payments.balance(con,n) if done else None
        status=ticket["status"]
        cls="done" if done else "alert" if status=="new" else ""
        jobheader=('<summary><div class="jobleft"><span class="jobid">ABD-'+f"{n:06d}"+'</span>'
                   '<span><span class="jobname">'+esc(ticket["customer"] or "Customer not entered")+'</span>'
                   '<span class="subline">'+esc(ticket["service"] or "Service request")+' · '+esc(ticket["machine"] or ticket["location"] or "Details pending")+'</span></span></div>'
                   '<div class="jobright"><span class="pill '+cls+'">'+esc(state_name(status))+'</span>'
                   '<span class="chev" aria-hidden="true">⌄</span></div></summary>')
        info="".join('<div><span>'+label+'</span><b>'+esc(value or "Not supplied")+'</b></div>' for label,value in
                     (("Phone",ticket["phone"]),("Location",ticket["location"]),("Equipment",ticket["machine"]),("Reported problem",ticket["problem"])))
        jobinfo='<div class="jobinfo">'+info+'</div>'
        inner=[]
        if not done:
            option=''.join('<option value="'+esc(s)+'"'+(' selected' if status==s else '')+'>'+esc(state_name(s))+'</option>'
                           for s in ("new","estimating","quoted","approved","in_progress","completed","cancelled"))
            workform=('<form method="post" action="/ticket/'+str(n)+'/update">'
                      '<div class="fields">'+
                      ''.join(field(k,title,ticket[k],"number",step=".01") for k,title in
                              (("labor_hours","Estimated labor hours"),("labor_rate","Hourly rate ($)"),
                               ("parts_charge","Parts billed ($)"),("parts_cost","Parts purchase cost ($)"),
                               ("travel_charge","Travel ($)"),("extra_charge","Other charges ($)")))+
                      '</div><label>Job status<select name="status">'+option+'</select></label>'
                      '<label>Shop notes<textarea name="notes">'+esc(ticket["notes"])+'</textarea></label>'+
                      button("Save estimate")+'</form>')
            left=('<section class="worksection"><h3>Estimate & job notes</h3>'
                  '<p class="muted">The mechanic reviews this estimate before calling the customer.</p>'
                  '<div class="price"><span>Current estimated job total</span><strong>$'+f'{a["total"]:,.2f}'+'</strong></div>'
                  +workform+'</section>')
            searchurl=job_reports.google_search_link(ticket["problem"][:90] or ticket["service"][:90],ticket["machine"][:120])
            right=('<section class="worksection"><h3>Parts & research</h3>'
                   '<div class="links"><a href="'+esc(searchurl)+'" target="_blank" rel="noopener noreferrer">Search job prices on Google ↗</a>'
                   '<a href="https://detroitaxle.com/parts" target="_blank" rel="noopener noreferrer">Detroit Axle ↗</a>'
                   '<a href="https://www.autozonepro.com/" target="_blank" rel="noopener noreferrer">AutoZonePro ↗</a></div>'
                   '<form method="get" action="/" class="inlineform">'+field("googlepart","Search a specific part",placeholder="Starter, brakes, alternator")+
                   '<input type="hidden" name="vehicle" value="'+esc(ticket["machine"])+'">'+button("Search")+'</form>')
            if attached:
                right+='<div class="minisection"><h3>Selected parts</h3><ul class="list">'+''.join(
                    '<li>'+esc(p["supplier"])+' · '+esc(p["sku"])+' · '+esc(p["description"])+' — $'+esc(p["unit_cost"])+'</li>'
                    for p in attached)+'</ul></div>'
            right+=('<details class="inner"><summary>Add a catalogue part</summary><form method="post" action="/ticket/'+str(n)+'/part">'
                    +field("supplier","Supplier",required=True)+field("sku","Part number",required=True)
                    +field("quantity","Quantity",value="1",kind="number",step=".01")
                    +button("Add part")+'</form></details>')
            right+=('<div class="minisection"><h3>AI assistance</h3>'+
                    postform('/ticket/'+str(n)+'/suggest',"Generate labor & diagnostic estimate","action secondary")+
                    ('<pre class="ai">'+esc(ticket["ai_notes"])+'</pre>' if ticket["ai_notes"] else '')+'</div></section>')
            inner.append('<div class="working">'+left+right+'</div>')
            completedform=('<section class="worksection" id="finish-'+str(n)+'"><h3>Finish this job</h3>'
              '<p class="muted">Enter the completed work and the final price. El Grande will prepare the PDF invoice.</p>'
              '<form method="post" action="/ticket/'+str(n)+'/complete">'
              '<label>Work performed<textarea name="work_performed" required placeholder="Repair completed, parts installed, work performed">'+esc(ticket["notes"])+'</textarea></label>'
              +field("actual_invoice","Final customer bill ($)",format(a["total"],".2f"),"number",required=True,step=".01")
              +'<details class="inner"><summary>Optional: hours and actual job expenses</summary><div class="fields">'
              +field("started_at","Started",kind="datetime-local")
              +field("finished_at","Finished",kind="datetime-local")
              +field("actual_hours","Hours worked",ticket["labor_hours"],"number",step=".01")
              +field("actual_labor_cost","Actual labor cost ($)","0","number",step=".01")
              +field("actual_parts_cost","Actual parts cost ($)",ticket["parts_cost"],"number",step=".01")
              +field("actual_other_cost","Other expenses ($)","0","number",step=".01")
              +'</div></details>'
              +'<div class="footactions">'+button("Finish Job & Create Invoice","action danger")+'</div></form></section>')
            inner.append(completedform)
        else:
            if completed:
                inner.append('<section class="worksection"><h3>Completed job</h3>'
                    '<p><strong>Work performed</strong></p><p>'+esc(completed["work_performed"])+'</p>'
                    '<div class="jobinfo">'+''.join('<div><span>'+t+'</span><b>'+v+'</b></div>'
                    for t,v in (("Final invoice","$"+esc(completed["actual_invoice"])),
                        ("Hours worked",esc(completed["actual_hours"])),
                        ("Labor cost","$"+esc(completed["actual_labor_cost"])),
                        ("Parts cost","$"+esc(completed["actual_parts_cost"])),
                        ("Report email",esc(owner["state"] if owner else "Not queued")),
                        ("BlueSeer order",esc(state_name(native["state"]) if native else "Not queued"))))+'</div></section>')
            else:
                inner.append('<section class="worksection"><h3>Finalized job</h3><p>Invoice: $'+esc(ticket["bill_total"])+'</p></section>')
            method_labels={"cash":"Cash","check":"Check","card":"Card",
                           "bank_transfer":"Bank transfer","other":"Other"}
            payment_html=('<section class="worksection"><h3>Customer invoice</h3>'
                '<p><a class="action" href="/ticket/'+str(n)+'/invoice.pdf" target="_blank" rel="noopener">View / print PDF invoice</a></p>'
                '<div class="jobinfo">'
                '<div><span>Invoice total</span><b>$'+format(paid_state["invoice"],",.2f")+'</b></div>'
                '<div><span>Payment status</span><b>'+("Paid" if paid_state["due"]==0 else "Unpaid" if paid_state["received"]==0 else "Partly paid")+'</b></div>'
                '<div><span>Still owed</span><b>$'+format(paid_state["due"],",.2f")+'</b></div></div>')
            if paid_state["due"]>0:
                payment_html+=(postform('/ticket/'+str(n)+'/pay-in-full',"Mark Paid","action")
                    +'<p class="small muted">Records the remaining amount received in cash today.</p>')
                choices=''.join('<option value="'+esc(k)+'"'+(' selected' if k=="cash" else '')+'>'+v+'</option>' for k,v in method_labels.items())
                payment_html+=('<details class="inner"><summary>Record partial payment or another payment method</summary>'
                    '<form method="post" action="/ticket/'+str(n)+'/payment">'
                    '<div class="fields">'
                    +field("amount_received","Amount received ($)",format(paid_state["due"],".2f"),"number",required=True,step=".01")
                    +'<label>Payment method<select name="method">'+choices+'</select></label>'
                    +field("paid_on","Date paid",date.today().isoformat(),"date")
                    +field("reference","Check / transaction reference (optional)")
                    +'</div>'+button("Record payment")+'</form></details>')
            else:
                payment_html+='<p class="pill done">Paid in full</p>'
            if receipts:
                payment_html+='<details class="inner"><summary>Payment history</summary><ul class="list">'
                for receipt in receipts:
                    detail=('$'+esc(receipt["applied"])+' applied · '+esc(method_labels.get(receipt["method"],receipt["method"]))
                            +' · '+esc(receipt["paid_on"]))
                    if receipt["method"]=="cash" and Decimal(receipt["change_given"])>0:
                        detail+=' · $'+esc(receipt["change_given"])+' change returned'
                    if receipt["reference"]:
                        detail+=' · '+esc(receipt["reference"])
                    if receipt["voided_at"]:
                        detail+=' · VOIDED ('+esc(receipt["void_reason"])+')'
                    payment_html+='<li>'+detail
                    if not receipt["voided_at"]:
                        payment_html+=('<details class="inner"><summary>Correct payment</summary>'
                           '<form method="post" action="/ticket/'+str(n)+'/void-payment">'
                           '<input type="hidden" name="payment_id" value="'+str(receipt["id"])+'">'
                           +field("reason","Reason for voiding",required=True)
                           +button("Void payment entry","action secondary")+'</form></details>')
                    payment_html+='</li>'
                payment_html+='</ul></details>'
            payment_html+='</section>'
            inner.append(payment_html)
        items.append('<details class="ticket" id="ticket-'+str(n)+'">'+jobheader+
                     '<div class="jobbody">'+jobinfo+''.join(inner)+'</div></details>')
    if not items:
        items.append('<div class="empty">No jobs yet. Create a ticket below or connect the business inbox.</div>')
    newfields=''.join(field(k,t,required=k in ("customer","problem"),placeholder=p) for k,t,p in (
        ("customer","Customer","Name"),("phone","Phone","Callback number"),
        ("location","Location","City or township"),("service","Service","Repair, scrap, removal"),
        ("machine","Vehicle or equipment","Year / make / model"),
        ("mobility","Where is it?","At shop, mobile, roadside"),
        ("problem","Customer's request","Brief job description")))
    catalogue=''.join('<li><b>'+esc(p["supplier"])+' · '+esc(p["sku"])+'</b> — '+esc(p["description"])+' · $'+esc(p["unit_cost"])+'</li>' for p in catalog)
    html_top='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#c90028"><title>All by Devoll | Shop Desk</title><style>'''+CSS+'''</style></head><body>
<header><div class="wrap"><div class="brand"><div class="mark">AD</div><div><strong>ALL BY DEVOLL</strong><small>Mobile repair & service · Shop desk</small></div></div>
<div class="topmeta">Office workspace <a href="/health">System status</a></div></div></header>
<nav><div class="wrap"><a href="#jobs">Jobs</a><a href="#new">New request</a><a href="#catalogue">Parts</a><a href="/bank">Money &amp; banks</a><a href="/settings">Settings</a><a href="/export.csv">Export jobs</a><a href="/payments.csv">Export payments</a></div></nav><main>
<div class="intro"><div><p class="eyebrow">Workshop overview</p><h1>Today's job desk</h1><p class="muted">Service requests, estimates and completed jobs in one place.</p></div><a class="action" href="#new">+ New service request</a></div>
'''
    content='<div class="cards">'+stats+'</div>'
    content+='<section class="panel" id="jobs"><div class="panelhead"><h2>Service jobs</h2><span class="muted small">'+str(len(rows))+' shown · Most recent first</span></div>'+''.join(items)+'</section>'
    content+='<section class="panel" id="new"><div class="panelhead"><h2>New service request</h2><span class="muted small">Phone calls and walk-ins</span></div><form method="post" action="/ticket/new"><div class="fields">'+newfields+'</div><div class="footactions">'+button("Create job")+'</div></form></section>'
    content+='<section class="panel" id="catalogue"><div class="panelhead"><h2>Parts catalogue</h2><span class="muted small">Supplier reference and price lookup</span></div>'
    content+='<div class="links"><a href="https://detroitaxle.com/parts" target="_blank" rel="noopener noreferrer">Detroit Axle catalogue ↗</a><a href="https://www.autozonepro.com/" target="_blank" rel="noopener noreferrer">AutoZonePro ↗</a></div>'
    content+='<form method="get" action="/" class="inlineform">'+field("partq","Search catalogue",placeholder="Part number or description")+button("Search parts")+'</form>'
    content+='<ul class="catalog list">'+(catalogue or '<li>No supplier parts loaded. You can still search market prices within any job.</li>')+'</ul>'
    content+='<details class="inner"><summary>Import supplier prices (CSV)</summary><form method="post" action="/parts/import"><label>Paste catalogue CSV<textarea name="catalog"></textarea></label>'+button("Import prices")+'</form></details>'
    content+=postform('/parts/fetch',"Refresh connected supplier feeds","action secondary")+'</section>'

    return html_top+content+'</main><footer><div class="wrap">All by Devoll · Internal office system</div></footer></body></html>'
