#!/usr/bin/env bash
# Headless import smoke for fixtures/godot_project (plan §9 Phase 0).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT_BIN="${GODOT_MCP_GODOT_BIN:-${GODOT_BIN:-$HOME/godot/Godot_v4.7.2-stable_linux.x86_64}}"
PROJECT="$ROOT/fixtures/godot_project"
if [[ ! -x "$GODOT_BIN" ]]; then
  echo "Godot binary not found at $GODOT_BIN — run scripts/download_godot.sh" >&2
  exit 1
fi
"$GODOT_BIN" --headless --path "$PROJECT" --import --quit
echo "import smoke OK"
