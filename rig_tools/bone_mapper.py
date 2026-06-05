import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import (
    PointerProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
    EnumProperty,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _armature_poll(self, obj):
    return obj and obj.type == 'ARMATURE'


def _get_bone_names(arm_obj):
    if not arm_obj or arm_obj.type != 'ARMATURE':
        return []
    return sorted([b.name for b in arm_obj.data.bones])


def _enum_custom_bones(self, context):
    s = context.scene.t8_bone_mapper_settings
    names = _get_bone_names(s.custom_rig)
    if not names:
        return [('NONE', "<No custom rig/bones loaded>", "")]
    return [(name, name, "") for name in names]


def _enum_target_bones(self, context):
    s = context.scene.t8_bone_mapper_settings
    names = _get_bone_names(s.target_rig)
    if not names:
        return [('NONE', "<No target rig/bones loaded>", "")]
    return [(name, name, "") for name in names]


def _validate_mappings(context):
    s = context.scene.t8_bone_mapper_settings
    custom_rig = s.custom_rig
    target_rig = s.target_rig

    custom_names = set(_get_bone_names(custom_rig))
    target_names = set(_get_bone_names(target_rig))

    used_custom = {}
    used_target = {}

    for i, entry in enumerate(s.mappings):
        entry.status = "OK"
        entry.is_valid = True

        custom = entry.custom_bone
        target = entry.target_bone

        if not custom or custom == 'NONE':
            entry.status = "Missing custom bone"
            entry.is_valid = False
            continue

        if not target or target == 'NONE':
            entry.status = "Missing target bone"
            entry.is_valid = False
            continue

        if custom not in custom_names:
            entry.status = "Custom bone not found"
            entry.is_valid = False
            continue

        if target not in target_names:
            entry.status = "Target bone not found"
            entry.is_valid = False
            continue

        used_custom.setdefault(custom, []).append(i)
        used_target.setdefault(target, []).append(i)

    for name, indexes in used_custom.items():
        if len(indexes) > 1:
            for i in indexes:
                s.mappings[i].status = "Duplicate custom bone"
                s.mappings[i].is_valid = False

    for name, indexes in used_target.items():
        if len(indexes) > 1:
            for i in indexes:
                s.mappings[i].status = "Duplicate target bone"
                s.mappings[i].is_valid = False

    for entry in s.mappings:
        if not entry.is_valid:
            continue

        custom = entry.custom_bone
        target = entry.target_bone

        if target in custom_names and custom != target:
            entry.status = "Target name already exists on custom rig"
            entry.is_valid = False


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class T8BoneMapEntry(PropertyGroup):
    custom_bone: EnumProperty(
        name="Custom Bone",
        description="Bone on the custom/source rig that will be renamed",
        items=_enum_custom_bones,
    )

    target_bone: EnumProperty(
        name="Target Bone",
        description="Tekken/reference bone name to rename into",
        items=_enum_target_bones,
    )

    status: StringProperty(
        name="Status",
        default="Not validated",
    )

    is_valid: bpy.props.BoolProperty(
        name="Valid",
        default=False,
    )


class T8BoneMapperSettings(PropertyGroup):
    custom_rig: PointerProperty(
        name="Custom Rig",
        type=bpy.types.Object,
        description="The rig whose bones will be renamed",
        poll=_armature_poll,
    )

    target_rig: PointerProperty(
        name="Target Rig",
        type=bpy.types.Object,
        description="The Tekken/reference rig providing desired bone names",
        poll=_armature_poll,
    )

    mappings: CollectionProperty(type=T8BoneMapEntry)

    active_mapping_index: IntProperty(default=0)

    conflict_mode: EnumProperty(
        name="If Target Name Exists",
        description="What to do if the desired target bone name already exists on the custom rig",
        items=[
            ('SKIP', "Skip", "Skip rows where the target name already exists"),
        ],
        default='SKIP',
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class T8TOOLS_OT_BoneMapper_AddRow(Operator):
    bl_idname = "t8tools.bone_mapper_add_row"
    bl_label = "Add Bone Mapping"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings
        entry = s.mappings.add()
        entry.status = "Not validated"
        s.active_mapping_index = len(s.mappings) - 1
        return {'FINISHED'}


class T8TOOLS_OT_BoneMapper_RemoveRow(Operator):
    bl_idname = "t8tools.bone_mapper_remove_row"
    bl_label = "Remove Bone Mapping"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty(default=-1)

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings

        if self.index < 0 or self.index >= len(s.mappings):
            self.report({'ERROR'}, "Invalid mapping row.")
            return {'CANCELLED'}

        s.mappings.remove(self.index)
        s.active_mapping_index = min(max(0, self.index - 1), max(0, len(s.mappings) - 1))
        return {'FINISHED'}


class T8TOOLS_OT_BoneMapper_ClearRows(Operator):
    bl_idname = "t8tools.bone_mapper_clear_rows"
    bl_label = "Clear All Mappings"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings
        s.mappings.clear()
        s.active_mapping_index = 0
        self.report({'INFO'}, "Cleared all bone mappings.")
        return {'FINISHED'}


class T8TOOLS_OT_BoneMapper_Validate(Operator):
    bl_idname = "t8tools.bone_mapper_validate"
    bl_label = "Validate Bone Mapping"
    bl_options = {'REGISTER'}

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings

        if not s.custom_rig:
            self.report({'ERROR'}, "Custom Rig is not set.")
            return {'CANCELLED'}

        if not s.target_rig:
            self.report({'ERROR'}, "Target Rig is not set.")
            return {'CANCELLED'}

        _validate_mappings(context)

        valid_count = sum(1 for e in s.mappings if e.is_valid)
        total = len(s.mappings)

        self.report({'INFO'}, f"Validated mappings: {valid_count}/{total} valid.")
        return {'FINISHED'}


class T8TOOLS_OT_BoneMapper_Apply(Operator):
    bl_idname = "t8tools.bone_mapper_apply"
    bl_label = "Apply Bone Renames"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings

        if not s.custom_rig:
            self.report({'ERROR'}, "Custom Rig is not set.")
            return {'CANCELLED'}

        if not s.target_rig:
            self.report({'ERROR'}, "Target Rig is not set.")
            return {'CANCELLED'}

        _validate_mappings(context)

        renamed = 0
        skipped = 0

        bones = s.custom_rig.data.bones

        for entry in s.mappings:
            if not entry.is_valid:
                skipped += 1
                continue

            bone = bones.get(entry.custom_bone)
            if not bone:
                entry.status = "Custom bone disappeared"
                entry.is_valid = False
                skipped += 1
                continue

            old_name = entry.custom_bone
            new_name = entry.target_bone

            try:
                bone.name = new_name
                entry.custom_bone = new_name
                entry.status = f"Renamed: {old_name} → {new_name}"
                renamed += 1
            except Exception as ex:
                entry.status = f"Failed: {ex}"
                entry.is_valid = False
                skipped += 1

        self.report({'INFO'}, f"Bone Mapper finished: {renamed} renamed, {skipped} skipped.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI Panel
# ---------------------------------------------------------------------------

class VIEW3D_PT_T8Tools_BoneMapper(Panel):
    bl_label = "Bone Mapper"
    bl_idname = "VIEW3D_PT_t8tools_bone_mapper"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_rig"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.t8_bone_mapper_settings

        col = layout.column(align=True)
        col.label(text="Rig Selection")
        col.prop(s, "custom_rig")
        col.prop(s, "target_rig")

        layout.separator()

        row = layout.row(align=True)
        row.operator("t8tools.bone_mapper_add_row", text="Add Mapping", icon='ADD')
        row.operator("t8tools.bone_mapper_clear_rows", text="Clear", icon='TRASH')

        layout.separator()

        if len(s.mappings) == 0:
            layout.label(text="No mappings yet.")
            layout.label(text="Click Add Mapping to begin.")
        else:
            for i, entry in enumerate(s.mappings):
                box = layout.box()

                header = box.row(align=True)
                header.label(text=f"Mapping {i + 1}")
                op = header.operator("t8tools.bone_mapper_remove_row", text="", icon='X')
                op.index = i

                box.prop_search(entry, "custom_bone", s.custom_rig.data, "bones", text="Custom")
                box.prop_search(entry, "target_bone", s.target_rig.data, "bones", text="Rename To")

                status_row = box.row()
                icon = 'CHECKMARK' if entry.is_valid else 'ERROR'
                status_row.label(text=entry.status, icon=icon)

        layout.separator()

        col = layout.column(align=True)
        col.operator("t8tools.bone_mapper_validate", text="Validate Mapping", icon='VIEWZOOM')
        col.operator("t8tools.bone_mapper_apply", text="Apply Bone Renames", icon='ARMATURE_DATA')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    T8BoneMapEntry,
    T8BoneMapperSettings,
    T8TOOLS_OT_BoneMapper_AddRow,
    T8TOOLS_OT_BoneMapper_RemoveRow,
    T8TOOLS_OT_BoneMapper_ClearRows,
    T8TOOLS_OT_BoneMapper_Validate,
    T8TOOLS_OT_BoneMapper_Apply,
    VIEW3D_PT_T8Tools_BoneMapper,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.t8_bone_mapper_settings = PointerProperty(
        type=T8BoneMapperSettings
    )


def unregister():
    del bpy.types.Scene.t8_bone_mapper_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)