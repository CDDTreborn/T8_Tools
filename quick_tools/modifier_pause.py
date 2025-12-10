import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import (
    BoolProperty,
    EnumProperty,
    StringProperty,
    CollectionProperty,
    PointerProperty,
)
import json


# ---------------------------------------------------------------------------
# Helper: list of modifier types for exclusion
# ---------------------------------------------------------------------------

def modifier_type_items(_self, _context):
    # Common modifier types; you can expand this list as needed.
    items = [
        ("SUBSURF", "Subdivision Surface", ""),
        ("MIRROR", "Mirror", ""),
        ("SOLIDIFY", "Solidify", ""),
        ("BEVEL", "Bevel", ""),
        ("ARRAY", "Array", ""),
        ("BOOLEAN", "Boolean", ""),
        ("TRIANGULATE", "Triangulate", ""),
        ("WELD", "Weld", ""),
        ("NODES", "Geometry Nodes", ""),
        ("SHRINKWRAP", "Shrinkwrap", ""),
        ("DATA_TRANSFER", "Data Transfer", ""),
        ("MASK", "Mask", ""),
        ("ARMATURE", "Armature", ""),
        ("CAST", "Cast", ""),
        ("CLOTH", "Cloth", ""),
        ("COLLISION", "Collision", ""),
        ("SOFT_BODY", "Soft Body", ""),
        ("PARTICLE_SYSTEM", "Particle System", ""),
        ("DISPLACE", "Displace", ""),
        ("LATTICE", "Lattice", ""),
        ("SIMPLE_DEFORM", "Simple Deform", ""),
        ("WAVE", "Wave", ""),
    ]
    return items


# ---------------------------------------------------------------------------
# Preset storage
# ---------------------------------------------------------------------------

class T8TOOLS_ModifierPausePreset(PropertyGroup):
    name: StringProperty(
        name="Preset Name",
        default="Preset",
    )
    # Comma-separated list of modifier type identifiers, e.g. "SUBSURF,BEVEL"
    modifier_types: StringProperty(
        name="Modifier Types",
        default="",
    )


class T8TOOLS_ModifierPauseSettings(PropertyGroup):
    affect_viewport: BoolProperty(
        name="Affect Viewport",
        description="Toggle show_in_viewport for modifiers when pausing/restoring",
        default=True,
    )

    affect_render: BoolProperty(
        name="Affect Render",
        description="Toggle show_in_render for modifiers when pausing/restoring",
        default=True,
    )

    exclude_types: EnumProperty(
        name="Excluded Modifiers",
        description="Modifier types that will NOT be paused",
        items=modifier_type_items,
        options={'ENUM_FLAG'},
    )

    # JSON string holding the last snapshot
    snapshot_json: StringProperty(
        name="Snapshot JSON",
        description="Stored modifier state snapshot as JSON",
        default="",
    )

    # Presets
    presets: CollectionProperty(
        type=T8TOOLS_ModifierPausePreset,
        name="Exclusion Presets",
    )

    active_preset: StringProperty(
        name="Active Preset",
        description="Name of the currently active exclusion preset",
        default="",
    )

    def get_exclude_type_set(self):
        """Return a set of modifier type identifiers to exclude."""
        if not self.exclude_types:
            return set()
        # exclude_types is an ENUM_FLAG; Blender stores it as a set-like bitmask.
        # We can access it directly as a Python set of identifiers.
        return set(self.exclude_types)


# ---------------------------------------------------------------------------
# Core utilities
# ---------------------------------------------------------------------------

def _debug_print(*args):
    print("[T8 Modifier Pause]", *args)


def _build_snapshot(context, settings):
    """
    Build a snapshot of all modifiers in the scene:
    {
        "ObjectName": {
            "ModifierName": {"type": "SUBSURF", "sv": bool, "sr": bool},
            ...
        },
        ...
    }
    """
    data = {}
    for obj in context.scene.objects:
        if not obj.modifiers:
            continue

        obj_data = {}
        for mod in obj.modifiers:
            obj_data[mod.name] = {
                "type": mod.type,
                "sv": bool(getattr(mod, "show_viewport", True)),
                "sr": bool(getattr(mod, "show_render", True)),
            }

        if obj_data:
            data[obj.name] = obj_data

    return data


