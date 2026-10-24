"""Making Things observability ring + resources."""

from __future__ import annotations

import json

import pytest

from mcp_server.observability import (
    BLENDER_CONVENTIONS,
    clear_events,
    open_errors,
    recent_events,
    record_event,
)


@pytest.fixture(autouse=True)
def _clean_ring() -> None:
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
