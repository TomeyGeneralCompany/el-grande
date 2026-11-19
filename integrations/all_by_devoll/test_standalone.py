"""Restart and HTTP acceptance tests for the standalone desk."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest
from unittest.mock import patch

import desk
import invoice_pdf


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        for obj,name,value in ((desk,"DB",base / "desk.sqlite"),(invoice_pdf,"ROOT",base / "invoices")):
            context = patch.object(obj,name,value)
            context.start()
            self.addCleanup(context.stop)
        desk.init()

    def test_restart_preserves_existing_ticket_and_payment(self):
        ticket, _ = desk.create_ticket({"customer": "Existing customer"}, "old")
        desk.finalize_ticket(ticket, "120.00")
        desk.record_customer_payment(ticket, {"amount_received": "20.00"})

        desk.init()

        with closing(desk.db()) as con:
            row = con.execute("SELECT customer, bill_total FROM tickets WHERE id=?", (ticket,)).fetchone()
            self.assertEqual(tuple(row), ("Existing customer", "120.00"))
            self.assertEqual(con.execute("SELECT count(*) FROM customer_payments").fetchone()[0], 1)

    def test_http_work_order_appointment_pdf_and_mark_paid(self):
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
                send("/inventory/save", {"sku": "STARTER", "description": "Starter", "unit": "EA"})
                plan = {"reference":"WO-1","ticket":"1","sku":"STARTER","quantity":"2","status":"open",
                        "scheduled_on":"2026-12-01"}
                self.assertIn(b"WO-1",send("/work-orders/save",plan))
                self.assertIn(b"complete",send("/work-orders/save",dict(plan,completed="2",status="complete")))
                send("/ticket/1/complete",{"work_performed":"Installed starter","actual_invoice":"400.00"})
                self.assertTrue(send("/ticket/1/invoice.pdf").startswith(b"%PDF"))
                self.assertIn(b"Paid in full",send("/ticket/1/pay-in-full",{}))
                with closing(desk.db()) as con:
                    self.assertEqual(con.execute("SELECT status FROM tickets WHERE id=1").fetchone()[0],"paid")
            finally:
                server.shutdown()
                worker.join(timeout=5)
