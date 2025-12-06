import bpy
from bpy.types import Operator, Panel


class TEXTUREBAKER_OT_set_blend_mode(Operator):
    """Set blend mode on all materials for selected meshes"""
    bl_idname = "t8tools.set_blend_mode"
    bl_label = "Apply Blend Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.texture_baker_settings
        mode = settings.blend_mode

        if not context.selected_objects:
            self.report({'WARNING'}, "No selected objects.")
            return {'CANCELLED'}

        mats_changed = 0
        meshes = [o for o in context.selected_objects if o.type == 'MESH']

        for obj in meshes:
            for slot in obj.material_slots:
                mat = slot.material
                if not mat:
                    continue

                # 3.x / 4.x compatibility
                if hasattr(mat, "blend_method"):
                    if mat.blend_method != mode:
                        mat.blend_method = mode
                        mats_changed += 1
                elif hasattr(mat, "blend_mode"):
                    if mat.blend_mode != mode:
                        mat.blend_mode = mode
                        mats_changed += 1

        if mats_changed == 0:
            self.report({'INFO'}, "No materials changed (nothing selected, or already set).")
        else:
            self.report({'INFO'}, f"Updated blend mode on {mats_changed} material slot(s).")
        return {'FINISHED'}


class TEXTUREBAKER_PT_blend_mode(Panel):
    bl_label = "Blend Mode Switch"
    bl_idname = "TEXTUREBAKER_PT_blend_mode"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_mesh"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "texture_baker_settings")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.texture_baker_settings

        box_blend = layout.box()
        box_blend.label(text="Blend Mode Switch", icon='MATERIAL')
        row = box_blend.row(align=True)
        row.prop(settings, "blend_mode", text="")
        box_blend.operator("texture_baker.set_blend_mode", text="Apply to Selected")


classes = (
    TEXTUREBAKER_OT_set_blend_mode,
    TEXTUREBAKER_PT_blend_mode,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
