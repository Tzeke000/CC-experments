"""Script read/patch tools (issue #10).

Lets an agent read, list, write, and patch GDScript, and check a script for parse
errors — the authoring half of the build/verify/fix loop. Read/write/patch route
through the addon (single path; the editor re-scans after writes, and writes are
UndoRedo-reversible). ``get_parse_errors`` shells out to ``godot --check-only``
(via the runner) because Godot exposes no in-editor API for structured parse
errors. All in the gated ``scripts`` toolset.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.bridge import Bridge
from mcp_server.categories import SCRIPTS_TAG
from mcp_server.config import ServerConfig
from mcp_server.models.scripts import (
    BuildCsharpResult,
    NodeScript,
    ParseCheckResult,
    PatchScriptResult,
    ScriptContent,
    ScriptList,
    WriteScriptResult,
)
from mcp_server.output import paginate
from mcp_server.paths import ResPath
from mcp_server.runtime import Runner, resolve_project_dir
from mcp_server.safety import (
    MUTATING,
    READ_ONLY,
    enforce_preconditions,
    require_godot_binary,
)
from mcp_server.scripts_parse import parse_check_errors
from mcp_server.tools._route import route, run_or_preview, validate_or_raise

SCRIPTS = {SCRIPTS_TAG}
DEFAULT_PAGE_LIMIT = 200


async def _script_exists(bridge: Bridge, script_path: str) -> bool:
    """Read-only existence probe for a script (for write_script's dry_run overwrite
    signal). Reads the file; a successful read means it exists (#205)."""
    response = await bridge.send("cmd_read_script", {"script_path": script_path})
    return bool(response.ok)


def register_scripts(mcp: FastMCP, bridge: Bridge, config: ServerConfig, runner: Runner) -> None:
    """Register the script read/patch tools."""

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    async def read_script(script_path: ResPath) -> ScriptContent:
        """Read the full text of the script at ``script_path`` (a ``res://`` path,
        ``.gd`` or ``.cs``)."""
        return ScriptContent(**await route(bridge, "cmd_read_script", {"script_path": script_path}))

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    async def list_scripts(
        directory: ResPath = "res://",
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=1000)] = DEFAULT_PAGE_LIMIT,
        language: Literal["gd", "cs"] = "gd",
    ) -> ScriptList:
        """List script files under ``directory`` (recursive, ``res://`` path) for a
        backend: ``language="gd"`` (default) lists ``.gd``, ``"cs"`` lists ``.cs``
        (C# support: issue #207 Phase 1).

        Paginated: ``scripts`` is a window of ``total`` files starting at ``offset``
        (default page ``limit`` 200). When ``truncated``, pass ``next_offset`` to page on.
        """
        result = ScriptList(
            **await route(
                bridge, "cmd_list_scripts", {"directory": directory, "language": language}
            )
        )
        result = ScriptList(
            **await route(
                bridge, "cmd_list_scripts", {"directory": directory, "language": language}
            )
        )
        window, total, truncated, next_offset = paginate(result.scripts, offset, limit)
        result.scripts = window
        result.total = total
        result.returned = len(window)
        result.truncated = truncated
        result.next_offset = next_offset
        return result

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    async def get_script_for_node(node_path: str = "") -> NodeScript:
        """Get the script attached to a node (by scene-relative ``node_path``, or the
        selected node when omitted). ``script_path``/``content`` are null if none.
        """
        result = await route(bridge, "cmd_get_script_for_node", {"node_path": node_path})
        return NodeScript(**result)

    @mcp.tool(meta=MUTATING, tags=SCRIPTS, output_schema=WriteScriptResult.model_json_schema())
    async def write_script(
        script_path: ResPath, content: str, dry_run: bool = False
    ) -> WriteScriptResult:
        """Create or overwrite the script at ``script_path`` (``res://``, ``.gd`` or
        ``.cs``) with ``content``. Reversible via the editor's undo. ``dry_run=True``
        writes nothing and reports ``would_overwrite`` so the agent knows whether it is
        about to replace an existing script. A real run reports what happened:
        ``created`` on a fresh file, ``overwrote``/``previous_existed`` when an existing
        script was replaced.

        C# (``.cs``) writes land the bytes but are NOT usable until a build — the
        result carries a ``hint`` saying to validate via a C# build (Phase 2; issue
        #207). GDScript is validated via ``get_parse_errors``.
        """
        params = {"script_path": script_path, "content": content}
        if script_path.endswith(".cs"):
            # A preview must predict the real run's guidance (PR #559 review):
            # the build hint rides the dry-run too.
            build_hint = (
                "C# script written but NOT yet usable until a build. Call "
                "godot_scripts_build_csharp (or `dotnet build` on the .csproj). "
                "godot_scripts_get_parse_errors does not cover .cs."
            )
        else:
            build_hint = None
        if dry_run:
            # Validate the path BEFORE probing — a dry-run must not bypass the
            # res:// containment check and read a file outside the project (#205).
            await validate_or_raise(bridge, "cmd_write_script", params)
            exists = await _script_exists(bridge, script_path)
            return WriteScriptResult(
                script_path=script_path,
                created=not exists,
                would_overwrite=exists,
                previous_existed=exists,
                hint=build_hint,
                dry_run=True,
            )
        result = WriteScriptResult(**await route(bridge, "cmd_write_script", params))
        result.hint = build_hint
        return result

    @mcp.tool(meta=MUTATING, tags=SCRIPTS)
    async def patch_script(
        script_path: ResPath, find: str, replace: str, dry_run: bool = False
    ) -> PatchScriptResult:
        """Replace every occurrence of ``find`` with ``replace`` in the script
        (``.gd`` or ``.cs``). Errors if ``find`` isn't present. Reversible via undo;
        ``dry_run`` previews. A ``.cs`` patch needs ``godot_scripts_build_csharp``
        before it is loadable (issue #207 Phase 2)."""
        params = {"script_path": script_path, "find": find, "replace": replace}
        preview = {
            "script_path": script_path,
            "replacements": 0,
            "hint": (
                "C# patch preview — call godot_scripts_build_csharp after a real run."
                if script_path.endswith(".cs")
                else None
            ),
        }
        return await run_or_preview(
            dry_run, PatchScriptResult, preview, bridge, "cmd_patch_script", params
        )

    @mcp.tool(meta=MUTATING, tags=SCRIPTS)
    async def build_csharp(
        configuration: Annotated[str, Field(description="MSBuild configuration")] = "Debug",
        dry_run: bool = False,
    ) -> BuildCsharpResult:
        """Build the project's C# assembly via ``dotnet build`` (issue #207 Phase 2).

        Requires a Godot .NET/mono editor, a ``.csproj`` under ``res://``, and the
        .NET SDK (``dotnet``) on PATH. Prefer this after ``write_script`` /
        ``patch_script`` on ``.cs`` files — until the build succeeds the new code
        is invisible to the game.

        WHEN TO USE: validate C# after authoring. WHEN NOT TO USE: GDScript —
        use ``get_parse_errors`` instead.
        """
        project_dir = Path(await resolve_project_dir(bridge, config))
        csprojs = sorted(project_dir.glob("*.csproj"))
        if not csprojs:
            raise ToolError(
                "PRECONDITION_FAILED: No .csproj at the project root — not a C# Godot project."
            )
        csproj = csprojs[0]
        if not shutil.which("dotnet"):
            raise ToolError(
                "PRECONDITION_FAILED: dotnet CLI not found on PATH. Install .NET 8 SDK."
            )
        if dry_run:
            return BuildCsharpResult(
                ok=True,
                exit_code=0,
                csproj=f"res://{csproj.name}",
                configuration=configuration,
                output="",
                hint=f"Would run: dotnet build {csproj} -c {configuration}",
                dry_run=True,
            )
        # Prefer the addon path when connected (editor-local env); fall back to
        # a host-side ``dotnet build`` so smoke/CI works without a live peer.
        if bridge.connected:
            try:
                result = await route(
                    bridge,
                    "cmd_build_csharp",
                    {"configuration": configuration},
                )
                return BuildCsharpResult(**result)
            except ToolError:
                pass
        proc = await asyncio.to_thread(
            subprocess.run,
            ["dotnet", "build", str(csproj), "-c", configuration, "-v", "q"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        joined = (proc.stdout or "") + (proc.stderr or "")
        return BuildCsharpResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            csproj=f"res://{csproj.name}",
            configuration=configuration,
            output=joined.strip(),
            hint=(
                "Build succeeded — reload the scene/game to pick up C# changes."
                if proc.returncode == 0
                else "Build failed — see output; fix .cs then retry."
            ),
        )

    @mcp.tool(meta=READ_ONLY, tags=SCRIPTS)
    @enforce_preconditions
    async def get_parse_errors(script_path: ResPath) -> ParseCheckResult:
        """Parse-check ``script_path`` and return structured errors (message + line),
        or an empty list when it parses cleanly. Use after writing/patching a script.

        Scope honesty (#423): this checks GDScript *syntax* — it does NOT catch
        class-API misuse (a nonexistent member parses clean and fails at runtime).
        For that, run the project: ``godot_runtime_run_and_capture`` reports the
        runtime errors (the recommended full-verification pattern); the shader
        analogue is ``godot_shader_validate``.
        """
        require_godot_binary(runner.binary)
        if script_path.endswith(".cs"):
            # Phase 2 honesty (#207): still no GDScript-style parse for C# —
            # point agents at the build primitive instead of a false parse-OK.
            raise ToolError(
                "VALIDATION_ERROR: get_parse_errors checks GDScript syntax only. "
                "For C#, call godot_scripts_build_csharp (issue #207 Phase 2)."
            )
        project_dir = await resolve_project_dir(bridge, config)
        # #453: the check's subprocess reads global_script_class_cache.cfg from
        # disk, and the editor's scan after a write (issue #417) is asynchronous.
        # Wait — bounded — for the scan to flush so the read is deterministic;
        # if it is still scanning, the result carries rescan_pending=true so the
        # agent knows a fresh class_name error may be stale-cache, not real.
        rescan_pending = await _wait_for_scan_quiet(bridge)
        output = await runner.check_script(project_dir, script_path, timeout=30.0)
        errors = parse_check_errors(output.stdout + "\n" + output.stderr)
        return ParseCheckResult(
            script_path=script_path, ok=not errors, errors=errors,
            rescan_pending=rescan_pending,
        )


async def _wait_for_scan_quiet(
    bridge: Bridge, max_wait_s: float = 2.0, poll_s: float = 0.05
) -> bool:
    """Wait (bounded) for the editor's filesystem scan to finish. Returns whether
    a scan was still in flight when the budget ran out (issue #453).

    Never raises: the scan-state probe is best-effort — an unreachable bridge
    just means no scan knowledge, so the check proceeds without gating.
    """
    try:
        for _ in range(max(1, int(max_wait_s / poll_s))):
            response = await bridge.send("cmd_get_scan_state", timeout=2.0)
            if not response.ok or not (response.result or {}).get("scanning"):
                return False
            await asyncio.sleep(poll_s)
        return True
    except Exception:
        return False
