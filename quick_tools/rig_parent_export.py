import bpy
import os
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import PointerProperty, BoolProperty, EnumProperty, StringProperty


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _stash_object_visibility(obj):
    """Capture visibility/selectability state we can restore later."""
    if not obj:
        return None

    state = {
        "hide_viewport": getattr(obj, "hide_viewport", False),
        "hide_select": getattr(obj, "hide_select", False),
    }

    # Blender 3.6/4.x supports hide_get/hide_set
    if hasattr(obj, "hide_get"):
        state["hide_get"] = obj.hide_get()

    return state


def _apply_object_visibility(obj, state):
    if not obj or not state:
        return

    if "hide_get" in state and hasattr(obj, "hide_set"):
        obj.hide_set(state["hide_get"])

    if hasattr(obj, "hide_viewport") and "hide_viewport" in state:
        obj.hide_viewport = state["hide_viewport"]

    if hasattr(obj, "hide_select") and "hide_select" in state:
        obj.hide_select = state["hide_select"]


def _ensure_object_selectable_and_visible(obj):
    """
    Make object selectable/visible enough for selection-based export.
    (Does not permanently change it; caller should restore state.)
    """
    if not obj:
        return

    # allow selection
    if hasattr(obj, "hide_select"):
        obj.hide_select = False

    # unhide in viewport (covers most workflows)
    if hasattr(obj, "hide_viewport"):
        obj.hide_viewport = False

    # unhide general hidden flag
    if hasattr(obj, "hide_set"):
        obj.hide_set(False)

def _selected_meshes(context):
    return [o for o in context.selected_objects if o and o.type == 'MESH']


def _clear_parent_keep_transform(obj):
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = mw


def _remove_armature_modifiers(obj):
    for mod in list(obj.modifiers):
        if mod.type == 'ARMATURE':
            obj.modifiers.remove(mod)


def _ensure_single_armature_modifier(mesh_obj, arm_obj):
    """
    Guarantees exactly ONE Armature modifier exists and points at arm_obj.
    Removes any other Armature modifiers.
    """
    arm_mods = [m for m in mesh_obj.modifiers if m.type == 'ARMATURE']
    for m in arm_mods:
        mesh_obj.modifiers.remove(m)

    arm_mod = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
    arm_mod.object = arm_obj
    return arm_mod


def _parent_mesh_to_armature(mesh_obj, arm_obj):
    """
    Parent mesh to armature:
    - Object parent to the armature object
    - Exactly one Armature modifier that points at that armature
    """
    mesh_obj.parent = arm_obj
    mesh_obj.parent_type = 'OBJECT'
    _ensure_single_armature_modifier(mesh_obj, arm_obj)


def _unit_precheck(scene):
    us = scene.unit_settings
    issues = []

    if getattr(us, "system", None) != 'METRIC':
        issues.append("Unit System is not METRIC")

    if abs(getattr(us, "scale_length", 1.0) - 0.01) > 1e-9:
        issues.append(f"Scene Scale is {us.scale_length} (expected 0.01)")

    lu = getattr(us, "length_unit", None)
    if lu is not None and lu != 'CENTIMETERS':
        issues.append(f"Length Unit is {lu} (expected CENTIMETERS)")

    return (len(issues) == 0), issues


def _ensure_export_dir(scene):
    s = scene.t8_rig_parent_export_settings
    path = bpy.path.abspath(s.export_dir).strip()

    if not path:
        if bpy.data.filepath:
            path = os.path.join(os.path.dirname(bpy.data.filepath), "UE_Ready")
        else:
            path = os.path.join(os.path.expanduser("~"), "UE_Ready")

    os.makedirs(path, exist_ok=True)
    return path


def _last_fbx_is_initialized():
    """
    If FBX export hasn't been run yet in this Blender session, we prefer INVOKE_DEFAULT
    so the user can confirm settings once.
    """
    try:
        props = bpy.context.window_manager.operator_properties_last("export_scene.fbx")
    except Exception:
        return False

    fp = getattr(props, "filepath", "")
    return bool(fp) and fp.lower().endswith(".fbx")


def _get_last_fbx_kwargs():
    """
    Pull Blender's last-used export_scene.fbx properties into kwargs.
    We only keep simple types. We'll override the two forced options + filepath.
    """
    props = bpy.context.window_manager.operator_properties_last("export_scene.fbx")
    kwargs = {}

    for k in dir(props):
        if k.startswith("_"):
            continue
        try:
            v = getattr(props, k)
        except Exception:
            continue
        if callable(v):
            continue
        if isinstance(v, (bool, int, float, str)):
            kwargs[k] = v

    return kwargs


def _stash_selection(context):
    sel = [o.name for o in context.selected_objects]
    active = context.view_layer.objects.active.name if context.view_layer.objects.active else ""
    return sel, active


