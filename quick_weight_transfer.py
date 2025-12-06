import bpy
from bpy.types import Operator, Panel

from .baker.texture_baker import debug_print


class TEXTUREBAKER_OT_add_weight_transfer_mods(Operator):
    """Add Data Transfer modifiers for quick weight transfer from active to other selected meshes"""
    bl_idname = "t8tools.add_weight_transfer_mods"
    bl_label = "Add Weight Transfer Mods"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.texture_baker_settings

        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if len(meshes) < 2:
            self.report({'WARNING'}, "Select at least two mesh objects (active will be the source).")
            return {'CANCELLED'}

        # Remember original active + mode
        prev_active = context.view_layer.objects.active
        prev_mode = prev_active.mode if prev_active else 'OBJECT'

        # Ensure Object Mode
        if context.object and context.object.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        # Source = active mesh, or first in list
        source = context.view_layer.objects.active
        if source not in meshes:
            source = meshes[0]
            context.view_layer.objects.active = source

        added = 0
        for obj in meshes:
            if obj == source:
                continue

            dt = obj.modifiers.new(name="TB_WeightTransfer", type='DATA_TRANSFER')
            dt.object = source

            # Vertex group weights only
            dt.use_vert_data = True
            try:
                dt.data_types_verts = {'VGROUP_WEIGHTS'}
            except Exception:
                dt.data_types_verts = {'VGROUP_WEIGHTS'}

            # Mapping – safe across 3.6–4.5
            dt.vert_mapping = 'POLYINTERP_NEAREST'
            dt.use_object_transform = True

            # Optional max distance
            if hasattr(dt, "use_max_distance"):
                dt.use_max_distance = True
                dt.max_distance = 10.0

            dt.mix_mode = 'REPLACE'
            dt.mix_factor = 1.0

            # Optional: auto-generate data layers, based on user setting
            if settings.auto_generate_data_layers:
                try:
                    context.view_layer.objects.active = obj
                    bpy.ops.object.datalayout_transfer(modifier=dt.name)
                except Exception as e:
                    debug_print(settings, f"Data layout transfer failed on {obj.name}: {e}")

            added += 1

        # Restore original active + mode
        if prev_active:
            context.view_layer.objects.active = prev_active
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except Exception:
                pass

        if settings.auto_generate_data_layers:
            msg = f"Added weight transfer modifiers + generated data layers on {added} mesh object(s). Source: {source.name}"
        else:
            msg = f"Added weight transfer modifiers on {added} mesh object(s). Source: {source.name} (Generate Data Layers manually)."

        self.report({'INFO'}, msg)
        return {'FINISHED'}


class TEXTUREBAKER_OT_clear_vertex_groups(Operator):
    """Delete all vertex groups from selected meshes"""
    bl_idname = "t8tools.clear_vertex_groups"
    bl_label = "Delete Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, "No selected mesh objects.")
            return {'CANCELLED'}

        cleared = 0
        for obj in meshes:
            if obj.vertex_groups:
                obj.vertex_groups.clear()
                cleared += 1

        if cleared == 0:
            self.report({'INFO'}, "No vertex groups found to delete.")
        else:
            self.report({'INFO'}, f"Deleted vertex groups on {cleared} mesh object(s).")
        return {'FINISHED'}


class TEXTUREBAKER_PT_quick_weights(Panel):
    bl_label = "Quick Weight Transfer"
    bl_idname = "TEXTUREBAKER_PT_quick_weights"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_quick"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "texture_baker_settings")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.texture_baker_settings

        box_weight = layout.box()
        box_weight.label(text="Quick Weight Transfer", icon='MOD_DATA_TRANSFER')
        box_weight.prop(settings, "auto_generate_data_layers",
                        text="Auto-generate Data Layers")
        box_weight.operator("texture_baker.add_weight_transfer_mods",
                            text="Add Data Transfer Modifiers")
        box_weight.operator("texture_baker.clear_vertex_groups",
                            text="Delete Vertex Groups")


classes = (
    TEXTUREBAKER_OT_add_weight_transfer_mods,
    TEXTUREBAKER_OT_clear_vertex_groups,
    TEXTUREBAKER_PT_quick_weights,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
