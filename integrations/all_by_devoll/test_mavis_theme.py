"""Regression checks for the MAVIS house-style across El Grande screens.

These checks focus exclusively on presentation. All existing business operations
are covered by the separate job desk, banking, invoice and AR test suites.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bank_connect
import bank_ui
import desk
import mavis_theme
import office_settings
import shop_ui

class MavisThemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original_db=desk.DB
        desk.DB=Path(self.tmp.name)/"test.sqlite3"
        desk.init()
    def tearDown(self):
        desk.DB=self.original_db
        self.tmp.cleanup()

    def test_reference_palette_is_shared(self):
        for name,color in (("--app-red","#c90028"),
                           ("--panel-teal","#00c4bf"),
                           ("--white","#ffffff")):
            self.assertIn(name,mavis_theme.CSS)
            self.assertIn(color,mavis_theme.CSS)
        self.assertIn("border-radius:50%",mavis_theme.CSS)
        self.assertIn("grid-template-columns",mavis_theme.CSS)
        self.assertIn("background:#c90028",mavis_theme.CSS)
        self.assertIn("color:#fff",mavis_theme.CSS)

    def test_job_desk_uses_same_mavis_style(self):
        with desk.db() as con:
            jobs=con.execute("SELECT * FROM tickets").fetchall()
        output=shop_ui.render(jobs,[],desk.db,desk.amounts,{
            "mailbox":False,"report":False,
            "erp":{"running":False,"configured":False}})
        self.assertIn("ALL BY DEVOLL",output)
        self.assertIn('href="/bank"',output)
        self.assertIn("--panel-teal:#00c4bf",output)
        self.assertIn("background:#c90028",output)
        self.assertIn("Cash received today",output)
        self.assertIn("New service request",output)

    def test_bank_and_safe_screen_use_same_mavis_style(self):
        with desk.db() as con:
            output=bank_ui.page(con,False)
        self.assertIn("Count cash in the safe",output)
        self.assertIn("Transfer / cash deposit",output)
        self.assertIn("--panel-teal:#00c4bf",output)
        self.assertIn("background:#c90028",output)
        self.assertIn("Recorded register balance",output)

    def test_settings_uses_same_mavis_style_without_secret_reflection(self):
        with patch.object(bank_connect,"ready",return_value=(False,"sandbox")):
            output=office_settings.page({"ABD_IMAP_APP_PASSWORD":"TOPSECRET"},"saved")
        self.assertIn("Add Gmail connection",output)
        self.assertIn("Add bank account",output)
        self.assertIn("--panel-teal:#00c4bf",output)
        self.assertNotIn("TOPSECRET",output)

    def test_bank_link_keeps_plaid_authorization_and_mavis_style(self):
        output=bank_connect.connection_page("mock-link-token","testnonce")
        self.assertIn("Plaid.create",output)
        self.assertIn("mock-link-token",output)
        self.assertIn("--panel-teal:#00c4bf",output)
        self.assertIn("background:#c90028",output)

if __name__=="__main__":
    unittest.main()
