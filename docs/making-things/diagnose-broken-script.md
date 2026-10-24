# Eval: diagnose broken script (Phase 4)

Manual / agent trajectory checklist (also automated partially by
`scripts/diagnose_fixture_smoke.sh`):

1. Open `fixtures/godot_project` with addon + bridge token.
2. Write a deliberately broken script via tools (syntax error).
3. Call `godot_scripts_get_parse_errors` — must report the location.
4. Call `godot_get_open_errors` / `godot://errors/open` after a failed mutate.
5. Fix the script via tools; re-check parse errors empty.
6. Optional: `godot_runtime_run_and_capture` confirms clean headless boot.

Pass criteria: agent never claims success while parse errors remain.
