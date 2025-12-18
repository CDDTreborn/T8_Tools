bl_info = {
    "name": "T8 Tools",
    "author": "You + ChatGPT",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > T8 Tools; Shader Editor > ID System; Object Menu > FBX Root Fix",
    "description": "Suite of tools for baking, mesh utilities, ID systems, and FBX exporter fixes.",
    "category": "3D View",
}

import bpy
from bpy.types import AddonPreferences, Panel
from bpy.props import BoolProperty

# ------------------------------------------------------------------------
# Imports for submodules
# ------------------------------------------------------------------------

from .baker import (
    batch_map_baking,
    texture_baker,
)

from .quick_tools import (
    consolidate_uvs,
    quick_weight_transfer,
    duplicate_mat_cleanup,
    modifier_pause,
)

from .mesh_tools import (
    blend_mode_switch,
    rig_match,
    multires_pipeline,
)

from .image_tools import (
    collect_images,
)

from .shader_tools import (
    id_system,
)

from .system_tools import (
    fbx_root_fix,
    asset_packs,
)


# For convenience, group modules by feature area
BAKING_MODULES = (
    texture_baker,
    batch_map_baking,
)

QUICK_MODULES = (
    consolidate_uvs,
    quick_weight_transfer,
    duplicate_mat_cleanup,
    modifier_pause,
)

IMAGE_MODULES = (
    collect_images,
)

MESH_MODULES = (
    blend_mode_switch,
    rig_match,
    multires_pipeline,
)

SHADER_MODULES = (
    id_system,
)

FBX_MODULES = (
    fbx_root_fix,
)

ASSET_PACK_MODULES = (
    asset_packs,
)


# ------------------------------------------------------------------------
# Add-on Preferences: user can toggle tool groups
# ------------------------------------------------------------------------

class T8ToolsPreferences(AddonPreferences):
    bl_idname = __package__

    use_baking_tools: BoolProperty(
        name="Baking Tools",
        description="Enable Baking Tools (Texture Baker, Batch Map Baking)",
        default=True,
    )
    use_quick_tools: BoolProperty(
        name="Quick Tools",
        description="Enable Quick Tools (Consolidate UVs, Quick Weight Transfer, Duplicate Material Cleanup)",
        default=True,
    )
    use_image_tools: BoolProperty(
        name="Image Tools",
        description="Enable Image Tools (Collect All Images)",
        default=True,
    )
    use_mesh_tools: BoolProperty(
        name="Mesh Tools",
        description="Enable Mesh Tools (Blend Mode Switch, Rig Matcher)",
        default=True,
    )
    use_id_system: BoolProperty(
        name="ID System (Shader Editor)",
        description="Enable ID System panel in Shader Editor",
        default=True,
    )
    use_fbx_root_fix: BoolProperty(
        name="FBX Root Bone Fix",
        description="Enable FBX exporter root-bone fix in Object menu",
        default=True,
    )
    use_asset_packs: BoolProperty(
        name="Asset Packs",
        description="Enable Asset Pack tools (download + register asset libraries)",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="Enable / Disable Tool Groups:", icon='PREFERENCES')
        col.prop(self, "use_baking_tools")
        col.prop(self, "use_quick_tools")
        col.prop(self, "use_image_tools")
        col.prop(self, "use_mesh_tools")
        col.prop(self, "use_id_system")
        col.separator()
        col.prop(self, "use_fbx_root_fix")
        col.prop(self, "use_asset_packs")


# ------------------------------------------------------------------------
# N-Panel organization for 3D Viewport: T8 Tools
# ------------------------------------------------------------------------

class VIEW3D_PT_T8ToolsRoot(Panel):
    """Top-level T8 Tools panel in the 3D Viewport N-panel."""
    bl_label = "T8 Tools"
    bl_idname = "VIEW3D_PT_t8tools_root"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"

    def draw(self, context):
        layout = self.layout
        layout.label(text="T8 Tools", icon='TOOL_SETTINGS')
        layout.label(text="Version 1.0.0")


