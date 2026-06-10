# rig_tools/rig_shape_key_bone_aligner.py
# T8 Tools Rig Module: Shape Key Bone Aligner
# Safely moves armature bones by weighted vertex-group deltas between two shape-key states.

import bpy
from mathutils import Vector
from bpy.props import (
    PointerProperty,
    FloatProperty,
    BoolProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)

T8_SKBA_PARENT_PANEL = "VIEW3D_PT_t8tools_rig"


def fmt_vec(v, precision=4):
    if v is None:
        return "None"
    return f"({v.x:.{precision}f}, {v.y:.{precision}f}, {v.z:.{precision}f})"


def _shape_key_items_common(self, context, include_current=True):
    items = []
    props = getattr(context.scene, "t8_skba_props", None) if context and context.scene else None
    mesh_obj = props.mesh_obj if props else None
    if mesh_obj and mesh_obj.type == "MESH" and mesh_obj.data.shape_keys:
        for key in mesh_obj.data.shape_keys.key_blocks:
            desc = "Basis shape key" if key.name == "Basis" else f"Shape Key: {key.name}"
            items.append((key.name, key.name, desc))
    return items if items else [("NONE", "None", "Select a mesh with shape keys")]


def get_source_shape_key_items(self, context):
    return _shape_key_items_common(self, context)


def get_target_shape_key_items(self, context):
    return _shape_key_items_common(self, context)


def get_selected_bone_names(armature_obj):
    """Return selected bones from Pose/Edit/Object data selection."""
    if not armature_obj or armature_obj.type != "ARMATURE":
        return set()
    selected = set()
    if armature_obj.mode == "POSE":
        selected.update(pb.name for pb in armature_obj.pose.bones if pb.bone.select)
    elif armature_obj.mode == "EDIT":
        selected.update(eb.name for eb in armature_obj.data.edit_bones if eb.select)
    else:
        selected.update(b.name for b in armature_obj.data.bones if b.select)
    return selected


def world_center_from_evaluated_vertices(mesh_obj, mesh_eval_data, vertex_indices, weights, use_weighted_average):
    if not vertex_indices:
        return None

    total = Vector((0.0, 0.0, 0.0))
    weight_sum = 0.0
    count = 0

    for idx in vertex_indices:
        if idx >= len(mesh_eval_data.vertices):
            continue
        world_pos = mesh_obj.matrix_world @ mesh_eval_data.vertices[idx].co
        if use_weighted_average:
            w = weights.get(idx, 1.0)
            total += world_pos * w
            weight_sum += w
        else:
            total += world_pos
        count += 1

    if count == 0:
        return None
    if use_weighted_average and weight_sum > 1e-8:
        return total / weight_sum
    return total / count


def vertex_group_indices(mesh_obj, group_name, threshold):
    vg = mesh_obj.vertex_groups.get(group_name)
    if not vg:
        return [], {}

    indices = []
    weights = {}
    for v in mesh_obj.data.vertices:
        try:
            w = vg.weight(v.index)
        except RuntimeError:
            continue
        if w >= threshold:
            indices.append(v.index)
            weights[v.index] = w
    return indices, weights


def set_shape_key_state(mesh_obj, source_name, target_name, source_value, target_value, zero_other_shape_keys):
    key_blocks = mesh_obj.data.shape_keys.key_blocks
    if zero_other_shape_keys:
        for kb in key_blocks:
            kb.value = 0.0

    source = key_blocks.get(source_name)
    target = key_blocks.get(target_name)

    if source:
        source.value = source_value
    if target and target != source:
        target.value = target_value


def make_eval_mesh_for_state(mesh_obj, source_name, target_name, source_value, target_value, zero_other_shape_keys, depsgraph):
    set_shape_key_state(mesh_obj, source_name, target_name, source_value, target_value, zero_other_shape_keys)
    depsgraph.update()
    eval_obj = mesh_obj.evaluated_get(depsgraph)
    return bpy.data.meshes.new_from_object(eval_obj, depsgraph=depsgraph)


def gather_candidate_bones(props, context):
    armature_obj = props.armature_obj
    mesh_obj = props.mesh_obj
    all_bone_names = [b.name for b in armature_obj.data.bones]

    if props.bone_name_filter.strip():
        token = props.bone_name_filter.strip().lower()
        all_bone_names = [name for name in all_bone_names if token in name.lower()]

    if props.only_selected_bones:
        selected = get_selected_bone_names(armature_obj)
        if not selected:
            return [], ["Only Selected Bones is ON, but no bones are selected on the armature."]
        all_bone_names = [name for name in all_bone_names if name in selected]

    warnings = []
    candidates = []
    for bone_name in all_bone_names:
        group_name = props.vertex_group_prefix + bone_name + props.vertex_group_suffix
        if mesh_obj.vertex_groups.get(group_name):
            candidates.append((bone_name, group_name))
        elif not props.skip_missing_vertex_groups:
            candidates.append((bone_name, group_name))

    if not candidates:
        warnings.append("No candidate bones found. Check bone names versus vertex group names, selected bones, or Bone Name Filter.")
    return candidates, warnings


