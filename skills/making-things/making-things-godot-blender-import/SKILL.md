---
name: making-things-godot-blender-import
description: Blender→Godot glTF import for Making Things — conventions resource, fixtures, gltf_pipeline (MIT), optional Goblend (GPL). Use fix_import prompt.
---

# Blender → Godot

1. Read `godot://conventions/blender`.
2. Export **glb/gltf** (default). `.blend` only if Blender is installed for the whole team.
3. Place under `res://art/`; reimport / await idle; inspect imported tree.
4. Fixture assets: `fixtures/godot_project/art/sample.glb` (+ triangle.*).
5. MIT `addons/gltf_pipeline` handles extras (collision flags, etc.).
6. **Goblend** (`third_party/goblend`, GPL-3.0) is optional — do not enable unless the project accepts GPL for that addon tree. See `third_party/README.md`.
7. Never claim import success without scene-tree evidence.
