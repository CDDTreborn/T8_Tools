bl_info = {
    "name": "T8 Tools – Asset Packs",
    "author": "You + ChatGPT",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "3D Viewport > Sidebar > T8 Tools > Asset Packs",
    "description": "Download, install, and register asset pack libraries from zip files.",
    "category": "Asset",
}

import os
import zipfile
import urllib.request
import shutil

import bpy
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import (
    StringProperty,
    PointerProperty,
    CollectionProperty,
    BoolProperty,
)

# ------------------------------------------------------------------------
# CONFIG: Catalog of packs you want to distribute
# ------------------------------------------------------------------------

ASSET_PACK_CATALOG = [
    {
        "id": "female_basemesh",
        "name": "T8 Female Base Mesh",
        "version": "1.0",
        "url": "https://mega.nz/file/puti0YjR#PRO5Y3zjwF759AdyrEdBtzIY-XdCbkmy4KzW2KMqRLw",
        "description": "Female base mesh with MSL+PRP weights and shape keys for all non-special characters.",
        "library_name": "T8 Female Base Mesh",
        # If the extracted zip has a subfolder containing the .blend, put its name here.
        # If the .blend is directly in the root of the extracted folder, use "" instead.
        "inner_folder": "New_Female_BaseMesh",
    },

        {
        "id": "male_basemesh",
        "name": "T8 Male Base Mesh",
        "version": "1.0",
        "url": "https://mega.nz/file/A3cURYDb#WuQ8yIVkRZYlTgd-xG1FUB8ON9k5AgL8VsEuNZVlZ-s",
        "description": "Male base mesh with MSL+PRP weights and shape keys for all non-special characters.",
        "library_name": "T8 Male Base Mesh",
        # # If the extracted zip has a subfolder containing the .blend, put its name here.
        # # If the .blend is directly in the root of the extracted folder, use "" instead.
        "inner_folder": "New_Male_BaseMesh",
    },
]


def get_pack_by_id(pack_id: str):
    for item in ASSET_PACK_CATALOG:
        if item["id"] == pack_id:
            return item
    return None


# ------------------------------------------------------------------------
# Data models (Property Groups)
# ------------------------------------------------------------------------

class ASSET_PACK_PackState(PropertyGroup):
    """Tracks install status for a single pack."""
    pack_id: StringProperty(name="Pack ID")
    installed_version: StringProperty(name="Installed Version", default="")
    install_path: StringProperty(
        name="Install Path",
        subtype="DIR_PATH",
        default="",
    )


class ASSET_PACK_Settings(PropertyGroup):
    """All settings stored on the Scene (per .blend)."""
    install_root: StringProperty(
        name="Install Root",
        description=(
            "Folder where downloaded asset packs will be extracted. "
            "Each pack gets its own subfolder here."
        ),
        subtype="DIR_PATH",
        default="",
    )

    installed_packs: CollectionProperty(
        name="Installed Packs",
        type=ASSET_PACK_PackState,
    )

    debug_mode: BoolProperty(
        name="Debug Mode",
        default=False,
        description="Print extra info to the console",
    )


# Helpers to access settings + installed states
def get_settings(context):
    return context.scene.assetpack_settings


def find_state_for_pack(settings: ASSET_PACK_Settings, pack_id: str):
    for state in settings.installed_packs:
        if state.pack_id == pack_id:
            return state
    return None


def get_or_create_state(settings: ASSET_PACK_Settings, pack_id: str):
    state = find_state_for_pack(settings, pack_id)
    if state is None:
        state = settings.installed_packs.add()
        state.pack_id = pack_id
    return state


def debug_print(context, *args):
    settings = get_settings(context)
    if settings and settings.debug_mode:
        print("[AssetPacks]", *args)


# ------------------------------------------------------------------------
# Core functionality
# ------------------------------------------------------------------------

def ensure_dir(path: str):
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def _set_library_path(lib, library_root: str):
    """Set the directory/path on a UserAssetLibrary in a version-agnostic way."""
    if hasattr(lib, "directory"):
        lib.directory = library_root
    else:
        lib.path = library_root


