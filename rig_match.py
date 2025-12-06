import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import PointerProperty
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


def match_pose_no_scale(src_obj, dst_obj, threshold=0.0):
    """
    Copy world-space location + rotation (no scale) from source pose bones
    to destination pose bones, for all matching bone names.
    """
    src_pbs = src_obj.pose.bones
    dst_pbs = dst_obj.pose.bones

    src_map = {pb.name: pb for pb in src_pbs}

    src_mw = src_obj.matrix_world
    dst_mw = dst_obj.matrix_world
    dst_mw_inv = dst_mw.inverted()

    count = 0

    for dst_pb in dst_pbs:
        name = dst_pb.name
        src_pb = src_map.get(name)
        if not src_pb:
            continue

        # World-space matrix of the source pose bone
        src_world_mat = src_mw @ src_pb.matrix

        loc, rot, scale = src_world_mat.decompose()

        # Optionally skip if already "close enough" (threshold > 0)
        if threshold > 0.0:
            dst_world_mat = dst_mw @ dst_pb.matrix
            dst_loc, dst_rot, _ = dst_world_mat.decompose()
            if (loc - dst_loc).length <= threshold:
                # Already close enough, skip
                continue

        # Build world matrix with location + rotation only (no scale)
        rot_mat = rot.to_matrix().to_4x4()
        world_no_scale = Matrix.Translation(loc) @ rot_mat

        # Convert back to destination armature space
        dst_local_mat = dst_mw_inv @ world_no_scale

        dst_pb.matrix = dst_local_mat
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


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class RIGMATCH_OT_MatchPoseNoScale(Operator):
    """Match destination rig pose to source rig (location + rotation only, no scale)."""
    bl_idname = "rigmatch.match_pose_no_scale"
    bl_label = "Match Pose (No Scale)"
    bl_options = {'REGISTER', 'UNDO'}

    # Optional: tiny distance threshold to skip bones that are already lined up
    distance_threshold: bpy.props.FloatProperty(
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

        count = match_pose_no_scale(src, dst, threshold=self.distance_threshold)

        self.report({'INFO'}, f"Matched {count} bones (no scale).")
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
        op = col.operator("rigmatch.match_pose_no_scale", icon='ARMATURE_DATA')
        op.distance_threshold = 0.0



# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    RigPoseMatchSimpleSettings,
    RIGMATCH_OT_MatchPoseNoScale,
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


    register()
