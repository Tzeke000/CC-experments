# SPDX-License-Identifier: MIT
"""Operators + UI for Godot-oriented glTF export (Making Things)."""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator, Panel

# Godot built-in import suffixes (docs: node type customization).
_SUFFIXES = (
    ("COL", "-col", "Static trimesh collision child"),
    ("CONVCOL", "-convcol", "Convex collision child"),
    ("COLONLY", "-colonly", "Collision only (mesh removed)"),
    ("CONVCOLONLY", "-convcolonly", "Convex collision only"),
    ("NOIMP", "-noimp", "Skip import"),
    ("NAVMESH", "-navmesh", "Navigation mesh"),
    ("OCC", "-occ", "Occluder"),
    ("RIGID", "-rigid", "RigidBody3D"),
)

# gltf_pipeline extras.collision keywords (MIT Godot runtime).
_COLLISION_EXTRAS = (
    ("TRIMESH", "trimesh", "StaticBody3D + trimesh"),
    ("SIMPLE", "simple", "StaticBody3D + convex hull"),
    ("BOX", "box", "BoxShape3D (needs size_x/y/z)"),
    ("SPHERE", "sphere", "SphereShape3D (needs radius)"),
    ("CAPSULE", "capsule", "CapsuleShape3D"),
    ("CYLINDER", "cylinder", "CylinderShape3D"),
    ("BOX_R", "box-r", "Box inside RigidBody3D"),
    ("TRIMESH_C", "trimesh-c", "Orphan trimesh shape (col-only)"),
)


def _strip_known_suffix(name: str) -> str:
    lower = name.lower()
    for _, suffix, _ in _SUFFIXES:
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return name


class MT_OT_apply_godot_suffix(Operator):
    bl_idname = "mt_godot.apply_suffix"
    bl_label = "Apply Godot Name Suffix"
    bl_options = {"REGISTER", "UNDO"}

    suffix: EnumProperty(
        name="Suffix",
        items=[(k, s, d) for k, s, d in _SUFFIXES],
        default="COL",
    )

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            base = _strip_known_suffix(obj.name)
            wanted = dict((k, s) for k, s, _ in _SUFFIXES)[self.suffix]
            obj.name = base + wanted
            count += 1
        self.report({"INFO"}, f"Applied {self.suffix} to {count} object(s)")
        return {"FINISHED"}


class MT_OT_set_collision_extra(Operator):
    bl_idname = "mt_godot.set_collision_extra"
    bl_label = "Set glTF collision Extra"
    bl_options = {"REGISTER", "UNDO"}

    collision: EnumProperty(
        name="Collision",
        items=[(k, v, d) for k, v, d in _COLLISION_EXTRAS],
        default="TRIMESH",
    )

    def execute(self, context):
        value = dict((k, v) for k, v, _ in _COLLISION_EXTRAS)[self.collision]
        count = 0
        for obj in context.selected_objects:
            obj["collision"] = value
            # Custom properties export as glTF extras when Custom Properties is on.
            count += 1
        self.report({"INFO"}, f"Set collision={value} on {count} object(s)")
        return {"FINISHED"}


class MT_OT_set_name_override(Operator):
    bl_idname = "mt_godot.set_name_override"
    bl_label = "Set name_override Extra"
    bl_options = {"REGISTER", "UNDO"}

    override: StringProperty(name="Godot Name", default="")

    def execute(self, context):
        if not self.override:
            self.report({"ERROR"}, "override name is empty")
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj["name_override"] = self.override
        return {"FINISHED"}

    def invoke(self, context, _event):
        if context.active_object:
            self.override = _strip_known_suffix(context.active_object.name)
        return context.window_manager.invoke_props_dialog(self)


class MT_OT_export_gltf_godot(Operator):
    bl_idname = "mt_godot.export_gltf"
    bl_label = "Export glTF for Godot"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")
    export_format: EnumProperty(
        name="Format",
        items=(
            ("GLB", "GLB (binary)", "Single .glb file"),
            ("GLTF_SEPARATE", "glTF Separate", ".gltf + .bin + textures (extras-friendly)"),
        ),
        default="GLB",
    )

    def execute(self, context):
        if not self.filepath:
            self.report({"ERROR"}, "Set filepath first")
            return {"CANCELLED"}
        # Recommended Godot settings: Y-up, extras/custom props, visible only.
        kwargs = {
            "filepath": self.filepath,
            "export_format": self.export_format,
            "export_extras": True,
            "export_yup": True,
            "export_apply": True,
            "use_visible": True,
            "export_cameras": True,
            "export_lights": True,
            "export_skins": True,
            "export_morph": True,
        }
        # Blender 4.x renamed some keys; try modern first, fall back.
        try:
            bpy.ops.export_scene.gltf(**kwargs)
        except TypeError:
            kwargs.pop("use_visible", None)
            kwargs["use_selection"] = False
            bpy.ops.export_scene.gltf(**kwargs)
        self.report({"INFO"}, f"Exported {self.filepath}")
        return {"FINISHED"}

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MT_PT_godot_panel(Panel):
    bl_label = "Godot MT"
    bl_idname = "MT_PT_godot_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Godot MT"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Name suffixes (Godot built-in)")
        layout.operator_menu_enum("mt_godot.apply_suffix", "suffix", text="Apply Suffix")
        layout.separator()
        layout.label(text="gltf_pipeline extras (MIT)")
        layout.operator_menu_enum(
            "mt_godot.set_collision_extra", "collision", text="Collision Extra"
        )
        layout.operator("mt_godot.set_name_override")
        layout.separator()
        layout.operator("mt_godot.export_gltf", icon="EXPORT")
        layout.label(text="Prefer .glb; use Separate for diffs")
        box = layout.box()
        box.label(text="Optional GPL: Goblend")
        box.label(text="Paid: Blender-Godot Pipeline")


_CLASSES = (
    MT_OT_apply_godot_suffix,
    MT_OT_set_collision_extra,
    MT_OT_set_name_override,
    MT_OT_export_gltf_godot,
    MT_PT_godot_panel,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
