#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VERS="${1:-0.4.0}"
OUT="$ROOT/artifacts"
PKG="$ROOT/build/el-grande-package"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/el-grande/integrations/all_by_devoll" \
    "$PKG/opt/el-grande/packaging" "$PKG/opt/el-grande/java" \
    "$PKG/usr/share/applications" "$PKG/usr/lib/systemd/user" "$OUT"
cp -a integrations/all_by_devoll/*.py "$PKG/opt/el-grande/integrations/all_by_devoll/"
cp -a packaging/el-grande-launcher.py "$PKG/opt/el-grande/packaging/"
cp -a packaging/el-grande.desktop "$PKG/usr/share/applications/"
cp -a packaging/el-grande-*.service "$PKG/usr/lib/systemd/user/"
mkdir -p "$PKG/opt/el-grande/java/classes" "$PKG/opt/el-grande/java/lib"
cp -a lib/*.jar "$PKG/opt/el-grande/java/lib/"
cp -a build/java-classes/. "$PKG/opt/el-grande/java/classes/"
cp -a sf/data "$PKG/opt/el-grande/java/data-template"
cat >"$PKG/DEBIAN/control" <<EOF
Package: el-grande
Version: $VERS
Section: office
Priority: optional
Architecture: all
Maintainer: Tomey General Company <noreply@github.com>
Depends: python3 (>= 3.10), python3-tk, default-jre | openjdk-17-jre | openjdk-21-jre
Description: All by Devoll local job desk and BlueSeer ERP runtime
 Operator-only ticket dashboard, job reporting, local SQLite storage,
 and bundled BlueSeer classes and resources. First-run desktop setup.
EOF
chmod 755 "$PKG/opt/el-grande/packaging/el-grande-launcher.py"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/el-grande_${VERS}_all.deb"
echo "Package: $OUT/el-grande_${VERS}_all.deb"
