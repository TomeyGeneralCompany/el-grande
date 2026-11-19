"""Exercise actual localhost dashboard routes for bank register and bank linking."""
import threading
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from unittest.mock import patch
import desk
import bank_connect

class BankRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db_old=desk.DB
        desk.DB=Path(self.tmp.name)/"jobs.sqlite3"
        desk.init()
        self.server=ThreadingHTTPServer(("127.0.0.1",0),desk.Handler)
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        desk.DB=self.db_old
        self.tmp.cleanup()
    def url(self,path):return "http://127.0.0.1:"+str(self.port)+path
    def get(self,path):
        with urlopen(self.url(path),timeout=5) as r:return r.status,r.read().decode()
    def post(self,path,data):
        request=Request(self.url(path),urlencode(data).encode(),method="POST",headers={
            "Content-Type":"application/x-www-form-urlencoded",
            "Origin":"http://127.0.0.1:"+str(self.port)})
        with urlopen(request,timeout=5) as r:return r.status,r.read().decode()
    def test_manual_bank_workflow_without_provider(self):
        status,page=self.get("/bank")
        self.assertEqual(status,200)
        self.assertIn("Money in &amp; out",page)
        self.assertIn("Cash",page)
        with desk.db() as con:
            ids=[x["id"] for x in con.execute("SELECT id FROM money_accounts ORDER BY id")]
        self.post("/bank/entry",{"account_id":str(ids[0]),"amount":"150",
             "direction":"in","memo":"Cash receipt"})
        self.post("/bank/transfer",{"from_account":str(ids[0]),
             "to_account":str(ids[1]),"amount":"75","memo":"Cash deposit"})
        status,page=self.get("/bank")
        self.assertIn("$75.00",page)
        with desk.db() as con:
            b=con.execute("SELECT name,opening_cents+(SELECT COALESCE(SUM(amount_cents),0) FROM money_entries WHERE account_id=money_accounts.id) AS balance FROM money_accounts ORDER BY id").fetchall()
        self.assertEqual([x["balance"] for x in b],[7500,7500])
    def test_safe_count_submitted_through_dashboard_persists(self):
        with desk.db() as con:
            cash=con.execute("SELECT id FROM money_accounts WHERE kind='cash'").fetchone()["id"]
        code,content=self.post("/bank/cash-count",{
            "account_id":str(cash),"counted_amount":"42.75",
            "notes":"Cash counted and locked in safe"})
        self.assertEqual(code,200)
        self.assertIn("Past cash counts",content)
        self.assertIn("42.75",content)
        with desk.db() as con:
            row=con.execute("SELECT * FROM cash_counts ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row["counted_cents"],4275)
            self.assertEqual(row["expected_cents"],0)
            self.assertEqual(row["variance_cents"],4275)
            self.assertEqual(con.execute("SELECT count(*) FROM money_entries").fetchone()[0],0)
    def test_bank_link_url_renders_provider_widget_not_local_credentials(self):
        with patch.object(bank_connect,"link_token",return_value="link-test-token"):
            request=Request(self.url("/bank/connect"),method="GET")
            with urlopen(request,timeout=5) as response:
                data=response.read().decode()
                policy=response.headers["Content-Security-Policy"]
        self.assertIn("Plaid.create",data)
        self.assertIn("link-test-token",data)
        self.assertIn("cdn.plaid.com",policy)
        self.assertIn("nonce-",policy)
    def test_bank_link_callback_through_local_server(self):
        with patch.object(bank_connect,"exchange",return_value=[1]) as bridge:
            status,_=self.post("/bank/exchange",{"public_token":"public-token"})
        self.assertEqual(status,200)
        self.assertEqual(bridge.call_args.args[0],"public-token")
    def test_settings_link_is_present(self):
        status,screen=self.get("/settings")
        self.assertEqual(status,200)
        self.assertIn("Connect to your bank",screen)
        self.assertIn('action="/bank/provider-settings"',screen)
        self.assertIn('href="/bank"',screen)

if __name__=="__main__":unittest.main()
