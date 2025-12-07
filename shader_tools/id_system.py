import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    IntVectorProperty,
    PointerProperty,
    StringProperty,
    FloatVectorProperty,   # <-- add this import
)
from mathutils import Vector

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

# Global ID layout:
#  1-4   = Red (R1..R4)
#  5-8   = Green (G1..G4)
#  9-12  = Blue (B1..B4)
#  13-16 = Alpha (A1..A4)

ID_CHANNEL_MAP = {
    1: ("R", 1),
    2: ("R", 2),
    3: ("R", 3),
    4: ("R", 4),
    5: ("G", 1),
    6: ("G", 2),
    7: ("G", 3),
    8: ("G", 4),
    9: ("B", 1),
    10: ("B", 2),
    11: ("B", 3),
    12: ("B", 4),
    13: ("A", 1),
    14: ("A", 2),
    15: ("A", 3),
    16: ("A", 4),
}

# Gray-range presets per number of IDs in a channel
ID_RANGE_PRESETS = {
    0: [],  # no IDs in this channel

    # 1 ID in this channel → single level 1.0
    1: [
        (1.0, 1.0),
    ],

    # 2 IDs in this channel → 0.05, 1.0
    2: [
        (0.05, 0.05),
        (1.0, 1.0),
    ],

    # 3 IDs in this channel → 0.08, 0.397, 1.0
    3: [
        (0.08, 0.08),
        (0.397, 0.397),
        (1.0, 1.0),
    ],

    # 4 IDs in this channel → 0.05, 0.212, 0.521, 1.0
    4: [
        (0.05, 0.05),
        (0.212, 0.212),
        (0.521, 0.521),
        (1.0, 1.0),
    ],
}


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def get_active_material(context):
    """Best-effort to get the material relevant to the current Shader Editor."""
    mat = None

    space = context.space_data
    if (
        hasattr(space, "type")
        and space.type == 'NODE_EDITOR'
        and hasattr(space, "node_tree")
    ):
        nt = space.node_tree
        if isinstance(nt, bpy.types.ShaderNodeTree):
            mat = getattr(nt, "material", None)

    if mat is None:
        obj = context.object
        if obj and obj.active_material:
            mat = obj.active_material

    return mat


def id_image_name(material, id_index: int) -> str:
    return f"{material.name}_ID{str(id_index).zfill(2)}"


def ensure_id_image(material, id_index: int, width=4096, height=4096):
    """Create or fetch a 4K image for the given ID (default black)."""
    name = id_image_name(material, id_index)
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.new(
            name=name,
            width=width,
            height=height,
            alpha=True,
            float_buffer=False,
        )
    return img


def ensure_id_system_frame(material):
    """Create or fetch a Frame node to group ID images + ID Core."""
    nt = material.node_tree
    frame = None
    for n in nt.nodes:
        if isinstance(n, bpy.types.NodeFrame) and n.label == "ID System":
            frame = n
            break
    if frame is None:
        frame = nt.nodes.new("NodeFrame")
        frame.label = "ID System"
        frame.name = "ID_System_Frame"
        frame.use_custom_color = True
        frame.color = (0.2, 0.4, 0.8)
    return frame


def iter_material_id_flags(settings):
    """Yield (id_index, bool_flag) for the 16 IDs from settings."""
    for i in range(1, 17):
        flag = getattr(settings, f"id_use_{i}")
        yield i, flag


def compute_split_from_flags(settings):
    """Compute split numbers (R,G,B,A) from which IDs are marked as used."""
    r_count = g_count = b_count = a_count = 0

    for i, used in iter_material_id_flags(settings):
        if not used:
            continue
        ch, slot = ID_CHANNEL_MAP[i]
        if ch == "R":
            r_count += 1
        elif ch == "G":
            g_count += 1
        elif ch == "B":
            b_count += 1
        elif ch == "A":
            a_count += 1

    return (r_count, g_count, b_count, a_count)


def compute_id_ranges(settings):
    """Return dict: id_index -> (low, high) based on channel usage and presets."""
    id_ranges = {i: (0.0, 0.0) for i in range(1, 17)}

    for ch, id_indices in {
        "R": [1, 2, 3, 4],
        "G": [5, 6, 7, 8],
        "B": [9, 10, 11, 12],
        "A": [13, 14, 15, 16],
    }.items():
        used_ids = [i for i in id_indices if getattr(settings, f"id_use_{i}")]
        count = len(used_ids)
        presets = ID_RANGE_PRESETS.get(count, [])

        for idx, id_index in enumerate(used_ids):
            if idx < len(presets):
                id_ranges[id_index] = presets[idx]
            else:
                id_ranges[id_index] = (0.0, 0.0)

    return id_ranges


def set_paint_canvas_for_id(context, material, id_index):
    """Set the texture paint canvas & image editor to the given ID's image."""
    ts = context.tool_settings

    if id_index is None:
        if hasattr(ts, "image_paint") and ts.image_paint:
            ts.image_paint.canvas = None
        return

    img = ensure_id_image(material, id_index)

    if hasattr(ts, "image_paint") and ts.image_paint:
        ts.image_paint.canvas = img

    for area in context.screen.areas:
        if area.type == 'IMAGE_EDITOR':
            for space in area.spaces:
                if space.type == 'IMAGE_EDITOR':
                    space.image = img

    obj = context.object
    if obj and obj.type == 'MESH':
        try:
            if obj.mode != 'TEXTURE_PAINT':
                bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        except Exception:
            pass


