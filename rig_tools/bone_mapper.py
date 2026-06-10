import bpy
import json
import os

from bpy.types import Panel, Operator, PropertyGroup, UIList
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

        if custom == target:
            entry.status = "Already matches"
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

    custom_bone: StringProperty(
        name="Custom Bone",
        description="Bone on the custom/source rig that will be renamed",
        default="",
    )

    target_bone: StringProperty(
        name="Target Bone",
        description="Tekken/reference bone name to rename into",
        default="",
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

    preset_path: StringProperty(
        name="Preset File",
        description="JSON file used to save/load bone mapping presets",
        subtype='FILE_PATH',
        default="//bone_mapping_preset.json",
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------



class T8TOOLS_OT_BoneMapper_AddRow(Operator):
    bl_idname = "t8tools.bone_mapper_add_row"
    bl_label = "Add Bone Mapping"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = (
        "Create an empty mapping row. "
        "Choose a custom bone and the target bone name it should be renamed to."
    )

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
    bl_description = (
        "Remove all mapping rows from the current session. "
        "Does not modify rigs or preset files."
    )
        


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
    bl_description = (
        "Validates and updates status of the bone renaming process."
        "Does not rename bones."
    )

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
    bl_description = (
        "(Desctructive Action) Applies the new name to the bones."

    )

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
    
class T8TOOLS_OT_BoneMapper_SavePreset(Operator):
    bl_idname = "t8tools.bone_mapper_save_preset"
    bl_label = "Save Bone Mapping Preset"
    bl_options = {'REGISTER'}
    bl_description = (
        "Save mappings to the selected Preset File"
    )

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings
        path = bpy.path.abspath(s.preset_path)

        if not path:
            self.report({'ERROR'}, "Preset path is empty.")
            return {'CANCELLED'}

        data = {
            "version": 1,
            "custom_rig_hint": s.custom_rig.name if s.custom_rig else "",
            "target_rig_hint": s.target_rig.name if s.target_rig else "",
            "mappings": [
                {
                    "custom": entry.custom_bone,
                    "target": entry.target_bone,
                }
                for entry in s.mappings
                if entry.custom_bone 
                # and entry.target_bone
            ],
        }

        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

        except Exception as ex:
            self.report({'ERROR'}, f"Failed to save preset: {ex}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Saved preset: {os.path.basename(path)}")
        return {'FINISHED'}


class T8TOOLS_OT_BoneMapper_LoadPreset(Operator):
    bl_idname = "t8tools.bone_mapper_load_preset"
    bl_label = "Load Bone Mapping Preset"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = (
        "Loads mappings from the file identified in the Preset File"
    )

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings
        path = bpy.path.abspath(s.preset_path)

        if not os.path.exists(path):
            self.report({'ERROR'}, "Preset file does not exist.")
            return {'CANCELLED'}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            mappings = data.get("mappings", [])

            s.mappings.clear()

            for item in mappings:
                entry = s.mappings.add()
                entry.custom_bone = item.get("custom", "")
                entry.target_bone = item.get("target", "")
                entry.status = "Loaded"
                entry.is_valid = False

            _validate_mappings(context)

        except Exception as ex:
            self.report({'ERROR'}, f"Failed to load preset: {ex}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Loaded preset: {len(s.mappings)} mapping(s).")
        return {'FINISHED'}
    
class T8TOOLS_OT_BoneMapper_SelectMappedBones(Operator):
    bl_idname = "t8tools.bone_mapper_select_mapped_bones"
    bl_label = "Select Mapped Bones"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = (
        "Opens Bone Edit mode and selects all bones on the Custom Rig."
        "If bones have been renamed it will select bones based on new name."

    )

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings
        rig = s.custom_rig

        if not rig or rig.type != 'ARMATURE':
            self.report({'ERROR'}, "Custom Rig is not set.")
            return {'CANCELLED'}

        if not s.mappings:
            self.report({'ERROR'}, "No mappings to select.")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        rig.select_set(True)
        context.view_layer.objects.active = rig

        bpy.ops.object.mode_set(mode='EDIT')

        for bone in rig.data.edit_bones:
            bone.select = False
            bone.select_head = False
            bone.select_tail = False

        selected = 0
        missing = 0
        seen = set()

        for entry in s.mappings:
            custom_name = entry.custom_bone.strip()
            target_name = entry.target_bone.strip()

            bone = None
            selected_name = ""

            if custom_name:
                bone = rig.data.edit_bones.get(custom_name)
                selected_name = custom_name if bone else ""

            if not bone and target_name:
                bone = rig.data.edit_bones.get(target_name)
                selected_name = target_name if bone else ""

            if bone and selected_name not in seen:
                bone.select = True
                bone.select_head = True
                bone.select_tail = True
                seen.add(selected_name)
                selected += 1
            elif not bone:
                missing += 1

        self.report({'INFO'}, f"Selected {selected} mapped bone(s). Missing {missing}.")
        return {'FINISHED'}

class T8TOOLS_OT_BoneMapper_AddRowsFromSelection(Operator):
    bl_idname = "t8tools.bone_mapper_add_rows_from_selection"
    bl_label = "Add Rows From Selected Bones"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = (
        "Adds a mapping for every bone currently selected in bone Pose/Edit mode."
    )

    def execute(self, context):
        s = context.scene.t8_bone_mapper_settings
        rig = s.custom_rig

        if not rig or rig.type != 'ARMATURE':
            self.report({'ERROR'}, "Custom Rig is not set.")
            return {'CANCELLED'}

        active = context.view_layer.objects.active
        if active != rig:
            self.report({'ERROR'}, "Custom Rig must be the active object.")
            return {'CANCELLED'}

        selected_names = []

        if context.mode == 'EDIT_ARMATURE':
            selected_names = [
                b.name for b in rig.data.edit_bones
                if b.select or b.select_head or b.select_tail
            ]

        elif context.mode == 'POSE':
            selected_names = [
                b.name for b in context.selected_pose_bones
                if b and b.id_data == rig
            ]

        else:
            self.report({'ERROR'}, "Select bones in Edit Mode or Pose Mode.")
            return {'CANCELLED'}

        if not selected_names:
            self.report({'ERROR'}, "No bones selected.")
            return {'CANCELLED'}

        existing_custom = {entry.custom_bone for entry in s.mappings}
        added = 0
        skipped = 0

        for name in selected_names:
            if name in existing_custom:
                skipped += 1
                continue

            entry = s.mappings.add()
            entry.custom_bone = name
            entry.target_bone = ""
            entry.status = "Needs target"
            entry.is_valid = False
            added += 1

        self.report({'INFO'}, f"Added {added} row(s) from selection. Skipped {skipped} duplicate(s).")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI Panel
# ---------------------------------------------------------------------------

class T8TOOLS_UL_BoneMapperMappings(UIList):
    bl_idname = "T8TOOLS_UL_bone_mapper_mappings"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        entry = item

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            status_icon = 'CHECKMARK' if entry.is_valid else 'ERROR'
            custom = entry.custom_bone if entry.custom_bone else "<No custom>"
            target = entry.target_bone if entry.target_bone else "<No target>"

            row.label(text=f"{custom}  →  {target}", icon=status_icon)

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='BONE_DATA')

    def filter_items(self, context, data, propname):
        mappings = getattr(data, propname)

        helper_funcs = bpy.types.UI_UL_list

        filter_name = self.filter_name.lower().strip()
        flags = []
        neworder = []

        for entry in mappings:
            custom = entry.custom_bone.lower() if entry.custom_bone else ""
            target = entry.target_bone.lower() if entry.target_bone else ""
            status = entry.status.lower() if entry.status else ""

            searchable = f"{custom} {target} {status}"

            if not filter_name or filter_name in searchable:
                flags.append(self.bitflag_filter_item)
            else:
                flags.append(0)

        if self.use_filter_sort_alpha:
            neworder = helper_funcs.sort_items_by_name(
                mappings,
                "custom_bone",
            )

        return flags, neworder

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

        row = layout.row(align=True)
        row.operator("t8tools.bone_mapper_add_rows_from_selection", text="Add Mapping From Selection", icon='GROUP_BONE')

        layout.separator()

        if len(s.mappings) == 0:
            layout.label(text="No mappings yet.")
            layout.label(text="Click Add Mapping to begin.")
        else:
            layout.template_list(
                "T8TOOLS_UL_bone_mapper_mappings",
                "",
                s,
                "mappings",
                s,
                "active_mapping_index",
                rows=8,
            )

            if 0 <= s.active_mapping_index < len(s.mappings):
                entry = s.mappings[s.active_mapping_index]

                box = layout.box()
                box.label(text=f"Selected Mapping {s.active_mapping_index + 1}")

                if s.custom_rig and s.custom_rig.type == 'ARMATURE':
                    box.prop_search(entry, "custom_bone", s.custom_rig.data, "bones", text="Custom")
                else:
                    box.prop(entry, "custom_bone", text="Custom")

                if s.target_rig and s.target_rig.type == 'ARMATURE':
                    box.prop_search(entry, "target_bone", s.target_rig.data, "bones", text="Rename To")
                else:
                    box.prop(entry, "target_bone", text="Rename To")

                status_icon = 'CHECKMARK' if entry.is_valid else 'ERROR'
                box.label(text=entry.status, icon=status_icon)

                op = box.operator("t8tools.bone_mapper_remove_row", text="Remove Selected Mapping", icon='X')
                op.index = s.active_mapping_index

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Presets")
        col.prop(s, "preset_path")

        row = col.row(align=True)
        row.operator("t8tools.bone_mapper_save_preset", text="Save Preset", icon='FILE_TICK')
        row.operator("t8tools.bone_mapper_load_preset", text="Load Preset", icon='FILE_FOLDER')
        col.operator("t8tools.bone_mapper_select_mapped_bones", text="Select Mapped Bones", icon='BONE_DATA')


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
    T8TOOLS_OT_BoneMapper_SavePreset,
    T8TOOLS_OT_BoneMapper_LoadPreset,
    T8TOOLS_OT_BoneMapper_SelectMappedBones,
    T8TOOLS_OT_BoneMapper_AddRowsFromSelection,
    T8TOOLS_UL_BoneMapperMappings,
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