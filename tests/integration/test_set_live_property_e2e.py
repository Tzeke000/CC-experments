"""Live e2e: godot_runtime_set_live_property / cmd_set_runtime_property (decision G).

Play a scratch scene with the runtime probe, then mutate a live Button property
while the game is running. Asserts honesty fields:

- ``persisted=false`` (game process only — never rewrites the edited .tscn)
- ``previous_value`` present for undo
- ``dry_run=true`` previews without writing
- undo by re-setting ``previous_value`` restores the prior live value
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pytest

from mcp_server.bridge import Bridge
from mcp_server.config import BridgeConfig
from tests.integration._godot import (
    GODOT_BIN,
    GODOT_PROJECT,
    e2e_bridge_url,
    needs_display,
    serve_and_await_editor,
    wait_probe_connected,
)

pytestmark = [
    pytest.mark.skipif(GODOT_BIN is None, reason="Godot binary not installed"),
    needs_display,
]

BRIDGE_URL = e2e_bridge_url()
SCRATCH = "res://tmp_e2e_set_live_property.tscn"
SCRATCH_FILE = GODOT_PROJECT / "tmp_e2e_set_live_property.tscn"
PROJECT_GODOT = GODOT_PROJECT / "project.godot"
PROBE = "res://addons/godot_mcp/mcp_runtime_probe.gd"


async def _ok(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await bridge.send(command, params)
    assert response.ok and response.result is not None, (
        f"{command}: {response.error} {response.hint}"
    )
    return response.result


async def _wait_scene_open(bridge: Bridge) -> None:
    for _ in range(40):
        r = await bridge.send("cmd_get_active_scene")
        if r.ok and (r.result or {}).get("is_open"):
            return
        await asyncio.sleep(0.25)
    raise AssertionError("scene did not open")


async def _poll(bridge: Bridge, command: str, params: dict[str, Any]) -> dict[str, Any]:
    # Same headless ~1 fps budget as runtime_inspect_e2e (90 x 0.2s).
    for _ in range(90):
        r = await _ok(bridge, command, params)
        if r.get("ready"):
            return r
        await asyncio.sleep(0.2)
    raise AssertionError(f"{command} never became ready")


async def _run() -> None:
    bridge = Bridge(BridgeConfig(url=BRIDGE_URL))
    if not await serve_and_await_editor(bridge):
        raise AssertionError("the addon never connected to the bridge")

    try:
        await _ok(bridge, "cmd_create_scene", {"root_type": "Node2D", "scene_path": SCRATCH})
        await _wait_scene_open(bridge)
        await _ok(
            bridge, "cmd_create_node", {"parent_path": ".", "node_type": "Button", "name": "Start"}
        )
        await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Start", "property": "text", "value": "Play"},
        )
        await _ok(
            bridge,
            "cmd_set_node_property",
            {"node_path": "Start", "property": "visible", "value": True},
        )
        await _ok(bridge, "cmd_save_scene", {})

        # No play session → structured precondition failure
        no_session = await bridge.send(
            "cmd_set_runtime_property",
            {
                "node_path": "/root/x",
                "property": "visible",
                "value": False,
                "request_id": "e2e-set-pre",
            },
        )
        assert no_session.ok is False and no_session.error == "PRECONDITION_FAILED"

        await _ok(bridge, "cmd_register_autoload", {"name": "GodotMcpProbe", "path": PROBE})
        await _ok(bridge, "cmd_play_scene", {"scene_path": SCRATCH})
        await wait_probe_connected(bridge, timeout=30.0)

        found = await _poll(
            bridge, "cmd_find_ui_elements", {"class_filter": "Button", "request_id": "e2e-set-find"}
        )
        buttons = [e for e in found["elements"] if e["name"] == "Start"]
        assert buttons, f"Start button not found in {found['elements']}"
        button_path = buttons[0]["path"]

        # dry_run: coerce/preview without writing
        dry = await _poll(
            bridge,
            "cmd_set_runtime_property",
            {
                "node_path": button_path,
                "property": "visible",
                "value": False,
                "dry_run": True,
                "request_id": "e2e-set-dry",
            },
        )
        assert dry.get("ok") is True
        assert dry.get("dry_run") is True
        assert dry.get("persisted") is False
        assert dry.get("channel") == "runtime_probe"
        assert dry.get("undoable") is True
        assert dry.get("previous_value") is True
        assert dry.get("value") is False

        # Confirm dry_run did not mutate
        still = await _poll(
            bridge,
            "cmd_read_property",
            {"node_path": button_path, "property": "visible", "request_id": "e2e-set-read-1"},
        )
        assert still.get("error") == ""
        assert still.get("value") is True

        # Real live mutate
        written = await _poll(
            bridge,
            "cmd_set_runtime_property",
            {
                "node_path": button_path,
                "property": "visible",
                "value": False,
                "request_id": "e2e-set-write",
            },
        )
        assert written.get("ok") is True
        assert written.get("dry_run") is False
        assert written.get("persisted") is False, "live mutate must never claim disk persist"
        assert written.get("channel") == "runtime_probe"
        assert written.get("undoable") is True
        assert written.get("previous_value") is True
        assert written.get("value") is False
        assert "Live" in str(written.get("hint", "")) or "runtime" in str(
            written.get("hint", "")
        ).lower()

        after = await _poll(
            bridge,
            "cmd_read_property",
            {"node_path": button_path, "property": "visible", "request_id": "e2e-set-read-2"},
        )
        assert after.get("value") is False

        # Undo via previous_value
        undone = await _poll(
            bridge,
            "cmd_set_runtime_property",
            {
                "node_path": button_path,
                "property": "visible",
                "value": written["previous_value"],
                "request_id": "e2e-set-undo",
            },
        )
        assert undone.get("ok") is True
        assert undone.get("persisted") is False
        assert undone.get("value") is True

        restored = await _poll(
            bridge,
            "cmd_read_property",
            {"node_path": button_path, "property": "visible", "request_id": "e2e-set-read-3"},
        )
        assert restored.get("value") is True

        # Also mutate a string property (text) end-to-end
        text_set = await _poll(
            bridge,
            "cmd_set_runtime_property",
            {
                "node_path": button_path,
                "property": "text",
                "value": "Mutated",
                "request_id": "e2e-set-text",
            },
        )
        assert text_set.get("ok") is True
        assert text_set.get("persisted") is False
        assert text_set.get("previous_value") == "Play"
        assert text_set.get("value") == "Mutated"

        await _ok(bridge, "cmd_stop_scene", {})
    finally:
        await bridge.close()


def test_live_set_runtime_property() -> None:
    assert GODOT_BIN is not None
    snapshot = PROJECT_GODOT.read_bytes()
    editor = subprocess.Popen(
        [GODOT_BIN, "--headless", "--editor", "--path", str(GODOT_PROJECT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GODOT_MCP_BRIDGE_URL": BRIDGE_URL},
    )
    try:
        asyncio.run(_run())
    finally:
        editor.terminate()
        try:
            editor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            editor.kill()
        SCRATCH_FILE.unlink(missing_ok=True)
        PROJECT_GODOT.write_bytes(snapshot)
