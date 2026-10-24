# Evals (server self-analysis + Making Things scripted trajectory)

`evals/` holds:

1. **Instruction Staleness Verifier** — static analysis of godot-mcp's *own*
   tool docs vs. the addon's bridge handler registrations.
2. **Making Things trajectory harness** (`making_things_trajectory.py`) — a
   **non-LLM** checklist that runs the diagnose smoke + structural gates an
   agent would need. Not a substitute for LLM agent evals.

The LLM eval **harness** (agents, task suites, variant A/B testing, transition/
composition/negative/batch runners, results archives) is a consumer concern and
lives in **godot-agents** as the self-contained `godot_agent_harness` package
(godot-agents#481, moved in #383). It imports `godot_editor_mcp` only via the
published wheel — no cross-repo source imports.

**Blocker / next step for LLM trajectories:** pin a `diagnose_broken_script`
(and `playtest_loop` + `set_live_property`) case in godot-agents against this
fork's wheel; this repo intentionally does not vendor that harness.

## Usage

```bash
# Static analysis: bridge.send()/route() cmd_* vs addon handlers["cmd_*"] + doc drift
uv run python -m evals.instruction_staleness --static

# Runtime verification: call each shared cmd_* through the bridge
uv run python -m evals.instruction_staleness --runtime

# Both
uv run python -m evals.instruction_staleness --all

# Making Things scripted trajectory (diagnose smoke + skills/prompts present)
uv run python -m evals.making_things_trajectory
```

## Why the harness moved

- godot-mcp is **game-agnostic and consumer-independent**; the harness evaluated
  *agents* (OllamaAgent, CloudAgent, LangGraph-side consumers), not the server.
- godot-agents owns the eval agents, telemetry, and the unified "Godot AI"
  experiment; vendoring the harness there (with the #276 bridge topology fix —
  `serve()` + addon-dials) keeps this repo's surface generic.
- Server-side safety gates (`confirm`, `dry_run`, toolset gating) are exercised
  by `tests/contract/` here, not by LLM-run trials.