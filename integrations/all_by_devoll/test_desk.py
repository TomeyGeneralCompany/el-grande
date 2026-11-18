"""No-network tests for the All by Devoll ticket and settlement desk."""
import email
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

FILE=Path(__file__).with_name("desk.py")
spec=importlib.util.spec_from_file_location("abd_desk",FILE)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class DeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app.DB=Path(self.tmp.name)/"data.sqlite3"
        app.init()
    def tearDown(self):
        self.tmp.cleanup()
    def create(self):
        id_,added=app.create_ticket({"customer":"Jane Doe","phone":"555-0102","problem":"Starter won't crank","service":"Automotive diagnosis or repair"}, "email:<test@example.com>")
        self.assertTrue(added)
        return id_
    def row(self,id_):
        with app.db() as con: return con.execute("SELECT * FROM tickets WHERE id=?",(id_,)).fetchone()
    def test_ticket_and_idempotency(self):
        id_=self.create()
        new,added=app.create_ticket({"customer":"Changed name"}, "email:<test@example.com>")
        self.assertEqual(new,id_)
        self.assertFalse(added)
        self.assertEqual(self.row(id_)["customer"],"Jane Doe")
    def test_exact_off_top_split(self):
        id_=self.create()
        app.update_ticket(id_,{"labor_hours":"2","labor_rate":"85","parts_charge":"140","travel_charge":"40","parts_cost":"110"})
        quote=app.amounts(self.row(id_))
        self.assertEqual(quote["total"],Decimal("350.00"))
        self.assertEqual(quote["parent"],Decimal("52.50"))
        self.assertEqual(quote["operator"],Decimal("297.50"))
        self.assertEqual(quote["after_parts"],Decimal("187.50"))
    def test_final_bill_overrides_quote_and_locks(self):
        id_=self.create()
        app.update_ticket(id_,{"parts_charge":"50"})
        app.finalize_ticket(id_,"100.00")
        amount=app.amounts(self.row(id_))
        self.assertEqual(amount["parent"],Decimal("15.00"))
        self.assertEqual(amount["operator"],Decimal("85.00"))
        self.assertTrue(amount["finalized"])
        with self.assertRaises(ValueError):app.finalize_ticket(id_,"200")
        with self.assertRaises(ValueError):app.update_ticket(id_,{"parts_charge":"100"})
    def test_zero_bill(self):
        id_=self.create();app.finalize_ticket(id_,"0")
        self.assertEqual(app.amounts(self.row(id_))["parent"],Decimal("0.00"))
    def test_fractional_cent_rounding(self):
        id_=self.create();app.finalize_ticket(id_,"0.03")
        self.assertEqual(app.amounts(self.row(id_))["parent"],Decimal("0.00"))
        self.assertEqual(app.amounts(self.row(id_))["operator"],Decimal("0.03"))
    def test_invalid_amounts_refused(self):
        id_=self.create()
        for number in ("-1","NaN","Infinity","1000000000","hello"):
            with self.assertRaises(ValueError):app.finalize_ticket(id_,number)
    def test_state_validation(self):
        id_=self.create()
        with self.assertRaises(ValueError):app.update_ticket(id_,{"status":"whatever"})
    def test_plaintext_email(self):
        m=email.message_from_string("""Subject: New All by Devoll service request
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Name: Jane Doe
Best callback number: 555-1212
City or township: Manistee
Service type: Automotive diagnosis or repair
Vehicle, machine, equipment, or removal job: 2018 Santa Fe
What needs to be done?: Starter does not crank
""")
        f,_=app.parse_request(m)
        self.assertEqual(f["customer"],"Jane Doe")
        self.assertEqual(f["phone"],"555-1212")
        self.assertEqual(f["machine"],"2018 Santa Fe")
    def test_html_table_email(self):
        m=email.message_from_string("""Subject: New All by Devoll service request
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

<table><tr><th>Name</th><td>Jane Doe</td></tr><tr><td>Service type</td><td>Scrap removal</td></tr></table>
""")
        f,_=app.parse_request(m)
        self.assertEqual(f["customer"],"Jane Doe")
        self.assertEqual(f["service"],"Scrap removal")
    def test_quotes_are_not_final_settlements(self):
        id_=self.create()
        app.update_ticket(id_,{"labor_hours":"2","labor_rate":"85"})
        self.assertFalse(app.amounts(self.row(id_))["finalized"])
        self.assertEqual(self.row(id_)["bill_total"],"")
    def test_render_is_escaped(self):
        id_,_=app.create_ticket({"customer":"<script>alert(1)</script>"}, "manual:test")
        page=app.render([self.row(id_)])
        self.assertNotIn("<script>",page)
        self.assertIn("&lt;script&gt;",page)
    def test_events_recorded(self):
        id_=self.create();app.finalize_ticket(id_,"350")
        with app.db() as con:
            ev=con.execute("SELECT event FROM events WHERE ticket_id=? ORDER BY id",(id_,)).fetchall()
        self.assertEqual([v[0] for v in ev],["received","bill_finalized"])

if __name__=="__main__":
    unittest.main()
