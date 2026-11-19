"""Approve the gold/teal live dashboard against its actual records and supplied PNG logos."""
import tempfile
import unittest
import struct
from threading import Thread
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
import desk
import shop_ui
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
        return desk.render_dashboard()
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
        self.assertIn("Job calendar",page)
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

    def test_dashboard_pages_jobs_but_counts_and_balances_use_all_history(self):
        oldest, _ = desk.create_ticket({"customer":"Old billing customer"}, "manual:old")
        desk.finalize_ticket(oldest, "123.45")
        desk.record_customer_payment(oldest, {"amount_received":"0.05","method":"check"})
        with desk.db() as con:
            stamp = desk.utc()
            con.executemany("""INSERT INTO tickets(source_id,received_at,customer,updated_at)
                VALUES(?,?,?,?)""", ((f"manual:extra-{i}",stamp,f"Fixture {i}",stamp) for i in range(501)))
        page = self.page()
        self.assertEqual(page.count('<article class="ticket"'), 25)
        self.assertIn('<strong>Jobs (total)</strong><span class="overview-money">502</span>',page)
        self.assertIn('<strong>Unpaid customer invoices</strong><span class="overview-money">$123.40</span>',page)
        self.assertNotIn('name="actual_invoice"',page)
        older = desk.render_dashboard({"before":["478"]})
        self.assertIn('id="ticket-477"',older)
        self.assertIn("Newer jobs",older)
        newer = desk.render_dashboard({"after":["477"]})
        self.assertIn('id="ticket-502"',newer)
        detail = desk.render_ticket(oldest)
        self.assertIn("Old billing customer",detail)
        self.assertIn("123.40",detail)
        self.assertIn("Mark Paid",detail)

    def test_calendar_schedules_existing_job_reschedules_and_removes_it(self):
        job,_=desk.create_ticket({"customer":"Shop <customer>","problem":"Replace starter"}, "manual:calendar")
        # Exercise initialization on a database created before appointments existed.
        with desk.db() as con:
            con.execute("DROP TABLE job_appointments")
        desk.init()

        with ThreadingHTTPServer(("127.0.0.1", 0), desk.Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def submit(path, **data):
                request = Request(base + path, urlencode(data).encode(), headers={"Origin": base})
                with urlopen(request, timeout=5) as response:
                    return response.read().decode(), response.url

            try:
                page, url = submit("/appointments/save", ticket_id=job, date="2026-12-01", time="09:30")
                self.assertIn("calendar=2026-12", url)
                self.assertIn('id="appointments-2026-12-01"', page)
                self.assertIn("Shop &lt;customer&gt;", page)
                self.assertIn("9:30 AM", page)
                self.assertIn(f'href="/ticket/{job}">Shop &lt;customer&gt;</a>', page)
                with urlopen(base + f"/ticket/{job}", timeout=5) as response:
                    self.assertIn('name="actual_invoice"', response.read().decode())

                with urlopen(base + f"/?calendar=2026-12&edit_appointment={job}", timeout=5) as response:
                    editor = response.read().decode()
                self.assertIn(f'<option value="{job}" selected>', editor)
                self.assertIn('name="time" value="09:30"', editor)

                page, _ = submit("/appointments/save", ticket_id=job, date="2027-01-05", time="13:00")
                self.assertIn('id="appointments-2027-01-05"', page)
                with desk.db() as con:
                    self.assertEqual(con.execute("SELECT count(*) FROM job_appointments").fetchone()[0], 1)

                with self.assertRaises(HTTPError) as invalid:
                    submit("/appointments/save", ticket_id=job, date="2027-02-30", time="13:00")
                self.assertEqual(invalid.exception.code, 400)
                desk.finalize_ticket(job, "400.00")
                with self.assertRaises(HTTPError) as finalized:
                    submit("/appointments/save", ticket_id=job, date="2027-01-06", time="13:00")
                self.assertEqual(finalized.exception.code, 400)

                page, _ = submit("/appointments/remove", ticket_id=job, calendar="2027-01")
                self.assertIn("No appointments this month.", page)
                with desk.db() as con:
                    self.assertEqual(con.execute("SELECT count(*) FROM job_appointments").fetchone()[0], 0)
                    self.assertEqual(con.execute("SELECT id FROM tickets").fetchone()[0], job)
            finally:
                server.shutdown()
                thread.join(timeout=5)

if __name__=="__main__":unittest.main()
