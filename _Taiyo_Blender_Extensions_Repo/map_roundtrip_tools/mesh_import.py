"""FBX library import with deferred destructive cleanup and reversible remaps."""
import csv
import os
import re
import bpy
from mathutils import Matrix
from .chunked import ChunkedOperator
from .mirror import mirror_path
from .placement import colname_parts, normalize, walk_library

LAST_IMPORTER = ''
DEFAULT_NEW_MESHES = 'FromHoudini'


def fbx_import(path):
    global LAST_IMPORTER
    before = data_snapshot()
    try:
        result = bpy.ops.wm.fbx_import(filepath=path)
        LAST_IMPORTER = 'wm.fbx_import'
    except (AttributeError, RuntimeError):
        remove_imported(before)
        result = bpy.ops.import_scene.fbx(filepath=path)
        LAST_IMPORTER = 'import_scene.fbx'
    if 'FINISHED' not in result:
        raise RuntimeError('FBX import did not finish.')
    return result


def data_snapshot():
    return {name: set(getattr(bpy.data, name)) for name in ('objects', 'meshes', 'materials', 'collections')}


def remove_imported(snapshot):
    objects = set(bpy.data.objects) - snapshot['objects']
    if objects:
        bpy.data.batch_remove(ids=objects)
    for kind in ('meshes', 'materials', 'collections'):
        extra = [item for item in getattr(bpy.data, kind) if item not in snapshot[kind] and (kind == 'collections' or item.users == 0)]
        if extra:
            bpy.data.batch_remove(ids=extra)


def _is_identity(matrix, tolerance=1e-6):
    return all(abs(matrix[r][c] - (r == c)) <= tolerance for r in range(4) for c in range(4))


def csv_colnames(path, name_mode):
    """{normalized objname: [colname, ...]} in file order. Missing file/columns and unreadable rows are ignored."""
    result = {}
    try:
        with open(path, newline='', encoding='utf-8-sig') as stream:
            reader = csv.reader(stream)
            header = next(reader, [])
            columns = {name: i for i, name in enumerate(header)}
            if 'objname' not in columns or 'colname' not in columns:
                return result
            need = max(columns['objname'], columns['colname']) + 1
            for row in reader:
                if len(row) >= need and row[columns['objname']].strip():
                    result.setdefault(normalize(row[columns['objname']], name_mode), []).append(row[columns['colname']])
    except (OSError, UnicodeError, csv.Error):
        pass
    return result


def choose_colname(colnames):
    """(the most common colname, number of different colnames); a tie goes to the one that appears first."""
    if not colnames:
        return '', 0
    counts = {}
    for name in colnames:
        counts[name] = counts.get(name, 0) + 1
    best = max(counts.values())
    chosen = next(name for name in colnames if counts[name] == best)
    return chosen, len(counts)


