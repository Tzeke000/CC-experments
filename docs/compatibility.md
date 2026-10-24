# Compatibility

| Component | Version / note |
|-----------|----------------|
| Godot editor | **4.7.x** (pinned **4.7.2-stable** standard + mono) |
| Bridge envelope | Upstream hybridindie contract; additive Making Things commands (`cmd_set_runtime_property`) |
| Python | ≥3.11 |
| MCP package | `godot-editor-mcp` CLI (morph); FastMCP 4.x |
| Addon path | `addons/godot_mcp/` |
| Auth | `GODOT_MCP_BRIDGE_TOKEN` required by default |

Making Things deltas that agents must know: required bridge token; `godot_runtime_set_live_property`; `godot://logs/recent`, `godot://errors/open`, `godot://conventions/blender`.
