#!/usr/bin/env bash
# Build dist/openpasco_<version>_all.deb for Ubuntu/Debian using the distro's own Python packages.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$HERE/openpasco/__init__.py")
[ -n "$VERSION" ] || { echo "version not found" >&2; exit 1; }
OUT="$HERE/dist"
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT

LIB="$ROOT/usr/lib/python3/dist-packages"
DOC="$ROOT/usr/share/doc/openpasco"
mkdir -p "$LIB" "$DOC" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/scalable/apps" "$ROOT/DEBIAN" "$OUT"

cp -r "$HERE/openpasco" "$LIB/"
find "$LIB" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$ROOT/usr/bin/openpasco" <<'LAUNCH'
#!/usr/bin/python3
import sys

from openpasco.app import main

sys.exit(main())
LAUNCH
install -m 644 "$HERE/packaging/openpasco.desktop" "$ROOT/usr/share/applications/openpasco.desktop"
install -m 644 "$HERE/packaging/openpasco.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/openpasco.svg"
install -m 644 "$HERE/README.md" "$DOC/README.md"

cat > "$DOC/copyright" <<'COPY'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: OpenPASCO
Source: https://github.com/keuil2526/OpenPascoCapstone

Files: *
Copyright: 2026 keuil2526
License: custom
 No open-source licence has been chosen yet. This is a personal, non-commercial,
 educational project. Do not redistribute without the author's permission.
 .
 OpenPASCO is independent software. It is not affiliated with or endorsed by PASCO
 scientific, and contains no PASCO code.
COPY
printf 'openpasco (%s) unstable; urgency=low\n\n  * Packaged release.\n\n -- keuil2526 <keuil2526@users.noreply.github.com>  %s\n' \
    "$VERSION" "$(date -R)" | gzip -9n > "$DOC/changelog.gz"

mkdir -p "$ROOT/usr/share/man/man1"
cat <<'MAN' | gzip -9n > "$ROOT/usr/share/man/man1/openpasco.1.gz"
.TH OPENPASCO 1
.SH NAME
openpasco \- PASCO sensor data collection and analysis
.SH SYNOPSIS
.B openpasco
.SH DESCRIPTION
Starts the OpenPASCO graphical program. Experiments are saved as .opasco files; settings are kept in
~/.config/OpenPASCO.
MAN
cat > "$ROOT/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
if [ "$1" = configure ] && command -v py3compile >/dev/null 2>&1; then
    py3compile -p openpasco
fi
exit 0
SH
cat > "$ROOT/DEBIAN/prerm" <<'SH'
#!/bin/sh
set -e
if command -v py3clean >/dev/null 2>&1; then
    py3clean -p openpasco
fi
exit 0
SH
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/prerm" "$ROOT/usr/bin/openpasco"
chmod 755 "$ROOT"
find "$ROOT/usr" -type d -exec chmod 755 {} +
find "$LIB" "$ROOT/usr/share" -type f -exec chmod 644 {} +

SIZE=$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<CONTROL
Package: openpasco
Version: $VERSION
Architecture: all
Maintainer: keuil2526 <keuil2526@users.noreply.github.com>
Installed-Size: $SIZE
Depends: python3 (>= 3.14), python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets, python3-pyside6.qtopengl, python3-pyside6.qtopenglwidgets, python3-pyqtgraph, python3-numpy, python3-scipy
Section: science
Priority: optional
Homepage: https://github.com/keuil2526/OpenPascoCapstone
Description: PASCO sensor data collection and analysis
 Record, graph and analyse sensor data: live graph, table, digits and meter
 displays, curve fitting, calculated measurements, CSV export, and read-only
 import of PASCO Capstone .cap files. Includes simulated sensors.
 .
 PASCO wireless sensors need PASCO's own Python library (pip install pasco),
 which is not packaged here; USB interfaces are not supported.
CONTROL

dpkg-deb --root-owner-group --build "$ROOT" "$OUT/openpasco_${VERSION}_all.deb" >/dev/null
echo "$OUT/openpasco_${VERSION}_all.deb"
