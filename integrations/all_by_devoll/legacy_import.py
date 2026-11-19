"""One-time read-only migration from a previous El Grande installation."""
from collections import defaultdict
from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path

import stock
import stock_reconcile
import work_orders

DEFAULT_PATH = Path.home() / ".local/share/el-grande/blueseer/data/en/bsdb.db"
DDL = """
CREATE TABLE IF NOT EXISTS legacy_import_complete (
 id INTEGER PRIMARY KEY CHECK(id=1), imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS legacy_records (
 entity TEXT NOT NULL, ordinal INTEGER NOT NULL, record TEXT NOT NULL,
 PRIMARY KEY(entity,ordinal)
);
"""
# Historical reports stay available without authentication tables or credentials.
HISTORY = (
    "item_mstr", "vd_mstr", "loc_mstr", "wh_mstr", "in_mstr", "tran_mstr",
    "po_mstr", "pod_mstr", "po_addr", "po_meta", "po_tax", "pod_tax",
    "recv_mstr", "recv_det", "plan_mstr", "plan_operation", "plan_opdet", "plan_meta",
    "cm_mstr", "cms_det", "sv_mstr", "svd_det", "quo_mstr", "quo_det",
    "ship_mstr", "ship_det", "ar_mstr", "ard_mstr", "ap_mstr", "vod_mstr", "gl_tran",
)
RETIRED_QUEUES = ("blue_sync", "erp_jobs", "erp_receipts")
CLOSED = {"closed", "cancelled", "canceled", "void", "voided"}


def decimal_string(value):
    try:
        number = Decimal(str(value or 0))
    except InvalidOperation as exc:
        raise ValueError("The old database contains an invalid number.") from exc
    if not number.is_finite():
        raise ValueError("The old database contains a non-finite number.")
    return format(number, "f")


def quantity(value):
    return stock.number(decimal_string(value), stock.QTY_SCALE, stock.MAX_QTY, "legacy quantity")


def ensure_item(con, sku, description="", unit=""):
    sku = stock.text(sku, "legacy SKU")
    old = con.execute("SELECT unit FROM stock_items WHERE sku=?", (sku,)).fetchone()
    if old:
        if unit and old["unit"] != unit:
            raise ValueError(f"Unit conflict for {sku}. Reconcile the item before migrating.")
        return
    stock.save_item(con, {"sku":sku, "description":description or sku, "unit":unit or "EA"})


def ensure_bin(con, site, warehouse, location):
    location = location or "Unassigned"
    warehouse = warehouse or "Unassigned"
    site = site or "Unassigned"
    row = con.execute("SELECT code FROM stock_bins WHERE site=? AND warehouse=? AND location=?",
                      (site,warehouse,location)).fetchone()
    if row:
        return row[0]
    code = location if not con.execute("SELECT 1 FROM stock_bins WHERE code=?", (location,)).fetchone() else (
        "Legacy-" + sha256(json.dumps([site,warehouse,location]).encode()).hexdigest()[:24])
    stock.save_bin(con, {"code":code, "site":site, "warehouse":warehouse, "location":location})
    return code


def archives(target, source, names):
    tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in names:
        if name not in tables:
            continue
        source_rows = source.execute(f"SELECT * FROM {name}")
        cols = [column[0] for column in source_rows.description]
        target.executemany("INSERT INTO legacy_records VALUES (?,?,?)",
            ((name, i, json.dumps(dict(zip(cols,row)), default=lambda value: {"hex":value.hex()}))
             for i,row in enumerate(source_rows,1)))


def opening_stock(con, source):
    for sku, description, unit in source.execute("SELECT it_item,it_desc,it_uom FROM item_mstr"):
        ensure_item(con, sku, description or "", (unit or "").strip())
    for code,name in source.execute("SELECT vd_addr,vd_name FROM vd_mstr"):
        con.execute("INSERT OR IGNORE INTO stock_vendors VALUES (?,?)",
                    (stock.text(code,"legacy vendor code"),stock.text(name or code,"legacy vendor name",160)))
    for location, site, warehouse in source.execute("SELECT loc_loc,loc_site,loc_wh FROM loc_mstr"):
        ensure_bin(con,site,warehouse,location)
    totals = defaultdict(int)
    for sku,site,warehouse,location,count in source.execute(
        "SELECT in_item,in_site,in_wh,in_loc,in_qoh FROM in_mstr"
    ):
        ensure_item(con,sku)
        bin_code = ensure_bin(con,site,warehouse,location)
        totals[(sku,bin_code)] += stock.number(decimal_string(count),stock.QTY_SCALE,stock.MAX_QTY,
                                             "legacy stock quantity",signed=True)
    for (sku,bin_code),count in totals.items():
        existing = con.execute("SELECT quantity FROM stock_balances WHERE sku=? AND bin=?", (sku,bin_code)).fetchone()
        if existing is not None and existing[0]!=count:
            raise ValueError(f"Stock conflict for {sku} at {bin_code}. Reconcile the two quantities before migrating.")
        if existing is None and count:
            stock.add_movement(con,sku,bin_code,count,"adjustment","BlueSeer opening balance")


