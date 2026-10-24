# C# / .NET Godot support (decision F)

Making Things v1 supports **Godot .NET** projects alongside GDScript.

## Editor binary

Use the official **mono / .NET** editor build matching the standard pin
(**4.7.2-stable**):

- Linux: `Godot_v4.7.2-stable_mono_linux_x86_64.zip`
- Requires a compatible .NET SDK (Godot 4.x typically .NET 8)

Download helper: `scripts/download_godot.sh` (standard + mono).

Point the MCP server at the mono binary:

```bash
export GODOT_MCP_GODOT_BIN=/path/to/Godot_v4.7.2-stable_mono_linux_x86_64/Godot_v4.7.2-stable_mono_linux.x86_64
```

## What the stack already does (from upstream hybridindie)

- `godot_scripts_*` accepts `.cs` list/read/write (full-file write)
- `godot_get_server_info().bridge.backend` reports:
  - `csharp_supported` — `CSharpScript` in ClassDB (editor is a .NET build)
  - `csharp_project` — a `.csproj` exists under `res://`
  - `csharp_build` — build integration (upstream Phase 2; treat as best-effort)
- `.cs` writes land bytes but need an **MSBuild** before they are usable;
  `godot --check-only` does **not** validate C#

## Fixture

`fixtures/godot_csharp_project/` is a minimal .NET Godot project used for smoke
checks (project loads; ClassDB reports C# when using the mono editor).

## Agent guidance

Prefer GDScript for rapid editor-automation loops. Use C# when the game project
is already .NET; after writing `.cs`, tell the user (or invoke build tooling) to
rebuild before expecting runtime behavior.
