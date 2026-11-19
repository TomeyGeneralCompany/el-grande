# El Grande for Zorin OS — desktop installer

**Mechanic experience:** download the installer, double-click the downloaded `.deb` file in Files, approve installation in the graphical package installer, open **El Grande — All by Devoll** from the app menu, and complete the short first-run wizard. No terminal and **no dashboard password**.

## What is installed

- Python operator dashboard under `/opt/el-grande/integrations/all_by_devoll`.
- Java BlueSeer ERP application classes and dependencies under `/opt/el-grande/java`.
- Local BlueSeer SQLite seed database under `/opt/el-grande/java/data-template`. First-run setup copies it into `~/.local/share/el-grande/blueseer/data` and writes a local configuration.
- User-owned ticket database at `~/.local/share/el-grande/data/tickets.sqlite3`. It is **not** stored in the read-only package directory, and updates should not overwrite it.
- User-owned protected email settings in `~/.config/el-grande/desk.env`.
- Desktop app launcher and separate **El Grande Setup** icon.
- Background user services `el-grande-desk.service` and `el-grande-api.service`, running on the local machine. BlueSeer's HTTP API listens only on 127.0.0.1:8088; the dashboard listens only on 127.0.0.1:8765.

No rented server, web hosting or separate office computer is needed. User service starts automatically when the local user logs in; keep the office machine logged in for unattended mailbox checks. For unattended operation even when logged out, configure systemd user linger later through admin settings.

## No password prompt

The dashboard opens at http://127.0.0.1:8765 without a login, but accepts connections **only on the local computer**. Nonlocal binding is refused without a configured dashboard password. This is designed for one trusted office workstation. The operator should use the workstation's normal Linux login and screen lock.

The wizard does not request an El Grande dashboard password. You only need the business Gmail **app password** if you want automatic ticket import and owner emails. That Google credential is separate from El Grande and remains local. You can leave it blank to demo the dashboard.

The reporting destination defaults to `isaiztomey7@gmail.com`, and can be changed later through **El Grande Setup**.

## Installer download

In this repository, open **Actions → El Grande Zorin installer**, choose the latest successful run and download the **el-grande-zorin-deb** artifact. Unzip it with the Files graphical archive manager; double-click `el-grande_0.4.0_all.deb` to install through Zorin's graphical software installer. The software installer may ask for the *computer administrator's password* to install system packages — this is different from an application login and is managed by Zorin.

Once installed, use the El Grande desktop entry; the first launch shows the setup wizard, and later launches go straight to the dashboard.

## Test before live business use

1. Start with business Gmail credential blank. Open the dashboard through the app menu; confirm it shows **no username or password prompt**.
2. Create a manual test ticket; review internal estimating, parts lookup, and mark the job complete. Confirm the 15% settlement and operator's 85%.
3. Enter the business Gmail app password in **El Grande Setup** (not chat), submit a test request on the website, and confirm it creates one ticket.
4. Complete a synthetic test job, verify the email report arrives in the owner's Gmail, and check the job's report status as sent.
5. Validate BlueSeer's API, account codes, service items and AR/GL mapping on test data. **Native financial posting remains disabled by default** until the accounting tests pass.

The Java ERP runtime is bundled to avoid an additional manual install, but its business chart of accounts, customer masters, service item codes and payment settings still need company-specific configuration. A fresh example SQLite database is **not a finished production accounting setup**. No real invoices should be posted until those master records and reconciliation have been qualified.

## For developers

CI packages the .deb with `packaging/build-java.sh` and `packaging/build-deb.sh`. CI performs Python checks and Java compilation before uploading an artifact. Runtime dependencies are installed automatically by the graphical package manager. The standalone Python desk remains usable even if the BlueSeer accounting setup has not been completed.

The legacy `all-by-devoll-desk.service` from the earlier checkout is stopped during graphical first-run setup so it cannot occupy the same local port. The wizard uses SQLite's online backup API to migrate the earlier developer checkout database if present and leaves the original copy untouched.


## El Grande 0.2.0: shop-facing interface and live connection setup

This upgrade replaces the first-version wall of forms and internal settlement banners with a clean All by Devoll shop workspace. The main screen has open/new/active/completed job counts and a job list. Opening a job shows its estimate, labor, parts lookup, work completion, and native ERP actions. Accounting-specific codes remain within expandable job details, while Tomey General's 15% allocation remains calculated in the backend and included in owner reporting rather than shown to the mechanic as shop branding.

**Upgrade existing installation:** download the newest successful 0.2.0 artifact from Actions, extract it, and install through Zorin's software manager. The package version is incremented, so it upgrades existing 0.1.0 without erasing ticket records or configuration in the home directory. On the next browser refresh, the new shop interface is served.

