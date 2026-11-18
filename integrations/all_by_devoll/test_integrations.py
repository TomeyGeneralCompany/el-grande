"""Regression checks for supplier pricing and native BlueSeer request shapes."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

import parts
import blue_bridge

FILE=Path(__file__).with_name("desk.py")
spec=importlib.util.spec_from_file_location("abd_desk_integration",FILE)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

CONFIG={
 "ABD_BLUESEER_URL":"http://127.0.0.1:8080/bsapi",
 "ABD_BLUESEER_USER":"test_operator",
 "ABD_BLUESEER_PASSWORD":"not_a_real_password",
 "ABD_BLUESEER_SITE":"TEST",
 "ABD_BLUESEER_CUSTOMER":"TEST_CUST",
 "ABD_BLUESEER_LABOR_ITEM":"LABOR",
 "ABD_BLUESEER_PARTS_ITEM":"PARTS",
 "ABD_BLUESEER_SERVICE_TYPE":"quote",
}
CSV="""supplier,sku,description,unit_cost,suggested_sale,currency,availability,checked_at,supplier_url
DemoSupplier,ST-123,Starter assembly,110.00,140.00,USD,in_stock,2026-11-18T12:00:00Z,https://supplier.example/parts/ST-123
DemoSupplier,BT-010,Battery,70.00,,USD,order,2026-11-18T12:00:00Z,
"""
class SupplierTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    app.DB=Path(self.tmp.name)/"desk.sqlite3"
    app.init()
    self.id,_=app.create_ticket({"customer":"Jane","phone":"555-0100","machine":"2018 Santa Fe","problem":"no start"},"manual:supplier-test")
 def tearDown(self):self.tmp.cleanup()
 def test_supplier_csv_and_quote_calculation(self):
    self.assertEqual(app.import_parts(CSV,"test supplier export"),2)
    app.save_part(self.id,"DemoSupplier","ST-123","2")
    with app.db() as con:
        attached,cost,sale=parts.ticket_totals(con,self.id)
        row=con.execute("SELECT * FROM tickets WHERE id=?",(self.id,)).fetchone()
    self.assertEqual(cost,Decimal("220.00"))
    self.assertEqual(sale,Decimal("280.00"))
    self.assertEqual(row["parts_cost"],"220.00")
    self.assertEqual(row["parts_charge"],"280.00")
    self.assertEqual(attached[0]["checked_at"],"2026-11-18T12:00:00Z")
    self.assertEqual(app.amounts(row)["parent"],Decimal("42.00"))
 def test_rejects_bad_feed(self):
    with self.assertRaises(ValueError):app.import_parts("sku,description\nX,Y\n","test")
    bad=CSV.replace("110.00","NaN")
    with self.assertRaises(ValueError):app.import_parts(bad,"test")
    with app.db() as con:
        self.assertEqual(con.execute("SELECT count(*) FROM supplier_parts").fetchone()[0],0)
 def test_no_part_added_after_finalization(self):
    app.import_parts(CSV,"test")
    app.finalize_ticket(self.id,"350")
    with self.assertRaises(ValueError):app.save_part(self.id,"DemoSupplier","ST-123","1")
 def test_no_unverified_price_fabricated(self):
    with self.assertRaises(LookupError):app.save_part(self.id,"SupplierNeverConfigured","FAKE","1")
 def test_out_of_stock_refused(self):
    app.import_parts(CSV.replace("in_stock","out_of_stock"),"test")
    with self.assertRaises(ValueError):app.save_part(self.id,"DemoSupplier","ST-123","1")
 def test_supplier_feed_rejects_unauthorized_origin(self):
    with patch.dict(os.environ,{"ABD_PARTS_FEED_URL":"http://evil.example/prices","ABD_PARTS_FEED_HOST":"evil.example"}):
        with self.assertRaises(ValueError):parts.supplier_feed()

class BlueSeerTests(unittest.TestCase):
 def setUp(self):
    self.env=patch.dict(os.environ,CONFIG)
    self.env.start()
    self.ticket={"id":7,"customer":"Jane","phone":"555","machine":"2018 Santa Fe","problem":"Starter not working",
                 "blue_customer":"","labor_hours":"2","labor_rate":"85","parts_charge":"140","travel_charge":"40",
                 "extra_charge":"0","parts_cost":"100","finalized_at":None}
    self.math={"labor":Decimal("170.00"),"total":Decimal("350.00")}
 def tearDown(self):self.env.stop()
 def test_native_records_are_valid_and_internal_only(self):
    with patch.dict(os.environ,{"ABD_BLUESEER_TRAVEL_ITEM":"TRAVEL"}):
        payload=blue_bridge.build_payloads(self.ticket,self.math)
    self.assertEqual(payload["key"],"ABD000007")
    self.assertEqual(payload["line_total"],Decimal("350.0"))
    detail,master,empty=payload["service_order"].split("=_=")
    import json
    d=json.loads(detail);m=json.loads(master)
    self.assertEqual(m["sv_cust"],"TEST_CUST")
    self.assertEqual(m["sv_type"],"quote")
    self.assertIn("DO NOT SEND",m["sv_rmks"])
    self.assertEqual(len(d),3)
    self.assertEqual(d[0]["svd_item"],"LABOR")
    self.assertEqual(d[1]["svd_item"],"PARTS")
    self.assertEqual(d[2]["svd_item"],"TRAVEL")
    qdetails,qmaster,_=payload["quote"].split("=_=")
    self.assertEqual(len(json.loads(qdetails)),3)
    self.assertEqual(json.loads(qmaster)["quo_approved"],"0")
 def test_blue_seer_refuses_remote_http(self):
    with patch.dict(os.environ,{"ABD_BLUESEER_URL":"http://example.com/bsapi"}):
        with self.assertRaises(blue_bridge.BridgeError):blue_bridge.require_config()
 def test_rejects_missing_part_item_code(self):
    with patch.dict(os.environ,{"ABD_BLUESEER_PARTS_ITEM":""}):
        with self.assertRaises(blue_bridge.BridgeError):
            blue_bridge.build_payloads(self.ticket,self.math)
 def test_native_transaction_deduplication(self):
    class FakeClient:
        def __init__(self,exists=False):
            self.exists=exists;self.calls=[]
        def get(self,*args):
            self.calls.append(("get",args))
            return {"quo_nbr":"ABD000007"} if self.exists else None
        def post(self,*args):
            self.calls.append(("post",args))
            return ["0","created"]
    with patch.dict(os.environ,{"ABD_BLUESEER_TRAVEL_ITEM":"TRAVEL"}):
        existing=FakeClient(True)
        self.assertEqual(blue_bridge.submit_internal_quote(self.ticket,self.math,existing)[1],"exists")
        self.assertEqual(len(existing.calls),1)
        new=FakeClient(False)
        self.assertEqual(blue_bridge.submit_internal_quote(self.ticket,self.math,new)[1],"created")
        self.assertEqual([x[0] for x in new.calls],["get","post"])
 def test_blue_auth_and_native_result_parsing(self):
    import base64
    calls=[]
    def transport(url,headers,body):
        calls.append((url,headers,body))
        if url.endswith("/authServ"):
            return base64.b64encode(b"fake-session").decode()
        return '["0","accepted"]'
    client=blue_bridge.BlueSeerClient(
        base="http://127.0.0.1:8080/bsapi",user="tester",password="test-pass",transport=transport)
    client.post("dataServORD","addQuoteTransaction","sample")
    self.assertEqual(calls[0][1]["pass"],"test-pass")
    self.assertEqual(calls[1][1]["sessionid"],"fake-session")
    self.assertEqual(calls[1][1]["id"],"addQuoteTransaction")

if __name__=="__main__":unittest.main()
