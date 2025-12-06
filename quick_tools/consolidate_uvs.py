import bpy
from bpy.types import Operator, Panel
from mathutils import Vector

def debug_print(*args, **kwargs):
    # Simple local debug helper to avoid circular imports
    print("[T8 QuickTools][Consolidate UVs]", *args)


def tb_create_and_set_active_uv_map(context, settings):
    """
    Ensure each selected mesh has a UV map with the desired name.
    If override is enabled: reuse or create that exact name.
    If override is disabled: always create a new layer (Blender will suffix .001, .002, ...).
    """
    uv_name = settings.consolidated_uv_name.strip() or "Consolidated"
    meshes = [o for o in context.selected_objects if o.type == 'MESH']

    for obj in meshes:
        me = obj.data
        if not me.uv_layers:
            # No UVs at all – just create the target map so pack can work on something
            if settings.consolidated_uv_override:
                uv_map = me.uv_layers.get(uv_name)
                if uv_map is None:
                    uv_map = me.uv_layers.new(name=uv_name)
            else:
                uv_map = me.uv_layers.new(name=uv_name)
            me.uv_layers.active = uv_map
            continue

        if settings.consolidated_uv_override:
            uv_map = me.uv_layers.get(uv_name)
            if uv_map is None:
                uv_map = me.uv_layers.new(name=uv_name)
        else:
            uv_map = me.uv_layers.new(name=uv_name)

        me.uv_layers.active = uv_map


def tb_pack_uv_islands_for_selected(context, settings):
    """
    Multi-object pack:
    - Uses whatever UV map is currently active on each mesh (we just set it to the consolidated one).
    - Runs the same sequence you used in your 3.6 script.
    """
    meshes = [o for o in context.selected_objects if o.type == 'MESH']
    if not meshes:
        return 0

    # Remember selection / active / mode
    prev_active = context.view_layer.objects.active
    prev_mode = prev_active.mode if prev_active else 'OBJECT'
    prev_selection = [obj for obj in context.view_layer.objects if obj.select_get()]

    # Make sure we're in Object Mode
    if context.object and context.object.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    processed = 0

    try:
        # Select only our meshes and go into multi-object edit
        bpy.ops.object.select_all(action='DESELECT')
        for obj in meshes:
            obj.select_set(True)
        context.view_layer.objects.active = meshes[0]

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='SELECT')

        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.average_islands_scale()

        # Pin all, pack, then clear pins
        bpy.ops.uv.pin()
        try:
            bpy.ops.uv.pack_islands(
                shape_method='CONCAVE',
                rotate=False,
                margin=0.003,
                margin_method='SCALED'
            )
        except TypeError:
            bpy.ops.uv.pack_islands(margin=0.003)

        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pin(clear=True)

        bpy.ops.object.mode_set(mode='OBJECT')
        processed = len(meshes)

    except Exception as e:
        debug_print(settings, f"UV pack failed: {e}")
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    # Restore previous selection / active / mode
    bpy.ops.object.select_all(action='DESELECT')
    for obj in prev_selection:
        if obj and obj.name in context.view_layer.objects:
            obj.select_set(True)

    if prev_active and prev_active.name in context.view_layer.objects:
        context.view_layer.objects.active = prev_active
        try:
            bpy.ops.object.mode_set(mode=prev_mode)
        except Exception:
            pass

    return processed


def tb_consolidate_uvs(context, settings):
    """
    High-level UV consolidation entry point.
    """
    tb_create_and_set_active_uv_map(context, settings)
    return tb_pack_uv_islands_for_selected(context, settings)


class TEXTUREBAKER_OT_consolidate_uvs(Operator):
    """Create a 'Consolidated' (or custom named) UV map on selected meshes and pack islands"""
    bl_idname = "t8tools.consolidate_uvs"
    bl_label = "Consolidate UVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.texture_baker_settings

        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if not meshes:
            self.report({'WARNING'}, "No selected mesh objects.")
            return {'CANCELLED'}

        processed = tb_consolidate_uvs(context, settings)

        if processed == 0:
            self.report({'WARNING'}, "No meshes were processed for UV consolidation.")
        else:
            uv_name = settings.consolidated_uv_name.strip() or "Consolidated"
            self.report({'INFO'}, f"Consolidated UV '{uv_name}' updated on {processed} mesh object(s).")

        return {'FINISHED'}


class TEXTUREBAKER_PT_quick_uvs(Panel):
    bl_label = "Consolidate UVs"
    bl_idname = "TEXTUREBAKER_PT_quick_uvs"
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

        box_uv = layout.box()
        box_uv.label(text="Consolidate UVs", icon='GROUP_UVS')
        row = box_uv.row(align=True)
        row.prop(settings, "consolidated_uv_name", text="Name")
        box_uv.prop(settings, "consolidated_uv_override")
        box_uv.operator("texture_baker.consolidate_uvs", text="Create / Pack UVs")


classes = (
    TEXTUREBAKER_OT_consolidate_uvs,
    TEXTUREBAKER_PT_quick_uvs,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
