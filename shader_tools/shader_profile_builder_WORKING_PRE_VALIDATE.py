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

    template_save_path: StringProperty(
        name="Template JSON Path",
        description="Path to save/load scanned shader template JSON",
        subtype="FILE_PATH",
        default="",
    )

    loaded_template_name: StringProperty(
        name="Loaded Template",
        description="Name of the currently loaded shader template",
        default="",
    )

    loaded_template_source_material: StringProperty(
        name="Source Material",
        description="Material name recorded when the template was scanned/exported",
        default="",
    )

    rebuild_prefix: StringProperty(
        name="Rebuild Prefix",
        description="Prefix used when generating node groups from a template JSON",
        default="REBUILT_",
    )


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


def make_safe_filename(name, fallback="Shader_Template"):
    safe_name = (name or "").strip() or fallback
    for ch in '<>:"/\|?*':
        safe_name = safe_name.replace(ch, "_")
    return safe_name.replace(" ", "_")


def scanned_template_to_dict(settings, context):
    obj = context.object
    mat = obj.active_material if obj else None

    return {
        "template_name": settings.profile_name,
        "version": 2,
        "source": {
            "object_name": obj.name if obj else "",
            "active_material_name": mat.name if mat else "",
        },
        "groups": [
            {
                "group_name": group.name,
                "node_name": group.node_name,
                "depth": int(group.depth),
                "node_count": int(group.node_count),
                "nested_group_count": int(group.internal_group_count),
                "inputs": [x.strip() for x in group.inputs.split(",") if x.strip()],
                "outputs": [x.strip() for x in group.outputs.split(",") if x.strip()],
            }
            for group in settings.scanned_groups
        ],
        "group_definitions": collect_group_definitions_from_material(mat),
    }


def load_template_from_dict(settings, data):
    """Load a saved shader template JSON into the scanner display list."""
    settings.scanned_groups.clear()
    settings.scanned_groups_index = 0

    settings.loaded_template_name = data.get("template_name", "Loaded Shader Template")
    source = data.get("source", {}) or {}
    settings.loaded_template_source_material = source.get("active_material_name", "")

    # Keep profile name in sync only if the current one is blank/default-ish.
    if settings.profile_name in {"", "New Shader Profile", "Loaded Shader Profile"}:
        settings.profile_name = settings.loaded_template_name

    for g_data in data.get("groups", []):
        group = settings.scanned_groups.add()
        group.name = g_data.get("group_name", "")
        group.node_name = g_data.get("node_name", "")
        group.depth = int(g_data.get("depth", 0))
        group.node_count = int(g_data.get("node_count", 0))
        group.internal_group_count = int(g_data.get("nested_group_count", 0))

        inputs = g_data.get("inputs", []) or []
        outputs = g_data.get("outputs", []) or []
        group.inputs = ", ".join(str(x) for x in inputs)
        group.outputs = ", ".join(str(x) for x in outputs)


# ============================================================
# Deep Template Serialization Helpers - Path B / Phase 2B
# ============================================================

