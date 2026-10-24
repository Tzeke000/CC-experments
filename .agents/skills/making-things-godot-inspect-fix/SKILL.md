---
name: making-things-godot-inspect-fix
description: Inspect and safely mutate Godot scenes via Making Things MCP — scene tree, properties, signals, undo, honesty fields (persisted/undoable).
---

# Inspect & fix (editor)

1. `godot_get_server_info` / bridge connected; enable `inspection` (+ `scene_edit` to mutate).
2. Read `godot://scene/tree` or `godot_inspection_get_scene_tree`.
3. Mutate with undo-backed tools; always read `persisted` / `reason` / `hint`.
4. Never treat `persisted=false` as saved (instanced children, etc.).
5. `godot_undo` / editor Ctrl+Z for reversible mistakes.
6. On failure: `godot_get_open_errors` then `debug_scene` prompt.
