# T8 Tools for Blender

## User Manual

**Add-on:** T8 Tools  
**Declared add-on version:** 1.0.0  
**Declared minimum Blender version:** 3.6  
**Primary location:** 3D Viewport → Sidebar → **T8 Tools**  
**Shader tools:** Shader Editor → Sidebar → **ID System** or **Shader Profile**  
**FBX patch:** 3D Viewport → Object menu

> **Important:** Several tools modify meshes, materials, rigs, modifiers, Blender installation files, or export bindings. Save the `.blend` file before using destructive operations. For rig renaming, shape-key bone alignment, multires commits, and FBX exporter patching, use a backup copy.

---

# 1. What T8 Tools Does

T8 Tools is a Blender add-on aimed at Tekken 8 asset preparation and general character-mod workflow cleanup. It combines baking, UV, material, rigging, shader, image, and FBX utilities in one sidebar.

The current suite includes:

- Texture and channel-packed map baking
- Batch map baking to PNG
- Consolidated UV creation and packing
- Active-to-selected weight transfer
- Duplicate material cleanup
- Scene-wide modifier pausing and restoration
- Rig parenting and controlled MSL/PRP FBX export
- Recursive image collection from materials and node groups
- Material blend-mode switching
- Pose matching between compatible rigs
- A multires sculpt-transfer workflow
- Bone-name mapping and JSON presets
- Shape-key-driven bone alignment
- A 16-mask, four-channel ID painting system
- Shader profile JSON files
- Shader node-group template scanning, export, rebuild, and validation
- An optional Blender FBX root-bone exporter patch

---

# 2. Installation

## 2.1 Install the release ZIP

1. Download the release ZIP named similar to:

   `T8_Tools-v1.x.x.zip`

2. In Blender, open **Edit → Preferences**.
3. Open the add-on installation area. Depending on Blender version, this may be labeled **Add-ons**, **Install**, or **Install from Disk**.
4. Select the ZIP without extracting it.
5. Enable **T8 Tools**.
6. Close Preferences.
7. In the 3D Viewport, press **N** to open the sidebar.
8. Open the **T8 Tools** tab.

The ZIP must contain one top-level folder named `T8_Tools`, with `__init__.py` directly inside that folder.

## 2.2 Updating

For a clean update:

1. Save and close active Blender projects.
2. Disable the old T8 Tools version.
3. Remove the old add-on version.
4. Install the new release ZIP.
5. Re-enable T8 Tools.
6. Restart Blender if panels or operators appear stale.

Avoid copying a new release over an older folder while Blender is open. Python bytecode and loaded modules can linger like glitter in carpet.

## 2.3 Tool-group preferences

The add-on preferences include switches for:

- Baking Tools
- Quick Tools
- Image Tools
- Mesh Tools
- Rig Tools
- ID System and Shader Editor tools
- FBX Root Bone Fix

These switches control which modules register when the add-on loads. After changing them, disable and re-enable the add-on or restart Blender so the panel set refreshes correctly.

---

# 3. Interface Map

## 3.1 3D Viewport sidebar

Press **N**, then open **T8 Tools**.

The main categories are:

### Baking Tools

- Texture Baker
- Batch Map Baking

### Quick Tools

- Consolidate UVs
- Quick Weight Transfer
- Duplicate Material Cleanup
- Modifier Pause
- Rig Parent / Export

### Image Tools

- Collect Images From Selected

### Mesh Tools

- Blend Mode Switch
- Rig Matcher
- Multires Pipeline

### Rig Tools

- Bone Mapper
- Shape Key Bone Align

## 3.2 Shader Editor sidebar

In the Shader Editor, press **N**.

- **ID System** tab: ID mask setup, painting, ID Core, and mix helpers
- **Shader Profile** tab: profile JSON and shader-template tools

## 3.3 Object menu

In the 3D Viewport, open **Object** to find the FBX Root Bone Fix controls and status.

---

# 4. General Working Rules

## 4.1 Selection matters

Many T8 Tools operators use Blender’s selected objects and active object differently.

- **Selected objects** are outlined.
- The **active object** is the most recently selected object and has the brighter outline.
- For source-to-target tools, the active object is often the source.

Read each workflow’s selection order before pressing the button.

## 4.2 Save before destructive tools

Use **File → Save As** to create a checkpoint before:

- Clearing destination vertex groups
- Applying bone renames
- Moving edit bones
- Rebuilding a multires object
- Rebinding meshes to MSL or PRP rigs
- Applying the FBX exporter patch

## 4.3 Watch Blender’s status messages