def json_safe_value(value):
    """Convert Blender/mathutils values into JSON-safe values."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    # mathutils vectors/colors and array-like socket values
    try:
        return [json_safe_value(v) for v in value]
    except TypeError:
        pass

    return str(value)


def socket_to_dict(socket):
    data = {
        "name": getattr(socket, "name", ""),
        "identifier": getattr(socket, "identifier", ""),
        "bl_socket_idname": getattr(socket, "bl_socket_idname", ""),
        "type": getattr(socket, "type", ""),
        "enabled": bool(getattr(socket, "enabled", True)),
        "hide": bool(getattr(socket, "hide", False)),
        "is_linked": bool(getattr(socket, "is_linked", False)),
    }

    if hasattr(socket, "default_value"):
        try:
            data["default_value"] = json_safe_value(socket.default_value)
        except Exception:
            data["default_value"] = None

    return data


def get_simple_node_properties(node):
    """Capture common rebuild-relevant node settings without trying to serialize every Blender intern."""
    props = {}

    candidate_attrs = [
        "operation",
        "data_type",
        "blend_type",
        "factor_mode",
        "clamp_factor",
        "clamp_result",
        "use_clamp",
        "use_clamp_result",
        "space",
        "uv_map",
        "projection",
        "projection_blend",
        "interpolation",
        "extension",
        "image",
        "attribute_name",
        "attribute_type",
        "direction_type",
        "gradient_type",
        "noise_dimensions",
        "voronoi_dimensions",
        "feature",
        "distance",
        "normalize",
        "invert",
    ]

    for attr in candidate_attrs:
        if not hasattr(node, attr):
            continue
        try:
            value = getattr(node, attr)
            if attr == "image" and value is not None:
                props[attr] = getattr(value, "name", str(value))
            else:
                props[attr] = json_safe_value(value)
        except Exception:
            pass

    # ColorRamp nodes need their ramp stops to be useful later.
    if hasattr(node, "color_ramp") and node.color_ramp:
        try:
            ramp = node.color_ramp
            props["color_ramp"] = {
                "interpolation": ramp.interpolation,
                "color_mode": getattr(ramp, "color_mode", ""),
                "hue_interpolation": getattr(ramp, "hue_interpolation", ""),
                "elements": [
                    {
                        "position": float(el.position),
                        "color": json_safe_value(el.color),
                    }
                    for el in ramp.elements
                ],
            }
        except Exception:
            props["color_ramp"] = "UNSUPPORTED_COLOR_RAMP_EXPORT"

    return props


def node_to_dict(node):
    data = {
        "name": node.name,
        "label": node.label,
        "bl_idname": node.bl_idname,
        "type": node.type,
        "location": [float(node.location.x), float(node.location.y)],
        "width": float(getattr(node, "width", 0.0)),
        "height": float(getattr(node, "height", 0.0)),
        "hide": bool(getattr(node, "hide", False)),
        "mute": bool(getattr(node, "mute", False)),
        "select": bool(getattr(node, "select", False)),
        "parent": node.parent.name if node.parent else None,
        "inputs": [socket_to_dict(s) for s in node.inputs],
        "outputs": [socket_to_dict(s) for s in node.outputs],
        "properties": get_simple_node_properties(node),
    }

    if node.bl_idname == "ShaderNodeGroup" and getattr(node, "node_tree", None):
        data["node_group"] = node.node_tree.name

    return data


def link_to_dict(link):
    return {
        "from_node": link.from_node.name,
        "from_socket": link.from_socket.name,
        "from_socket_identifier": getattr(link.from_socket, "identifier", ""),
        "from_socket_index": list(link.from_node.outputs).index(link.from_socket),
        "to_node": link.to_node.name,
        "to_socket": link.to_socket.name,
        "to_socket_identifier": getattr(link.to_socket, "identifier", ""),
        "to_socket_index": list(link.to_node.inputs).index(link.to_socket),
    }


def interface_to_dict(node_tree):
    inputs = []
    outputs = []

    if hasattr(node_tree, "interface") and hasattr(node_tree.interface, "items_tree"):
        for item in node_tree.interface.items_tree:
            if getattr(item, "item_type", "") != "SOCKET":
                continue
            entry = {
                "name": getattr(item, "name", ""),
                "identifier": getattr(item, "identifier", ""),
                "socket_type": getattr(item, "socket_type", ""),
                "description": getattr(item, "description", ""),
            }
            if getattr(item, "in_out", "") == "INPUT":
                inputs.append(entry)
            elif getattr(item, "in_out", "") == "OUTPUT":
                outputs.append(entry)
    else:
        # Blender 3.x fallback
        try:
            inputs = [socket_to_dict(s) for s in node_tree.inputs]
            outputs = [socket_to_dict(s) for s in node_tree.outputs]
        except Exception:
            pass

    return {"inputs": inputs, "outputs": outputs}


def node_tree_to_dict(node_tree):
    return {
        "name": node_tree.name,
        "bl_idname": node_tree.bl_idname,
        "interface": interface_to_dict(node_tree),
        "nodes": [node_to_dict(node) for node in node_tree.nodes],
        "links": [link_to_dict(link) for link in node_tree.links],
    }


def collect_group_definitions_from_material(mat):
    """Collect full node/link data for all node groups used by a material, including nested groups."""
    definitions = {}
    visited = set()

    def visit_tree(node_tree):
        for node in node_tree.nodes:
            if node.bl_idname != "ShaderNodeGroup" or not getattr(node, "node_tree", None):
                continue

            group_tree = node.node_tree
            key = id(group_tree)
            if key in visited:
                continue

            visited.add(key)
            definitions[group_tree.name] = node_tree_to_dict(group_tree)
            visit_tree(group_tree)

    if mat and mat.use_nodes and mat.node_tree:
        visit_tree(mat.node_tree)

    return definitions


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
        


class T8SPB_OT_SaveTemplateJSON(Operator):
    bl_idname = "t8_shader_profile.save_template_json"
    bl_label = "Save Template JSON"
    bl_description = "Save scanned shader template JSON, including node/link data when an active material is available"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        settings = get_settings(context)

        base_name = make_safe_filename(settings.profile_name, "Shader_Template")
        if not base_name.lower().endswith("_template"):
            base_name = f"{base_name}_Template"

        if settings.template_save_path:
            folder = os.path.dirname(bpy.path.abspath(settings.template_save_path))
            self.filepath = os.path.join(folder, f"{base_name}.json")
        elif settings.save_path:
            folder = os.path.dirname(bpy.path.abspath(settings.save_path))
            self.filepath = os.path.join(folder, f"{base_name}.json")
        else:
            self.filepath = f"{base_name}.json"

        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = get_settings(context)

        if not settings.scanned_groups:
            self.report({"WARNING"}, "No scanned shader groups to save. Run Scan Active Material Groups first.")
            return {"CANCELLED"}

        if not self.filepath.lower().endswith(".json"):
            self.filepath += ".json"

        data = scanned_template_to_dict(settings, context)

        try:
            folder = os.path.dirname(self.filepath)
            if folder and not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)

            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

            settings.template_save_path = self.filepath
            self.report({"INFO"}, f"Saved shader template with deep node data: {self.filepath}")
            return {"FINISHED"}

        except Exception as ex:
            self.report({"ERROR"}, f"Failed to save shader template: {ex}")
            return {"CANCELLED"}



class T8SPB_OT_LoadTemplateJSON(Operator):
    bl_idname = "t8_shader_profile.load_template_json"
    bl_label = "Load Template JSON"
    bl_description = "Load a saved shader template JSON into the scanner display"

    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        settings = get_settings(context)

        if settings.template_save_path:
            self.filepath = bpy.path.abspath(settings.template_save_path)

        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        settings = get_settings(context)

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "groups" not in data:
                self.report({"ERROR"}, "This JSON does not look like a shader template export.")
                return {"CANCELLED"}

            load_template_from_dict(settings, data)
            settings.template_save_path = self.filepath

            self.report({"INFO"}, f"Loaded shader template: {settings.loaded_template_name}")
            return {"FINISHED"}

        except Exception as ex:
            self.report({"ERROR"}, f"Failed to load shader template: {ex}")
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
# Experimental Template Rebuilder - Path B / Phase 2C
# ============================================================

def _make_unique_name(base_name):
    """Return a Blender data-block name that is not currently used by node groups."""
    if base_name not in bpy.data.node_groups:
        return base_name

    i = 1
    while f"{base_name}.{i:03d}" in bpy.data.node_groups:
        i += 1
    return f"{base_name}.{i:03d}"


def _socket_type_from_template(socket_type, fallback="NodeSocketFloat"):
    if not socket_type:
        return fallback
    return socket_type


def _clear_node_tree(node_tree):
    for node in list(node_tree.nodes):
        node_tree.nodes.remove(node)


def _new_interface_socket(node_tree, socket_def, in_out):
    name = socket_def.get("name", "Socket") or "Socket"
    socket_type = _socket_type_from_template(socket_def.get("socket_type"), "NodeSocketFloat")

    # Blender 4.x interface API
    if hasattr(node_tree, "interface") and hasattr(node_tree.interface, "new_socket"):
        try:
            return node_tree.interface.new_socket(
                name=name,
                in_out=in_out,
                socket_type=socket_type,
            )
        except Exception:
            # Fallback to float if the original socket type is not accepted.
            return node_tree.interface.new_socket(
                name=name,
                in_out=in_out,
                socket_type="NodeSocketFloat",
            )

    # Blender 3.x fallback
    try:
        if in_out == "INPUT":
            return node_tree.inputs.new(socket_type, name)
        return node_tree.outputs.new(socket_type, name)
    except Exception:
        if in_out == "INPUT":
            return node_tree.inputs.new("NodeSocketFloat", name)
        return node_tree.outputs.new("NodeSocketFloat", name)


def _set_default_value(socket, value):
    if value is None or not hasattr(socket, "default_value"):
        return
    try:
        socket.default_value = value
    except Exception:
        try:
            # Some socket defaults are vector-like and dislike tuples/lists of the wrong size.
            for i, v in enumerate(value):
                if i < len(socket.default_value):
                    socket.default_value[i] = v
        except Exception:
            pass


def _set_node_properties(node, props):
    if not props:
        return

    for attr, value in props.items():
        if attr == "image":
            if value and value in bpy.data.images and hasattr(node, "image"):
                try:
                    node.image = bpy.data.images[value]
                except Exception:
                    pass
            continue

        if attr == "color_ramp":
            ramp_data = value
            if hasattr(node, "color_ramp") and isinstance(ramp_data, dict):
                try:
                    ramp = node.color_ramp
                    if "interpolation" in ramp_data:
                        ramp.interpolation = ramp_data["interpolation"]
                    if "color_mode" in ramp_data and hasattr(ramp, "color_mode"):
                        ramp.color_mode = ramp_data["color_mode"]
                    if "hue_interpolation" in ramp_data and hasattr(ramp, "hue_interpolation"):
                        ramp.hue_interpolation = ramp_data["hue_interpolation"]

                    elements = ramp_data.get("elements", [])
                    # Ensure matching number of ramp elements.
                    while len(ramp.elements) < len(elements):
                        ramp.elements.new(0.5)
                    while len(ramp.elements) > len(elements) and len(ramp.elements) > 2:
                        ramp.elements.remove(ramp.elements[-1])

                    for idx, el_data in enumerate(elements):
                        if idx >= len(ramp.elements):
                            continue
                        ramp.elements[idx].position = float(el_data.get("position", ramp.elements[idx].position))
                        color = el_data.get("color")
                        if color:
                            ramp.elements[idx].color = color
                except Exception:
                    pass
            continue

        if hasattr(node, attr):
            try:
                setattr(node, attr, value)
            except Exception:
                pass


def _apply_node_basics(node, node_def):
    node.name = node_def.get("name", node.name)
    node.label = node_def.get("label", "")
    loc = node_def.get("location") or [0.0, 0.0]
    try:
        node.location = (float(loc[0]), float(loc[1]))
    except Exception:
        pass
    for attr in ("width", "height", "hide", "mute"):
        if attr in node_def and hasattr(node, attr):
            try:
                setattr(node, attr, node_def[attr])
            except Exception:
                pass


def _apply_socket_defaults(node, node_def):
    for idx, s_def in enumerate(node_def.get("inputs", [])):
        if idx >= len(node.inputs):
            continue
        _set_default_value(node.inputs[idx], s_def.get("default_value"))


def _find_socket_by_identifier_or_index(sockets, identifier, index, name=""):
    if identifier:
        for socket in sockets:
            if getattr(socket, "identifier", "") == identifier:
                return socket
    if index is not None and 0 <= index < len(sockets):
        return sockets[index]
    if name:
        for socket in sockets:
            if socket.name == name:
                return socket
    return None


def rebuild_node_groups_from_template_data(template_data, prefix="REBUILT_"):
    """Create node groups from exported template JSON. Returns (created, warnings)."""
    group_defs = template_data.get("group_definitions", {}) or {}
    if not group_defs:
        return [], ["Template JSON has no group_definitions section."]

    warnings = []
    created = []
    name_map = {}
    tree_map = {}

    # Pass 1: create empty node groups and interfaces.
    for original_name, g_def in group_defs.items():
        target_name = _make_unique_name(f"{prefix}{original_name}" if prefix else original_name)
        node_tree = bpy.data.node_groups.new(target_name, "ShaderNodeTree")
        name_map[original_name] = target_name
        tree_map[original_name] = node_tree
        created.append(target_name)

        interface = g_def.get("interface", {}) or {}
        for socket_def in interface.get("inputs", []):
            _new_interface_socket(node_tree, socket_def, "INPUT")
        for socket_def in interface.get("outputs", []):
            _new_interface_socket(node_tree, socket_def, "OUTPUT")

    # Pass 2: create nodes.
    all_node_maps = {}
    for original_name, g_def in group_defs.items():
        node_tree = tree_map[original_name]
        _clear_node_tree(node_tree)
        node_map = {}
        all_node_maps[original_name] = node_map

        for node_def in g_def.get("nodes", []):
            bl_idname = node_def.get("bl_idname", "")
            if not bl_idname:
                continue
            try:
                node = node_tree.nodes.new(bl_idname)
            except Exception as ex:
                warnings.append(f"Skipped node {node_def.get('name', '<unnamed>')} in {original_name}: {bl_idname} could not be created ({ex}).")
                continue

            _apply_node_basics(node, node_def)
            _set_node_properties(node, node_def.get("properties", {}))

            # Assign nested node group datablock after the node exists.
            if bl_idname == "ShaderNodeGroup":
                ref_name = node_def.get("node_group", "")
                rebuilt_ref = name_map.get(ref_name)
                if rebuilt_ref and rebuilt_ref in bpy.data.node_groups:
                    try:
                        node.node_tree = bpy.data.node_groups[rebuilt_ref]
                    except Exception as ex:
                        warnings.append(f"Could not assign nested group {ref_name} to node {node.name}: {ex}")
                elif ref_name:
                    warnings.append(f"Nested group reference not found for node {node.name}: {ref_name}")

            # Defaults should be applied after group assignment because sockets may update.
            _apply_socket_defaults(node, node_def)
            node_map[node_def.get("name", node.name)] = node

    # Pass 2.5: Restore frame parent relationships and framed-node positions
    for original_name, g_def in group_defs.items():

        node_map = all_node_maps.get(original_name, {})

        for node_def in g_def.get("nodes", []):

            parent_name = node_def.get("parent")
            if not parent_name:
                continue

            node = node_map.get(node_def.get("name"))
            parent = node_map.get(parent_name)

            if not node or not parent:
                continue

            try:
                node.parent = parent

                # IMPORTANT:
                # Re-apply location AFTER parenting.
                # Blender changes coordinate behavior once a node belongs to a frame.
                loc = node_def.get("location") or [0.0, 0.0]
                node.location = (float(loc[0]), float(loc[1]))

            except Exception as ex:
                warnings.append(
                    f"Failed to parent {node.name} to frame {parent_name}: {ex}"
                )

    # Pass 3: create links.
    for original_name, g_def in group_defs.items():
        node_tree = tree_map[original_name]
        node_map = all_node_maps.get(original_name, {})

        for link_def in g_def.get("links", []):
            from_node = node_map.get(link_def.get("from_node"))
            to_node = node_map.get(link_def.get("to_node"))
            if not from_node or not to_node:
                warnings.append(f"Skipped link in {original_name}: missing node {link_def.get('from_node')} -> {link_def.get('to_node')}.")
                continue

            from_socket = _find_socket_by_identifier_or_index(
                from_node.outputs,
                link_def.get("from_socket_identifier", ""),
                link_def.get("from_socket_index", None),
                link_def.get("from_socket", ""),
            )
            to_socket = _find_socket_by_identifier_or_index(
                to_node.inputs,
                link_def.get("to_socket_identifier", ""),
                link_def.get("to_socket_index", None),
                link_def.get("to_socket", ""),
            )
            if not from_socket or not to_socket:
                warnings.append(f"Skipped link in {original_name}: missing socket {link_def.get('from_node')}.{link_def.get('from_socket')} -> {link_def.get('to_node')}.{link_def.get('to_socket')}.")
                continue

            try:
                node_tree.links.new(from_socket, to_socket)
            except Exception as ex:
                warnings.append(f"Skipped link in {original_name}: {ex}")

    return created, warnings


class T8SPB_OT_RebuildTemplateGroups(Operator):
    bl_idname = "t8_shader_profile.rebuild_template_groups"
    bl_label = "Rebuild Template Groups"
    bl_description = "Experimental: rebuild node groups from the loaded template JSON"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = get_settings(context)

        if not settings.template_save_path:
            self.report({"WARNING"}, "No template JSON path set. Load or save a template first.")
            return {"CANCELLED"}

        try:
            with open(bpy.path.abspath(settings.template_save_path), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            self.report({"ERROR"}, f"Failed to read template JSON: {ex}")
            return {"CANCELLED"}

        created, warnings = rebuild_node_groups_from_template_data(
            data,
            prefix=settings.rebuild_prefix,
        )

        if warnings:
            print("\n[T8 Shader Profile Builder] Rebuild warnings:")
            for warning in warnings:
                print(" -", warning)

        if not created:
            self.report({"WARNING"}, "No node groups were rebuilt. Check console for details.")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Rebuilt {len(created)} node groups. Warnings: {len(warnings)}")
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
        scanner_box.label(text="Path B: save includes node/link data when scanned from active material.")
        scanner_box.prop(settings, "template_save_path")

        row = scanner_box.row(align=True)
        row.operator("t8_shader_profile.scan_active_material_groups", icon="VIEWZOOM")
        row.operator("t8_shader_profile.save_template_json", icon="FILE_TICK")
        row.operator("t8_shader_profile.load_template_json", icon="FILE_FOLDER")

        rebuild_row = scanner_box.row(align=True)
        rebuild_row.prop(settings, "rebuild_prefix", text="Prefix")
        rebuild_row.operator("t8_shader_profile.rebuild_template_groups", icon="NODETREE")

        if settings.loaded_template_name:
            info = scanner_box.box()
            info.label(text=f"Loaded Template: {settings.loaded_template_name}")
            if settings.loaded_template_source_material:
                info.label(text=f"Source Material: {settings.loaded_template_source_material}")

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
    T8SPB_OT_SaveTemplateJSON,
    T8SPB_OT_LoadTemplateJSON,
    T8SPB_OT_ScanActiveMaterialGroups,
    T8SPB_OT_RebuildTemplateGroups,
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