def _apply_pause(context, settings):
    """
    Disable modifiers (viewport/render) for all objects,
    skipping modifiers whose type is in the exclusion list.
    """
    exclude_types = settings.get_exclude_type_set()

    for obj in context.scene.objects:
        if not obj.modifiers:
            continue

        for mod in obj.modifiers:
            if mod.type in exclude_types:
                continue

            if settings.affect_viewport and hasattr(mod, "show_viewport"):
                mod.show_viewport = False

            if settings.affect_render and hasattr(mod, "show_render"):
                mod.show_render = False


def _apply_restore(context, settings):
    """
    Restore modifier visibility from the stored snapshot.
    If objects/modifiers were deleted/renamed, they are skipped safely.
    """
    if not settings.snapshot_json:
        _debug_print("No snapshot stored.")
        return False

    try:
        data = json.loads(settings.snapshot_json)
    except Exception as e:
        _debug_print("Failed to decode snapshot JSON:", e)
        return False

    for obj_name, obj_mods in data.items():
        obj = context.scene.objects.get(obj_name)
        if obj is None:
            continue

        if not obj.modifiers:
            continue

        for mod_name, mod_state in obj_mods.items():
            mod = obj.modifiers.get(mod_name)
            if mod is None:
                continue

            if settings.affect_viewport and hasattr(mod, "show_viewport"):
                mod.show_viewport = bool(mod_state.get("sv", True))

            if settings.affect_render and hasattr(mod, "show_render"):
                mod.show_render = bool(mod_state.get("sr", True))

    return True


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class T8TOOLS_OT_modifier_pause_snapshot_and_disable(Operator):
    """Snapshot modifier states and disable modifiers (optionally excluding types)."""
    bl_idname = "t8tools.modifier_pause_snapshot_and_disable"
    bl_label = "Snapshot & Pause Modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.t8tools_modifier_pause_settings

        # Build snapshot
        snapshot = _build_snapshot(context, settings)
        try:
            settings.snapshot_json = json.dumps(snapshot)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to serialize snapshot: {e}")
            return {'CANCELLED'}

        # Apply pause
        _apply_pause(context, settings)

        self.report({'INFO'}, "Modifiers paused and snapshot stored.")
        return {'FINISHED'}


class T8TOOLS_OT_modifier_pause_restore(Operator):
    """Restore modifier states from the last snapshot."""
    bl_idname = "t8tools.modifier_pause_restore"
    bl_label = "Restore Modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.t8tools_modifier_pause_settings

        ok = _apply_restore(context, settings)
        if not ok:
            self.report({'WARNING'}, "No valid snapshot to restore from.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Modifiers restored from snapshot.")
        return {'FINISHED'}


class T8TOOLS_OT_modifier_pause_preset_add(Operator):
    """Create a new exclusion preset from the current excluded types."""
    bl_idname = "t8tools.modifier_pause_preset_add"
    bl_label = "Add Exclusion Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: StringProperty(
        name="Preset Name",
        default="New Preset",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        settings = context.scene.t8tools_modifier_pause_settings
        exclude_types = settings.get_exclude_type_set()

        if not exclude_types:
            self.report({'WARNING'}, "No excluded types selected to store.")
            return {'CANCELLED'}

        preset = settings.presets.add()
        preset.name = self.preset_name

        # Store as comma-separated string
        preset.modifier_types = ",".join(sorted(exclude_types))

        settings.active_preset = preset.name

        self.report({'INFO'}, f"Preset '{preset.name}' added.")
        return {'FINISHED'}


