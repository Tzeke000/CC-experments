# Making Things — Blender → Godot export helpers (MIT)

Lightweight Blender 3.6+ addon so humans or AI agents can prepare assets for Godot
**without** depending on the paid Blender-Godot Pipeline panel or GPL Goblend.

## What it does

| Action | Effect |
|--------|--------|
| Apply Godot name suffix | `-col`, `-convcol`, `-colonly`, `-navmesh`, … |
| Set `collision` custom property | glTF extras consumed by MIT `addons/gltf_pipeline` |
| Set `name_override` | Renames node on import via gltf_pipeline |
| Export glTF for Godot | Y-up, extras on, apply modifiers, visible objects |

## Install

1. Zip this folder (must contain `__init__.py`) **or** point Blender at the folder.
2. Blender → *Edit → Preferences → Add-ons → Install…*
3. Enable **Making Things: Godot glTF Export**.
4. Sidebar **Godot MT** tab in the 3D View.

## Godot side

```bash
cp -a third_party/gltf_pipeline your_project/addons/gltf_pipeline
# Project Settings → Plugins → enable glTF Pipeline
```

Then place exports under `res://art/` and use MCP:

- `godot_asset_import_asset` / `godot_asset_import_reimport`
- `godot_asset_import_diagnose`
- prompt `fix_import` / skill `making-things-godot-blender-import`

## Related (optional)

- **Goblend** (`third_party/goblend`, GPL-3.0) — richer collection-based collisions; accept GPL if enabled.
- **Blender-Godot Pipeline** (paid Superhive addon) — fuller extras authoring UI; Godot runtime already MIT-vendored as `gltf_pipeline`.
