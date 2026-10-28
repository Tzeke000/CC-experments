"""External asset import tools (issue #108).

Generic drop-in for external files (local paths or HTTP URLs) and PBR material
assembly. This is the open-source foundation for external AI content pipelines
(e.g. Meshy, Tripo) without hard-coding provider-specific logic.

Gated ``asset_import`` toolset.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.bridge import Bridge
from mcp_server.categories import ASSET_IMPORT_TAG
from mcp_server.constraints import TimeoutMs
from mcp_server.models.import_asset import (
    CreateMaterialResult,
    DiagnoseImportResult,
    ImportAssetResult,
    ImportOptions,
    ImportStatusResult,
    ReimportAssetsResult,
)
from mcp_server.paths import ResPath
from mcp_server.safety import MUTATING, READ_ONLY
from mcp_server.tools._route import route

ASSET_IMPORT = {ASSET_IMPORT_TAG}

# Extension → Godot type mapping (auto-detect on import).
_EXT_TO_TYPE: dict[str, str] = {
    ".png": "Texture2D",
    ".jpg": "Texture2D",
    ".jpeg": "Texture2D",
    ".webp": "Texture2D",
    ".svg": "Texture2D",
    ".glb": "PackedScene",
    ".gltf": "PackedScene",
    # Editor imports .blend via Blender→glTF (PackedScene). Prefer committing
    # .glb/.gltf so teammates need not install Blender (Godot ≥4.5 needs Blender
    # ≥3.5; older Blender fails on export_import_convert_lighting_mode).
    ".blend": "PackedScene",
    ".obj": "Mesh",
    ".fbx": "PackedScene",
    ".wav": "AudioStreamWAV",
    ".ogg": "AudioStreamOggVorbis",
    ".mp3": "AudioStreamMP3",
    ".tres": "Resource",
    ".res": "Resource",
    ".tscn": "PackedScene",
    ".scn": "PackedScene",
    ".gd": "GDScript",
    ".cs": "CSharpScript",
    ".gdshader": "Shader",
}


def _detect_type(path: str) -> str | None:
    """Auto-detect Godot resource type from file extension."""
    ext = Path(path).suffix.lower()
    return _EXT_TO_TYPE.get(ext)


def _require_res_path(path: str, field: str = "target_path") -> None:
    if not path.startswith("res://"):
        raise ToolError(f"VALIDATION_ERROR: '{field}' must start with 'res://' (got '{path}').")


# #419: metallic/roughness/emission_enabled are scalars on StandardMaterial3D, not
# textures — a numeric string is a scalar value; anything else for these channels
# is still accepted as a texture path (texture-driven roughness is legitimate).
_SCALAR_CHANNELS = ("metallic", "roughness", "emission_enabled")


def _is_scalar(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


async def _validate_material_params(bridge: Bridge, params: dict[str, Any]) -> None:
    """Validate the material channels BEFORE the (dry-run or real) bridge call (#419).

    Every texture-typed channel that carries a res:// path is probed for existence via
    ``cmd_search_files`` (a read-only recursive search) so a missing texture fails
    the call — a dry-run gets the same validation as the real run instead of a
    success-flavored empty preview. The search globs the *basename* (the addon's glob
    matches file names, not relative paths — verified on Godot 4.7) and passes only
    when a match's path ends with the requested ``res://`` path, so a different file
    sharing the basename can't satisfy the probe.
    """
    for channel in ("albedo", "normal", "roughness", "metallic", "ao", "emission"):
        value = str(params.get(channel, ""))
        if not value or _is_scalar(value):
            continue  # empty or scalar — nothing filesystem-backed to validate
        _require_res_path(value, field=channel)
        rel = value.removeprefix("res://")
        probe = await route(
            bridge, "cmd_search_files",
            {"directory": "res://", "name_glob": rel.rsplit("/", 1)[-1]},
        )
        matches = probe.get("matches") or []
        if not any(str(m).endswith(value) for m in matches):
            raise ToolError(
                f"RESOURCE_NOT_FOUND: Texture not found for '{channel}': '{value}'."
            )


def _is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


async def _download_url(url: str) -> str:
    """Download ``url`` to a temporary file and return its absolute path.

    Streams the response to disk in 64 KiB chunks to avoid buffering the
    entire payload in memory. Raises ``ToolError`` on network or HTTP failure.
    """
    try:
        import httpx2 as httpx
    except ImportError as exc:
        raise ToolError(
            "INTERNAL_ERROR: httpx2 is not installed. Install it to enable URL download support."
        ) from exc

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                suffix = Path(url.split("?")[0]).suffix or ".tmp"
                fd, tmp_path = tempfile.mkstemp(suffix=suffix)
                try:
                    with os.fdopen(fd, "wb") as tmp:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            tmp.write(chunk)
                    return tmp_path
                except Exception:
                    os.close(fd)
                    raise
    except httpx.HTTPStatusError as exc:
        raise ToolError(f"DOWNLOAD_FAILED: HTTP {exc.response.status_code} for '{url}'.") from exc
    except httpx.RequestError as exc:
        raise ToolError(f"DOWNLOAD_FAILED: Network error downloading '{url}': {exc}.") from exc


# ---------------------------------------------------------------------------
# Public tool registration
# ---------------------------------------------------------------------------

# ``cmd_import_asset`` only kicks EditorFileSystem.scan() (async) on the addon
# side; the .import sidecar lands a few frames later. Poll from the server —
# a busy-wait in the handler would block the very main thread the scan needs.
_SCAN_POLL_INTERVAL_S = 0.25
_SCAN_TIMEOUT_MS_DEFAULT = 5000


async def _poll_import_ready(
    bridge: Bridge, target_path: str, timeout_ms: int
) -> dict[str, Any] | None:
    """Poll ``cmd_get_import_status`` until the sidecar exists or time is up.

    Returns the ready status result, or ``None`` if the budget expired first.
    Transient command failures are treated as not-ready (retried until deadline).
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_ms / 1000.0
    while True:
        response = await bridge.send("cmd_get_import_status", {"target_path": target_path})
        if response.ok and (response.result or {}).get("imported"):
            return dict(response.result or {})
        if loop.time() >= deadline:
            return None
        await asyncio.sleep(_SCAN_POLL_INTERVAL_S)


def register_import_asset(mcp: FastMCP, bridge: Bridge) -> None:
    """Register the asset import tools."""

    @mcp.tool(meta=MUTATING, tags=ASSET_IMPORT)
    async def import_asset(
        source: str,
        target_path: ResPath,
        options: ImportOptions | None = None,
        dry_run: bool = False,
        wait_for_scan: bool = False,
        timeout_ms: TimeoutMs = _SCAN_TIMEOUT_MS_DEFAULT,
    ) -> ImportAssetResult:
        """Copy an external file into the Godot project and trigger import.

        Prefer ``.glb``/``.gltf`` under ``res://art/`` for Blender→Godot (see
        ``godot://conventions/blender``). ``imported: true`` means the **copy**
        landed — not that the ``.import`` sidecar exists yet. Use
        ``wait_for_scan=true``, ``get_import_status``, or ``diagnose_import``
        before claiming success; then open the scene and inspect the tree.

        ``source`` may be a local filesystem path or an HTTP(S) URL.

        ``options`` (optional):
        - ``overwrite`` (bool, default ``False``)
        - ``import_settings`` (dict, type-specific — e.g.
          ``{"type": "Texture2D", "compress": "lossy"}``). For a ``.wav``
          (AudioStreamWAV): ``{"loop_mode": 1, "loop_begin": 0, "loop_end": N}``
          (#418) — loop config lands in the ``.import`` sidecar and reimports
          (``loop_applied`` reports whether it was applied).

        ``wait_for_scan`` (default ``False``): poll until the ``.import`` sidecar
        exists (up to ``timeout_ms``); ``scan_complete`` reports readiness.
        ``scan_deferred: true`` means a scan was already in flight (#628).
        """
        _require_res_path(target_path)
        opts = options or ImportOptions()
        detected_type = _detect_type(target_path)

        preview = ImportAssetResult(
            imported=False,
            target_path=target_path,
            detected_type=detected_type,
            dry_run=True,
        )
        if dry_run:
            return preview

        local_source = source
        downloaded_tmp: str | None = None
        if _is_url(source):
            downloaded_tmp = await _download_url(source)
            local_source = downloaded_tmp

        params: dict[str, Any] = {
            "source": local_source,
            "target_path": target_path,
            "overwrite": opts.overwrite,
            "import_settings": opts.import_settings,
        }
        try:
            result = await route(bridge, "cmd_import_asset", params)
        finally:
            if downloaded_tmp and os.path.exists(downloaded_tmp):
                os.unlink(downloaded_tmp)
        scan_complete = False
        if wait_for_scan and result.get("imported", True):
            scan_complete = await _poll_import_ready(bridge, target_path, timeout_ms) is not None
        return ImportAssetResult(
            imported=result.get("imported", True),
            target_path=result.get("target_path", target_path),
            detected_type=result.get("detected_type") or detected_type,
            dry_run=False,
            scan_complete=scan_complete,
            # #418: the .wav loop config landed in the .import sidecar + reimport.
            loop_applied=result.get("loop_applied", False),
            # #628: the addon deferred its scan (one was already in flight); the
            # plugin re-issues it, so the import still lands.
            scan_deferred=result.get("scan_deferred", False),
        )

    @mcp.tool(meta=MUTATING, tags=ASSET_IMPORT)
    async def create_material_from_textures(
        albedo: str = "",
        normal: str = "",
        roughness: str = "",
        metallic: str = "",
        ao: str = "",
        emission: str = "",
        emission_enabled: str = "",
        path: ResPath = "",
        dry_run: bool = False,
    ) -> CreateMaterialResult:
        """Assemble a PBR material from texture paths and save it as a ``.tres``.

        Creates a ``StandardMaterial3D`` and assigns whichever texture channels
        were provided.  ``path`` defaults to ``res://materials/generated_{rand}.tres``
        when omitted. ``metallic``/``roughness``/``emission_enabled`` accept either a
        texture path or a scalar string (e.g. ``"0.7"``); a scalar sets the float
        property directly, and an ``emission`` texture auto-enables emission
        (``emission_enabled=true``, white color) so the material actually glows.
        Validation (including texture existence) runs before the call, on both the
        dry-run and the real run.
        """
        params: dict[str, Any] = {
            "albedo": albedo,
            "normal": normal,
            "roughness": roughness,
            "metallic": metallic,
            "ao": ao,
            "emission": emission,
            "emission_enabled": emission_enabled,
            "path": path,
        }
        # #419: validate BEFORE the bridge call in both modes — a dry-run must
        # fail on a missing texture exactly like the real run, not return a
        # success-flavored empty preview.
        await _validate_material_params(bridge, params)
        if dry_run:
            channels_preview = [
                c for c, v in (
                    ("albedo", albedo), ("normal", normal), ("roughness", roughness),
                    ("metallic", metallic), ("ao", ao), ("emission", emission),
                    ("emission_enabled", emission_enabled),
                ) if v
            ]
            return CreateMaterialResult(
                material_path=path or "res://materials/generated_{rand}.tres",
                created=False,
                channels_set=channels_preview,
                dry_run=True,
            )
        return CreateMaterialResult(
            **await route(bridge, "cmd_create_material_from_textures", params)
        )

    @mcp.tool(meta=READ_ONLY, tags=ASSET_IMPORT)
    async def get_import_status(
        target_path: ResPath, wait_ms: Annotated[int, Field(ge=0, le=600_000)] = 0
    ) -> ImportStatusResult:
        """Check whether ``target_path`` has been imported by the Godot editor.

        Looks for the ``.import`` sidecar (canonical signal) and returns type /
        last-modified. ``scanning: true`` / ``reason: rescan_in_flight`` means
        the status is provisional — do not treat as final failure.

        ``wait_ms`` (default 0): if not yet imported, poll that many ms first —
        useful right after ``import_asset`` / ``reimport``.
        """
        _require_res_path(target_path)
        result = await route(bridge, "cmd_get_import_status", {"target_path": target_path})
        if not result.get("imported", False) and wait_ms > 0:
            polled = await _poll_import_ready(bridge, target_path, wait_ms)
            if polled is not None:
                result = polled
        return ImportStatusResult(
            imported=result.get("imported", False),
            last_modified=result.get("last_modified"),
            type=result.get("type"),
            # #459/#453: the scan-in-flight state rides the status read.
            scanning=result.get("scanning", False),
            reason=result.get("reason"),
        )

    @mcp.tool(meta=MUTATING, tags=ASSET_IMPORT)
    async def reimport(
        paths: Annotated[list[ResPath], Field(min_length=1)],
        dry_run: bool = False,
        wait_for_scan: bool = False,
        timeout_ms: TimeoutMs = _SCAN_TIMEOUT_MS_DEFAULT,
    ) -> ReimportAssetsResult:
        """Force Godot to reimport existing ``res://`` asset path(s).

        Use after overwriting a Blender export in place (or when
        ``diagnose_import`` reports a stale sidecar). Distinct from
        ``rescan_filesystem`` (whole-project scan) and from ``import_asset``
        (copy into the project).

        Honesty: ``reimported: true`` means the editor **queued** reimport —
        poll ``get_import_status`` / ``diagnose_import``, then inspect the
        scene tree. ``missing`` lists paths that were not on disk.
        """
        for path in paths:
            _require_res_path(path, field="paths")
        if dry_run:
            return ReimportAssetsResult(
                reimported=False,
                paths=list(paths),
                dry_run=True,
                hint="dry_run: no reimport queued.",
            )
        result = await route(bridge, "cmd_reimport_assets", {"paths": list(paths)})
        scanning = bool(result.get("scanning", False))
        if wait_for_scan:
            # Prefer the first successfully queued path for the readiness poll.
            for path in result.get("paths") or paths:
                ready = await _poll_import_ready(bridge, path, timeout_ms)
                if ready is not None:
                    scanning = bool(ready.get("scanning", False))
                    break
        return ReimportAssetsResult(
            reimported=result.get("reimported", True),
            paths=list(result.get("paths") or paths),
            missing=list(result.get("missing") or []),
            scan_deferred=result.get("scan_deferred", False),
            scanning=scanning,
            dry_run=False,
            hint=result.get("hint"),
        )

    @mcp.tool(meta=READ_ONLY, tags=ASSET_IMPORT)
    async def diagnose_import(target_path: ResPath) -> DiagnoseImportResult:
        """Diagnose a Blender→Godot (or general) asset import for agents.

        Returns honesty fields: ``file_exists``, ``sidecar_present``,
        ``scanning``, ``gltf_pipeline_enabled``, ``gltf_summary`` (extras /
        Godot name-suffix hits for ``.gltf``), ``issues[]``, ``hints[]``, and
        ``ready``. ``ready: true`` still requires scene-tree evidence before
        claiming import success.

        Prefer ``.gltf`` (Separate) when you need extras parsed; ``.glb`` gets
        a limited summary. Enable MIT ``addons/gltf_pipeline`` when collision /
        name_override extras are present.
        """
        _require_res_path(target_path)
        result = await route(bridge, "cmd_diagnose_import", {"target_path": target_path})
        return DiagnoseImportResult(
            target_path=result.get("target_path", target_path),
            file_exists=result.get("file_exists", False),
            sidecar_present=result.get("sidecar_present", False),
            scanning=result.get("scanning", False),
            detected_type=result.get("detected_type"),
            remap_type=result.get("remap_type"),
            importer=result.get("importer"),
            gltf_pipeline_enabled=result.get("gltf_pipeline_enabled", False),
            gltf_summary=dict(result.get("gltf_summary") or {}),
            issues=list(result.get("issues") or []),
            hints=list(result.get("hints") or []),
            ready=result.get("ready", False),
            reason=result.get("reason"),
            hint=result.get("hint"),
        )
