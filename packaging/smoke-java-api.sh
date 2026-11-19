#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
mkdir -p build/smoke-java
cp -a sf/data build/smoke-java/data
cp scripts/bs.cfg.sqlite.linux build/smoke-java/bs.cfg
(
 cd build/smoke-java
 java -Djava.awt.headless=true -cp "$ROOT/build/java-classes:$ROOT/lib/*" utilities.apiServer -config bs.cfg -port 18088 >java-api.log 2>&1 &
 echo $! >java-api.pid
)
pid="$(cat build/smoke-java/java-api.pid)"
trap 'kill "$pid" 2>/dev/null || true' EXIT
success=0
for _ in $(seq 1 30); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "BlueSeer API exited unexpectedly"
    tail -100 build/smoke-java/java-api.log
    exit 1
  fi
  status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:18088/bsapi/authServ || true)"
  if [ "$status" = "401" ]; then success=1; break; fi
  sleep 1
done
if [ "$success" -ne 1 ]; then
  echo "BlueSeer local API did not respond as expected"
  tail -100 build/smoke-java/java-api.log
  exit 1
fi
echo "BlueSeer local ERP API responded on loopback (expected 401 for unauthenticated GET)."
# Exercise the actual packaged Java API and seed SQLite database, not a mock.
# The test uses an isolated copy and never posts an invoice or touches live data.
mkdir -p "$ROOT/build/smoke-java/xdg"
ABD_BOOTSTRAP_DB="$ROOT/build/smoke-java/data/en/bsdb.db" \
ABD_BOOTSTRAP_ENV="$ROOT/build/smoke-java/desk.env" \
ABD_BLUESEER_URL="http://127.0.0.1:18088/bsapi" \
PYTHONPATH="$ROOT/integrations/all_by_devoll" \
python3 "$ROOT/integrations/all_by_devoll/erp_bootstrap.py" || {
  echo "BlueSeer native auth failed; printing bytecode signatures for debugging."
  javap -c -p -classpath "$ROOT/lib/bsmf.jar" bsmf.MainFrame |
    sed -n '/confirmServerLogin(/,/^  public static /p' | head -160 || true
  tail -70 "$ROOT/build/smoke-java/java-api.log"
  exit 1
}

