# Blender ↔ Godot AI pipeline (Making Things)

glTF-first path so an agent can export from Blender, import into Godot, diagnose,
and prove success with scene-tree evidence.

## Pieces

| Piece | Path | License |
|-------|------|---------|
| Blender helpers | `third_party/mt_blender_export/` | MIT |
| Godot extras runtime | `third_party/gltf_pipeline/` → `addons/gltf_pipeline` | MIT |
| Optional full UX | `third_party/goblend/` | GPL-3.0 |
| Conventions | `godot://conventions/blender` | — |
| Prompt | `fix_import` | — |
| Skill | `making-things-godot-blender-import` | — |

## MCP tools (`asset_import` toolset)

- `godot_asset_import_asset` — copy external/URL → `res://`
- `godot_asset_import_reimport` — force reimport of existing paths
- `godot_asset_import_get_status` — sidecar / scanning honesty
- `godot_asset_import_diagnose` — extras, suffixes, pipeline plugin, issues[]
- `godot_asset_import_create_material_from_textures` — PBR `.tres`

## Agent loop

See store plan `docs/blender-godot-pipeline-plan.md` and prompt `fix_import`.