def calculate_bone_deltas(props, context, operator=None):
    armature_obj = props.armature_obj
    mesh_obj = props.mesh_obj
    source_key_name = props.source_shape_key_name
    target_key_name = props.target_shape_key_name

    if not armature_obj or armature_obj.type != "ARMATURE":
        raise ValueError("Select a valid armature.")
    if not mesh_obj or mesh_obj.type != "MESH":
        raise ValueError("Select a valid mesh.")
    if not mesh_obj.data.shape_keys:
        raise ValueError(f"Mesh '{mesh_obj.name}' has no shape keys.")
    key_blocks = mesh_obj.data.shape_keys.key_blocks
    if source_key_name == "NONE" or not key_blocks.get(source_key_name):
        raise ValueError("Select a valid source shape key.")
    if target_key_name == "NONE" or not key_blocks.get(target_key_name):
        raise ValueError("Select a valid target shape key.")

    original_values = {kb.name: kb.value for kb in key_blocks}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    candidates, warnings = gather_candidate_bones(props, context)

    results = []
    source_mesh = None
    target_mesh = None

    try:
        # Source state: source key at Source Strength, target key at 0.
        source_mesh = make_eval_mesh_for_state(
            mesh_obj,
            source_key_name,
            target_key_name,
            props.source_shape_key_strength,
            0.0,
            props.zero_other_shape_keys,
            depsgraph,
        )

        # Target state: source key optionally remains active, target key at Target Strength.
        source_in_target_value = props.source_shape_key_strength if props.keep_source_active_in_target else 0.0
        target_mesh = make_eval_mesh_for_state(
            mesh_obj,
            source_key_name,
            target_key_name,
            source_in_target_value,
            props.target_shape_key_strength,
            props.zero_other_shape_keys,
            depsgraph,
        )

        for bone_name, group_name in candidates:
            if not mesh_obj.vertex_groups.get(group_name):
                results.append({
                    "bone": bone_name,
                    "group": group_name,
                    "status": "missing_group",
                    "message": f"No vertex group named '{group_name}'",
                })
                continue

            indices, weights = vertex_group_indices(mesh_obj, group_name, props.weight_threshold)
            if len(indices) < props.min_vertex_count:
                results.append({
                    "bone": bone_name,
                    "group": group_name,
                    "status": "too_few_vertices",
                    "vertex_count": len(indices),
                    "message": f"Only {len(indices)} vertices met threshold",
                })
                continue

            center_source = world_center_from_evaluated_vertices(
                mesh_obj, source_mesh, indices, weights, props.use_weighted_average
            )
            center_target = world_center_from_evaluated_vertices(
                mesh_obj, target_mesh, indices, weights, props.use_weighted_average
            )

            if center_source is None or center_target is None:
                results.append({
                    "bone": bone_name,
                    "group": group_name,
                    "status": "bad_center",
                    "vertex_count": len(indices),
                    "message": "Could not calculate weighted center",
                })
                continue

            delta_world = center_target - center_source
            delta_len = delta_world.length

            if props.invert_delta:
                delta_world = -delta_world
                delta_len = delta_world.length

            if delta_len < props.min_move_distance:
                results.append({
                    "bone": bone_name,
                    "group": group_name,
                    "status": "below_min_move",
                    "vertex_count": len(indices),
                    "delta_world": delta_world,
                    "delta_length": delta_len,
                    "message": f"Delta {delta_len:.6f} below minimum",
                })
                continue

            clamped = False
            if props.limit_max_move and props.max_move_distance > 0 and delta_len > props.max_move_distance:
                delta_world = delta_world.normalized() * props.max_move_distance
                clamped = True

            results.append({
                "bone": bone_name,
                "group": group_name,
                "status": "ready",
                "vertex_count": len(indices),
                "center_source": center_source,
                "center_target": center_target,
                "delta_world": delta_world,
                "delta_length": delta_world.length,
                "clamped": clamped,
                "message": "Ready",
            })

    finally:
        if source_mesh:
            bpy.data.meshes.remove(source_mesh, do_unlink=True)
        if target_mesh:
            bpy.data.meshes.remove(target_mesh, do_unlink=True)
        if props.restore_shape_key_values:
            for kb_name, val in original_values.items():
                kb = key_blocks.get(kb_name)
                if kb:
                    kb.value = val
            depsgraph.update()

    return results, warnings


