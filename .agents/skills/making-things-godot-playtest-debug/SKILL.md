---
name: making-things-godot-playtest-debug
description: Playtest and debug live Godot sessions — play/stop, remote tree, game output, screenshots, set_live_property (runtime-only). Use playtest_loop prompt.
---

# Playtest & debug

Two modes:

- **Headless:** `godot_runtime_run_and_capture` — no probe, CI-friendly.
- **Live:** `godot_runtime_play_scene` + `MCPRuntimeProbe` autoload.

Live loop (`playtest_loop` prompt):

1. Enable `runtime` (+ `input` / `testing` / `debugger` as needed).
2. Register probe autoload if missing.
3. Play → `get_game_scene_tree` → `get_game_output`.
4. Live mutate: `godot_runtime_set_live_property` (`persisted=false`; undo via `previous_value`).
5. Screenshot: `capture_game_screenshot` / `capture_editor_screenshot` (needs display; fails clearly headless).
6. Stop scene; check `godot_get_open_errors`.

Also see upstream skill `godot-playtest-and-debug` under `skills/`.