def ensure_temp_preview_nodes(mat, settings):
    """Create or fetch the temporary Principled BSDF + Output for ID painting."""
    nt = mat.node_tree

    temp_bsdf = nt.nodes.get(settings.temp_bsdf_name) if settings.temp_bsdf_name else None
    temp_output = nt.nodes.get(settings.temp_output_name) if settings.temp_output_name else None

    if temp_bsdf is None:
        temp_bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        temp_bsdf.name = "IDTEMP_Principled"
        temp_bsdf.label = "ID Paint Preview"
        temp_bsdf.location = (200, 200)
        settings.temp_bsdf_name = temp_bsdf.name

    if temp_output is None:
        temp_output = nt.nodes.new("ShaderNodeOutputMaterial")
        temp_output.name = "IDTEMP_Output"
        temp_output.label = "ID Paint Output"
        temp_output.location = (500, 200)
        settings.temp_output_name = temp_output.name

    if not settings.prev_output_name:
        prev = None
        if isinstance(nt.nodes.active, bpy.types.ShaderNodeOutputMaterial):
            prev = nt.nodes.active
        else:
            for n in nt.nodes:
                if isinstance(n, bpy.types.ShaderNodeOutputMaterial) and n != temp_output:
                    prev = n
                    break
        if prev:
            settings.prev_output_name = prev.name

    for link in list(nt.links):
        if link.to_node == temp_output and link.to_socket.name == "Surface":
            nt.links.remove(link)
    nt.links.new(temp_bsdf.outputs.get("BSDF"), temp_output.inputs.get("Surface"))

    nt.nodes.active = temp_output

    return temp_bsdf, temp_output

from mathutils import Vector  # you already import this at the top of the file


def setup_paint_mix_chain(mat, settings, img_node):
    """
    Insert/refresh a MixRGB node between the active ID image and
    the ID Paint Preview BSDF's Base Color:
      - Fac  = Color output of the ID image
      - A    = whatever is feeding the main Principled's Base Color
               (or its default color if no link)
      - B    = user-selected settings.paint_mix_color
      - Mix output -> ID Paint Preview Base Color
    """
    if not mat.use_nodes or not mat.node_tree:
        return

    nt = mat.node_tree

    # Get the temp preview Principled created by ensure_temp_preview_nodes
    temp_bsdf = nt.nodes.get(settings.temp_bsdf_name) if settings.temp_bsdf_name else None
    if temp_bsdf is None or temp_bsdf.type != 'BSDF_PRINCIPLED':
        return

    # Find the "main" Principled (the one that is NOT the temp preview)
    main_bsdf = None
    for node in nt.nodes:
        if isinstance(node, bpy.types.ShaderNodeBsdfPrincipled) and node is not temp_bsdf:
            main_bsdf = node
            break

    # Create or reuse the MixRGB node
    mix = nt.nodes.get("ID_Paint_Mix")
    if mix is None or mix.type != 'MIX_RGB':
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.name = "ID_Paint_Mix"
        mix.label = "ID Paint Mix"

    # Place it a bit in front of the temp BSDF
    mix.location = temp_bsdf.location + Vector((-250.0, 0.0))
    mix.blend_type = 'MIX'
    mix.inputs["Fac"].default_value = 1.0  # will be overridden by factor link

    # --- Factor: COLOR output of the ID image (NOT Alpha) ---
    fac_input = mix.inputs[0]  # Factor
    # Clear existing links into Factor
    for link in list(nt.links):
        if link.to_node is mix and link.to_socket is fac_input:
            nt.links.remove(link)

    fac_socket = img_node.outputs.get("Color") or img_node.outputs[0]
    if fac_socket:
        nt.links.new(fac_socket, fac_input)

    # --- A: whatever is feeding the main Principled's Base Color, or its default ---
    a_input = mix.inputs[1]
    # Clear existing links into A
    for link in list(nt.links):
        if link.to_node is mix and link.to_socket is a_input:
            nt.links.remove(link)

    if main_bsdf:
        base_in = main_bsdf.inputs.get("Base Color")
        if base_in:
            if base_in.is_linked:
                # Reuse the existing upstream color (we do NOT remove it from the main BSDF)
                src = base_in.links[0].from_socket
                nt.links.new(src, a_input)
            else:
                a_input.default_value = base_in.default_value
    else:
        # Fallback if no main Principled found
        a_input.default_value = (1.0, 1.0, 1.0, 1.0)

    # --- B: user-chosen paint color ---
    b_input = mix.inputs[2]
    b_input.default_value = settings.paint_mix_color

    # --- Output of Mix -> temp preview BSDF Base Color ---
    base_in_temp = temp_bsdf.inputs.get("Base Color")
    if base_in_temp:
        # Remove any previous links into the temp Base Color
        for link in list(nt.links):
            if link.to_node is temp_bsdf and link.to_socket is base_in_temp:
                nt.links.remove(link)
        nt.links.new(mix.outputs[0], base_in_temp)



def clear_temp_preview_nodes(mat, settings):
    """Remove temporary preview nodes and restore previous output if possible."""
    if not mat.use_nodes:
        return
    nt = mat.node_tree

    if settings.temp_output_name:
        node = nt.nodes.get(settings.temp_output_name)
        if node:
            nt.nodes.remove(node)
    if settings.temp_bsdf_name:
        node = nt.nodes.get(settings.temp_bsdf_name)
        if node:
            nt.nodes.remove(node)

    if settings.prev_output_name:
        prev = nt.nodes.get(settings.prev_output_name)
        if isinstance(prev, bpy.types.ShaderNodeOutputMaterial):
            nt.nodes.active = prev

    settings.temp_output_name = ""
    settings.temp_bsdf_name = ""
    settings.prev_output_name = ""

