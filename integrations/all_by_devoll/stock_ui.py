"""Inventory and procurement pages using the existing shop layout."""
from decimal import Decimal
from secrets import token_hex
from urllib.parse import urlencode

import shop_ui
import stock

PAGE_SIZE = 25
MASTERS = {
    "/inventory": ("Items", "stock_items", "sku", (("sku", "SKU"), ("description", "Description"), ("unit", "Unit of measure"))),
    "/inventory/vendors": ("Vendors", "stock_vendors", "code", (("code", "Vendor code"), ("name", "Vendor name"))),
    "/inventory/bins": ("Bins", "stock_bins", "code", (("code", "Bin code"), ("site", "Site"), ("warehouse", "Warehouse"), ("location", "Location"))),
}

esc = shop_ui.esc
field = shop_ui.field


def hidden(name, value):
    return f'<input type="hidden" name="{name}" value="{esc(value)}">'


def form(path, fields, action, *, request=False):
    token = hidden("request", token_hex(16)) if request else ""
    return (f'<form method="post" action="{path}">{token}<div class="fields">{fields}</div>'
            f'<div class="footactions">{shop_ui.button(action)}</div></form>')


def control(name, label, kind="text", step=None, required=True):
    return field(name, label, kind=kind, step=step, required=required)


def section(title, content):
    return f'<section class="panel"><h2>{title}</h2>{content}</section>'