def apply_deltas_to_armature(armature_obj, results, props, operator):
    prev_active = bpy.context.view_layer.objects.active
    prev_mode = armature_obj.mode

    moved = 0
    skipped = 0

    try:
        bpy.context.view_layer.objects.active = armature_obj
        if armature_obj.mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")

        edit_bones = armature_obj.data.edit_bones
        arm_inv = armature_obj.matrix_world.inverted().to_3x3()

        for item in results:
            if item.get("status") != "ready":
                skipped += 1
                continue

            eb = edit_bones.get(item["bone"])
            if not eb:
                skipped += 1
                continue

            delta_local = arm_inv @ item["delta_world"]

            if props.move_heads:
                eb.head = eb.head + delta_local
            if props.move_tails:
                eb.tail = eb.tail + delta_local

            moved += 1

    finally:
        if bpy.context.view_layer.objects.active == armature_obj and armature_obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if prev_active:
            bpy.context.view_layer.objects.active = prev_active
        if prev_active == armature_obj and prev_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode=prev_mode)
            except Exception as exc:
                if operator:
                    operator.report({'WARNING'}, f"Could not restore previous armature mode '{prev_mode}': {exc}")

    return moved, skipped


def build_report_text(results, warnings, title="T8 Shape Key Bone Align Report"):
    lines = []
    lines.append("\n" + "=" * 88)
    lines.append(title)
    lines.append("=" * 88)
    for warning in warnings:
        lines.append(f"WARNING: {warning}")
    for item in results:
        bone = item.get("bone", "?")
        status = item.get("status", "?")
        vcount = item.get("vertex_count", 0)
        delta = item.get("delta_world")
        delta_len = item.get("delta_length", 0.0)
        clamp = " CLAMPED" if item.get("clamped") else ""
        if delta is not None:
            lines.append(f"{bone:44s} {status:18s} verts={vcount:5d} delta={fmt_vec(delta)} len={delta_len:.6f}{clamp}")
        else:
            lines.append(f"{bone:44s} {status:18s} {item.get('message', '')}")
    lines.append("=" * 88)
    return "\n".join(lines)


def print_report(results, warnings, title="T8 Shape Key Bone Align Report"):
    print(build_report_text(results, warnings, title) + "\n")


def show_preview_popup(context, results, warnings):
    ready = [r for r in results if r.get("status") == "ready"]
    skipped = len(results) - len(ready)
    largest = sorted(ready, key=lambda r: r.get("delta_length", 0), reverse=True)[:8]

    def draw(self, _context):
        layout = self.layout
        layout.label(text=f"Ready: {len(ready)}    Skipped: {skipped}")
        for warning in warnings[:3]:
            layout.label(text=warning, icon="ERROR")
        if largest:
            layout.separator()
            layout.label(text="Largest deltas:")
            for item in largest:
                layout.label(text=f"{item['bone']}: {item.get('delta_length', 0):.6f}")
        else:
            layout.label(text="No ready bones. Check console report.", icon="INFO")

    context.window_manager.popup_menu(draw, title="T8 Shape Key Bone Align Preview", icon="ARMATURE_DATA")


