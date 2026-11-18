#!/usr/bin/env python3
"""Graphical first-run configuration and launcher. No terminal required."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.request
import webbrowser

APP=Path("/opt/el-grande")
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

def try_dashboard():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/",timeout=2) as r:
            return r.status in (200,401)
    except Exception:
        # urllib raises HTTPError for BasicAuth challenge; that means service exists.
        try:
            import urllib.error
            with urllib.request.urlopen(URL,timeout=2):pass
        except urllib.error.HTTPError as e:
            return e.code==401
        except Exception:pass
        return False

def open_dashboard():
    if try_dashboard():
        webbrowser.open(URL)
        return
    res=service("enable","--now","el-grande-desk.service")
    if res.returncode:
        messagebox.showerror("El Grande startup",res.stderr.strip() or "Could not start the service.")
        return
    webbrowser.open(URL)

def configure():
    env=read_env()
    root=tk.Tk()
    root.title("El Grande — First Run Setup")
    root.geometry("560x420")
    root.resizable(False,False)
    frm=ttk.Frame(root,padding=22);frm.pack(fill="both",expand=True)
    ttk.Label(frm,text="EL GRANDE",font=("Sans",20,"bold")).pack(anchor="w")
    ttk.Label(frm,text="All by Devoll — job desk and owner reporting",font=("Sans",10)).pack(anchor="w",pady=(0,14))
    vars_={}
    def field(key,title,default="",secret=False):
        ttk.Label(frm,text=title).pack(anchor="w",pady=(8,2))
        var=tk.StringVar(value=env.get(key,default))
        ttk.Entry(frm,textvariable=var,width=62,show="*" if secret else "").pack(fill="x")
        vars_[key]=var
    field("ABD_DASHBOARD_PASSWORD","Dashboard password (create your own)",secret=True)
    field("ABD_OWNER_REPORT_TO","Owner's completed-job report address","isaiztomey7@gmail.com")
    field("ABD_IMAP_USER","Business Gmail address (leave blank for demo mode)","allbydevoll@gmail.com")
    field("ABD_IMAP_APP_PASSWORD","Gmail app password (optional until email is connected)",secret=True)
    ttk.Label(frm,text="No customer estimates are emailed. Accounting postings are OFF until verified.",wraplength=500).pack(anchor="w",pady=12)
    def save():
        vals={k:v.get().strip() for k,v in vars_.items()}
        if len(vals["ABD_DASHBOARD_PASSWORD"])<12:
            messagebox.showerror("Password","Choose a dashboard password with at least 12 characters.")
            return
        recipient=vals["ABD_OWNER_REPORT_TO"]
        if "@" not in recipient or recipient.count("@")!=1:
            messagebox.showerror("Email","Enter a valid owner report email.")
            return
        vals["ABD_BLUESEER_ENABLE_LIVE_INVOICES"]="no"
        vals["ABD_REPORT_SMTP_USER"]=vals["ABD_IMAP_USER"] if vals["ABD_IMAP_APP_PASSWORD"] else ""
        try:
            write_env(vals)
            DATA.mkdir(parents=True,exist_ok=True)
            DATA.chmod(0o700)
            service("daemon-reload")
            res=service("enable","--now","el-grande-desk.service")
            if res.returncode:
                raise RuntimeError(res.stderr.strip() or "Failed to start job desk")
        except (OSError,ValueError,RuntimeError) as exc:
            messagebox.showerror("Setup failed",str(exc));return
        messagebox.showinfo("Installed","El Grande is configured. The dashboard opens in your browser.\n\nUsername: operator\nPassword: the password you chose.")
        root.destroy()
        webbrowser.open(URL)
    ttk.Button(frm,text="Save & Open Job Desk",command=save).pack(anchor="e",pady=6)
    root.mainloop()

def main():
    if "--setup" in sys.argv or not ENV.exists() or not read_env().get("ABD_DASHBOARD_PASSWORD"):
        configure()
    else:
        open_dashboard()

if __name__=="__main__":
    main()
