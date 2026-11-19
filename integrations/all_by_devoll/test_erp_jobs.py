"""Automated completed-job BlueSeer sync: durable, idempotent, non-GL."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import desk
import erp_jobs

ERP_CONFIG={
    "ABD_BLUESEER_CONNECTED":"yes",
    "ABD_BLUESEER_URL":"http://127.0.0.1:8088/bsapi",
    "ABD_BLUESEER_USER":"test_erp",
    "ABD_BLUESEER_PASSWORD":"test_only",
    "ABD_BLUESEER_SITE":"1000",
    "ABD_BLUESEER_LABOR_ITEM":"ABD-LABOR",
    "ABD_BLUESEER_PARTS_ITEM":"ABD-PARTS",
}
class BackgroundSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        desk.DB=Path(self.tmp.name)/"tickets.sqlite3"
        desk.init()
        self.ident,_=desk.create_ticket(
            {"customer":"Shop Test","phone":"555-0100","problem":"Brake replacement"},
            "manual:native-sync-test")
        desk.update_ticket(self.ident,{"labor_hours":"2","labor_rate":"85",
              "parts_charge":"140","parts_cost":"100"})
    def tearDown(self):
        self.tmp.cleanup()
    def complete(self,total="310"):
        desk.finish_job(self.ident,{"work_performed":"Replaced brake components",
            "started_at":"","finished_at":"","actual_hours":"2",
            "actual_labor_cost":"50","actual_parts_cost":"100",
            "actual_other_cost":"0","actual_invoice":total})
    def test_completed_job_posts_native_order_and_invoice_once(self):
        with patch.dict("os.environ",ERP_CONFIG):
            self.complete()
            with desk.db() as con:
                self.assertEqual(con.execute("SELECT state FROM erp_jobs").fetchone()[0],"queued")
            with patch.object(erp_jobs.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_jobs.customer_bridge,"upsert_customer",
                              return_value=("ABD000001","created")) as customer, \
                 patch.object(erp_jobs.blue_bridge,"submit_service_order",
                              return_value=("900000001","created")) as order, \
                 patch.object(erp_jobs.invoice_bridge,"reserve_native_shipment_number",
                              return_value="917") as reserve, \
                 patch.object(erp_jobs.invoice_bridge,"post_native_invoice",
                              return_value="917") as invoice:
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),1)
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),0)
                self.assertEqual(customer.call_count,1)
                self.assertEqual(order.call_count,1)
                self.assertEqual(reserve.call_count,1)
                self.assertEqual(invoice.call_count,1)
            with desk.db() as con:
                self.assertEqual(con.execute("SELECT state FROM erp_jobs").fetchone()[0],"posted")
                self.assertEqual(con.execute("SELECT state FROM blue_sync WHERE kind='invoice'").fetchone()[0],"posted")
                self.assertEqual(con.execute("SELECT status FROM tickets").fetchone()[0],"invoiced")
    def test_final_bill_overrides_estimate_and_preserves_off_top_split(self):
        with patch.dict("os.environ",ERP_CONFIG):
            self.complete(total="325")
            with desk.db() as con:
                row=con.execute("SELECT * FROM tickets").fetchone()
            amounts=desk.amounts(row)
            self.assertEqual(amounts["parent"],__import__("decimal").Decimal("48.75"))
            self.assertEqual(amounts["operator"],__import__("decimal").Decimal("276.25"))
            self.assertEqual(amounts["after_parts"],__import__("decimal").Decimal("176.25"))
            with patch.object(erp_jobs.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_jobs.customer_bridge,"upsert_customer",
                              return_value=("ABD000001","created")), \
                 patch.object(erp_jobs.blue_bridge,"submit_service_order",
                              return_value=("900000001","created")) as order, \
                 patch.object(erp_jobs.invoice_bridge,"reserve_native_shipment_number",
                              return_value="917"), \
                 patch.object(erp_jobs.invoice_bridge,"post_native_invoice") as invoice:
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),1)
                self.assertEqual(order.call_args.args[1]["basis"],
                                 __import__("decimal").Decimal("325.00"))
                self.assertEqual(invoice.call_args.args[1]["basis"],
                                 __import__("decimal").Decimal("325.00"))
    def test_ambiguous_invoice_failure_does_not_retry(self):
        with patch.dict("os.environ",ERP_CONFIG):
            self.complete()
            with patch.object(erp_jobs.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_jobs.customer_bridge,"upsert_customer",
                              return_value=("ABD000001","created")), \
                 patch.object(erp_jobs.blue_bridge,"submit_service_order",
                              return_value=("900000001","created")), \
                 patch.object(erp_jobs.invoice_bridge,"reserve_native_shipment_number",
                              return_value="917"), \
                 patch.object(erp_jobs.invoice_bridge,"post_native_invoice",
                              side_effect=ConnectionError("response lost")) as post:
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),0)
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),0)
                self.assertEqual(post.call_count,1)
            with desk.db() as con:
                self.assertEqual(con.execute("SELECT state FROM erp_jobs").fetchone()[0],"needs_review")
                self.assertEqual(con.execute("SELECT state FROM blue_sync WHERE kind='invoice'").fetchone()[0],"unknown")
    def test_disconnected_erp_does_not_lose_job(self):
        with patch.dict("os.environ",ERP_CONFIG):
            with patch.dict("os.environ",{"ABD_BLUESEER_CONNECTED":"no"}):
                self.complete()
        with desk.db() as con:
            self.assertEqual(con.execute("SELECT state FROM erp_jobs").fetchone()[0],"queued")
            self.assertEqual(con.execute("SELECT status FROM tickets").fetchone()[0],"completed")

if __name__=="__main__":unittest.main()
