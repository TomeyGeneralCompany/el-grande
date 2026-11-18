"""BlueSeer 8.0 native API adapter for internal All by Devoll drafts and service orders.

Calls the existing BlueSeer /bsapi/authServ and /bsapi/dataServORD operations,
not its underlying tables. Never emails a quote and never silently creates AR/GL.
"""
import base64
import hashlib
import json
import os
import re
import urllib.request
from datetime import date,timedelta
from decimal import Decimal
from urllib.parse import urlparse

REQUIRED = ("ABD_BLUESEER_URL","ABD_BLUESEER_USER","ABD_BLUESEER_PASSWORD",
            "ABD_BLUESEER_SITE",
            "ABD_BLUESEER_LABOR_ITEM","ABD_BLUESEER_PARTS_ITEM")
class BridgeError(Exception):pass

def enabled():
    return bool(os.getenv("ABD_BLUESEER_URL"))

def require_config():
    missing=[k for k in REQUIRED if not os.getenv(k,"").strip()]
    if missing:raise BridgeError("Missing BlueSeer configuration: "+", ".join(missing))
    url=os.environ["ABD_BLUESEER_URL"].rstrip("/")
    u=urlparse(url)
    if (u.scheme=="http" and u.hostname not in ("localhost","127.0.0.1","::1")) or u.scheme not in ("http","https"):
        raise BridgeError("BlueSeer endpoint must be HTTPS or loopback-only HTTP")
    if not u.hostname or u.username or u.password:raise BridgeError("Invalid BlueSeer endpoint")
    return url

def record(fields,**kwargs):
    # Jackson requires exact Java record component names; unprovided components
    # are nullable in the upstream record but supply explicit strings instead.
    return {"m":None, **{k:kwargs.get(k,"") for k in fields}}

def line(item,description,unit_price,quantity=1):
    if not item:raise BridgeError("A valid BlueSeer item code is required")
    price=float(Decimal(str(unit_price)))
    qty=float(Decimal(str(quantity)))
    if not (0<=price<=100000000 and 0<qty<=10000):
        raise BridgeError("Invalid BlueSeer line quantity or price")
    return item,description[:240],price,qty

def header_data(ticket,amounts):
    key=f"ABD{int(ticket['id']):06d}"
    today=date.today().isoformat()
    cust=ticket["blue_customer"] if "blue_customer" in ticket.keys() and ticket["blue_customer"] else os.getenv("ABD_BLUESEER_CUSTOMER","")
    if not cust:raise BridgeError("Assign or create a BlueSeer customer before synchronization")
    return key,today,cust,os.environ["ABD_BLUESEER_SITE"]

class BlueSeerClient:
    def __init__(self,base=None,user=None,password=None,transport=None):
        self.base=(base or require_config()).rstrip("/")
        self.user=user or os.environ["ABD_BLUESEER_USER"]
        self.password=password or os.environ["ABD_BLUESEER_PASSWORD"]
        self.transport=transport or self._transport
        self.session=None
    @staticmethod
    def _transport(url,headers,body):
        request=urllib.request.Request(url,data=body,headers=headers,method="POST")
        with urllib.request.urlopen(request,timeout=30) as response:
            return response.read(1024*1024).decode("utf-8","replace")
    def request(self,path,action,body=b"",**headers):
        h={"id":action,"user":self.user,"sessionid":self.session or "","Content-Type":"text/plain"}
        h.update(headers)
        return self.transport(self.base+"/"+path,h,body)
    def authenticate(self):
        h={"id":"loginAPI","user":self.user,"pass":self.password,"sessionid":"","Content-Type":"text/plain"}
        raw=self.transport(self.base+"/authServ",h,b"").strip()
        if raw=="0" or not raw:raise BridgeError("BlueSeer authentication refused")
        try:self.session=base64.b64decode(raw,validate=True).decode()
        except Exception as e:raise BridgeError("BlueSeer returned an invalid session") from e
        if not self.session:raise BridgeError("BlueSeer returned an empty session")
        return self.session
    def call(self,resource,action,body="",**headers):
        if self.session is None:self.authenticate()
        raw=self.request(resource,action,body.encode("utf-8"),**headers)
        try:return json.loads(raw)
        except json.JSONDecodeError as e:raise BridgeError("Unexpected BlueSeer response from "+action) from e
    def get(self,resource,action,key):
        return self.call(resource,action,param1=key)
    def post(self,resource,action,body):
        result=self.call(resource,action,body=body)
        if not isinstance(result,list) or not result or result[0]!="0":
            raise BridgeError("BlueSeer rejected "+action+": "+str(result)[:300])
        return result

SV_FIELDS=("sv_nbr","sv_cust","sv_ship","sv_po","sv_crew","sv_create_date",
           "sv_due_date","sv_rmks","sv_status","sv_issched","sv_userid","sv_type",
           "sv_char1","sv_char2","sv_char3","sv_terms","sv_curr","sv_ar_acct",
           "sv_ar_cc","sv_onhold","sv_taxcode","sv_site")
SVD_FIELDS=("svd_nbr","svd_line","svd_uom","svd_item","svd_desc","svd_type",
            "svd_custitem","svd_qty","svd_completed_hrs","svd_po",
            "svd_ord_date","svd_due_date","svd_create_date",
            "svd_char1","svd_char2","svd_char3","svd_status",
            "svd_listprice","svd_netprice","svd_disc","svd_taxamt",
            "svd_taxcode","svd_site")
