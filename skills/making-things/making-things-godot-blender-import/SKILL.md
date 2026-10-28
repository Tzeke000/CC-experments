---
name: making-things-godot-blender-import
description: Blender→Godot glTF import for Making Things — conventions, mt_blender_export, reimport/diagnose MCP tools, gltf_pipeline (MIT), optional Goblend (GPL). Use fix_import prompt.
---

# Blender → Godot

Enable toolsets first: `godot_enable_toolset(category="asset_import")`, then `inspection` (and `scene_edit` if you need `rescan_filesystem`).

1. Read `godot://conventions/blender` via `godot_read_resource(uri="godot://conventions/blender")`.
2. **Blender (MIT):** install `third_party/mt_blender_export` — Godot name suffixes, `collision` / `name_override` extras, Export glTF for Godot. Prefer **`.glb`/`.gltf`**; `.blend` only if the whole team has Blender ≥3.5.
3. Place under `res://art/`. External files: `godot_asset_import_asset(source=..., target_path=..., wait_for_scan=True)`. In-place overwrite: `godot_asset_import_reimport(paths=["res://art/..."])`.
4. `godot_asset_import_diagnose(target_path=...)` — honor `issues[]`, `hints[]`, `scanning`, `sidecar_present`, `gltf_pipeline_enabled`. `ready: true` is not proof.
5. `godot_asset_import_get_status` until imported and not scanning (`reason: rescan_in_flight` = provisional).
6. Open the imported scene; `godot_inspection_get_scene_tree(...)` — **never claim success without tree evidence**.
7. Fixtures: `fixtures/godot_project/art/sample.glb`, `triangle.gltf` (carries `collision` + `name_override` extras).
8. MIT `addons/gltf_pipeline` applies extras. **Goblend** (`third_party/goblend`, GPL-3.0) is optional — do not enable unless the project accepts GPL. See `third_party/README.md`.
9. Prompt: `fix_import`.
