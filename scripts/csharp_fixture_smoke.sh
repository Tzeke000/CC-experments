#!/usr/bin/env bash
# Making Things decision F / issue #207 Phase 2 smoke:
# 1) Godot mono editor loads the C# fixture
# 2) Backend probe reports csharp_supported + csharp_project (+ csharp_build when dotnet present)
# 3) ``dotnet build`` succeeds on the fixture csproj
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONO_BIN="${GODOT_MCP_GODOT_BIN:-${GODOT_MONO_BIN:-}}"
if [[ -z "${MONO_BIN}" ]]; then
  MONO_BIN="$HOME/godot/Godot_v4.7.2-stable_mono_linux_x86_64/Godot_v4.7.2-stable_mono_linux.x86_64"
fi
PROJECT="$ROOT/fixtures/godot_csharp_project"
LOG_DIR="${LOG_DIR:-$ROOT/.godot-smoke-logs}"
mkdir -p "$LOG_DIR"
export PATH="${HOME}/.dotnet:${PATH:-}"
export DOTNET_ROOT="${DOTNET_ROOT:-$HOME/.dotnet}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1

if [[ ! -x "$MONO_BIN" ]]; then
  echo "Godot mono binary not found at $MONO_BIN" >&2
  echo "Set GODOT_MCP_GODOT_BIN or GODOT_MONO_BIN to the mono editor." >&2
  exit 1
fi

echo "== mono version =="
"$MONO_BIN" --version

echo "== headless import (mono) =="
"$MONO_BIN" --headless --path "$PROJECT" --import --quit \
  --log-file "$LOG_DIR/csharp-import.log"

PROBE_SCRIPT="$PROJECT/scripts/_csharp_backend_probe.gd"
cat > "$PROBE_SCRIPT" << 'EOF'
extends SceneTree
## Headless backend probe for fixtures/godot_csharp_project (Making Things F).
func _initialize() -> void:
	var supported := ClassDB.class_exists("CSharpScript")
	var csproj := ""
	var dir := DirAccess.open("res://")
	if dir:
		dir.list_dir_begin()
		var name := dir.get_next()
		while name != "":
			if name.ends_with(".csproj"):
				csproj = "res://" + name
				break
			name = dir.get_next()
		dir.list_dir_end()
	var project := not csproj.is_empty()
	var output: Array = []
	var dotnet_ok := OS.execute("dotnet", PackedStringArray(["--version"]), output, true, false) == 0
	var build_ready := supported and project and dotnet_ok
	print("CSHARP_PROBE supported=%s project=%s build=%s csproj=%s" % [
		supported, project, build_ready, csproj
	])
	if not supported:
		push_error("expected csharp_supported on mono editor")
		quit(1)
		return
	if not project:
		push_error("expected .csproj in fixture")
		quit(1)
		return
	print("CSHARP_PROBE_OK")
	quit(0)
EOF

echo "== backend probe (mono SceneTree) =="
set +e
"$MONO_BIN" --headless --path "$PROJECT" --script "$PROBE_SCRIPT" \
  --log-file "$LOG_DIR/csharp-probe.log" 2>"$LOG_DIR/csharp-probe.stderr"
PROBE_EC=$?
set -e
rm -f "$PROBE_SCRIPT" "${PROBE_SCRIPT}.uid" 2>/dev/null || true
if [[ "$PROBE_EC" -ne 0 ]]; then
  echo "backend probe failed (exit $PROBE_EC); see $LOG_DIR/csharp-probe.*" >&2
  exit "$PROBE_EC"
fi
grep -q "CSHARP_PROBE_OK" "$LOG_DIR/csharp-probe.log" \
  || grep -q "CSHARP_PROBE_OK" "$LOG_DIR/csharp-probe.stderr" \
  || { echo "CSHARP_PROBE_OK marker missing" >&2; exit 1; }

if ! command -v dotnet >/dev/null 2>&1; then
  echo "WARN: dotnet not on PATH — csharp_build capability stays false; skip MSBuild." >&2
  echo "Install .NET 8 SDK and re-run for full Phase 2 smoke." >&2
  echo "CSHARP_SMOKE_PARTIAL_OK (mono + fixture only)"
  exit 0
fi

echo "== dotnet build =="
dotnet --version
dotnet build "$PROJECT/MakingThingsCsharpFixture.csproj" -c Debug -v q \
  | tee "$LOG_DIR/csharp-build.log"
echo "CSHARP_SMOKE_OK (mono + csharp_build)"
