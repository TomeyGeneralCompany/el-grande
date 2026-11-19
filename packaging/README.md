# El Grande 0.14.0 installer

Run `bash packaging/build-deb.sh` to build `artifacts/el-grande_0.14.0_all.deb`. The package installs the Python job desk and one systemd user service. It requires Python 3.10 or later, Tk for launcher messages, and ReportLab for PDF invoices. Run `bash packaging/smoke-standalone.sh` to exercise the extracted package.

## Existing installations

The desk opens the existing database at `~/.local/share/el-grande/data/tickets.sqlite3` by default. Use SQLite’s backup command or API to create a consistent backup of a database in WAL mode. Use **Export receipts** under Purchase orders for the receipt cost and reversal history.
