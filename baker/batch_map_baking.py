import os
import bpy
from bpy.types import Operator, Panel
from bpy.props import StringProperty

from .texture_baker import get_map_suffix, debug_print


class TEXTUREBAKER_OT_batch_bake(Operator):
    """Batch bake multiple map types and save images to a chosen folder"""
    bl_idname = "t8tools.batch_bake"
    bl_label = "Batch Bake to Folder"
    bl_options = {'REGISTER', 'UNDO'}

    directory: StringProperty(
        name="Target Folder",
        description="Folder where baked images will be saved",
        subtype='DIR_PATH',
    )

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "No directory selected.")
            return {'CANCELLED'}

        settings = context.scene.texture_baker_settings
        scene = context.scene

        if not context.selected_objects:
            self.report({'WARNING'}, "No selected objects to bake.")
            return {'CANCELLED'}

        # Build list of map types from settings
        map_order = []
        if settings.batch_rma:
            map_order.append('RMA')
        if settings.batch_mra:
            map_order.append('MRA')
        if settings.batch_obd:
            map_order.append('OBD')
        if settings.batch_tse:
            map_order.append('TSE')
        if settings.batch_pc:
            map_order.append('PC')
        if settings.batch_c:
            map_order.append('C')
        if settings.batch_n:
            map_order.append('N')

        if not map_order:
            self.report({'WARNING'}, "No map types selected for batch baking.")
            return {'CANCELLED'}

        # Ensure directory exists
        os.makedirs(self.directory, exist_ok=True)

        # Keep reference to active object for naming
        active_mesh = context.view_layer.objects.active
        base_name = active_mesh.name if active_mesh else "Baked"

        wm = context.window_manager
        total = len(map_order)
        wm.progress_begin(0, total)

        saved_files = []

        try:
            for i, map_type in enumerate(map_order):
                wm.progress_update(i)
                settings.map_type = map_type

                # Status in the Info/Status area
                self.report({'INFO'}, f"Batch baking {map_type} ({i+1}/{total})...")

                # Call the existing single bake operator
                result = bpy.ops.t8tools.bake('EXEC_DEFAULT')
                if result != {'FINISHED'}:
                    self.report({'ERROR'}, f"Batch bake aborted while baking {map_type}.")
                    break

                # Fetch the image and save to folder
                img_name = base_name + get_map_suffix(map_type)
                img = bpy.data.images.get(img_name)
                if img is None:
                    debug_print(settings, f"Image '{img_name}' not found after baking {map_type}.")
                    continue

                filename = img_name + ".png"
                path = os.path.join(self.directory, filename)

                img.filepath_raw = path
                img.file_format = 'PNG'
                try:
                    img.save()
                    saved_files.append(filename)
                    debug_print(settings, f"Saved {map_type} to '{path}'")
                except Exception as e:
                    self.report({'WARNING'}, f"Failed to save {img_name}: {e}")

        finally:
            wm.progress_end()

        if saved_files:
            self.report(
                {'INFO'},
                f"Batch bake complete. Saved {len(saved_files)} file(s): {', '.join(saved_files)}"
            )
        else:
            self.report({'WARNING'}, "Batch bake finished but no images were saved.")

        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class TEXTUREBAKER_PT_batch(Panel):
    """Batch map baking panel"""
    bl_label = "Batch Map Baking"
    bl_idname = "TEXTUREBAKER_PT_batch"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_baking"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and hasattr(context.scene, "texture_baker_settings")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.texture_baker_settings

        layout.label(text="Select Maps to Bake:")

        row = layout.row(align=True)
        col1 = row.column()
        col2 = row.column()

        col1.prop(settings, "batch_rma")
        col1.prop(settings, "batch_mra")
        col1.prop(settings, "batch_obd")

        col2.prop(settings, "batch_tse")
        col2.prop(settings, "batch_pc")
        col2.prop(settings, "batch_c")
        col2.prop(settings, "batch_n")

        layout.label(
            text="Note: ID maps are not included in batch. Use single Bake for ID.",
            icon='INFO'
        )

        layout.separator()
        layout.operator(
            "t8tools.batch_bake",
            text="Batch Bake to Folder...",
            icon='RENDER_STILL'
        )


classes = (
    TEXTUREBAKER_OT_batch_bake,
    TEXTUREBAKER_PT_batch,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
