# SPDX-License-Identifier: MIT
"""Making Things — MIT Blender helpers for Godot glTF export.

Install: Blender → Edit → Preferences → Add-ons → Install → select this folder
(or zip containing __init__.py + mt_godot_export.py). Enable "Making Things:
Godot glTF Export".

Writes glTF extras compatible with Godot MIT addons/gltf_pipeline and applies
Godot built-in name suffixes. Does not replace the paid Blender-Godot Pipeline
panel or GPL Goblend — see third_party/README.md.
"""

bl_info = {
    "name": "Making Things: Godot glTF Export",
    "author": "Making Things",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D → Sidebar → Godot MT",
    "description": "Godot name suffixes, gltf_pipeline extras, and glTF export presets",
    "category": "Import-Export",
    "doc_url": "https://github.com/Tzeke000/CC-experments",
}

from . import mt_godot_export


def register() -> None:
    mt_godot_export.register()


def unregister() -> None:
    mt_godot_export.unregister()
