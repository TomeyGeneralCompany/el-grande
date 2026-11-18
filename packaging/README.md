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

In this repository, open **Actions → El Grande Zorin installer**, choose the latest successful run and download the **el-grande-zorin-deb** artifact. Unzip it with the Files graphical archive manager; double-click `el-grande_0.2.0_all.deb` to install through Zorin's graphical software installer. The software installer may ask for the *computer administrator's password* to install system packages — this is different from an application login and is managed by Zorin.

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
