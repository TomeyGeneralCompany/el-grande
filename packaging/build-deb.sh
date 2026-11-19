#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VERS="${1:-0.13.0}"
OUT="$ROOT/artifacts"
PKG="$ROOT/build/el-grande-package"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/el-grande/integrations/all_by_devoll" \
    "$PKG/opt/el-grande/packaging" "$PKG/opt/el-grande/java" \
    "$PKG/usr/share/applications" "$PKG/usr/lib/systemd/user" "$OUT"
find integrations/all_by_devoll -maxdepth 1 -type f -name '*.py' \
    ! -name 'test_*.py' ! -name 'smoke_native.py' \
    -exec cp -a -t "$PKG/opt/el-grande/integrations/all_by_devoll/" {} +
mkdir -p "$PKG/opt/el-grande/integrations/all_by_devoll/brand"
cp -a integrations/all_by_devoll/brand/*.png "$PKG/opt/el-grande/integrations/all_by_devoll/brand/"
cp -a packaging/el-grande-launcher.py "$PKG/opt/el-grande/packaging/"
cp -a packaging/el-grande.desktop "$PKG/usr/share/applications/"
cp -a packaging/el-grande-*.service "$PKG/usr/lib/systemd/user/"
mkdir -p "$PKG/opt/el-grande/java/classes" "$PKG/opt/el-grande/java/lib"
# These are kept on the full Java build classpath. The shop installer
# transaction smoke passes without them in the installed runtime.
for jar in lib/*.jar; do
    case "${jar##*/}" in
        aspose-cells-7.0.0.jar|jxbrowser-3.0.jar|junit-4.11.jar|hamcrest-core-1.3.jar|oshi-core-3.4.0.jar|jfreechart-1.0.16-experimental.jar|jfreechart-1.0.16-swt.jar|swtgraphics2d.jar)
            continue ;;
    esac
    cp -a "$jar" "$PKG/opt/el-grande/java/lib/"
done
cp -a build/java-classes/. "$PKG/opt/el-grande/java/classes/"
install -D -m 0644 sf/data/en/bsdb.db "$PKG/opt/el-grande/java/data-template/en/bsdb.db"
cat >"$PKG/DEBIAN/control" <<EOF
Package: el-grande
Version: $VERS
Section: office
Priority: optional
Architecture: all
Maintainer: Tomey General Company <noreply@github.com>
Depends: python3 (>= 3.10), python3-tk, python3-reportlab, default-jre | openjdk-17-jre | openjdk-21-jre
Description: All by Devoll local job desk and BlueSeer ERP runtime
 Operator-only ticket dashboard, job reporting, local SQLite storage,
 and bundled BlueSeer classes and resources. First-run desktop setup.
EOF
chmod 755 "$PKG/opt/el-grande/packaging/el-grande-launcher.py"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/el-grande_${VERS}_all.deb"
echo "Package: $OUT/el-grande_${VERS}_all.deb"
