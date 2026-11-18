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