class VIEW3D_PT_T8Tools_Baking(Panel):
    bl_label = "Baking Tools"
    bl_idname = "VIEW3D_PT_t8tools_baking"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_root"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Texture Baker, Batch Map Baking")


class VIEW3D_PT_T8Tools_Quick(Panel):
    bl_label = "Quick Tools"
    bl_idname = "VIEW3D_PT_t8tools_quick"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_root"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Consolidate UVs, Quick Weight Transfer, Duplicate Material Cleanup, Mofifier Puase")


class VIEW3D_PT_T8Tools_Image(Panel):
    bl_label = "Image Tools"
    bl_idname = "VIEW3D_PT_t8tools_image"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_root"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Collect All Images")


class VIEW3D_PT_T8Tools_Mesh(Panel):
    bl_label = "Mesh Tools"
    bl_idname = "VIEW3D_PT_t8tools_mesh"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_root"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blend Mode Switch, Rig Matcher")


CORE_CLASSES = (
    T8ToolsPreferences,
    VIEW3D_PT_T8ToolsRoot,
    VIEW3D_PT_T8Tools_Baking,
    VIEW3D_PT_T8Tools_Quick,
    VIEW3D_PT_T8Tools_Image,
    VIEW3D_PT_T8Tools_Mesh,
)


# ------------------------------------------------------------------------
# Helper: (un)register submodules based on preferences
# ------------------------------------------------------------------------

def _get_prefs_safe():
    """Gracefully get addon preferences, even on first install."""
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def register_submodules():
    prefs = _get_prefs_safe()

    # If prefs is None (first install), treat everything as enabled
    all_on = (prefs is None)

    if all_on or prefs.use_baking_tools:
        for mod in BAKING_MODULES:
            mod.register()

    if all_on or prefs.use_quick_tools:
        for mod in QUICK_MODULES:
            mod.register()

    if all_on or prefs.use_image_tools:
        for mod in IMAGE_MODULES:
            mod.register()

    if all_on or prefs.use_mesh_tools:
        for mod in MESH_MODULES:
            mod.register()

    if all_on or prefs.use_id_system:
        for mod in SHADER_MODULES:
            mod.register()

    if all_on or prefs.use_fbx_root_fix:
        for mod in FBX_MODULES:
            mod.register()

    if all_on or prefs.use_asset_packs:
        for mod in ASSET_PACK_MODULES:
            mod.register()


def unregister_submodules():
    prefs = _get_prefs_safe()
    all_on = (prefs is None)

    # Unregister in reverse-ish order

    if all_on or (prefs and prefs.use_asset_packs):
        for mod in reversed(ASSET_PACK_MODULES):
            mod.unregister()

    if all_on or (prefs and prefs.use_fbx_root_fix):
        for mod in reversed(FBX_MODULES):
            mod.unregister()

    if all_on or (prefs and prefs.use_id_system):
        for mod in reversed(SHADER_MODULES):
            mod.unregister()

    if all_on or (prefs and prefs.use_mesh_tools):
        for mod in reversed(MESH_MODULES):
            mod.unregister()

    if all_on or (prefs and prefs.use_image_tools):
        for mod in reversed(IMAGE_MODULES):
            mod.unregister()

    if all_on or (prefs and prefs.use_quick_tools):
        for mod in reversed(QUICK_MODULES):
            mod.unregister()

    if all_on or (prefs and prefs.use_baking_tools):
        for mod in reversed(BAKING_MODULES):
            mod.unregister()


# ------------------------------------------------------------------------
# Blender registration
# ------------------------------------------------------------------------

def register():
    for cls in CORE_CLASSES:
        bpy.utils.register_class(cls)

    register_submodules()


def unregister():
    unregister_submodules()

    for cls in reversed(CORE_CLASSES):
        bpy.utils.unregister_class(cls)
