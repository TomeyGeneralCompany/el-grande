"""Operator UI regression: workflow first, accounting private, connections honest."""
import os
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import desk
import shop_ui

class ShopUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        desk.DB=Path(self.tmp.name)/"test.sqlite3"
        desk.init()
        self.job,_=desk.create_ticket({
            "customer":"Jane Customer","phone":"231-555-0100",
            "service":"Brake service","machine":"2018 Hyundai Santa Fe",
            "problem":"Pads are squealing and warning light is on"},"manual:shop-ui-test")
    def tearDown(self):
        self.tmp.cleanup()
    def page(self,status=None):
        with desk.db() as con:
            tickets=con.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
        return shop_ui.render(tickets,[],desk.db,desk.amounts,status or {
            "mailbox":False,"report":False,
            "erp":{"running":False,"configured":False}})
    def test_operator_branding_not_settlement_branding(self):
        page=self.page()
        self.assertIn("ALL BY DEVOLL",page)
        self.assertIn("Today's job desk",page)
        self.assertNotIn("Tomey General 15%",page)
        self.assertNotIn("No invented prices",page)
        self.assertNotIn("automatic customer quotes",page)
        self.assertNotIn("15% applies",page)
    def test_job_workflow_not_hidden(self):
        page=self.page()
        for label in ('name="labor_hours"','name="parts_cost"','name="work_performed"',
                      'name="actual_labor_cost"','name="actual_parts_cost"',
                      'name="actual_hours"','name="actual_invoice"',
                      "Save estimate","Save completed job","Create service order"):
            self.assertIn(label,page)
        self.assertIn("www.google.com/search",page)
        self.assertIn("Detroit Axle",page)
        self.assertIn("AutoZonePro",page)
    def test_customer_data_is_escaped(self):
        _,_=desk.create_ticket({"customer":"<script>alert(1)</script>"},
            "manual:escape-ui-test")
        page=self.page()
        self.assertNotIn("<script>alert(1)</script>",page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",page)
    def test_connection_labels_reflect_reality(self):
        page=self.page({"mailbox":False,"report":False,
                       "erp":{"running":False,"configured":False}})
        self.assertIn("Business inbox not connected",page)
        self.assertIn("BlueSeer not responding",page)
        page=self.page({"mailbox":True,"report":True,
                       "erp":{"running":True,"configured":False}})
        self.assertIn("BlueSeer running · business setup needed",page)
        self.assertIn("Business inbox configured",page)
    def test_closed_job_has_actual_invoice_not_edit_form(self):
        desk.finish_job(self.job,{
            "work_performed":"Changed pads and tested braking",
            "actual_hours":"2","actual_labor_cost":"20",
            "actual_parts_cost":"50","actual_other_cost":"0",
            "actual_invoice":"350","started_at":"","finished_at":""})
        page=self.page()
        self.assertIn("Completed job",page)
        self.assertIn("350.00",page)
        self.assertNotIn('name="actual_invoice"',page)
        self.assertNotIn("Tomey General 15%",page)

if __name__=="__main__":unittest.main()