def create_id_paint_mix_node(mat, temp_bsdf, img_node):
    """
    Insert (or reuse) an 'ID Paint Mix' node between the active ID image and the
    temp Principled BSDF's Base Color:

        Fac = ID image (Alpha if available, else Color)
        A   = whatever was driving the *main* Principled Base Color
        B   = user-editable paint color

    If called again (changing paint ID), it reuses the same Mix node and only
    rewires the factor/image.
    """
    if not mat or not mat.use_nodes or not mat.node_tree:
        return

    nt = mat.node_tree
    base_input = temp_bsdf.inputs.get("Base Color")
    if base_input is None:
        return

    # Remove any existing direct links into temp_bsdf Base Color
    for link in list(nt.links):
        if link.to_node == temp_bsdf and link.to_socket == base_input:
            nt.links.remove(link)

    # Try to find an existing "ID Paint Mix" node
    mix = nt.nodes.get("ID_Paint_Mix")

    # Helper: find the main (non-temp) Principled BSDF
    def find_main_principled():
        for n in nt.nodes:
            if isinstance(n, bpy.types.ShaderNodeBsdfPrincipled) and n != temp_bsdf:
                return n
        return None

    if mix is None:
        # --- First time: create the Mix node and hook up A/B/Result ---

        # Figure out what was feeding the main Principled's Base Color
        main_pb = find_main_principled()
        original_from_socket = None
        original_default = (0.8, 0.8, 0.8, 1.0)

        if main_pb:
            main_base = main_pb.inputs.get("Base Color")
            if main_base:
                if main_base.is_linked:
                    original_from_socket = main_base.links[0].from_socket
                original_default = getattr(main_base, "default_value", original_default)

        # Version-safe Mix Color node
        if bpy.app.version >= (4, 0, 0):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = 'RGBA'
            fac_input = mix.inputs["Factor"]
            a_input   = mix.inputs["A"]
            b_input   = mix.inputs["B"]
            result_out = mix.outputs["Result"]
        else:
            mix = nt.nodes.new("ShaderNodeMixRGB")
            fac_input = mix.inputs["Fac"]
            a_input   = mix.inputs["Color1"]
            b_input   = mix.inputs["Color2"]
            result_out = mix.outputs["Color"]

        mix.label = "ID Paint Mix"
        mix.name = "ID_Paint_Mix"
        mix.location = temp_bsdf.location + Vector((-250.0, 0.0))

        # A = original Base Color chain (or its default)
        if original_from_socket is not None:
            nt.links.new(original_from_socket, a_input)
        else:
            if hasattr(a_input, "default_value"):
                a_input.default_value = original_default

        # B = user paint color (start as red; user can change)
        if hasattr(b_input, "default_value"):
            dv = b_input.default_value
            if len(dv) == 4:
                b_input.default_value = (1.0, 0.0, 0.0, 1.0)
            elif len(dv) == 3:
                b_input.default_value = (1.0, 0.0, 0.0)

        # Result → temp BSDF Base Color
        nt.links.new(result_out, base_input)

    else:
        # Mix already exists; figure out its Fac socket
        if bpy.app.version >= (4, 0, 0):
            fac_input = mix.inputs.get("Factor")
        else:
            fac_input = mix.inputs.get("Fac")

    # --- Every time: wire the new ID image as the Factor ---

    if fac_input is not None:
        # Clear old fac links
        for link in list(nt.links):
            if link.to_node == mix and link.to_socket == fac_input:
                nt.links.remove(link)

        # Prefer Alpha as mask; fall back to Color
        fac_socket = img_node.outputs.get("Alpha")
        if fac_socket is None:
            fac_socket = img_node.outputs.get("Color") or img_node.outputs[0]

        if fac_socket:
            nt.links.new(fac_socket, fac_input)

    # Make sure Mix output is actually driving Base Color (in case of rewiring)
    # (Cheap sanity check)
    has_link = any(
        link.to_node == temp_bsdf and link.to_socket == base_input
        for link in nt.links
    )
    if not has_link:
        if bpy.app.version >= (4, 0, 0):
            result_out = mix.outputs.get("Result")
        else:
            result_out = mix.outputs.get("Color")
        if result_out:
            nt.links.new(result_out, base_input)

def ensure_id_image_node(material, id_index: int):
    """Create or fetch an Image Texture node for the ID image in this material.

    This recreates the 4×4 grid layout and names like <Mat>_ID01, _ID02…,
    and assigns the correct image datablock.
    """
    if not material.use_nodes:
        material.use_nodes = True

    nt = material.node_tree

    # Node name = image name so we can find it later
    node_name = id_image_name(material, id_index)
    node = nt.nodes.get(node_name)

    img = ensure_id_image(material, id_index)

    if node is None:
        node = nt.nodes.new("ShaderNodeTexImage")
        node.name = node_name
        node.label = f"ID {id_index:02d}"
        node.image = img

        # Recreate the grid layout from the old version
        ch, slot = ID_CHANNEL_MAP[id_index]   # e.g. ("R", 1)
        base_x = -1200
        base_y = 400
        channel_offset_y = {
            "R": 0,
            "G": -300,
            "B": -600,
            "A": -900,
        }[ch]
        slot_offset_x = (slot - 1) * 220

        node.location = (
            base_x + slot_offset_x,
            base_y + channel_offset_y,
        )
    else:
        # Ensure it uses the correct image
        if node.type == 'TEX_IMAGE':
            node.image = img

    return node, img


# -------------------------------------------------------------------------
# ID Core node group (with RGB_ID + Alpha_ID outputs)
# -------------------------------------------------------------------------


