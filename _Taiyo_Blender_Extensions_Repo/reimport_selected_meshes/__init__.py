bl_info = {
    "name": "Reimport Selected Meshes",
    "author": "Taiyo",
    "version": (1, 0, 0),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar > Reimport",
    "description": "Reimport the source FBX of the selected meshes and swap every linked use at once",
    "category": "Import-Export",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/reimport_selected_meshes/README.md"

import os
import re

import bpy
from bpy.props import BoolProperty, StringProperty

SRC_KEY = "rsm_src_fbx"          # on a mesh: the FBX file it was reimported from / assigned to
LEGACY_SRC_KEYS = ("mrt_src_fbx",)  # Map Roundtrip Tools records the same thing
SIZE_RATIO_LIMIT = (0.5, 2.0)
SNAPSHOT_KINDS = ("objects", "meshes", "materials", "images", "collections", "armatures", "actions", "cameras", "lights")
CLEANUP_KINDS = ("meshes", "materials", "images", "armatures", "actions", "cameras", "lights")

_SUFFIX = re.compile(r"\.\d+$")


# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────

def base_name(name):
    """Name without Blender's duplicate suffix (.001)."""
    return _SUFFIX.sub("", name)


def file_stem(path):
    """File name without extension; also works for a Windows path read on macOS."""
    return os.path.splitext(re.split(r"[\\/]", path)[-1])[0]


def data_snapshot():
    return {kind: set(getattr(bpy.data, kind)) for kind in SNAPSHOT_KINDS}


def remove_new_data(snapshot, keep=()):
    """Remove everything created since the snapshot (the imported objects first, then data that became unused)."""
    keep = set(keep)
    objects = set(bpy.data.objects) - snapshot["objects"]
    if objects:
        bpy.data.batch_remove(ids=objects)
    collections = [c for c in bpy.data.collections if c not in snapshot["collections"]]
    if collections:
        bpy.data.batch_remove(ids=collections)
    for kind in CLEANUP_KINDS:  # materials before images: an image is only unused once its material is gone
        extra = [item for item in getattr(bpy.data, kind)
                 if item not in snapshot[kind] and item not in keep and item.users == 0]
        if extra:
            bpy.data.batch_remove(ids=extra)


def linear_color_options(operator):
    """{option: 'LINEAR'} for the vertex color option this importer has."""
    try:
        properties = operator.get_rna_type().properties
    except (AttributeError, KeyError, RuntimeError):
        return {}
    for name in ("import_colors", "colors_type"):
        if name in properties and "LINEAR" in {item.identifier for item in properties[name].enum_items}:
            return {name: "LINEAR"}
    return {}


def fbx_import(path, linear_colors=True):
    before = data_snapshot()
    try:
        options = linear_color_options(bpy.ops.wm.fbx_import) if linear_colors else {}
        result = bpy.ops.wm.fbx_import(filepath=path, **options)
    except (AttributeError, RuntimeError):
        remove_new_data(before)
        options = linear_color_options(bpy.ops.import_scene.fbx) if linear_colors else {}
        result = bpy.ops.import_scene.fbx(filepath=path, **options)
    if "FINISHED" not in result:
        raise RuntimeError("FBX import did not finish.")


def world_matrix(ob):
    """Object transform including parents, from the stored values (matrix_world can be stale right after an import)."""
    matrix = ob.matrix_basis.copy()
    if ob.parent is None:
        return matrix
    return world_matrix(ob.parent) @ ob.matrix_parent_inverse @ matrix


def is_identity(matrix, tolerance=1e-6):
    return all(abs(matrix[r][c] - (r == c)) <= tolerance for r in range(4) for c in range(4))


def max_extent(mesh):
    import numpy as np
    count = len(mesh.vertices)
    if not count:
        return 0.0
    co = np.empty(count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(count, 3)
    return float((co.max(axis=0) - co.min(axis=0)).max())


def existing_source(mesh):
    """The recorded source FBX of a mesh, when that file exists."""
    for key in (SRC_KEY, *LEGACY_SRC_KEYS):
        value = mesh.get(key)
        if isinstance(value, str) and value:
            path = bpy.path.abspath(value)
            if os.path.isfile(path):
                return path
    return ""


def recorded_stem(mesh):
    for key in (SRC_KEY, *LEGACY_SRC_KEYS):
        value = mesh.get(key)
        if isinstance(value, str) and value:
            return file_stem(value)
    return ""


def build_folder_index(folder, recursive):
    """{lowercase file stem: [paths]} for the FBX files of a folder."""
    index = {}
    root = bpy.path.abspath(folder) if folder else ""
    if not root or not os.path.isdir(root):
        return index
    walker = os.walk(root) if recursive else [(root, [], os.listdir(root))]
    for directory, _dirs, files in walker:
        for name in sorted(files):
            if name.lower().endswith(".fbx"):
                index.setdefault(os.path.splitext(name)[0].casefold(), []).append(os.path.join(directory, name))
    return index


# ─────────────────────────────────────────
#  Plan: which meshes, which FBX
# ─────────────────────────────────────────

class Target:
    def __init__(self, mesh):
        self.mesh = mesh
        self.object_names = []
        self.source = ""

    def name_candidates(self):
        return [self.mesh.name, *self.object_names]


class Plan:
    def __init__(self):
        self.targets = []
        self.unresolved = []
        self.warnings = []


def make_plan(context, settings):
    plan = Plan()
    by_pointer = {}
    for ob in context.selected_objects:
        if ob.type != "MESH" or ob.data is None:
            continue
        mesh = ob.data
        if mesh.library is not None or mesh.override_library is not None:
            plan.warnings.append(f"{mesh.name}: linked-library mesh skipped")
            continue
        target = by_pointer.get(mesh.as_pointer())
        if target is None:
            target = by_pointer[mesh.as_pointer()] = Target(mesh)
            plan.targets.append(target)
        target.object_names.append(ob.name)
    plan.targets.sort(key=lambda t: t.mesh.name)
    index = build_folder_index(settings.fbx_folder, settings.recursive)
    for target in plan.targets:
        recorded = existing_source(target.mesh)
        found = ""
        if index:
            names = [base_name(n).casefold() for n in target.name_candidates()]
            stem = recorded_stem(target.mesh)
            if stem:
                names.append(stem.casefold())
            for name in dict.fromkeys(names):
                paths = index.get(name, [])
                if len(paths) == 1:
                    found = paths[0]
                    break
                if len(paths) > 1:
                    plan.warnings.append(f"{target.mesh.name}: {len(paths)} FBX files named '{name}' in the folder; choose one")
                    break
        if settings.prefer_folder:
            target.source = found or recorded
        else:
            target.source = recorded or found
        if not target.source:
            plan.unresolved.append(target)
    return plan


# ─────────────────────────────────────────
#  Reimport
# ─────────────────────────────────────────

class Result:
    def __init__(self):
        self.replaced = []     # (name, users)
        self.unmatched = []    # names
        self.warnings = []


def match_group(targets, fbx_objects):
    """{Target: imported object}. A single mesh in the FBX needs no name match when only one mesh uses that FBX."""
    if len(fbx_objects) == 1 and len(targets) == 1:
        return {targets[0]: fbx_objects[0]}
    result, used = {}, set()
    passes = (lambda n: n, base_name, lambda n: base_name(n).casefold())
    for transform in passes:
        for target in targets:
            if target in result:
                continue
            wanted = {transform(n) for n in target.name_candidates()}
            for ob in fbx_objects:
                if ob in used:
                    continue
                if wanted & {transform(ob.name), transform(ob.data.name)}:
                    result[target] = ob
                    used.add(ob)
                    break
    return result


def reimport(context, settings, plan, extra_source=""):
    """Swap the mesh data of every target. Returns a Result. Everything is rolled back when anything fails before the swap."""
    result = Result()
    groups = {}
    for target in plan.targets:
        source = target.source or extra_source
        if source:
            groups.setdefault(source, []).append(target)
    if not groups:
        return result
    original = data_snapshot()
    selected, active = tuple(context.selected_objects), context.view_layer.objects.active
    pairs = []  # (old mesh, new mesh, users)
    committed = False
    wm = context.window_manager
    wm.progress_begin(0, len(groups))
    try:
        for step, (path, targets) in enumerate(sorted(groups.items())):
            group_before = data_snapshot()
            fbx_import(path, settings.linear_colors)
            new_objects = set(bpy.data.objects) - group_before["objects"]
            fbx_objects = sorted((ob for ob in new_objects if ob.type == "MESH"), key=lambda ob: ob.name)
            matches = match_group(targets, fbx_objects)
            for target in targets:
                ob = matches.get(target)
                if ob is None:
                    result.unmatched.append(f"{target.mesh.name} (not in {os.path.basename(path)})")
                    continue
                new_mesh, old_mesh = ob.data, target.mesh
                if settings.bake_transform:
                    world = world_matrix(ob)
                    if not is_identity(world):
                        new_mesh.transform(world)
                        if world.determinant() < 0:
                            new_mesh.flip_normals()
                        new_mesh.update()
                        if world.translation.length > 1e-6:
                            result.warnings.append(f"{old_mesh.name}: the FBX object is not at the origin; its position was baked into the mesh")
                if settings.keep_materials:
                    known = {base_name(m.name): m for m in old_mesh.materials if m}
                    others = {m.name: m for m in group_before["materials"]}
                    for slot, mat in enumerate(new_mesh.materials):
                        if mat is None:
                            continue
                        previous = known.get(base_name(mat.name)) or others.get(base_name(mat.name))
                        if previous is not None and previous != mat:
                            new_mesh.materials[slot] = previous
                old_size, new_size = max_extent(old_mesh), max_extent(new_mesh)
                if old_size > 1e-9:
                    ratio = new_size / old_size
                    if not SIZE_RATIO_LIMIT[0] <= ratio <= SIZE_RATIO_LIMIT[1]:
                        result.warnings.append(f"{old_mesh.name}: size changed x{ratio:.3g} (check 'Bake FBX transform')")
                pairs.append((old_mesh, new_mesh, old_mesh.users, path))
            wm.progress_update(step + 1)
        # Commit. Nothing below creates new data, so it does not fail half way in practice.
        remapped = []
        try:
            for old_mesh, new_mesh, users, path in pairs:
                for key in old_mesh.keys():
                    if key == SRC_KEY:
                        continue
                    try:
                        new_mesh[key] = old_mesh[key]
                    except (TypeError, ValueError):
                        pass
                new_mesh.use_fake_user = old_mesh.use_fake_user
                old_mesh.user_remap(new_mesh)
                remapped.append((old_mesh, new_mesh))
        except BaseException:
            for old_mesh, new_mesh in reversed(remapped):
                new_mesh.user_remap(old_mesh)
            raise
        names = [(new_mesh, old_mesh.name, path, users) for old_mesh, new_mesh, users, path in pairs]
        kept = [new_mesh for _old, new_mesh, _users, _path in pairs]
        objects = set(bpy.data.objects) - original["objects"]
        if objects:
            bpy.data.batch_remove(ids=objects)
        if pairs:
            bpy.data.batch_remove(ids=[old for old, _new, _users, _path in pairs])
        for new_mesh, name, path, users in names:
            new_mesh.name = name
            new_mesh[SRC_KEY] = path
            new_mesh.update_tag()  # a custom property alone is not recorded by Undo
            result.replaced.append((name, users))
        remove_new_data(original, keep=kept)
        committed = True
    except BaseException:
        if not committed:
            remove_new_data(original)
        raise
    finally:
        wm.progress_end()
        for ob in tuple(context.selected_objects):
            ob.select_set(False)
        for ob in selected:
            try:
                ob.select_set(True)
            except ReferenceError:
                pass
        try:
            context.view_layer.objects.active = active
        except ReferenceError:
            pass
    return result


# ─────────────────────────────────────────
#  Properties / Operator / Panel
# ─────────────────────────────────────────

class RSM_Settings(bpy.types.PropertyGroup):
    fbx_folder: StringProperty(
        name="FBX Folder",
        description="Folder searched for the source FBX. A file named like the mesh (Rock.fbx for Rock) is used",
        subtype="DIR_PATH",
    )
    recursive: BoolProperty(name="Search Subfolders", default=True)
    prefer_folder: BoolProperty(
        name="Prefer Folder",
        description="Use the FBX found in the folder before the FBX recorded on the mesh",
        default=False,
    )
    bake_transform: BoolProperty(
        name="Bake FBX Transform",
        description="Bake the FBX object's transform (for example a Houdini Y-up / centimetre rotation 90 and scale 0.01) into the mesh. "
                    "Turn it off for FBX files that already match Blender's size and axes",
        default=True,
    )
    keep_materials: BoolProperty(
        name="Keep Existing Materials",
        description="Use the materials already in the file when the FBX material has the same name (no Material.001)",
        default=True,
    )
    linear_colors: BoolProperty(
        name="Vertex Colors as Linear",
        description="Read vertex colors as Linear (Blender stores them as linear)",
        default=True,
    )


def selected_meshes_exist(context):
    return any(ob.type == "MESH" for ob in context.selected_objects)


class RSM_OT_reimport(bpy.types.Operator):
    bl_idname = "rsm.reimport"
    bl_label = "Reimport Selected Meshes"
    bl_description = ("選択したMeshを元のFBXから再インポートし、そのMeshを使う全Objectを新しいMeshへ入れ替えます。"
                      "FBXが見つからないMeshがあるときはファイルを選びます")
    bl_options = {"UNDO"}

    filepath: StringProperty(subtype="FILE_PATH", options={"HIDDEN", "SKIP_SAVE"})
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and selected_meshes_exist(context)

    def invoke(self, context, event):
        self.filepath = ""
        plan = make_plan(context, context.scene.rsm_settings)
        if plan.unresolved:
            names = ", ".join(t.mesh.name for t in plan.unresolved[:5]) + (" ..." if len(plan.unresolved) > 5 else "")
            self.report({"INFO"}, f"No source FBX found for {names}. Choose the FBX.")
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        return self.execute(context)

    def execute(self, context):
        settings = context.scene.rsm_settings
        extra = bpy.path.abspath(self.filepath) if self.filepath else ""
        if extra and not os.path.isfile(extra):
            self.report({"ERROR"}, f"FBX does not exist: {extra}")
            return {"CANCELLED"}
        plan = make_plan(context, settings)
        if not plan.targets:
            self.report({"WARNING"}, "No selected mesh object.")
            return {"CANCELLED"}
        for message in plan.warnings:
            self.report({"WARNING"}, message)
        if plan.unresolved and not extra:
            names = ", ".join(t.mesh.name for t in plan.unresolved[:5]) + (" ..." if len(plan.unresolved) > 5 else "")
            self.report({"WARNING"}, f"No source FBX found for {names} (skipped)")
        try:
            result = reimport(context, settings, plan, extra)
        except Exception as exc:
            self.report({"ERROR"}, f"Reimport failed and was rolled back: {exc}")
            return {"CANCELLED"}
        for message in result.warnings:
            self.report({"WARNING"}, message)
        for message in result.unmatched:
            self.report({"WARNING"}, f"Not replaced: {message}")
        if not result.replaced:
            self.report({"WARNING"}, "Nothing was replaced.")
            return {"CANCELLED"}
        users = sum(count for _name, count in result.replaced)
        self.report({"INFO"}, f"Reimported {len(result.replaced)} meshes ({users} users updated)")
        return {"FINISHED"}


class RSM_PT_panel(bpy.types.Panel):
    bl_label = "Reimport Selected Meshes"
    bl_idname = "RSM_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Reimport"

    def draw(self, context):
        layout = self.layout
        s = context.scene.rsm_settings
        layout.prop(s, "fbx_folder")
        layout.prop(s, "recursive")
        layout.prop(s, "prefer_folder")
        box = layout.box()
        box.prop(s, "bake_transform")
        box.prop(s, "keep_materials")
        box.prop(s, "linear_colors")
        layout.operator("rsm.reimport", icon="FILE_REFRESH")


classes = (RSM_Settings, RSM_OT_reimport, RSM_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rsm_settings = bpy.props.PointerProperty(type=RSM_Settings)


def unregister():
    del bpy.types.Scene.rsm_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
