"""Native BlueSeer 8.0 service-order invoicing via shipper -> AR/GL transaction.

Only explicit operator actions, and only after configuration and successful source
document reconciliation. A remote ambiguous commit must be manually reconciled.
"""
import json
import os
from datetime import date
from decimal import Decimal
import blue_bridge

SHIP_FIELDS=("sh_id","sh_cust","sh_ship","sh_pallets","sh_boxes","sh_shipvia",
             "sh_shipdate","sh_po_date","sh_ref","sh_po","sh_rmks","sh_userid",
             "sh_site","sh_curr","sh_wh","sh_cust_terms","sh_taxcode",
             "sh_ar_acct","sh_ar_cc","sh_type","sh_so","sh_shipfrom",
             "sh_trailer","sh_status","sh_char1","sh_char2","sh_char3")
SHD_FIELDS=("shd_id","shd_line","shd_item","shd_custitem","shd_so","shd_soline",
            "shd_date","shd_po","shd_qty","shd_uom","shd_curr",
            "shd_netprice","shd_disc","shd_listprice","shd_desc",
            "shd_wh","shd_loc","shd_taxamt","shd_cont","shd_ref",
            "shd_serial","shd_site","shd_bom","shd_packqty","shd_kvpair")

def require_invoice_permission():
    if os.getenv("ABD_BLUESEER_ENABLE_LIVE_INVOICES")!="yes":
        raise blue_bridge.BridgeError("Live BlueSeer invoice posting disabled. Set ABD_BLUESEER_ENABLE_LIVE_INVOICES=yes only after controlled dry-run verification.")
    blue_bridge.require_config()

def prepare_invoice(ticket,math,shipper_id,client):
    if not ticket["finalized_at"]:raise blue_bridge.BridgeError("Finalize bill before invoicing")
    if math["total"]!=math["basis"]:
        raise blue_bridge.BridgeError("Final bill must match the reviewed service-order line total; reconcile the job before native invoicing")
    shipto=(ticket["blue_ship_to"] if "blue_ship_to" in ticket.keys() and ticket["blue_ship_to"] else os.getenv("ABD_BLUESEER_SHIP_TO","")).strip()
    if not shipto:raise blue_bridge.BridgeError("Enter the correct BlueSeer ship-to code on this ticket before invoicing")
    if not str(shipper_id).isdigit() or int(shipper_id)<=0:
        raise blue_bridge.BridgeError("BlueSeer native shipper ID must be a positive integer")
    key,today,cust,site=blue_bridge.header_data(ticket,math)
    customer=client.get("dataServCUS","getCustMstr",cust)
    if not isinstance(customer,dict) or customer.get("cm_code")!=cust:
        raise blue_bridge.BridgeError("BlueSeer customer code not found: "+cust)
    if not customer.get("cm_ar_acct"):
        raise blue_bridge.BridgeError("Customer is missing a BlueSeer AR account")
    currency=customer.get("cm_curr") or os.getenv("ABD_BLUESEER_CURRENCY","USD")
    if currency!="USD":raise blue_bridge.BridgeError("Only USD native invoicing supported")
    lines=blue_bridge.sales_lines(ticket,math)
    header=blue_bridge.record(
        SHIP_FIELDS,sh_id=str(shipper_id),sh_cust=cust,sh_ship=shipto,
        sh_pallets=0,sh_boxes=0,sh_shipdate=today,sh_po_date=today,
        sh_ref=key,sh_po=key,
        sh_rmks=("All by Devoll completed service - "+key)[:255],
        sh_userid=os.environ["ABD_BLUESEER_USER"],sh_site=site,
        sh_curr=currency,sh_cust_terms=customer.get("cm_terms") or "",
        sh_taxcode="",sh_ar_acct=customer["cm_ar_acct"],
        sh_ar_cc=customer.get("cm_ar_cc") or "",sh_type="S",sh_so=key,
        sh_shipfrom=site,sh_status="open",sh_char2="")
    details=[]
    for i,(item,desc,price,qty) in enumerate(lines,1):
        details.append(blue_bridge.record(
            SHD_FIELDS,shd_id=str(shipper_id),shd_line=i,shd_item=item,
            shd_custitem=item,shd_so=key,shd_soline=i,
            shd_date=today,shd_qty=qty,shd_uom="EA",shd_curr=currency,
            shd_netprice=price,shd_listprice=price,shd_disc=0.0,shd_desc=desc,
            shd_taxamt=0,shd_cont="0",shd_site=site,shd_packqty=1))
    price=sum((Decimal(str(d["shd_qty"]))*Decimal(str(d["shd_netprice"])) for d in details),Decimal("0")).quantize(Decimal(".01"))
    if price!=math["basis"]:
        raise blue_bridge.BridgeError("Native invoice lines differ from finalized bill")
    payload=json.dumps(details)+"=_="+json.dumps(header)+"=_=[]"
    return payload

def reserve_native_shipment_number(client):
    value=client.call("dataServOV","getNextNbr",param1="shipper")
    if not isinstance(value,int) or value<=0:
        raise blue_bridge.BridgeError("BlueSeer did not issue a valid native shipper number")
    return str(value)

def post_native_invoice(ticket,math,shipper_id,client=None):
    """Creates and confirms a real native invoice. Do not call automatically on intake."""
    require_invoice_permission()
    client=client or blue_bridge.BlueSeerClient()
    key,today,cust,site=blue_bridge.header_data(ticket,math)
    service=client.get("dataServORD","getServiceOrderMstr",key)
    if not isinstance(service,dict) or service.get("sv_nbr")!=key:
        raise blue_bridge.BridgeError("Create the native BlueSeer service order first")
    if service.get("sv_cust")!=cust:
        raise blue_bridge.BridgeError("Native service order customer does not match invoice")
    blue_bridge.verify_existing_lines(client,"service_order",key,math["basis"],cust)
    payload=prepare_invoice(ticket,math,shipper_id,client)
    existing=client.get("dataServSHP","getShipMstr",str(shipper_id))
    if isinstance(existing,dict) and existing.get("sh_id")==str(shipper_id):
        # Never confirm an already existing invoice blindly. The caller must reconcile
        # a previously unknown outcome with its native AR/GL records.
        raise blue_bridge.BridgeError("Shipper number already exists; reconcile in BlueSeer before retrying")
    client.post("dataServSHP","addShipperTransaction",payload)
    # Upstream ServiceOrderMaint.autoInvoiceOrder calls updateShipperSAC then confirm.
    client.request("dataServSHP","updateShipperSAC",b"",param1=str(shipper_id))
    confirmation=client.call("dataServSHP","confirmShipperTransaction",
                             param1="serviceorder",param2=str(shipper_id),param3=today)
    if not isinstance(confirmation,list) or not confirmation or confirmation[0]!="0":
        raise blue_bridge.BridgeError("Native invoicing returned an unsuccessful confirmation: "+str(confirmation)[:200])
    return str(shipper_id)
