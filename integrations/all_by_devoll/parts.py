"""Supplier-priced parts catalogue. Feed data must originate from an authorized supplier.
Compatible with private CSV export and HTTPS JSON/CSV supplier feeds; no guessed prices.
"""
import csv
import io
import json
import os
import re
import sqlite3
import ssl
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

DDL = """
CREATE TABLE IF NOT EXISTS supplier_parts (
 supplier TEXT NOT NULL,
 sku TEXT NOT NULL,
 description TEXT NOT NULL,
 unit_cost TEXT NOT NULL,
 suggested_sale TEXT NOT NULL DEFAULT '',
 currency TEXT NOT NULL DEFAULT 'USD',
 availability TEXT NOT NULL DEFAULT 'unknown',
 checked_at TEXT NOT NULL,
 supplier_url TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL,
 PRIMARY KEY (supplier, sku)
);
CREATE TABLE IF NOT EXISTS ticket_parts (
 ticket_id INTEGER NOT NULL,
 supplier TEXT NOT NULL,
 sku TEXT NOT NULL,
 description TEXT NOT NULL,
 quantity TEXT NOT NULL,
 unit_cost TEXT NOT NULL,
 unit_sale TEXT NOT NULL,
 checked_at TEXT NOT NULL,
 PRIMARY KEY (ticket_id, supplier, sku)
);
"""
HEADERS=("supplier","sku","description","unit_cost","suggested_sale","currency","availability","checked_at","supplier_url")
MAX_ROWS=50000
MAX_BYTES=5*1024*1024

def decimal_amount(value):
    try: n=Decimal(str(value))
    except InvalidOperation as e: raise ValueError("Invalid part price") from e
    if not n.is_finite() or n<0 or n>Decimal("1000000"):raise ValueError("Part price out of range")
    return n.quantize(Decimal(".01"),rounding=ROUND_HALF_UP)

def validate_record(entry,source):
    item={k:str(entry.get(k,"") or "").strip() for k in HEADERS}
    if not item["supplier"] or not item["sku"] or not item["description"]:
        raise ValueError("Supplier, SKU and description are required")
    if len(item["supplier"])>100 or len(item["sku"])>100 or len(item["description"])>400:
        raise ValueError("Supplier record too long")
    if item["currency"].upper()!="USD":raise ValueError("Only USD catalogues are supported")
    item["currency"]="USD"
    item["unit_cost"]=str(decimal_amount(item["unit_cost"]))
    if item["suggested_sale"]:
        item["suggested_sale"]=str(decimal_amount(item["suggested_sale"]))
    if item["availability"] not in ("unknown","in_stock","order","out_of_stock"):
        raise ValueError("Invalid availability")
    stamp=item["checked_at"]
    if stamp:
        try: datetime.fromisoformat(stamp.replace("Z","+00:00"))
        except ValueError as e:raise ValueError("Invalid supplier timestamp") from e
    else:item["checked_at"]=datetime.now(timezone.utc).isoformat(timespec="seconds")
    if item["supplier_url"]:
        target=urlparse(item["supplier_url"])
        if target.scheme!="https":raise ValueError("Supplier links must use HTTPS")
    item["source"]=source[:250]
    return item

def csv_records(content):
    if len(content.encode("utf-8"))>MAX_BYTES:raise ValueError("Catalogue too large")
    reader=csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not set(("supplier","sku","description","unit_cost")).issubset(reader.fieldnames):
        raise ValueError("CSV must include supplier,sku,description,unit_cost")
    rows=list(reader)
    if len(rows)>MAX_ROWS:raise ValueError("Too many catalogue rows")
    return rows

def upsert_catalogue(con,rows,source):
    records=[validate_record(row,source) for row in rows]
    with con:
        for p in records:
            con.execute("""INSERT INTO supplier_parts(supplier,sku,description,unit_cost,suggested_sale,
                currency,availability,checked_at,supplier_url,source) VALUES
                (:supplier,:sku,:description,:unit_cost,:suggested_sale,:currency,:availability,:checked_at,:supplier_url,:source)
                ON CONFLICT(supplier,sku) DO UPDATE SET description=excluded.description,
                unit_cost=excluded.unit_cost,suggested_sale=excluded.suggested_sale,
                currency=excluded.currency,availability=excluded.availability,
                checked_at=excluded.checked_at,supplier_url=excluded.supplier_url,source=excluded.source""",p)
    return len(records)

