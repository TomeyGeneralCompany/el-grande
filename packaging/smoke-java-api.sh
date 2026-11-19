#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
package="${1:-$ROOT/artifacts/el-grande_0.13.0_all.deb}"
mkdir -p build/smoke-java
work=$(mktemp -d "$ROOT/build/smoke-java/run.XXXXXXXX")
pid=
cleanup() {
    local result=$?
    if [[ -n "$pid" ]]; then
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    fi
    if [[ "$result" -ne 0 && -f "$work/java-api.log" ]]; then
        tail -100 "$work/java-api.log" | sed -E '/confirmServerLogin b64decoded:|isValidUserLogin:/d'
    fi
    rm -rf "$work"
}
trap cleanup EXIT
dpkg-deb -x "$package" "$work/package"
app="$work/package/opt/el-grande"
mkdir -p "$work/data"
cp -a "$app/java/data-template/." "$work/data/"
cp scripts/bs.cfg.sqlite.linux "$work/bs.cfg"
(
    cd "$work"
    exec java -Djava.awt.headless=true -cp "$app/java/classes:$app/java/lib/*" utilities.apiServer -shop -config bs.cfg -port 18088
) >"$work/java-api.log" 2>&1 &
pid=$!
success=0
for _ in $(seq 1 30); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "BlueSeer API exited unexpectedly"
    exit 1
  fi
  status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:18088/bsapi/authServ || true)"
  if [ "$status" = "401" ]; then success=1; break; fi
  sleep 1
done
if [ "$success" -ne 1 ]; then
  echo "BlueSeer local API did not respond as expected"
  exit 1
fi
echo "BlueSeer local ERP API responded on loopback (expected 401 for unauthenticated GET)."
legacy_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:18088/bsapi/dataServEDI)"
if [[ "$legacy_status" != "404" ]]; then
    echo "Legacy EDI route is enabled in the shop profile"
    exit 1
fi
# Exercise the packaged Java API and an isolated copy of its seed database.
ABD_BOOTSTRAP_DB="$work/data/en/bsdb.db" \
ABD_BOOTSTRAP_ENV="$work/desk.env" \
ABD_BLUESEER_URL="http://127.0.0.1:18088/bsapi" \
PYTHONPATH="$app/integrations/all_by_devoll" \
python3 "$app/integrations/all_by_devoll/erp_bootstrap.py"

# Run the integration checks against the unpacked package.
ABD_BOOTSTRAP_DB="$work/data/en/bsdb.db" \
ABD_BOOTSTRAP_ENV="$work/desk.env" \
PYTHONPATH="$app/integrations/all_by_devoll" \
python3 -c 'import runpy, sys; runpy.run_path(sys.argv[1], run_name="__main__")' \
    "$ROOT/integrations/all_by_devoll/smoke_native.py"
