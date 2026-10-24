---
name: making-things-godot-stack
description: How to use the Making Things Godot MCP + editor addon (morph of hybridindie godot-mcp) — auth, toolsets, honesty fields, live mutate, Blender import.
---

# Making Things Godot stack

## Before tools

1. Ensure Godot editor has the `godot_mcp` addon enabled and connected.
2. Bridge auth is **required**: set `GODOT_MCP_BRIDGE_TOKEN` (or use the minted file at `~/.config/making-things-godot/bridge.token`) on **both** server and editor.
3. Call `godot_get_server_info` / status first; enable only needed toolsets.

## Honesty fields

Mutation results include `persisted`, `undoable`, `reason`, `hint`. Never claim a change is saved when `persisted` is false (e.g. instanced children, or **runtime** live sets).

## Live play mutate (decision G)

- Inspect: `godot_runtime_get_game_scene_tree`, `godot_runtime_read_property`
- Write: `godot_runtime_set_live_property` — **runtime-only** (`persisted=false`); use `previous_value` to undo; prefer `dry_run` first.

## Blender → Godot (decisions D/E)

- Default assets: glTF/glb under `res://art/`
- MIT import extras: enable `addons/gltf_pipeline` (from `third_party/gltf_pipeline`)
- Optional GPL Goblend: see `third_party/README.md` — do not mix licensing casually
- After copy: reimport / await filesystem idle, then inspect the imported scene tree

## C# / .NET (decision F)

- Use Godot **mono** binary; see `docs/dotnet-csharp.md`
- `.cs` writes need an MSBuild before runtime use

## Observability

- Use game output / log tools during play; correlate bridge errors with dock status
- Prefer structured tool errors over guessing
