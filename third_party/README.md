# Third-party Blender → Godot pipelines (decision E)

Default interchange remains **glTF/glb** (decision D). Making Things ships an
MIT Blender helper plus the MIT Godot extras runtime; Goblend stays optional GPL.

## Chosen paths

### 0. Making Things Blender export helpers (MIT) — default agent path

- `third_party/mt_blender_export/` — Godot name suffixes, `collision` /
  `name_override` custom properties (gltf_pipeline extras), Export glTF for Godot
- Install in Blender 3.6+ via Preferences → Add-ons → Install (see that folder’s README)
- Does **not** replace Goblend or the paid Blender-Godot Pipeline panel

### 1. Goblend (GPL-3.0) — full Blender↔Godot export UX

- Vendored at `third_party/goblend/` from
  [Togira123/Goblend-Export-Addon](https://github.com/Togira123/Goblend-Export-Addon)
- Contains Blender addon sources + Godot addon (`goblend-godot/addons/goblend/`)
- **License: GPL-3.0** — optional; do not merge into MIT-licensed MCP server code.
  Copy the Godot addon into a project only when you accept GPL for that addon tree.
- Docs: https://goblend.dev

**Install into a Godot project**

```bash
cp -a third_party/goblend/goblend-godot/addons/goblend your_project/addons/
# Enable "Goblend" in Project → Project Settings → Plugins
# Install the Blender side from Blender Extensions or this tree per Goblend docs
```

### 2. glTF Pipeline / Blender-Godot Pipeline runtime (MIT) — extras on import

- Vendored at `third_party/gltf_pipeline/` from
  [zheqd/blender-godot-pipeline](https://github.com/zheqd/blender-godot-pipeline)
  (`addons/gltf_pipeline`, MIT)
- Applies glTF `extras` (collision flags, scripts, packed scenes, …) in
  `GLTFDocumentExtension._import_post`
- **Blender authoring addon** that writes those extras is a **separate paid**
  product (SuperHive / bikemurt). CI fixtures use hand-authored glTF extras JSON
  so we do not depend on the paid Blender addon for tests.

**Install**

```bash
cp -a third_party/gltf_pipeline your_project/addons/gltf_pipeline
# Enable "glTF Pipeline" in Project Settings → Plugins
```

## Fixture project wiring

`fixtures/godot_project/` enables the MIT `gltf_pipeline` addon and ships sample
`.glb` / `.gltf` assets. Goblend is documented and available under `third_party/`
but not enabled by default (GPL boundary).
