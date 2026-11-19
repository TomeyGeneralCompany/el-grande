"""Shop work orders, separate from customer appointment times."""
from datetime import date
from urllib.parse import urlencode

import shop_ui
import stock
import stock_ui

DDL = """
CREATE TABLE IF NOT EXISTS work_orders (
 id INTEGER PRIMARY KEY,
 reference TEXT NOT NULL UNIQUE,
 ticket_id INTEGER REFERENCES tickets(id),
 sku TEXT REFERENCES stock_items(sku),
 quantity INTEGER NOT NULL CHECK(quantity>0),
 completed INTEGER NOT NULL DEFAULT 0 CHECK(completed>=0 AND completed<=quantity),
 scheduled_quantity INTEGER NOT NULL DEFAULT 0 CHECK(scheduled_quantity>=0 AND scheduled_quantity<=quantity),
 due_on TEXT NOT NULL,
 scheduled_on TEXT NOT NULL,
 notes TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('open','complete','cancelled'))
);
"""


def day(value):
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("Enter a valid work order date.") from None


def save(con, data):
    reference = stock.text(data.get("reference", ""), "work order reference")
    ticket = stock.identifier(data["ticket"]) if data.get("ticket") else None
    sku = stock.text(data.get("sku", ""), "SKU", required=False) or None
    if ticket:
        stock.lookup(con, "SELECT id FROM tickets WHERE id=?", (ticket,), "Ticket")
    if sku:
        stock.lookup(con, "SELECT sku FROM stock_items WHERE sku=?", (sku,), "Item")
    quantity = stock.qty(data.get("quantity", ""))
    completed = stock.number(data.get("completed") or "0", stock.QTY_SCALE, quantity, "completed quantity")
    scheduled = stock.number(data.get("scheduled_quantity") or "0", stock.QTY_SCALE, quantity, "scheduled quantity")
    status = data.get("status", "open")
    if status not in ("open", "complete", "cancelled") or (status == "complete" and completed != quantity):
        raise ValueError("A completed order must have its entire quantity completed.")
    con.execute("""INSERT INTO work_orders(reference,ticket_id,sku,quantity,completed,scheduled_quantity,due_on,scheduled_on,notes,status)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(reference) DO UPDATE SET
        ticket_id=excluded.ticket_id,sku=excluded.sku,quantity=excluded.quantity,completed=excluded.completed,
        scheduled_quantity=excluded.scheduled_quantity,due_on=excluded.due_on,
        scheduled_on=excluded.scheduled_on,notes=excluded.notes,status=excluded.status""",
        (reference, ticket, sku, quantity, completed, scheduled, day(data.get("due_on", "")),
         day(data.get("scheduled_on", "")), stock.text(data.get("notes", ""), "notes", 300, False), status))


def page(con, query):
    cursor = query.get("before", [""])[0]
    before = stock.identifier(cursor) if cursor else None
    size = stock_ui.PAGE_SIZE
    if before:
        rows = con.execute("SELECT * FROM work_orders WHERE id<? ORDER BY id DESC LIMIT ?", (before,size+1)).fetchall()
    else:
        rows = con.execute("SELECT * FROM work_orders ORDER BY id DESC LIMIT ?", (size+1,)).fetchall()
    reference = stock.text(query.get("reference", [""])[0], "work order reference", required=False)
    selected = con.execute("SELECT * FROM work_orders WHERE reference=?", (reference,)).fetchone()
    esc = shop_ui.esc
    table = stock_ui.list_table(("Order","Ticket","SKU","Planned","Completed","Scheduled quantity","Scheduled date","Due","Status"), [
        (f'<a href="/work-orders?{esc(urlencode({"reference": r["reference"]}))}#edit-work">{esc(r["reference"])}</a>',
         f'<a href="/ticket/{r["ticket_id"]}">ABD-{r["ticket_id"]:06d}</a>' if r["ticket_id"] else "—",
         esc(r["sku"] or "—"), stock.quantity_label(r["quantity"]), stock.quantity_label(r["completed"]),
         stock.quantity_label(r["scheduled_quantity"]), esc(r["scheduled_on"]), esc(r["due_on"]), esc(r["status"])) for r in rows[:size]
    ])
    table += stock_ui.navigation("/work-orders", "before", before, rows[size-1]["id"] if len(rows)>size else None)
    fields = []
    for name,label,kind,default in (
        ("reference","Work order reference","text",""), ("ticket_id","Ticket number (optional)","number",""),
        ("sku","SKU (optional)","text",""), ("quantity","Planned quantity","number","1"),
        ("completed","Completed quantity","number","0"),
        ("scheduled_quantity","Scheduled quantity","number","0"), ("scheduled_on","Scheduled date","date",""),
        ("due_on","Due date","date",""), ("notes","Notes","text",""),
    ):
        value = selected[name] if selected is not None and selected[name] is not None else default
        if selected is not None and name in ("quantity","completed","scheduled_quantity"):
            value = stock.quantity_label(selected[name])
        fields.append(shop_ui.field("ticket" if name=="ticket_id" else name,label,value,kind,
                                    required=name in ("reference","quantity"),
                                    step="0.000001" if name in ("quantity","completed","scheduled_quantity") else None))
    status = selected["status"] if selected is not None else "open"
    options = "".join(f'<option value="{x}"{" selected" if x==status else ""}>{x.title()}</option>'
                      for x in ("open","complete","cancelled"))
    form = stock_ui.form("/work-orders/save","".join(fields)+f'<label>Status<select name="status">{options}</select></label>',
                         "Save work order")
    return shop_ui.page_shell(stock_ui.section("Work orders", table) +
        '<section class="panel" id="edit-work"><h2>' + ("Edit work order" if selected else "New work order") + "</h2>" +
        form + "</section>")