def register_asset_library(pack_def: dict, library_root: str):
    """
    Register the given folder as an Asset Library in Blender preferences.
    Works across 3.6 and 4.x by probing the API instead of relying on version.
    """
    filepaths = bpy.context.preferences.filepaths
    library_name = pack_def.get("library_name") or pack_def["name"]

    # Find existing library by name (if any)
    existing = None
    for lib in filepaths.asset_libraries:
        if lib.name == library_name:
            existing = lib
            break

    if existing:
        # Just update its path/directory
        _set_library_path(existing, library_root)
    else:
        # Try the 4.x-style keyword first...
        try:
            new_lib = filepaths.asset_libraries.new(
                name=library_name,
                directory=library_root,
            )
        except TypeError:
            # ...fall back to the 3.x-style keyword.
            new_lib = filepaths.asset_libraries.new(
                name=library_name,
                path=library_root,
            )

        _set_library_path(new_lib, library_root)

    # Save user prefs so the library persists for all files
    try:
        bpy.ops.wm.save_userpref()
    except Exception as e:
        print("[AssetPacks] Could not save user preferences:", e)

def _get_library_path(lib):
    """Get the path/directory for a UserAssetLibrary in a version-agnostic way."""
    if hasattr(lib, "directory"):
        return lib.directory
    return lib.path


def unregister_asset_library(pack_def: dict, library_root: str):
    """
    Remove the asset library entry that points to this pack, if any.
    """
    filepaths = bpy.context.preferences.filepaths
    library_name = pack_def.get("library_name") or pack_def["name"]

    libs_to_remove = []

    for lib in filepaths.asset_libraries:
        if lib.name != library_name:
            continue

        lib_path = _get_library_path(lib)
        if lib_path:
            lib_abs = os.path.abspath(bpy.path.abspath(lib_path))
            root_abs = os.path.abspath(library_root)
            if lib_abs != root_abs:
                continue

        # This library matches by name and path – mark for removal
        libs_to_remove.append(lib)

    # Remove the actual UserAssetLibrary objects
    for lib in libs_to_remove:
        try:
            filepaths.asset_libraries.remove(lib)
        except TypeError:
            # Fallback for older API that expects index
            try:
                idx = list(filepaths.asset_libraries).index(lib)
                filepaths.asset_libraries.remove(idx)
            except Exception:
                pass

    if libs_to_remove:
        try:
            bpy.ops.wm.save_userpref()
        except Exception as e:
            print("[AssetPacks] Could not save user preferences (unregister):", e)



def extract_zip_to_folder(zip_path: str, dest_folder: str):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_folder)


def download_file_with_progress(url: str, dest_path: str, context):
    """
    Simple chunked download with basic progress in the status bar.
    This will work for standard HTTP/HTTPS direct links.
    MEGA links may require an external tool or manual download.
    """
    wm = bpy.context.window_manager
    wm.progress_begin(0, 100)

    try:
        with urllib.request.urlopen(url) as response, open(dest_path, 'wb') as out_file:
            total = response.length or 0
            read = 0
            chunk_size = 1024 * 256  # 256 KB

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                read += len(chunk)

                if total > 0:
                    progress = int((read / total) * 100)
                else:
                    progress = 0
                wm.progress_update(progress)
    finally:
        wm.progress_end()


# ------------------------------------------------------------------------
# Operators
# ------------------------------------------------------------------------

class ASSET_PACK_OT_download_install(Operator):
    """Download, extract, and register an asset pack from the catalog."""
    bl_idname = "asset_packs.download_install"
    bl_label = "Download & Install Pack"
    bl_options = {'REGISTER', 'UNDO'}

    pack_id: StringProperty()

    def execute(self, context):
        pack = get_pack_by_id(self.pack_id)
        if not pack:
            self.report({'ERROR'}, f"Unknown pack id: {self.pack_id}")
            return {'CANCELLED'}

        url = (pack.get("url") or "").lower()
        if "mega.nz" in url:
            self.report(
                {'ERROR'},
                "This pack is hosted on MEGA. Use 'Open Page' to download the zip, "
                "then 'Install From Zip' to install it."
            )
            return {'CANCELLED'}

        settings = get_settings(context)
        if not settings.install_root:
            self.report(
                {'ERROR'},
                "Install Root is not set. Please choose a folder first."
            )
            return {'CANCELLED'}

        install_root = bpy.path.abspath(settings.install_root)
        ensure_dir(install_root)

        pack_folder_name = pack["id"]
        pack_install_dir = os.path.join(install_root, pack_folder_name)
        ensure_dir(pack_install_dir)

        zip_path = os.path.join(pack_install_dir, pack["id"] + ".zip")

        self.report({'INFO'}, f"Downloading {pack['name']}...")
        debug_print(context, "Downloading from URL:", pack["url"])
        try:
            download_file_with_progress(pack["url"], zip_path, context)
        except Exception as e:
            self.report(
                {'ERROR'},
                f"Failed to download pack: {e}. "
                f"For MEGA links, please use 'Open Page' and 'Install From Zip' instead."
            )
            return {'CANCELLED'}

        self.report({'INFO'}, "Extracting pack...")
        try:
            extract_zip_to_folder(zip_path, pack_install_dir)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to extract zip: {e}")
            return {'CANCELLED'}
        finally:
            try:
                os.remove(zip_path)
            except OSError:
                pass

        inner_folder = pack.get("inner_folder") or ""
        if inner_folder:
            library_root = os.path.join(pack_install_dir, inner_folder)
        else:
            library_root = pack_install_dir

        library_root = os.path.abspath(library_root)

        register_asset_library(pack, library_root)

        state = get_or_create_state(settings, pack["id"])
        state.installed_version = pack["version"]
        state.install_path = library_root

        self.report({'INFO'}, f"Installed and registered: {pack['name']}")
        debug_print(context, "Installed at:", library_root)

        return {'FINISHED'}