Most tools report success, warnings, or errors in Blender’s status area. Advanced tools also print detailed reports to the system console.

On Windows, use **Window → Toggle System Console** when a manual section says to inspect the console.

---

# 5. Baking Tools

# 5.1 Texture Baker

## Purpose

Texture Baker builds temporary nodes around the selected meshes’ materials, gathers the requested shader data, and bakes it into a shared image named after the active mesh.

## Requirements

- Select one or more mesh objects.
- Make the intended naming mesh active.
- Each relevant material should use nodes.
- Most map types expect a Principled BSDF and Material Output.
- The meshes need usable UVs.
- Cycles baking must be supported by the current Blender setup.

The tool temporarily switches the render engine to Cycles and temporarily uses four Cycles samples. It disables Selected to Active during its bake.

## Map types

| Type | Packed channels or result | Output suffix |
|---|---|---|
| RMA | Roughness → R, Metallic → G, AO → B | `_RMA` |
| MRA | Metallic → R, Roughness → G, AO → B | `_MRA` |
| OBD | Alpha → R, G and B = 0 | `_OBD` |
| TSE | R = 0, Specular or Specular IOR → G, Emission → B | `_TSE` |
| Normal | Blender normal bake | `_N` |
| Color (PC) | Base Color with material alpha | `_PC` |
| ID | Two passes from ID Core: RGB ID and Alpha ID | `_C_ID`, `_A_ID` |
| Diffuse / Grey | Base Color, optionally converted to grayscale | `_C` |

## Single-map workflow

1. Select all mesh objects that should contribute to the same texture.
2. Make the mesh that should control the output filename active.
3. Open **T8 Tools → Baking Tools → Texture Baker**.
4. Choose the map type.
5. Set Width and Height.
6. Configure map-specific options.
7. Optionally click **Build / Refresh Setup** to inspect the temporary nodes before baking.
8. Click **Bake**.
9. Inspect the generated image in the Image Editor.
10. Save the image manually if using the single-bake workflow.
11. Click **Clear Temporary Nodes** when finished.

## AO settings

For RMA and MRA, the tool first looks for an existing Ambient Occlusion node in each material.

When **Generate AO if Missing** is enabled, it creates a temporary AO node using:

- AO Samples
- AO Inside
- AO Only Local
- AO Distance

When AO is unavailable and generation is disabled, the blue channel is filled with `1.0`.

## Diffuse grayscale

When **Diffuse: Convert to Grayscale** is enabled, the add-on adds a temporary Hue/Saturation node with saturation at zero and a Bright/Contrast adjustment before the emit bake.

## ID baking

The ID bake runs two passes:

1. `RGB_ID` from the material’s ID Core is baked to `<ActiveMesh>_C_ID`.
2. `Alpha_ID` is converted to grayscale and baked to `<ActiveMesh>_A_ID`.

When the expected ID Core is missing, the tool falls back to Base Color for the color pass and Principled Alpha for the alpha pass. This fallback prevents a hard failure, but it is not equivalent to a properly configured ID System.

## Temporary nodes

Temporary baking nodes use the prefix `TB_TEMP_`. **Clear Temporary Nodes** removes those nodes and attempts to reconnect the first non-temporary Principled BSDF to Material Output.

Because material graphs can be complex, inspect unusual custom shaders after cleanup.

## Common problems

### “No Principled BSDF”

The material uses a custom shader without a top-level Principled BSDF. Add or expose a suitable Principled node, or bake that material manually.

### Blank or overlapping bake

Check that:

- The target UV map is active.
- UV islands are inside the 0–1 tile.
- The generated image node is active in each material.
- Selected meshes do not unintentionally overlap in UV space.

### Output is not on disk

The single Bake button creates or updates a Blender image datablock. Save it from the Image Editor. Use Batch Map Baking when automatic PNG saving is preferred.

---

# 5.2 Batch Map Baking

## Purpose

Batch Map Baking runs the existing Texture Baker once per selected map type and saves each generated image as PNG in a chosen folder.

ID maps are intentionally excluded from batch mode.

## Workflow

1. Prepare the meshes exactly as for a single Texture Baker run.
2. Open **Batch Map Baking**.
3. Enable the desired maps:
   - RMA
   - MRA
   - OBD
   - TSE
   - PC
   - Diffuse
   - Normal
4. Click **Batch Bake to Folder...**.
5. Choose an output folder.
6. Allow the sequence to finish.

Files are named from the active mesh, for example:

- `Hair_RMA.png`
- `Hair_PC.png`
- `Hair_N.png`

