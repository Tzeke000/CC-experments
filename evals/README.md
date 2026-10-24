# Evals

`evals/` holds:

1. **Instruction Staleness Verifier** — static analysis of tool docs vs addon handlers.
2. **Making Things trajectory harness** (`making_things_trajectory.py`) — non-LLM
   structural + diagnose smoke checklist.
3. **Making Things agent evals** (`mt_agent/`) — **MT-4** multi-step diagnose /
   playtest / import cases with mock (always) and optional live LLM tool-loop.
   See [`docs/making-things/agent-evals.md`](../docs/making-things/agent-evals.md).

The historical upstream LLM harness modules (`llm_eval_v2`, `ollama_agent`, …)
moved to **godot-agents** (`godot_agent_harness`). That repo is not vendored here
(and was not clonable from this environment). MT-4 pins Making Things cases
locally instead of depending on it.

## Usage

```bash
# Server self-analysis
uv run python -m evals.instruction_staleness --static

# Non-LLM Making Things checklist
uv run python -m evals.making_things_trajectory

# MT-4 agent cases (mock — no keys)
uv run python -m evals.mt_agent.runner --mode mock
uv run pytest tests/unit/test_mt_agent_evals.py -q

# MT-4 live LLM (needs OPENAI_API_KEY or MAKING_THINGS_LLM_API_KEY)
uv run python -m evals.mt_agent.runner --mode live
```
