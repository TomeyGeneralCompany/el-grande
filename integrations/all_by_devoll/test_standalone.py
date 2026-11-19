"""Upgrade and HTTP acceptance tests for the Java-free desk."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import hashlib
import sqlite3
import unittest
from unittest.mock import patch

import desk
import invoice_pdf
import stock_reconcile


FIXTURE = """
CREATE TABLE item_mstr(it_item,it_desc,it_uom);
CREATE TABLE vd_mstr(vd_addr,vd_name);
CREATE TABLE loc_mstr(loc_loc,loc_site,loc_wh);
CREATE TABLE in_mstr(in_item,in_site,in_wh,in_loc,in_qoh);
CREATE TABLE po_mstr(po_nbr,po_vend,po_ord_date,po_status);
CREATE TABLE pod_mstr(pod_nbr,pod_line,pod_item,pod_ord_qty,pod_rcvd_qty,pod_netprice,pod_status);
CREATE TABLE plan_mstr(plan_nbr,plan_item,plan_qty_req,plan_qty_comp,plan_qty_sched,
  plan_date_due,plan_date_sched,plan_status,plan_rmks,plan_type);
CREATE TABLE gl_tran(glt_id,glt_amt);
CREATE TABLE ar_mstr(ar_id,ar_amt);
CREATE TABLE recv_det(rvd_id,rvd_qty);
INSERT INTO item_mstr VALUES('STARTER','Starter','EA');
INSERT INTO vd_mstr VALUES('ACME','Acme');
INSERT INTO loc_mstr VALUES('MAINLOC','1000','MAIN');
INSERT INTO in_mstr VALUES('STARTER','1000','MAIN','MAINLOC',3);
INSERT INTO po_mstr VALUES('89000001','ACME','2026-11-18','open');
INSERT INTO pod_mstr VALUES('89000001',1,'STARTER',5,3,12,'open');
INSERT INTO plan_mstr VALUES(89000003,'STARTER',3,0,2,'2026-12-01','2026-12-01',0,'Fixture','WO');
INSERT INTO gl_tran VALUES(1,120);
INSERT INTO ar_mstr VALUES(1,120);
INSERT INTO recv_det VALUES('89000002',3);
"""


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.source = base / "native.sqlite"
        for obj,name,value in ((desk,"DB",base / "desk.sqlite"),(invoice_pdf,"ROOT",base / "invoices")):
            context = patch.object(obj,name,value)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(desk.legacy_import, "DEFAULT_PATH", self.source)
        context.start()
        self.addCleanup(context.stop)
        desk.init()

    def open_fixture(self):
        with closing(sqlite3.connect(self.source)) as con:
            con.executescript(FIXTURE)
        return hashlib.sha256(self.source.read_bytes()).digest()

    def test_upgrade_imports_once_and_preserves_finance_without_replay(self):
        digest = self.open_fixture()
        ticket,_ = desk.create_ticket({"customer":"Existing customer"},"old")
        desk.finalize_ticket(ticket,"120.00")
        desk.record_customer_payment(ticket,{"amount_received":"20.00"})
        with closing(desk.db()) as con, con:
            con.execute("CREATE TABLE erp_jobs(ticket_id,state)")
            con.execute("INSERT INTO erp_jobs VALUES(?,'queued')",(ticket,))
        desk.init()
        desk.init()
        with closing(desk.db()) as con, closing(stock_reconcile.read_copy(self.source)) as original:
            self.assertFalse(any(stock_reconcile.compare(original,con).values()))
            order = con.execute("SELECT reference,status FROM purchase_orders").fetchone()
            self.assertEqual(tuple(order),("89000001","open"))
            self.assertEqual(con.execute("SELECT count(*) FROM stock_movements").fetchone()[0],1)
            self.assertEqual(tuple(con.execute("SELECT reference,scheduled_quantity FROM work_orders").fetchone()),("BlueSeer-89000003",2000000))
            for entity in ("gl_tran","ar_mstr","erp_jobs","recv_det"):
                self.assertEqual(con.execute("SELECT count(*) FROM legacy_records WHERE entity=?",(entity,)).fetchone()[0],1)
            self.assertEqual(con.execute("SELECT count(*) FROM customer_payments").fetchone()[0],1)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(),digest)

    def test_conflicting_opening_balance_rolls_back_import(self):
        self.open_fixture()
        desk.init()
        with closing(desk.db()) as con, con:
            con.execute("DELETE FROM legacy_import_complete")
            con.execute("DELETE FROM legacy_records")
            con.execute("UPDATE stock_balances SET quantity=4000000")
        with self.assertRaisesRegex(ValueError,"Stock conflict"):
            desk.init()
        with closing(desk.db()) as con:
            self.assertEqual(con.execute("SELECT quantity FROM stock_balances").fetchone()[0],4000000)
            self.assertEqual(con.execute("SELECT count(*) FROM legacy_records").fetchone()[0],0)

    def test_http_work_order_appointment_pdf_and_mark_paid_without_java(self):
        self.open_fixture()
        desk.init()
        with desk.ThreadingHTTPServer(("127.0.0.1",0),desk.Handler) as server:
            worker = Thread(target=server.serve_forever,daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def send(path,data=None):
                request = Request(base+path, None if data is None else urlencode(data).encode(),
                                  headers={"Origin":base})
                with urlopen(request,timeout=5) as response:
                    return response.read()
            try:
                self.assertEqual(send("/ready"),b"ready-local")
                send("/ticket/new",{"customer":"Local test","problem":"Starter"})
                send("/appointments/save",{"ticket_id":"1","date":"2026-12-01","time":"09:30"})
                plan = {"reference":"WO-1","ticket":"1","sku":"STARTER","quantity":"2","status":"open",
                        "scheduled_on":"2026-12-01"}
                self.assertIn(b"WO-1",send("/work-orders/save",plan))
                self.assertIn(b"complete",send("/work-orders/save",dict(plan,completed="2",status="complete")))
                send("/ticket/1/complete",{"work_performed":"Installed starter","actual_invoice":"400.00"})
                self.assertTrue(send("/ticket/1/invoice.pdf").startswith(b"%PDF"))
                self.assertIn(b"Paid in full",send("/ticket/1/pay-in-full",{}))
                self.assertIn(b"gl_tran",send("/reports/legacy.csv"))
                with closing(desk.db()) as con:
                    self.assertEqual(con.execute("SELECT status FROM tickets WHERE id=1").fetchone()[0],"paid")
                    self.assertFalse(con.execute("SELECT 1 FROM sqlite_master WHERE name='erp_jobs'").fetchone())
            finally:
                server.shutdown()
                worker.join(timeout=5)