def build_id_core_group(material, settings):
    """Create or rebuild the per-material ID Core node group and its node."""
    if not material.use_nodes:
        material.use_nodes = True

    nt = material.node_tree
    group_name = f"ID_Core__{material.name}"

    group = bpy.data.node_groups.get(group_name)
    is_new = group is None
    if group is None:
        group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')

    # Clear internal nodes & links, but NOT interface if group already existed
    group.nodes.clear()
    group.links.clear()

    is_4x = bpy.app.version >= (4, 0, 0)

    # Interface: keep IDxx_Mask outputs and add RGB_ID, Alpha_ID
    if is_new:
        if is_4x:
            io = group.interface
            io.clear()

            # Outputs
            io.new_socket(name="RGB_ID", in_out='OUTPUT', socket_type='NodeSocketColor')
            io.new_socket(name="Alpha_ID", in_out='OUTPUT', socket_type='NodeSocketFloat')

            for i in range(1, 17):
                io.new_socket(
                    name=f"ID{i:02d}_Mask",
                    in_out='OUTPUT',
                    socket_type='NodeSocketFloat',
                )

            # Inputs
            for i in range(1, 17):
                io.new_socket(
                    name=f"ID{i:02d}_Mask",
                    in_out='INPUT',
                    socket_type='NodeSocketFloat',
                )
        else:
            group.inputs.clear()
            group.outputs.clear()

            group.outputs.new('NodeSocketColor', 'RGB_ID')
            group.outputs.new('NodeSocketFloat', 'Alpha_ID')

            for i in range(1, 17):
                group.outputs.new('NodeSocketFloat', f"ID{i:02d}_Mask")

            for i in range(1, 17):
                group.inputs.new('NodeSocketFloat', f"ID{i:02d}_Mask")

    n_in = group.nodes.new("NodeGroupInput")
    n_in.location = (-800, 0)
    n_out = group.nodes.new("NodeGroupOutput")
    n_out.location = (800, 0)

    ranges = compute_id_ranges(settings)

    # Pass-through original masks for IDxx_Mask outputs (for Mix helpers)
    for i in range(1, 17):
        input_name = f"ID{i:02d}_Mask"
        group.links.new(n_in.outputs[input_name], n_out.inputs[input_name])

    # Helper: build a layered mix chain for one channel using its IDs.
    # Each ID overrides the previous value where its mask > 0:
    # result = prev + mask * (gray - prev)
    def build_channel_value(id_indices):
        """
        id_indices: list of ID numbers that belong to this channel (e.g. [1,2,3,4])
        Uses only Math operations, no 'MIX' enum.
        """
        used_ids = [i for i in id_indices if getattr(settings, f"id_use_{i}")]

        # Start from 0.0 (no ID)
        base_val_node = group.nodes.new("ShaderNodeValue")
        base_val_node.location = (-600, 300 - 60 * (id_indices[0]))
        base_val_node.outputs[0].default_value = 0.0
        current_socket = base_val_node.outputs[0]

        for idx, i in enumerate(used_ids):
            low, high = ranges.get(i, (0.0, 0.0))
            gray = low  # our chosen grayscale value

            input_name = f"ID{i:02d}_Mask"
            mask_socket = n_in.outputs[input_name]

            # Keep a reference to the previous channel value
            prev_socket = current_socket

            # diff = gray - prev
            diff = group.nodes.new("ShaderNodeMath")
            diff.operation = 'SUBTRACT'
            diff.location = (-350, 300 - 80 * (id_indices[0] + idx))
            diff.inputs[0].default_value = gray       # A
            group.links.new(prev_socket, diff.inputs[1])  # B

            # mul = mask * diff
            mul = group.nodes.new("ShaderNodeMath")
            mul.operation = 'MULTIPLY'
            mul.location = (-150, 300 - 80 * (id_indices[0] + idx))
            group.links.new(mask_socket, mul.inputs[0])
            group.links.new(diff.outputs[0], mul.inputs[1])

            # result = prev + mul
            add = group.nodes.new("ShaderNodeMath")
            add.operation = 'ADD'
            add.location = (50, 300 - 80 * (id_indices[0] + idx))
            group.links.new(prev_socket, add.inputs[0])
            group.links.new(mul.outputs[0], add.inputs[1])

            current_socket = add.outputs[0]

        return current_socket


    # Build R, G, B, A values from their respective IDs
    sock_R = build_channel_value([1, 2, 3, 4])
    sock_G = build_channel_value([5, 6, 7, 8])
    sock_B = build_channel_value([9, 10, 11, 12])
    sock_A = build_channel_value([13, 14, 15, 16])

    # Combine RGB and output Alpha separately
    comb = group.nodes.new("ShaderNodeCombineRGB")
    comb.location = (400, 200)
    group.links.new(sock_R, comb.inputs['R'])
    group.links.new(sock_G, comb.inputs['G'])
    group.links.new(sock_B, comb.inputs['B'])

    group.links.new(comb.outputs['Image'], n_out.inputs["RGB_ID"])
    group.links.new(sock_A, n_out.inputs["Alpha_ID"])

    # 🔹 This was missing – creates/updates the ID_Core node in the material
    ensure_id_core_node(material, group)



def ensure_id_core_node(material, group):
    """Ensure there's a Group node using the ID Core in the material's node tree,
    and wire each ID image node into the matching IDxx_Mask input."""
    nt = material.node_tree
    frame = ensure_id_system_frame(material)

    core_node = None
    for node in nt.nodes:
        if node.type == 'GROUP' and node.node_tree == group:
            core_node = node
            break

    if core_node is None:
        core_node = nt.nodes.new("ShaderNodeGroup")
        core_node.node_tree = group
        core_node.label = "ID Core"
        core_node.name = "ID_Core"
        core_node.location = (-400, -400)

    core_node.parent = frame

    # Create/refresh the 16 ID image nodes and connect them
    for i in range(1, 17):
        input_name = f"ID{i:02d}_Mask"
        if input_name not in core_node.inputs:
            continue

        img_node, img = ensure_id_image_node(material, i)
        img_node.parent = frame

        # Clear any existing links into that input
        for link in list(nt.links):
            if link.to_node == core_node and link.to_socket == core_node.inputs[input_name]:
                nt.links.remove(link)

        color_out = img_node.outputs.get("Color") or img_node.outputs[0]
        nt.links.new(color_out, core_node.inputs[input_name])

    return core_node



def get_id_core_node(material):
    """Return the ID Core group node in this material, if any."""
    if not material.use_nodes:
        return None
    nt = material.node_tree
    group_name = f"ID_Core__{material.name}"
    for node in nt.nodes:
        if node.type == 'GROUP' and node.node_tree and node.node_tree.name == group_name:
            return node
    return None