class T8TOOLS_OT_modifier_pause_preset_apply(Operator):
    """Apply the selected exclusion preset to the current settings."""
    bl_idname = "t8tools.modifier_pause_preset_apply"
    bl_label = "Apply Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.t8tools_modifier_pause_settings
        name = settings.active_preset

        if not name:
            self.report({'WARNING'}, "No preset selected.")
            return {'CANCELLED'}

        preset = None
        for p in settings.presets:
            if p.name == name:
                preset = p
                break

        if not preset:
            self.report({'WARNING'}, f"Preset '{name}' not found.")
            return {'CANCELLED'}

        types_str = preset.modifier_types or ""
        # Convert back to a tuple for ENUM_FLAG assignment
        types = [t for t in types_str.split(",") if t]
        settings.exclude_types = types

        self.report({'INFO'}, f"Preset '{name}' applied.")
        return {'FINISHED'}


class T8TOOLS_OT_modifier_pause_preset_remove(Operator):
    """Remove the currently active exclusion preset."""
    bl_idname = "t8tools.modifier_pause_preset_remove"
    bl_label = "Remove Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.t8tools_modifier_pause_settings
        name = settings.active_preset

        if not name:
            self.report({'WARNING'}, "No preset selected.")
            return {'CANCELLED'}

        idx_to_remove = None
        for idx, p in enumerate(settings.presets):
            if p.name == name:
                idx_to_remove = idx
                break

        if idx_to_remove is None:
            self.report({'WARNING'}, f"Preset '{name}' not found.")
            return {'CANCELLED'}

        settings.presets.remove(idx_to_remove)
        settings.active_preset = ""

        self.report({'INFO'}, f"Preset '{name}' removed.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel (Quick Tools child)
# ---------------------------------------------------------------------------

class VIEW3D_PT_T8Tools_ModifierPause(Panel):
    bl_label = "Modifier Pause"
    bl_idname = "VIEW3D_PT_t8tools_modifier_pause"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_quick"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "t8tools_modifier_pause_settings")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.t8tools_modifier_pause_settings

        col = layout.column(align=True)
        col.label(text="Affect:", icon='MODIFIER')
        col.prop(settings, "affect_viewport")
        col.prop(settings, "affect_render")

        col.separator()
        col.label(text="Excluded Modifier Types:")

        col.prop(settings, "exclude_types")

        col.separator()
        row = col.row(align=True)
        row.operator("t8tools.modifier_pause_snapshot_and_disable", icon='PAUSE')
        row.operator("t8tools.modifier_pause_restore", icon='PLAY')

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Exclusion Presets:", icon='PRESET')

        # Dropdown for presets (by name)
        if settings.presets:
            row = col.row(align=True)
            # Enum-like behavior via template_list would be overkill; simple menu via names:
            names = [p.name for p in settings.presets]
            # Ensure active_preset is at least a valid string
            if settings.active_preset not in names:
                settings.active_preset = names[0]

            col.prop(settings, "active_preset", text="Preset Name")

            row = col.row(align=True)
            row.operator("t8tools.modifier_pause_preset_apply", icon='CHECKMARK', text="Apply")
            row.operator("t8tools.modifier_pause_preset_remove", icon='TRASH', text="")
        else:
            col.label(text="No presets defined.", icon='INFO')

        col.operator("t8tools.modifier_pause_preset_add", icon='ADD', text="Add from Current Exclusions")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    T8TOOLS_ModifierPausePreset,
    T8TOOLS_ModifierPauseSettings,
    T8TOOLS_OT_modifier_pause_snapshot_and_disable,
    T8TOOLS_OT_modifier_pause_restore,
    T8TOOLS_OT_modifier_pause_preset_add,
    T8TOOLS_OT_modifier_pause_preset_apply,
    T8TOOLS_OT_modifier_pause_preset_remove,
    VIEW3D_PT_T8Tools_ModifierPause,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.t8tools_modifier_pause_settings = PointerProperty(
        type=T8TOOLS_ModifierPauseSettings
    )


def unregister():
    del bpy.types.Scene.t8tools_modifier_pause_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
