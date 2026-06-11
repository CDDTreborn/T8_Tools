import bpy
import json
import os

from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    UIList,
)

from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
)


# ============================================================
# Constants
# ============================================================

ELEMENT_TYPES = [
    ("BASE_COLOR", "Base Color", ""),
    ("AO", "Ambient Occlusion", ""),
    ("ROUGHNESS", "Roughness", ""),
    ("METALLIC", "Metallic", ""),
    ("SPECULAR", "Specular", ""),
    ("NORMAL", "Normal", ""),
    ("ALPHA", "Alpha", ""),
    ("EMISSION", "Emission", ""),
]

SOURCE_TYPES = [
    ("TEXTURE", "Texture", "Use a texture source"),
    ("VALUE", "Value", "Use a constant numeric value"),
    ("DISABLED", "Disabled", "Do not use this element"),
]

MATCH_MODES = [
    ("SUFFIX", "Suffix", "Texture name ends with this identifier"),
    ("PREFIX", "Prefix", "Texture name starts with this identifier"),
    ("CONTAINS", "Contains", "Texture name contains this identifier"),
    ("EXACT", "Exact", "Texture name matches this identifier exactly"),
]

CHANNELS = [
    ("RGB", "RGB", "Use RGB"),
    ("R", "Red", "Use red channel"),
    ("G", "Green", "Use green channel"),
    ("B", "Blue", "Use blue channel"),
    ("A", "Alpha", "Use alpha channel"),
]

COLORSPACES = [
    ("SRGB", "sRGB", "Color texture"),
    ("NON_COLOR", "Non-Color", "Data texture"),
]

ALPHA_MODES = [
    ("STRAIGHT", "Straight", ""),
    ("PREMULTIPLIED", "Premultiplied", ""),
    ("CHANNEL_PACKED", "Channel Packed", ""),
    ("NONE", "None", ""),
]

# ============================================================
# Data Model
# ============================================================

class T8SPB_IdentifierRule(PropertyGroup):
    identifier: StringProperty(
        name="Identifier",
        description="Suffix, prefix, contains text, or exact texture name",
        default="",
    )

    match_mode: EnumProperty(
        name="Match",
        description="How this identifier should match texture names",
        items=MATCH_MODES,
        default="SUFFIX",
    )


class T8SPB_ShaderElement(PropertyGroup):
    element_type: EnumProperty(
        name="Element",
        items=ELEMENT_TYPES,
        default="BASE_COLOR",
    )

    enabled: BoolProperty(
        name="Enabled",
        default=True,
    )

    source_type: EnumProperty(
        name="Source",
        items=SOURCE_TYPES,
        default="TEXTURE",
    )

    identifiers: CollectionProperty(type=T8SPB_IdentifierRule)
    identifiers_index: IntProperty(default=0)

    channel: EnumProperty(
        name="Channel",
        items=CHANNELS,
        default="RGB",
    )

    colorspace: EnumProperty(
        name="Color Space",
        items=COLORSPACES,
        default="NON_COLOR",
    )

    alpha_mode: EnumProperty(
        name="Alpha Mode",
        items=ALPHA_MODES,
        default="STRAIGHT",
    )

    default_value: FloatProperty(
        name="Fallback / Value",
        description="Used when source is Value or when texture is missing",
        default=0.5,
        min=0.0,
        max=1.0,
    )

    preview_image: PointerProperty(
        name="Preview Image",
        description="Optional loaded Blender image for preview/testing",
        type=bpy.types.Image,
    )


class T8SPB_ScannedGroup(PropertyGroup):
    name: StringProperty(default="")
    node_name: StringProperty(default="")
    depth: IntProperty(default=0)
    inputs: StringProperty(default="")
    outputs: StringProperty(default="")
    node_count: IntProperty(default=0)
    internal_group_count: IntProperty(default=0)


class T8SPB_ProfileSettings(PropertyGroup):
    profile_name: StringProperty(
        name="Profile Name",
        default="New Shader Profile",
    )

    save_path: StringProperty(
        name="Profile JSON Path",
        description="Path to save/load shader profile JSON",
        subtype="FILE_PATH",
        default="",
    )

    elements: CollectionProperty(type=T8SPB_ShaderElement)
    elements_index: IntProperty(default=0)

    scanned_groups: CollectionProperty(type=T8SPB_ScannedGroup)
    scanned_groups_index: IntProperty(default=0)