def ensure_id_core_rgb_alpha(material):
    """
    Ensure the ID Core group exists for this material and return its node + RGB/Alpha sockets.

    Returns: (core_node, rgb_socket, alpha_socket) or (None, None, None)
    """
    if material is None:
        return None, None, None
    if not material.use_nodes:
        material.use_nodes = True

    settings = material.idsystem_settings
    build_id_core_group(material, settings)
    core_node = get_id_core_node(material)
    if core_node is None:
        return None, None, None

    rgb = core_node.outputs.get("RGB_ID")
    alpha = core_node.outputs.get("Alpha_ID")
    return core_node, rgb, alpha


# -------------------------------------------------------------------------
# Properties
# -------------------------------------------------------------------------


class IDSystemMaterialSettings(PropertyGroup):
    # Which IDs are used per material
    id_use_1: BoolProperty(name="ID 1", default=False)
    id_use_2: BoolProperty(name="ID 2", default=False)
    id_use_3: BoolProperty(name="ID 3", default=False)
    id_use_4: BoolProperty(name="ID 4", default=False)

    id_use_5: BoolProperty(name="ID 5", default=False)
    id_use_6: BoolProperty(name="ID 6", default=False)
    id_use_7: BoolProperty(name="ID 7", default=False)
    id_use_8: BoolProperty(name="ID 8", default=False)

    id_use_9: BoolProperty(name="ID 9", default=False)
    id_use_10: BoolProperty(name="ID 10", default=False)
    id_use_11: BoolProperty(name="ID 11", default=False)
    id_use_12: BoolProperty(name="ID 12", default=False)

    id_use_13: BoolProperty(name="ID 13", default=False)
    id_use_14: BoolProperty(name="ID 14", default=False)
    id_use_15: BoolProperty(name="ID 15", default=False)
    id_use_16: BoolProperty(name="ID 16", default=False)

    split_rgba: IntVectorProperty(
        name="Split",
        size=4,
        default=(0, 0, 0, 0),
        min=0,
        max=4,
        description="Split number per channel (R,G,B,A).",
    )

    active_paint_id: EnumProperty(
        name="Active Paint ID",
        description="Which ID mask image to paint on",
        items=[
            ('NONE', "None", "Do not focus on any ID mask"),
            ('ID01', "ID 1 (R1)", "Paint on ID 1 (Red slot 1)"),
            ('ID02', "ID 2 (R2)", "Paint on ID 2 (Red slot 2)"),
            ('ID03', "ID 3 (R3)", "Paint on ID 3 (Red slot 3)"),
            ('ID04', "ID 4 (R4)", "Paint on ID 4 (Red slot 4)"),
            ('ID05', "ID 5 (G1)", "Paint on ID 5 (Green slot 1)"),
            ('ID06', "ID 6 (G2)", "Paint on ID 6 (Green slot 2)"),
            ('ID07', "ID 7 (G3)", "Paint on ID 7 (Green slot 3)"),
            ('ID08', "ID 8 (G4)", "Paint on ID 8 (Green slot 4)"),
            ('ID09', "ID 9 (B1)", "Paint on ID 9 (Blue slot 1)"),
            ('ID10', "ID 10 (B2)", "Paint on ID 10 (Blue slot 2)"),
            ('ID11', "ID 11 (B3)", "Paint on ID 11 (Blue slot 3)"),
            ('ID12', "ID 12 (B4)", "Paint on ID 12 (Blue slot 4)"),
            ('ID13', "ID 13 (A1)", "Paint on ID 13 (Alpha slot 1)"),
            ('ID14', "ID 14 (A2)", "Paint on ID 14 (Alpha slot 2)"),
            ('ID15', "ID 15 (A3)", "Paint on ID 15 (Alpha slot 3)"),
            ('ID16', "ID 16 (A4)", "Paint on ID 16 (Alpha slot 4)"),
        ],
        default='NONE',
    )
    
    paint_mix_color: FloatVectorProperty(
        name="Paint Color",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 0.0, 0.0, 1.0),  # default red, tweak if you like
        description="Color used as B input for the ID Paint Mix node",
    )

    temp_bsdf_name: StringProperty(default="")
    temp_output_name: StringProperty(default="")
    prev_output_name: StringProperty(default="")


# -------------------------------------------------------------------------
# Operators – init, build split, painting
# -------------------------------------------------------------------------


class IDS_OT_InitMasks(Operator):
    bl_idname = "t8tools.init_masks"
    bl_label = "Initialize ID Masks"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat = get_active_material(context)
        if mat is None:
            self.report({'ERROR'}, "No active material found.")
            return {'CANCELLED'}

        if not mat.use_nodes:
            mat.use_nodes = True

        nt = mat.node_tree
        frame = ensure_id_system_frame(mat)

        # Create or update the 16 image textures in a grid
        for i in range(1, 17):
            node, img = ensure_id_image_node(mat, i)
            node.parent = frame

        # Also (re)build ID Core so its inputs exist
        build_id_core_group(mat, mat.idsystem_settings)

        frame.label = "ID System"
        self.report({'INFO'}, f"Initialized ID mask images/nodes for material '{mat.name}'.")
        return {'FINISHED'}



class IDS_OT_BuildSplit(Operator):
    bl_idname = "t8tools.build_split"
    bl_label = "Build / Refresh Split Number & ID Core"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat = get_active_material(context)
        if mat is None:
            self.report({'ERROR'}, "No active material found.")
            return {'CANCELLED'}

        settings = mat.idsystem_settings
        split = compute_split_from_flags(settings)
        settings.split_rgba = split

        build_id_core_group(mat, settings)

        self.report(
            {'INFO'},
            f"Split updated for '{mat.name}': R={split[0]} G={split[1]} B={split[2]} A={split[3]} (ID Core rebuilt)",
        )
        return {'FINISHED'}