Batch order is RMA, MRA, OBD, TSE, PC, Diffuse, then Normal.

---

# 6. Quick Tools

# 6.1 Consolidate UVs

## Purpose

Creates or reuses a UV layer on every selected mesh, makes that layer active, then performs multi-object island scaling and packing.

## Workflow

1. Select the mesh objects to place in one consolidated UV layout.
2. Open **Quick Tools → Consolidate UVs**.
3. Enter the UV layer name. Default: `Consolidated`.
4. Choose whether to override an existing layer with that exact name.
5. Click **Create / Pack UVs**.

The packing sequence:

- Enters multi-object Edit Mode
- Reveals geometry
- Selects all faces and UVs
- Averages island scale
- Packs without rotation
- Uses approximately `0.003` scaled margin
- Restores the earlier selection, active object, and mode where possible

## Override Existing

- **Enabled:** Reuses the named layer when it exists, or creates it when missing.
- **Disabled:** Always creates a new layer. Blender may add `.001`, `.002`, and similar suffixes.

## Warning

This is a packing tool, not an atlas-material merger. It does not combine materials or rewrite texture assignments.

---

# 6.2 Quick Weight Transfer

## Purpose

Transfers all vertex-group weights from the active source mesh to every other selected mesh using an applied Data Transfer modifier.

## Selection order

1. Select one or more destination meshes.
2. Select the source mesh last so it becomes active.
3. Confirm that the active source contains vertex groups.

## Settings

### Clear Dest Weights First

Deletes every vertex group on each destination before transfer. This is destructive but produces the most predictable replacement.

### Vertex Mapping

- **Nearest Vertex:** Uses the closest source vertices.
- **Nearest Face Interp:** Interpolates weights from nearby source faces. This is the default and usually the best choice for similar but non-identical garments.
- **Topology:** Requires matching topology and ordering.

### Mix Mode

- Replace
- Add
- Subtract

When **Clear Dest Weights First** is enabled, Replace is the logical default.

### Ray Radius

Search distance in Blender units. Increase it when distant sections receive no useful weights.

### Object Transform

Accounts for object transforms during transfer.

### By Name

Attempts to match vertex groups by name. Recommended for Tekken rigs.

## Workflow

1. Save a backup when destination groups matter.
2. Select destination mesh or meshes.
3. Select the weighted source mesh last.
4. Open **Quick Weight Transfer**.
5. Choose mapping and cleanup settings.
6. Click **Transfer Active → Selected**.
7. Test deformation in Pose Mode.

The temporary Data Transfer modifier is applied, so it does not remain in the modifier stack.

---

# 6.3 Duplicate Material Cleanup

## Purpose

Replaces numbered Blender duplicates such as `Body.001` or `Hair.003` with their unsuffixed base materials when those base materials exist.

## Workflow

1. Select the affected mesh objects.
2. Click **Remap Duplicates → Base**.
3. Review the confirmation list.
4. Confirm the operation.

Example:

`Skin.002` → `Skin`

The tool only changes material slots on selected meshes. It does not delete unused material datablocks afterward. Use Blender’s orphan-data cleanup separately when needed.

---

# 6.4 Modifier Pause

## Purpose

Snapshots modifier visibility states across the entire scene, then disables selected visibility targets to improve viewport or render performance. The snapshot can later restore the previous state.

## Scope

Modifier Pause affects **all objects in the current scene**, not only selected objects.

## Settings

- **Affect Viewport:** Controls `show_viewport`.
- **Affect Render:** Controls `show_render`.
- **Excluded Modifier Types:** Modifiers that remain enabled.

## Workflow

1. Choose whether to affect viewport, render, or both.
2. Select any modifier types that should remain active.
3. Click **Snapshot & Pause Modifiers**.
4. Work with the lighter scene.
5. Click **Restore Modifiers** to restore the stored states.

The snapshot uses object and modifier names. Renamed or deleted objects and modifiers are skipped during restoration.

## Exclusion presets

1. Set the current excluded modifier types.
2. Click **Add from Current Exclusions**.
3. Name the preset.
4. Enter or select the preset name later.
5. Click **Apply**.

Presets are stored in the `.blend` scene data, not as separate portable files.

## Caution

Creating a new snapshot replaces the previous snapshot. Restore before taking another snapshot when the earlier state still matters.

---

# 6.5 Rig Parent / Export

## Purpose

Parents selected meshes to designated MSL or PRP armatures and exports controlled FBX files using the user’s last-used FBX settings while forcing two required options:

- Selected Objects
- Apply Modifiers

