#!/usr/bin/env bash
# Best-effort live-editor smoke (Phase 3/exit #5). Requires GODOT_BIN + display.
# Uses xvfb-run when no usable DISPLAY for play-session suites.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
export GODOT_BIN="${GODOT_MCP_GODOT_BIN:-${GODOT_BIN:-$HOME/godot/Godot_v4.7.2-stable_linux.x86_64}}"
export GODOT_MCP_ALLOW_INSECURE_BRIDGE="${GODOT_MCP_ALLOW_INSECURE_BRIDGE:-1}"
export GODOT_MCP_BRIDGE_TOKEN="${GODOT_MCP_BRIDGE_TOKEN:-live-smoke-token}"

if [[ ! -x "$GODOT_BIN" ]]; then
  echo "skip: no Godot at $GODOT_BIN" >&2
  exit 0
fi

cd "$ROOT"
uv sync --frozen >/dev/null

RUNNER=(uv run pytest)
# Prefer a small, high-signal subset that boots the editor when possible.
TESTS=(
  tests/integration/test_bridge_auth_e2e.py
  tests/integration/test_addon_screenshot.py
  tests/integration/test_addon_inspect.py
)

if [[ -z "${DISPLAY:-}" ]] || [[ "${FORCE_XVFB:-}" == "1" ]]; then
  if command -v xvfb-run >/dev/null 2>&1; then
    echo "using xvfb-run for live smoke"
    RUNNER=(xvfb-run -a uv run pytest)
  else
    echo "no DISPLAY/xvfb — running bridge-auth only (may skip editor suites)"
    TESTS=(tests/integration/test_bridge_auth_e2e.py)
  fi
fi

"${RUNNER[@]}" "${TESTS[@]}" -q --tb=line "$@" || {
  ec=$?
  echo "live smoke exited $ec (skips are environmental; failures are real)" >&2
  exit "$ec"
}
