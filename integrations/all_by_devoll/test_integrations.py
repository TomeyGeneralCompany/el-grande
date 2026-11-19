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
import customer_bridge
import invoice_bridge

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
 "ABD_BLUESEER_SERVICE_TYPE":"order",
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
 def test_local_qwen_structured_estimate_is_internal(self):
    import io
    import json
    self.assertEqual(app.import_parts(CSV,"authorized vendor sample"),2)
    response=json.dumps({"response":json.dumps({
         "labor_hours_min":1.5,"labor_hours_max":2.5,
         "diagnostic_steps":["Check charging voltage"],
         "parts_to_check":["Starter assembly"],
         "uncertainties":["Confirm engine specification"]})}).encode()
    with patch.object(app.urllib.request,"urlopen",return_value=io.BytesIO(response)):
        app.suggest(self.id)
    with app.db() as con:
        row=con.execute("SELECT * FROM tickets WHERE id=?",(self.id,)).fetchone()
    self.assertEqual(row["labor_hours"],"2.00")
    self.assertIn("INTERNAL PRELIMINARY",row["ai_notes"])
    self.assertIn("DemoSupplier / ST-123",row["ai_notes"])
    self.assertEqual(row["parts_cost"],"0")
 def test_distinct_authorized_supplier_feeds(self):
    import io,json
    class Response(io.BytesIO):
        @property
        def headers(self):return {"Content-Type":"application/json"}
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    with patch.dict(os.environ,{
        "ABD_DETROIT_AXLE_URL":"https://supplier-detroit.example/feed",
        "ABD_DETROIT_AXLE_HOST":"supplier-detroit.example",
        "ABD_DETROIT_AXLE_SUPPLIER":"Detroit Axle",
        "ABD_AUTOZONE_URL":"https://supplier-autozone.example/feed",
        "ABD_AUTOZONE_HOST":"supplier-autozone.example",
        "ABD_AUTOZONE_SUPPLIER":"AutoZone",
        "ABD_PARTS_FEED_URL":""}):
        def fake_open(request,timeout):
            supplier="Detroit Axle" if "detroit" in request.full_url else "AutoZone"
            return Response(json.dumps([{"sku":"S-1","description":"Test starter",
                                         "unit_cost":"100.00","currency":"USD",
                                         "availability":"in_stock",
                                         "checked_at":"2026-11-18T15:00:00Z"}]).encode())
        with patch("parts.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect=fake_open
            feed=parts.supplier_feeds()
        self.assertEqual(len(feed),2)
        with app.db() as con:
            for records,url in feed:parts.upsert_catalogue(con,records,url)
            stored=con.execute("SELECT supplier FROM supplier_parts ORDER BY supplier").fetchall()
        self.assertEqual([x[0] for x in stored],["AutoZone","Detroit Axle"])
 def test_rejects_supplier_spoofing(self):
    import io,json
    class Response(io.BytesIO):
        @property
        def headers(self):return {"Content-Type":"application/json"}
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    with patch.dict(os.environ,{
        "ABD_DETROIT_AXLE_URL":"https://supplier-detroit.example/feed",
        "ABD_DETROIT_AXLE_HOST":"supplier-detroit.example",
        "ABD_DETROIT_AXLE_SUPPLIER":"Detroit Axle"}):
        with patch("parts.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value=Response(json.dumps([
                {"supplier":"AutoZone","sku":"X","description":"Other","unit_cost":"10.00"}
            ]).encode())
            with self.assertRaises(ValueError):parts.supplier_feed("ABD_DETROIT_AXLE")
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
    self.assertEqual(m["sv_type"],"order")
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
            if not self.exists:return None
            if args[1]=="getQuoteDet":
                return [{"quod_qty":2,"quod_netprice":85},
                        {"quod_qty":1,"quod_netprice":140},
                        {"quod_qty":1,"quod_netprice":40}]
            return {"quo_nbr":"ABD000007","quo_cust":"TEST_CUST"}
        def post(self,*args):
            self.calls.append(("post",args))
            return ["0","created"]
    with patch.dict(os.environ,{"ABD_BLUESEER_TRAVEL_ITEM":"TRAVEL"}):
        existing=FakeClient(True)
        self.assertEqual(blue_bridge.submit_internal_quote(self.ticket,self.math,existing)[1],"exists")
        self.assertEqual(len(existing.calls),2)
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
    self.assertEqual(calls[0][1]["Authorization"],"Basic "+base64.b64encode(b"tester:test-pass").decode())
    self.assertEqual(calls[1][1]["sessionid"],"fake-session")
    self.assertEqual(calls[1][1]["id"],"addQuoteTransaction")

