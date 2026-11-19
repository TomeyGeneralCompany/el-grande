"""Local-to-native receipt synchronization and idempotency regression tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
import desk
import erp_receipts

CONFIG={
    "ABD_BLUESEER_CONNECTED":"yes",
    "ABD_BLUESEER_URL":"http://127.0.0.1:8088/bsapi",
    "ABD_BLUESEER_USER":"admin",
    "ABD_BLUESEER_PASSWORD":"test-credential",
    "ABD_BLUESEER_SITE":"1000",
}
class ReceiptSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=desk.DB
        desk.DB=Path(self.tmp.name)/"tickets.sqlite3"
        desk.init()
        self.ticket,_=desk.create_ticket({"customer":"Native payment customer","problem":"Starter replacement"},
                                        "manual:receipt-test")
        desk.finish_job(self.ticket,{"work_performed":"Replaced starter","actual_invoice":"400",
                            "actual_hours":"2","actual_labor_cost":"80","actual_parts_cost":"110"})
        with desk.db() as con:
            con.execute("""UPDATE tickets SET blue_customer='ABD000001' WHERE id=?""",(self.ticket,))
            con.execute("""INSERT INTO blue_sync(ticket_id,kind,record_number,state,updated_at)
               VALUES (?,'invoice','901','posted','2026-11-19')""",(self.ticket,))
    def tearDown(self):
        desk.DB=self.old
        self.tmp.cleanup()
    def add(self,amt):
        return desk.record_customer_payment(self.ticket,{"amount_received":str(amt)})[0]
    def states(self):
        with desk.db() as con:
            return {(x["payment_id"],x["kind"]):x["state"] for x in
                    con.execute("SELECT * FROM erp_receipts")}
    def test_partial_payments_post_once_and_reconcile(self):
        p=self.add("125")
        self.assertEqual(self.states()[(p,"payment")],"queued")
        with patch.dict(os.environ,CONFIG):
            with patch.object(erp_receipts.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_receipts,"post",return_value=erp_receipts.number(p,"payment")) as post:
                self.assertEqual(erp_receipts.process_once(desk.db),1)
                self.assertEqual(erp_receipts.process_once(desk.db),0)
                self.assertEqual(post.call_count,1)
        self.assertEqual(self.states()[(p,"payment")],"posted")
        with desk.db() as con:
            self.assertEqual(con.execute("SELECT status FROM tickets").fetchone()[0],"completed")
    def test_cancel_unsent_payment(self):
        pid=self.add("90")
        desk.void_customer_payment(self.ticket,{"payment_id":pid,"reason":"Wrong cash receipt"})
        self.assertEqual(self.states()[(pid,"payment")],"cancelled")
        with patch.dict(os.environ,CONFIG), patch.object(erp_receipts.blue_bridge,"BlueSeerClient") as client:
            self.assertEqual(erp_receipts.process_once(desk.db),0)
            client.assert_not_called()
    def test_posted_payment_reversed_once_on_void(self):
        pid=self.add("100")
        with desk.db() as con:
            con.execute("""UPDATE erp_receipts SET state='posted'
              WHERE payment_id=? AND kind='payment'""",(pid,))
        desk.void_customer_payment(self.ticket,{"payment_id":pid,"reason":"Customer was incorrectly charged"})
        self.assertEqual(self.states()[(pid,"reversal")],"queued")
        with patch.dict(os.environ,CONFIG):
            with patch.object(erp_receipts.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_receipts,"post",return_value=erp_receipts.number(pid,"reversal")) as post:
                self.assertEqual(erp_receipts.process_once(desk.db),1)
                self.assertEqual(erp_receipts.process_once(desk.db),0)
                self.assertEqual(post.call_count,1)
                self.assertEqual(post.call_args.args[-1],"reversal")
        self.assertEqual(self.states()[(pid,"reversal")],"posted")
    def test_unknown_outcome_never_replays_payment(self):
        pid=self.add("100")
        with patch.dict(os.environ,CONFIG):
            with patch.object(erp_receipts.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_receipts,"post",side_effect=ConnectionError("response lost")) as post:
                self.assertEqual(erp_receipts.process_once(desk.db),0)
                self.assertEqual(post.call_count,1)
                self.assertEqual(self.states()[(pid,"payment")],"needs_review")
            with patch.object(erp_receipts.blue_bridge,"BlueSeerClient",return_value=object()), \
                 patch.object(erp_receipts,"check_record",return_value=True) as confirm, \
                 patch.object(erp_receipts,"post") as post:
                self.assertEqual(erp_receipts.process_once(desk.db),1)
                post.assert_not_called()
                self.assertEqual(self.states()[(pid,"payment")],"posted")
    def test_payment_waits_until_invoice_posted(self):
        pid=self.add("50")
        with desk.db() as con:
            con.execute("""UPDATE blue_sync SET state='reserved' WHERE kind='invoice'""")
        with patch.dict(os.environ,CONFIG),patch.object(erp_receipts.blue_bridge,"BlueSeerClient") as c:
            self.assertEqual(erp_receipts.process_once(desk.db),0)
            c.assert_not_called()
        self.assertEqual(self.states()[(pid,"payment")],"queued")
    def test_legacy_payment_backfills_without_duplicates(self):
        pid=self.add("40")
        with desk.db() as con:
            con.execute("DELETE FROM erp_receipts")
            erp_receipts.init_queue(con)
            erp_receipts.init_queue(con)
            count=con.execute("SELECT count(*) FROM erp_receipts").fetchone()[0]
        self.assertEqual(count,1)
    def test_native_payment_document_number_is_deterministic(self):
        self.assertEqual(erp_receipts.number(5,"payment"),"700000005")
        self.assertEqual(erp_receipts.number(5,"reversal"),"600000005")

if __name__=="__main__":
    unittest.main()