During export, each selected mesh is guaranteed to have exactly one Armature modifier pointing to the chosen rig.

## Scene-unit precheck

The tool expects:

- Unit System: Metric
- Unit Scale: `0.01`
- Length: Centimeters

When **Stop on unit mismatch** is disabled, mismatches produce a warning. When enabled, export is blocked.

## Initial setup

1. Assign the **MSL Rig**.
2. Assign the **PRP Rig**.
3. Choose an Export Folder.
4. Choose overwrite behavior.
5. Set scene units.

When no export folder is specified:

- A saved `.blend` uses a folder named `UE_Ready` beside the blend file.
- An unsaved file uses `UE_Ready` in the user home folder.

## First export in a Blender session

The tool needs Blender’s last-used FBX options.

1. Select the mesh or meshes to export.
2. Make the intended filename mesh active.
3. Click **Export MSL** or **Export PRP**.
4. The normal Blender FBX dialog opens.
5. Configure the remaining FBX settings and complete that export.

After this initialization, later exports use the last-used settings automatically while still forcing Selected Objects and Apply Modifiers.

## Manual parenting

The **→ MSL** and **→ PRP** buttons parent selected meshes to the selected rig.

Options:

- **Keep Transform on Unparent:** Preserves world transform when clearing an old parent.
- **Remove Armature Modifiers:** Removes old Armature modifiers before manual reparenting.

Even if the manual-removal option is disabled, the export path itself removes existing Armature modifiers and creates one clean modifier for the export rig.

## Single-rig export

1. Select one or more mesh objects. The rig does not need to be selected.
2. Make the mesh that should provide the filename active.
3. Click **Export MSL** or **Export PRP**.

Naming:

- `<ActiveMesh>_MSL.fbx`
- `<ActiveMesh>_PRP.fbx`

The selected meshes are rebound to the chosen rig before export.

## Export Both

1. Initialize FBX settings with a single export first.
2. Assign both rigs.
3. Select the meshes.
4. Click **Export Both (MSL→PRP)**.

The tool exports MSL first and PRP second. Afterward, the meshes remain bound to the PRP rig because that is the final pass.

## Important caution

Export is not merely a passive save operation. It clears and rebuilds Armature modifiers and parents selected meshes to the export rig. Save the project first when the current binding must be preserved.

---

# 7. Image Tools

# 7.1 Collect Images From Selected

## Purpose

Finds all image textures used by materials on selected meshes, including images inside nested node groups, then copies or saves them into one folder.

## Workflow

1. Select the relevant mesh objects.
2. Open **Image Tools**.
3. Click **Collect Images From Selected (Choose Folder)**.
4. Choose a destination folder.

## File handling

- Existing external image files are copied with their original filenames.
- Packed or generated Blender images are saved as PNG.
- Duplicate image datablocks are processed once.
- Node groups are scanned recursively.

## Caution

Saving a packed or generated image changes its Blender filepath and file format to the new PNG destination. Save a backup when existing image-path behavior matters.

When two different source images share the same filename, the later copy can overwrite the earlier file in the chosen folder.

---

# 8. Mesh Tools

# 8.1 Blend Mode Switch

## Purpose

Applies one material blend mode to all material slots on selected mesh objects.

Available modes:

- Opaque
- Alpha Clip
- Alpha Hashed
- Alpha Blend

## Workflow

1. Select the mesh objects.
2. Choose a blend mode.
3. Click **Apply to Selected**.

The tool updates material datablocks. If the same material is shared by unselected objects, those objects also display the changed material behavior.

---

# 8.2 Rig Matcher

## Purpose

Matches destination pose bones to source pose bones by name, copying world-space location and rotation without copying overall scale.

An optional mode adjusts destination pose-bone Y scale to approximate source pose length.

## Requirements

- Source and destination must be different armature objects.
- Bones are matched by exact name.
- This changes pose transforms, not edit-bone rest positions.

## Pose-matching workflow

1. Set **Source Rig**.
2. Set **Destination Rig**.
3. Enable **Match Bone Length** only when needed.
4. Click **Match Pose (No Scale)**.
5. Inspect the destination pose.

Length matching is clamped to a scale range of approximately `0.3` to `3.0` to reduce extreme results.

## Bone Relations Tools

This secondary operator works on selected armatures and can:

- Disconnect connected child bones in Edit Mode.
- Set Inherit Scale to None on deform bones.

Workflow:

1. Select the armature or armatures.
2. Enable the desired relation options.
3. Click **Apply Bone Relations to Selected Rigs**.

This modifies rig structure settings. Use a backup.

---

# 8.3 Multires Pipeline

