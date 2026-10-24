# C# / .NET Godot support (decision F)

Making Things v1 supports **Godot .NET** projects alongside GDScript.

## Editor binary

Use the official **mono / .NET** editor build matching the standard pin
(**4.7.2-stable**):

- Linux: `Godot_v4.7.2-stable_mono_linux_x86_64.zip`
- Requires a compatible .NET SDK (Godot 4.x → **.NET 8**)

Download helper: `scripts/download_godot.sh` (standard + mono).

Point the MCP server at the mono binary:

```bash
export GODOT_MCP_GODOT_BIN=/path/to/Godot_v4.7.2-stable_mono_linux_x86_64/Godot_v4.7.2-stable_mono_linux.x86_64
# Ensure the SDK is on PATH (user-local install example):
export PATH="$HOME/.dotnet:$PATH"
export DOTNET_ROOT="$HOME/.dotnet"
```

## Capability probe (`godot_get_server_info().bridge.backend`)

| Field | Meaning |
|-------|---------|
| `csharp_supported` | `CSharpScript` in ClassDB (editor is a .NET build) |
| `csharp_project` | a `.csproj` exists under `res://` |
| `csharp_build` | Phase 2: `dotnet` CLI available **and** supported + project (addon probe) |

## Phase 2 build primitive

- MCP tool: **`godot_scripts_build_csharp`** → `dotnet build` on the project `.csproj`
  (host-side fallback when the editor peer is unavailable; addon `cmd_build_csharp` when connected)
- After `godot_scripts_write` / `godot_scripts_patch` on `.cs`, call `godot_scripts_build_csharp`
  before expecting the game to load the new code
- `godot_scripts_get_parse_errors` still refuses `.cs` (no false GDScript-style parse-OK) —
  use the build tool instead
- `.cs` **patch** is allowed when `csharp_build` is ready; still requires a follow-up build

## Fixture + smoke

```bash
bash scripts/csharp_fixture_smoke.sh
```

`fixtures/godot_csharp_project/` is a minimal .NET Godot project. The smoke:

1. Imports the fixture with the **mono** editor
2. Asserts `csharp_supported` + `.csproj` present
3. Runs `dotnet build` when the SDK is on PATH (`CSHARP_SMOKE_OK`)

## Agent guidance

Prefer GDScript for rapid editor-automation loops. Use C# when the game project
is already .NET; after writing `.cs`, call `godot_scripts_build_csharp` (or tell
the user to rebuild) before expecting runtime behavior.