def orders(con, source):
    for reference,vendor,created,status in source.execute("SELECT po_nbr,po_vend,po_ord_date,po_status FROM po_mstr"):
        if not reference or not vendor:
            continue  # Preserved in the original record archive.
        lines = []
        for line_no,sku,ordered,received,price,state in source.execute(
            "SELECT pod_line,pod_item,pod_ord_qty,pod_rcvd_qty,pod_netprice,pod_status FROM pod_mstr WHERE pod_nbr=?",
            (reference,),
        ):
            ordered,received = quantity(ordered),quantity(received)
            if not sku or not 0 <= received <= ordered or not ordered:
                continue
            if received < ordered and str(state or "").strip().lower() in CLOSED:
                continue  # A historical closed remainder is not a live commitment.
            ensure_item(con,sku)
            cost = Decimal(decimal_string(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            lines.append((int(line_no),sku,ordered,received,int(cost*100)))
        finished = bool(lines) and all(line[2]==line[3] for line in lines)
        if not lines or (str(status or "").strip().lower() in CLOSED and not finished):
            continue
        con.execute("INSERT OR IGNORE INTO stock_vendors VALUES (?,?)",(vendor,vendor))
        prior = con.execute("SELECT id,vendor FROM purchase_orders WHERE reference=?", (str(reference),)).fetchone()
        if prior:
            local = con.execute("""SELECT line_no,sku,ordered,received,unit_cost_cents FROM purchase_lines
                WHERE order_id=? AND voided=0""",(prior["id"],)).fetchall()
            if prior["vendor"]!=vendor or sorted(map(tuple,local))!=sorted(lines):
                raise ValueError(f"Purchase order {reference} conflicts with a local order.")
            continue
        order_id = con.execute("""INSERT INTO purchase_orders(vendor,reference,request_key,created_at,status)
            VALUES (?,?,?,?,?)""",(vendor,str(reference),"legacy-order:"+str(reference),created or stock.now(),
                                   "received" if finished else "open")).lastrowid
        con.executemany("""INSERT INTO purchase_lines(order_id,line_no,sku,ordered,received,unit_cost_cents,request_key)
            VALUES (?,?,?,?,?,?,?)""",((order_id,*line,f"legacy-line:{order_id}:{line[0]}") for line in lines))


def plans(con, source):
    for ref,sku,total,done,scheduled_qty,due,scheduled,status,notes in source.execute("""SELECT
        plan_nbr,plan_item,plan_qty_req,plan_qty_comp,plan_qty_sched,plan_date_due,plan_date_sched,plan_status,plan_rmks
        FROM plan_mstr WHERE plan_type='WO'"""):
        total,done,scheduled_qty = quantity(total),quantity(done),quantity(scheduled_qty)
        if not ref or not total or done>total or scheduled_qty>total:
            continue  # Preserve irregular historical plans in the archive.
        if sku:
            ensure_item(con,sku)
        reference = "BlueSeer-" + str(ref)
        state = "cancelled" if status == -1 else "complete" if status == 1 or total == done else "open"
        con.execute("""INSERT INTO work_orders
            (reference,sku,quantity,completed,scheduled_quantity,due_on,scheduled_on,notes,status) VALUES (?,?,?,?,?,?,?,?,?)""",
            (reference,sku or None,total,done,scheduled_qty,due or "",scheduled or "",notes or "",state))


def migrate(con, path=None):
    """Run inside an immediate transaction on the destination."""
    # Existing local transactions are authoritative. Retain their old posting
    # outcomes in the archive and never send their outbox again.
    if path is not None and not con.execute("SELECT 1 FROM legacy_import_complete WHERE id=1").fetchone():
        with closing(stock_reconcile.read_copy(path)) as source:
            source.execute("BEGIN")
            opening_stock(con,source)
            orders(con,source)
            plans(con,source)
            archives(con,source,HISTORY)
        con.execute("INSERT INTO legacy_import_complete VALUES (1,?)", (stock.now(),))
    for name in RETIRED_QUEUES:
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():
            if not con.execute("SELECT 1 FROM legacy_records WHERE entity=? LIMIT 1",(name,)).fetchone():
                archives(con,con,(name,))
