"""Approve the gold/teal live dashboard against its actual records and supplied PNG logos."""
import tempfile
import unittest
import struct
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import desk
import shop_ui
import dashboard_overview
import mavis_theme

class DashboardGoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=desk.DB
        desk.DB=Path(self.tmp.name)/"shop.sqlite3"
        desk.init()
    def tearDown(self):
        desk.DB=self.old
        self.tmp.cleanup()
    def page(self):
        with desk.db() as con:
            jobs=con.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
        return shop_ui.render(jobs,[],desk.db,desk.amounts)
    def test_two_real_logos_are_bundled_pngs(self):
        root=Path(shop_ui.__file__).parent/"brand"
        for name in ("tomey.png","devoll.png"):
            raw=(root/name).read_bytes()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(raw),2000)
            width,height=struct.unpack(">II",raw[16:24])
            self.assertGreaterEqual(width,96)
            self.assertEqual(width,height)
        html=self.page()
        self.assertIn('src="/brand/tomey.png"',html)
        self.assertIn('src="/brand/devoll.png"',html)
        self.assertIn('class="sidebar-brand"',html)
        self.assertIn("Tomey General Company LLC logo",html)
        self.assertIn("All by Devoll, LLC logo",html)
    def test_house_gold_red_box_and_teal_cards(self):
        css=mavis_theme.CSS
        for phrase in ("background:#e09915","background:#c9031e","border:3px solid #00c4bf",
                       ".dashboard-overview",".sidebar-links",".dashboard-company"):
            self.assertIn(phrase,css)
    def test_real_job_data_and_no_fake_activity(self):
        job,_=desk.create_ticket({
          "customer":"Motorist Alpha",
          "machine":"2018 Hyundai Santa Fe",
          "service":"Starter replacement",
          "problem":"No crank"}, "manual:dashboard-1")
        page=self.page()
        self.assertIn("Motorist Alpha",page)
        self.assertIn("2018 Hyundai Santa Fe",page)
        self.assertIn("Starter replacement",page)
        self.assertIn("Jobs (open)",page)
        self.assertIn("Upcoming Jobs",page)
        self.assertNotIn("Jacob M.",page)
        self.assertNotIn("Lisa R.",page)
    def test_cash_receipts_reflected_as_real_balances(self):
        ticket,_=desk.create_ticket({"customer":"Cash customer","problem":"Fixed starter"},"manual:dashboard-2")
        desk.finalize_ticket(ticket,"400.00")
        desk.record_customer_payment(ticket,{"amount_received":"150.00","method":"cash"})
        page=self.page()
        self.assertIn("Cash (safe)",page)
        self.assertIn("$150.00",page)
        self.assertIn("Unpaid customer invoices",page)
        self.assertIn("$250.00",page)
        self.assertIn("Tomey General (15%)",page)
        self.assertIn("Operator (85%)",page)
        with desk.db() as con:
            row=con.execute("SELECT * FROM tickets WHERE id=?",(ticket,)).fetchone()
        self.assertEqual(desk.amounts(row)["parent"],Decimal("60.00"))
    def test_job_forms_and_invoice_routes_preserved(self):
        page=self.page()
        self.assertIn('action="/ticket/new"',page)
        self.assertIn('href="/bank"',page)
        self.assertIn('href="/settings"',page)
        self.assertIn('href="/bank#cash-count"',page)
        self.assertIn("New service request",page)

if __name__=="__main__":unittest.main()