# ============================================================
# Helpers
# ============================================================

def get_settings(context):
    return context.scene.t8_shader_profile_builder


def element_label(element_type):
    for key, label, _desc in ELEMENT_TYPES:
        if key == element_type:
            return label
    return element_type


def ensure_default_elements(settings):
    """Create one entry for each major shader element if missing."""
    existing = {e.element_type for e in settings.elements}

    defaults = {
        "BASE_COLOR": {
            "source_type": "TEXTURE",
            "channel": "RGB",
            "colorspace": "SRGB",
            "default_value": 1.0,
            "identifiers": [("_D", "SUFFIX"), ("_BaseColor", "SUFFIX"), ("_Albedo", "SUFFIX")],
        },
        "NORMAL": {
            "source_type": "TEXTURE",
            "channel": "RGB",
            "colorspace": "NON_COLOR",
            "default_value": 0.0,
            "identifiers": [("_N", "SUFFIX"), ("_Normal", "SUFFIX")],
        },
        "ROUGHNESS": {
            "source_type": "TEXTURE",
            "channel": "G",
            "colorspace": "NON_COLOR",
            "default_value": 0.5,
            "identifiers": [("_M", "SUFFIX"), ("_R", "SUFFIX"), ("_Roughness", "SUFFIX")],
        },
        "METALLIC": {
            "source_type": "VALUE",
            "channel": "R",
            "colorspace": "NON_COLOR",
            "default_value": 0.0,
            "identifiers": [("_M", "SUFFIX"), ("_Metallic", "SUFFIX")],
        },
        "AO": {
            "source_type": "TEXTURE",
            "channel": "R",
            "colorspace": "NON_COLOR",
            "default_value": 1.0,
            "identifiers": [("_M", "SUFFIX"), ("_AO", "SUFFIX")],
        },
        "SPECULAR": {
            "source_type": "VALUE",
            "channel": "R",
            "colorspace": "NON_COLOR",
            "default_value": 0.5,
            "identifiers": [("_S", "SUFFIX"), ("_Specular", "SUFFIX")],
        },
        "ALPHA": {
            "source_type": "DISABLED",
            "channel": "A",
            "colorspace": "NON_COLOR",
            "default_value": 1.0,
            "identifiers": [("_A", "SUFFIX"), ("_Alpha", "SUFFIX")],
        },
        "EMISSION": {
            "source_type": "DISABLED",
            "channel": "RGB",
            "colorspace": "SRGB",
            "default_value": 0.0,
            "identifiers": [("_E", "SUFFIX"), ("_Emission", "SUFFIX")],
        },
    }

    for element_type, cfg in defaults.items():
        if element_type in existing:
            continue

        item = settings.elements.add()
        item.element_type = element_type
        item.enabled = cfg["source_type"] != "DISABLED"
        item.source_type = cfg["source_type"]
        item.channel = cfg["channel"]
        item.colorspace = cfg["colorspace"]
        item.alpha_mode = cfg.get("alpha_mode", "STRAIGHT")
        item.default_value = cfg["default_value"]

        for ident, mode in cfg["identifiers"]:
            rule = item.identifiers.add()
            rule.identifier = ident
            rule.match_mode = mode


def profile_to_dict(settings):
    data = {
        "profile_name": settings.profile_name,
        "version": 1,
        "elements": [],
    }

    for element in settings.elements:
        data["elements"].append({
            "element_type": element.element_type,
            "enabled": bool(element.enabled),
            "source_type": element.source_type,
            "channel": element.channel,
            "colorspace": element.colorspace,
            "alpha_mode": element.alpha_mode,
            "default_value": float(element.default_value),
            "identifiers": [
                {
                    "identifier": rule.identifier,
                    "match_mode": rule.match_mode,
                }
                for rule in element.identifiers
            ],
        })

    return data


def load_profile_from_dict(settings, data):
    settings.profile_name = data.get("profile_name", "Loaded Shader Profile")
    settings.elements.clear()

    for e_data in data.get("elements", []):
        element = settings.elements.add()
        element.element_type = e_data.get("element_type", "BASE_COLOR")
        element.enabled = bool(e_data.get("enabled", True))
        element.source_type = e_data.get("source_type", "TEXTURE")
        element.channel = e_data.get("channel", "RGB")
        element.colorspace = e_data.get("colorspace", "NON_COLOR")
        element.alpha_mode = e_data.get("alpha_mode", "STRAIGHT")
        element.default_value = float(e_data.get("default_value", 0.5))

        for r_data in e_data.get("identifiers", []):
            rule = element.identifiers.add()
            rule.identifier = r_data.get("identifier", "")
            rule.match_mode = r_data.get("match_mode", "SUFFIX")


