#!/usr/bin/env python3
"""End-to-end native transaction checks on a disposable ERP DB.

CI only: must be called with ABD_BOOTSTRAP_DB pointing into build/smoke-java,
never the office user's real database. No customer emails or live postings.
"""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from decimal import Decimal
import blue_bridge
import customer_bridge
import erp_bootstrap

def check_stock_workflows(client, path):
    """Create and receive a purchase order and schedule a work order."""
    site = os.environ["ABD_BLUESEER_SITE"]
    user = os.environ["ABD_BLUESEER_USER"]
    item = "ABD-SMOKE-STOCK"
    order = "89000001"
    receiver = "89000002"
    today = date.today().isoformat()

    item_payload = erp_bootstrap.service_item_payload(item, "Installer test stock", site)
    item_payload.update(it_type="P", it_code="P", it_group="", it_wh="MAIN", it_loc="MAINLOC")
    client.post("dataServINV", "addItemMstr", json.dumps(item_payload))
    assert client.get("dataServINV", "getItemMstr", item)["it_item"] == item

    po = blue_bridge.record(
        """po_nbr po_vend po_ord_date po_due_date po_rmks po_shipvia po_status po_userid
        po_type po_curr po_terms po_site po_buyer po_ap_acct po_ap_cc po_ship
        po_edistatus po_confirm po_taxcode po_entrytype""".split(),
        po_nbr=order, po_vend="ACME", po_ord_date=today, po_due_date=today, po_status="open",
        po_userid=user, po_curr="USD", po_terms="N00", po_site=site,
        po_ap_acct="30000000", po_ap_cc="9999",
    )
    address = blue_bridge.record(
        """poa_code poa_shipto poa_name poa_line1 poa_line2 poa_line3 poa_city poa_state
        poa_zip poa_country poa_contact poa_phone poa_email""".split(),
        poa_code=order, poa_shipto=site, poa_name="Installer test address",
    )
    line = blue_bridge.record(
        """pod_nbr pod_line pod_item pod_venditem pod_ord_qty pod_rcvd_qty pod_netprice
        pod_disc pod_listprice pod_due_date pod_status pod_site pod_ord_date pod_uom
        pod_desc pod_ship pod_taxcode pod_taxamt""".split(),
        pod_nbr=order, pod_line=1, pod_item=item, pod_ord_qty=3, pod_rcvd_qty=0, pod_netprice=12,
        pod_listprice=12, pod_disc=0, pod_taxamt=0, pod_due_date=today, pod_status="open",
        pod_site=site, pod_ord_date=today, pod_uom="EA", pod_desc="Installer test stock",
    )
    client.post("dataServPUR", "addPOTransaction",
                "=_=".join(map(json.dumps, ([line], address, po, [], [], []))))
    assert order in client.get("dataServPUR", "getPOListByVend", "ACME")

    receipt = blue_bridge.record(
        """rv_id rv_vend rv_recvdate rv_status rv_packingslip rv_userid rv_ap_acct rv_ap_cc
        rv_terms rv_site rv_confdate rv_ref rv_rmks""".split(),
        rv_id=receiver, rv_vend="ACME", rv_recvdate=today, rv_status="0", rv_userid=user,
        rv_ap_acct="30000000", rv_ap_cc="9999", rv_terms="N00", rv_site=site,
    )
    received = blue_bridge.record(
        """rvd_id rvd_po rvd_poline rvd_packingslip rvd_item rvd_qty rvd_date rvd_listprice
        rvd_netprice rvd_disc rvd_lot rvd_wh rvd_serial rvd_loc rvd_jobnbr rvd_site
        rvd_status rvd_rline rvd_voqty rvd_cost rvd_uom""".split(),
        rvd_id=receiver, rvd_po=order, rvd_poline=1, rvd_item=item, rvd_qty=3,
        rvd_date=today, rvd_listprice=12, rvd_netprice=12, rvd_disc=0, rvd_wh="MAIN",
        rvd_loc="MAINLOC", rvd_site=site, rvd_status="0", rvd_rline=1, rvd_voqty=0,
        rvd_cost=12, rvd_uom="EA",
    )
    client.post("dataServRCV", "addReceiverTransaction",
                "=_=".join(map(json.dumps, ([received], receipt, None, None))))
    assert receiver in client.call("dataServRCV", "getReceiversFromPO", param1=order, param2="all")
    assert client.get("dataServPUR", "getPODet", order)[0]["pod_rcvd_qty"] == 3
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT SUM(in_qoh) FROM in_mstr WHERE in_item=?", (item,)).fetchone()[0] == 3

    plan = {
        "plan_nbr": 89000003,
        "plan_item": item,
        "plan_site": site,
        "plan_qty_req": 3,
        "plan_qty_sched": 3,
        "plan_date_create": today,
        "plan_date_due": today,
        "plan_date_sched": today,
        "plan_rmks": "",
        "plan_order": order,
        "plan_line": "1",
        "plan_type": "WO",
        "plan_cell": "INSTALLER",
        "plan_is_sched": 1,
    }
    client.post("dataServSCH", "addPlanMstr", json.dumps(plan))
    scheduled = client.call("dataServSCH", "getPlanMstr", param1=str(plan["plan_nbr"]), param2="")
    assert scheduled["plan_date_sched"] == today and scheduled["plan_qty_sched"] == 3
    print("Packaged ERP inventory, purchase order, receipt, stock update and work-order scheduling PASS")