## Purpose

Builds a controlled A0/B/C workflow for transferring sculpted form into a multires object using Surface Deform and Multires Reshape.

## Object roles

- **A:** User-selected base mesh.
- **A0:** Hidden full copy of the original base.
- **B:** Multires object that receives the committed sculpt and is used for baking.
- **C:** Sculpt target.
- **D:** Temporary applied duplicate created during Commit, then deleted.

## Setup workflow

1. Select **Base Mesh (A)** in the panel.
2. Choose the number of Multires Levels.
3. Click **Setup Multires Pipeline**.
4. The tool creates or refreshes A0, B, and C.
5. Sculpt or edit **C**.
6. Do not delete B’s `T8_SurfaceDeform` before committing.
7. Click **Commit Sculpt to B (Reshape Multires)**.

During setup:

- A0 is created once and hidden.
- Existing B and C objects recorded by the panel are deleted and rebuilt.
- B receives Multires.
- C is duplicated from B.
- B receives a Surface Deform modifier bound to C.
- B is hidden so C is easier to sculpt.

## Commit

Commit:

1. Makes B and C visible.
2. Duplicates B to a temporary D object.
3. Applies all modifiers on D.
4. Uses D to reshape B’s Multires data.
5. Deletes D.
6. Removes B’s Surface Deform modifier.

## Prep Bake Material

1. Choose 2K, 4K, or 8K.
2. Set the Bake Image Name.
3. Set the Bake Material name.
4. Click **Prep Bake Material (on B)**.

The tool creates or reuses a non-color image and material, assigns the material to B, and makes the image node active. It does not execute the normal bake itself.

## Caution

Running Setup again deletes the previously recorded B and C objects and creates new ones. Preserve finished sculpt work before rebuilding.

---

# 9. Rig Tools

# 9.1 Bone Mapper

## Purpose

Renames bones on a custom rig to match names from a target Tekken/reference rig. Mapping lists can be saved to and loaded from JSON.

## Terms

- **Custom Rig:** The rig whose bones will be renamed.
- **Target Rig:** The reference rig supplying desired names.
- **Custom Bone:** Existing source name.
- **Rename To:** Desired target name.

## Manual mapping workflow

1. Set Custom Rig and Target Rig.
2. Click **Add Mapping**.
3. Choose the Custom bone.
4. Choose the target name under **Rename To**.
5. Repeat for each bone.
6. Click **Validate Mapping**.
7. Resolve all errors.
8. Save the `.blend` and preferably a mapping preset.
9. Click **Apply Bone Renames**.
10. Confirm the destructive action.

## Add mappings from selected bones

1. Set Custom Rig.
2. Make it active.
3. Enter Edit Mode or Pose Mode.
4. Select the source bones.
5. Click **Add Mapping From Selection**.
6. Return to the panel and assign each target name.

Existing custom-bone rows are skipped.

## Validation checks

Validation marks rows invalid when:

- Custom bone is missing.
- Target bone is missing.
- A name is absent from the selected rig.
- Source and target already match.
- The same custom bone appears more than once.
- Multiple rows request the same target name.
- The requested target name already exists on the custom rig.

Only valid rows are renamed.

## Presets

Default preset path:

`//bone_mapping_preset.json`

The `//` prefix means relative to the saved `.blend` location.

Preset workflow:

1. Set the Preset File path.
2. Click **Save Preset**.
3. In another session or file, assign Custom and Target rigs.
4. Set the same preset path.
5. Click **Load Preset**.
6. Validate before applying.

The preset stores mapping names and rig-name hints. It does not include armature data.

## Select Mapped Bones

This button enters Edit Mode on the Custom Rig and selects bones using the custom name first, then the target name. It remains useful before and after renaming.

---

# 9.2 Shape Key Bone Align

## Purpose

Measures how weighted vertex clusters move between two shape-key states, then moves matching edit bones by the measured world-space deltas.

This is designed for cases where a body or face shape key changes mesh proportions but the rig must be repositioned to follow the new form.

## Requirements

- One armature.
- One mesh with shape keys.
- Vertex groups whose names match bone names, optionally with a prefix or suffix.
- Sensible weights around the body region controlled by each bone.

## Recommended safe workflow

1. Duplicate the armature or save a new `.blend` version.
2. Select the armature and mesh.
3. Click **Auto Fill From Selection**.
4. Choose Source Shape Key and Target Shape Key.
5. Select only the bones that should move.
6. Keep **Only Selected Bones** enabled.
7. Click **Dry Run / Preview**.
8. Review the popup and system-console report.
9. Reduce Max Move Distance or narrow the Bone Filter when any delta looks suspicious.
10. Click **Apply Delta Alignment**.
11. Inspect bone positions in Edit Mode and test deformation.

