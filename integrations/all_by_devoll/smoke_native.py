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
    assert quote=="ABD950000" and order=="ABD950000"
    assert blue_bridge.submit_internal_quote(ticket,total,client)[1]=="exists"
    assert blue_bridge.submit_service_order(ticket,total,client)[1]=="exists"
    print("Native ERP integration PASS: customer, internal quote, service order, idempotent reads.")
    print("No invoices or GL entries were posted.")

if __name__=="__main__":main()
