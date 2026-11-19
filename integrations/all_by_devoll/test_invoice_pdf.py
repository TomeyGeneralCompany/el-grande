"""PDF invoice and simple cash-paid workflow regression tests."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import desk
import invoice_pdf
import customer_payments

class InvoicePdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original_db=desk.DB
        self.original_pdf=invoice_pdf.ROOT
        desk.DB=Path(self.tmp.name)/"jobs.sqlite3"
        invoice_pdf.ROOT=Path(self.tmp.name)/"invoices"
        desk.init()
        self.id,_=desk.create_ticket({"customer":"Jane Customer","phone":"555-0100",
          "location":"Manistee","service":"Starter replacement",
          "machine":"2018 Hyundai Santa Fe","problem":"No crank"},"manual:pdf-example")
        desk.update_ticket(self.id,{"labor_hours":"2","labor_rate":"125","parts_cost":"90"})
    def tearDown(self):
        desk.DB=self.original_db
        invoice_pdf.ROOT=self.original_pdf
        self.tmp.cleanup()
    def complete(self):
        desk.finish_job(self.id,{
          "work_performed":"Replaced defective starter and verified engine starts",
          "started_at":"","finished_at":"","actual_hours":"2",
          "actual_labor_cost":"100","actual_parts_cost":"90","actual_other_cost":"0",
          "actual_invoice":"400.00"})
    def test_pdf_automatically_created_once_on_completion(self):
        self.complete()
        filepath=invoice_pdf.path_for(self.id)
        self.assertTrue(filepath.is_file())
        content=filepath.read_bytes()
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content),900)
        self.assertEqual(filepath.stat().st_mode & 0o777,0o600)
        before=filepath.read_bytes()
        with desk.db() as db:
            ticket=db.execute("SELECT * FROM tickets WHERE id=?",(self.id,)).fetchone()
            completion=db.execute("SELECT * FROM job_completions WHERE ticket_id=?",(self.id,)).fetchone()
        self.assertEqual(invoice_pdf.create(ticket,completion),filepath)
        self.assertEqual(filepath.read_bytes(),before)
        self.assertEqual(desk.amounts(ticket)["parent"],Decimal("60.00"))
        self.assertEqual(desk.amounts(ticket)["operator"],Decimal("340.00"))
    def test_unpaid_until_marked_paid_and_pdf_not_rewritten(self):
        self.complete()
        before=invoice_pdf.path_for(self.id).read_bytes()
        with desk.db() as con:
            self.assertEqual(customer_payments.balance(con,self.id)["due"],Decimal("400.00"))
            self.assertNotEqual(con.execute("SELECT status FROM tickets").fetchone()[0],"paid")
        _,balance=desk.pay_invoice_in_full(self.id)
        self.assertEqual(balance["due"],Decimal("0.00"))
        with desk.db() as con:
            self.assertEqual(con.execute("SELECT status FROM tickets").fetchone()[0],"paid")
            payment=con.execute("SELECT method,applied FROM customer_payments").fetchone()
            self.assertEqual(tuple(payment),("cash","400.00"))
        self.assertEqual(invoice_pdf.path_for(self.id).read_bytes(),before)
        with self.assertRaises(ValueError):
            desk.pay_invoice_in_full(self.id)
    def test_pdf_link_visible_with_simple_status_controls(self):
        self.complete()
        page=desk.render_ticket(self.id)
        self.assertIn("invoice.pdf",page)
        self.assertIn("View / print PDF invoice",page)
        self.assertIn("Mark Paid",page)
        self.assertIn("Unpaid",page)
        desk.pay_invoice_in_full(self.id)
        page=desk.render_ticket(self.id)
        self.assertIn("Paid in full",page)
        self.assertNotIn("Mark Paid",page)
    def test_pdf_available_for_legacy_finalized_job(self):
        desk.finalize_ticket(self.id,"400")
        with desk.db() as con:
            ticket=con.execute("SELECT * FROM tickets WHERE id=?",(self.id,)).fetchone()
        filepath=invoice_pdf.create(ticket,None)
        self.assertTrue(filepath.read_bytes().startswith(b"%PDF-"))
    def test_no_pdf_for_unfinished_job(self):
        with desk.db() as con:
            ticket=con.execute("SELECT * FROM tickets").fetchone()
        with self.assertRaises(ValueError):
            invoice_pdf.create(ticket,None)
        self.assertFalse(invoice_pdf.path_for(self.id).exists())

if __name__=="__main__":unittest.main()
