"""Making Things decision G — runtime live property result honesty fields."""

from __future__ import annotations

from mcp_server.models.runtime_inspect import SetRuntimePropertyResult


def test_set_runtime_property_result_defaults_are_runtime_honest() -> None:
    result = SetRuntimePropertyResult(
        ready=True,
        ok=True,
        node_path="/root/Main",
        property="visible",
        value=False,
        previous_value=True,
        dry_run=False,
        persisted=False,
        undoable=True,
        channel="runtime_probe",
        hint="Live game state only.",
    )
    assert result.persisted is False
    assert result.channel == "runtime_probe"
    assert result.undoable is True
    assert result.previous_value is True