class ASSET_PACK_OT_install_from_local_zip(Operator):
    """
    Fallback operator: user downloads the zip manually (e.g., from MEGA),
    then picks it here to extract + register.
    """
    bl_idname = "asset_packs.install_from_local_zip"
    bl_label = "Install From Local Zip"
    bl_options = {'REGISTER', 'UNDO'}

    pack_id: StringProperty()
    filepath: StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        pack = get_pack_by_id(self.pack_id)
        if not pack:
            self.report({'ERROR'}, f"Unknown pack id: {self.pack_id}")
            return {'CANCELLED'}

        settings = get_settings(context)
        if not settings.install_root:
            self.report(
                {'ERROR'},
                "Install Root is not set. Please choose a folder first."
            )
            return {'CANCELLED'}

        install_root = bpy.path.abspath(settings.install_root)
        ensure_dir(install_root)

        pack_folder_name = pack["id"]
        pack_install_dir = os.path.join(install_root, pack_folder_name)
        # If the pack is already installed, wipe the folder first so this acts as a clean reinstall
        if os.path.isdir(pack_install_dir):
            try:
                shutil.rmtree(pack_install_dir)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to clear existing install folder: {e}")
                return {'CANCELLED'}

        ensure_dir(pack_install_dir)

        self.report({'INFO'}, f"Extracting {pack['name']} from local zip...")
        try:
            extract_zip_to_folder(self.filepath, pack_install_dir)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to extract local zip: {e}")
            return {'CANCELLED'}

        inner_folder = pack.get("inner_folder") or ""
        if inner_folder:
            library_root = os.path.join(pack_install_dir, inner_folder)
        else:
            library_root = pack_install_dir

        library_root = os.path.abspath(library_root)

        register_asset_library(pack, library_root)

        state = get_or_create_state(settings, pack["id"])
        state.installed_version = pack["version"]
        state.install_path = library_root

        self.report({'INFO'}, f"Installed and registered: {pack['name']}")
        debug_print(context, "Installed at:", library_root)

        return {'FINISHED'}


class ASSET_PACK_OT_open_pack_url(Operator):
    """
    Opens the pack URL in the default web browser.
    Useful for MEGA links that can't be downloaded directly via urllib.
    """
    bl_idname = "asset_packs.open_pack_url"
    bl_label = "Open Pack Page in Browser"
    bl_options = {'INTERNAL'}

    pack_id: StringProperty()

    def execute(self, context):
        import webbrowser

        pack = get_pack_by_id(self.pack_id)
        if not pack:
            self.report({'ERROR'}, f"Unknown pack id: {self.pack_id}")
            return {'CANCELLED'}

        url = pack["url"]
        if not url:
            self.report({'ERROR'}, "Pack has no URL defined.")
            return {'CANCELLED'}

        webbrowser.open(url)
        self.report({'INFO'}, f"Opened browser for: {pack['name']}")
        return {'FINISHED'}