class T8_SKBA_Properties(bpy.types.PropertyGroup):
    armature_obj: PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "ARMATURE",
        description="Armature whose bones will be moved",
    )
    mesh_obj: PointerProperty(
        name="Mesh",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "MESH",
        description="Skinned mesh with vertex groups and shape keys",
    )
    source_shape_key_name: EnumProperty(
        name="Source Shape Key",
        items=get_source_shape_key_items,
        description="Shape key state used as the starting position",
    )
    target_shape_key_name: EnumProperty(
        name="Target Shape Key",
        items=get_target_shape_key_items,
        description="Shape key state used as the target position",
    )

    source_shape_key_strength: FloatProperty(
        name="Source Strength",
        description="Source shape key value used for the starting state",
        default=0.0,
        min=-10.0,
        max=10.0,
    )
    target_shape_key_strength: FloatProperty(
        name="Target Strength",
        description="Target shape key value used for the deformed target state",
        default=1.0,
        min=-10.0,
        max=10.0,
    )
    keep_source_active_in_target: BoolProperty(
        name="Keep Source Active In Target",
        description="When enabled, target state uses Source + Target. When disabled, target state uses Target only",
        default=False,
    )
    invert_delta: BoolProperty(
        name="Invert Delta",
        description="Move bones opposite the measured shape-key delta",
        default=False,
    )

    weight_threshold: FloatProperty(
        name="Weight Threshold",
        description="Only vertices with this weight or higher are used for each matching vertex group",
        default=0.80,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    min_vertex_count: IntProperty(
        name="Minimum Vertices",
        description="Skip bones whose matching vertex group has fewer qualifying vertices",
        default=3,
        min=1,
    )
    min_move_distance: FloatProperty(
        name="Minimum Move",
        description="Skip tiny movements below this world-space distance",
        default=0.00001,
        min=0.0,
        precision=6,
    )
    limit_max_move: BoolProperty(
        name="Limit Max Move",
        description="Clamp very large movement deltas to avoid rig explosions",
        default=True,
    )
    max_move_distance: FloatProperty(
        name="Max Move Distance",
        description="Maximum world-space distance a bone can move when Limit Max Move is enabled",
        default=0.15,
        min=0.0,
        precision=4,
    )

    use_weighted_average: BoolProperty(
        name="Use Weighted Average",
        description="Higher vertex weights influence the center more strongly",
        default=True,
    )
    only_selected_bones: BoolProperty(
        name="Only Selected Bones",
        description="Only process selected bones from the chosen armature. Use Pose/Edit mode selection before running",
        default=True,
    )
    skip_missing_vertex_groups: BoolProperty(
        name="Skip Missing Groups",
        description="Skip bones that do not have a matching vertex group on the mesh",
        default=True,
    )
    bone_name_filter: StringProperty(
        name="Bone Filter",
        description="Optional text filter for bone names, such as jaw, neck, eye, clavicle",
        default="",
    )
    move_heads: BoolProperty(
        name="Heads",
        description="Move bone heads by the calculated delta",
        default=True,
    )
    move_tails: BoolProperty(
        name="Tails",
        description="Move bone tails by the same delta, preserving bone length and direction",
        default=True,
    )
    zero_other_shape_keys: BoolProperty(
        name="Zero Other Shape Keys",
        description="Temporarily set all other shape keys to 0 while measuring the source/target states",
        default=True,
    )
    restore_shape_key_values: BoolProperty(
        name="Restore Shape Keys",
        description="Restore all shape key values after analysis",
        default=True,
    )
    vertex_group_prefix: StringProperty(
        name="VG Prefix",
        description="Optional prefix added before bone name when looking for vertex groups",
        default="",
    )
    vertex_group_suffix: StringProperty(
        name="VG Suffix",
        description="Optional suffix added after bone name when looking for vertex groups",
        default="",
    )


class T8_SKBA_OT_AutoFill(bpy.types.Operator):
    bl_idname = "t8.skba_auto_fill"
    bl_label = "Auto Fill From Selection"
    bl_description = "Fill Armature and Mesh fields from the selected objects"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.t8_skba_props
        selected = list(context.selected_objects)
        active = context.view_layer.objects.active

        armatures = [o for o in selected if o.type == "ARMATURE"]
        meshes = [o for o in selected if o.type == "MESH"]

        if active and active.type == "ARMATURE":
            props.armature_obj = active
        elif armatures:
            props.armature_obj = armatures[0]

        if active and active.type == "MESH":
            props.mesh_obj = active
        elif meshes:
            props.mesh_obj = meshes[0]

        if props.mesh_obj and props.mesh_obj.type == "MESH" and props.mesh_obj.data.shape_keys:
            keys = props.mesh_obj.data.shape_keys.key_blocks
            if props.source_shape_key_name == "NONE" and keys.get("Basis"):
                props.source_shape_key_name = "Basis"
            if props.target_shape_key_name == "NONE" and len(keys) > 1:
                props.target_shape_key_name = keys[1].name

        if not props.armature_obj or not props.mesh_obj:
            self.report({'WARNING'}, "Select one armature and one mesh, then run Auto Fill.")
        else:
            self.report({'INFO'}, f"Armature: {props.armature_obj.name}, Mesh: {props.mesh_obj.name}")
        return {'FINISHED'}


class T8_SKBA_OT_DryRun(bpy.types.Operator):
    bl_idname = "t8.skba_dry_run"
    bl_label = "Dry Run / Preview"
    bl_description = "Calculate bone deltas and print a report without moving bones"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.t8_skba_props
        try:
            results, warnings = calculate_bone_deltas(props, context, self)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        print_report(results, warnings, "T8 SKBA Dry Run")
        show_preview_popup(context, results, warnings)
        ready = sum(1 for r in results if r.get("status") == "ready")
        skipped = len(results) - ready
        self.report({'INFO'}, f"Dry run complete: {ready} ready, {skipped} skipped. See console for full details.")
        return {'FINISHED'}


class T8_SKBA_OT_AlignBones(bpy.types.Operator):
    bl_idname = "t8.skba_align_bones"
    bl_label = "Apply Delta Alignment"
    bl_description = "Move bones by the measured delta between source and target shape-key states"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "t8_skba_props", None)
        return bool(
            props and props.armature_obj and props.mesh_obj and
            props.armature_obj.type == "ARMATURE" and props.mesh_obj.type == "MESH" and
            props.source_shape_key_name != "NONE" and props.target_shape_key_name != "NONE" and
            props.mesh_obj.data.shape_keys and
            props.mesh_obj.data.shape_keys.key_blocks.get(props.source_shape_key_name) and
            props.mesh_obj.data.shape_keys.key_blocks.get(props.target_shape_key_name) and
            (props.move_heads or props.move_tails)
        )

    def execute(self, context):
        props = context.scene.t8_skba_props
        try:
            results, warnings = calculate_bone_deltas(props, context, self)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        print_report(results, warnings, "T8 SKBA Apply Report")
        moved, skipped = apply_deltas_to_armature(props.armature_obj, results, props, self)

        if moved == 0:
            self.report({'WARNING'}, f"No bones moved. Skipped {skipped}. Run Dry Run and check console.")
        else:
            self.report({'INFO'}, f"Moved {moved} bones. Skipped {skipped}.")
        return {'FINISHED'}