def supplier_feed(prefix="ABD_PARTS_FEED"):
    """One explicitly authorized supplier feed, not HTML scraping."""
    url=os.getenv(prefix+"_URL","").strip()
    if not url:return None
    parsed=urlparse(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Supplier feed must be a credential-free HTTPS URL")
    allowed=os.getenv(prefix+"_HOST","").strip().lower()
    if not allowed or parsed.hostname.lower()!=allowed:
        raise ValueError("Set "+prefix+"_HOST to the approved supplier hostname")
    headers={"Accept":"application/json,text/csv","User-Agent":"AllByDevoll-AuthorizedPartsFeed/1.0"}
    token=os.getenv(prefix+"_TOKEN","").strip()
    if token:headers["Authorization"]="Bearer "+token
    request=urllib.request.Request(url,headers=headers)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            raise ValueError("Supplier feed redirects must be reviewed and configured explicitly")
    opener=urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(request,timeout=20) as res:
        raw=res.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError("Supplier response too large")
        content=raw.decode("utf-8-sig")
        if "json" in res.headers.get("Content-Type","") or content.lstrip().startswith("[") or content.lstrip().startswith("{"):
            rows=json.loads(content)
            if isinstance(rows,dict):rows=rows.get("parts")
            if not isinstance(rows,list):raise ValueError("Supplier JSON must contain a list of parts")
            if len(rows)>MAX_ROWS:raise ValueError("Too many supplier items")
        else:rows=csv_records(content)
        supplier=os.getenv(prefix+"_SUPPLIER","").strip()
        if supplier:
            # An authorized feed may omit a supplier column; never silently misattribute
            # records that explicitly claim to belong to somebody else.
            normalized=[]
            for item in rows:
                if not isinstance(item,dict):raise ValueError("Invalid supplier part")
                if item.get("supplier") and item["supplier"]!=supplier:
                    raise ValueError("Feed supplier does not match configured provider")
                normalized.append({**item,"supplier":supplier})
            rows=normalized
        return rows,url

def supplier_feeds():
    """Fetch all configured providers without one supplier replacing another."""
    results=[]
    for prefix in ("ABD_DETROIT_AXLE","ABD_AUTOZONE","ABD_PARTS_FEED"):
        result=supplier_feed(prefix)
        if result:results.append(result)
    return results

def search(con,text,limit=50):
    q="%"+text.strip().replace("%","\\%").replace("_","\\_")+"%"
    return con.execute("""SELECT * FROM supplier_parts
        WHERE sku LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR supplier LIKE ? ESCAPE '\\'
        ORDER BY supplier,sku LIMIT ?""",(q,q,q,limit)).fetchall()

def add_to_ticket(con,ticket_id,supplier,sku,quantity,markup_percent="0"):
    try:qty=Decimal(str(quantity))
    except InvalidOperation as e:raise ValueError("Invalid quantity") from e
    if not qty.is_finite() or qty<=0 or qty>10000:raise ValueError("Quantity outside allowed range")
    qty=qty.quantize(Decimal(".01"),rounding=ROUND_HALF_UP)
    if qty<=0:raise ValueError("Quantity must be positive")
    p=con.execute("SELECT * FROM supplier_parts WHERE supplier=? AND sku=?",(supplier,sku)).fetchone()
    if not p:raise LookupError("Supplier price not found")
    if p["availability"]=="out_of_stock":raise ValueError("Supplier reports part out of stock")
    cost=decimal_amount(p["unit_cost"])
    if p["suggested_sale"]:sale=decimal_amount(p["suggested_sale"])
    else:
        markup=Decimal(str(markup_percent))
        if not markup.is_finite() or markup<0 or markup>1000:raise ValueError("Invalid markup")
        sale=decimal_amount(cost*(Decimal("1")+markup/Decimal("100")))
    with con:
        con.execute("""INSERT INTO ticket_parts
          (ticket_id,supplier,sku,description,quantity,unit_cost,unit_sale,checked_at)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id,supplier,sku) DO UPDATE SET
          quantity=excluded.quantity,unit_cost=excluded.unit_cost,unit_sale=excluded.unit_sale,
          checked_at=excluded.checked_at,description=excluded.description""",
          (ticket_id,supplier,sku,p["description"],str(qty),str(cost),str(sale),p["checked_at"]))
    return dict(supplier=supplier,sku=sku,cost=str(cost),sale=str(sale),quantity=str(qty),checked_at=p["checked_at"])

def ticket_totals(con,ticket_id):
    rows=con.execute("SELECT * FROM ticket_parts WHERE ticket_id=? ORDER BY supplier,sku",(ticket_id,)).fetchall()
    cost=sum((Decimal(x["quantity"])*Decimal(x["unit_cost"])).quantize(Decimal(".01"),rounding=ROUND_HALF_UP) for x in rows)
    sale=sum((Decimal(x["quantity"])*Decimal(x["unit_sale"])).quantize(Decimal(".01"),rounding=ROUND_HALF_UP) for x in rows)
    return rows,cost,sale
