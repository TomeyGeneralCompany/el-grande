#!/usr/bin/env python3
"""End-to-end native customer / quote / service-order test on a disposable ERP DB.

CI only: must be called with ABD_BOOTSTRAP_DB pointing into build/smoke-java,
never the office user's real database. No customer emails or invoice postings.
"""
import os
from pathlib import Path
from decimal import Decimal
import blue_bridge
import customer_bridge
import erp_bootstrap

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
    import sqlite3
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
