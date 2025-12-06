import bpy
from bpy.types import Operator, Panel
from bpy.props import StringProperty


def _material_duplicate_mapping(context):
    """
    Build a mapping of duplicate material names to their base materials
    among selected objects only.

    Example: 'Mat.001' -> 'Mat' (if 'Mat' exists).
    """
    mapping = {}
    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat:
                continue
            name = mat.name
            parts = name.rsplit('.', 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_name = parts[0]
                if base_name in bpy.data.materials:
                    mapping[name] = base_name
    return mapping


class TEXTUREBAKER_OT_cleanup_material_duplicates(Operator):
    """Replace duplicate materials (Mat.001, Mat.002, ...) with their base material (Mat) on selected meshes"""
    bl_idname = "t8tools.cleanup_material_duplicates"
    bl_label = "Duplicate Material Cleanup"
    bl_options = {'REGISTER', 'UNDO'}

    material_report: StringProperty(
        name="Summary",
        default="",
        options={'HIDDEN'},
    )

    def invoke(self, context, event):
        mapping = _material_duplicate_mapping(context)
        if not mapping:
            self.report({'INFO'}, "No duplicate materials found among selected objects.")
            return {'CANCELLED'}

        lines = []
        for dup, base in sorted(mapping.items()):
            lines.append(f"{dup}  →  {base}")

        # Limit lines so the dialog doesn't get absurdly tall
        max_lines = 32
        if len(lines) > max_lines:
            shown = lines[:max_lines]
            shown.append(f"... and {len(lines) - max_lines} more.")
            lines = shown

        self.material_report = "\n".join(lines)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.label(text="The following materials will be remapped:")
        for line in self.material_report.splitlines():
            layout.label(text=line)

    def execute(self, context):
        mapping = _material_duplicate_mapping(context)
        if not mapping:
            self.report({'INFO'}, "No duplicate materials to remap.")
            return {'CANCELLED'}

        changes = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if not mat:
                    continue
                base_name = mapping.get(mat.name)
                if base_name:
                    base_mat = bpy.data.materials.get(base_name)
                    if base_mat:
                        slot.material = base_mat
                        changes += 1

        if changes == 0:
            self.report({'INFO'}, "No material slots were changed.")
        else:
            self.report({'INFO'}, f"Remapped {changes} material slot(s) to base materials.")
        return {'FINISHED'}


class TEXTUREBAKER_PT_quick_materials(Panel):
    bl_label = "Duplicate Material Cleanup"
    bl_idname = "TEXTUREBAKER_PT_quick_materials"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_quick"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        box_mat = layout.box()
        box_mat.label(text="Duplicate Material Cleanup", icon='NODE_MATERIAL')
        box_mat.operator("texture_baker.cleanup_material_duplicates",
                         text="Remap Duplicates → Base")


classes = (
    TEXTUREBAKER_OT_cleanup_material_duplicates,
    TEXTUREBAKER_PT_quick_materials,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