class IDS_OT_SetPaintID(Operator):
    bl_idname = "t8tools.set_paint_id"
    bl_label = "Set Active Paint ID"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat = get_active_material(context)
        if mat is None:
            self.report({'ERROR'}, "No active material found.")
            return {'CANCELLED'}

        nt = mat.node_tree
        settings = mat.idsystem_settings
        enum_val = settings.active_paint_id

        # NONE: clear paint canvas & temp nodes
        if enum_val == 'NONE':
            set_paint_canvas_for_id(context, mat, None)
            clear_temp_preview_nodes(mat, settings)
            self.report({'INFO'}, "Cleared active ID paint canvas and restored original shader.")
            return {'FINISHED'}

        # Convert enum like 'ID06' -> 6
        try:
            id_index = int(enum_val.replace("ID", ""))
        except ValueError:
            self.report({'ERROR'}, f"Invalid ID enum value: {enum_val}")
            return {'CANCELLED'}

        # Ensure the image and its grid node exist
        img_node, img = ensure_id_image_node(mat, id_index)

        # Set paint canvas + image editor
        set_paint_canvas_for_id(context, mat, id_index)

        # Ensure preview nodes (temp Principled + Output)
        temp_bsdf, temp_output = ensure_temp_preview_nodes(mat, settings)

        # Build/refresh the Mix node chain:
        #   Color (ID image) -> Fac
        #   A = original Base Color
        #   B = settings.paint_mix_color
        #   Mix -> ID Paint Preview Base Color
        setup_paint_mix_chain(mat, settings, img_node)

        # Make this image node the active one in the Shader Editor
        for n in nt.nodes:
            n.select = False
        img_node.select = True
        nt.nodes.active = img_node

        self.report({'INFO'}, f"Set active paint ID to {id_index} for material '{mat.name}'.")
        return {'FINISHED'}


# -------------------------------------------------------------------------
# Multi-ID Mix helpers (Color & Normal) – same behavior as before
# -------------------------------------------------------------------------


class IDS_OT_AddIDMixColor(Operator):
    """Create an 'ID Mix (Color)' node that mixes multiple colors using ID masks."""
    bl_idname = "t8tools.add_id_mix_color"
    bl_label = "Add ID Mix (Color)"
    bl_options = {'REGISTER', 'UNDO'}

    num_slots: IntProperty(
        name="Num Slots",
        description="How many ID slots to use (1-4)",
        default=2,
        min=1,
        max=4,
    )
    id1: IntProperty(name="ID 1", default=1, min=1, max=16)
    id2: IntProperty(name="ID 2", default=2, min=1, max=16)
    id3: IntProperty(name="ID 3", default=3, min=1, max=16)
    id4: IntProperty(name="ID 4", default=4, min=1, max=16)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "num_slots")
        col = layout.column()
        col.prop(self, "id1")
        if self.num_slots >= 2:
            col.prop(self, "id2")
        if self.num_slots >= 3:
            col.prop(self, "id3")
        if self.num_slots >= 4:
            col.prop(self, "id4")

    def execute(self, context):
        mat = get_active_material(context)
        if mat is None:
            self.report({'ERROR'}, "No active material found.")
            return {'CANCELLED'}

        settings = mat.idsystem_settings
        build_id_core_group(mat, settings)
        core_node = get_id_core_node(mat)
        if core_node is None:
            self.report({'ERROR'}, "ID Core node not found or failed to build.")
            return {'CANCELLED'}

        nt = mat.node_tree

        used_ids = []
        for i in range(1, self.num_slots + 1):
            id_val = getattr(self, f"id{i}")
            used_ids.append(id_val)

        # Create a per-instance node group
        group_name = (
            "ID_Mix_Color_" +
            mat.name.replace(".", "_") + "_" +
            "_".join(f"{i:02d}" for i in used_ids)
        )
        group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
        n_in = group.nodes.new("NodeGroupInput")
        n_in.location = (-600, 0)
        n_out = group.nodes.new("NodeGroupOutput")
        n_out.location = (600, 0)

        is_4x = bpy.app.version >= (4, 0, 0)

        # Interface: Base, then Color/Mask for each used ID, then Result
        if is_4x:
            io = group.interface
            io.clear()
            io.new_socket(name="Base", in_out='INPUT', socket_type='NodeSocketColor')
            for id_val in used_ids:
                io.new_socket(
                    name=f"Color_ID{id_val:02d}",
                    in_out='INPUT',
                    socket_type='NodeSocketColor',
                )
                io.new_socket(
                    name=f"Mask_ID{id_val:02d}",
                    in_out='INPUT',
                    socket_type='NodeSocketFloat',
                )
            io.new_socket(name="Result", in_out='OUTPUT', socket_type='NodeSocketColor')
        else:
            group.inputs.clear()
            group.outputs.clear()
            group.inputs.new('NodeSocketColor', 'Base')
            for id_val in used_ids:
                group.inputs.new('NodeSocketColor', f"Color_ID{id_val:02d}")
                group.inputs.new('NodeSocketFloat', f"Mask_ID{id_val:02d}")
            group.outputs.new('NodeSocketColor', 'Result')

        # Build Mix chain: Base then each ID
        current_socket = n_in.outputs["Base"]

        for idx, id_val in enumerate(used_ids):
            col_name = f"Color_ID{id_val:02d}"
            mask_name = f"Mask_ID{id_val:02d}"

            mix = group.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = 'MIX'
            mix.location = (0, 200 - 150 * idx)

            group.links.new(current_socket, mix.inputs[1])        # base
            group.links.new(n_in.outputs[col_name], mix.inputs[2])  # id color
            group.links.new(n_in.outputs[mask_name], mix.inputs[0]) # factor

            current_socket = mix.outputs[0]

        group.links.new(current_socket, n_out.inputs["Result"])

        # Instance the group in the material
        node = nt.nodes.new("ShaderNodeGroup")
        node.node_tree = group
        node.label = "ID Mix Color (" + ", ".join(str(i) for i in used_ids) + ")"
        node.name = "ID_Mix_Color_Instance"
        node.location = (core_node.location.x + 600, core_node.location.y)

        # Connect masks from ID Core
        for id_val in used_ids:
            out_name = f"ID{id_val:02d}_Mask"
            mask_input_name = f"Mask_ID{id_val:02d}"
            if out_name in core_node.outputs and mask_input_name in node.inputs:
                nt.links.new(core_node.outputs[out_name], node.inputs[mask_input_name])

        nt.nodes.active = node
        node.select = True

        self.report({'INFO'}, f"Created ID Mix (Color) for IDs {used_ids}.")
        return {'FINISHED'}


