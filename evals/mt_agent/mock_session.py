"""In-process mock MCP tool surface for dry-run agent evals (no Godot, no LLM)."""

from __future__ import annotations

import re
from typing import Any

from evals.mt_agent.fake_world import MakingThingsFakeWorld
from evals.mt_agent.score import ToolCall


def _parse_errors_for(content: str) -> list[dict[str, Any]]:
    """Heuristic GDScript syntax probe for fixture scripts (not a full parser)."""
    errors: list[dict[str, Any]] = []
    if re.search(r"func\s+_ready\(\s*\n", content) or re.search(
        r"func\s+_ready\(\s*$", content, re.M
    ):
        errors.append(
            {
                "message": "Expected ')' after function parameters.",
                "source": None,
                "line": 2,
            }
        )
    if content.count("(") != content.count(")"):
        if not errors:
            errors.append({"message": "Unbalanced parentheses.", "source": None, "line": 1})
    return errors


class MockToolSession:
    """Executes a subset of Making Things MCP tools against ``MakingThingsFakeWorld``."""

    def __init__(self, world: MakingThingsFakeWorld | None = None) -> None:
        self.world = world or MakingThingsFakeWorld()
        self.enabled: set[str] = {"core", "inspection"}
        self.history: list[ToolCall] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> ToolCall:
        args = dict(arguments or {})
        try:
            result = await self._dispatch(name, args)
            call = ToolCall(name=name, arguments=args, ok=True, result=result)
        except Exception as exc:  # noqa: BLE001 — surface as tool error for scoring
            call = ToolCall(name=name, arguments=args, ok=False, error=str(exc), result=None)
        self.history.append(call)
        return call

    async def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        if name == "godot_enable_toolset":
            cat = str(args.get("category", ""))
            for part in cat.split(","):
                self.enabled.add(part.strip())
            return {"enabled": sorted(self.enabled), "category": cat}

        if name == "godot_scripts_write":
            path = str(args["script_path"])
            content = str(args["content"])
            existed = path in self.world.scripts
            self.world.scripts[path] = content
            return {
                "script_path": path,
                "created": not existed,
                "overwrote": existed,
                "previous_existed": existed,
            }

        if name == "godot_scripts_get_parse_errors":
            path = str(args["script_path"])
            content = self.world.scripts.get(path, "")
            if path not in self.world.scripts:
                raise RuntimeError(f"No script at {path}")
            errors = _parse_errors_for(content)
            return {"script_path": path, "ok": not errors, "errors": errors, "rescan_pending": False}

        if name == "godot_scripts_read":
            path = str(args["script_path"])
            return {"script_path": path, "content": self.world.scripts[path]}

        if name == "godot_runtime_play_scene":
            self.world.playing = True
            return {"playing": True, "scene_path": args.get("scene_path", "")}

        if name == "godot_runtime_stop_scene":
            self.world.playing = False
            return {"playing": False}

        if name == "godot_runtime_set_live_property":
            node = str(args["node_path"])
            prop = str(args["property"])
            dry = bool(args.get("dry_run", False))
            value = args.get("value")
            key = (node, prop)
            previous = self.world.live_props.get(key, True if prop == "visible" else None)
            if not self.world.playing:
                raise RuntimeError("PRECONDITION_FAILED: play session required")
            if not dry:
                self.world.live_props[key] = value
            return {
                "ready": True,
                "ok": True,
                "node_path": node,
                "property": prop,
                "value": value if dry else self.world.live_props.get(key, value),
                "previous_value": previous,
                "dry_run": dry,
                "persisted": False,
                "undoable": True,
                "channel": "runtime_probe",
                "error": "",
                "hint": "Live game state only.",
            }

        if name == "godot_asset_import_asset":
            target = str(args.get("target_path", "res://art/imported.glb"))
            self.world.imports[target] = {"status": "ok", "source": args.get("source")}
            return {"target_path": target, "imported": True, "ok": True}

        if name == "godot_asset_import_get_status":
            path = str(args.get("path", ""))
            st = self.world.imports.get(path, {"status": "unknown"})
            return {"path": path, "status": st.get("status", "unknown"), "ok": True}

        if name == "godot_inspection_get_scene_tree":
            return {
                "root": {
                    "name": "Main",
                    "type": "Node3D",
                    "children": [{"name": "sample_eval", "type": "Node3D", "children": []}],
                }
            }

        if name == "godot_get_open_errors":
            return {"errors": [], "count": 0}

        if name == "godot_get_server_info":
            return {
                "server": "godot-editor-mcp",
                "bridge": {"connected": True},
            }

        raise RuntimeError(f"mock session does not implement tool: {name}")


async def run_scripted_case(case_mock_script: list[dict[str, Any]]) -> list[ToolCall]:
    session = MockToolSession()
    for step in case_mock_script:
        await session.call_tool(str(step["tool"]), dict(step.get("arguments") or {}))
    return session.history
