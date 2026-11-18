# All by Devoll — Friday launch desk

This is a self-contained, Python-standard-library service-request intake and operator quote console for **All by Devoll, LLC**, housed in the El Grande repository. It runs **alongside** BlueSeer ERP 8.0; it does not change BlueSeer's upstream database schema or pretend to have posted BlueSeer invoices.

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

An editable draft quote uses:

```quoted_labor = labor_hours * customer_hourly_rate
quoted_bill = quoted_labor + parts_charged + travel_charged + extras
```

The operator enters verified prices and durations. A separate, optional local Qwen draft offers diagnostic considerations and possible labor-hour ranges but **cannot finalize or set monetary amounts**. Parts acquisition cost is an internal operating cost, not a reduction of Tomey General's share.

When the operator finalizes the actual customer bill, the desk saves the amount and fixes the settlement:

```TomeyGeneral = round_to_cents(final_bill * 0.15)
Operator = final_bill - TomeyGeneral
```

**15% is computed on the entire finalized customer bill before any expenses.** The operator's other costs come from their 85%. Finalization is one-way in this launch build: correcting a finalized bill requires a documented follow-up workflow (not silent rewriting). The CSV download contains finalized settlement columns; draft quotes are not recorded as final revenue.

The desk is not a payment processor or general-ledger application. Marking a ticket "invoiced" does not prove payment. The internal allocation should not be presented as an additional charge to the customer.

## What is included and what is not

**Included:** persistent tickets, IMAP mailbox polling, email parsing and deduplication, telephone/walk-in ticket creation, status log, manual labor/parts/travel estimates, optional Qwen diagnostic draft, finalized bill lock, 15% off-the-top settlements, operator share, CSV export, basic password authentication, local-only default bind, test suite.

**Not included yet:** automatic posting of service-order and quote records into BlueSeer's `ordData` schema, inventory/parts supplier lookups, payment capture, self-hosted website ticket endpoint, and customer email or SMS quoting. The existing BlueSeer service-order functions `addServiceOrderTransaction` and `addQuoteTransaction` have been inspected, but their object mappings and authentication must be qualified before live postings. This desk is the immediately deployable ticket/quoting intake that supplies reliable data for that next adapter.

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

BlueSeer upstream code and its MIT license remain unchanged.