class IDS_OT_AddIDMixNormal(Operator):
    """Create an 'ID Mix (Normal)' node mixing normal maps with OpenGL/DirectX toggle."""
    bl_idname = "t8tools.add_id_mix_normal"
    bl_label = "Add ID Mix (Normal)"
    bl_options = {'REGISTER', 'UNDO'}

    num_slots: IntProperty(
        name="Num Slots",
        description="How many ID slots to use (1-4)",
        default=2,
        min=1,
        max=4,
    )
    id1: IntProperty(name="ID 1", default=1, min=1, max=16)
    id2: IntProperty(name="ID 2", default=2, min=1, max=16)
    id3: IntProperty(name="ID 3", default=3, min=1, max=16)
    id4: IntProperty(name="ID 4", default=4, min=1, max=16)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "num_slots")
        col = layout.column()
        col.prop(self, "id1")
        if self.num_slots >= 2:
            col.prop(self, "id2")
        if self.num_slots >= 3:
            col.prop(self, "id3")
        if self.num_slots >= 4:
            col.prop(self, "id4")

    def execute(self, context):
        mat = get_active_material(context)
        if mat is None:
            self.report({'ERROR'}, "No active material found.")
            return {'CANCELLED'}

        settings = mat.idsystem_settings
        build_id_core_group(mat, settings)
        core_node = get_id_core_node(mat)
        if core_node is None:
            self.report({'ERROR'}, "ID Core node not found or failed to build.")
            return {'CANCELLED'}

        nt = mat.node_tree

        used_ids = []
        for i in range(1, self.num_slots + 1):
            id_val = getattr(self, f"id{i}")
            used_ids.append(id_val)

        # Create a per-instance node group
        group_name = (
            "ID_Mix_Normal_" +
            mat.name.replace(".", "_") + "_" +
            "_".join(f"{i:02d}" for i in used_ids)
        )
        group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
        n_in = group.nodes.new("NodeGroupInput")
        n_in.location = (-1000, 0)
        n_out = group.nodes.new("NodeGroupOutput")
        n_out.location = (800, 0)

        is_4x = bpy.app.version >= (4, 0, 0)

        # Interface: BaseColor/BaseSpace, then per-ID Color/Space/Mask, then Result (vector)
        if is_4x:
            io = group.interface
            io.clear()
            io.new_socket(name="BaseColor", in_out='INPUT', socket_type='NodeSocketColor')
            io.new_socket(name="BaseSpace", in_out='INPUT', socket_type='NodeSocketFloat')
            for id_val in used_ids:
                io.new_socket(
                    name=f"Color_ID{id_val:02d}",
                    in_out='INPUT',
                    socket_type='NodeSocketColor',
                )
                io.new_socket(
                    name=f"Space_ID{id_val:02d}",
                    in_out='INPUT',
                    socket_type='NodeSocketFloat',
                )
                io.new_socket(
                    name=f"Mask_ID{id_val:02d}",
                    in_out='INPUT',
                    socket_type='NodeSocketFloat',
                )
            io.new_socket(name="Result", in_out='OUTPUT', socket_type='NodeSocketVector')
        else:
            group.inputs.clear()
            group.outputs.clear()
            group.inputs.new('NodeSocketColor', 'BaseColor')
            group.inputs.new('NodeSocketFloat', 'BaseSpace')
            for id_val in used_ids:
                group.inputs.new('NodeSocketColor', f"Color_ID{id_val:02d}")
                group.inputs.new('NodeSocketFloat', f"Space_ID{id_val:02d}")
                group.inputs.new('NodeSocketFloat', f"Mask_ID{id_val:02d}")
            group.outputs.new('NodeSocketVector', 'Result')

        # Helper that builds OpenGL/DirectX switch for a given color+space input
        def build_normal_from_color(color_name, space_name, y_offset):
            col_socket = n_in.outputs[color_name]
            space_socket = n_in.outputs[space_name]

            # OpenGL normal
            nmap_gl = group.nodes.new("ShaderNodeNormalMap")
            nmap_gl.location = (-600, y_offset)
            nmap_gl.label = f"{color_name}_GL"
            group.links.new(col_socket, nmap_gl.inputs["Color"])

            # DirectX color (flip green)
            sep = group.nodes.new("ShaderNodeSeparateRGB")
            sep.location = (-1000, y_offset - 200)
            group.links.new(col_socket, sep.inputs[0])

            inv_g = group.nodes.new("ShaderNodeMath")
            inv_g.operation = 'SUBTRACT'
            inv_g.inputs[0].default_value = 1.0
            inv_g.location = (-800, y_offset - 200)
            group.links.new(sep.outputs['G'], inv_g.inputs[1])

            comb = group.nodes.new("ShaderNodeCombineRGB")
            comb.location = (-600, y_offset - 200)
            group.links.new(sep.outputs['R'], comb.inputs['R'])
            group.links.new(inv_g.outputs[0], comb.inputs['G'])
            group.links.new(sep.outputs['B'], comb.inputs['B'])

            nmap_dx = group.nodes.new("ShaderNodeNormalMap")
            nmap_dx.location = (-400, y_offset - 200)
            nmap_dx.label = f"{color_name}_DX"
            group.links.new(comb.outputs[0], nmap_dx.inputs["Color"])

            # Mix between GL and DX normals using Space (0 = GL, 1 = DX)
            mix_vec = group.nodes.new("ShaderNodeMixRGB")
            mix_vec.location = (-200, y_offset - 100)
            mix_vec.label = f"{color_name}_SpaceMix"
            group.links.new(space_socket, mix_vec.inputs[0])
            group.links.new(nmap_gl.outputs['Normal'], mix_vec.inputs[1])
            group.links.new(nmap_dx.outputs['Normal'], mix_vec.inputs[2])

            return mix_vec.outputs[0]

        # Base normal
        base_vec = build_normal_from_color("BaseColor", "BaseSpace", 400)

        # Per-ID normals
        id_normal_outputs = {}
        for idx, id_val in enumerate(used_ids):
            y = 200 - 250 * idx
            col_name = f"Color_ID{id_val:02d}"
            space_name = f"Space_ID{id_val:02d}"
            id_normal_outputs[id_val] = build_normal_from_color(col_name, space_name, y)

        # Mix chain over masks: start from base_vec
        current_socket = base_vec
        for idx, id_val in enumerate(used_ids):
            mask_name = f"Mask_ID{id_val:02d}"
            mix = group.nodes.new("ShaderNodeMixRGB")
            mix.location = (200, 200 - 150 * idx)
            group.links.new(current_socket, mix.inputs[1])
            group.links.new(id_normal_outputs[id_val], mix.inputs[2])
            group.links.new(n_in.outputs[mask_name], mix.inputs[0])
            current_socket = mix.outputs[0]

        group.links.new(current_socket, n_out.inputs["Result"])

        # Instance the group in the material
        node = nt.nodes.new("ShaderNodeGroup")
        node.node_tree = group
        node.label = "ID Mix Normal (" + ", ".join(str(i) for i in used_ids) + ")"
        node.name = "ID_Mix_Normal_Instance"
        node.location = (core_node.location.x + 600, core_node.location.y - 300)

        # Connect masks from ID Core
        for id_val in used_ids:
            out_name = f"ID{id_val:02d}_Mask"
            mask_input_name = f"Mask_ID{id_val:02d}"
            if out_name in core_node.outputs and mask_input_name in node.inputs:
                nt.links.new(core_node.outputs[out_name], node.inputs[mask_input_name])

        nt.nodes.active = node
        node.select = True

        self.report({'INFO'}, f"Created ID Mix (Normal) for IDs {used_ids}.")
        return {'FINISHED'}


