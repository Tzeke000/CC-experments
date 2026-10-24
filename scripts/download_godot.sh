#!/usr/bin/env bash
# Download Godot 4.7.2 standard + mono (.NET) Linux x86_64 builds.
set -euo pipefail
VERSION="${GODOT_VERSION:-4.7.2-stable}"
DEST="${GODOT_INSTALL_DIR:-$HOME/godot}"
BASE="https://github.com/godotengine/godot/releases/download/${VERSION}"
mkdir -p "$DEST" /tmp/godot-dl
cd /tmp/godot-dl

download_unzip() {
  local zip="$1"
  if [[ ! -f "$DEST/${zip%.zip}" ]] && [[ ! -x "$DEST"/Godot_v${VERSION}_linux.x86_64 ]] && [[ ! -d "$DEST/${zip%.zip}" ]]; then
    echo "Downloading $zip ..."
    curl -fsSL -o "$zip" "$BASE/$zip"
    unzip -o "$zip" -d "$DEST"
  else
    echo "Already present: $zip (skipping download if binary exists)"
    if [[ ! -f "$DEST/$zip" ]] && [[ ! -x $(find "$DEST" -maxdepth 2 -name 'Godot_*' -type f | head -1) ]]; then
      curl -fsSL -o "$zip" "$BASE/$zip"
      unzip -o "$zip" -d "$DEST"
    fi
  fi
}

curl -fsSL -o "Godot_v${VERSION}_linux.x86_64.zip" "$BASE/Godot_v${VERSION}_linux.x86_64.zip"
unzip -o "Godot_v${VERSION}_linux.x86_64.zip" -d "$DEST"
chmod +x "$DEST"/Godot_v${VERSION}_linux.x86_64 || true

curl -fsSL -o "Godot_v${VERSION}_mono_linux_x86_64.zip" "$BASE/Godot_v${VERSION}_mono_linux_x86_64.zip"
unzip -o "Godot_v${VERSION}_mono_linux_x86_64.zip" -d "$DEST"
# mono zip extracts a directory
find "$DEST" -maxdepth 2 -type f -name 'Godot_*mono*' -exec chmod +x {} \;

echo "Installed under $DEST:"
find "$DEST" -maxdepth 2 -type f -name 'Godot_*' | sort
"$DEST/Godot_v${VERSION}_linux.x86_64" --version || true
MONO_BIN=$(find "$DEST" -maxdepth 2 -type f -name 'Godot_*mono*linux*' | head -1)
if [[ -n "${MONO_BIN}" ]]; then
  "$MONO_BIN" --version || true
  echo "Export GODOT_MCP_GODOT_BIN=$MONO_BIN for .NET projects"
fi
