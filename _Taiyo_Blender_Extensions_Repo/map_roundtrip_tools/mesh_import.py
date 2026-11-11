"""FBX library import with deferred destructive cleanup and reversible remaps."""
import os
import re
import bpy
from .chunked import ChunkedOperator
from .placement import normalize, walk_collections

LAST_IMPORTER = ''


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


class MRT_OT_ImportMeshes(ChunkedOperator, bpy.types.Operator):
    bl_description = '指定したMesh FBXをLibraryへ取り込みます。配置を置換する操作ではありません'
    bl_idname = 'mrt.import_meshes'
    bl_label = 'Import New Meshes'

    def work(self, context):
        p = context.scene.mrt_props
        if p.library_coll is None:
            raise ValueError('Library collection is not set.')
        path = bpy.path.abspath(p.mesh_fbx)
        if not p.mesh_fbx or not os.path.isfile(path):
            raise ValueError('Mesh FBX does not exist.')
        if not p.new_mesh_coll_name.strip():
            raise ValueError('New Meshes To is empty.')
        exact, norm = {}, {}
        for c in walk_collections(p.library_coll):
            for ob in c.objects:
                if ob.type == 'MESH':
                    exact.setdefault(ob.name, ob)
                    norm.setdefault(normalize(ob.name, p.name_mode), ob)
            yield
        snapshot = data_snapshot()
        # Name sets are captured before import; pointers also survive renaming.
        original_names = {kind: {item.name for item in items} for kind, items in snapshot.items()}
        selected, active = tuple(context.selected_objects), context.view_layer.objects.active
        target = None
        target_created = False
        updates, kept, discard = [], [], []
        remapped = []
        old_mesh_names = {}
        off_origin = skipped = updated = 0
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
            target = p.library_coll.children.get(p.new_mesh_coll_name)
            if kept and target is None:
                target = bpy.data.collections.new(p.new_mesh_coll_name)
                target_created = True
                p.library_coll.children.link(target)
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
            for ob in meshes:
                # Keep imported world transforms when removing FBX parent empties.
                if ob.parent:
                    world = ob.matrix_world.copy()
                    ob.parent = None
                    ob.matrix_world = world
                yield
            kept_set = set(kept)
            for ob in kept:
                target.objects.link(ob)
                yield
            for c, members in memberships.items():
                if c == target:
                    continue
                for ob in members:
                    if ob in kept_set:
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
            empty_collections = [c for c in bpy.data.collections if c not in snapshot['collections'] and c != target and not c.objects and not c.children]
            if empty_collections:
                bpy.data.batch_remove(ids=empty_collections)
            committed = True
            imported = len(kept) + updated
            p.plan_new_meshes_imported += imported
            if off_origin:
                self.report({'WARNING'}, f'{off_origin} imported meshes are not at the origin; transforms preserved.')
            self.result = f'Imported {imported} meshes (skipped {skipped}, updated {updated}); importer {LAST_IMPORTER}'
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
