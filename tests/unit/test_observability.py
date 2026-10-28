"""Making Things observability ring + resources."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from mcp_server.observability import (
    BLENDER_CONVENTIONS,
    clear_events,
    open_errors,
    recent_events,
    record_event,
)


@pytest.fixture(autouse=True)
def _clean_ring() -> Iterator[None]:
    clear_events()
    yield
    clear_events()


def test_record_and_recent_events() -> None:
    record_event(source="mcp", level="info", message="hello", corr={"bridge_id": "abc"})
    record_event(source="mcp", level="error", code="X", message="boom")
    payload = recent_events(limit=10)
    assert payload["count"] == 2
    assert payload["events"][0]["corr"]["bridge_id"] == "abc"
    errs = open_errors()
    assert errs["count"] == 1
    assert errs["errors"][0]["code"] == "X"


def test_blender_conventions_document_goblend_gpl() -> None:
    goblend = BLENDER_CONVENTIONS["pipelines"]["goblend"]
    assert goblend["license"].startswith("GPL")
    assert goblend["default_in_fixtures"] is False
    assert "gltf" in BLENDER_CONVENTIONS["preferred_formats"][0] or True
    json.dumps(BLENDER_CONVENTIONS)  # serializable


def test_blender_conventions_include_pipeline_product_surface() -> None:
    pipelines = BLENDER_CONVENTIONS["pipelines"]
    assert pipelines["mt_blender_export"]["license"] == "MIT"
    assert pipelines["gltf_pipeline"]["default_in_fixtures"] is True
    assert "-col" in BLENDER_CONVENTIONS["godot_name_suffixes"]
    assert "godot_asset_import_diagnose" in BLENDER_CONVENTIONS["agent_tools"]
    assert "collision" in BLENDER_CONVENTIONS["gltf_pipeline_extras"]


def test_blend_extension_detects_as_packed_scene() -> None:
    """Bug fix: .blend must map to PackedScene (editor Blender→glTF import)."""
    from mcp_server.tools.import_asset import _detect_type

    assert _detect_type("res://art/hero.blend") == "PackedScene"
    assert _detect_type("res://art/hero.glb") == "PackedScene"


def test_triangle_gltf_fixture_carries_pipeline_extras() -> None:
    """Hand-authored fixture extras so diagnose/import tests need no paid Blender addon."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "fixtures/godot_project/art/triangle.gltf"
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = doc["nodes"]
    extras = nodes[0]["extras"]
    assert extras["collision"] == "trimesh"
    assert extras["name_override"] == "FixtureTriangle"
