# Making Things agent evals (MT-4)

Multi-step agent trajectories that pin **diagnose / playtest / import** behavior
against this fork’s MCP tools — beyond the non-LLM
`evals/making_things_trajectory.py` checklist.

Upstream `godot-agents` / `godot_agent_harness` is not public/clonable from this
environment; this package morphs the **tool-accuracy eval** pattern from Godot
Editor MCP consumer docs (score calls against an `expected_tools` /
subsequence spec) plus fixture-style cases (inspired by public agent-harness
eval layouts).

## Cases

| Id | What it exercises | Pass means |
|----|-------------------|------------|
| `diagnose_broken_script` | `godot_scripts_write` → `get_parse_errors` → fix → re-check | Required tool subsequence; parse errors empty after fix; never “success” while errors remain |
| `playtest_live_mutate` | `play_scene` → `godot_runtime_set_live_property` → stop | Live mutate present; **`persisted=false`**; dry_run or `previous_value` honesty |
| `import_gltf` | `godot_asset_import_asset` + scene tree inspect | Import ok; required import tool in trajectory |

Fixtures live in `evals/mt_agent/cases/*.yaml`.

## How to run

```bash
# Always-green dry run (scripted agent, no LLM, no Godot)
uv run python -m evals.mt_agent.runner --mode mock
uv run python -m evals.mt_agent.runner --mode mock --case diagnose_broken_script
uv run python -m evals.mt_agent.runner --mode mock --json

# Pytest wrapper (CI)
uv run pytest tests/unit/test_mt_agent_evals.py -q

# Live LLM tool-loop (OpenAI-compatible). Without keys → exit 2 + BLOCKED message.
export OPENAI_API_KEY=sk-...                    # or MAKING_THINGS_LLM_API_KEY
# optional:
export MAKING_THINGS_LLM_BASE_URL=https://api.openai.com/v1
export MAKING_THINGS_LLM_MODEL=gpt-4o-mini
uv run python -m evals.mt_agent.runner --mode live
```

### Env vars (live)

| Variable | Required | Default |
|----------|----------|---------|
| `OPENAI_API_KEY` or `MAKING_THINGS_LLM_API_KEY` (or `ANTHROPIC_API_KEY` with a compatible gateway URL) | **yes for live** | — |
| `MAKING_THINGS_LLM_BASE_URL` | no | `https://api.openai.com/v1` |
| `MAKING_THINGS_LLM_MODEL` | no | `gpt-4o-mini` |

Live mode currently drives the **mock tool world** (deterministic Godot fakes) so
tool-selection can be scored without a display/editor. Wiring the same cases to a
live editor+bridge is a follow-up (needs `GODOT_BIN` + xvfb / self-hosted runners —
owned by the CI worker, not this PR).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All selected cases passed |
| 1 | One or more cases failed scoring |
| 2 | Live mode blocked (missing API key / LLM HTTP error) and nothing passed |

## Relationship to other harnesses

| Harness | Role |
|---------|------|
| `evals/instruction_staleness.py` | Server↔addon cmd_* drift (self-analysis) |
| `evals/making_things_trajectory.py` | Non-LLM structural + diagnose smoke |
| `evals/mt_agent/` (**this**) | Multi-step agent tool trajectories (mock + optional LLM) |
| godot-agents (private/upstream) | Full LLM consumer harness when available |
