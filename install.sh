#!/usr/bin/env bash
# Install OpenPASCO for the current user (no sudo): private virtualenv, launcher, menu entry.
#   ./install.sh                install
#   ./install.sh --with-pasco   also install PASCO's own BLE library (personal/educational licence)
# Override: PYTHON=python3.14  OPENPASCO_BIN_DIR=~/bin  XDG_DATA_HOME=...
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
BIN=${OPENPASCO_BIN_DIR:-$HOME/.local/bin}
VENV=$DATA/openpasco/venv
PY=${PYTHON:-python3}

if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 14))' 2>/dev/null; then
    echo "Python 3.14 이상이 필요합니다. (PYTHON=/경로/python3.14 ./install.sh 로 지정할 수 있습니다)" >&2
    exit 1
fi

target="$HERE"
[ "${1:-}" = "--with-pasco" ] && target="$HERE[pasco]"

"$PY" -m venv "$VENV"
"$VENV/bin/pip" install "$target"

mkdir -p "$BIN" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
ln -sf "$VENV/bin/openpasco" "$BIN/openpasco"
install -m 644 "$HERE/packaging/openpasco.svg" "$DATA/icons/hicolor/scalable/apps/openpasco.svg"
# absolute Exec: the menu launcher may not have ~/.local/bin on its PATH
sed "s|^Exec=.*|Exec=\"$VENV/bin/openpasco\"|" "$HERE/packaging/openpasco.desktop" > "$DATA/applications/openpasco.desktop"
update-desktop-database "$DATA/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$DATA/icons/hicolor" 2>/dev/null || true

echo "설치 완료. 앱 메뉴의 OpenPASCO 또는 터미널의 'openpasco' 로 실행합니다."
case ":$PATH:" in *":$BIN:"*) ;; *) echo "참고: $BIN 이 PATH에 없습니다. 메뉴 아이콘으로는 실행됩니다." ;; esac
