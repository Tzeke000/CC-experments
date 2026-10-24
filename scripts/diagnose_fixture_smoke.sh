#!/usr/bin/env bash
# Headless diagnose smoke: parse a broken script, confirm Godot reports the error,
# then parse a fixed script. Uses --log-file for CI artifact capture (Phase 4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT_BIN="${GODOT_MCP_GODOT_BIN:-${GODOT_BIN:-$HOME/godot/Godot_v4.7.2-stable_linux.x86_64}}"
PROJECT="$ROOT/fixtures/godot_project"
LOG_DIR="${LOG_DIR:-$ROOT/.godot-smoke-logs}"
mkdir -p "$LOG_DIR" "$PROJECT/scripts"

BROKEN="$PROJECT/scripts/_broken_smoke.gd"
FIXED="$PROJECT/scripts/_fixed_smoke.gd"
cat > "$BROKEN" << 'EOF'
extends Node
func _ready(
	print("missing paren")
EOF
cat > "$FIXED" << 'EOF'
extends Node
func _ready() -> void:
	print("ok")
EOF

if [[ ! -x "$GODOT_BIN" ]]; then
  echo "Godot binary not found at $GODOT_BIN" >&2
  exit 1
fi

set +e
"$GODOT_BIN" --headless --path "$PROJECT" --script "$BROKEN" --check-only \
  --log-file "$LOG_DIR/broken.log" 2>"$LOG_DIR/broken.stderr"
BROKEN_EC=$?
set -e
if [[ "$BROKEN_EC" -eq 0 ]]; then
  echo "expected broken script to fail --check-only" >&2
  exit 1
fi
echo "broken script correctly failed (exit $BROKEN_EC)"

"$GODOT_BIN" --headless --path "$PROJECT" --script "$FIXED" --check-only \
  --log-file "$LOG_DIR/fixed.log" 2>"$LOG_DIR/fixed.stderr"
echo "fixed script OK; logs in $LOG_DIR"
# cleanup temp scripts so fixtures stay clean for import smoke
rm -f "$BROKEN" "$FIXED" "${BROKEN}.uid" "${FIXED}.uid" 2>/dev/null || true
