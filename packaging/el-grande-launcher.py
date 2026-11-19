#!/usr/bin/env python3
"""Graphical first-run configuration and launcher. No terminal required."""
import os
import base64
from pathlib import Path
import subprocess
import sqlite3
import sys
import time
from tkinter import messagebox
import urllib.request
import webbrowser

ENV=Path.home()/".config"/"el-grande"/"desk.env"
DATA=Path.home()/".local"/"share"/"el-grande"
URL="http://127.0.0.1:8765"

def read_env():
    vals={}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k,v=line.split("=",1);vals[k]=v
    return vals

def write_env(values):
    ENV.parent.mkdir(parents=True,exist_ok=True)
    ENV.parent.chmod(0o700)
    keep=read_env()
    keep.update(values)
    # systemd environment file: do not allow newlines/quotes/control characters.
    for k,v in keep.items():
        if not k.replace("_","").isalnum() or any(c in v for c in ("\n","\r","\"","'","\\","%")):
            raise ValueError("Invalid configuration characters")
    ENV.write_text("".join(f"{k}={v}\n" for k,v in sorted(keep.items())))
    ENV.chmod(0o600)

def service(*args):
    return subprocess.run(["systemctl","--user",*args],capture_output=True,text=True,timeout=20)

def prepare_local_data():
    DATA.mkdir(parents=True,exist_ok=True)
    DATA.chmod(0o700)
    (DATA / "data").mkdir(exist_ok=True)
    (DATA / "data").chmod(0o700)
    local_db=DATA / "data" / "tickets.sqlite3"
    if not local_db.exists():
        # Migrate any tickets from the earlier developer checkout.
        old=Path.home() / "Applications" / "el-grande" / "integrations" / "all_by_devoll" / "data" / "tickets.sqlite3"
        if old.exists():
            with sqlite3.connect(old) as source, sqlite3.connect(local_db) as dest:
                source.backup(dest)


def ensure_first_run_defaults():
    # A brand-new install should open the shop directly. Email authorization
    # is offered in Settings when convenient, not as a startup obstacle.
    if ENV.exists():return
    prepare_local_data()
    write_env({
        "ABD_OWNER_REPORT_TO":"isaiztomey7@gmail.com",
        "ABD_IMAP_USER":"allbydevoll@gmail.com",
        "ABD_IMAP_APP_PASSWORD":"",
        "ABD_DB":str(DATA / "data" / "tickets.sqlite3"),
        "ABD_BIND":"127.0.0.1",
        "ABD_DASHBOARD_PASSWORD":""
    })

def try_dashboard(settings):
    request = urllib.request.Request(URL + "/ready")
    password = settings.get("ABD_DASHBOARD_PASSWORD")
    if password:
        token = base64.b64encode(("operator:" + password).encode("utf-8")).decode("ascii")
        request.add_header("Authorization", "Basic " + token)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 200 and response.read(16) == b"ready-local"
    except (OSError, ValueError):
        return False


def open_dashboard():
    try:
        prepare_local_data()
    except OSError as err:
        messagebox.showerror("El Grande storage", str(err))
        return
    settings = read_env()
    if not try_dashboard(settings):
        service("daemon-reload")
        desk = service("enable", "el-grande-desk.service")
        if not desk.returncode:
            # Also replaces any still-running pre-upgrade desk with no readiness route.
            desk = service("restart", "el-grande-desk.service")
        if desk.returncode:
            messagebox.showerror("El Grande startup", desk.stderr.strip() or "Could not start the service.")
            return
    for _ in range(40):
        if try_dashboard(settings):
            webbrowser.open(URL + ("/settings" if "--setup" in sys.argv else ""))
            return
        time.sleep(0.25)
    messagebox.showerror("El Grande startup", "The shop is not ready. See the El Grande desk service log for startup details.")


def main():
    try:
        ensure_first_run_defaults()
        open_dashboard()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        messagebox.showerror("El Grande startup", str(exc))


if __name__ == "__main__":
    main()
