"""Operator UI regression: workflow first, accounting private, connections honest."""
import os
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
from threading import Event
import desk

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
        return desk.render_dashboard()
    def test_operator_branding_not_settlement_branding(self):
        page=self.page()
        self.assertIn("All by Devoll, LLC",page)
        self.assertIn("Current Job",page)
        self.assertNotIn("Tomey General 15%",page)
        self.assertNotIn("No invented prices",page)
        self.assertNotIn("automatic customer quotes",page)
        self.assertNotIn("15% applies",page)
    def test_job_workflow_not_hidden(self):
        page=desk.render_ticket(self.job)
        for label in ('name="labor_hours"','name="parts_cost"','name="work_performed"',
                      'name="actual_labor_cost"','name="actual_parts_cost"',
                      'name="actual_hours"','name="actual_invoice"',
                      "Save estimate","Finish Job &amp; Create Invoice"):
            self.assertIn(label,page)
        self.assertIn("www.google.com/search",page)
        self.assertIn("Detroit Axle",page)
        self.assertIn("AutoZonePro",page)
    def test_dashboard_render_requires_no_native_service(self):
        self.assertIn("Job calendar", desk.render_dashboard())
        self.assertNotIn("erp", desk.system_status())

    def test_optional_estimate_runs_in_background_one_at_a_time(self):
        started, release, finished = Event(), Event(), Event()
        def fake_suggest(ticket_id):
            self.assertEqual(ticket_id, self.job)
            started.set()
            release.wait(timeout=3)
        def worker(ticket_id):
            try:
                actual_worker(ticket_id)
            finally:
                finished.set()
        actual_worker = desk.run_estimate
        with patch.object(desk, "suggest", side_effect=fake_suggest), patch.object(desk, "run_estimate", side_effect=worker):
            try:
                desk.start_estimate(self.job)
                self.assertTrue(started.wait(timeout=3))
                self.assertIn("Estimate running", desk.render_ticket(self.job))
                with self.assertRaisesRegex(ValueError, "already running"):
                    desk.start_estimate(self.job)
            finally:
                release.set()
                self.assertTrue(finished.wait(timeout=3))
        self.assertIn("Generate labor &amp; diagnostic estimate", desk.render_ticket(self.job))

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
    def test_closed_job_has_actual_invoice_not_edit_form(self):
        desk.finish_job(self.job,{
            "work_performed":"Changed pads and tested braking",
            "actual_hours":"2","actual_labor_cost":"20",
            "actual_parts_cost":"50","actual_other_cost":"0",
            "actual_invoice":"350","started_at":"","finished_at":""})
        page=desk.render_ticket(self.job)
        self.assertIn("Completed job",page)
        self.assertIn("350.00",page)
        self.assertNotIn('name="actual_invoice"',page)
        self.assertNotIn("Tomey General 15%",page)

if __name__=="__main__":unittest.main()