QUO_FIELDS=("quo_nbr","quo_cust","quo_ship","quo_site","quo_date","quo_expire",
            "quo_priceexpire","quo_status","quo_rmks","quo_ref","quo_type",
            "quo_taxcode","quo_disccode","quo_groupcode","quo_curr",
            "quo_approved","quo_approver","quo_varchar","quo_terms")
QUOD_FIELDS=("quod_nbr","quod_line","quod_item","quod_isinv","quod_desc",
             "quod_pricetype","quod_listprice","quod_disc",
             "quod_netprice","quod_qty","quod_uom")

def sales_lines(ticket,math):
    rows=[]
    labor=math["labor"]
    if labor>0:
        rows.append(line(os.environ["ABD_BLUESEER_LABOR_ITEM"],
                         "Mechanic labor (internal estimate)",
                         ticket["labor_rate"],ticket["labor_hours"]))
    price=Decimal(str(ticket["parts_charge"] or "0"))
    if price>0:
        rows.append(line(os.environ["ABD_BLUESEER_PARTS_ITEM"],
                         "Parts (estimate; confirm vendor and fitment)",price))
    for field,item_env,desc in (
      ("travel_charge","ABD_BLUESEER_TRAVEL_ITEM","Travel charge"),
      ("extra_charge","ABD_BLUESEER_MISC_ITEM","Additional service charge")):
        charge=Decimal(str(ticket[field] or "0"))
        if charge>0:
            item=os.getenv(item_env)
            if not item:raise BridgeError("Set "+item_env+" before syncing nonzero "+field)
            rows.append(line(item,desc,charge))
    if not rows:raise BridgeError("Nothing billable in draft; enter estimate first")
    return rows

def build_payloads(ticket,math):
    """Build native Java-record-compatible JSON for the 8.0 endpoints."""
    key,today,cust,site=header_data(ticket,math)
    remarks=(f"INTERNAL ESTIMATE ONLY - DO NOT SEND. {key}. "
             f"{ticket['machine']}. {ticket['problem']}")[:255]
    currency=os.getenv("ABD_BLUESEER_CURRENCY","USD")
    service_type=os.getenv("ABD_BLUESEER_SERVICE_TYPE","quote")
    lines=sales_lines(ticket,math)
    sv=record(SV_FIELDS,sv_nbr=key,sv_cust=cust,sv_ship=cust,
              sv_create_date=today,sv_due_date=today,sv_rmks=remarks,
              sv_status="open",sv_userid=os.environ["ABD_BLUESEER_USER"],
              sv_type=service_type,sv_curr=currency,sv_site=site,
              sv_taxcode=os.getenv("ABD_BLUESEER_TAX_CODE",""))
    svd=[]
    for i,(item,desc,price,qty) in enumerate(lines,1):
        svd.append(record(SVD_FIELDS,svd_nbr=key,svd_line=i,svd_uom="EA",svd_item=item,
            svd_desc=desc,svd_type=service_type,svd_qty=qty,
            svd_ord_date=today,svd_due_date=today,svd_create_date=today,
            svd_completed_hrs=0.0,svd_disc=0.0,svd_taxamt=0.0,
            svd_status="open",svd_listprice=price,svd_netprice=price,svd_site=site))
    q=record(QUO_FIELDS,quo_nbr=key,quo_cust=cust,quo_site=site,
             quo_date=today,quo_expire=(date.today()+timedelta(days=30)).isoformat(),
             quo_priceexpire=(date.today()+timedelta(days=7)).isoformat(),
             quo_status="open",quo_rmks=remarks,quo_ref=key,
             quo_type=os.getenv("ABD_BLUESEER_QUOTE_TYPE","service"),quo_curr=currency,
             quo_approved="0")
    qd=[]
    for i,(item,desc,price,qty) in enumerate(lines,1):
        qd.append(record(QUOD_FIELDS,quod_nbr=key,quod_line=i,quod_item=item,
             quod_isinv="0",quod_desc=desc,quod_listprice=price,
             quod_disc=0.0,quod_netprice=price,quod_qty=qty,quod_uom="EA"))
    return {"key":key,"service_order":json.dumps(svd)+"=_="+json.dumps(sv)+"=_=[]",
            "quote":json.dumps(qd)+"=_="+json.dumps(q)+"=_=[]",
            "line_total":sum(Decimal(str(price))*Decimal(str(qty)) for _,_,price,qty in lines)}

def submit_internal_quote(ticket,math,client=None):
    require_config()
    if ticket["finalized_at"]:raise BridgeError("Do not overwrite a finalized ticket")
    payload=build_payloads(ticket,math)
    if payload["line_total"].quantize(Decimal(".01"))!=math["total"]:
        raise BridgeError("BlueSeer lines do not reconcile to the internal quote")
    client=client or BlueSeerClient()
    existing=client.get("dataServORD","getQuoteMstr",payload["key"])
    if isinstance(existing,dict) and existing.get("quo_nbr")==payload["key"]:
        return payload["key"],"exists"
    result=client.post("dataServORD","addQuoteTransaction",payload["quote"])
    return payload["key"],"created"

def submit_service_order(ticket,math,client=None):
    require_config()
    payload=build_payloads(ticket,math)
    if payload["line_total"].quantize(Decimal(".01"))!=math["total"]:
        raise BridgeError("Native service-order lines do not reconcile to quote")
    client=client or BlueSeerClient()
    existing=client.get("dataServORD","getServiceOrderMstr",payload["key"])
    if isinstance(existing,dict) and existing.get("sv_nbr")==payload["key"]:
        return payload["key"],"exists"
    client.post("dataServORD","addServiceOrderTransaction",payload["service_order"])
    return payload["key"],"created"