class ASSET_PACK_OT_uninstall(Operator):
    """Remove the installed files and asset library entry for a pack."""
    bl_idname = "asset_packs.uninstall"
    bl_label = "Uninstall Pack"
    bl_options = {'REGISTER', 'UNDO'}

    pack_id: StringProperty()

    def execute(self, context):
        pack = get_pack_by_id(self.pack_id)
        if not pack:
            self.report({'ERROR'}, f"Unknown pack id: {self.pack_id}")
            return {'CANCELLED'}

        settings = get_settings(context)
        if not settings.install_root:
            self.report(
                {'ERROR'},
                "Install Root is not set. Nothing to uninstall."
            )
            return {'CANCELLED'}

        install_root = bpy.path.abspath(settings.install_root)
        pack_folder = os.path.join(install_root, pack["id"])

        # Reconstruct library_root the same way we did during install
        inner_folder = pack.get("inner_folder") or ""
        if inner_folder:
            library_root = os.path.join(pack_folder, inner_folder)
        else:
            library_root = pack_folder
        library_root = os.path.abspath(library_root)

        # Remove asset library entry
        unregister_asset_library(pack, library_root)

        # Delete the installed files
        if os.path.isdir(pack_folder):
            try:
                shutil.rmtree(pack_folder)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to remove install folder: {e}")
                return {'CANCELLED'}

        # Remove state entry
        idx_to_remove = None
        for i, state in enumerate(settings.installed_packs):
            if state.pack_id == pack["id"]:
                idx_to_remove = i
                break
        if idx_to_remove is not None:
            settings.installed_packs.remove(idx_to_remove)

        self.report({'INFO'}, f"Uninstalled pack: {pack['name']}")
        debug_print(context, "Uninstalled pack folder:", pack_folder)
        return {'FINISHED'}

# ------------------------------------------------------------------------
# UI Panel
# ------------------------------------------------------------------------

class ASSET_PACK_PT_panel(Panel):
    ...
    def draw(self, context):
        ...
class ASSET_PACK_PT_panel(Panel):
    bl_idname = "ASSET_PACK_PT_panel"
    bl_label = "Asset Packs"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "T8 Tools"

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw(self, context):
        layout = self.layout
        settings = get_settings(context)

        col = layout.column(align=True)
        col.label(text="Install Root:")
        col.prop(settings, "install_root", text="")

        col.separator()
        col.prop(settings, "debug_mode", text="Debug Mode")

        col.separator()
        col.label(text="Available Packs:")

        if not ASSET_PACK_CATALOG:
            col.label(text="No packs defined in catalog.", icon='INFO')
            return

        for pack in ASSET_PACK_CATALOG:
            box = col.box()
            row = box.row()
            row.label(text=pack["name"])
            row.label(text=f"v{pack['version']}")

            state = find_state_for_pack(settings, pack["id"])
            installed = state is not None and state.install_path and os.path.isdir(
                bpy.path.abspath(state.install_path)
            )

            status_row = box.row()
            if installed:
                status_row.label(text="Status: Installed", icon='CHECKMARK')
            else:
                status_row.label(text="Status: Not installed", icon='ERROR')

            if pack.get("description"):
                box.label(text=pack["description"], icon='DOT')

            # Detect MEGA links
            url_lower = (pack.get("url") or "").lower()
            is_mega = "mega.nz" in url_lower

            btn_row = box.row(align=True)

            if not is_mega:
                op_dl = btn_row.operator(
                    ASSET_PACK_OT_download_install.bl_idname,
                    text="Download & Install",
                )
                op_dl.pack_id = pack["id"]
            else:
                btn_row.label(text="MEGA-hosted pack")

            # If already installed, this acts as "Reinstall From Zip"
            local_label = "Reinstall From Zip" if installed else "Install From Zip"
            op_local = btn_row.operator(
                ASSET_PACK_OT_install_from_local_zip.bl_idname,
                text=local_label,
            )
            op_local.pack_id = pack["id"]

            op_browser = btn_row.operator(
                ASSET_PACK_OT_open_pack_url.bl_idname,
                text="Open Page",
            )
            op_browser.pack_id = pack["id"]

            # Extra row for uninstall when installed
            if installed:
                row_un = box.row(align=True)
                op_un = row_un.operator(
                    ASSET_PACK_OT_uninstall.bl_idname,
                    text="Uninstall Pack",
                )
                op_un.pack_id = pack["id"]




            if installed and state:
                box.label(text=f"Path: {state.install_path}", icon='FILE_FOLDER')


# ------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------

classes = (
    ASSET_PACK_PackState,
    ASSET_PACK_Settings,
    ASSET_PACK_OT_download_install,
    ASSET_PACK_OT_install_from_local_zip,
    ASSET_PACK_OT_open_pack_url,
    ASSET_PACK_OT_uninstall,          # <-- add this
    ASSET_PACK_PT_panel,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.assetpack_settings = PointerProperty(
        type=ASSET_PACK_Settings
    )


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)

    del bpy.types.Scene.assetpack_settings