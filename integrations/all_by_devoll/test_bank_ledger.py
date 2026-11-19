"""End-to-end cash/bank register and bank-provider contract tests (offline)."""
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import bank_ledger
import bank_connect
import bank_ui
import desk

class MoneyLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_db=desk.DB
        desk.DB=Path(self.temp.name)/"jobs.sqlite3"
        desk.init()
        self.job,_=desk.create_ticket({"customer":"Main Street customer",
             "problem":"Starter job"},"manual:bank-test")
        desk.finalize_ticket(self.job,"400.00")
    def tearDown(self):
        desk.DB=self.old_db
        self.temp.cleanup()
    def test_cash_receipt_and_correction_are_reflected(self):
        pay,_=desk.record_customer_payment(self.job,{"amount_received":"125","method":"cash"})
        with desk.db() as con:
            a=bank_ledger.accounts(con)
            self.assertEqual([(x["kind"],x["balance_cents"]) for x in a],
                             [("cash",12500),("bank",0)])
            bank_ledger.init(con)
            self.assertEqual(bank_ledger.accounts(con)[0]["balance_cents"],12500)
        desk.void_customer_payment(self.job,{"payment_id":pay,"reason":"Entry posted in error"})
        with desk.db() as con:
            self.assertEqual(bank_ledger.accounts(con)[0]["balance_cents"],0)
            e=bank_ledger.recent_entries(con)
            self.assertEqual(sorted(x["amount_cents"] for x in e),[-12500,12500])
    def test_transfer_moves_cash_to_bank_without_creating_income(self):
        desk.record_customer_payment(self.job,{"amount_received":"300","method":"cash"})
        with desk.db() as con:
            a=bank_ledger.accounts(con)
            bank_ledger.transfer(con,{"from_account":a[0]["id"],"to_account":a[1]["id"],
                                  "amount":"200","memo":"Cash deposited"})
            updated=bank_ledger.accounts(con)
            self.assertEqual([r["balance_cents"] for r in updated],[10000,20000])
            self.assertEqual(sum(x["balance_cents"] for x in updated),30000)
    def test_manual_expense_and_income(self):
        with desk.db() as con:
            a=bank_ledger.accounts(con)[1]
            bank_ledger.record(con,{"account_id":a["id"],"direction":"in","amount":"250","memo":"Deposit"})
            bank_ledger.record(con,{"account_id":a["id"],"direction":"out","amount":"80","memo":"Parts"})
            self.assertEqual(bank_ledger.accounts(con)[1]["balance_cents"],17000)
            with self.assertRaises(ValueError):
                bank_ledger.record(con,{"account_id":a["id"],"direction":"out","amount":"3.001"})
    def test_import_bank_feed_and_match_existing_entry(self):
        with desk.db() as con:
            bank=bank_ledger.accounts(con)[1]
            bank_ledger.record(con,{"account_id":bank["id"],"direction":"in","amount":"200"})
            ledger=bank_ledger.recent_entries(con)[0]
            bank_ledger.imported(con,bank["id"],"plaid",{
                  "transaction_id":"unique-123","date":date.today().isoformat(),
                  "name":"Deposit","amount":-200.0,"pending":False})
            feed=bank_ledger.feed(con,bank["id"])[0]
            self.assertEqual(feed["amount_cents"],20000)
            bank_ledger.feed_match(con,feed["id"],ledger["id"])
            self.assertEqual(bank_ledger.accounts(con)[1]["balance_cents"],20000)
            with self.assertRaises(ValueError):
                bank_ledger.feed_record(con,feed["id"])
    def test_feed_add_once_and_pending_requires_bank_post(self):
        with desk.db() as con:
            bank=bank_ledger.accounts(con)[1]
            transaction={"transaction_id":"bank-789","date":date.today().isoformat(),
                         "name":"Fuel station","amount":47.5,"pending":True}
            bank_ledger.imported(con,bank["id"],"plaid",transaction)
            fid=bank_ledger.feed(con,bank["id"])[0]["id"]
            with self.assertRaises(ValueError):
                bank_ledger.feed_record(con,fid)
            transaction["pending"]=False
            bank_ledger.imported(con,bank["id"],"plaid",transaction)
            bank_ledger.feed_record(con,fid)
            self.assertEqual(bank_ledger.accounts(con)[1]["balance_cents"],-4750)
            with self.assertRaises(ValueError):
                bank_ledger.feed_record(con,fid)
    def test_local_bank_ui_works_offline(self):
        with desk.db() as con:
            html=bank_ui.page(con,False)
        for phrase in ("Money in &amp; out","Record transfer","Record money","Add register account"):
            if phrase=="Record transfer":continue
            self.assertIn(phrase,html)
        self.assertIn("Transfer / cash deposit",html)
        self.assertNotIn("Plaid.create",html)
    def test_safe_count_exact_match_and_duplicate_snapshots(self):
        desk.record_customer_payment(self.job,{"amount_received":"300","method":"cash"})
        with desk.db() as con:
            cash=bank_ledger.cash_accounts(con)[0]
            first,diff=bank_ledger.record_cash_count(con,{"account_id":str(cash["id"]),
                  "counted_amount":"300.00","notes":"End of shift count"})
            self.assertEqual(diff,0)
            second,diff=bank_ledger.record_cash_count(con,{"account_id":str(cash["id"]),
                  "counted_amount":"290.00","notes":"Recount"})
            self.assertEqual(diff,-1000)
            self.assertNotEqual(first,second)
            self.assertEqual(bank_ledger.accounts(con)[0]["balance_cents"],30000)
            hist=bank_ledger.recent_cash_counts(con)
            self.assertEqual(hist[0]["expected_cents"],30000)
            self.assertEqual(hist[0]["counted_cents"],29000)
            self.assertEqual(hist[0]["variance_cents"],-1000)
            self.assertEqual(hist[1]["variance_cents"],0)
    def test_safe_count_surplus_ignores_non_cash_accounts(self):
        desk.record_customer_payment(self.job,{"amount_received":"200","method":"cash"})
        with desk.db() as con:
            cash,bank=bank_ledger.accounts(con)[:2]
            bank_ledger.transfer(con,{"from_account":str(cash["id"]),"to_account":str(bank["id"]),
                  "amount":"75"})
            ident,diff=bank_ledger.record_cash_count(con,{"account_id":cash["id"],"counted_amount":"135"})
            self.assertEqual(diff,1000)
            self.assertEqual(bank_ledger.accounts(con)[0]["balance_cents"],12500)
            self.assertEqual(bank_ledger.accounts(con)[1]["balance_cents"],7500)
            with self.assertRaises(ValueError):
                bank_ledger.record_cash_count(con,{"account_id":bank["id"],"counted_amount":"75"})
    def test_safe_count_rejects_bad_amounts_and_is_not_a_ledger_adjustment(self):
        with desk.db() as con:
            cash=bank_ledger.cash_accounts(con)[0]
            for invalid in ("NaN","-1","10.001","abc",""):
                with self.assertRaises(ValueError):
                    bank_ledger.record_cash_count(con,{"account_id":cash["id"],
                         "counted_amount":invalid})
            self.assertEqual(len(bank_ledger.recent_cash_counts(con)),0)
            bank_ledger.record_cash_count(con,{"account_id":cash["id"],"counted_amount":"0"})
            self.assertEqual(con.execute("SELECT count(*) FROM money_entries").fetchone()[0],0)
            screen=bank_ui.page(con,False)
            self.assertIn("Count cash in the safe",screen)
            self.assertIn('action="/bank/cash-count"',screen)
            self.assertIn("Safe-count history",screen)
    def test_customer_gross_split_not_modified(self):
        with desk.db() as con:
            job=con.execute("SELECT * FROM tickets").fetchone()
        self.assertEqual(desk.amounts(job)["parent"],__import__("decimal").Decimal("60.00"))

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original_settings=bank_connect.SETTINGS
        self.original_data=bank_connect.DATA
        bank_connect.SETTINGS=Path(self.temp.name)/"plaid.json"
        bank_connect.DATA=Path(self.temp.name)/"accounts.json"
    def tearDown(self):
        bank_connect.SETTINGS=self.original_settings
        bank_connect.DATA=self.original_data
        self.temp.cleanup()
    def test_provider_credentials_stay_off_html_and_disk_private(self):
        bank_connect.setup({"client_id":"unit-test-client","secret":"PRIVATE-SECRET","environment":"sandbox"})
        self.assertTrue(bank_connect.ready()[0])
        self.assertEqual(bank_connect.SETTINGS.stat().st_mode & 0o777,0o600)
        html=bank_connect.connection_page("link-fake-token","randomnonce")
        self.assertIn("Plaid.create",html)
        self.assertNotIn("PRIVATE-SECRET",html)
        self.assertIn("randomnonce",html)
    def test_token_exchange_and_import_balances_transactions(self):
        with sqlite3.connect(":memory:") as con:
            con.row_factory=sqlite3.Row
            bank_ledger.init(con)
            def mocked(route,payload,settings=None):
                if route=="/item/public_token/exchange":
                    return {"access_token":"access-token","item_id":"item-5"}
                if route=="/accounts/get":
                    return {"accounts":[{"account_id":"account-5","name":"Business checking",
                       "mask":"4321","balances":{"current":1234.56}}]}
                if route=="/transactions/sync":
                    return {"added":[{"transaction_id":"tx-9","account_id":"account-5",
                        "date":date.today().isoformat(),"amount":-20,"name":"Receipt"}],
                       "modified":[],"removed":[],"next_cursor":"next-1","has_more":False}
                raise AssertionError(route)
            with patch.object(bank_connect,"request",side_effect=mocked):
                bank_connect.exchange("public-token",con)
                self.assertEqual(bank_connect.sync(con),1)
                self.assertEqual(bank_connect.sync(con),1)
            acc=con.execute("SELECT * FROM money_accounts WHERE provider='plaid'").fetchone()
            self.assertEqual(acc["official_balance_cents"],123456)
            self.assertEqual(con.execute("SELECT count(*) FROM bank_feed").fetchone()[0],1)
            self.assertEqual(bank_connect.DATA.stat().st_mode & 0o777,0o600)
    def test_bank_service_needs_actual_provider_credentials(self):
        with self.assertRaises(ValueError):
            bank_connect.link_token()
        with self.assertRaises(ValueError):
            bank_connect.setup({"client_id":"test","secret":"","environment":"production"})

if __name__=="__main__":unittest.main()