## Shape-key states

- **Source Strength:** Source state value. Default `0.0`.
- **Target Strength:** Target state value. Default `1.0`.
- **Keep Source Active In Target:** Measures Source + Target rather than Target alone.
- **Zero Other Shape Keys:** Temporarily zeros unrelated keys while measuring.
- **Restore Shape Keys:** Restores original values afterward.

## Bone scope

### Only Selected Bones

Restricts processing to selected bones. Recommended.

### Auto Include Parents

Adds parent bones up to the selected Parent Depth so child clusters do not drift away from their hierarchy.

### Child-delta fallback

When a scoped parent has no useful matching vertex group, it can inherit an averaged delta from ready descendants. Child Depth controls the search depth.

### Bone Filter

Processes only bone names containing the entered text, such as `jaw`, `eye`, or `clavicle`.

### VG Prefix and Suffix

Changes the vertex-group lookup pattern:

`<Prefix><BoneName><Suffix>`

## Delta settings

- **Weight Threshold:** Minimum vertex-group weight used in the cluster. Default `0.80`.
- **Minimum Vertices:** Minimum qualifying cluster size. Default `3`.
- **Use Weighted Average:** Stronger weights influence the measured center more.
- **Minimum Move:** Ignores tiny deltas.
- **Limit Max Move:** Clamps large deltas.
- **Max Move Distance:** Default `0.15` world units.
- **Invert Delta:** Moves opposite the measured change.

## Apply options

- **Heads:** Moves bone heads.
- **Tails:** Moves bone tails by the same delta.

With both enabled, length and direction are preserved while the entire bone translates. Moving only one endpoint changes length or orientation.

## Dry-run report statuses

Common statuses include:

- `ready`
- `ready_child_fallback`
- `missing_group`
- `too_few_vertices`
- `bad_center`
- `below_min_move`

The console report includes vertex count, delta vector, delta length, clamping, automatic parent inclusion, and fallback descendants.

---

# 10. Shader Editor Tools

# 10.1 ID System

## Purpose

Creates a per-material ID-mask system with up to sixteen logical IDs packed into four final channels.

Global ID layout:

| Final channel | IDs |
|---|---|
| Red | 1–4 |
| Green | 5–8 |
| Blue | 9–12 |
| Alpha | 13–16 |

Each logical ID initially receives its own 4096 × 4096 paint image. The ID Core converts the enabled masks into packed RGB and Alpha outputs.

## Basic setup

1. Open the Shader Editor.
2. Make the intended material active.
3. Press **N** and open **ID System**.
4. Click **Initialize ID Masks**.
5. Enable only the logical IDs needed by this material.
6. Click **Build / Refresh Split Number & ID Core**.

Initialization creates:

- Sixteen image texture nodes
- Images named `<Material>_ID01` through `<Material>_ID16`
- An `ID System` frame
- A per-material ID Core node group

## Channel split values

The displayed split number is the count of enabled IDs in R, G, B, and A. Example:

`2 1 0 0`

means two IDs are packed into Red, one into Green, and none into Blue or Alpha.

## Per-channel level presets

The ID Core uses fixed grayscale levels based on the number of active IDs within a channel:

| Active IDs in channel | Levels |
|---|---|
| 1 | 1.0 |
| 2 | 0.05, 1.0 |
| 3 | 0.08, 0.397, 1.0 |
| 4 | 0.05, 0.212, 0.521, 1.0 |

Enable only the IDs actually used, because the level assigned to an ID depends on the channel’s active count.

## Painting an ID

1. Choose an Active Paint ID.
2. Choose a Paint Color for preview.
3. Click **Set Active Paint ID**.
4. Blender switches the selected mesh to Texture Paint mode when possible.
5. The matching ID image becomes the paint canvas and is shown in open Image Editors.
6. Paint white where the ID should exist and black where it should not.

The preview shader mixes the original Base Color with the selected preview color using the ID image as factor.

To exit ID preview:

1. Set Paint ID to **None**.
2. Click **Set Active Paint ID** again.

The tool clears the paint canvas, removes temporary preview nodes, and attempts to restore the previous material output.

## Saving masks

ID mask images are Blender image datablocks. Save or pack them before closing Blender. The Image Tools collector can also export generated images to PNG.

## ID Mix (Color)

Creates a node group that starts with a Base color and blends one to four ID-specific colors using masks from ID Core.

