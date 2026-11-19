"""Local vendor, stock, order and receiving records for the shop desk."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

QTY_SCALE = 1_000_000
MAX_QTY = 1_000_000_000 * QTY_SCALE

DDL = """
CREATE TABLE IF NOT EXISTS stock_vendors (
    code TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_items (
    sku TEXT PRIMARY KEY, description TEXT NOT NULL, unit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_bins (
    code TEXT PRIMARY KEY, site TEXT NOT NULL, warehouse TEXT NOT NULL, location TEXT NOT NULL,
    UNIQUE(site, warehouse, location)
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY, vendor TEXT NOT NULL REFERENCES stock_vendors(code),
    reference TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','open','received'))
);
CREATE UNIQUE INDEX IF NOT EXISTS purchase_orders_reference
    ON purchase_orders(reference) WHERE reference != '';
CREATE TABLE IF NOT EXISTS purchase_lines (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
    line_no INTEGER NOT NULL, sku TEXT NOT NULL REFERENCES stock_items(sku),
    ordered INTEGER NOT NULL CHECK(ordered>0), received INTEGER NOT NULL DEFAULT 0
        CHECK(received>=0 AND received<=ordered),
    unit_cost_cents INTEGER NOT NULL CHECK(unit_cost_cents>=0),
    voided INTEGER NOT NULL DEFAULT 0 CHECK(voided IN (0,1)), request_key TEXT NOT NULL UNIQUE, UNIQUE(order_id,line_no)
);
CREATE TABLE IF NOT EXISTS stock_receipts (
    id INTEGER PRIMARY KEY, line_id INTEGER NOT NULL REFERENCES purchase_lines(id),
    bin TEXT NOT NULL REFERENCES stock_bins(code), quantity INTEGER NOT NULL CHECK(quantity>0),
    unit_cost_cents INTEGER NOT NULL CHECK(unit_cost_cents>=0),
    reference TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, received_at TEXT NOT NULL,
    reversed_at TEXT, reversal_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS stock_receipts_line ON stock_receipts(line_id,id);
CREATE TABLE IF NOT EXISTS stock_balances (
    sku TEXT NOT NULL REFERENCES stock_items(sku), bin TEXT NOT NULL REFERENCES stock_bins(code),
    quantity INTEGER NOT NULL CHECK(quantity>=0), PRIMARY KEY(sku,bin)
);
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY, sku TEXT NOT NULL REFERENCES stock_items(sku),
    bin TEXT NOT NULL REFERENCES stock_bins(code), delta INTEGER NOT NULL CHECK(delta<>0),
    kind TEXT NOT NULL CHECK(kind IN ('adjustment','receipt','reversal')),
    receipt_id INTEGER REFERENCES stock_receipts(id), request_key TEXT UNIQUE,
    reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(receipt_id,kind)
);
CREATE INDEX IF NOT EXISTS stock_movements_item ON stock_movements(sku,id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text(value, label, limit=80, required=True):
    value = value.strip()
    if len(value) > limit or (required and not value) or any(ord(c) < 32 for c in value):
        raise ValueError(f"Enter a valid {label} of up to {limit} characters.")
    return value


def number(value, scale, limit, label, *, signed=False):
    try:
        # Bound input length and reject exponent notation before Decimal arithmetic.
        if len(value) > 26 or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value):
            raise ValueError
        n = Decimal(value) * scale
        if n != n.to_integral_value() or not (-limit if signed else 0) <= n <= limit:
            raise ValueError
    except (ValueError, InvalidOperation):
        raise ValueError(f"Enter a valid {label}.") from None
    return int(n)


def qty(value, *, signed=False):
    quantity = number(value, QTY_SCALE, MAX_QTY, "quantity (up to six decimal places)", signed=signed)
    if quantity == 0:
        raise ValueError("Quantity must be nonzero.")
    return quantity


def quantity_label(quantity):
    return format(Decimal(quantity) / QTY_SCALE, "f")


def key(value):
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Reload the form before submitting.")
    return value


def identifier(value):
    if not re.fullmatch(r"[0-9]{1,19}", value) or not 0 < int(value) < 2**63:
        raise ValueError("Enter a valid record number.")
    return int(value)


def lookup(con, sql, values, label):
    row = con.execute(sql, values).fetchone()
    if row is None:
        raise LookupError(f"{label} was not found.")
    return row


def save_item(con, data):
    values = (text(data.get("sku", ""), "SKU"), text(data.get("description", ""), "description", 160),
              text(data.get("unit", ""), "unit of measure", 24))
    existing = con.execute("SELECT description,unit FROM stock_items WHERE sku=?", values[:1]).fetchone()
    if existing and existing["unit"] != values[2]:
        raise ValueError("An existing item's unit of measure cannot change.")
    con.execute("""INSERT INTO stock_items VALUES (?,?,?)
        ON CONFLICT(sku) DO UPDATE SET description=excluded.description""", values)


def save_vendor(con, data):
    con.execute("""INSERT INTO stock_vendors VALUES (?,?)
        ON CONFLICT(code) DO UPDATE SET name=excluded.name""",
        (text(data.get("code", ""), "vendor code"), text(data.get("name", ""), "vendor name", 160)))


def save_bin(con, data):
    values = tuple(text(data.get(name, ""), name) for name in ("code", "site", "warehouse", "location"))
    existing = con.execute("SELECT site,warehouse,location FROM stock_bins WHERE code=?", values[:1]).fetchone()
    if existing and tuple(existing) != values[1:]:
        raise ValueError("An existing bin's location cannot change.")
    if con.execute("SELECT 1 FROM stock_bins WHERE site=? AND warehouse=? AND location=? AND code!=?",
                   (*values[1:], values[0])).fetchone():
        raise ValueError("That site, warehouse and location already has a bin.")
    con.execute("INSERT OR IGNORE INTO stock_bins VALUES (?,?,?,?)", values)


def add_movement(con, sku, bin_code, delta, kind, reason, receipt=None, request=None):
    lookup(con, "SELECT sku FROM stock_items WHERE sku=?", (sku,), "Item")
    lookup(con, "SELECT code FROM stock_bins WHERE code=?", (bin_code,), "Bin")
    before = con.execute("SELECT quantity FROM stock_balances WHERE sku=? AND bin=?", (sku, bin_code)).fetchone()
    total = (before["quantity"] if before else 0) + delta
    if not 0 <= total <= MAX_QTY:
        raise ValueError("That movement would leave an invalid on-hand quantity.")
    con.execute("""INSERT INTO stock_balances VALUES (?,?,?)
        ON CONFLICT(sku,bin) DO UPDATE SET quantity=excluded.quantity""", (sku, bin_code, total))
    con.execute("""INSERT INTO stock_movements(sku,bin,delta,kind,receipt_id,request_key,reason,created_at)
        VALUES (?,?,?,?,?,?,?,?)""", (sku, bin_code, delta, kind, receipt, request, reason, now()))


def adjust(con, data):
    request = key(data.get("request", ""))
    values = (text(data.get("sku", ""), "SKU"), text(data.get("bin", ""), "bin"),
              qty(data.get("quantity", ""), signed=True), text(data.get("reason", ""), "reason", 200))
    existing = con.execute("SELECT sku,bin,delta,reason FROM stock_movements WHERE request_key=?",
                           (request,)).fetchone()
    if existing:
        if tuple(existing) != values:
            raise ValueError("This adjustment was already submitted with different values.")
        return
    add_movement(con, *values[:3], "adjustment", values[3], request=request)


def create_order(con, data):
    values = (text(data.get("vendor", ""), "vendor code"),
              text(data.get("reference", ""), "purchase order number", required=False))
    request = key(data.get("request", ""))
    existing = con.execute("SELECT id,vendor,reference FROM purchase_orders WHERE request_key=?", (request,)).fetchone()
    if existing:
        if tuple(existing)[1:] != values:
            raise ValueError("This order was already submitted with different values.")
        return existing["id"]
    lookup(con, "SELECT code FROM stock_vendors WHERE code=?", values[:1], "Vendor")
    if values[1] and con.execute("SELECT 1 FROM purchase_orders WHERE reference=?", values[1:]).fetchone():
        raise ValueError("This purchase order number already exists.")
    return con.execute("""INSERT INTO purchase_orders(vendor,reference,request_key,created_at,status)
        VALUES (?,?,?,?,'draft')""", (*values, request, now())).lastrowid


def add_line(con, order_id, data):
    values = (order_id, text(data.get("sku", ""), "SKU"), qty(data.get("quantity", "")),
              number(data.get("cost", ""), 100, 10_000_000_000, "unit cost (in dollars and cents)"))
    request = key(data.get("request", ""))
    existing = con.execute("""SELECT order_id,sku,ordered,unit_cost_cents
        FROM purchase_lines WHERE request_key=?""", (request,)).fetchone()
    if existing:
        if tuple(existing) != values:
            raise ValueError("This line was already submitted with different values.")
        return
    order = lookup(con, "SELECT status FROM purchase_orders WHERE id=?", (order_id,), "Purchase order")
    if order["status"] != "draft":
        raise ValueError("Lines can only be added to draft orders.")
    lookup(con, "SELECT sku FROM stock_items WHERE sku=?", values[1:2], "Item")
    line_no = con.execute("SELECT COALESCE(MAX(line_no),0)+1 FROM purchase_lines WHERE order_id=?",
                          (order_id,)).fetchone()[0]
    con.execute("""INSERT INTO purchase_lines(order_id,sku,ordered,unit_cost_cents,line_no,request_key)
        VALUES (?,?,?,?,?,?)""", (*values, line_no, request))


def remove_line(con, order_id, data):
    order = lookup(con, "SELECT status FROM purchase_orders WHERE id=?", (order_id,), "Purchase order")
    if order["status"] != "draft":
        raise ValueError("Lines can only be removed from draft orders.")
    line_id = identifier(data.get("line", ""))
    lookup(con, "SELECT id FROM purchase_lines WHERE id=? AND order_id=?",
           (line_id, order_id), "Purchase order line")
    con.execute("UPDATE purchase_lines SET voided=1 WHERE id=?", (line_id,))


def open_order(con, order_id):
    order = lookup(con, "SELECT status FROM purchase_orders WHERE id=?", (order_id,), "Purchase order")
    if order["status"] != "draft":
        return
    if not con.execute("SELECT 1 FROM purchase_lines WHERE order_id=? AND voided=0", (order_id,)).fetchone():
        raise ValueError("Add at least one line before opening the order.")
    con.execute("UPDATE purchase_orders SET status='open' WHERE id=?", (order_id,))


def update_order_status(con, order_id):
    is_open = con.execute("SELECT 1 FROM purchase_lines WHERE order_id=? AND voided=0 AND ordered>received LIMIT 1",
                          (order_id,)).fetchone()
    con.execute("UPDATE purchase_orders SET status=? WHERE id=?", ("open" if is_open else "received", order_id))


def receive(con, order_id, data):
    line_id = identifier(data.get("line", ""))
    bin_code = text(data.get("bin", ""), "bin")
    quantity = qty(data.get("quantity", ""))
    reference = text(data.get("reference", ""), "packing slip", required=False)
    request = key(data.get("request", ""))
    line = lookup(con, """SELECT l.*,o.status FROM purchase_lines l
        JOIN purchase_orders o ON o.id=l.order_id WHERE l.id=? AND l.order_id=? AND l.voided=0""",
        (line_id, order_id), "Purchase order line")
    existing = con.execute("SELECT line_id,bin,quantity,reference FROM stock_receipts WHERE request_key=?",
                           (request,)).fetchone()
    if existing:
        if tuple(existing) != (line_id, bin_code, quantity, reference):
            raise ValueError("This receipt was already submitted with different values.")
        return
    if line["status"] != "open" or quantity > line["ordered"] - line["received"]:
        raise ValueError("The receipt exceeds the open quantity for this line.")
    lookup(con, "SELECT code FROM stock_bins WHERE code=?", (bin_code,), "Bin")
    receipt = con.execute("""INSERT INTO stock_receipts(line_id,bin,quantity,unit_cost_cents,reference,request_key,received_at)
        VALUES (?,?,?,?,?,?,?)""", (line_id, bin_code, quantity, line["unit_cost_cents"], reference, request, now())).lastrowid
    add_movement(con, line["sku"], bin_code, quantity, "receipt", reference, receipt)
    con.execute("UPDATE purchase_lines SET received=received+? WHERE id=?", (quantity, line_id))
    update_order_status(con, order_id)


def reverse(con, order_id, data):
    receipt_id = identifier(data.get("receipt", ""))
    reason = text(data.get("reason", ""), "reversal reason", 200)
    receipt = lookup(con, """SELECT r.*,l.sku FROM stock_receipts r
        JOIN purchase_lines l ON l.id=r.line_id WHERE r.id=? AND l.order_id=?""",
        (receipt_id, order_id), "Receipt")
    if receipt["reversed_at"]:
        if receipt["reversal_reason"] != reason:
            raise ValueError("This receipt already has a reversal.")
        return
    quantity = receipt["quantity"]
    add_movement(con, receipt["sku"], receipt["bin"], -quantity, "reversal", reason, receipt_id)
    con.execute("UPDATE stock_receipts SET reversed_at=?,reversal_reason=? WHERE id=?", (now(), reason, receipt_id))
    con.execute("UPDATE purchase_lines SET received=received-? WHERE id=?", (quantity, receipt["line_id"]))
    update_order_status(con, order_id)