def _restore_selection(context, sel_names, active_name):
    bpy.ops.object.select_all(action='DESELECT')
    for name in sel_names:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.select_set(True)
    context.view_layer.objects.active = bpy.data.objects.get(active_name) if active_name else None


def _force_selection_meshes_plus_rig(context, meshes, rig_obj):
    bpy.ops.object.select_all(action='DESELECT')
    for m in meshes:
        m.select_set(True)
    rig_obj.select_set(True)
    # keep a mesh active (stable naming + avoids armature-active weirdness)
    context.view_layer.objects.active = meshes[0]


def _build_filename(active_mesh_name: str, rig_type: str) -> str:
    suffix = "_MSL" if rig_type == 'MSL' else "_PRP"
    return f"{active_mesh_name}{suffix}.fbx"


def _cleanup_and_bind(meshes, rig_obj, keep_transform: bool):
    for obj in meshes:
        if keep_transform:
            _clear_parent_keep_transform(obj)
        else:
            obj.parent = None

        # Export pipeline MUST guarantee single armature modifier
        _remove_armature_modifiers(obj)

        _parent_mesh_to_armature(obj, rig_obj)


def _export_fbx_with_forced_flags(filepath: str):
    """
    Forces only:
      - Selected Objects
      - Apply Modifiers
    Everything else stays as user's last-used settings.
    """
    export_kwargs = _get_last_fbx_kwargs()

    export_kwargs["filepath"] = filepath
    export_kwargs["use_selection"] = True

    # Apply Modifiers (Geometry > Apply Modifiers)
    export_kwargs["use_mesh_modifiers"] = True
    # Some versions expose this; set if present in last props
    if "use_mesh_modifiers_render" in export_kwargs:
        export_kwargs["use_mesh_modifiers_render"] = True

    bpy.ops.export_scene.fbx('EXEC_DEFAULT', **export_kwargs)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class T8RigParentExportSettings(PropertyGroup):
    msl_rig: PointerProperty(
        name="MSL Rig",
        type=bpy.types.Object,
        description="Armature to use for MSL exports",
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )

    prp_rig: PointerProperty(
        name="PRP Rig",
        type=bpy.types.Object,
        description="Armature to use for PRP exports",
        poll=lambda self, obj: obj.type == 'ARMATURE',
    )

    export_dir: StringProperty(
        name="Export Folder",
        subtype='DIR_PATH',
        default="",
        description="Folder to export FBX files into",
    )

    overwrite_mode: EnumProperty(
        name="Overwrite",
        items=[
            ('WARN', "Warn", "Warn before overwriting existing files"),
            ('ALWAYS', "Always overwrite", "Overwrite without prompting"),
        ],
        default='WARN',
    )

    keep_transform: BoolProperty(
        name="Keep Transform on Unparent",
        default=False,
        description="Clear parent while keeping world transform",
    )

    # Keep this for the manual parent buttons; export path will always ensure single armature mod
    remove_armature_mods: BoolProperty(
        name="Remove Armature Modifiers",
        default=False,
        description="Remove existing Armature modifiers before re-parenting (manual parent buttons)",
    )

    hard_stop_on_unit_mismatch: BoolProperty(
        name="Stop on unit mismatch",
        default=False,
        description="Block export unless units match (Metric, 0.01 scale, centimeters)",
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class T8TOOLS_OT_ParentSelectedToRig(Operator):
    bl_idname = "t8tools.parent_selected_to_rigtype"
    bl_label = "Parent Selected to Rig"
    bl_options = {'REGISTER', 'UNDO'}

    rig_type: EnumProperty(
        items=[('MSL', "MSL", ""), ('PRP', "PRP", "")],
        default='MSL',
    )

    def execute(self, context):
        s = context.scene.t8_rig_parent_export_settings
        rig = s.msl_rig if self.rig_type == 'MSL' else s.prp_rig

        if not rig or rig.type != 'ARMATURE':
            self.report({'ERROR'}, f"{self.rig_type} rig is not set.")
            return {'CANCELLED'}

        meshes = _selected_meshes(context)
        if not meshes:
            self.report({'ERROR'}, "Select one or more mesh objects.")
            return {'CANCELLED'}

        for obj in meshes:
            if s.keep_transform:
                _clear_parent_keep_transform(obj)
            else:
                obj.parent = None

            if s.remove_armature_mods:
                _remove_armature_modifiers(obj)

            _parent_mesh_to_armature(obj, rig)

        self.report({'INFO'}, f"Parented {len(meshes)} mesh(es) to {self.rig_type}.")
        return {'FINISHED'}


class T8TOOLS_OT_ExportSelectedFBX(Operator):
    bl_idname = "t8tools.export_selected_fbx_rigtype"
    bl_label = "Export Selected FBX"
    bl_options = {'REGISTER'}

    rig_type: EnumProperty(
        items=[('MSL', "MSL", ""), ('PRP', "PRP", "")],
        default='MSL',
    )

    def invoke(self, context, event):
        scene = context.scene
        s = scene.t8_rig_parent_export_settings

        ok, issues = _unit_precheck(scene)
        if not ok:
            msg = " | ".join(issues)
            if s.hard_stop_on_unit_mismatch:
                self.report({'ERROR'}, f"Unit pre-check failed: {msg}")
                return {'CANCELLED'}
            else:
                self.report({'WARNING'}, f"Unit pre-check failed: {msg}")

        rig = s.msl_rig if self.rig_type == 'MSL' else s.prp_rig
        if not rig or rig.type != 'ARMATURE':
            self.report({'ERROR'}, f"{self.rig_type} rig is not set.")
            return {'CANCELLED'}

        meshes = _selected_meshes(context)
        if not meshes:
            self.report({'ERROR'}, "Select one or more mesh objects. (Rig is included automatically.)")
            return {'CANCELLED'}

        export_dir = _ensure_export_dir(scene)
        filename = _build_filename(meshes[0].name, self.rig_type)
        filepath = os.path.join(export_dir, filename)

        if s.overwrite_mode == 'WARN' and os.path.exists(filepath):
            # store path for confirm
            self._pending_path = filepath
            return context.window_manager.invoke_confirm(self, event)

        self._pending_path = filepath
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        s = scene.t8_rig_parent_export_settings

        rig = s.msl_rig if self.rig_type == 'MSL' else s.prp_rig
        if not rig or rig.type != 'ARMATURE':
            self.report({'ERROR'}, f"{self.rig_type} rig is not set.")
            return {'CANCELLED'}

        meshes = _selected_meshes(context)
        if not meshes:
            self.report({'ERROR'}, "Select one or more mesh objects.")
            return {'CANCELLED'}

        # If settings not initialized, open exporter once and stop.
        # User sets *their* settings; later runs are deterministic.
        if not _last_fbx_is_initialized():
            export_dir = _ensure_export_dir(scene)
            filename = _build_filename(meshes[0].name, self.rig_type)
            filepath = os.path.join(export_dir, filename)

            # Force ONLY the two required toggles in the UI pass as well:
            return bpy.ops.export_scene.fbx(
                'INVOKE_DEFAULT',
                filepath=filepath,
                use_selection=True,
                use_mesh_modifiers=True,
            )

        # Deterministic export path (after init):
        sel_names, active_name = _stash_selection(context)

        try:
            # Clean + bind (single armature modifier guaranteed)
            _cleanup_and_bind(meshes, rig, keep_transform=s.keep_transform)

            rig_state = _stash_object_visibility(rig) # New
            _ensure_object_selectable_and_visible(rig) # New

            # Export selection must be meshes + exactly this rig
            _force_selection_meshes_plus_rig(context, meshes, rig)

            filepath = getattr(self, "_pending_path", "")
            if not filepath:
                export_dir = _ensure_export_dir(scene)
                filename = _build_filename(meshes[0].name, self.rig_type)
                filepath = os.path.join(export_dir, filename)

            _export_fbx_with_forced_flags(filepath)

            self.report({'INFO'}, f"Exported: {os.path.basename(filepath)}")
            return {'FINISHED'}
        finally:
            _apply_object_visibility(rig, rig_state)
            _restore_selection(context, sel_names, active_name)


class T8TOOLS_OT_ExportBothRigs(Operator):
    bl_idname = "t8tools.export_both_rigs_fbx"
    bl_label = "Export Both (MSL then PRP)"
    bl_options = {'REGISTER'}

    _paths = None  # for confirm flow

    def invoke(self, context, event):
        scene = context.scene
        s = scene.t8_rig_parent_export_settings

        ok, issues = _unit_precheck(scene)
        if not ok:
            msg = " | ".join(issues)
            if s.hard_stop_on_unit_mismatch:
                self.report({'ERROR'}, f"Unit pre-check failed: {msg}")
                return {'CANCELLED'}
            else:
                self.report({'WARNING'}, f"Unit pre-check failed: {msg}")

        if not _last_fbx_is_initialized():
            self.report({'WARNING'}, "FBX settings not initialized yet. Run a single export once (MSL or PRP), confirm settings, then use Export Both.")
            return {'CANCELLED'}

        rig_msl = s.msl_rig
        rig_prp = s.prp_rig
        if not rig_msl or rig_msl.type != 'ARMATURE' or not rig_prp or rig_prp.type != 'ARMATURE':
            self.report({'ERROR'}, "MSL and PRP rigs must both be set.")
            return {'CANCELLED'}

        meshes = _selected_meshes(context)
        if not meshes:
            self.report({'ERROR'}, "Select one or more mesh objects.")
            return {'CANCELLED'}

        export_dir = _ensure_export_dir(scene)
        base = meshes[0].name
        path_msl = os.path.join(export_dir, _build_filename(base, 'MSL'))
        path_prp = os.path.join(export_dir, _build_filename(base, 'PRP'))

        self._paths = (path_msl, path_prp)

        if s.overwrite_mode == 'WARN' and (os.path.exists(path_msl) or os.path.exists(path_prp)):
            return context.window_manager.invoke_confirm(self, event)

        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        s = scene.t8_rig_parent_export_settings

        rig_msl = s.msl_rig
        rig_prp = s.prp_rig
        meshes = _selected_meshes(context)

        if not meshes or not rig_msl or not rig_prp:
            self.report({'ERROR'}, "Missing meshes or rigs.")
            return {'CANCELLED'}

        path_msl, path_prp = self._paths if self._paths else ("", "")
        if not path_msl or not path_prp:
            export_dir = _ensure_export_dir(scene)
            base = meshes[0].name
            path_msl = os.path.join(export_dir, _build_filename(base, 'MSL'))
            path_prp = os.path.join(export_dir, _build_filename(base, 'PRP'))

        sel_names, active_name = _stash_selection(context)

        try:
            # PASS 1: MSL
            state_msl = _stash_object_visibility(rig_msl)
            try:
                _ensure_object_selectable_and_visible(rig_msl)

                _cleanup_and_bind(meshes, rig_msl, keep_transform=s.keep_transform)  # <-- ADD THIS

                _force_selection_meshes_plus_rig(context, meshes, rig_msl)
                _export_fbx_with_forced_flags(path_msl)
            finally:
                _apply_object_visibility(rig_msl, state_msl)

            # PASS 2: PRP
            state_prp = _stash_object_visibility(rig_prp)
            try:
                _ensure_object_selectable_and_visible(rig_prp)

                _cleanup_and_bind(meshes, rig_prp, keep_transform=s.keep_transform)  # <-- ADD THIS

                _force_selection_meshes_plus_rig(context, meshes, rig_prp)
                _export_fbx_with_forced_flags(path_prp)
            finally:
                _apply_object_visibility(rig_prp, state_prp)

            self.report({'INFO'}, f"Exported both: {os.path.basename(path_msl)} + {os.path.basename(path_prp)}")
            return {'FINISHED'}
        finally:
            _restore_selection(context, sel_names, active_name)


# ---------------------------------------------------------------------------
# UI Panel
# ---------------------------------------------------------------------------

class VIEW3D_PT_T8Tools_RigParentExport(Panel):
    bl_label = "Rig Parent / Export"
    bl_idname = "VIEW3D_PT_t8tools_rig_parent_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_quick"  # Quick Tools parent panel

    def draw(self, context):
        layout = self.layout
        s = context.scene.t8_rig_parent_export_settings

        col = layout.column(align=True)
        col.label(text="Designate Rigs")
        col.prop(s, "msl_rig")
        col.prop(s, "prp_rig")

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Parent Selected")
        row = col.row(align=True)
        row.operator("t8tools.parent_selected_to_rigtype", text="→ MSL").rig_type = 'MSL'
        row.operator("t8tools.parent_selected_to_rigtype", text="→ PRP").rig_type = 'PRP'
        col.prop(s, "keep_transform")
        col.prop(s, "remove_armature_mods")

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Export FBX")

        box = col.box()
        box.label(text="Exports: selected meshes + chosen rig only.")
        box.label(text="Forces: Selected Objects + Apply Modifiers.")
        box.label(text="Also enforces exactly one Armature modifier per mesh.")

        col.prop(s, "export_dir")
        col.prop(s, "overwrite_mode")
        col.prop(s, "hard_stop_on_unit_mismatch")

        row = col.row(align=True)
        row.operator("t8tools.export_selected_fbx_rigtype", text="Export MSL").rig_type = 'MSL'
        row.operator("t8tools.export_selected_fbx_rigtype", text="Export PRP").rig_type = 'PRP'
        col.operator("t8tools.export_both_rigs_fbx", text="Export Both (MSL→PRP)")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    T8RigParentExportSettings,
    T8TOOLS_OT_ParentSelectedToRig,
    T8TOOLS_OT_ExportSelectedFBX,
    T8TOOLS_OT_ExportBothRigs,
    VIEW3D_PT_T8Tools_RigParentExport,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.t8_rig_parent_export_settings = PointerProperty(
        type=T8RigParentExportSettings
    )


def unregister():
    del bpy.types.Scene.t8_rig_parent_export_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)