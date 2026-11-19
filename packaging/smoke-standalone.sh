#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
package="${1:-artifacts/el-grande_0.14.0_all.deb}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
dpkg-deb -x "$package" "$work/package"
app="$work/package/opt/el-grande/integrations/all_by_devoll"
test ! -e "$work/package/opt/el-grande/java"
test "$(find "$work/package/usr/lib/systemd/user" -type f | wc -l)" -eq 1
if dpkg-deb -f "$package" Depends | grep -Ei 'jre|jdk|java'; then exit 1; fi
python="$(command -v python3)"
mkdir "$work/no-java"
cat >"$work/no-java/java" <<'EOF'
#!/bin/sh
touch "$JAVA_ATTEMPT"
exit 125
EOF
chmod +x "$work/no-java/java"
export JAVA_ATTEMPT="$work/java-attempt"
cd "$work"
PATH="$work/no-java:$PATH" PYTHONPATH="$app:$root/integrations/all_by_devoll" "$python" -c '
import desk, os, unittest
assert "/opt/el-grande/" in desk.__file__, desk.__file__
suite = unittest.defaultTestLoader.loadTestsFromNames(["test_standalone", "test_stock"])
raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())
'
test ! -e "$JAVA_ATTEMPT"
