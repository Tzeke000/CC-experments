# CI path (Making Things fork)

## What is green on GitHub-hosted runners

Workflow: `.github/workflows/making-things-smoke.yml` (`ubuntu-latest`)

| Job | What it runs |
|-----|----------------|
| `godot-import-diagnose` | Download Godot **standard** 4.7.2 → fixture import → `scripts/diagnose_fixture_smoke.sh` |
| `python-unit-mt` | `uv sync` + expanded pytest (unit + contract Making Things surface) |
| `csharp-mono-smoke` | .NET 8 + Godot **mono** 4.7.2 → `scripts/csharp_fixture_smoke.sh` |
| `trajectory-harness` | `uv run python -m evals.making_things_trajectory` (scripted; no LLM) |

## What needs self-hosted labels (upstream hybridindie)

These workflows are inherited from hybridindie and **will not run** on this fork until matching runners exist:

| Workflow | Labels | Typical command once runners exist |
|----------|--------|--------------------------------------|
| `ci.yml` | `[self-hosted, linux, hybridindie]` and `[self-hosted, godot]` | Full lint/type/unit/contract matrix |
| `e2e.yml` | `[self-hosted, godot]` | Live editor e2e (play sessions, xvfb) |
| Eval runners | `godot-eval` (see `e2e.yml` comments) | LLM agent harness (lives in **godot-agents**) |

### Exact local / self-hosted commands

```bash
# Making Things cloud-equivalent
uv sync --frozen
export GODOT_MCP_ALLOW_INSECURE_BRIDGE=1
uv run pytest tests/unit tests/contract -q --tb=line

# Live e2e subset (needs DISPLAY / xvfb-run + GODOT_BIN)
export GODOT_BIN=$HOME/godot/Godot_v4.7.2-stable_linux.x86_64
xvfb-run -a uv run pytest \
  tests/integration/test_set_live_property_e2e.py \
  tests/integration/test_game_output_e2e.py \
  tests/integration/test_mutation_e2e.py \
  tests/integration/test_runtime_inspect_e2e.py \
  -q --tb=line

# Full upstream-style suite (self-hosted godot runner)
xvfb-run -a uv run pytest -q --tb=line

# C# Phase 2
export GODOT_MCP_GODOT_BIN=$HOME/godot/Godot_v4.7.2-stable_mono_linux_x86_64/Godot_v4.7.2-stable_mono_linux.x86_64
export PATH="$HOME/.dotnet:$PATH"
bash scripts/csharp_fixture_smoke.sh

# Trajectory (non-LLM)
uv run python -m evals.making_things_trajectory
uv run python -m evals.instruction_staleness --static
```

## Honesty

- Fork CI does **not** claim full upstream e2e parity.
- `csharp_build` is green when mono + .NET SDK are present (Phase 2 smoke).
- LLM agent trajectory evals are **not** in this repo; see `evals/README.md` and `evals/making_things_trajectory.py`.
