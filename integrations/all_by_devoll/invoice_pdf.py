"""Local customer PDF invoices, with no internal accounting figures."""
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit

ROOT=Path.home()/".local"/"share"/"el-grande"/"invoices"
def path_for(number,root=None):
    if int(number)<=0:raise ValueError("Invalid invoice ID")
    return (Path(root) if root is not None else ROOT)/("ABD-%06d.pdf"%int(number))
def clean(value,limit=700):
    return " ".join(str(value or "").split())[:limit].encode("latin-1","replace").decode("latin-1")
def render(ticket,completed,out):
    if not ticket["finalized_at"]:
        raise ValueError("A finalized bill is required before issuing a PDF")
    total=Decimal(str(ticket["bill_total"]))
    if not total.is_finite() or total<0 or (completed is not None and
            total!=Decimal(str(completed["actual_invoice"]))):
        raise ValueError("Customer invoice does not agree with final bill")
    c=canvas.Canvas(str(out),pagesize=letter,pageCompression=1,invariant=1)
    c.setTitle("All by Devoll invoice ABD-%06d"%ticket["id"])
    c.setAuthor("All by Devoll")
    width,height=letter
    c.setFillColor(HexColor("#123f3e"))
    c.rect(0,height-132,width,132,fill=1,stroke=0)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold",23)
    c.drawString(42,height-63,"ALL BY DEVOLL")
    c.setFont("Helvetica",10)
    c.drawString(43,height-84,"Mobile repair and service  |  Manistee, Michigan")
    c.setFont("Helvetica-Bold",12)
    c.drawRightString(width-42,height-63,"INVOICE")
    c.setFont("Helvetica",10)
    c.drawRightString(width-42,height-84,"ABD-%06d"%ticket["id"])
    y=height-170
    def label(name,value):
        nonlocal y
        c.setFont("Helvetica-Bold",9);c.setFillColor(HexColor("#116a65"))
        c.drawString(43,y,name)
        c.setFont("Helvetica",11);c.setFillColor(HexColor("#123f3e"))
        c.drawString(160,y,clean(value,65))
        y-=25
    label("CUSTOMER",ticket["customer"] or "Customer")
    if ticket["phone"]:label("PHONE",ticket["phone"])
    if ticket["location"]:label("LOCATION",ticket["location"])
    try:issued=datetime.fromisoformat(ticket["finalized_at"].replace("Z","+00:00")).strftime("%B %d, %Y")
    except ValueError:issued=clean(ticket["finalized_at"],40)
    label("ISSUED",issued)
    if ticket["machine"]:label("VEHICLE / JOB",ticket["machine"])
    y-=18
    c.setStrokeColor(HexColor("#dbe6e2"));c.line(42,y,width-42,y);y-=31
    c.setFillColor(HexColor("#116a65"));c.setFont("Helvetica-Bold",11)
    c.drawString(43,y,"COMPLETED WORK");y-=28
    description=(completed["work_performed"] if completed is not None else
                 ticket["notes"] or "Service as recorded on the job ticket")
    for paragraph in (ticket["service"] or "Repair service",ticket["problem"],description):
        if not paragraph:continue
        for line in simpleSplit(clean(paragraph,1800),"Helvetica",10,width-100):
            if y<145:c.showPage();y=height-65
            c.setFillColor(HexColor("#172b2c"));c.setFont("Helvetica",10)
            c.drawString(43,y,line);y-=16
        y-=10
    y=min(y-12,180)
    c.setStrokeColor(HexColor("#dbe6e2"));c.line(42,y,width-42,y);y-=31
    c.setFont("Helvetica-Bold",16);c.setFillColor(HexColor("#123f3e"))
    c.drawString(43,y,"TOTAL INVOICE")
    c.drawRightString(width-43,y,"$"+format(total,",.2f"))
    y-=21
    c.setFillColor(HexColor("#617478"));c.setFont("Helvetica",9)
    c.drawString(43,y,"Agreed customer price. No separate tax is added.")
    c.drawString(43,50,"Please retain this invoice for your records.")
    c.save()
def create(ticket,completed,root=None):
    target=path_for(ticket["id"],root)
    target.parent.mkdir(parents=True,exist_ok=True)
    os.chmod(target.parent,0o700)
    if target.exists():return target
    fd,temp=tempfile.mkstemp(prefix=".new-invoice-",suffix=".pdf",dir=target.parent)
    os.close(fd)
    try:
        render(ticket,completed,temp)
        os.chmod(temp,0o600)
        if not target.exists():os.replace(temp,target)
        return target
    finally:
        if os.path.exists(temp):os.unlink(temp)
