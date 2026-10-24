# Self-hosted Godot runner (Making Things)

## Why jobs used to stay queued

Upstream hybridindie workflows required labels that **do not exist** on this fork:

| Label set | Used by |
|-----------|---------|
| `[self-hosted, linux, hybridindie]` | `ci.yml` python jobs, `runner-image.yml` |
| `[self-hosted, godot]` | `ci.yml` godot-floor, `e2e.yml` |

With no matching runners, GitHub Actions left those jobs **queued forever**.

## What runs where (after MT-3)

| Workflow | Default `runs-on` | Coverage |
|----------|-------------------|----------|
| `making-things-smoke.yml` | `ubuntu-latest` | Fixture import, diagnose, C# mono smoke, trajectory |
| `ci.yml` | `ubuntu-latest` (override via `MT_CI_RUNS_ON`) | ruff, mypy, full pytest (Godot tests skipif), 4.4 floor |
| `e2e.yml` | `ubuntu-latest` (override via `MT_E2E_RUNS_ON`) | Live editor integration + play-session under xvfb |

**Honesty:** default GitHub-hosted lanes download Godot and install xvfb as needed. They are slower/more expensive than a dedicated runner but **actually execute**. Empty `UV_CACHE_DIR` uses uv defaults (no `/runner/_work/_cache` dependency).

## Optional: attach your own runner

Use this when you want a dedicated Linux box (faster e2e, baked Godot, less GH minutes).

### 1. Create the runner in GitHub

Repo → **Settings → Actions → Runners → New self-hosted runner** → Linux x64.

Copy the token shown on that page (expires quickly).

### 2. Bootstrap on the machine

```bash
# On a Linux x86_64 host with sudo (or rootless docker — see infra/)
export REPO_URL="https://github.com/Tzeke000/CC-experments"
export RUNNER_TOKEN="AAAA..."   # from the GitHub UI — do NOT commit
export RUNNER_NAME="mt-godot-1"
export RUNNER_LABELS="self-hosted,making-things,godot"

curl -fsSL -o /tmp/mt-runner.sh \
  "$REPO_URL/raw/main/scripts/ci/setup-github-runner.sh"
# Or clone the repo and run:
bash scripts/ci/setup-github-runner.sh
```

The script installs the actions runner under `~/actions-runner`, registers it with
labels `self-hosted,making-things,godot`, and optionally installs Godot 4.7.2 + xvfb.

### 3. Point workflows at the runner

Repo → **Settings → Secrets and variables → Actions → Variables**:

| Variable | Example value | Purpose |
|----------|---------------|---------|
| `MT_CI_RUNS_ON` | `["self-hosted","making-things","godot"]` | All `ci.yml` jobs |
| `MT_E2E_RUNS_ON` | `["self-hosted","making-things","godot"]` | `e2e.yml` jobs (falls back to `MT_CI_RUNS_ON`) |
| `GODOT_BIN` | `/opt/godot/godot` or `$HOME/godot/...` | Skip download when baked |
| `MT_UV_CACHE_DIR` | `/runner/_work/_cache/uv` | Only if you mount that path |

Leave variables **unset** to keep `ubuntu-latest` (recommended until a runner is online).

### 4. Verify

```bash
# On the runner host
~/actions-runner/run.sh   # or the systemd service the script installs

# In GitHub: Actions → ci → Run workflow
# Confirm the job lands on your runner name, not "ubuntu-latest"
```

### Security

- Do **not** enable the runner for fork PRs from strangers (workflows already skip
  when `head.repo != github.repository`). Prefer ephemeral runners.
- Require approval for outside collaborators (repo Actions settings).

## Local equivalent (this cloud VM / laptop)

```bash
export GODOT_MCP_ALLOW_INSECURE_BRIDGE=1
export GODOT_BIN=$HOME/godot/Godot_v4.7.2-stable_linux.x86_64
uv sync --frozen
bash scripts/ci/check-no-skipped-tests.sh
uv run ruff check .
uv run mypy
uv run pytest -q                    # Godot tests skip without GODOT_BIN
xvfb-run -a uv run pytest -q tests/integration   # full e2e-style
```
