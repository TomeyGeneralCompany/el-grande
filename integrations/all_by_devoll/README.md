# All by Devoll shop desk

The Python desk serves the job, calendar, work order, inventory, purchasing, receiving, invoice, payment, and cashbook pages. The installer starts it as a systemd user service. For development, install `reportlab` and run `python3 integrations/all_by_devoll/desk.py` with `ABD_DB` set to a disposable SQLite path.

`desk.py` owns the existing job and HTTP flows. `stock.py` and `work_orders.py` manage local purchasing, receipts, movements and work orders. `legacy_import.py` imports the old operational data once and archives historical transaction rows. See the [installer README](../../packaging/README.md) for upgrade and verification details.
