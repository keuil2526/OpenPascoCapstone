#!/usr/bin/env bash
# Remove what install.sh created. Your experiment files and app settings (~/.config/OpenPASCO) are kept.
set -euo pipefail
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
BIN=${OPENPASCO_BIN_DIR:-$HOME/.local/bin}
rm -rf "$DATA/openpasco"
rm -f "$BIN/openpasco" "$DATA/applications/openpasco.desktop" "$DATA/icons/hicolor/scalable/apps/openpasco.svg"
update-desktop-database "$DATA/applications" 2>/dev/null || true
echo "제거했습니다."