def main():
    path=Path(os.environ.get("ABD_BOOTSTRAP_DB",""))
    if "/build/smoke-java/" not in str(path.resolve()):
        raise SystemExit("Refusing to run native write test against non-disposable BlueSeer database")
    cfg=erp_bootstrap.read_env()
    for k,v in cfg.items():os.environ[k]=v
    ticket={
        "id":950000, "customer":"El Grande Integration Check",
        "phone":"000-000-0000", "location":"Manistee",
        "machine":"Internal test vehicle", "problem":"Internal integration check",
        "labor_hours":"2", "labor_rate":"85.00",
        "parts_charge":"140.00", "parts_cost":"110.00",
        "travel_charge":"0", "extra_charge":"0",
        "blue_customer":"","blue_ship_to":"","finalized_at":None,
    }
    total={"labor":Decimal("170.00"),"total":Decimal("310.00")}
    client=blue_bridge.BlueSeerClient()
    check_stock_workflows(client, path)
    customer,created=customer_bridge.upsert_customer(ticket,client)
    assert customer=="ABD950000"
    ticket["blue_customer"]=customer
    ticket["blue_ship_to"]=customer
    quote,quote_result=blue_bridge.submit_internal_quote(ticket,total,client)
    order,order_result=blue_bridge.submit_service_order(ticket,total,client)
    assert quote=="900950000" and order=="900950000"
    quote_second=blue_bridge.submit_internal_quote(ticket,total,client)
    order_second=blue_bridge.submit_service_order(ticket,total,client)
    print("Native quote first/second:",quote_result,quote_second[1])
    print("Native service order first/second:",order_result,order_second[1])
    print("Native quote response:",str(client.get("dataServORD","getQuoteMstr",quote))[:300])
    print("Native order response:",str(client.get("dataServORD","getServiceOrderMstr",order))[:300])
    with sqlite3.connect(str(path)) as db:
        for table in ("cm_mstr","quo_mstr","sv_mstr"):
            cols=[x[1] for x in db.execute('PRAGMA table_info("'+table+'")')]
            idcol=next((x for x in cols if x in ("cm_code","quo_nbr","sv_nbr")),None)
            if idcol:
                row=db.execute(f"SELECT count(*) FROM {table} WHERE {idcol}=?",("900950000" if table!="cm_mstr" else "ABD950000",)).fetchone()
                print("Native DB",table,"matching records:",row[0])
    assert quote_second[1]=="exists"
    assert order_second[1]=="exists"
    print("Native ERP integration PASS: customer, internal quote, service order, idempotent reads.")
    # A second test job is finalized at a DIFFERENT amount from its estimate.
    # Production invoices must match the actual bill, never the draft quote.
    import invoice_bridge
    complete=dict(ticket,id=950001,blue_customer="",blue_ship_to="",
                  finalized_at="2026-11-18T12:00:00Z")
    final_math={"labor":Decimal("170"),"total":Decimal("310"),
                "basis":Decimal("375.25")}
    cust,_=customer_bridge.upsert_customer(complete,client)
    complete["blue_customer"]=cust
    complete["blue_ship_to"]=cust
    native,kind=blue_bridge.submit_service_order(complete,final_math,client)
    assert native=="900950001" and kind=="created"
    assert blue_bridge.submit_service_order(complete,final_math,client)[1]=="exists"
    shipper=invoice_bridge.reserve_native_shipment_number(client)
    invoice_bridge.post_native_invoice(complete,final_math,shipper,client)
    print("Native ERP disposable final-bill invoice confirmed:",shipper,
          "amount",str(final_math["basis"]))


    # Real native BlueSeer accounts-receivable payment, partial receipt,
    # idempotent re-read, and correction against a disposable invoice.
    import erp_receipts
    opening,_=erp_receipts.native_ar(client,shipper)
    assert opening and opening["ar_type"]=="I",opening
    print("Native invoice open amount before receipt:",opening["ar_open_amt"])
    receipt={"id":950001,"ticket_id":950001,"method":"cash","applied":"125.25",
             "paid_on":"2026-11-18","reference":"","voided_at":None}
    paid_ref=erp_receipts.post(client,receipt,shipper,cust,"BK","payment")
    assert paid_ref=="700950001"
    paid_again=erp_receipts.post(client,receipt,shipper,cust,"BK","payment")
    assert paid_again==paid_ref
    after,_=erp_receipts.native_ar(client,shipper)
    print("Native AR open after partial cash payment:",after["ar_open_amt"])
    assert abs(float(after["ar_open_amt"])-250.00)<0.01, after
    corrected=erp_receipts.post(client,receipt,shipper,cust,"BK","reversal")
    assert corrected=="600950001"
    restored,_=erp_receipts.native_ar(client,shipper)
    print("Native AR open after receipt reversal:",restored["ar_open_amt"])
    assert abs(float(restored["ar_open_amt"])-375.25)<0.01,restored
    full=dict(receipt,id=950002,applied="375.25")
    full_id=erp_receipts.post(client,full,shipper,cust,"BK","payment")
    assert full_id=="700950002"
    closed,_=erp_receipts.native_ar(client,shipper)
    print("Native AR open after final full payment:",closed["ar_open_amt"])
    assert abs(float(closed["ar_open_amt"]))<0.01,closed
    assert closed["ar_status"]=="c",closed
    print("Native cash receipt, partial/full AR settlement, GL and reversal PASS")

if __name__=="__main__":main()
