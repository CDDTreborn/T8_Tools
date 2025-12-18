import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _ensure_object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _is_mesh(obj):
    return obj and obj.type == 'MESH'


def _transfer_vgroups_via_modifier(src, dst, settings):
    """
    Robust weight transfer across Blender versions:
    add Data Transfer modifier to dst, set src, transfer VGROUP_WEIGHTS, apply modifier.
    """
    _ensure_object_mode()

    # Create (or reuse) modifier
    mod = dst.modifiers.get("T8_WT_DataTransfer")
    if mod is None:
        mod = dst.modifiers.new(name="T8_WT_DataTransfer", type='DATA_TRANSFER')

    # Source object
    mod.object = src

    # What to transfer
    if hasattr(mod, "data_types_verts"):
        mod.data_types_verts = {'VGROUP_WEIGHTS'}
    else:
        # Older fallback (rare)
        mod.use_vert_data = True

    # Mapping / influence
    if hasattr(mod, "vert_mapping"):
        mod.vert_mapping = settings.vertex_mapping

    if hasattr(mod, "ray_radius"):
        mod.ray_radius = settings.ray_radius

    if hasattr(mod, "use_object_transform"):
        mod.use_object_transform = settings.use_object_transform

    if hasattr(mod, "mix_mode"):
        mod.mix_mode = settings.mix_mode

    if hasattr(mod, "mix_factor"):
        mod.mix_factor = 1.0

    # Vertex group layer selection (varies by version)
    # Try to match by name when available; otherwise leave default.
    if settings.by_name:
        for prop in ("layers_vgroup_select_src", "layers_vgroup_select_dst"):
            if hasattr(mod, prop):
                try:
                    setattr(mod, prop, 'NAME')
                except Exception:
                    pass

    # Apply modifier (needs correct context)
    bpy.ops.object.select_all(action='DESELECT')
    dst.select_set(True)
    bpy.context.view_layer.objects.active = dst

    bpy.ops.object.modifier_apply(modifier=mod.name)

def _call_data_transfer_vgroups(settings, **dt_kwargs):
    """
    Blender versions disagree on layers_select_* enums.
    Try NAME/INDEX first (common for vertex groups), then ALL/ACTIVE fallback.
    """
    # Prefer by-name mapping when available
    preferred = 'NAME' if settings.by_name else 'INDEX'

    attempts = [
        dict(layers_select_src=preferred, layers_select_dst=preferred),  # ('NAME','INDEX') builds
        dict(layers_select_src='NAME', layers_select_dst='NAME'),
        dict(layers_select_src='INDEX', layers_select_dst='INDEX'),
        dict(layers_select_src='ALL', layers_select_dst='ALL'),          # ('ALL','ACTIVE') builds
        dict(layers_select_src='ACTIVE', layers_select_dst='ACTIVE'),
    ]

    last_err = None
    for extra in attempts:
        try:
            return bpy.ops.object.data_transfer(**dt_kwargs, **extra)
        except TypeError as e:
            last_err = e
            continue

    # If none worked, re-raise the last error so you see the true failure.
    raise last_err

def _transfer_vgroups_via_modifier(src, dst, settings):
    _ensure_object_mode()

    mod = dst.modifiers.get("T8_WT_DataTransfer")
    if mod is None:
        mod = dst.modifiers.new(name="T8_WT_DataTransfer", type='DATA_TRANSFER')

    mod.object = src

    # Vertex group weights
    mod.use_vert_data = True
    mod.data_types_verts = {'VGROUP_WEIGHTS'}

    mod.vert_mapping = settings.vertex_mapping
    mod.ray_radius = settings.ray_radius
    mod.use_object_transform = settings.use_object_transform
    mod.mix_mode = settings.mix_mode
    mod.mix_factor = 1.0

    # Apply modifier (must be active)
    bpy.ops.object.select_all(action='DESELECT')
    dst.select_set(True)
    bpy.context.view_layer.objects.active = dst
    bpy.ops.object.modifier_apply(modifier=mod.name)


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

