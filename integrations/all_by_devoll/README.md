# All by Devoll — Friday launch desk

This is a Python-standard-library service-request intake and **operator-only preliminary estimation** console for All by Devoll, LLC. It runs alongside BlueSeer ERP 8.0, with authenticated native customer, quote, service-order and guarded AR/GL invoice adapters. Estimates are internal only; the mechanic calls the customer himself.

## Friday launch path: website email -> ticket desk

The live website `allbydevoll.com` currently sends its service form directly to FormSubmit, which delivers messages to the existing business email inbox. This implementation **does not break or replace that working submission**. The desk periodically checks the business Gmail inbox with IMAP, recognizes email subjects containing "All by Devoll" and "service request", extracts available customer and job fields, deduplicates by Message-ID, assigns an `ABD-000001`-style ticket number, and stores it in SQLite.

If mail import is delayed or Qwen is offline, existing ticket records and manual data entry still work. The business email remains the recipient of the original message.

## Requirements

- Python 3.10+ (no pip dependencies).
- Business Gmail with IMAP access and an **app password** or an authorized IMAP-compatible service credential; your regular Google account password must not be put here. Gmail accounts using Advanced Protection or organizational policies may disallow app passwords. In that case, the IMAP implementation will need OAuth before unattended ingestion is usable.
- A strong local console password.
- Optional: Ollama on the operator machine with `qwen3:4b` for nonbinding diagnostic ideas. The program operates without it.

## Operator installation (Linux / Zorin OS)

From the El Grande clone:

```bash
cd integrations/all_by_devoll
mkdir -p data
export ABD_DASHBOARD_PASSWORD='REPLACE_WITH_A_LONG_UNIQUE_PASSWORD'
export ABD_IMAP_USER='allbydevoll@gmail.com'
export ABD_IMAP_APP_PASSWORD='PASTE_A_GMAIL_APP_PASSWORD_HERE'
python3 desk.py
```

Then on that computer open **http://127.0.0.1:8765**. Your browser asks for Basic authentication: username **operator**, password equal to `ABD_DASHBOARD_PASSWORD`. The app binds to loopback by default; do not expose the unsecured HTTP service directly to the public internet. For remote access, use an authenticated HTTPS reverse proxy or private VPN.

For a quick local trial **without mailbox credentials**, omit `ABD_IMAP_USER` and `ABD_IMAP_APP_PASSWORD` and use the manual ticket form.

Credentials should be stored as OS service secrets or a file outside the repository with restrictive permissions (never commit them).

## Stable local service (systemd user unit example)

Place this in `~/.config/systemd/user/all-by-devoll-desk.service`, adjusting the absolute checkout location and EnvironmentFile:

```ini
[Unit]
Description=All by Devoll email ticket and operator desk
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/el-grande/integrations/all_by_devoll
EnvironmentFile=%h/.config/all-by-devoll/desk.env
ExecStart=/usr/bin/python3 %h/el-grande/integrations/all_by_devoll/desk.py
Restart=on-failure
RestartSec=10
UMask=0077

[Install]
WantedBy=default.target
```

