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
    def test_email_settings_save_without_erasing_erp(self):
        office_settings.HOME_CONFIG.parent.mkdir(parents=True,exist_ok=True)
        office_settings.HOME_CONFIG.write_text("ABD_BLUESEER_SITE=1000\nABD_IMAP_APP_PASSWORD=oldvalue\n")
        d=office_settings.save({"ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
           "ABD_IMAP_USER":"allbydevoll@gmail.com","ABD_IMAP_APP_PASSWORD":""})
        self.assertEqual(d["ABD_BLUESEER_SITE"],"1000")
        self.assertEqual(d["ABD_IMAP_APP_PASSWORD"],"oldvalue")
        self.assertEqual(office_settings.HOME_CONFIG.stat().st_mode & 0o777,0o600)
        self.assertIn("ABD_BLUESEER_SITE=1000",office_settings.HOME_CONFIG.read_text())
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
    def test_shop_handler_exposes_settings(self):
        self.assertTrue(hasattr(desk.Handler,"do_GET"))
        self.assertTrue(hasattr(desk.Handler,"do_POST"))

if __name__=="__main__":unittest.main()
