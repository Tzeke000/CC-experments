"""Making Things observability: structured event ring + correlation IDs.

Captures bridge tool traffic so agents can diagnose failures via
``godot://logs/recent`` / ``godot://errors/open`` and the matching tools.
Events never include secrets (bridge tokens, auth headers).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

_MAX_EVENTS = 500
_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_seq = 0


def new_correlation_id() -> str:
    """Mint a short correlation id for one bridge round-trip."""
    return uuid.uuid4().hex[:12]


def record_event(
    *,
    source: str,
    level: str,
    message: str,
    code: str = "",
    corr: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    loc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a structured event; returns the stored event (with seq)."""
    global _seq
    event: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "level": level,
        "code": code,
        "message": message,
        "corr": corr or {},
        "data": data or {},
        "loc": loc or {},
    }
    with _lock:
        _seq += 1
        event["seq"] = _seq
        _events.append(event)
    return event


def recent_events(
    *,
    since_seq: int = 0,
    level: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return recent events newer than ``since_seq``, optionally filtered by level."""
    with _lock:
        items = [e for e in _events if int(e.get("seq", 0)) > since_seq]
        next_seq = _seq
    if level:
        wanted = level.lower()
        items = [e for e in items if str(e.get("level", "")).lower() == wanted]
    truncated = len(items) > limit
    items = items[-limit:]
    return {
        "events": items,
        "next_seq": next_seq,
        "truncated": truncated,
        "count": len(items),
    }


def open_errors(*, limit: int = 50) -> dict[str, Any]:
    """Errors and warnings still useful for diagnose-and-fix (recent ring)."""
    with _lock:
        items = [
            e
            for e in _events
            if str(e.get("level", "")).lower() in ("error", "warn", "warning")
        ]
    items = items[-limit:]
    return {"errors": items, "count": len(items)}


def clear_events() -> None:
    """Test helper: empty the ring."""
    global _seq
    with _lock:
        _events.clear()
        _seq = 0


BLENDER_CONVENTIONS: dict[str, Any] = {
    "interchange": "gltf",
    "preferred_formats": [".glb", ".gltf"],
    "optional_blend": {
        "supported": True,
        "requires": (
            "Blender ≥3.5 on PATH; "
            "Editor Settings → Filesystem → Import → Blender Path"
        ),
        "team_note": "Prefer committing glTF so teammates need not install Blender",
        "godot_45_note": (
            "Godot 4.5+ .blend import fails on Blender <3.5 "
            "(unrecognized export_import_convert_lighting_mode)"
        ),
    },
    "godot_name_suffixes": [
        "-col",
        "-convcol",
        "-colonly",
        "-convcolonly",
        "-noimp",
        "-navmesh",
        "-occ",
        "-occonly",
        "-rigid",
        "-vehicle",
        "-wheel",
        "-alpha",
        "-vcol",
        "loop/cycle (animation clip name)",
    ],
    "gltf_pipeline_extras": {
        "collision": (
            "trimesh|simple|box|sphere|capsule|cylinder "
            "+ optional flags -r/-a/-m/-h/-c/-d"
        ),
        "name_override": "rename node on import",
        "material_0..3": "surface override materials",
        "script": "attach script + prop_string/prop_file",
        "nav_mesh": "path to save NavigationRegion3D",
        "packed_scene": "replace node with PackedScene instance",
    },
    "lods": {
        "auto_for_scenes": True,
        "note": (
            "meshes/generate_lods defaults true for glTF scenes; "
            "disable per-mesh if LODs look broken; OBJ needs Import As → Scene"
        ),
    },
    "meshlibrary": {
        "layout": (
            "Node3D root → uniquely named MeshInstance3D children "
            "(+ optional StaticBody3D/CollisionShape3D, NavigationRegion3D)"
        ),
        "pain": (
            "duplicate mesh names collapse GridMap items; "
            "prefer one .glb of uniquely named tiles + shared external material"
        ),
    },
    "export_checklist": [
        "Apply object transforms before export",
        "Triangulate meshes (modifier or export option)",
        "Armature at rest pose; Export Deformation Bones Only for shape keys",
        "Enable Backface Culling on materials when appropriate",
        "Enable Custom Properties / extras when using gltf_pipeline",
        "Agree on meters / Y-up conventions per project",
        "Place under res://art/ then godot_asset_import_reimport / await idle",
        (
            "godot_asset_import_diagnose then inspect imported scene tree "
            "before claiming success"
        ),
    ],
    "agent_tools": [
        "godot_asset_import_asset",
        "godot_asset_import_reimport",
        "godot_asset_import_get_status",
        "godot_asset_import_diagnose",
        "godot_asset_import_create_material_from_textures",
        "godot_scene_edit_rescan_filesystem",
    ],
    "pipelines": {
        "mt_blender_export": {
            "path": "third_party/mt_blender_export",
            "license": "MIT",
            "role": "Blender helpers: Godot suffixes, gltf_pipeline extras, export preset",
            "default_in_fixtures": False,
        },
        "gltf_pipeline": {
            "path": "third_party/gltf_pipeline",
            "license": "MIT",
            "role": "Godot GLTFDocumentExtension for Blender-Godot Pipeline extras",
            "default_in_fixtures": True,
        },
        "goblend": {
            "path": "third_party/goblend",
            "license": "GPL-3.0",
            "role": "Optional Blender+Godot export UX — keep separate; accept GPL if enabled",
            "default_in_fixtures": False,
        },
    },
    "fixture_assets": [
        "fixtures/godot_project/art/sample.glb",
        "fixtures/godot_project/art/triangle.glb",
        "fixtures/godot_project/art/triangle.gltf",
    ],
}