class T8_SKBA_PT_Panel(bpy.types.Panel):
    bl_label = "Shape Key Bone Align"
    bl_idname = "VIEW3D_PT_t8tools_rig_shape_key_bone_align"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "T8 Tools"
    bl_parent_id = T8_SKBA_PARENT_PANEL
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.t8_skba_props

        box = layout.box()
        box.label(text="Objects", icon="OBJECT_DATA")
        box.operator(T8_SKBA_OT_AutoFill.bl_idname, icon="EYEDROPPER")
        box.prop(props, "armature_obj")
        box.prop(props, "mesh_obj")

        if props.mesh_obj and props.mesh_obj.type == "MESH" and props.mesh_obj.data.shape_keys:
            box.prop(props, "source_shape_key_name")
            box.prop(props, "target_shape_key_name")
            row = box.row(align=True)
            row.prop(props, "source_shape_key_strength")
            row.prop(props, "target_shape_key_strength")
            box.prop(props, "keep_source_active_in_target")
        elif props.mesh_obj:
            box.label(text="Selected mesh has no shape keys.", icon="ERROR")
        else:
            box.label(text="Select a mesh with shape keys.", icon="INFO")

        box = layout.box()
        box.label(text="Bone Scope", icon="BONE_DATA")
        box.prop(props, "only_selected_bones")
        box.prop(props, "skip_missing_vertex_groups")
        box.prop(props, "bone_name_filter")
        row = box.row(align=True)
        row.prop(props, "vertex_group_prefix")
        row.prop(props, "vertex_group_suffix")

        box = layout.box()
        box.label(text="Delta Settings", icon="MOD_SHRINKWRAP")
        box.prop(props, "weight_threshold")
        box.prop(props, "min_vertex_count")
        box.prop(props, "use_weighted_average")
        box.prop(props, "min_move_distance")
        box.prop(props, "limit_max_move")
        if props.limit_max_move:
            box.prop(props, "max_move_distance")
        box.prop(props, "invert_delta")

        box = layout.box()
        box.label(text="Apply Options", icon="CONSTRAINT_BONE")
        row = box.row(align=True)
        row.prop(props, "move_heads")
        row.prop(props, "move_tails")
        box.prop(props, "zero_other_shape_keys")
        box.prop(props, "restore_shape_key_values")

        layout.separator()
        layout.operator(T8_SKBA_OT_DryRun.bl_idname, icon="VIEWZOOM")
        row = layout.row()
        row.scale_y = 1.5
        row.operator(T8_SKBA_OT_AlignBones.bl_idname, icon="ARMATURE_DATA")

        if not T8_SKBA_OT_AlignBones.poll(context):
            layout.label(text="Pick Armature, Mesh, Source, Target, and move option.", icon="INFO")


classes = (
    T8_SKBA_Properties,
    T8_SKBA_OT_AutoFill,
    T8_SKBA_OT_DryRun,
    T8_SKBA_OT_AlignBones,
    T8_SKBA_PT_Panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.t8_skba_props = PointerProperty(type=T8_SKBA_Properties)


def unregister():
    if hasattr(bpy.types.Scene, "t8_skba_props"):
        del bpy.types.Scene.t8_skba_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