Workflow:

1. Build the ID Core.
2. Click **Add ID Mix (Color)**.
3. Choose one to four logical IDs.
4. Confirm.
5. Connect Base and each ID color input.
6. Connect Result to the desired shader input.

Mask connections are made automatically from ID Core.

## ID Mix (Normal)

Creates a normal-combination group for one to four logical IDs.

For Base and each selected ID it provides:

- Normal Color input
- Space switch, where `0` is OpenGL and `1` is DirectX
- Automatic mask input from ID Core

The group converts textures with Normal Map nodes and blends normal vectors through the selected masks.

## Texture Baker integration

The Texture Baker’s ID mode searches for a node group named:

`ID_Core__<MaterialName>`

and reads:

- `RGB_ID`
- `Alpha_ID`

Renaming or replacing that group can cause fallback baking instead of proper ID output.

---

# 10.2 Shader Profile Builder

## Purpose

The Shader Profile Builder contains two related systems:

1. **Shader Profiles:** JSON descriptions of how texture names and channels map to standard shader elements.
2. **Shader Templates:** Deep scans of node groups that can be exported, loaded, experimentally rebuilt, and validated.

The current code stores profile definitions and template structures. It does not yet present a one-click operator that automatically builds a complete material from a folder of textures.

## Shader Profiles

### Initialize defaults

1. Open the Shader Editor sidebar.
2. Open **Shader Profile → Shader Profiles**.
3. Under Profile Management, enter a profile name.
4. Click **Initialize Default Elements**.

Default elements include:

- Base Color
- Ambient Occlusion
- Roughness
- Metallic
- Specular
- Normal
- Alpha
- Emission

Each element includes:

- Enabled state
- Source type: Texture, Value, or Disabled
- Channel: RGB, R, G, B, or A
- Color space: sRGB or Non-Color
- Alpha mode
- Fallback/value
- Texture-name identifier rules
- Optional preview image

### Identifier rules

A rule can match texture names by:

- Suffix
- Prefix
- Contains
- Exact

Examples:

- `_D` as Suffix
- `_Normal` as Suffix
- `rough` as Contains

Use multiple identifiers when different tools or artists use different naming conventions.

### Save and load profile JSON

1. Set Profile Name.
2. Adjust elements and identifiers.
3. Click **Save Profile JSON**.
4. Choose a location.

Use **Load Profile JSON** to restore the profile.

Preview images are references for inspection and are not embedded in the profile JSON.

## Shader Templates

### Scan active material

1. Make an object active.
2. Assign and activate the material to inspect.
3. Click **Scan Active Material Groups**.

The scanner records direct and nested node groups, including:

- Group name
- Instance node name
- Nesting depth
- Inputs and outputs
- Node count
- Nested-group count

### Save Template JSON

1. Scan the active material.
2. Set Template JSON Path or use the file picker.
3. Optionally enable **Export Template Resources**.
4. Click **Save Template JSON**.

The deep template export can include:

- Group interfaces
- Internal nodes
- Node properties
- Socket defaults
- Links
- Nested group definitions

When resource export is enabled, image textures used inside exported groups are copied or saved into a partner resource folder beside the JSON, with a manifest.

### Load Template JSON

Loading restores the scanner display and attempts to load partner resources when the matching resource folder and manifest exist.

## Advanced rebuild and validation

> **Experimental:** Use these controls only in a backup `.blend`.

### Rebuild Template Groups

Creates node groups from loaded template JSON using the selected prefix, default `REBUILT_`.

### Validate Rebuilt Groups

Compares rebuilt groups with the loaded template data and prints validation details.

### Dump Interface Map

Prints original and rebuilt interface socket names, identifiers, and types to the system console.

These operations are development and diagnostic tools. Complex nodes, version-specific properties, external dependencies, or unsupported socket behavior may not reconstruct perfectly.

---

# 11. FBX Root Bone Fix

## Purpose

Patches Blender’s `export_fbx_bin.py` so the standard FBX exporter no longer exports EMPTY or ARMATURE objects through a specific root-handling branch used by the add-on’s Tekken workflow.

## Location

3D Viewport → **Object** menu

The menu displays one status:

- Patched
- Original
- File not found
- Error reading file
- Mixed/Partial
- Unknown

## Apply

1. Save work and close other Blender sessions.
2. Open the Object menu.
3. Confirm status is Original.
4. Click **Apply Fix**.
5. Restart Blender or reload the FBX add-on.

The tool creates one backup beside the exporter file:

`export_fbx_bin.py.bak`

It then comments the target line and the following two lines.

## Restore