Open **El Grande Setup** in Zorin's applications menu to configure the actual connections:

1. **Office & Email** tab: enter the business Gmail app password and click **Test business Gmail connection**. This uses a real Gmail login, without sending messages or changing the mailbox. Save settings to restart the job desk service, activating website email intake and completed-job owner reports.
2. **ERP Connection** tab: click **Check local ERP service** to check the installed Java API. Enter the BlueSeer login and click **Test BlueSeer login**. A successful test establishes authentication, not that the accounting master data are ready.
3. **Accounting Codes** tab: enter the business-specific site, receivables account, terms, labor service item, parts service item, and optional travel item. Confirm these against the installed BlueSeer business database before native postings.
4. **Save settings & Open Job Desk** restarts the local service so the updated settings take effect.

A missing or unconfigured ERP is shown as such in the shop's **Office connections** panel. The app does not claim financial posting is ready merely because the API port responds. Native invoice posting remains disabled until real accounting validation is complete.

The user does not need to create or remember an El Grande dashboard password. No customer-facing quotes are sent automatically.


## El Grande 0.3 — One application, one settings page

The mechanic's shop dashboard does not contain connection warnings, internal technical instructions, or parent-company settlement banners. The sole **Settings** navigation link opens the email connection within the same local El Grande browser app.

On the first launch after installing version 0.3, El Grande creates the local ticket database, creates/retains the bundled BlueSeer SQLite working database, registers and starts its local BlueSeer Java API and opens the shop directly. There is no separate BlueSeer installer and no requirement to use the deprecated setup desktop icon. The system automatically preserves the existing environment and job records on a package upgrade.

Email setup is intentionally minimal: **Settings → Business email** has the shop Gmail address, the parent's report destination (pre-filled), and one credential field with a direct link to Google's app-password page. After that credential has been authorized by Google and saved, the desk's mail reader and report sender work without a separate terminal process or restart. The **Test Gmail connection** button checks the live business mailbox login.

Local BlueSeer processes and SQLite runtime are installed together and brought up automatically. A running BlueSeer API does **not** by itself prove that business-specific AR codes, items, and account permissions are valid. Native invoice/GL posting remains disabled until those records have been verified. Ordinary job tickets and final bills continue to work locally without that step; do not represent them as reconciled BlueSeer journal entries.

The old graphical setup application remains in the package as a backward-compatibility script path only. The default installation exposes only one El Grande app icon.


## El Grande 0.4.0: actual native BlueSeer connection on install

The same app launcher prepares the bundled SQLite database, starts the local Java BlueSeer API, verifies BlueSeer user login and loopback access, and provisions native service-item records for labor, parts, travel and other charges. It uses the BlueSeer authenticated APIs for business master records, not a mock or a second disconnected database.

The original upstream sample ERP database may contain an unencoded default admin password that the Java API cannot authenticate. For this untouched seed only, the bootstrap generates an internal random credential, transforms it using the upstream password storage routine, saves the generated credential to the user's protected settings file, and allows only 127.0.0.1 in the seeded account's IP permission records. Existing changed passwords and customized business records are not overwritten. If the seeded company is still labeled "MFG Company", the native site update API changes it to "All by Devoll" (Manistee, MI); modified business names are preserved.

The native BlueSeer quote and service-order identifiers are deterministic numeric values in the reserved range `900000000 + ticket_id`. That is necessary because native BlueSeer getters parse those fields as integers; string job IDs are unsuitable and caused the previous integration to silently fail read-backs.

On a completed job **after the ERP connector is initialized**, El Grande queues native customer creation/verification and a native service order in the background. The existing job record, completed-work details, owner report and 15% calculation are retained even if BlueSeer temporarily fails. Deterministic IDs, read-back verification and retries prevent duplicate creation. The job's expanded completed record shows its current BlueSeer sync state. An actual final bill different from the estimate is flagged for reconciliation rather than creating a mismatched native order.

The integration build checks **a real BlueSeer Java server backed by a disposable copy of the bundled SQLite database**, completing native login, item master creation, business-site setup, customer creation, quote and service-order creation, native read-back idempotency, and a test AR/GL invoice. The disposable invoice test does not post a production transaction. Live production AR/GL posting stays disabled until the company's tax, chart of accounts and invoice settings have been confirmed.

Upgrading to 0.4.0 preserves the existing local ticket and BlueSeer databases. No email credentials are needed to run the native ERP integration. Gmail remains optional.


## El Grande 0.5.0 — invoice posting is enabled, not disabled

