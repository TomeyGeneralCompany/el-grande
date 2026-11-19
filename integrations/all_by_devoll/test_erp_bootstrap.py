"""Bootstrap the real bundled ERP using native APIs without touching production data."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import erp_bootstrap

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"bsdb.db"
        self.env=Path(self.tmp.name)/"desk.env"
        with sqlite3.connect(self.db) as con:
            for name,column,values in (
              ("user_mstr","us_userid",("admin",)),
              ("site_mstr","site_site",("1000",)),
              ("ac_mstr","ac_id",("20000000",)),
              ("cust_term","cut_code",("N30",)),
              ("item_mstr","it_item",())):
                con.execute(f"CREATE TABLE {name} ({column} TEXT PRIMARY KEY)")
                for value in values:con.execute(f"INSERT INTO {name} VALUES (?)",(value,))
            con.execute("""CREATE TABLE usr_meta(
              usrm_id TEXT, usrm_type TEXT, usrm_key TEXT, usrm_value TEXT)""")
    def tearDown(self):self.tmp.cleanup()
    def test_readonly_detection(self):
        found=erp_bootstrap.discover_database(self.db)
        self.assertEqual(found,{"site":"1000","ar_account":"20000000","terms":"N30"})
    def test_loopback_acl_is_idempotent(self):
        self.assertTrue(erp_bootstrap.allow_loopback_api_user(self.db,"admin"))
        self.assertFalse(erp_bootstrap.allow_loopback_api_user(self.db,"admin"))
        with sqlite3.connect(self.db) as con:
            acl=con.execute("SELECT usrm_type,usrm_key,usrm_value FROM usr_meta").fetchall()
        self.assertEqual(acl,[("ip","admin","127.0.0.1")])
    def test_native_item_bootstrap_and_persist(self):
        sessions=[]
        class FakeClient:
            def __init__(self,base,user,password):
                self.base=base;self.user=user;self.password=password
                self.items={}
                sessions.append(self)
            def authenticate(self):return "session"
            def get(self,res,action,key):
                return self.items.get(key,{})
            def post(self,res,action,body):
                data=json.loads(body)
                self.items[data["it_item"]]=data
                return ["0","success"]
        result=erp_bootstrap.configure(self.db,self.env,FakeClient)
        self.assertTrue(result["connected"])
        settings=erp_bootstrap.read_env(self.env)
        self.assertEqual(settings["ABD_BLUESEER_USER"],"admin")
        self.assertEqual(settings["ABD_BLUESEER_SITE"],"1000")
        self.assertEqual(settings["ABD_BLUESEER_AR_ACCOUNT"],"20000000")
        self.assertEqual(settings["ABD_BLUESEER_LABOR_ITEM"],"ABD-LABOR")
        self.assertEqual(settings["ABD_BLUESEER_PARTS_ITEM"],"ABD-PARTS")
        self.assertEqual(settings["ABD_BLUESEER_ENABLE_LIVE_INVOICES"],"no")
        self.assertEqual(self.env.stat().st_mode & 0o777,0o600)
        self.assertEqual(len(sessions[0].items),4)
    def test_refuse_failed_login_and_preserve_configuration(self):
        self.env.write_text("ABD_IMAP_USER=allbydevoll@gmail.com\n")
        before=self.env.read_text()
        class NoAuth:
            def __init__(self,**kw):pass
            def authenticate(self):raise ValueError("Unauthorized")
        with self.assertRaises(ValueError):
            erp_bootstrap.configure(self.db,self.env,NoAuth)
        self.assertEqual(self.env.read_text(),before)
    def test_no_silent_live_invoices(self):
        p=erp_bootstrap.service_item_payload("ABD-LABOR","Labor","1000")
        self.assertEqual(p["it_type"],"S")
        self.assertEqual(p["it_uom"],"EA")
        self.assertIsInstance(p["it_lotsize"],int)
        self.assertIsInstance(p["it_sell_price"],float)

if __name__=="__main__":unittest.main()
