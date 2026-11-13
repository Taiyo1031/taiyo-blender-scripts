"""Reversible changes (journal), saved before/after states of objects, and the per-zone archive collection."""
import json
import bpy
from mathutils import Matrix
from .constants import ARCHIVED_KEY, RUN_KEY, ZONE_KEY
from .mirror import mirror_path

STATE_KEY = 'ub_state'  # on the archive collection: 'after' (imported map is shown) or 'before' (original map is shown)
STATE_AFTER, STATE_BEFORE = 'after', 'before'
TAG_KEYS = (ZONE_KEY, ARCHIVED_KEY)


def archive_name(zone):
    return '_Replaced_' + zone


def map_state(zone):
    """'after' / 'before' for a zone that has been replaced, else ''."""
    archive = bpy.data.collections.get(archive_name(zone))
    return archive.get(STATE_KEY, STATE_AFTER) if archive is not None else ''


def find_layer(root, collection):
    pending = [root]
    while pending:
        layer = pending.pop()
        if layer.collection == collection:
            return layer
        pending.extend(layer.children)
    return None


class Journal:
    """Everything a task changes goes through here so ESC / failure can put it back."""

    def __init__(self):
        self.items = []
        self.created_objects = []
        self.created_collections = []

    def created_object(self, ob):
        self.created_objects.append(ob)

    def created_collection(self, collection):
        self.created_collections.append(collection)

    def link(self, collection, ob):
        collection.objects.link(ob)
        self.items.append(('unlink', collection, ob))

    def unlink(self, collection, ob):
        collection.objects.unlink(ob)
        self.items.append(('link', collection, ob))

    def attach(self, parent, child):
        parent.children.link(child)
        self.items.append(('detach', parent, child))

    def prop(self, ob, key):
        """Call before writing or deleting ob[key]."""
        self.items.append(('prop', ob, key, key in ob, ob.get(key)))

    def transform(self, ob):
        self.items.append(('transform', ob, ob.matrix_basis.copy(), ob.data))

    def exclude(self, layer):
        self.items.append(('exclude', layer, layer.exclude))

    def rollback(self):
        """Generator: undo everything in reverse order, then remove what was created."""
        for n, entry in enumerate(reversed(self.items)):
            kind = entry[0]
            if kind == 'unlink':
                entry[1].objects.unlink(entry[2])
            elif kind == 'link':
                entry[1].objects.link(entry[2])
            elif kind == 'detach':
                entry[1].children.unlink(entry[2])
            elif kind == 'prop':
                _, ob, key, existed, value = entry
                if existed:
                    ob[key] = value
                elif key in ob:
                    del ob[key]
            elif kind == 'transform':
                _, ob, matrix, data = entry
                ob.matrix_basis = matrix
                if ob.data != data:
                    ob.data = data
            elif kind == 'exclude':
                entry[1].exclude = entry[2]
            if n % 256 == 255:
                yield
        for start in range(0, len(self.created_objects), 512):
            bpy.data.batch_remove(ids=self.created_objects[start:start + 512])
            yield
        if self.created_collections:
            bpy.data.batch_remove(ids=self.created_collections)


def ensure_archive(scene, view_layer, zone, journal):
    """The excluded `_Replaced_<zone>` collection that holds objects absent from the shown state."""
    name = archive_name(zone)
    archive = bpy.data.collections.get(name)
    if archive is None:
        archive = bpy.data.collections.new(name)
        archive[STATE_KEY] = STATE_AFTER
        scene.collection.children.link(archive)
        journal.created_collection(archive)
    elif archive not in scene.collection.children[:]:
        journal.attach(scene.collection, archive)
    layer = find_layer(view_layer.layer_collection, archive)
    if layer is not None and not layer.exclude:
        journal.exclude(layer)
        layer.exclude = True
    return archive


def collection_names(collections, scene_root):
    return ['' if c == scene_root else c.name for c in collections]


def capture(ob, collections, scene_root):
    """The saved form of an object that is present in the map."""
    return {
        'm': [list(row) for row in ob.matrix_basis],
        'mesh': ob.data.name if ob.data is not None else None,
        'colls': collection_names(collections, scene_root),
        'tags': {key: (ob[key] if key in ob else None) for key in TAG_KEYS},
    }


def read_run(ob):
    raw = ob.get(RUN_KEY)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def write_run(journal, ob, spec):
    journal.prop(ob, RUN_KEY)
    ob[RUN_KEY] = json.dumps(spec)


def set_tags(journal, ob, tags):
    for key, value in tags.items():
        journal.prop(ob, key)
        if value is None:
            if key in ob:
                del ob[key]
        else:
            ob[key] = value


def apply_present(journal, ob, state, scene, fallback, owners):
    """Put an object back into a saved present state. Returns the number of collections that no longer exist."""
    journal.transform(ob)
    ob.matrix_basis = Matrix(state['m'])
    mesh = bpy.data.meshes.get(state['mesh']) if state.get('mesh') else None
    if mesh is not None and ob.data != mesh:
        ob.data = mesh
    set_tags(journal, ob, state['tags'])
    wanted, missing = [], 0
    for name in state['colls']:
        c = scene.collection if name == '' else bpy.data.collections.get(name)
        if c is None:
            missing += 1
            c = fallback
        if c not in wanted:
            wanted.append(c)
    current = list(owners.get(ob, []))
    for c in wanted:  # link first so the object always stays in a collection (its Base keeps its flags)
        if c not in current:
            journal.link(c, ob)
    for c in current:
        if c not in wanted:
            journal.unlink(c, ob)
    owners[ob] = wanted
    return missing


def apply_absent(journal, ob, archive, zone, stash_parts, owners):
    """Move an object out of the map into the mirrored archive collection."""
    created = []
    target = mirror_path(archive, tuple(stash_parts), zone, created)
    for c in created:
        journal.created_collection(c)
    current = list(owners.get(ob, []))
    if target not in current:
        journal.link(target, ob)
    for c in current:
        if c != target:
            journal.unlink(c, ob)
    owners[ob] = [target]
    set_tags(journal, ob, {ZONE_KEY: None, ARCHIVED_KEY: zone})
