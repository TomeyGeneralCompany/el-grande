"""Settings are part of the local application, and never expose saved secrets."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import office_settings
import desk

class OfficeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=office_settings.HOME_CONFIG
        office_settings.HOME_CONFIG=Path(self.tmp.name)/".config"/"desk.env"
    def tearDown(self):
        office_settings.HOME_CONFIG=self.old
        self.tmp.cleanup()
    def test_email_settings_save_preserves_other_settings(self):
        office_settings.HOME_CONFIG.parent.mkdir(parents=True,exist_ok=True)
        office_settings.HOME_CONFIG.write_text("ABD_BIND=127.0.0.1\nABD_IMAP_APP_PASSWORD=oldvalue\n")
        d=office_settings.save({"ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
           "ABD_IMAP_USER":"allbydevoll@gmail.com","ABD_IMAP_APP_PASSWORD":""})
        self.assertEqual(d["ABD_BIND"],"127.0.0.1")
        self.assertEqual(d["ABD_IMAP_APP_PASSWORD"],"oldvalue")
        self.assertEqual(office_settings.HOME_CONFIG.stat().st_mode & 0o777,0o600)
        self.assertIn("ABD_BIND=127.0.0.1",office_settings.HOME_CONFIG.read_text())
    def test_updated_gmail_secret_applies_to_outbound_immediately(self):
        with patch.dict(os.environ,{"ABD_REPORT_SMTP_APP_PASSWORD":"oldpassword"},clear=False):
            office_settings.save({"ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
                 "ABD_IMAP_USER":"allbydevoll@gmail.com",
                 "ABD_IMAP_APP_PASSWORD":"newpassword"})
            self.assertEqual(os.environ["ABD_REPORT_SMTP_APP_PASSWORD"],"newpassword")
            self.assertEqual(os.environ["ABD_IMAP_APP_PASSWORD"],"newpassword")
    def test_email_credentials_do_not_echo_in_settings_html(self):
        rendered=office_settings.page({"ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
            "ABD_IMAP_USER":"allbydevoll@gmail.com",
            "ABD_IMAP_APP_PASSWORD":"TOPSECRET"},"saved")
        self.assertIn('action="/settings/save"',rendered)
        self.assertIn("Gmail app password",rendered)
        self.assertNotIn("TOPSECRET",rendered)
    def test_bad_input_does_not_overwrite(self):
        office_settings.save({"ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
            "ABD_IMAP_USER":"allbydevoll@gmail.com"})
        prior=office_settings.HOME_CONFIG.read_text()
        for bad in ("not-an-email","one@example.com\nBAD=1"):
            with self.assertRaises(ValueError):
                office_settings.save({"ABD_OWNER_REPORT_TO":bad})
        self.assertEqual(office_settings.HOME_CONFIG.read_text(),prior)
    def test_gmail_test_does_not_login_without_credentials(self):
        with patch.dict(os.environ,{"ABD_IMAP_APP_PASSWORD":"","ABD_IMAP_USER":""}):
            with self.assertRaises(ValueError):office_settings.test_gmail()
    def test_clickable_gmail_and_bank_panels(self):
        html=office_settings.page({},"")
        self.assertIn("Add Gmail connection",html)
        self.assertIn("Add bank account",html)
        self.assertIn('action="/settings/save-bank"',html)
        self.assertIn('action="/settings/test-gmail"',html)
        self.assertNotIn("Native BlueSeer accounting posting is kept off",html)
    def test_bank_account_saves_only_last_four_and_preserves_email(self):
        office_settings.save({"ABD_IMAP_USER":"allbydevoll@gmail.com",
                              "ABD_IMAP_APP_PASSWORD":"credential"})
        with patch.dict(os.environ,{"ABD_BLUESEER_CONNECTED":"no"}):
            result=office_settings.save_bank({"ABD_BANK_NAME":"Local Bank",
                "ABD_BANK_LABEL":"Shop checking",
                "ABD_BANK_LAST4":"4321","ABD_BLUESEER_PAYMENT_BANK":"bk"})
        self.assertEqual(result["ABD_BANK_NAME"],"Local Bank")
        self.assertEqual(result["ABD_BANK_LAST4"],"4321")
        self.assertNotIn("ABD_BLUESEER_PAYMENT_BANK",result)
        self.assertEqual(result["ABD_IMAP_APP_PASSWORD"],"credential")
        self.assertEqual(office_settings.HOME_CONFIG.stat().st_mode & 0o777,0o600)
        html=office_settings.page(result,"bank-saved")
        self.assertIn("Local Bank",html)
        self.assertIn("4321",html)
        self.assertNotIn("credential",html)
    def test_reject_full_account(self):
        with self.assertRaises(ValueError):
            office_settings.save_bank({"ABD_BANK_LAST4":"1234567890"})

    def test_shop_handler_exposes_settings(self):
        self.assertTrue(hasattr(desk.Handler,"do_GET"))
        self.assertTrue(hasattr(desk.Handler,"do_POST"))

if __name__=="__main__":unittest.main()
