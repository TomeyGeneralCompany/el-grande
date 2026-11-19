# El Grande

El Grande is the local shop desk for All by Devoll. Use it for job tickets, customer appointments, work orders, stock, purchase orders, receiving, PDF invoices, payments, and the cashbook. The desk runs in Python and stores shop records in one SQLite database.

Install the Zorin/Debian package and open **El Grande — All by Devoll** from the app menu. The desk binds to `127.0.0.1:8765` by default. Optional email intake, owner reports, bank feeds, and Ollama estimates are configured separately in the shop settings or environment.

## Existing installations

The installer uses the existing El Grande database for shop records. See the [installer details](packaging/README.md) for the database path and backup guidance.

## Test and package

```bash
python3 -m unittest discover -s integrations/all_by_devoll -p 'test_*.py'
bash packaging/build-deb.sh
bash packaging/smoke-standalone.sh
```

## License

El Grande is proprietary to Tomey General Company, LLC. See the [copyright notice](LICENSE).