class CustomerAndAccountingTests(unittest.TestCase):
 def setUp(self):
    self.env=patch.dict(os.environ,{**CONFIG,"ABD_BLUESEER_AR_ACCOUNT":"1100","ABD_BLUESEER_TERMS":"NET30","ABD_BLUESEER_ENABLE_LIVE_INVOICES":"yes"})
    self.env.start()
    self.ticket={"id":7,"customer":"Jane Doe","phone":"555-0100",
        "location":"Manistee","machine":"2018 Santa Fe","problem":"no start",
        "blue_customer":"ABD000007","blue_ship_to":"ABD000007",
        "labor_hours":"2","labor_rate":"85","parts_charge":"140",
        "travel_charge":"40","extra_charge":"0","parts_cost":"110",
        "finalized_at":"2026-11-18T15:00:00Z"}
    self.math={"labor":Decimal("170.00"),"total":Decimal("350.00"),"basis":Decimal("350.00")}
 def tearDown(self):self.env.stop()
 def test_native_customer_record_format(self):
    import json
    body=customer_bridge.customer_payload(self.ticket,"ABD000007")
    master,contact,shipto=body.split("=_=")
    cm=json.loads(master);cms=json.loads(shipto)
    self.assertEqual(cm["cm_code"],"ABD000007")
    self.assertEqual(cm["cm_ar_acct"],"1100")
    self.assertEqual(cms["cms_shipto"],"ABD000007")
    self.assertEqual(json.loads(contact),[])
 def test_invoice_requires_operator_activation(self):
    with patch.dict(os.environ,{"ABD_BLUESEER_ENABLE_LIVE_INVOICES":"no"}):
        with self.assertRaises(blue_bridge.BridgeError):invoice_bridge.require_invoice_permission()
 def test_invoice_payload_reconciles_and_uses_native_records(self):
    import json
    class Client:
        def get(self,*args):
            return {"cm_code":"ABD000007","cm_terms":"NET30","cm_curr":"USD",
                    "cm_ar_acct":"1100","cm_ar_cc":""}
    with patch.dict(os.environ,{"ABD_BLUESEER_TRAVEL_ITEM":"TRAVEL"}):
        payload=invoice_bridge.prepare_invoice(self.ticket,self.math,"917",Client())
    detail,master,tree=payload.split("=_=")
    lines=json.loads(detail);hdr=json.loads(master)
    self.assertEqual(hdr["sh_id"],"917")
    self.assertEqual(hdr["sh_so"],"ABD000007")
    self.assertEqual(hdr["sh_ar_acct"],"1100")
    self.assertEqual(sum(Decimal(str(p["shd_qty"]))*Decimal(str(p["shd_netprice"])) for p in lines),Decimal("350"))
    self.assertEqual(json.loads(tree),[])
    self.assertEqual(lines[0]["shd_qty"],2)
    self.assertEqual(lines[0]["shd_netprice"],85.0)
 def test_native_invoice_refuses_bill_discrepancy(self):
    class Client:
        def get(self,*args):return {}
    with self.assertRaises(blue_bridge.BridgeError):
        invoice_bridge.prepare_invoice(self.ticket,{**self.math,"basis":Decimal("351")},17,Client())
 def test_duplicate_shipper_refuses_auto_confirmation(self):
    class Client:
        def __init__(self):self.actions=[]
        def get(self,resource,action,ident):
            if action=="getServiceOrderMstr":return {"sv_nbr":"ABD000007","sv_cust":"ABD000007"}
            if action=="getServiceOrderDet":return [{"svd_qty":2,"svd_netprice":85},{"svd_qty":1,"svd_netprice":140},{"svd_qty":1,"svd_netprice":40}]
            if action=="getCustMstr":return {"cm_code":"ABD000007","cm_curr":"USD","cm_ar_acct":"1100"}
            if action=="getShipMstr":return {"sh_id":"917"}
            return None
        def post(self,*args):self.actions.append(args);return ["0","ok"]
    fake=Client()
    with patch.dict(os.environ,{"ABD_BLUESEER_TRAVEL_ITEM":"TRAVEL"}):
        with self.assertRaises(blue_bridge.BridgeError):
            invoice_bridge.post_native_invoice(self.ticket,self.math,"917",fake)
    self.assertEqual(fake.actions,[])
 def test_native_invoice_api_sequence(self):
    class Client:
        def __init__(self):self.calls=[]
        def get(self,resource,action,ident):
            self.calls.append(action)
            if action=="getServiceOrderMstr":return {"sv_nbr":"ABD000007","sv_cust":"ABD000007"}
            if action=="getServiceOrderDet":return [{"svd_qty":2,"svd_netprice":85},{"svd_qty":1,"svd_netprice":140},{"svd_qty":1,"svd_netprice":40}]
            if action=="getCustMstr":return {"cm_code":"ABD000007","cm_curr":"USD","cm_ar_acct":"1100"}
            if action=="getShipMstr":return None
        def post(self,resource,action,body):
            self.calls.append(action);return ["0","ok"]
        def request(self,resource,action,body,**headers):
            self.calls.append(action);return ""
        def call(self,resource,action,**headers):
            self.calls.append(action);return ["0","confirmed"]
    fake=Client()
    with patch.dict(os.environ,{"ABD_BLUESEER_TRAVEL_ITEM":"TRAVEL"}):
        self.assertEqual(invoice_bridge.post_native_invoice(self.ticket,self.math,"917",fake),"917")
    self.assertEqual(fake.calls,["getServiceOrderMstr","getServiceOrderDet","getCustMstr","getShipMstr",
                                  "addShipperTransaction","updateShipperSAC","confirmShipperTransaction"])

if __name__=="__main__":unittest.main()
