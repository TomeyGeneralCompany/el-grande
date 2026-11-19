#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VERS="${1:-0.14.0}"
OUT="$ROOT/artifacts"
PKG="$ROOT/build/el-grande-package"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/el-grande/integrations/all_by_devoll" \
    "$PKG/opt/el-grande/packaging" \
    "$PKG/usr/share/applications" "$PKG/usr/lib/systemd/user" "$OUT"
find integrations/all_by_devoll -maxdepth 1 -type f -name '*.py' \
    ! -name 'test_*.py' \
    -exec cp -a -t "$PKG/opt/el-grande/integrations/all_by_devoll/" {} +
mkdir -p "$PKG/opt/el-grande/integrations/all_by_devoll/brand"
cp -a integrations/all_by_devoll/brand/*.png "$PKG/opt/el-grande/integrations/all_by_devoll/brand/"
cp -a packaging/el-grande-launcher.py "$PKG/opt/el-grande/packaging/"
cp -a packaging/el-grande.desktop "$PKG/usr/share/applications/"
cp -a packaging/el-grande-desk.service "$PKG/usr/lib/systemd/user/"
install -D -m 0644 NOTICES "$PKG/usr/share/doc/el-grande/copyright"
cat >"$PKG/DEBIAN/control" <<EOF
Package: el-grande
Version: $VERS
Section: office
Priority: optional
Architecture: all
Maintainer: Tomey General Company <noreply@github.com>
Depends: python3 (>= 3.10), python3-tk, python3-reportlab
Description: All by Devoll local job desk
 Work orders, stock, purchasing, receipts, PDF invoices and the cashbook
 use one local SQLite database.
EOF
chmod 755 "$PKG/opt/el-grande/packaging/el-grande-launcher.py"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/el-grande_${VERS}_all.deb"
echo "Package: $OUT/el-grande_${VERS}_all.deb"