def list_table(headers, rows):
    if not rows:
        return '<p class="muted">No records on this page.</p>'
    head = "".join(f'<th scope="col">{name}</th>' for name in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div style="overflow-x:auto"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def navigation(path, parameter, cursor, next_value, query=None):
    args = query or {}
    links = []
    if cursor:
        url = path + ("?" + urlencode(args) if args else "")
        links.append(f'<a class="action secondary" href="{esc(url)}">First page</a>')
    if next_value is not None:
        url = path + "?" + urlencode({**args, parameter: next_value})
        links.append(f'<a class="action secondary" href="{esc(url)}">Next page</a>')
    return '<div class="footactions">' + "".join(links) + "</div>" if links else ""


def master_page(con, path, query):
    title, table, key, fields = MASTERS[path]
    after = stock.text(query.get("after", [""])[0], "page cursor", required=False)
    prefix = stock.text(query.get("q", [""])[0], "filter", required=False)
    # Table and column identifiers come only from the fixed page map.
    pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    records = con.execute(f"""SELECT * FROM {table}
        WHERE {key}>? AND {key} LIKE ? ESCAPE '\\' ORDER BY {key} LIMIT ?""",
        (after, pattern, PAGE_SIZE + 1)).fetchall()
    data = []
    for row in records[:PAGE_SIZE]:
        cells = [esc(row[name]) for name, _ in fields]
        if path == "/inventory":
            url = "/inventory/item?" + urlencode({"sku": row["sku"]})
            cells[0] = f'<a href="{esc(url)}">{cells[0]}</a>'
        data.append(cells)
    links = ('<div class="footactions"><a href="/inventory">Items</a> '
             '<a href="/inventory/vendors">Vendors</a> <a href="/inventory/bins">Bins</a> '
             '<a href="/purchases">Purchase orders</a></div>')
    search = (f'<form method="get" action="{path}" class="inlineform">' +
              field("q", "Filter by code", prefix) + shop_ui.button("Filter") + "</form>")
    page = list_table([label for _, label in fields], data)
    page += navigation(path, "after", after, records[PAGE_SIZE-1][key] if len(records)>PAGE_SIZE else None,
                       {"q": prefix} if prefix else None)
    save = form(path + "/save", "".join(control(name, label) for name, label in fields), "Save")
    if path == "/inventory":
        links += '<p>Reconcile existing BlueSeer quantities before recording movements for existing stock.</p>'
    return shop_ui.page_shell(section(title, links + search + page) + section("Add or update", save))


def item_page(con, query):
    sku = stock.text(query.get("sku", [""])[0], "SKU")
    item = stock.lookup(con, "SELECT * FROM stock_items WHERE sku=?", (sku,), "Item")
    cursor = query.get("before", [""])[0]
    before = stock.identifier(cursor) if cursor else None
    balances = con.execute("""SELECT b.bin,b.quantity,l.site,l.warehouse,l.location
        FROM stock_balances b JOIN stock_bins l ON l.code=b.bin WHERE b.sku=? ORDER BY b.bin""", (sku,)).fetchall()
    if before is None:
        moves = con.execute("SELECT * FROM stock_movements WHERE sku=? ORDER BY id DESC LIMIT ?",
                            (sku, PAGE_SIZE+1)).fetchall()
    else:
        moves = con.execute("SELECT * FROM stock_movements WHERE sku=? AND id<? ORDER BY id DESC LIMIT ?",
                            (sku, before, PAGE_SIZE+1)).fetchall()
    stock_rows = [(esc(r["bin"]), esc(r["site"]), esc(r["warehouse"]), esc(r["location"]),
                   stock.quantity_label(r["quantity"])) for r in balances]
    move_rows = [(esc(r["created_at"]), esc(r["bin"]), stock.quantity_label(r["delta"]),
                  esc(r["kind"]), esc(r["reason"])) for r in moves[:PAGE_SIZE]]
    adjust = form("/inventory/adjust", hidden("sku", sku) + control("bin", "Bin code") +
                  control("quantity", "Quantity change (+ or −)") + control("reason", "Reason"),
                  "Record adjustment", request=True)
    content = section(f'{esc(sku)} · {esc(item["description"])}',
                      '<p><a href="/inventory">Back to inventory</a></p>'
                      f'<p>Unit of measure: {esc(item["unit"])}</p>' +
                      list_table(("Bin", "Site", "Warehouse", "Location", "On hand"), stock_rows))
    content += section("Adjust stock", adjust)
    content += section("Stock movements", list_table(("Recorded", "Bin", "Change", "Type", "Reason"), move_rows) +
                       navigation("/inventory/item", "before", before,
                                  moves[PAGE_SIZE-1]["id"] if len(moves)>PAGE_SIZE else None, {"sku": sku}))
    return shop_ui.page_shell(content)


def order_page(con, query):
    cursor = query.get("before", [""])[0]
    before = stock.identifier(cursor) if cursor else None
    sql = "SELECT o.*,v.name FROM purchase_orders o JOIN stock_vendors v ON v.code=o.vendor"
    if before is None:
        rows = con.execute(sql + " ORDER BY o.id DESC LIMIT ?", (PAGE_SIZE+1,)).fetchall()
    else:
        rows = con.execute(sql + " WHERE o.id<? ORDER BY o.id DESC LIMIT ?", (before, PAGE_SIZE+1)).fetchall()
    orders = [(f'<a href="/purchases/{r["id"]}">PO-{r["id"]}</a>', esc(r["reference"]), esc(r["name"]),
               esc(r["status"])) for r in rows[:PAGE_SIZE]]
    create = form("/purchases/new", control("vendor", "Vendor code") +
                  control("reference", "Purchase order reference (optional)", required=False), "Create draft", request=True)
    return shop_ui.page_shell(section("Purchase orders",
        '<p><a href="/inventory/vendors">Find a vendor code</a></p>' +
        list_table(("Order", "Reference", "Vendor", "Status"), orders) +
        navigation("/purchases", "before", before, rows[PAGE_SIZE-1]["id"] if len(rows)>PAGE_SIZE else None)) +
        section("New purchase order", create))


def order_detail(con, order_id):
    order = stock.lookup(con, """SELECT o.*,v.name FROM purchase_orders o
        JOIN stock_vendors v ON v.code=o.vendor WHERE o.id=?""", (order_id,), "Purchase order")
    lines = con.execute("""SELECT l.*,i.description,i.unit FROM purchase_lines l
        JOIN stock_items i ON i.sku=l.sku WHERE l.order_id=? AND l.voided=0 ORDER BY l.line_no""",
        (order_id,)).fetchall()
    receipts = con.execute("""SELECT r.*,l.line_no,l.sku FROM stock_receipts r
        JOIN purchase_lines l ON l.id=r.line_id WHERE l.order_id=? ORDER BY r.id DESC""", (order_id,)).fetchall()
    url = f"/purchases/{order_id}"
    line_rows = []
    for line in lines:
        remaining = line["ordered"] - line["received"]
        action = ""
        if order["status"] == "draft":
            action = form(url + "/remove-line", hidden("line", line["id"]), "Remove line")
        if order["status"] == "open" and remaining:
            controls = hidden("line", line["id"]) + control("bin", "Bin code") + control(
                "quantity", "Received quantity", "number", "0.000001") + control(
                "reference", "Packing slip (optional)", required=False)
            action = '<details class="inner"><summary>Receive</summary>' + form(
                url + "/receive", controls, "Record receipt", request=True) + "</details>"
        line_rows.append((str(line["line_no"]), esc(line["sku"]), esc(line["unit"]),
                          stock.quantity_label(line["ordered"]), stock.quantity_label(line["received"]),
                          stock.quantity_label(remaining), f'${Decimal(line["unit_cost_cents"])/100:.2f}', action))
    vendor = esc(order["name"])
    reference = esc(order["reference"] or "—")
    meta = (f'<p><a href="/purchases">Back to purchase orders</a> · <a href="/inventory/bins">Find a bin code</a></p>'
            f'<p>{vendor} · Reference {reference} · {esc(order["status"])}</p>')
    content = section(f"Purchase order PO-{order_id}", meta + list_table(
        ("Line", "SKU", "Unit", "Ordered", "Received", "Remaining", "Unit cost", "Actions"), line_rows))
    if order["status"] == "draft":
        add = form(url + "/line", control("sku", "SKU") + control("quantity", "Ordered quantity", "number", "0.000001") +
                   control("cost", "Unit cost ($)", "number", "0.01"), "Add line", request=True)
        content += section("Add order line", '<p><a href="/inventory">Find an item SKU</a></p>' + add +
                           (form(url + "/open", "", "Open order for receiving") if lines else ""))
    if receipts:
        entries = []
        for receipt in receipts:
            if receipt["reversed_at"]:
                correction = "Reversed: " + esc(receipt["reversal_reason"])
            else:
                correction = '<details class="inner"><summary>Reverse receipt</summary>' + form(
                    url + "/reverse", hidden("receipt", receipt["id"]) + control("reason", "Reason"),
                    "Record reversal") + "</details>"
            entries.append((str(receipt["id"]), str(receipt["line_no"]), esc(receipt["bin"]),
                            stock.quantity_label(receipt["quantity"]), esc(receipt["reference"]), correction))
        content += section("Receipt history", list_table(("Receipt", "Line", "Bin", "Quantity", "Packing slip", "Correction"), entries))
    return shop_ui.page_shell(content)
