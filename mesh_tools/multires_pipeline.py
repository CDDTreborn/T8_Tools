import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import (
    PointerProperty,
    StringProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
)

# ------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------

def _ensure_surface_deform_bound(driver_obj, target_obj, mod_name="T8_SurfaceDeform"):
    _ensure_object_mode()

    mod = driver_obj.modifiers.get(mod_name)
    if not mod:
        mod = driver_obj.modifiers.new(name=mod_name, type='SURFACE_DEFORM')

    mod.target = target_obj

    # Bind needs correct context
    bpy.ops.object.select_all(action='DESELECT')
    target_obj.select_set(True)
    driver_obj.select_set(True)
    bpy.context.view_layer.objects.active = driver_obj


    # Bind if not bound
    if hasattr(mod, "is_bound"):
        if not mod.is_bound:
            bpy.ops.object.surfacedeform_bind(modifier=mod.name)
    else:
        bpy.ops.object.surfacedeform_bind(modifier=mod.name)

    return mod

def _get_obj(name: str):
    return bpy.data.objects.get(name) if name else None

def _ensure_object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

def _duplicate_object(obj: bpy.types.Object, name: str, link_data=True):
    """Duplicate object + data. link_data=False makes a full mesh copy."""
    new_obj = obj.copy()
    new_obj.name = name
    new_obj.data = obj.data.copy() if not link_data else obj.data
    bpy.context.collection.objects.link(new_obj)
    new_obj.matrix_world = obj.matrix_world.copy()
    return new_obj

def _hide(obj: bpy.types.Object, hide=True):
    """Operator-safe hiding: keeps object selectable for ops."""
    obj.hide_viewport = hide
    obj.hide_render = hide
    # DO NOT call obj.hide_set(hide) — it can make ops fail in 4.x


def _remove_modifier(obj, mod_name):
    mod = obj.modifiers.get(mod_name)
    if mod:
        obj.modifiers.remove(mod)

def _find_modifier(obj, mod_type):
    for m in obj.modifiers:
        if m.type == mod_type:
            return m
    return None

def _add_multires(obj, target_levels: int):
    """Ensure obj has Multires and ends up at EXACTLY target_levels subdivisions."""
    _ensure_object_mode()
    mr = _find_modifier(obj, 'MULTIRES')
    if not mr:
        mr = obj.modifiers.new(name="Multires", type='MULTIRES')

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Subdivide only as much as needed to reach target_levels
    current = getattr(mr, "total_levels", None)
    if current is None:
        # Fallback: assume current levels are mr.levels
        current = mr.levels

    # total_levels is read-only; but it updates as you subdivide.
    # So we loop until we hit the desired level.
    while getattr(mr, "total_levels", mr.levels) < target_levels:
        bpy.ops.object.multires_subdivide(modifier=mr.name)

    # Clamp viewport/sculpt/render to target (or as close as allowed)
    if hasattr(mr, "levels"):
        mr.levels = min(target_levels, getattr(mr, "total_levels", target_levels))
    if hasattr(mr, "sculpt_levels"):
        mr.sculpt_levels = min(target_levels, getattr(mr, "total_levels", target_levels))
    if hasattr(mr, "render_levels"):
        mr.render_levels = min(target_levels, getattr(mr, "total_levels", target_levels))

    obj.select_set(False)
    return mr


def _apply_all_modifiers(obj):
    _ensure_object_mode()
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    obj.select_set(False)

def _ensure_bake_material_and_image(settings):
    mat_name = settings.bake_material_name
    img_name = settings.bake_image_name
    res = int(settings.bake_res)

    # Image
    img = bpy.data.images.get(img_name)
    if not img:
        img = bpy.data.images.new(img_name, width=res, height=res, alpha=False, float_buffer=False)
    img.colorspace_settings.name = 'Non-Color'

    # Material
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True

    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")

    bsdf = None
    for n in nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break
    if not bsdf:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    if not out.inputs['Surface'].is_linked:
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    img_node = None
    for n in nodes:
        if n.type == 'TEX_IMAGE' and n.image == img:
            img_node = n
            break
    if not img_node:
        img_node = nodes.new("ShaderNodeTexImage")
        img_node.image = img

    # Make active for bake
    for n in nodes:
        n.select = False
    img_node.select = True
    nodes.active = img_node

    return mat, img, img_node

