"""Making Things observability tools — recent logs + open errors."""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from mcp_server.bridge import Bridge
from mcp_server.categories import CORE_TAG
from mcp_server.observability import open_errors, recent_events
from mcp_server.safety import READ_ONLY


class LogEventsResult(BaseModel):
    events: list[dict] = Field(default_factory=list)
    next_seq: int = 0
    truncated: bool = False
    count: int = 0


class OpenErrorsResult(BaseModel):
    errors: list[dict] = Field(default_factory=list)
    count: int = 0


def register_observability_tools(mcp: FastMCP, bridge: Bridge) -> None:
    """Register diagnose-loop helpers (always-on core)."""

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def get_recent_logs(
        since_seq: int = 0,
        level: str = "",
        limit: int = 100,
    ) -> LogEventsResult:
        """Return recent structured MCP/bridge events (Making Things observability).

        Each event has ``seq``, ``ts``, ``source``, ``level``, ``code``, ``message``,
        ``corr`` (includes ``bridge_id`` / ``command``), and optional ``data``.
        Pass ``since_seq`` from a previous ``next_seq`` for incremental reads.
        Filter with ``level`` = ``error`` / ``warn`` / ``info``.
        """
        _ = bridge  # available for future game-output merge
        payload = recent_events(
            since_seq=since_seq,
            level=level or None,
            limit=max(1, min(limit, 500)),
        )
        return LogEventsResult(**payload)

    @mcp.tool(meta=READ_ONLY, tags={CORE_TAG})
    async def get_open_errors(limit: int = 50) -> OpenErrorsResult:
        """Return recent error/warning events for diagnose-and-fix loops.

        Prefer this (or ``godot://errors/open``) before guessing; then enable
        ``scripts`` / ``runtime`` toolsets and follow the ``debug_scene`` /
        ``playtest_loop`` prompts. Also check ``godot_runtime_get_game_output``
        while a play session is active.
        """
        return OpenErrorsResult(**open_errors(limit=max(1, min(limit, 200))))
