# El Grande

El Grande is the local shop desk for All by Devoll. Use it for job tickets, customer appointments, work orders, stock, purchase orders, receiving, PDF invoices, payments, and the cashbook. The desk runs in Python and stores shop records in one SQLite database.

Install the Zorin/Debian package and open **El Grande — All by Devoll** from the app menu. The desk binds to `127.0.0.1:8765` by default. Optional email intake, owner reports, bank feeds, and Ollama estimates are configured separately in the shop settings or environment.

## Existing installations

The first standalone launch stops the old ERP service before starting the new desk. It reads the former installed BlueSeer SQLite database, imports operational inventory, orders and work orders, and preserves historical transaction and accounting rows in the shop database. The import is transactional and runs once. The old database file, shop tickets, payments, and saved PDFs are preserved.

See [installer and upgrade details](packaging/README.md) for paths and the read-only comparison command.

## Test and package

```bash
python3 -m unittest discover -s integrations/all_by_devoll -p 'test_*.py'
bash packaging/build-deb.sh
bash packaging/smoke-standalone.sh
```

The previous Java implementation and its build are available through repository history. See [NOTICES](NOTICES) for the inherited notice.