def _assign_material(obj, mat):
    if obj.type != 'MESH':
        return
    mats = obj.data.materials
    if mats:
        if mat.name not in [m.name for m in mats if m]:
            mats.append(mat)
    else:
        mats.append(mat)


# ------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------

class T8TOOLS_PG_MultiresPipelineSettings(PropertyGroup):
    base_obj: PointerProperty(
        name="Base Mesh (A)",
        type=bpy.types.Object,
        description="Select the base mesh. The pipeline will build A0, B (multires), and C (sculpt target)."
    )

    a0_name: StringProperty(name="A0 Name", default="")
    b_name: StringProperty(name="B Name", default="")
    c_name: StringProperty(name="C Name", default="")

    multires_levels: IntProperty(
        name="Multires Levels",
        default=3, min=0, max=10,
        description="Multires levels added to B."
    )


    bake_res: EnumProperty(
        name="Bake Resolution",
        items=[('2048', "2K", ""), ('4096', "4K", ""), ('8192', "8K", "")],
        default='4096',
    )
    bake_image_name: StringProperty(name="Bake Image Name", default="Multires_Normal")
    bake_material_name: StringProperty(name="Bake Material", default="MultiresBake")


# ------------------------------------------------------------------------
# Operators
# ------------------------------------------------------------------------

class T8TOOLS_OT_multires_pipeline_setup(Operator):
    bl_idname = "t8tools.multires_pipeline_setup"
    bl_label = "Setup Multires Pipeline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.t8tools_multires_pipeline
        base = s.base_obj

        if not base or base.type != 'MESH':
            self.report({'ERROR'}, "Pick a mesh object for Base Mesh (A).")
            return {'CANCELLED'}

        _ensure_object_mode()

        # --- A0 ---
        a0 = _get_obj(s.a0_name)
        if not a0:
            a0 = _duplicate_object(base, base.name + "_A0_ORIGINAL", link_data=False)
            _hide(a0, True)
            s.a0_name = a0.name

        # --- B (multires object you reshape + bake) ---
        old_b = _get_obj(s.b_name)
        if old_b:
            bpy.data.objects.remove(old_b, do_unlink=True)

        b = _duplicate_object(a0, base.name + "_B", link_data=False)
        s.b_name = b.name
        _hide(b, False)

        mr_b = _add_multires(b, s.multires_levels)

        # --- C (sculpt target) ---
        old_c = _get_obj(s.c_name)
        if old_c:
            bpy.data.objects.remove(old_c, do_unlink=True)

        c = _duplicate_object(b, base.name + "_C_SCULPT", link_data=False)
        s.c_name = c.name
        _hide(c, False)

        # C should NOT inherit shrinkwrap from B; (it doesn't yet, but safe)
        _remove_modifier(c, "T8_Shrinkwrap")

        mr_c = _find_modifier(c, 'MULTIRES')
        if mr_c:
            mr_c.levels = s.multires_levels
            mr_c.sculpt_levels = s.multires_levels
            mr_c.render_levels = s.multires_levels


        _hide(b, False)
        _hide(c, False)
        sd = _ensure_surface_deform_bound(b, c, mod_name="T8_SurfaceDeform")

        # keep ordering consistent
        mods = list(b.modifiers)
        if mods.index(mr_b) > mods.index(sd):
            b.modifiers.move(mods.index(mr_b), mods.index(sd))



        # Optional: hide B so you sculpt on C cleanly
        _hide(b, True)

        self.report({'INFO'}, "Setup complete. Sculpt/edit C. Then run Commit.")
        return {'FINISHED'}