1. Open the Object menu.
2. Click **Restore Original**.
3. Restart Blender or reload the FBX add-on.

Restore copies the `.bak` file over the active exporter file.

## Warnings

- This modifies Blender installation or user-script files, not merely the current `.blend`.
- Blender updates can replace or relocate the FBX exporter.
- The target source-code pattern can change between Blender versions.
- Applying the patch may require permission to write to Blender’s installation folder.
- The patch is only as current as the exact Blender exporter version it was written against.
- Keep a clean Blender installer or portable copy available when testing.

---

# 12. Troubleshooting

## The T8 Tools tab is missing

- Confirm the add-on is enabled.
- Confirm the ZIP contains `T8_Tools/__init__.py`.
- Restart Blender.
- Check the system console for registration errors.
- Re-enable all tool groups in add-on preferences.

## One category is missing

The category may be disabled in add-on preferences. Change the preference, then disable/re-enable T8 Tools or restart Blender.

## A button reports “No selected objects”

Confirm objects are selected in the 3D Viewport and that they are the required type, usually Mesh or Armature.

## Source-to-target result is reversed

Check the active object. In Quick Weight Transfer, the active mesh is the source and all other selected meshes are destinations.

## Baking changes the shader preview

The Texture Baker temporarily reconnects Material Output. Use **Clear Temporary Nodes** after baking. For unusual material graphs, save first and inspect the output connection afterward.

## ID paint preview remains active

Set Active Paint ID to **None**, then click **Set Active Paint ID**.

## Bone Mapper says target name already exists

The current conflict mode only skips that mapping. Rename or remove the conflicting custom-rig bone manually, or revise the mapping.

## Shape Key Bone Align moves too far

- Run Dry Run first.
- Lower Max Move Distance.
- Raise Weight Threshold.
- Increase Minimum Vertices.
- Limit processing to selected bones.
- Use a Bone Filter.
- Verify the vertex group represents the intended body region.

## Export Both refuses to run

Run one single MSL or PRP export first so Blender’s FBX settings are initialized for the current session.

## FBX patch reports target pattern not found

The Blender exporter source likely changed. Restore any partial edits and do not manually force the patch without reviewing the installed exporter code.

---

# 13. Known Limitations and Safety Notes

- The add-on metadata reports version 1.0.0 even when repository tags may be newer.
- The declared Blender minimum is 3.6, but several modules contain Blender 4.x compatibility paths. Every public release should be tested on the exact supported versions.
- Add-on preference switches are evaluated during module registration and do not dynamically rebuild the UI immediately.
- Texture Baker cleanup assumes a reasonably conventional material with a non-temporary Principled BSDF.
- Single-map baking does not automatically save the image to disk.
- Batch baking excludes ID maps.
- Image collection can overwrite same-named files in the destination.
- Modifier Pause tracks objects and modifiers by name.
- Weight transfer applies the Data Transfer modifier and can delete all destination groups.
- Export tools alter parenting and Armature modifiers.
- Export Both leaves meshes bound to PRP after the second pass.
- Rig Matcher matches only exact bone names.
- Bone Mapper’s conflict mode currently supports Skip only.
- Multires Setup replaces previously recorded B and C objects.
- Shape Key Bone Align moves edit bones and depends heavily on vertex-group quality.
- Shader-template rebuilding is experimental and may not reproduce every node or interface perfectly.
- FBX Root Bone Fix edits Blender’s exporter source file.

---

# 14. Recommended First-Time Test

Before using the add-on on a production mod:

1. Create a small test `.blend`.
2. Add two simple meshes, two materials, and a small armature.
3. Test Duplicate Material Cleanup.
4. Test Consolidate UVs.
5. Test a simple RMA bake at 512 × 512.
6. Test Quick Weight Transfer on duplicate geometry.
7. Initialize one material’s ID System and paint ID 1.
8. Run an ID bake.
9. Save a small Bone Mapper preset without applying it.
10. Test a single FBX export to a temporary folder.
11. Test experimental tools only after the core tools behave correctly in the installed Blender version.

This small rehearsal catches version incompatibilities before they become a full-cost boss fight.

---

# 15. Support Information to Include in Bug Reports

When reporting a problem, include:

- T8 Tools release tag
- Blender version
- Operating system
- Tool name
- Exact steps
- Expected result
- Actual result
- Screenshot of the panel and selection
- Blender system-console output
- Whether the issue reproduces in a fresh `.blend`
- A minimal sample file when sharing is permitted

Do not share copyrighted game assets publicly when a simplified reproduction can demonstrate the issue.