# ============================================================
# UI Lists
# ============================================================

class T8SPB_UL_Elements(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        element = item
        row = layout.row(align=True)

        icon_name = "CHECKBOX_HLT" if element.enabled else "CHECKBOX_DEHLT"
        row.label(text=element_label(element.element_type), icon=icon_name)

        if element.source_type == "TEXTURE":
            row.label(text=f"{element.channel} / {element.colorspace}")
        elif element.source_type == "VALUE":
            row.label(text=f"Value {element.default_value:.2f}")
        else:
            row.label(text="Disabled")


class T8SPB_UL_IdentifierRules(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        rule = item
        row = layout.row(align=True)
        row.prop(rule, "match_mode", text="")
        row.prop(rule, "identifier", text="")


class T8SPB_UL_ScannedGroups(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        indent = "  " * item.depth
        row = layout.row(align=True)
        row.label(text=f"{indent}{item.name}", icon="NODETREE")
        row.label(text=f"{item.node_count} nodes")


# ============================================================
# Operators
# ============================================================

class T8SPB_OT_InitDefaults(Operator):
    bl_idname = "t8_shader_profile.init_defaults"
    bl_label = "Initialize Default Elements"
    bl_description = "Create default shader element slots"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_settings(context)
        ensure_default_elements(settings)
        self.report({"INFO"}, "Default shader profile elements initialized.")
        return {"FINISHED"}


class T8SPB_OT_ClearProfile(Operator):
    bl_idname = "t8_shader_profile.clear_profile"
    bl_label = "Clear Profile"
    bl_description = "Clear the current shader profile"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_settings(context)
        settings.profile_name = "New Shader Profile"
        settings.elements.clear()
        settings.elements_index = 0
        self.report({"INFO"}, "Shader profile cleared.")
        return {"FINISHED"}


class T8SPB_OT_AddIdentifier(Operator):
    bl_idname = "t8_shader_profile.add_identifier"
    bl_label = "Add Identifier"
    bl_description = "Add a texture matching rule to the selected shader element"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_settings(context)

        if not settings.elements:
            self.report({"WARNING"}, "No shader element selected.")
            return {"CANCELLED"}

        element = settings.elements[settings.elements_index]
        rule = element.identifiers.add()
        rule.identifier = ""
        rule.match_mode = "SUFFIX"
        element.identifiers_index = len(element.identifiers) - 1

        return {"FINISHED"}


class T8SPB_OT_RemoveIdentifier(Operator):
    bl_idname = "t8_shader_profile.remove_identifier"
    bl_label = "Remove Identifier"
    bl_description = "Remove selected texture matching rule"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_settings(context)

        if not settings.elements:
            return {"CANCELLED"}

        element = settings.elements[settings.elements_index]

        if not element.identifiers:
            return {"CANCELLED"}

        idx = element.identifiers_index
        element.identifiers.remove(idx)
        element.identifiers_index = min(max(0, idx - 1), len(element.identifiers) - 1)

        return {"FINISHED"}


class T8SPB_OT_SaveProfile(Operator):
    bl_idname = "t8_shader_profile.save_profile"
    bl_label = "Save Profile JSON"
    bl_description = "Save current shader profile to JSON"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        settings = get_settings(context)

        safe_name = settings.profile_name.strip()
        if not safe_name:
            safe_name = "New_Shader_Profile"

        # Replace unsafe filename characters
        for ch in '<>:"/\\|?*':
            safe_name = safe_name.replace(ch, "_")

        safe_name = safe_name.replace(" ", "_")

        if settings.save_path:
            folder = os.path.dirname(bpy.path.abspath(settings.save_path))
            self.filepath = os.path.join(folder, f"{safe_name}.json")
        else:
            self.filepath = f"{safe_name}.json"

        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = get_settings(context)

        if not self.filepath.lower().endswith(".json"):
            self.filepath += ".json"

        data = profile_to_dict(settings)

        try:
            folder = os.path.dirname(self.filepath)
            if folder and not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)

            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            settings.save_path = self.filepath
            self.report({"INFO"}, f"Saved shader profile: {self.filepath}")
            return {"FINISHED"}

        except Exception as ex:
            self.report({"ERROR"}, f"Failed to save shader profile: {ex}")
            return {"CANCELLED"}


class T8SPB_OT_LoadProfile(Operator):
    bl_idname = "t8_shader_profile.load_profile"
    bl_label = "Load Profile JSON"
    bl_description = "Load shader profile from JSON"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        settings = get_settings(context)

        if settings.save_path:
            self.filepath = bpy.path.abspath(settings.save_path)

        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = get_settings(context)

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            load_profile_from_dict(settings, data)
            settings.save_path = self.filepath

            self.report({"INFO"}, f"Loaded shader profile: {self.filepath}")
            return {"FINISHED"}

        except Exception as ex:
            self.report({"ERROR"}, f"Failed to load shader profile: {ex}")
            return {"CANCELLED"}


class T8SPB_OT_LoadPreviewImage(Operator):
    bl_idname = "t8_shader_profile.load_preview_image"
    bl_label = "Load Preview Texture"
    bl_description = "Load a texture image for manual preview/reference"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = get_settings(context)

        if not settings.elements:
            self.report({"WARNING"}, "No shader element selected.")
            return {"CANCELLED"}

        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
            element = settings.elements[settings.elements_index]
            element.preview_image = img

            self.report({"INFO"}, f"Loaded preview image: {img.name}")
            return {"FINISHED"}

        except Exception as ex:
            self.report({"ERROR"}, f"Failed to load preview image: {ex}")
            return {"CANCELLED"}
        


class T8SPB_OT_ScanActiveMaterialGroups(Operator):
    bl_idname = "t8_shader_profile.scan_active_material_groups"
    bl_label = "Scan Active Material Groups"
    bl_description = "Scan the active material for direct and nested node groups"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_settings(context)

        obj = context.object
        if not obj:
            self.report({"WARNING"}, "No active object found.")
            return {"CANCELLED"}

        mat = obj.active_material
        if not mat:
            self.report({"WARNING"}, "Active object has no active material.")
            return {"CANCELLED"}

        if not mat.use_nodes or not mat.node_tree:
            self.report({"WARNING"}, "Active material does not use nodes.")
            return {"CANCELLED"}

        settings.scanned_groups.clear()
        visited_trees = set()

        def get_interface_socket_names(node_tree):
            inputs = []
            outputs = []

            # Blender 4.x node group interface
            if hasattr(node_tree, "interface") and hasattr(node_tree.interface, "items_tree"):
                for item in node_tree.interface.items_tree:
                    if getattr(item, "item_type", "") != "SOCKET":
                        continue
                    if getattr(item, "in_out", "") == "INPUT":
                        inputs.append(item.name)
                    elif getattr(item, "in_out", "") == "OUTPUT":
                        outputs.append(item.name)

            # Blender 3.x fallback
            else:
                try:
                    inputs = [socket.name for socket in node_tree.inputs]
                    outputs = [socket.name for socket in node_tree.outputs]
                except Exception:
                    pass

            return inputs, outputs

        def count_internal_groups(node_tree):
            return sum(
                1 for node in node_tree.nodes
                if node.bl_idname == "ShaderNodeGroup" and node.node_tree
            )

        def scan_tree(node_tree, depth=0):
            for node in node_tree.nodes:
                if node.bl_idname != "ShaderNodeGroup" or not node.node_tree:
                    continue

                group_tree = node.node_tree
                inputs, outputs = get_interface_socket_names(group_tree)

                item = settings.scanned_groups.add()
                item.name = group_tree.name
                item.node_name = node.name
                item.depth = depth
                item.inputs = ", ".join(inputs)
                item.outputs = ", ".join(outputs)
                item.node_count = len(group_tree.nodes)
                item.internal_group_count = count_internal_groups(group_tree)

                key = id(group_tree)
                if key in visited_trees:
                    continue

                visited_trees.add(key)
                scan_tree(group_tree, depth + 1)

        scan_tree(mat.node_tree, 0)

        self.report({"INFO"}, f"Scanned {len(settings.scanned_groups)} node group entries from {mat.name}.")
        return {"FINISHED"}


# ============================================================
# Panels
# ============================================================

class NODE_PT_T8ShaderProfileBuilder(Panel):
    bl_label = "Shader Profile Builder"
    bl_idname = "NODE_PT_t8_shader_profile_builder"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Shader Profile"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = get_settings(context)

        row = layout.row(align=True)
        row.operator("t8_shader_profile.init_defaults", icon="ADD")
        row.operator("t8_shader_profile.clear_profile", icon="TRASH")

        layout.separator()

        layout.prop(settings, "profile_name")
        layout.prop(settings, "save_path")

        row = layout.row(align=True)
        row.operator("t8_shader_profile.save_profile", icon="FILE_TICK")
        row.operator("t8_shader_profile.load_profile", icon="FILE_FOLDER")

        layout.separator()

        layout.label(text="Shader Elements", icon="MATERIAL")

        layout.template_list(
            "T8SPB_UL_Elements",
            "",
            settings,
            "elements",
            settings,
            "elements_index",
            rows=8,
        )

        if not settings.elements:
            box = layout.box()
            box.label(text="No elements yet.")
            box.label(text="Click Initialize Default Elements.")
            return

        element = settings.elements[settings.elements_index]

        layout.separator()

        box = layout.box()
        box.label(text=f"Element: {element_label(element.element_type)}", icon="NODE_MATERIAL")
        box.prop(element, "enabled")
        box.prop(element, "source_type")

        if element.source_type == "TEXTURE":
            box.prop(element, "channel")
            box.prop(element, "colorspace")
            box.prop(element, "alpha_mode")
            box.prop(element, "default_value")

            box.separator()
            box.label(text="Texture Identifiers", icon="VIEWZOOM")

            box.template_list(
                "T8SPB_UL_IdentifierRules",
                "",
                element,
                "identifiers",
                element,
                "identifiers_index",
                rows=4,
            )

            row = box.row(align=True)
            row.operator("t8_shader_profile.add_identifier", icon="ADD")
            row.operator("t8_shader_profile.remove_identifier", icon="REMOVE")

            box.separator()
            box.label(text="Preview / Reference", icon="IMAGE_DATA")
            box.operator("t8_shader_profile.load_preview_image", icon="IMAGE")

            if element.preview_image:
                box.label(text=f"Loaded: {element.preview_image.name}")
                box.template_ID_preview(element, "preview_image", rows=4, cols=4)

        elif element.source_type == "VALUE":
            box.prop(element, "default_value", text="Value")

        else:
            box.label(text="This element is disabled.")

        layout.separator()
        scanner_box = layout.box()
        scanner_box.label(text="Shader Template Scanner", icon="NODETREE")
        scanner_box.operator("t8_shader_profile.scan_active_material_groups", icon="VIEWZOOM")

        if settings.scanned_groups:
            scanner_box.template_list(
                "T8SPB_UL_ScannedGroups",
                "",
                settings,
                "scanned_groups",
                settings,
                "scanned_groups_index",
                rows=6,
            )

            group = settings.scanned_groups[settings.scanned_groups_index]
            detail = scanner_box.box()
            detail.label(text=f"Group: {group.name}")
            detail.label(text=f"Node: {group.node_name}")
            detail.label(text=f"Depth: {group.depth}")
            detail.label(text=f"Nodes: {group.node_count}")
            detail.label(text=f"Nested Groups: {group.internal_group_count}")
            detail.label(text="Inputs:")
            detail.label(text=group.inputs if group.inputs else "None")
            detail.label(text="Outputs:")
            detail.label(text=group.outputs if group.outputs else "None")


# ============================================================
# Registration
# ============================================================

CLASSES = (
    T8SPB_IdentifierRule,
    T8SPB_ShaderElement,
    T8SPB_ScannedGroup,
    T8SPB_ProfileSettings,
    T8SPB_UL_Elements,
    T8SPB_UL_IdentifierRules,
    T8SPB_UL_ScannedGroups,
    T8SPB_OT_InitDefaults,
    T8SPB_OT_ClearProfile,
    T8SPB_OT_AddIdentifier,
    T8SPB_OT_RemoveIdentifier,
    T8SPB_OT_SaveProfile,
    T8SPB_OT_LoadProfile,
    T8SPB_OT_LoadPreviewImage,
    T8SPB_OT_ScanActiveMaterialGroups,
    NODE_PT_T8ShaderProfileBuilder,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.t8_shader_profile_builder = bpy.props.PointerProperty(
        type=T8SPB_ProfileSettings
    )


def unregister():
    if hasattr(bpy.types.Scene, "t8_shader_profile_builder"):
        del bpy.types.Scene.t8_shader_profile_builder

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)