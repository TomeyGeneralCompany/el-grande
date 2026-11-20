"""Run the existing El Grande Python desk inside a private Android process."""
import os
import secrets
import sys
import types
from decimal import Decimal
from pathlib import Path
from threading import Thread

_server_started = False


def _android_invoice_adapter(home):
    """Use the Android PDF engine without depending on native ReportLab wheels."""
    from java import jclass

    module = types.ModuleType("invoice_pdf")
    directory = Path(home) / "invoices"

    def create(ticket, completed, root=None):
        if not ticket["finalized_at"]:
            raise ValueError("A finalized bill is required before issuing a PDF")
        total = Decimal(str(ticket["bill_total"]))
        if not total.is_finite() or total < 0 or (completed is not None and
                total != Decimal(str(completed["actual_invoice"]))):
            raise ValueError("Customer invoice does not agree with final bill")
        target = Path(root) / ("ABD-%06d.pdf" % ticket["id"]) if root else directory / ("ABD-%06d.pdf" % ticket["id"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            description = (completed["work_performed"] if completed is not None else
                           ticket["notes"] or "Service as recorded on the job ticket")
            jclass("com.tomeygeneral.elgrande.AndroidPdf").render(
                str(target), int(ticket["id"]), str(ticket["customer"] or "Customer"),
                str(ticket["phone"] or ""), str(ticket["location"] or ""),
                str(ticket["machine"] or ""), str(ticket["service"] or "Repair service"),
                str(ticket["problem"] or ""), str(description or ""), format(total, ".2f"),
                str(ticket["finalized_at"]))
        return target

    module.create = create
    sys.modules["invoice_pdf"] = module


def start(home, token):
    global _server_started
    if _server_started:
        return "running"
    if not token or len(token) < 32:
        raise ValueError("Missing private app session")
    home = str(Path(home).resolve())
    os.environ["HOME"] = home
    os.environ["ABD_DB"] = str(Path(home) / "data" / "tickets.sqlite3")
    os.environ["ABD_BIND"] = "127.0.0.1"
    os.environ["ABD_PORT"] = "8765"
    os.environ.pop("ABD_DASHBOARD_PASSWORD", None)

    _android_invoice_adapter(home)
    import desk

    original_auth = desk.Handler.auth
    def private_auth(handler):
        # Other local Android apps can reach loopback. Require a per-launch
        # random browser session for every page and every mutation.
        cookie = handler.headers.get("Cookie", "")
        values = [p.strip().partition("=") for p in cookie.split(";")]
        supplied = next((v for name, _, v in values if name == "eg_session"), "")
        if not secrets.compare_digest(supplied, token):
            handler.response_headers(403, "text/plain")
            handler.wfile.write(b"Private El Grande session required")
            return False
        return original_auth(handler)

    desk.Handler.auth = private_auth
    Thread(target=desk.main, name="el-grande-local-server", daemon=True).start()
    _server_started = True
    return "started"
