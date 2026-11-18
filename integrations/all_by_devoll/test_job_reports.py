"""Completed-job reporting and Google price-reference workflow tests."""
import io
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import desk
import job_reports

class CompletedJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        desk.DB=Path(self.temp.name)/"tickets.sqlite3"
        desk.init()
        self.ident,_=desk.create_ticket({"customer":"Customer A","phone":"555-0188",
             "machine":"2018 Santa Fe","service":"Starter replacement",
             "problem":"Car does not start"},"manual:completion-test")
        self.values={"work_performed":"Tested starter circuit, replaced starter, verified cranking",
          "started_at":"2026-11-18T10:00","finished_at":"2026-11-18T12:30",
          "actual_hours":"2.5","actual_labor_cost":"80.00",
          "actual_parts_cost":"110.00","actual_other_cost":"10.00",
          "actual_invoice":"350.00"}
    def tearDown(self):
        self.temp.cleanup()
    def test_complete_records_invoice_costs_and_15_percent_first(self):
        desk.finish_job(self.ident,self.values)
        with desk.db() as con:
            ticket=con.execute("SELECT * FROM tickets WHERE id=?",(self.ident,)).fetchone()
            record=con.execute("SELECT * FROM job_completions WHERE ticket_id=?",(self.ident,)).fetchone()
            report=con.execute("SELECT state FROM owner_reports WHERE ticket_id=?",(self.ident,)).fetchone()
        self.assertEqual(ticket["bill_total"],"350.00")
        self.assertEqual(record["actual_hours"],"2.50")
        self.assertEqual(record["actual_parts_cost"],"110.00")
        self.assertEqual(report["state"],"pending")
        numbers=desk.amounts(ticket)
        self.assertEqual(numbers["parent"],Decimal("52.50"))
        self.assertEqual(numbers["operator"],Decimal("297.50"))
        content=job_reports.report_text(ticket,record,numbers)
        self.assertIn("Tomey General 15% OFF THE TOP: $52.50",content)
        self.assertIn("Actual parts COST (operator expense): $110.00",content)
        self.assertIn("Operator remainder after recorded costs: $97.50",content)
        self.assertIn("Tested starter circuit",content)
    def test_invalid_completion_does_not_finalize(self):
        for wrong in [{**self.values,"actual_invoice":"NaN"},
                      {**self.values,"work_performed":""},
                      {**self.values,"actual_labor_cost":"-1"},
                      {**self.values,"started_at":"2026-11-18T12:30","finished_at":"2026-11-18T10:00"}]:
            with self.assertRaises(ValueError):desk.finish_job(self.ident,wrong)
        with desk.db() as con:
            self.assertFalse(con.execute("SELECT finalized_at FROM tickets WHERE id=?",(self.ident,)).fetchone()[0])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM owner_reports").fetchone()[0],0)
    def test_job_finalize_is_idempotently_locked(self):
        desk.finish_job(self.ident,self.values)
        with self.assertRaises(ValueError):desk.finish_job(self.ident,self.values)
        with desk.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM owner_reports").fetchone()[0],1)
    def test_owner_email_outbox_and_retry(self):
        desk.finish_job(self.ident,self.values)
        actual=[]
        def sender(to,subject,body):
            actual.append((to,subject,body))
        with patch.dict(os.environ,{"ABD_OWNER_REPORT_TO":"owner@example.com"}):
            self.assertEqual(job_reports.process_pending(desk.db,desk.amounts,sender),1)
            self.assertEqual(job_reports.process_pending(desk.db,desk.amounts,sender),0)
        self.assertEqual(len(actual),1)
        self.assertEqual(actual[0][0],"owner@example.com")
        with desk.db() as con:
            self.assertEqual(con.execute("SELECT state FROM owner_reports").fetchone()[0],"sent")
    def test_failed_send_is_retryable(self):
        desk.finish_job(self.ident,self.values)
        def broken(*args):raise OSError("offline")
        with patch.dict(os.environ,{"ABD_OWNER_REPORT_TO":"owner@example.com"}):
            self.assertEqual(job_reports.process_pending(desk.db,desk.amounts,broken),0)
            with desk.db() as con:
                self.assertEqual(con.execute("SELECT state FROM owner_reports").fetchone()[0],"failed")
            self.assertEqual(job_reports.process_pending(desk.db,desk.amounts,lambda *a:None),1)
    def test_google_search_is_prepopulated_not_a_price_prediction(self):
        url=job_reports.google_search_link("starter assembly","2018 Santa Fe")
        self.assertTrue(url.startswith("https://www.google.com/search?"))
        self.assertIn("starter+assembly",url)
        self.assertIn("2018+Santa+Fe",url)
        with self.assertRaises(ValueError):job_reports.google_search_link("x"*450)
    def test_operator_html_contains_actual_completion_form_and_search(self):
        with desk.db() as con:
            row=con.execute("SELECT * FROM tickets WHERE id=?",(self.ident,)).fetchone()
        page=desk.render([row])
        self.assertIn("name=\"work_performed\"",page)
        self.assertIn("name=\"actual_labor_cost\"",page)
        self.assertIn("name=\"actual_invoice\"",page)
        self.assertIn("www.google.com/search",page)

if __name__=="__main__":
    unittest.main()
