"""Fake Godot addon world for mock/dry-run agent evals (no live editor)."""

from __future__ import annotations

from typing import Any

from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope


class MakingThingsFakeWorld:
    """Stateful responder covering diagnose / playtest / import tool paths."""

    def __init__(self) -> None:
        self.scripts: dict[str, str] = {}
        self.playing = False
        self.imports: dict[str, dict[str, Any]] = {}
        self.live_props: dict[tuple[str, str], Any] = {}

    def __call__(self, cmd: CommandEnvelope) -> ResponseEnvelope | None:
        p = cmd.params or {}
        match cmd.command:
            case "cmd_get_project_info":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "name": "MakingThingsEval",
                        "godot_version": "4.7.2-stable",
                        "main_scene": "res://scenes/main.tscn",
                        "project_path": "/tmp/making_things_eval",
                        "autoloads": {},
                        "input_actions": [],
                        "csharp_supported": False,
                        "csharp_project": False,
                        "csharp_build": False,
                    },
                )
            case "cmd_write_script":
                path = str(p.get("script_path", ""))
                content = str(p.get("content", ""))
                existed = path in self.scripts
                self.scripts[path] = content
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "script_path": path,
                        "created": not existed,
                        "overwrote": existed,
                        "previous_existed": existed,
                    },
                )
            case "cmd_read_script":
                path = str(p.get("script_path", ""))
                if path not in self.scripts:
                    return ResponseEnvelope.failure(
                        cmd.id, "RESOURCE_NOT_FOUND", f"No script at '{path}'."
                    )
                return ResponseEnvelope.success(
                    cmd.id, {"script_path": path, "content": self.scripts[path]}
                )
            case "cmd_list_scripts":
                lang = str(p.get("language", "gd"))
                ext = ".gd" if lang == "gd" else ".cs"
                scripts = sorted(s for s in self.scripts if s.endswith(ext))
                return ResponseEnvelope.success(
                    cmd.id, {"directory": p.get("directory", "res://"), "scripts": scripts}
                )
            case "cmd_get_scan_state":
                return ResponseEnvelope.success(cmd.id, {"scanning": False})
            case "cmd_play_scene":
                self.playing = True
                return ResponseEnvelope.success(
                    cmd.id, {"playing": True, "scene_path": p.get("scene_path")}
                )
            case "cmd_stop_scene":
                self.playing = False
                return ResponseEnvelope.success(cmd.id, {"playing": False})
            case "cmd_is_playing":
                return ResponseEnvelope.success(cmd.id, {"playing": self.playing})
            case "cmd_set_runtime_property":
                node = str(p.get("node_path", ""))
                prop = str(p.get("property", ""))
                dry = bool(p.get("dry_run", False))
                value = p.get("value")
                key = (node, prop)
                previous = self.live_props.get(key, True if prop == "visible" else None)
                if not dry:
                    self.live_props[key] = value
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "ready": True,
                        "ok": True,
                        "node_path": node,
                        "property": prop,
                        "value": value if dry else self.live_props.get(key, value),
                        "previous_value": previous,
                        "dry_run": dry,
                        "persisted": False,
                        "undoable": True,
                        "channel": "runtime_probe",
                        "error": "",
                        "hint": "Live game state only.",
                    },
                )
            case "cmd_get_game_output":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "entries": [],
                        "total": 0,
                        "dropped": 0,
                        "next_seq": 0,
                    },
                )
            case "cmd_import_asset":
                target = str(p.get("target_path", "res://art/imported.glb"))
                self.imports[target] = {"status": "ok", "source": p.get("source")}
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "target_path": target,
                        "imported": True,
                        "ok": True,
                    },
                )
            case "cmd_get_import_status":
                path = str(p.get("path", ""))
                st = self.imports.get(path, {"status": "unknown"})
                return ResponseEnvelope.success(
                    cmd.id, {"path": path, "status": st.get("status", "unknown"), "ok": True}
                )
            case "cmd_get_scene_tree":
                return ResponseEnvelope.success(
                    cmd.id,
                    {
                        "root": {
                            "name": "Main",
                            "type": "Node3D",
                            "children": [
                                {"name": "sample_eval", "type": "Node3D", "children": []}
                            ],
                        }
                    },
                )
            case "cmd_get_active_scene":
                return ResponseEnvelope.success(
                    cmd.id, {"is_open": True, "scene_path": "res://scenes/main.tscn"}
                )
        # Unknown → let FakeAddonConnection base/bootstrap handle ping etc.
        return ResponseEnvelope.failure(
            cmd.id, "VALIDATION_ERROR", f"Unknown command '{cmd.command}'."
        )
