import os
import shutil
import bpy
from bpy.types import Operator, Panel
from bpy.props import StringProperty


def collect_images_from_node_tree(node_tree, images, visited):
    """Recursively collect images from a node tree, including nested node groups."""
    if not node_tree:
        return

    if node_tree in visited:
        return
    visited.add(node_tree)

    for node in node_tree.nodes:
        # Standard image texture node
        if node.type == "TEX_IMAGE" and getattr(node, "image", None):
            images.add(node.image)

        # Node group: recurse into its node tree
        elif node.type == "GROUP" and getattr(node, "node_tree", None):
            collect_images_from_node_tree(node.node_tree, images, visited)


def tb_get_images_from_selected_meshes(context):
    images = set()
    visited_trees = set()

    for obj in context.selected_objects:
        if obj.type != 'MESH':
            continue

        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes or not mat.node_tree:
                continue

            collect_images_from_node_tree(mat.node_tree, images, visited_trees)

    return images


def tb_save_or_copy_image(image, target_dir):
    """Copy an existing image file, or save packed/generated images as PNG."""
    # Ensure target directory exists
    os.makedirs(target_dir, exist_ok=True)

    # Try to use the existing file path
    src = bpy.path.abspath(image.filepath_raw or image.filepath)

    # If image has an external file and it exists, copy it
    if src and os.path.exists(src) and not image.packed_file:
        filename = os.path.basename(src)
        dst = os.path.join(target_dir, filename)

        # Avoid copying onto itself
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)

        return dst

    # Otherwise, save it out as a PNG (for packed or generated images)
    base_name = bpy.path.clean_name(image.name)
    dst = os.path.join(target_dir, base_name + ".png")

    image.filepath_raw = dst
    image.file_format = 'PNG'
    image.save()

    return dst


class TEXTUREBAKER_OT_collect_images_from_selected(Operator):
    """Collect all images used by materials (including node groups) on selected meshes and save to a folder"""
    bl_idname = "t8tools.collect_images_from_selected"
    bl_label = "Collect Images From Selected"
    bl_options = {'REGISTER', 'UNDO'}

    directory: StringProperty(
        name="Target Folder",
        description="Folder where the images will be saved/copied",
        subtype='DIR_PATH'
    )

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "No directory selected.")
            return {'CANCELLED'}

        images = tb_get_images_from_selected_meshes(context)

        if not images:
            self.report({'WARNING'}, "No images found on selected meshes (including node groups).")
            return {'CANCELLED'}

        saved_paths = []
        for img in images:
            try:
                path = tb_save_or_copy_image(img, self.directory)
                saved_paths.append(path)
            except Exception as e:
                self.report({'WARNING'}, f"Failed to save/copy {img.name}: {e}")

        self.report({'INFO'}, f"Processed {len(images)} images. Saved {len(saved_paths)} files.")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class TEXTUREBAKER_PT_image_tools(Panel):
    """Image collector panel"""
    bl_label = "Image Tools"
    bl_idname = "TEXTUREBAKER_PT_image_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_image"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        layout.label(text="Collect Images:", icon='IMAGE_DATA')
        layout.label(text="From materials on selected meshes")
        layout.operator(
            "texture_baker.collect_images_from_selected",
            text="Collect Images From Selected (Choose Folder)",
            icon='FILE_FOLDER'
        )


classes = (
    TEXTUREBAKER_OT_collect_images_from_selected,
    TEXTUREBAKER_PT_image_tools,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
