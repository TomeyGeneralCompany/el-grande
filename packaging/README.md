# El Grande 0.14.0 installer

Run `bash packaging/build-deb.sh` to build `artifacts/el-grande_0.14.0_all.deb`. The package installs the Python job desk and one systemd user service. It requires Python 3.10 or later, Tk for launcher messages, and ReportLab for PDF invoices. Run `bash packaging/smoke-standalone.sh` to exercise the extracted package.

## Upgrade

The launcher stops the prior ERP services and restarts the shop desk. The desk opens `~/.local/share/el-grande/data/tickets.sqlite3` and imports the old installed SQLite source from `~/.local/share/el-grande/blueseer/data/en/bsdb.db` if present. Set `ABD_LEGACY_DB` in the desk's environment file only if the original SQLite source is elsewhere. The import changes only the local shop database. The original file is available for rollback or independent review.

The import preserves original stock by SKU/site/warehouse/location, eligible PO lines and received quantities, and work order quantities and dates. Historical purchasing, receipt, customer, billing, and posting records are available as CSV through Settings. Closed orders with unreceived quantities and other historical records remain in the archive. Legacy invoices and posting queues are never replayed. The desk uses its existing ticket, payment and cashbook records for current billing. Use **Export receipts** under Purchase orders for the local receipt cost and reversal history.

If local and old stock counts disagree for the same item and location, or an order reference has conflicting lines, startup logs identify the conflict and the import rolls back. Compare database copies before correcting the records:

```bash
python3 /opt/el-grande/integrations/all_by_devoll/stock_reconcile.py blueseer-copy.db el-grande-copy.sqlite3
```

Use SQLite's backup command or API to create consistent copies of a database in WAL mode.
