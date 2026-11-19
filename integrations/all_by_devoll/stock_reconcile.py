"""Compare copied BlueSeer and El Grande stock databases without writing.

Exit 0 if quantities agree, 1 if mismatches exist, or 2 if a copy is unreadable.
"""
import argparse
from collections import defaultdict
from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3

from stock import QTY_SCALE


def read_copy(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def decimal_quantity(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("A source quantity is missing or non-finite.")
    return number


def balances(source):
    quantities = defaultdict(Decimal)
    for item, site, warehouse, location, quantity in source.execute(
        "SELECT in_item,in_site,in_wh,in_loc,in_qoh FROM in_mstr"
    ):
        quantities[(item, site or "", warehouse or "", location or "")] += decimal_quantity(quantity)
    return quantities


def open_lines(source):
    quantities = {}
    for reference, line, item, ordered, received in source.execute("""SELECT
        l.pod_nbr,l.pod_line,l.pod_item,l.pod_ord_qty,l.pod_rcvd_qty
        FROM pod_mstr l JOIN po_mstr o ON o.po_nbr=l.pod_nbr
        WHERE LOWER(TRIM(COALESCE(o.po_status,''))) NOT IN ('closed','cancelled','canceled','void')
          AND LOWER(TRIM(COALESCE(l.pod_status,''))) NOT IN ('closed','cancelled','canceled','void')"""):
        identity = (str(reference), int(line), item)
        if identity in quantities:
            raise ValueError(f"Duplicate BlueSeer purchase order line {reference}/{line}.")
        quantities[identity] = max(Decimal(0), decimal_quantity(ordered) - decimal_quantity(received or 0))
    return quantities


def differences(source, local, names):
    rows = []
    for identity in sorted(source.keys() | local.keys()):
        original, current = source.get(identity, Decimal(0)), local.get(identity, Decimal(0))
        if original != current:
            rows.append({**dict(zip(names, identity)), "blueseer": format(original, "f"),
                         "el_grande": format(current, "f")})
    return rows


def compare(source, local):
    source_stock = balances(source)
    local_stock = {
        (item, site, warehouse, location): Decimal(qty) / QTY_SCALE
        for item, site, warehouse, location, qty in local.execute("""SELECT
            s.sku,b.site,b.warehouse,b.location,s.quantity
            FROM stock_balances s JOIN stock_bins b ON b.code=s.bin""")
    }
    source_lines = open_lines(source)
    local_lines = {
        (reference, line, item): Decimal(qty) / QTY_SCALE
        for reference, line, item, qty in local.execute("""SELECT
            COALESCE(NULLIF(o.reference,''),'PO-'||o.id),l.line_no,l.sku,l.ordered-l.received
            FROM purchase_orders o JOIN purchase_lines l ON l.order_id=o.id
            WHERE o.status='open' AND l.voided=0 AND l.ordered>l.received""")
    }
    return {
        "stock_differences": differences(source_stock, local_stock, ("sku", "site", "warehouse", "location")),
        "open_order_differences": differences(source_lines, local_lines, ("order", "line", "sku")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueseer_copy")
    parser.add_argument("el_grande_copy")
    args = parser.parse_args()
    try:
        with closing(read_copy(args.blueseer_copy)) as source, closing(read_copy(args.el_grande_copy)) as local:
            source.execute("BEGIN")
            local.execute("BEGIN")
            report = compare(source, local)
    except (sqlite3.Error, ValueError, TypeError, InvalidOperation) as err:
        parser.exit(2, f"Unable to reconcile database copies: {err}\n")
    print(json.dumps(report, indent=2))
    return int(any(report.values()))


if __name__ == "__main__":
    raise SystemExit(main())
