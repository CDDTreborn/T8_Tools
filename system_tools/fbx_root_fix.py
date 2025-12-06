import bpy
import os
import shutil


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

TARGET_SUBSTRING = "elif ob_obj.type == 'EMPTY' or ob_obj.type == 'ARMATURE'"


def find_fbx_exporter_file():
    """
    Try to locate export_fbx_bin.py, in both addons and addons_core.
    Works with Blender 4.5 where script_paths() takes no args.
    """
    candidates = []

    # 1. All known script roots Blender is aware of
    for base in bpy.utils.script_paths():
        # /scripts/addons/io_scene_fbx
        candidates.append(os.path.join(base, "addons", "io_scene_fbx", "export_fbx_bin.py"))
        # /scripts/addons_core/io_scene_fbx
        candidates.append(os.path.join(base, "addons_core", "io_scene_fbx", "export_fbx_bin.py"))

    # 2. Resource paths (LOCAL, SYSTEM, USER) in case of weird setups
    for kind in ('LOCAL', 'SYSTEM', 'USER'):
        root = bpy.utils.resource_path(kind)
        if not root:
            continue

        scripts_root = os.path.join(root, "scripts")
        candidates.append(os.path.join(scripts_root, "addons", "io_scene_fbx", "export_fbx_bin.py"))
        candidates.append(os.path.join(scripts_root, "addons_core", "io_scene_fbx", "export_fbx_bin.py"))

    # 3. Check all candidates and return the first that actually exists
    for path in candidates:
        if os.path.isfile(path):
            return path

    # 4. If nothing found, give up
    return None


def comment_line_and_next_two(lines, start_idx):
    """
    Comment the line at start_idx and the next two lines.
    Keeps indentation and adds '#'.
    """
    for i in range(start_idx, min(start_idx + 3, len(lines))):
        stripped = lines[i].lstrip()
        # Already commented?
        if stripped.startswith("#"):
            continue

        leading_ws_len = len(lines[i]) - len(stripped)
        indent = lines[i][:leading_ws_len]
        lines[i] = indent + "#" + stripped
    return lines


def get_patch_status():
    """
    Returns (status, path) where status is one of:
    - 'NOT_FOUND'
    - 'ERROR'
    - 'ORIGINAL'
    - 'PATCHED'
    - 'MIXED'
    - 'UNKNOWN'
    """
    path = find_fbx_exporter_file()
    if not path:
        return "NOT_FOUND", None

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return "ERROR", path

    has_uncommented = any(
        TARGET_SUBSTRING in line and not line.lstrip().startswith("#")
        for line in lines
    )
    has_commented = any(
        TARGET_SUBSTRING in line and line.lstrip().startswith("#")
        for line in lines
    )

    if has_commented and not has_uncommented:
        return "PATCHED", path
    elif has_uncommented and not has_commented:
        return "ORIGINAL", path
    elif has_commented and has_uncommented:
        return "MIXED", path
    else:
        return "UNKNOWN", path


# -------------------------------------------------------------------
# Operators
# -------------------------------------------------------------------

class FBX_OT_root_bone_fix(bpy.types.Operator):
    """Patch export_fbx_bin.py to disable EMPTY/ARMATURE root export"""
    bl_idname = "t8tools.apply"
    bl_label = "Apply FBX Root Bone Fix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        path = find_fbx_exporter_file()
        if not path:
            self.report({'ERROR'}, "Could not find export_fbx_bin.py (io_scene_fbx).")
            return {'CANCELLED'}

        # Read file
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read file: {e}")
            return {'CANCELLED'}

        # Look for the target line
        target_index = -1
        for i, line in enumerate(lines):
            if TARGET_SUBSTRING in line and not line.lstrip().startswith("#"):
                target_index = i
                break

        if target_index == -1:
            # Maybe already patched?
            already_patched = any(
                TARGET_SUBSTRING in line and line.lstrip().startswith("#")
                for line in lines
            )
            if already_patched:
                self.report({'INFO'}, "File already appears to be patched.")
            else:
                self.report({'WARNING'}, "Target pattern not found. Blender version or script may have changed.")
            return {'CANCELLED'}

        # Make backup once
        backup_path = path + ".bak"
        if not os.path.exists(backup_path):
            try:
                shutil.copy2(path, backup_path)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to create backup: {e}")
                return {'CANCELLED'}

        # Comment the three lines
        lines = comment_line_and_next_two(lines, target_index)

        # Write back
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to write patched file: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, "FBX root bone fix applied. Restart Blender or reload the FBX add-on.")
        return {'FINISHED'}


class FBX_OT_root_bone_restore(bpy.types.Operator):
    """Restore original export_fbx_bin.py from backup"""
    bl_idname = "t8tools.restore"
    bl_label = "Restore FBX Root Bone File"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        path = find_fbx_exporter_file()
        if not path:
            self.report({'ERROR'}, "Could not find export_fbx_bin.py (io_scene_fbx).")
            return {'CANCELLED'}

        backup_path = path + ".bak"

        if not os.path.exists(backup_path):
            self.report({'ERROR'}, "No backup found (.bak). You must apply the fix at least once before restoring.")
            return {'CANCELLED'}

        try:
            shutil.copy2(backup_path, path)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to restore file: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, "Original FBX exporter file restored. Restart Blender or reload the FBX add-on.")
        return {'FINISHED'}


# -------------------------------------------------------------------
# UI (Object menu)
# -------------------------------------------------------------------

def menu_func(self, context):
    layout = self.layout
    col = layout.column()

    # Status display
    status, _path = get_patch_status()
    if status == "PATCHED":
        col.label(text="FBX Root Status: Patched", icon='CHECKMARK')
    elif status == "ORIGINAL":
        col.label(text="FBX Root Status: Original", icon='INFO')
    elif status == "NOT_FOUND":
        col.label(text="FBX Root Status: File not found", icon='ERROR')
    elif status == "ERROR":
        col.label(text="FBX Root Status: Error reading file", icon='ERROR')
    elif status == "MIXED":
        col.label(text="FBX Root Status: Mixed/Partial", icon='QUESTION')
    else:  # UNKNOWN
        col.label(text="FBX Root Status: Unknown", icon='QUESTION')

    col.separator()
    col.label(text="FBX Root Bone Fix:")
    col.operator(FBX_OT_root_bone_fix.bl_idname, icon='FILE_SCRIPT', text="Apply Fix")
    col.operator(FBX_OT_root_bone_restore.bl_idname, icon='LOOP_BACK', text="Restore Original")


classes = (
    FBX_OT_root_bone_fix,
    FBX_OT_root_bone_restore,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