class T8TOOLS_WT_Settings(PropertyGroup):
    clear_destination_groups: BoolProperty(
        name="Clear Dest Weights First",
        description="Deletes all vertex groups on each destination before transferring (very destructive, very consistent)",
        default=True,
    )

    vertex_mapping: EnumProperty(
        name="Vertex Mapping",
        description="How to map source vertices to destination",
        items=[
            ('NEAREST', "Nearest Vertex", "Use nearest vertices"),
            ('POLYINTERP_NEAREST', "Nearest Face Interp", "Interpolate from nearest faces"),
            ('TOPOLOGY', "Topology", "Match by topology (requires identical topology)"),
        ],
        default='POLYINTERP_NEAREST',
    )

    mix_mode: EnumProperty(
        name="Mix Mode",
        description="How to mix transferred weights with existing destination weights",
        items=[
            ('REPLACE', "Replace", "Replace destination weights"),
            ('ADD', "Add", "Add to destination weights"),
            ('SUB', "Subtract", "Subtract from destination weights"),
        ],
        default='REPLACE',
    )

    ray_radius: FloatProperty(
        name="Ray Radius",
        description="Search radius (Blender units). Increase if transfer misses areas",
        default=10.0,
        min=0.0,
        soft_max=1000.0,
    )

    use_object_transform: BoolProperty(
        name="Object Transform",
        description="Account for object transforms when transferring",
        default=True,
    )

    by_name: BoolProperty(
        name="By Name",
        description="Match vertex groups by name (recommended)",
        default=True,
    )


# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class T8TOOLS_OT_weight_transfer_active_to_selected(Operator):
    bl_idname = "t8tools.weight_transfer_active_to_selected"
    bl_label = "Transfer Active → Selected"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _ensure_object_mode()

        settings = context.scene.t8tools_wt_settings
        src = context.view_layer.objects.active

        if not _is_mesh(src):
            self.report({'ERROR'}, "Active object must be a mesh (source).")
            return {'CANCELLED'}

        dests = [o for o in context.selected_objects if o != src and _is_mesh(o)]
        ignored = [o for o in context.selected_objects if o != src and not _is_mesh(o)]

        if ignored:
            self.report({'WARNING'}, "Ignored non-mesh: " + ", ".join(o.name for o in ignored))

        if not dests:
            self.report({'ERROR'}, "Select at least one destination mesh (in addition to the active source mesh).")
            return {'CANCELLED'}

        if len(src.vertex_groups) == 0:
            self.report({'ERROR'}, "Source mesh has no vertex groups to transfer.")
            return {'CANCELLED'}

        # A -> each dest
        for dst in dests:
            bpy.ops.object.select_all(action='DESELECT')

            # Source must be active
            src.select_set(True)
            context.view_layer.objects.active = src

            # Destination selected
            dst.select_set(True)

            if settings.clear_destination_groups:
                dst.vertex_groups.clear()

            # Ensure destination has groups
            for name in [vg.name for vg in src.vertex_groups]:
                if name not in dst.vertex_groups:
                    dst.vertex_groups.new(name=name)

            # 🔴 THIS IS STEP 2 🔴
            _transfer_vgroups_via_modifier(src, dst, settings)




        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        src.select_set(True)
        context.view_layer.objects.active = src
        for d in dests:
            d.select_set(True)

        self.report({'INFO'}, f"Transferred weights from '{src.name}' to {len(dests)} object(s).")
        return {'FINISHED'}


# ------------------------------------------------------------
# UI Panel (nested under your Quick Tools panel)
# ------------------------------------------------------------

class VIEW3D_PT_T8Tools_QuickWeightTransfer(Panel):
    bl_label = "Quick Weight Transfer"
    bl_idname = "VIEW3D_PT_t8tools_quick_weight_transfer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_quick"   # <-- nests under your Quick Tools panel
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = context.scene.t8tools_wt_settings

        layout.label(text="Active → Selected (Destructive)")
        layout.prop(s, "clear_destination_groups")
        layout.prop(s, "vertex_mapping")
        layout.prop(s, "mix_mode")
        layout.prop(s, "ray_radius")
        layout.prop(s, "use_object_transform")
        layout.prop(s, "by_name")

        layout.separator()
        layout.operator("t8tools.weight_transfer_active_to_selected", icon='MOD_DATA_TRANSFER')


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

classes = (
    T8TOOLS_WT_Settings,
    T8TOOLS_OT_weight_transfer_active_to_selected,
    VIEW3D_PT_T8Tools_QuickWeightTransfer,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.t8tools_wt_settings = PointerProperty(type=T8TOOLS_WT_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "t8tools_wt_settings"):
        del bpy.types.Scene.t8tools_wt_settings

    for c in reversed(classes):
        bpy.utils.unregister_class(c)