# -------------------------------------------------------------------------
# UI Panel
# -------------------------------------------------------------------------


class NODE_PT_IDSystem(Panel):
    bl_label = "ID System"
    bl_idname = "NODE_PT_idsystem"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "ID System"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        if not space or space.type != 'NODE_EDITOR':
            return False
        if space.tree_type != 'ShaderNodeTree':
            return False

        mat = get_active_material(context)
        return mat is not None

    def draw(self, context):
        layout = self.layout
        mat = get_active_material(context)
        if mat is None:
            layout.label(text="No active material.", icon='ERROR')
            return

        settings = mat.idsystem_settings

        layout.label(text=f"Material: {mat.name}", icon='MATERIAL')

        # Init
        box = layout.box()
        box.label(text="Initialization", icon='FILE_NEW')
        box.operator("t8tools.init_masks", icon='IMAGE_DATA')

        # Usage / Split
        box = layout.box()
        box.label(text="ID Usage (per Channel)", icon='OUTLINER_OB_GROUP_INSTANCE')

        col = box.column(align=True)
        col.label(text="Red Channel (IDs 1-4)")
        row = col.row(align=True)
        row.prop(settings, "id_use_1", text="ID 1")
        row.prop(settings, "id_use_2", text="ID 2")
        row = col.row(align=True)
        row.prop(settings, "id_use_3", text="ID 3")
        row.prop(settings, "id_use_4", text="ID 4")

        col.separator()
        col.label(text="Green Channel (IDs 5-8)")
        row = col.row(align=True)
        row.prop(settings, "id_use_5", text="ID 5")
        row.prop(settings, "id_use_6", text="ID 6")
        row = col.row(align=True)
        row.prop(settings, "id_use_7", text="ID 7")
        row.prop(settings, "id_use_8", text="ID 8")

        col.separator()
        col.label(text="Blue Channel (IDs 9-12)")
        row = col.row(align=True)
        row.prop(settings, "id_use_9", text="ID 9")
        row.prop(settings, "id_use_10", text="ID 10")
        row = col.row(align=True)
        row.prop(settings, "id_use_11", text="ID 11")
        row.prop(settings, "id_use_12", text="ID 12")

        col.separator()
        col.label(text="Alpha Channel (IDs 13-16)")
        row = col.row(align=True)
        row.prop(settings, "id_use_13", text="ID 13")
        row.prop(settings, "id_use_14", text="ID 14")
        row = col.row(align=True)
        row.prop(settings, "id_use_15", text="ID 15")
        row.prop(settings, "id_use_16", text="ID 16")

        box.operator("t8tools.build_split", icon='SORTBYEXT')
        split = settings.split_rgba
        box.label(text=f"Split Number (R,G,B,A): {split[0]} {split[1]} {split[2]} {split[3]}")

        # Painting
        box = layout.box()
        box.label(text="Mask Painting", icon='BRUSH_DATA')
        box.prop(settings, "active_paint_id", text="Paint ID")
        box.prop(settings, "paint_mix_color", text="Paint Color")   # <-- add this
        box.operator("t8tools.set_paint_id", icon='TPAINT_HLT')

        # Mix helpers
        box = layout.box()
        box.label(text="ID Mix Helpers", icon='NODETREE')
        box.operator("t8tools.add_id_mix_color", icon='SHADING_RENDERED')
        box.operator("t8tools.add_id_mix_normal", icon='SHADING_SOLID')


# -------------------------------------------------------------------------
# Registration
# -------------------------------------------------------------------------


classes = (
    IDSystemMaterialSettings,
    IDS_OT_InitMasks,
    IDS_OT_BuildSplit,
    IDS_OT_SetPaintID,
    IDS_OT_AddIDMixColor,
    IDS_OT_AddIDMixNormal,
    NODE_PT_IDSystem,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Material.idsystem_settings = PointerProperty(type=IDSystemMaterialSettings)


def unregister():
    del bpy.types.Material.idsystem_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