class T8TOOLS_OT_multires_pipeline_commit(Operator):
    bl_idname = "t8tools.multires_pipeline_commit"
    bl_label = "Commit Sculpt to B (Reshape Multires)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.t8tools_multires_pipeline

        a0 = _get_obj(s.a0_name)
        b = _get_obj(s.b_name)
        c = _get_obj(s.c_name)

        if not all([a0, b, c]):
            self.report({'ERROR'}, "Missing A0/B/C. Run Setup first.")
            return {'CANCELLED'}

        if b.type != 'MESH' or c.type != 'MESH':
            self.report({'ERROR'}, "B and C must both be Mesh objects.")
            return {'CANCELLED'}

        _ensure_object_mode()

        # Ensure B has multires
        mr = _find_modifier(b, 'MULTIRES')
        if not mr:
            self.report({'ERROR'}, "B has no Multires modifier (Setup should add it).")
            return {'CANCELLED'}

        # Ensure Surface Deform exists (bound during Setup)
        sd = b.modifiers.get("T8_SurfaceDeform") or _find_modifier(b, 'SURFACE_DEFORM')
        if not sd:
            self.report({'ERROR'}, "Surface Deform missing on B. Run Setup again.")
            return {'CANCELLED'}

        # Ensure modifier order: Multires ABOVE Surface Deform
        mods = list(b.modifiers)
        if mods.index(mr) > mods.index(sd):
            b.modifiers.move(mods.index(mr), mods.index(sd))


        # Make sure B and C are not hidden (ops require selectable objects)
        _hide(b, False)
        _hide(c, False)

        # Duplicate B -> D, apply all modifiers on D (your step B)
        d = _duplicate_object(b, b.name + "_D_APPLIED", link_data=False)
        d_name = d.name

        # Keep D visible/selectable but unobtrusive
        d.hide_render = True
        d.display_type = 'WIRE'

        try:
            _apply_all_modifiers(d)

            # Reshape B using D (your step C)
            _ensure_object_mode()
            bpy.ops.object.select_all(action='DESELECT')
            d.select_set(True)
            b.select_set(True)
            bpy.context.view_layer.objects.active = b

            bpy.ops.object.multires_reshape(modifier=mr.name)

        except Exception as e:
            self.report({'ERROR'}, f"Multires reshape failed: {e}")
            return {'CANCELLED'}

        finally:
            d_obj = bpy.data.objects.get(d_name)
            if d_obj:
                bpy.data.objects.remove(d_obj, do_unlink=True)

        _remove_modifier(b, "T8_SurfaceDeform")


        self.report({'INFO'}, "Commit complete. B is reshaped; ready to bake.")
        return {'FINISHED'}


class T8TOOLS_OT_multires_pipeline_prep_bake(Operator):
    bl_idname = "t8tools.multires_pipeline_prep_bake"
    bl_label = "Prep Bake Material (on B)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.t8tools_multires_pipeline
        b = _get_obj(s.b_name)
        if not b:
            self.report({'ERROR'}, "Missing B. Run Setup first.")
            return {'CANCELLED'}

        mat, img, img_node = _ensure_bake_material_and_image(s)
        _assign_material(b, mat)

        self.report({'INFO'}, f"Ready to bake into image '{img.name}' using material '{mat.name}' on B.")
        return {'FINISHED'}


# ------------------------------------------------------------------------
# UI Panel
# ------------------------------------------------------------------------

class VIEW3D_PT_T8Tools_MultiresPipeline(Panel):
    bl_label = "Multires Pipeline"
    bl_idname = "VIEW3D_PT_t8tools_multires_pipeline"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_mesh"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.t8tools_multires_pipeline
        layout = self.layout

        layout.prop(s, "base_obj")
        layout.prop(s, "multires_levels")

        layout.separator()
        layout.operator("t8tools.multires_pipeline_setup", icon='MOD_SUBSURF')
        layout.operator("t8tools.multires_pipeline_commit", icon='CHECKMARK')

        layout.separator()
        layout.prop(s, "bake_res")
        layout.prop(s, "bake_image_name")
        layout.prop(s, "bake_material_name")
        layout.operator("t8tools.multires_pipeline_prep_bake", icon='IMAGE_DATA')


# ------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------

CLASSES = (
    T8TOOLS_PG_MultiresPipelineSettings,
    T8TOOLS_OT_multires_pipeline_setup,
    T8TOOLS_OT_multires_pipeline_commit,
    T8TOOLS_OT_multires_pipeline_prep_bake,
    VIEW3D_PT_T8Tools_MultiresPipeline,
)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.t8tools_multires_pipeline = PointerProperty(type=T8TOOLS_PG_MultiresPipelineSettings)

def unregister():
    if hasattr(bpy.types.Scene, "t8tools_multires_pipeline"):
        del bpy.types.Scene.t8tools_multires_pipeline
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
