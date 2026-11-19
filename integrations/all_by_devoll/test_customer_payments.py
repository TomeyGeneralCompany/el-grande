"""Real local payment ledger tests: cash default, partials, change, voids, gross split."""
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import customer_payments
import desk
import shop_ui

class PaymentLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=desk.DB
        desk.DB=Path(self.tmp.name)/"tickets.sqlite3"
        desk.init()
        self.ident,_=desk.create_ticket(
           {"customer":"Cash Customer","phone":"555-0100","problem":"Car repair"},"manual:cash-test")
        desk.update_ticket(self.ident,{"labor_hours":"2","labor_rate":"85","parts_cost":"45"})
    def tearDown(self):
        desk.DB=self.old
        self.tmp.cleanup()
    def complete(self,total="100",payment=""):
        data={"work_performed":"Fixed vehicle","started_at":"","finished_at":"",
              "actual_hours":"2","actual_labor_cost":"25","actual_parts_cost":"45",
              "actual_other_cost":"0","actual_invoice":total}
        if payment:data.update(amount_received=payment,method="cash",paid_on=date.today().isoformat())
        desk.finish_job(self.ident,data)
    def check(self):
        with desk.db() as con:
            return customer_payments.balance(con,self.ident)
    def test_cash_default_and_partial_receipts(self):
        self.complete("200")
        payment,bal=desk.record_customer_payment(self.ident,{
            "amount_received":"50","method":"cash","paid_on":date.today().isoformat()})
        self.assertEqual(bal["due"],Decimal("150"))
        self.assertEqual(payment,1)
        _,bal=desk.record_customer_payment(self.ident,{"amount_received":"150","method":"cash"})
        self.assertEqual(bal["due"],Decimal("0"))
        with desk.db() as con:
            row=con.execute("SELECT status FROM tickets WHERE id=?",(self.ident,)).fetchone()
        self.assertEqual(row["status"],"paid")
    def test_cash_over_tender_returns_change_and_not_revenue(self):
        self.complete("175")
        _,bal=desk.record_customer_payment(self.ident,{"amount_received":"200","method":"cash"})
        self.assertEqual(bal["received"],Decimal("175"))
        self.assertEqual(bal["due"],Decimal("0"))
        with desk.db() as con:
            p=customer_payments.payments(con,self.ident)[0]
            job=con.execute("SELECT * FROM tickets WHERE id=?",(self.ident,)).fetchone()
        self.assertEqual(p["change_given"],"25.00")
        self.assertEqual(desk.amounts(job)["parent"],Decimal("26.25"))
        self.assertEqual(desk.amounts(job)["operator"],Decimal("148.75"))
    def test_cash_paid_at_completion_is_atomic(self):
        self.complete("100","120")
        self.assertEqual(self.check()["due"],Decimal("0"))
        with desk.db() as con:
            p=customer_payments.payments(con,self.ident)[0]
        self.assertEqual(p["change_given"],"20.00")
    def test_invalid_payment_does_not_finalize_job(self):
        with self.assertRaises(ValueError):
            self.complete("100","not-money")
        with desk.db() as con:
            job=con.execute("SELECT finalized_at FROM tickets WHERE id=?",(self.ident,)).fetchone()
        self.assertIsNone(job["finalized_at"])
    def test_no_overpay_on_non_cash_and_duplicate_full_payment(self):
        self.complete("100")
        with self.assertRaises(ValueError):
            desk.record_customer_payment(self.ident,{"method":"check","amount_received":"120"})
        desk.record_customer_payment(self.ident,{"method":"check","amount_received":"100"})
        with self.assertRaises(ValueError):
            desk.record_customer_payment(self.ident,{"method":"cash","amount_received":"100"})
    def test_void_reverses_balance_and_retains_audit_row(self):
        self.complete("100")
        pay,_=desk.record_customer_payment(self.ident,{"amount_received":"100"})
        with self.assertRaises(ValueError):
            desk.void_customer_payment(self.ident,{"payment_id":pay,"reason":"bad"})
        state=desk.void_customer_payment(self.ident,{"payment_id":pay,"reason":"Recorded wrong customer payment"})
        self.assertEqual(state["due"],Decimal("100"))
        with desk.db() as con:
            p=customer_payments.payments(con,self.ident)[0]
            status=con.execute("SELECT status FROM tickets WHERE id=?",(self.ident,)).fetchone()
        self.assertIsNotNone(p["voided_at"])
        self.assertEqual(status["status"],"completed")
        with self.assertRaises(ValueError):
            desk.void_customer_payment(self.ident,{"payment_id":pay,"reason":"Already voided"})
    def test_payment_date_and_precision_rejected(self):
        self.complete("100")
        for amount in ("-2","0","5.001","NaN","Inf"):
            with self.assertRaises(ValueError):
                desk.record_customer_payment(self.ident,{"amount_received":amount})
        with self.assertRaises(ValueError):
            desk.record_customer_payment(self.ident,{"amount_received":"25","paid_on":"2049-02-15"})
    def test_cash_form_and_payment_history_render(self):
        self.complete("100")
        desk.record_customer_payment(self.ident,{"amount_received":"40","method":"cash"})
        with desk.db() as con:
            rows=con.execute("SELECT * FROM tickets").fetchall()
        html=shop_ui.render(rows,[],desk.db,desk.amounts)
        self.assertIn("Record payment",html)
        self.assertIn("Still owed",html)
        self.assertIn("60.00",html)
        self.assertIn("Correct payment",html)
        self.assertNotIn("Mark paid",html)
        self.assertNotIn("Complete the accounting setup before creating financial records",html)
    def test_only_completed_jobs_accept_payment(self):
        with self.assertRaises(ValueError):
            desk.record_customer_payment(self.ident,{"amount_received":"20"})

if __name__=="__main__":unittest.main()
