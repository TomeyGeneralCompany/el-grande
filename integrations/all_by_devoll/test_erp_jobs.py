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
    def test_complete_job_syncs_customer_and_native_order_once(self):
        with patch.dict("os.environ",ERP_CONFIG):
            self.complete()
            with desk.db() as con:
                row=con.execute("SELECT state FROM erp_jobs WHERE ticket_id=?",(self.ident,)).fetchone()
                self.assertEqual(row["state"],"queued")
            with patch.object(erp_jobs.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_jobs.customer_bridge,"upsert_customer",
                              return_value=("ABD000001","created")) as create, \
                 patch.object(erp_jobs.blue_bridge,"submit_service_order",
                              return_value=("900000001","created")) as order:
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),1)
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),0)
                self.assertEqual(create.call_count,1)
                self.assertEqual(order.call_count,1)
            with desk.db() as con:
                self.assertEqual(con.execute("SELECT state FROM erp_jobs").fetchone()[0],"synced")
                self.assertEqual(con.execute("SELECT record_number FROM blue_sync WHERE kind='service_order'").fetchone()[0],"900000001")
                self.assertEqual(con.execute("SELECT blue_customer FROM tickets").fetchone()[0],"ABD000001")
    def test_unreconciled_final_bill_does_not_create_native_order(self):
        with patch.dict("os.environ",ERP_CONFIG):
            self.complete(total="325")
            with patch.object(erp_jobs.blue_bridge,"BlueSeerClient") as client:
                self.assertEqual(erp_jobs.process_once(desk.db,desk.amounts),0)
                client.assert_not_called()
            with desk.db() as con:
                self.assertEqual(con.execute("SELECT state FROM erp_jobs").fetchone()[0],"needs_review")
                self.assertIsNotNone(con.execute("SELECT * FROM job_completions").fetchone())
    def test_no_erp_connection_does_not_block_local_completion(self):
        with patch.dict("os.environ",ERP_CONFIG):
            with patch.dict("os.environ",{"ABD_BLUESEER_CONNECTED":"no"}):
                self.complete()
        with desk.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM erp_jobs").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT status FROM tickets").fetchone()[0],"completed")

if __name__=="__main__":unittest.main()
