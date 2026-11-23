#!/bin/sh
# Builds dist/cdtracker_<version>_all.deb (Debian desktop app).
# Usage: sh packaging/build-deb.sh        (run from the repository root)
set -e
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import re;print(re.search(r'VERSION = \"([^\"]+)\"', open('cdtracker_core.py').read()).group(1))")
PKG=cdtracker
ROOT=$(mktemp -d)
chmod 755 "$ROOT"
trap 'rm -rf "$ROOT"' EXIT

install -d "$ROOT/DEBIAN" "$ROOT/usr/bin" "$ROOT/usr/share/$PKG" \
           "$ROOT/usr/share/applications" "$ROOT/usr/share/doc/$PKG"
install -m 644 cdtracker_core.py "$ROOT/usr/share/$PKG/"
install -m 755 cdtracker_desktop.py "$ROOT/usr/share/$PKG/"
ln -s "/usr/share/$PKG/cdtracker_desktop.py" "$ROOT/usr/bin/cdtracker"
install -m 644 README.txt "$ROOT/usr/share/doc/$PKG/README.txt"

cat > "$ROOT/usr/share/applications/cdtracker.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=CDTracker
Comment=Cash deposit tracker (Goff Computer)
Exec=cdtracker
Icon=accessories-calculator
Terminal=false
Categories=Office;Finance;
DESK

cat > "$ROOT/usr/share/doc/$PKG/copyright" <<COPY
CDTracker - Goff Computer cash deposit tracker
Copyright $(date +%Y) Goff Computer
COPY

SIZE=$(du -sk "$ROOT/usr" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION
Section: office
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-tk, smbclient
Installed-Size: $SIZE
Maintainer: Goff Computer <noreply@goffcomputer.com>
Homepage: https://github.com/regoff32/CDTracker
Description: Cash deposit tracker for Goff Computer
 Replaces the paper Cash Form (DATE / NAME / CASH / TOTAL). Add cash as
 it comes in; when the running total reaches about \$200, record the
 deposit and start over. Data is kept in one file on the NAS (SMB over
 Tailscale) and shared with the CDTracker Android app.
CTRL

cat > "$ROOT/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if [ "$1" = "configure" ] && command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
POST
chmod 755 "$ROOT/DEBIAN/postinst"

mkdir -p dist
OUT="dist/${PKG}_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT" >/dev/null
echo "$OUT"