A finalized customer job with a nonzero bill now enters the durable BlueSeer work queue even when the ERP is temporarily unavailable. After the connector authenticates, it creates/verifies the customer, creates/verifies the native service order for the **final customer bill**, reserves a BlueSeer shipper/invoice ID, and posts/validates the native AR/GL invoice. The actual customer bill is authoritative even when it differs from an earlier internal estimate. Completion labor/parts figures are costs, not substitute customer sale prices; the full final bill is posted as one completed-service charge so the invoiced amount is never an invented breakdown.

The installer configures `ABD_BLUESEER_ENABLE_LIVE_INVOICES=yes`, and native invoicing does not depend on a hidden disable flag. Each job's native invoice ID and state are recorded in `blue_sync`; an ambiguous response marks the invoice for reconciliation rather than blindly replaying the charge. Gmail authorization remains optional. Existing completed records are not retroactively sent to financial ledgers without explicit handling.

**Gross allocation is off the top:** Tomey General is entitled to 15% of the full customer invoice before any operating costs. The operator's 85% bears their expenses. The 15% allocation is tracked in job calculations/reports and is not a customer discount or a 15% reduction of invoice revenue. Native AR/GL invoicing is not itself a bank transfer to the parent.

Production tax-code configuration remains an independent accounting matter; posting an invoice with no tax code is not proof of the proper sales tax treatment. Operators should set applicable tax rules in the accounting system; this release does not fabricate rates or claim that tax configuration was verified.


## El Grande 0.6.0 — cash-first payments, not a card checkout

The mechanic enters the **actual final customer bill**, with no separate tax line added by El Grande (tax-inclusive customer-price assumption). Parts need not be sold as separate checkout items. Whether and how the business owes sales tax is a separate tax compliance determination, not something the software assumes away.

At job completion, the mechanic may optionally record cash collected at the job. Otherwise, the customer payment panel stays available on each completed job, defaulting to **cash**. Payment method options: cash, check, card, bank transfer, or other. He can record a partial payment or multiple subsequent installments, select the date money was received, and optionally add the check/transaction reference. For cash, the amount physically handed over may exceed the remaining balance: El Grande records **only the amount owed as revenue collected** and the excess as change returned. The dashboard calculates received versus unpaid amounts from an append-only local ledger and shows a job as paid **only when all recorded applied payments cover the final invoice**.

Mistakes are corrected by voiding an entry with a required reason, never deleting or silently editing the payment history. The **Export payments** CSV includes payment date, method, tendered amount, applied amount, change, recorded timestamp, and any void correction. Cash receipts are **operator attestations**, not proof of a bank deposit or processor settlement.

**Important BlueSeer boundary:** Native invoices and AR/GL charges are already posted by El Grande. Version 0.6 records customer collections in its protected local payment ledger, but does *not* automatically post BlueSeer AR cash-receipt or bank-deposit entries. Do not represent BlueSeer open-AR balances as paid from the local ledger alone. Native receipt allocation and undeposited-cash bookkeeping require their own reconciled transaction workflow. This release neither invents a bank deposit nor misclassifies cash in hand as funds deposited at a bank.

Tomey General remains owed **15% of the full finalized customer bill before all operator expenses**, not 15% after parts or other costs, and not 15% of cash received so far. The operator bears expenses from their other 85%; this payment workflow does not automatically transfer either party's money.


## El Grande 0.7.0 — print invoice, then mark paid

The ordinary mechanic workflow is **Finish Job & Create Invoice → View / print PDF invoice → Mark Paid**. Completing a job requires a brief description of the work and the *actual final customer price*. Time and detailed operator expenses are optional inputs, hidden under an expanded section. A job may be completed and invoiced even before the customer pays.

On completion, a customer-facing letter-sized PDF is generated under the user's private local \`~/.local/share/el-grande/invoices/ABD-XXXXXX.pdf\` folder, with mode 0600. The dashboard's PDF link opens or prints the same saved invoice. Previously finalized jobs can generate their PDF on the first request without changing the original final amount. PDFs show the business, customer, vehicle or job, work performed, invoice number, date, and agreed full bill. They **never show Tomey General's private 15% allocation, the operator's costs, ERP account numbers, or passwords**. A PDF invoice is immutable once generated, including after payment.

After the mechanic **actually receives** the customer's money, **Mark Paid** records a receipt for the remaining outstanding amount, using cash and today's date as defaults. A fully paid job visibly shows Paid and cannot be charged twice through this button. For checks, other methods, partial payments, change, and corrections, the existing detailed payment ledger remains available under a collapsed section; its audit trail and exports remain intact.

