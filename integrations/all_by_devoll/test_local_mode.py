"""Local workstation mode: no operator password required, never remote access."""
import base64
import os
import subprocess
import sys
import types
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler

from desk import Handler

class FakeHeaders(dict):
    def get(self,key,default=None):return super().get(key,default)

class LocalModeTests(unittest.TestCase):
    def handler(self,host,authorization=None):
        h=object.__new__(Handler)
        h.headers=FakeHeaders({"Host":host})
        if authorization:h.headers["Authorization"]=authorization
        messages=[]
        h.send_response=lambda code:messages.append(code)
        h.send_header=lambda name,value:None
        h.end_headers=lambda :None
        h.wfile=types.SimpleNamespace(write=lambda x:None)
        return h,messages
    def test_no_password_accepted_on_loopback(self):
        h,_=self.handler("127.0.0.1:8765")
        with patch.object(sys.modules["desk"],"PASSWORD",""):
            self.assertTrue(h.auth())
    def test_no_password_rejected_for_forged_remote_host(self):
        h,status=self.handler("example.com:8765")
        with patch.object(sys.modules["desk"],"PASSWORD",""):
            self.assertFalse(h.auth())
        self.assertEqual(status,[403])
    def test_password_optional_but_enforced_when_set(self):
        h,status=self.handler("127.0.0.1:8765")
        with patch.object(sys.modules["desk"],"PASSWORD","some-secret"):
            self.assertFalse(h.auth())
        self.assertEqual(status,[401])
        encoded=base64.b64encode(b"operator:some-secret").decode("ascii")
        h,_=self.handler("127.0.0.1:8765","Basic "+encoded)
        with patch.object(sys.modules["desk"],"PASSWORD","some-secret"):
            self.assertTrue(h.auth())

if __name__=="__main__":unittest.main()
