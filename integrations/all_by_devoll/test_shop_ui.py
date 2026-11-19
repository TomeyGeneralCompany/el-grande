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
    def page(self):
        with desk.db() as con:
            tickets=con.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
        return shop_ui.render(tickets,[],desk.db,desk.amounts)
    def test_operator_branding_not_settlement_branding(self):
        page=self.page()
        self.assertIn("All by Devoll, LLC",page)
        self.assertIn("Current Job",page)
        self.assertNotIn("Tomey General 15%",page)
        self.assertNotIn("No invented prices",page)
        self.assertNotIn("automatic customer quotes",page)
        self.assertNotIn("15% applies",page)
    def test_job_workflow_not_hidden(self):
        page=self.page()
        for label in ('name="labor_hours"','name="parts_cost"','name="work_performed"',
                      'name="actual_labor_cost"','name="actual_parts_cost"',
                      'name="actual_hours"','name="actual_invoice"',
                      "Save estimate","Finish Job &amp; Create Invoice"):
            self.assertIn(label,page)
        self.assertIn("www.google.com/search",page)
        self.assertIn("Detroit Axle",page)
        self.assertIn("AutoZonePro",page)
        self.assertNotIn("ERP customer code",page)
        self.assertNotIn("BlueSeer accounting",page)
    def test_dashboard_render_skips_erp_probe(self):
        with desk.db() as con:
            ticket = con.execute("SELECT * FROM tickets WHERE id=?", (self.job,)).fetchone()
        erp = {"running": True, "configured": True}
        with patch.object(desk, "erp_status", return_value=erp) as probe:
            self.assertIn("Job calendar", desk.render([ticket]))
            probe.assert_not_called()
            self.assertEqual(desk.system_status()["erp"], erp)
            probe.assert_called_once()

    def test_customer_data_is_escaped(self):
        _,_=desk.create_ticket({"customer":"<script>alert(1)</script>"},
            "manual:escape-ui-test")
        page=self.page()
        self.assertNotIn("<script>alert(1)</script>",page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",page)
    def test_settings_are_in_app_not_instructions_on_dashboard(self):
        page=self.page()
        self.assertIn('href="/settings"',page)
        self.assertNotIn('open <strong>El Grande Setup</strong>',page)
        self.assertNotIn("Office connections",page)
        self.assertNotIn("BlueSeer not responding",page)
    def test_unchanged_price_after_native_sync_is_not_rejected(self):
        with desk.db() as con:
            con.execute("INSERT INTO blue_sync(ticket_id,kind,record_number,state,updated_at) VALUES (?,?,?,?,?)",
                        (self.job,"quote","ABD000001","synced",desk.utc()))
        desk.update_ticket(self.job,{"labor_hours":"0.00","labor_rate":"0.00","parts_charge":"0.00",
                                     "notes":"Spoke to customer"})
        with desk.db() as con:
            row=con.execute("SELECT notes FROM tickets WHERE id=?",(self.job,)).fetchone()
        self.assertEqual(row["notes"],"Spoke to customer")
        with self.assertRaises(ValueError):
            desk.update_ticket(self.job,{"parts_charge":"5.00"})
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