class MRT_OT_ImportMeshes(ChunkedOperator, bpy.types.Operator):
    bl_description = '指定したMesh FBXをLibraryへ取り込みます。配置を置換する操作ではありません'
    bl_idname = 'mrt.import_meshes'
    undo_push = True
    bl_label = 'Import New Meshes'

    def work(self, context):
        p = context.scene.mrt_props
        if p.library_coll is None:
            raise ValueError('Library collection is not set.')
        path = bpy.path.abspath(p.mesh_fbx)
        if not p.mesh_fbx or not os.path.isfile(path):
            raise ValueError('Mesh FBX does not exist.')
        exact, norm = {}, {}
        for c in walk_library(p):
            for ob in c.objects:
                if ob.type == 'MESH':
                    exact.setdefault(ob.name, ob)
                    norm.setdefault(normalize(ob.name, p.name_mode), ob)
            yield
        snapshot = data_snapshot()
        # Name sets are captured before import; pointers also survive renaming.
        original_names = {kind: {item.name for item in items} for kind, items in snapshot.items()}
        selected, active = tuple(context.selected_objects), context.view_layer.objects.active
        updates, kept, discard = [], [], []
        remapped = []
        old_mesh_names = {}
        off_origin = skipped = updated = transformed = 0
        committed = False
        try:
            fbx_import(path)
            yield
            new_objects = set(bpy.data.objects) - snapshot['objects']
            meshes = sorted((ob for ob in new_objects if ob.type == 'MESH'), key=lambda ob: ob.name)
            # Cache imported memberships once by collection.
            memberships = {}
            for c in (*bpy.data.collections, *(s.collection for s in bpy.data.scenes)):
                members = [ob for ob in c.objects if ob in new_objects]
                if members:
                    memberships[c] = members
                yield
            updated_meshes = set()
            for i, ob in enumerate(meshes):
                off_origin += ob.matrix_world.translation.length > 1e-6
                old = exact.get(ob.name)
                # Blender may have appended .001 to avoid a pre-import name.
                if old is None:
                    base = re.sub(r'\.\d+$', '', ob.name)
                    if base in original_names['objects']:
                        old = exact.get(base)
                if old is None:
                    old = norm.get(normalize(ob.name, p.name_mode))
                if old is not None:
                    if p.if_exists == 'SKIP' or old.data in updated_meshes:
                        skipped += 1
                    else:
                        updated_meshes.add(old.data)
                        updates.append((old.data, ob.data))
                        updated += 1
                    discard.append(ob)
                else:
                    kept.append(ob)
                self.progress('Planning imported meshes', i + 1, len(meshes))
                yield
            # Validate the entire import plan before changing existing data.
            unique_updates = []
            used_new_meshes = set()
            for old_mesh, new_mesh in updates:
                if new_mesh in used_new_meshes:
                    new_mesh = new_mesh.copy()
                used_new_meshes.add(new_mesh)
                unique_updates.append((old_mesh, new_mesh))
            updates = unique_updates
            for old_mesh, new_mesh in updates:
                if old_mesh.library or new_mesh.library:
                    raise ValueError('Cannot update a linked-library mesh.')
            root = p.new_mesh_coll or p.library_coll.children.get(DEFAULT_NEW_MESHES)
            if kept and root is None:
                root = bpy.data.collections.new(DEFAULT_NEW_MESHES)
                p.library_coll.children.link(root)
            # Where each new mesh goes: the colname path of the CSV rows that use it, rebuilt below the destination.
            csv_path = bpy.path.abspath(p.placement_csv) if p.placement_csv else ''
            colnames_of = csv_colnames(csv_path, p.name_mode) if csv_path and os.path.isfile(csv_path) else {}
            map_name = p.map_coll.name if p.map_coll else ''
            created_collections, destination, from_csv = [], {}, 0
            for ob in kept:
                rows = (colnames_of.get(ob.name) or colnames_of.get(re.sub(r'\.\d+$', '', ob.name))
                        or colnames_of.get(normalize(ob.name, p.name_mode)) or [])
                colname, distinct = choose_colname(rows)
                if distinct > 1:
                    shown = ', '.join(list(dict.fromkeys(rows))[:3])
                    self.report({'WARNING'}, f'{ob.name}: used with {distinct} different collection paths ({shown}); '
                                f'using {colname or "(root)"}')
                parts = colname_parts(colname, map_name) if colname else ()
                destination[ob] = mirror_path(root, parts, root.name, created_collections) if parts else root
                from_csv += bool(parts)
            existing_mats = {m.name: m for m in snapshot['materials']}
            material_meshes = {ob.data for ob in meshes} | {mesh for _, mesh in updates}
            for mesh in material_meshes:
                # Material edits only touch imported meshes, never existing ones.
                for index, mat in enumerate(mesh.materials):
                    if mat:
                        base = re.sub(r'\.\d+$', '', mat.name)
                        previous = existing_mats.get(base)
                        if previous is not None and previous != mat:
                            mesh.materials[index] = previous
                yield
            baked = set()
            for ob in meshes:
                # Keep imported world transforms when removing FBX parent empties.
                if ob.parent:
                    world = ob.matrix_world.copy()
                    ob.parent = None
                    ob.matrix_world = world
                # Only with 'Convert Houdini FBX to Blender size'. A Y-up / centimetre FBX (Houdini) arrives as an object
                # with rotation 90 deg and scale 0.01 over raw mesh data. Placement only uses the mesh, so that transform
                # is baked into it: the mesh then matches the Library (Z-up, metres, identity object).
                world = ob.matrix_basis.copy()  # the parent is gone; matrix_world can be stale right after an import
                if not p.convert_houdini_fbx:
                    pass
                elif ob.data not in baked and not _is_identity(world):
                    ob.data.transform(world)
                    if world.determinant() < 0:
                        ob.data.flip_normals()
                    ob.data.update()
                    baked.add(ob.data)
                    transformed += 1
                    ob.matrix_basis = Matrix.Identity(4)
                elif ob.data in baked:
                    ob.matrix_basis = Matrix.Identity(4)
                yield
            kept_set = set(kept)
            for ob in kept:
                destination[ob].objects.link(ob)
                yield
            for c, members in memberships.items():
                for ob in members:
                    if ob in kept_set and c != destination[ob]:
                        c.objects.unlink(ob)
                    yield
            for old_mesh, new_mesh in updates:
                old_mesh_names[old_mesh] = old_mesh.name
                old_mesh.user_remap(new_mesh)
                remapped.append((old_mesh, new_mesh))
                yield
            # No yielding after destructive commit begins.
            disposable = [ob for ob in new_objects if ob not in kept_set]
            if disposable:
                bpy.data.batch_remove(ids=disposable)
            rename = [(new, old_mesh_names[old]) for old, new in remapped]
            if remapped:
                bpy.data.batch_remove(ids=[old for old, new in remapped])
            for mesh, name in rename:
                mesh.name = name
            for kind in ('meshes', 'materials'):
                unused = [item for item in getattr(bpy.data, kind) if item not in snapshot[kind] and item.users == 0]
                if unused:
                    bpy.data.batch_remove(ids=unused)
            empty_collections = [c for c in bpy.data.collections if c not in snapshot['collections'] and c != root and c not in created_collections and not c.objects and not c.children]
            if empty_collections:
                bpy.data.batch_remove(ids=empty_collections)
            committed = True
            imported = len(kept) + updated
            p.plan_new_meshes_imported += imported
            if off_origin:
                self.report({'WARNING'}, f'{off_origin} imported meshes are not at the origin; transforms preserved.')
            self.result = f'Imported {imported} meshes (skipped {skipped}, updated {updated}); importer {LAST_IMPORTER}; collection paths from CSV {from_csv}' + (f'; FBX transform baked into {transformed} meshes' if p.convert_houdini_fbx else '')
        except BaseException as exc:
            if not committed:
                for old_mesh, new_mesh in reversed(remapped):
                    new_mesh.user_remap(old_mesh)
                    yield
                remove_imported(snapshot)
                self._error = 'Rolled back imported meshes. ' + (self._error or str(exc) or 'Operation failed.')
            raise
        finally:
            # FBX import changes selection even when using the data API afterwards.
            for ob in tuple(context.selected_objects):
                ob.select_set(False)
            for ob in selected:
                try:
                    ob.select_set(True)
                except ReferenceError:
                    pass
            context.view_layer.objects.active = active