This feature requires no printer connection, internet, Gmail, card processor, or manually launched BlueSeer screen. The Debian package depends on \`python3-reportlab\` to generate the PDF locally. BlueSeer service invoice posting continues as a separate accounting action; a dashboard paid indicator is an operator-recorded receipt, **not proof of a bank deposit nor an automatically applied native BlueSeer AR payment**. No separate sales-tax line is added to the agreed customer invoice, per the current provisional billing assumption.


## El Grande 0.8.0 — payments also settle the native BlueSeer invoice

This release completes the outstanding integration. The mechanic records each customer payment **once** using the existing **Mark Paid** button or manual partial-payment form. El Grande's local payment ledger immediately updates the customer/job record and automatically queues a native BlueSeer AR payment against the precise invoice created for that job. As soon as the corresponding native invoice is confirmed, the background worker calls BlueSeer's native AR payment transaction; BlueSeer updates the invoice's open accounts-receivable amount and posts its corresponding general-ledger entry.

The same workflow applies to cash, checks, card payments, and partial receipts. Payment date, applied amount, invoice and customer are linked. Corrected/voided receipts generate the corresponding native reversal when the original payment had already posted. Payments voided before posting are cancelled instead. Receipt and reversal transactions use deterministic IDs and are never blindly sent a second time after an uncertain response; BlueSeer native read-back confirms the exact amount and invoice before a transaction is marked reconciled.

Previously recorded payments are queued on upgrade. The sync runs on the same local BlueSeer service and does not require Gmail, a card processor, a second app, or any additional operator account setup. The full invoice is unchanged by the payment, and Tomey General's 15% remains **off the top of the original final customer bill**, prior to operator expenses. This 0.8 implementation **supersedes** the former 0.6/0.7 limitation described above: native AR receipts are now integrated and processed automatically.

The test suite includes native Java API and SQLite integration with an actual posted service invoice, an applied partial cash receipt, a reversal, an applied full receipt, and checks that BlueSeer reports the correct outstanding amount after each operation.


## El Grande 0.9.0 — clickable connection setup in Settings

The mechanic opens the El Grande desk icon and uses **Settings** from the ordinary browser dashboard. **Add Gmail connection** expands an in-app Gmail address, owner notification address and app-password form, with Save and Test actions. Gmail remains optional. The app-password value is not echoed back into the web page.

**Add bank account** expands a bank name, account nickname, masked last-four digits and advanced existing BlueSeer bank-ledger code. Save validates that ledger code against the local BlueSeer API when connected and updates the existing protected office settings without a terminal or separate setup application. Bank account and Gmail details can be edited individually without erasing the other settings. This is manual accounting bank identification; it does not ask for full bank account numbers, routing numbers, online bank login credentials, or initiate bank transfers.

The forms use ordinary local HTTP dashboard functionality, avoiding Linux shell interaction during routine use and retaining an interface that can be reused in a later **native Windows** port. This release itself is still a Zorin/Ubuntu package and does not include a native Windows installer.


## El Grande 0.10.0 — full cash/bank register and bank connection

Open **Money & banks** in El Grande's browser dashboard. The module works offline and provides an auditable register of cash received, money spent, withdrawals, deposits and transfers with running balances and dated transaction history. The default register accounts are **Cash** and **Business bank**; additional bank register accounts can be added from the screen. Customer payments already recorded in El Grande are migrated into the register exactly once, and subsequent payment entries/voids produce corresponding register entries automatically. Cash receipts are recorded into the cash account; cash-to-bank deposits are paired transactions on the same date, so the overall register does not invent extra income when the cash is deposited. Changing the customer bill or parent allocation is not part of this feature.

**Live bank connection:** Settings -> Connect to your bank allows entering the application's Plaid developer client ID, secret and environment through protected browser forms. These app developer credentials are not the customer's bank password. Once configured, Money & banks -> Connect another bank launches Plaid Link, where the institution and its actual authentication flow are provided by Plaid. El Grande exchanges the authorized public token on the local server, stores the persistent access token in a local owner-readable 0600 credential file, and displays bank-reported balances. **Refresh bank balances & activity** obtains balance updates and imported bank transactions, which may be matched to an existing register entry or recorded as a new register entry once. All received transactions are deduplicated by provider ID.

This uses Plaid's **Transactions/read-only** authorization; availability depends on the financial institution and the user's Plaid developer account/product permissions. Production credentials are needed for real bank data. Plaid Transfer is a separately approved service; **this release cannot electronically initiate ACH transfers or physically deposit currency at a bank.** The user-requested cash deposit register is implemented without needing that permission: transfer cash from Cash to the bank register and it records both sides of the movement. A bank balance is always labeled as bank-reported, separate from the manually entered running register when the two have not yet been matched.

**No terminal required for routine operation or bank linking.** The web-based Settings, register and Plaid Link screens can be reused in a Windows-native version later. El Grande 0.10.0 remains a Zorin/Ubuntu installer; it is not a Windows executable.
