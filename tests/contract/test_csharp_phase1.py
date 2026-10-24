"""Contract tests for C# Phase 1: language-aware script authoring + gate (issue #207).

The scripts surface becomes language-aware: read/write/list/patch accept ``.cs``
paths (default remains GDScript; existing contracts unchanged), ``list_scripts``
gains a ``language`` param, a capability probe rides ``cmd_get_project_info``
(``csharp_supported`` = .NET editor build; ``csharp_project`` = ``.csproj`` in
``res://``), ``get_server_info`` surfaces the backend, and ``.cs`` writes return
an explicit validate-via-build hint instead of a false parse-OK.
"""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP

from mcp_server.bridge import Bridge
from mcp_server.config import ServerConfig
from mcp_server.models.envelope import CommandEnvelope, ResponseEnvelope
from mcp_server.server import create_server
from tests.fakes import FakeAddonConnection, connector_for

pytestmark = pytest.mark.asyncio


def _responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
    p = cmd.params
    match cmd.command:
        case "cmd_get_project_info":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "name": "demo",
                    "godot_version": "4.7.2",
                    "main_scene": "res://main.tscn",
                    "autoloads": {},
                    "input_actions": [],
                    # The Phase 1 capability probe (#207).
                    "csharp_supported": True,  # .NET editor build (fake)
                    "csharp_project": True,  # a .csproj exists in res://
                },
            )
        case "cmd_read_script":
            if p.get("script_path", "").endswith(".cs"):
                return ResponseEnvelope.success(
                    cmd.id, {"script_path": p["script_path"], "content": "// C# script"}
                )
            return ResponseEnvelope.success(
                cmd.id, {"script_path": p["script_path"], "content": "extends Node"}
            )
        case "cmd_list_scripts":
            scripts = (
                ["res://enemy.cs", "res://player.cs"]
                if p.get("language") == "cs"
                else ["res://player.gd", "res://main.gd"]
            )
            return ResponseEnvelope.success(
                cmd.id, {"directory": p.get("directory", "res://"), "scripts": scripts}
            )
        case "cmd_write_script":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "script_path": p["script_path"],
                    "created": True,
                    "overwrote": False,
                    "previous_existed": False,
                },
            )
        case "cmd_patch_script":
            return ResponseEnvelope.success(
                cmd.id, {"script_path": p["script_path"], "replacements": 2}
            )
    return ResponseEnvelope.failure(cmd.id, "VALIDATION_ERROR", "unexpected")


def _build() -> tuple[FastMCP, FakeAddonConnection]:
    conn = FakeAddonConnection(responder=_responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    return create_server(ServerConfig(), bridge=bridge), conn


async def test_write_script_accepts_cs_path() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_write",
            {"script_path": "res://scripts/player.cs", "content": "partial class Player {}"},
        )
    sc = result.structured_content
    assert sc["created"] is True
    assert conn.last_command().params["script_path"] == "res://scripts/player.cs"


async def test_write_script_cs_carries_build_hint() -> None:
    """A .cs write succeeds but must say 'validate via build' — never a false
    parse-OK (Phase 1 has no C# build yet)."""
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_write",
            {"script_path": "res://a.cs", "content": "class A {}"},
        )
    sc = result.structured_content
    assert sc["created"] is True
    assert "build" in (sc.get("hint") or "").lower()


async def test_write_script_gd_has_no_build_hint() -> None:
    """The GDScript contract is unchanged: no validate-via-build hint on .gd writes."""
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_write",
            {"script_path": "res://a.gd", "content": "extends Node"},
        )
    assert "hint" not in (result.structured_content or {})


async def test_write_script_dry_run_cs_carries_build_hint() -> None:
    """A dry-run of a .cs write must carry the same build hint — a preview must
    predict the real run's guidance (PR #559 review)."""
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_write",
            {"script_path": "res://a.cs", "content": "class A {}", "dry_run": True},
        )
    sc = result.structured_content
    assert sc["dry_run"] is True
    assert "build" in (sc.get("hint") or "").lower()


async def test_read_script_accepts_cs() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_read", {"script_path": "res://a.cs"}
        )
    assert result.structured_content["content"] == "// C# script"


async def test_list_scripts_language_cs() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_list", {"language": "cs"}
        )
    assert result.structured_content["scripts"] == ["res://enemy.cs", "res://player.cs"]
    assert conn.last_command().params["language"] == "cs"


async def test_list_scripts_language_default_gd() -> None:
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        await client.call_tool("godot_scripts_list", {})
    params = conn.last_command().params
    assert params["language"] == "gd"  # default preserved


async def test_patch_script_routes_cs_phase2() -> None:
    """Phase 2: .cs patch is allowed and routed to the addon (build still required
    before the change is loadable — see godot_scripts_build_csharp)."""
    server, conn = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool(
            "godot_scripts_patch",
            {"script_path": "res://a.cs", "find": "class A", "replace": "class B"},
        )
    assert result.structured_content["script_path"] == "res://a.cs"
    assert conn.last_command().command == "cmd_patch_script"


async def test_server_info_surfaces_backend() -> None:
    server, _ = _build()
    async with Client(server) as client:
        await client.call_tool("godot_enable_toolset", {"category": "scripts"})
        result = await client.call_tool("godot_get_server_info", {})
    bridge_info = result.structured_content["bridge"]
    backend = bridge_info["backend"]
    assert backend["csharp_supported"] is True
    assert backend["csharp_project"] is True
    # Fake addon omits csharp_build → False (older addon / no Phase 2 probe).
    assert backend["csharp_build"] is False


async def test_server_info_surfaces_csharp_build_when_addon_reports_it() -> None:
    def responder(cmd: CommandEnvelope) -> ResponseEnvelope | None:
        if cmd.command == "cmd_get_project_info":
            return ResponseEnvelope.success(
                cmd.id,
                {
                    "name": "demo",
                    "godot_version": "4.7.2.mono",
                    "csharp_supported": True,
                    "csharp_project": True,
                    "csharp_build": True,
                },
            )
        return _responder(cmd)

    conn = FakeAddonConnection(responder=responder)
    bridge = Bridge(ServerConfig().bridge, connector=connector_for(conn))
    server = create_server(ServerConfig(), bridge=bridge)
    async with Client(server) as client:
        result = await client.call_tool("godot_get_server_info", {})
    assert result.structured_content["bridge"]["backend"]["csharp_build"] is True