# CI path (Making Things fork)

## What runs where (MT-3)

| Workflow | Default runner | What it covers |
|----------|----------------|----------------|
| `making-things-smoke.yml` | `ubuntu-latest` | Fixture import, diagnose, C# mono smoke, trajectory harness |
| `ci.yml` | `ubuntu-latest` via `MT_CI_RUNS_ON` default | ruff · mypy · full `pytest -q` (Godot tests skipif) · camelCase · **Godot 4.4 floor** |
| `e2e.yml` | `ubuntu-latest` via `MT_E2E_RUNS_ON` default | Live editor integration + play-session e2e under **xvfb** (downloads Godot 4.7.2) |

Upstream hybridindie labels (`[self-hosted, linux, hybridindie]`, `[self-hosted, godot]`) are **no longer required**. Jobs no longer sit queued forever on this fork.

### Optional self-hosted override

Set repo Actions variables (JSON arrays) when you attach a runner — see
[`self-hosted-runner.md`](./self-hosted-runner.md):

```text
MT_CI_RUNS_ON  = ["self-hosted","making-things","godot"]
MT_E2E_RUNS_ON = ["self-hosted","making-things","godot"]
GODOT_BIN      = /opt/godot/godot
```

Bootstrap: `bash scripts/ci/setup-github-runner.sh` (needs `RUNNER_TOKEN` from the GitHub UI).

## Exact local commands

```bash
uv sync --frozen
export GODOT_MCP_ALLOW_INSECURE_BRIDGE=1

# ci.yml equivalent (no Godot)
bash scripts/ci/check-no-skipped-tests.sh
uv run ruff check .
uv run mypy
uv run pytest -q

# e2e.yml equivalent
export GODOT_BIN=$HOME/godot/Godot_v4.7.2-stable_linux.x86_64
xvfb-run -a --server-args="-screen 0 1280x1024x24" \
  uv run pytest -q tests/integration \
  tests/contract/test_addon_guards.py \
  tests/contract/test_addon_handshake.py \
  tests/contract/test_router_refactor.py \
  tests/contract/test_undo_threshold.py

# Making Things extras
bash scripts/csharp_fixture_smoke.sh
uv run python -m evals.making_things_trajectory
```

## Honesty

- Default GH-hosted `ci` + `e2e` **do** claim full upstream suite coverage (with Godot downloaded on e2e/floor jobs). They cost more Actions minutes than a dedicated runner.
- `making-things-smoke` remains the fast PR signal; `ci`/`e2e` are the complete gates.
- LLM agent evals are **not** in this repo (godot-agents).

## Godot 4.8 beta advisory lane

`e2e.yml` job `live editor (Godot 4.8 beta, advisory)` runs the same integration
suite on **4.8-beta1** with `continue-on-error: true`. The 4.7.2 lane remains the
blocking gate.

Known behaviors (do not skip the suite):

| Symptom | Cause / handling |
|---------|------------------|
| MeshLibrary items empty after save | Upstream [godot#124712](https://github.com/godotengine/godot/issues/124712); persistence e2e asserts the known-bad shape via `is_godot_48_beta1()` |
| `probe never connected` on `test_live_game_output` under full-suite load | Fixed-iteration 15s wait raced cold play; use `wait_probe_connected(..., timeout=30)` (#626 wall-clock). Probe now announces `ready` before best-effort Logger setup |

Prefer real waits / known-bad assertions over silencing the advisory job.