Create `~/.config/all-by-devoll/desk.env` with `ABD_DASHBOARD_PASSWORD=...`, `ABD_IMAP_USER=...` and `ABD_IMAP_APP_PASSWORD=...`; secure it with `chmod 600`. Then run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now all-by-devoll-desk.service
systemctl --user status all-by-devoll-desk.service
```

User services normally run while logged in. To run while logged out, an administrator may configure linger; otherwise keep the machine logged in and online. No server is able to poll Gmail while powered off.

## Accounting and quoting behavior

An editable **operator-only draft estimate** uses:

```
quoted_labor = labor_hours * customer_hourly_rate
quoted_bill = quoted_labor + parts_charged + travel_charged + extras
```

The operator enters verified prices and durations. A separate, optional local Qwen draft offers diagnostic considerations and possible labor-hour ranges but **cannot finalize or set monetary amounts**. Parts acquisition cost is an internal operating cost, not a reduction of Tomey General's share.

After finalization, the operator can mark the invoice as paid. That is a manual operator attestation, not bank verification.

When the operator finalizes the actual customer bill, the desk saves the amount and fixes the settlement:

```
TomeyGeneral = round_to_cents(final_bill * 0.15)
Operator = final_bill - TomeyGeneral
```

**15% is computed on the entire finalized customer bill before any expenses.** The operator's other costs come from their 85%. Finalization is one-way in this launch build: correcting a finalized bill requires a documented follow-up workflow (not silent rewriting). The CSV download contains finalized settlement columns; draft quotes are not recorded as final revenue.

The desk is not a payment processor or general-ledger application. Marking a ticket "invoiced" does not prove payment. The internal allocation should not be presented as an additional charge to the customer.

## What is included and what is not

**Implemented in code:** email-to-ticket intake, permanent local record and status log; operator-only Qwen notes, labor and internal pricing estimates, approved supplier CSV/HTTPS-feed parts catalogue with source dates and searchable SKUs, 15%-off-the-entire-final-bill settlement, native BlueSeer customer/ship-to creation, quotes and service orders, and guarded native shipment-based AR/GL invoicing.

**Not automatically active without deployment configuration:** Gmail mailbox import; access to a running BlueSeer 8.0 server and configured item/account/customer masters; a real supplier-provided feed; or native invoicing. These require external credentials and live qualification. The native invoice path is disabled by default. Marking paid is an operator attestation, not verified bank payment or a BlueSeer AR payment posting. No automated outbound customer quotes or SMS are included, by design.

## Verification

```bash
python3 -m unittest discover -s integrations/all_by_devoll -p 'test_*.py' -v
python3 -m py_compile integrations/all_by_devoll/desk.py
```

Conduct a live, non-customer test submission through the website and verify it arrives in Gmail and as one unique ticket. Re-submit/import to confirm deduplication. Verify finalized bill examples: $350 -> $52.50 parent and $297.50 operator; $1,000 -> $150 parent and $850 operator.

For backups, stop the service or use SQLite's online backup API so that the WAL is included; copy the complete `data` directory to secure storage and test restoration.

## Files

- `desk.py`: standard library ticket service, IMAP importer and desktop dashboard
- `test_desk.py`: unit tests
- `../../.github/workflows/all-by-devoll-desk.yml`: source compilation and test checks

BlueSeer's MIT license remains unchanged. A narrow hardening change to the upstream authServ.java removes raw password and session IDs from login diagnostics.


## Internal-only pricing and supplier configuration

The mechanic sees the preliminary estimate BEFORE he calls the customer. There is deliberately no automatic outbound quote or customer notification. The final bill is separate and its 15%/85% division is fixed by exact-cent arithmetic.

Import an authorized vendor CSV through the supplier catalogue panel. Required columns are: supplier,sku,description,unit_cost. Optional columns: suggested_sale,currency,availability,checked_at,supplier_url. USD is currently supported. Prices are source-stamped, and parts must be selected by exact supplier and SKU; the mechanic still verifies vehicle fitment. Missing supplier data is never made up.

An authorized JSON or CSV HTTPS feed can be configured in the protected systemd EnvironmentFile with these names:

    ABD_PARTS_FEED_URL=https://supplier.example/authorized/prices
    ABD_PARTS_FEED_HOST=supplier.example
    ABD_PARTS_FEED_TOKEN=YOUR_SUPPLIER_TOKEN
    ABD_PARTS_MARKUP_PERCENT=0
    ABD_PARTS_POLL_SECONDS=3600

The example URL is a placeholder, not a live supplier. The feed must return JSON as a list of part objects (or an object with a parts array) or an equivalent CSV. Redirects are refused; TLS is verified.

## BlueSeer 8.0 native API configuration

The bridge calls the existing /bsapi/authServ, dataServCUS, dataServORD, dataServSHP and dataServOV operations, NOT direct database writes. BlueSeer must have its server running and valid items, site, terms and AR accounts configured. Add these to a protected desk.env file (never commit actual credentials):

    ABD_BLUESEER_URL=http://127.0.0.1:8080/bsapi
    ABD_BLUESEER_USER=YOUR_BLUESEER_USER
    ABD_BLUESEER_PASSWORD=YOUR_BLUESEER_PASSWORD
    ABD_BLUESEER_SITE=YOUR_SITE
    ABD_BLUESEER_CURRENCY=USD
    ABD_BLUESEER_TERMS=YOUR_TERMS
    ABD_BLUESEER_AR_ACCOUNT=YOUR_VALID_AR_ACCOUNT
    ABD_BLUESEER_LABOR_ITEM=YOUR_LABOR_ITEM
    ABD_BLUESEER_PARTS_ITEM=YOUR_PARTS_ITEM
    ABD_BLUESEER_TRAVEL_ITEM=YOUR_TRAVEL_ITEM
    ABD_BLUESEER_MISC_ITEM=YOUR_MISC_ITEM
    ABD_BLUESEER_SERVICE_TYPE=order
    ABD_BLUESEER_ENABLE_LIVE_INVOICES=no

Use actual configured BlueSeer codes. For an API on a remote host, the adapter requires HTTPS; loopback HTTP alone is allowed.

### Mechanic's workflow

1. FormSubmit still routes website requests to the business Gmail mailbox. The desk imports messages and assigns permanent ticket IDs. The website remains unchanged.
2. Qwen provides optional diagnostic notes and rough labor ranges; the mechanic selects verified supplier parts, enters labor hours/rate, reviews the INTERNAL estimate and calls the customer to negotiate/confirm the real quote.
3. Click Create/reuse native BlueSeer customer. This posts an actual customer and ship-to record under the configured AR account (or reuses matching local name+phone records).
4. Click Save internal draft to BlueSeer quote and Create BlueSeer service order. Both are real, authenticated native BlueSeer transaction calls; existing records must match customer and line totals.
5. Once the job is done, finalize the ENTIRE customer bill; Tomey General receives 15% of that amount before any parts, labor expense, fuel or other deduction. The operator receives the remaining 85%.
6. After a real test on a disposable BlueSeer instance, set ABD_BLUESEER_ENABLE_LIVE_INVOICES=yes and use the native invoice button. It uses BlueSeer's genuine shipper number, creates shipment rows and executes the existing serviceorder shipper confirmation, which posts AR/GL. It refuses any mismatched final bill and does not automatically retry an uncertain financial action.
7. Paid status can be recorded for internal tracking, but bank confirmation and native AR payment posting remain independent tasks.

Once native quote/service-order records are synchronized, amount-bearing fields are locked in the sidecar against silent divergence. Corrections require native amendment and reconciliation.

## Before production activation

Verify the actual Gmail message format and deduplication, source-stamped vendor price feed, correct BlueSeer site/customer/ship-to and item masters, customer and service order creation, native accounting postings in a test database, invoice reconciliation, restart behavior and backup restoration. No credentials or real supplier rates are bundled in this repository.

## Files added

- parts.py: validated supplier price feed and ticket parts records
- blue_bridge.py: authenticated BlueSeer 8.0 quote and service-order transaction adapter
- customer_bridge.py: native BlueSeer customer and ship-to creation
- invoice_bridge.py: guarded native shipper-to-AR/GL invoicing
- test_integrations.py: supplier, native adapter and accounting mock checks

## Preferred parts suppliers: Detroit Axle and AutoZone

All by Devoll commonly purchases from **Detroit Axle** and **AutoZone**. The internal desk links to their real catalogues and accepts independently source-stamped authorized price feeds for both. Each provider keeps its own supplier/SKU identity; supplier prices are never invented and are never treated as a confirmed vehicle fitment until the mechanic verifies fitment.

**Detroit Axle:** official catalogue https://detroitaxle.com/parts, wholesale enrollment https://detroitaxle.com/wholesale. Its published Terms of Service disallow automated scraping/robots/AI tools accessing its website. Do NOT configure a public storefront scraper. Ask Detroit Axle wholesale support for an approved catalogue export/feed or data-sharing authorization. The code accepts authorized supplier JSON/CSV over HTTPS or operator-imported supplier CSV.

**AutoZone:** AutoZonePro https://www.autozonepro.com/ offers commercial account catalogue access; AutoZone has documented third-party direct API and cXML punchout integrations with commercial partners. Contact the AutoZone commercial account representative for the supported API/punchout integration or authorized catalogue export. Public autozone.com prices are not assumed to be commercial account pricing. The generic HTTPS feed contract can ingest an approved feed that outputs standardized records.

Configure independent authorized supplier feeds in your protected systemd environment file (all sample URLs are PLACEHOLDERS):

    ABD_DETROIT_AXLE_URL=https://approved-detroit-feed.example/api/parts
    ABD_DETROIT_AXLE_HOST=approved-detroit-feed.example
    ABD_DETROIT_AXLE_TOKEN=APPROVED_VENDOR_TOKEN
    ABD_DETROIT_AXLE_SUPPLIER=Detroit Axle

    ABD_AUTOZONE_URL=https://approved-autozone-feed.example/api/parts
    ABD_AUTOZONE_HOST=approved-autozone-feed.example
    ABD_AUTOZONE_TOKEN=APPROVED_COMMERCIAL_TOKEN
    ABD_AUTOZONE_SUPPLIER=AutoZone

The configured URLs must actually exist and be authorized by their suppliers. Their response must match the catalogue JSON/CSV schema described earlier. AutoZone's native direct API and punchout formats, if offered to All by Devoll, may require a separate response-format adapter; do not assume these sample URLs represent a published AutoZone or Detroit Axle API.

The existing ABD_PARTS_FEED_* legacy feed remains supported as a third independent provider. A refresh downloads all configured feeds and validates supplier identity to prevent misattribution. Records retain the source URL and checked-at timestamps. If the source is not connected, the operator can open the supplier catalogue manually, obtain a valid quotation, and import the price using the CSV interface.

The business email connection is **independent** of parts vendors: the website continues emailing allbydevoll@gmail.com via FormSubmit; El Grande watches that mailbox using authorized Gmail IMAP login and saves service requests as tickets. It neither logs into Detroit Axle/AutoZone through Gmail nor automatically sends customer estimates.
