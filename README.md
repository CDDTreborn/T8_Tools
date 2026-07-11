# T8 Tools

T8 Tools is a Blender add-on for Tekken 8 asset preparation, texture baking, mesh cleanup, rig workflows, shader IDs, and FBX export support.

## Highlights

- Channel-packed RMA, MRA, OBD, and TSE baking
- Color, normal, diffuse, and two-pass ID baking
- Batch baking to PNG
- Consolidated UV packing
- Active-to-selected weight transfer
- Duplicate material cleanup
- Scene-wide modifier pause and restore
- MSL and PRP rig parenting and FBX export
- Recursive material-image collection
- Rig pose matching
- Multires sculpt-transfer pipeline
- Bone-name mapping with JSON presets
- Shape-key-driven bone alignment
- Sixteen-mask, four-channel ID shader system
- Shader profile and node-group template JSON tools
- Optional FBX root-bone exporter patch

## Requirements

- Blender 3.6 or newer according to the add-on metadata
- A tested Blender version is strongly recommended for each release
- Cycles support for Texture Baker

## Installation

1. Download the release ZIP from GitHub Releases.
2. In Blender, open **Edit → Preferences**.
3. Use **Install** or **Install from Disk** and select the ZIP without extracting it.
4. Enable **T8 Tools**.
5. Open the 3D Viewport sidebar with **N** and choose the **T8 Tools** tab.

Shader tools appear in the Shader Editor sidebar under **ID System** and **Shader Profile**.

## Documentation

See [`T8_Tools_User_Manual.md`](T8_Tools_User_Manual.md) for installation, workflows, warnings, and troubleshooting.

## Safety

Some operations are destructive or alter Blender installation files. Save a backup before:

- Clearing destination weights
- Applying bone renames
- Moving edit bones
- Rebuilding the multires pipeline
- Rebinding meshes for export
- Applying the FBX exporter patch

## Bug reports

Include:

- T8 Tools release tag
- Blender version
- Operating system
- Exact reproduction steps
- Screenshot of the selection and panel
- System-console output
- A minimal sample file when permitted

## Credits

Developed by CDDT Reborn with iterative development assistance from ChatGPT.
