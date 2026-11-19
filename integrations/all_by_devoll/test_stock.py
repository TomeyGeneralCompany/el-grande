from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest
from unittest.mock import patch

import desk


class StockWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = Path(self.temp.name) / "desk.sqlite"
        context = patch.object(desk, "DB", database)
        context.start()
        self.addCleanup(context.stop)
        desk.init()
        self.server = desk.ThreadingHTTPServer(("127.0.0.1", 0), desk.Handler)
        worker = Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def post(self, path, **data):
        request = Request(self.base + path, urlencode(data).encode(), headers={"Origin": self.base})
        with urlopen(request, timeout=5) as response:
            return response.read().decode()

    def get(self, path):
        with urlopen(self.base + path, timeout=5) as response:
            return response.read().decode()

    def order(self, quantity="3"):
        self.post("/inventory/save", sku="STARTER", description="Starter <assembly>", unit="EA")
        self.post("/inventory/vendors/save", code="ACME", name="Acme")
        self.post("/inventory/bins/save", code="MAIN", site="1000", warehouse="MAIN", location="MAINLOC")
        token = token_hex(16)
        self.post("/purchases/new", vendor="ACME", reference="89000001", request=token)
        self.post("/purchases/new", vendor="ACME", reference="89000001", request=token)
        # Remove an erroneous draft line and ensure replay cannot add it again.
        line_token = token_hex(16)
        self.post("/purchases/1/line", sku="STARTER", quantity="1", cost="10", request=line_token)
        self.post("/purchases/1/remove-line", line="1")
        self.post("/purchases/1/line", sku="STARTER", quantity="1", cost="10", request=line_token)
        self.post("/purchases/1/line", sku="STARTER", quantity=quantity, cost="12", request=token_hex(16))
        self.post("/purchases/1/open")

    def receive(self, quantity, token=None, reference="SLIP-1"):
        return self.post("/purchases/1/receive", line="2", bin="MAIN", quantity=quantity,
                         reference=reference, request=token or token_hex(16))

    def state(self):
        with closing(desk.db()) as con:
            return tuple(con.execute("""SELECT o.status,l.received,
                COALESCE((SELECT quantity FROM stock_balances WHERE sku='STARTER' AND bin='MAIN'),0),
                (SELECT count(*) FROM stock_receipts),(SELECT count(*) FROM stock_movements)
                FROM purchase_orders o JOIN purchase_lines l ON l.order_id=o.id
                WHERE l.id=2""").fetchone())

    def test_http_partial_receipts_replay_overage_and_reversal(self):
        self.order()
        self.assertIn('href="/purchases/1">PO-1</a>', self.get("/purchases"))
        self.assertIn("Starter &lt;assembly&gt;", self.get("/inventory"))
        token = token_hex(16)
        self.receive("1.25", token)
        self.receive("1.25", token)
        with self.assertRaises(HTTPError) as altered:
            self.receive("1.25", token, "different correction")
        self.assertEqual(altered.exception.code, 400)
        self.assertEqual(self.state(), ("open", 1_250_000, 1_250_000, 1, 1))
        with self.assertRaises(HTTPError) as over:
            self.receive("2")
        self.assertEqual(over.exception.code, 400)
        page = self.receive("1.75")
        self.assertIn("Receipt history", page)
        self.assertEqual(self.state(), ("received", 3_000_000, 3_000_000, 2, 2))
        self.post("/purchases/1/reverse", receipt="1", reason="Duplicate packing slip")
        self.post("/purchases/1/reverse", receipt="1", reason="Duplicate packing slip")
        self.assertEqual(self.state(), ("open", 1_750_000, 1_750_000, 2, 3))
        correction = token_hex(16)
        self.post("/inventory/adjust", sku="STARTER", bin="MAIN", quantity="-0.25",
                  reason="Used on a job", request=correction)
        self.post("/inventory/adjust", sku="STARTER", bin="MAIN", quantity="-0.25",
                  reason="Used on a job", request=correction)
        self.assertEqual(self.state(), ("open", 1_750_000, 1_500_000, 2, 4))
        export = self.get("/reports/purchases.csv")
        self.assertIn("1.25,12.00,15.00", export)
        self.assertIn("Duplicate packing slip", export)
        desk.init()
        self.assertEqual(self.state(), ("open", 1_750_000, 1_500_000, 2, 4))

    def test_receiving_serializes_competing_requests(self):
        self.order()
        def attempt():
            try:
                self.receive("2")
                return 200
            except HTTPError as err:
                return err.code
        with ThreadPoolExecutor(max_workers=2) as workers:
            requests = [workers.submit(attempt) for _ in range(2)]
            self.assertEqual(sorted(request.result() for request in requests), [200, 400])
        self.assertEqual(self.state(), ("open", 2_000_000, 2_000_000, 1, 1))

    def test_receipt_failure_rolls_back_all_writes(self):
        self.order()
        with closing(desk.db()) as con, con:
            con.execute("""CREATE TRIGGER fail_movement BEFORE INSERT ON stock_movements
                BEGIN SELECT RAISE(ABORT,'fixture movement failure'); END""")
        with self.assertRaises(HTTPError) as failure:
            self.receive("1")
        self.assertEqual(failure.exception.code, 502)
        self.assertEqual(self.state(), ("open", 0, 0, 0, 0))
