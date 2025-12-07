import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import PointerProperty, BoolProperty, FloatProperty
from mathutils import Matrix


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_settings(context):
    return context.scene.rig_pose_match_simple_settings


def ensure_armatures_valid(settings):
    src = settings.source_rig
    dst = settings.dest_rig

    if not src or not dst:
        return None, None, "Source and Destination rigs must both be set."

    if src == dst:
        return None, None, "Source and Destination must be different objects."

    if src.type != 'ARMATURE' or dst.type != 'ARMATURE':
        return None, None, "Both Source and Destination must be Armature objects."

    return src, dst, None


def match_pose_no_scale(src_obj, dst_obj, threshold=0.0, match_length=False):
    """
    Copy world-space location + rotation (no scale) from source pose bones
    to destination pose bones, for all matching bone names.

    If match_length is True, also adjust the destination pose bone scale
    along its local Y axis so that its pose length matches the source
    bone's pose length.
    """
    src_pbs = src_obj.pose.bones
    dst_pbs = dst_obj.pose.bones

    src_map = {pb.name: pb for pb in src_pbs}

    src_mw = src_obj.matrix_world
    dst_mw = dst_obj.matrix_world
    dst_mw_inv = dst_mw.inverted()

    count = 0

    # Safety limits for scaling so we don't get wild distortions
    MIN_SCALE_Y = 0.3
    MAX_SCALE_Y = 3.0

    for dst_pb in dst_pbs:
        name = dst_pb.name
        src_pb = src_map.get(name)
        if not src_pb:
            continue

        # World-space matrix of the source pose bone
        src_world_mat = src_mw @ src_pb.matrix

        loc, rot, _scale = src_world_mat.decompose()

        # Optionally skip if already "close enough" (threshold > 0)
        if threshold > 0.0:
            dst_world_mat = dst_mw @ dst_pb.matrix
            dst_loc, _dst_rot, _dst_scale = dst_world_mat.decompose()
            if (loc - dst_loc).length <= threshold:
                # Already close enough, skip
                continue

        # Build world matrix with location + rotation only (no scale)
        rot_mat = rot.to_matrix().to_4x4()
        world_no_scale = Matrix.Translation(loc) @ rot_mat

        # Convert back to destination armature space
        dst_local_mat = dst_mw_inv @ world_no_scale

        # Apply location + rotation (no scale)
        dst_pb.matrix = dst_local_mat

        # Optional: match bone length via pose scale along local Y
        if match_length:
            # Source pose length (in armature space)
            src_head = src_pb.head
            src_tail = src_pb.tail
            len_src = (src_tail - src_head).length

            # Destination rest length (Edit Mode length, armature space)
            dst_bone = dst_pb.bone
            dst_head_rest = dst_bone.head_local
            dst_tail_rest = dst_bone.tail_local
            len_rest_dst = (dst_tail_rest - dst_head_rest).length

            if len_src > 1e-6 and len_rest_dst > 1e-6:
                # Scale factor to make destination pose length match source length
                scale_y = len_src / len_rest_dst

                # Clamp to avoid extreme stretching/shrinking
                scale_y = max(MIN_SCALE_Y, min(MAX_SCALE_Y, scale_y))

                # Apply only along bone's local Y axis
                current_scale = dst_pb.scale
                dst_pb.scale = (current_scale.x, scale_y, current_scale.z)

        count += 1

    return count


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class RigPoseMatchSimpleSettings(PropertyGroup):
    source_rig: PointerProperty(
        name="Source Rig",
        type=bpy.types.Object,
        description="Armature to use as the source pose",
    )

    dest_rig: PointerProperty(
        name="Destination Rig",
        type=bpy.types.Object,
        description="Armature to move to match the source pose",
    )

    match_bone_length: BoolProperty(
        name="Match Bone Length to Source",
        description=(
            "After matching pose (location + rotation), adjust destination pose "
            "bone scale along its length so its pose length matches the source bone. "
            "This can help reduce 'squishing' when bones are much longer or shorter."
        ),
        default=False,
    )

    # New: options for disconnecting and inherit scale
    disconnect_bones: BoolProperty(
        name="Disconnect Bones",
        description="Turn off 'Connected' for all bones in selected armatures (Edit Mode)",
        default=True,
    )

    inherit_scale_none: BoolProperty(
        name="Inherit Scale: None",
        description="Set 'Inherit Scale' to None for deform bones in selected armatures",
        default=True,
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class RIGMATCH_OT_MatchPoseNoScale(Operator):
    """Match destination rig pose to source rig (location + rotation only, no scale)."""
    bl_idname = "rigmatch.match_pose_no_scale"
    bl_label = "Match Pose (No Scale)"
    bl_options = {'REGISTER', 'UNDO'}

    # Optional: tiny distance threshold to skip bones that are already lined up
    distance_threshold: FloatProperty(
        name="Skip if distance <",
        description="If > 0, bones whose heads are already closer than this distance will be skipped.",
        default=0.0,
        min=0.0,
    )

    def execute(self, context):
        settings = get_settings(context)
        src, dst, err = ensure_armatures_valid(settings)
        if err:
            self.report({'ERROR'}, err)
            return {'CANCELLED'}

        # Read the length-matching option from the panel settings
        match_length = settings.match_bone_length

        count = match_pose_no_scale(
            src,
            dst,
            threshold=self.distance_threshold,
            match_length=match_length,
        )

        msg = f"Matched {count} bones (no scale"
        if match_length:
            msg += ", length matched"
        msg += ")."

        self.report({'INFO'}, msg)
        return {'FINISHED'}


class RIGMATCH_OT_CleanupBones(Operator):
    """
    For all selected armatures:
    - Optionally disconnect bones (turn off 'Connected' in Edit Mode).
    - Optionally set Inherit Scale = None on deform bones.
    """
    bl_idname = "rigmatch.cleanup_bones"
    bl_label = "Apply Bone Relations to Selected Rigs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)

        do_disconnect = settings.disconnect_bones
        do_inherit = settings.inherit_scale_none

        if not (do_disconnect or do_inherit):
            self.report({'WARNING'}, "No options enabled (nothing to do).")
            return {'CANCELLED'}

        selected_armatures = [
            obj for obj in context.selected_objects
            if obj.type == 'ARMATURE'
        ]

        if not selected_armatures:
            self.report({'ERROR'}, "Select at least one armature object.")
            return {'CANCELLED'}

        # Store original active + mode so we can restore
        orig_active = context.view_layer.objects.active
        orig_mode = orig_active.mode if orig_active else 'OBJECT'

        # Ensure we're in OBJECT mode before switching active objects
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        for rig in selected_armatures:
            context.view_layer.objects.active = rig

            # Disconnect bones in Edit Mode
            if do_disconnect:
                bpy.ops.object.mode_set(mode='EDIT')
                for eb in rig.data.edit_bones:
                    if eb.parent and eb.use_connect:
                        eb.use_connect = False

            # Set Inherit Scale = None on deform bones
            if do_inherit:
                # We can be in POSE or OBJECT mode; using POSE is convenient here
                bpy.ops.object.mode_set(mode='POSE')
                for bone in rig.data.bones:
                    if bone.use_deform:
                        bone.inherit_scale = 'NONE'

        # Restore original active + mode as best we can
        if orig_active and orig_active.name in bpy.data.objects:
            context.view_layer.objects.active = orig_active
            try:
                bpy.ops.object.mode_set(mode=orig_mode)
            except Exception:
                bpy.ops.object.mode_set(mode='OBJECT')
        else:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        self.report({'INFO'}, f"Processed {len(selected_armatures)} armature(s).")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI Panel
# ---------------------------------------------------------------------------

class VIEW3D_PT_RigPoseMatchSimple(Panel):
    bl_label = "Rig Matcher"
    bl_idname = "VIEW3D_PT_rig_pose_match_simple"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "T8 Tools"
    bl_parent_id = "VIEW3D_PT_t8tools_mesh"   # <- parent panel from __init__.py

    def draw(self, context):
        layout = self.layout
        settings = get_settings(context)

        col = layout.column(align=True)
        col.label(text="Rigs")
        col.prop(settings, "source_rig")
        col.prop(settings, "dest_rig")

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Pose Matching")
        col.prop(settings, "match_bone_length", text="Match Bone Length")
        op = col.operator("rigmatch.match_pose_no_scale", icon='ARMATURE_DATA')
        op.distance_threshold = 0.0

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Bone Relations Tools")
        col.prop(settings, "disconnect_bones")
        col.prop(settings, "inherit_scale_none")
        col.operator("rigmatch.cleanup_bones", icon='BONE_DATA')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    RigPoseMatchSimpleSettings,
    RIGMATCH_OT_MatchPoseNoScale,
    RIGMATCH_OT_CleanupBones,
    VIEW3D_PT_RigPoseMatchSimple,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rig_pose_match_simple_settings = PointerProperty(
        type=RigPoseMatchSimpleSettings
    )


def unregister():
    del bpy.types.Scene.rig_pose_match_simple_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
