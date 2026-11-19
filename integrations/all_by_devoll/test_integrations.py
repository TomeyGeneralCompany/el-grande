"""Regression checks for supplier pricing and part estimates."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

import parts

FILE=Path(__file__).with_name("desk.py")
spec=importlib.util.spec_from_file_location("abd_desk_integration",FILE)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

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
