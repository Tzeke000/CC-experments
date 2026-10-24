---
name: making-things-godot-observability
description: Diagnose Making Things Godot MCP failures — structured logs, open errors, correlation IDs, game output, parse errors, debug_scene prompt.
---

# Observability / diagnose loop

1. `godot_get_open_errors` or `godot://errors/open`.
2. `godot_get_recent_logs` / `godot://logs/recent` — use `corr.bridge_id` + `command`.
3. Script issues: `godot_scripts_get_parse_errors`.
4. Runtime: `godot_runtime_get_game_output` while playing, or `run_and_capture` headless.
5. Follow `debug_scene` or `playtest_loop` prompts; fix; re-check errors cleared.
6. CI: prefer `--log-file` on Godot invocations when capturing failures.
