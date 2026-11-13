"""Plan the CSV against the zone, then add new objects, move changed ones and retire the rest (reversibly)."""
import csv
import difflib
import json
import math
import os
import re
from dataclasses import dataclass, field
import bpy
from mathutils import Euler
from . import placement_report
from .constants import ZONE_KEY, COLNAME_SEPARATOR, CSV_COLUMNS, CSV_ID_KEY, NEW_MESH_ID, RUN_KEY
from .chunked import ChunkedOperator
from .journal import (Journal, STATE_AFTER, STATE_BEFORE, STATE_KEY, apply_absent, capture,
                      ensure_archive, find_layer, map_state, read_run, write_run)  # noqa: F401 (find_layer is re-exported)
from .placement_report import Issue


def normalize(name, mode):
    if mode == 'numeric_suffix':
        return re.sub(r'\.\d{3,}$', '', name)
    if mode == 'trim_after_dot':
        return name.split('.', 1)[0]
    return name


class NameAllocator:
    """Avoid Blender's quadratic repeated auto-suffix search for shared names."""
    def __init__(self, names):
        self.names = names
        self.next_suffix = {}

    def take(self, name):
        if name not in self.names:
            self.names.add(name)
            return name
        base = re.sub(r'\.\d{3,}$', '', name)
        # Leave room for Blender's numeric suffix within the 63-byte ID limit.
        base = base.encode('utf-8')[:59].decode('utf-8', errors='ignore')
        index = self.next_suffix.get(base, 1)
        candidate = f'{base}.{index:03d}'
        while candidate in self.names:
            index += 1
            candidate = f'{base}.{index:03d}'
        self.next_suffix[base] = index + 1
        self.names.add(candidate)
        return candidate


def walk_collections(root):
    pending = [root]
    seen = set()
    while pending:
        c = pending.pop()
        if c in seen:
            continue
        seen.add(c)
        yield c
        pending.extend(reversed(tuple(c.children)))


def walk_library(p):
    """Collections searched for meshes: Library plus the New Meshes To collection (it may sit outside Library).

    A destination inside the Map is ignored: placed objects must never count as Library meshes.
    """
    seen = set(walk_collections(p.map_coll)) if p.map_coll else set()
    for root in (p.library_coll, p.new_mesh_coll):
        if root is None or root in seen:
            continue
        for c in walk_collections(root):
            if c not in seen:
                seen.add(c)
                yield c


def build_parent_index(map_coll):
    """First parent of every collection (parents inside the map tree win) and the set of scene root collections."""
    parents = {}
    if map_coll is not None:
        for c in walk_collections(map_coll):
            for child in c.children:
                parents.setdefault(child, c)
    roots = {scene.collection for scene in bpy.data.scenes}
    for c in (*bpy.data.collections, *roots):
        for child in c.children:
            parents.setdefault(child, c)
    return parents, roots


def collection_colname(collection, map_coll, parents, roots):
    """The CSV colname of a collection: its path below the Map collection (or below the scene root).

    The Map collection and scene roots give an empty name. A name that contains the separator cannot be written as a
    path without becoming ambiguous, so the plain collection name is used instead.
    """
    names, node, seen = [], collection, set()
    while node is not None and node != map_coll and node not in roots and node not in seen:
        seen.add(node)
        names.append(node.name)
        node = parents.get(node)
    if any(COLNAME_SEPARATOR in name for name in names):
        return collection.name
    return COLNAME_SEPARATOR.join(reversed(names))


def map_collection_paths(map_coll):
    """{(name, ...): collection} for every collection below the Map collection."""
    index, stack, seen = {}, [(map_coll, ())], set()
    while stack:
        c, path = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        if path:
            index.setdefault(path, c)
        stack.extend((child, path + (child.name,)) for child in reversed(tuple(c.children)))
    return index


def colname_parts(colname, map_name=''):
    """A CSV colname as a tuple of collection names below Map.

    Empty segments make it one literal name; a leading Map name is dropped (CSV written without a Map set).
    """
    parts = tuple(colname.split(COLNAME_SEPARATOR))
    if any(not part for part in parts):
        return (colname,)
    if len(parts) > 1 and map_name and parts[0] == map_name:
        parts = parts[1:]
    return parts


def resolve_colname(plan, map_coll, colname):
    """Find the collection for a CSV colname, or record the collections that have to be created.

    1. A collection of that exact name in the Map tree (older CSVs; also the Map collection itself).
    2. Otherwise colname is a path below Map. Missing collections are planned, parents before children.
    """
    if colname in plan.collections or colname in plan.colname_new:
        return
    parts = colname_parts(colname, map_coll.name)
    existing = next((k for k in range(len(parts), 0, -1) if parts[:k] in plan.path_index), 0)
    if existing == len(parts):
        plan.collections[colname] = plan.path_index[parts]
        return
    plan.colname_new[colname] = parts
    for k in range(existing + 1, len(parts) + 1):
        plan.new_collections.add(parts[:k])
        if parts[k - 1] in bpy.data.collections:
            plan.name_conflicts.add(COLNAME_SEPARATOR.join(parts[:k]))


def effective_zone(p):
    return p.zone_override.strip() or os.path.splitext(os.path.basename(bpy.path.abspath(p.placement_csv)))[0]


@dataclass
class Plan:
    zone: str
    rows: list = field(default_factory=list)        # (mesh, name, loc, rot, scale, colname) for each usable CSV row
    row_ob: list = field(default_factory=list)      # parallel to rows: the zone object the row updates, or None for a new object
    row_line: list = field(default_factory=list)    # parallel to rows: the CSV line
    old: list = field(default_factory=list)         # every object tagged with the zone
    unchanged: list = field(default_factory=list)   # objects that stay exactly as they are
    moved: list = field(default_factory=list)       # row indices whose object changes
    collection_moves: set = field(default_factory=set)  # row indices that also change collection
    retired: list = field(default_factory=list)     # zone objects without a row
    adds: list = field(default_factory=list)        # row indices that create a new object
    kept_unresolved: set = field(default_factory=set)   # zone objects whose row names a mesh that is not in Library
    owners: dict = field(default_factory=dict)      # zone object -> its collections, in export order
    collections: dict = field(default_factory=dict)
    new_collections: set = field(default_factory=set)  # tuples of names, relative to the Map collection
    colname_new: dict = field(default_factory=dict)  # colname -> tuple of names that has to be created
    path_index: dict = field(default_factory=dict)  # tuple of names -> existing collection below Map
    name_conflicts: set = field(default_factory=set)  # new paths whose name is already used elsewhere
    unmatched: set = field(default_factory=set)
    missing_rows: int = 0
    invalid: int = 0
    duplicates: int = 0
    object_names: set = field(default_factory=set)
    added: int = 0            # rows with id -1 whose Library mesh was found
    unknown_id_rows: int = 0  # rows skipped because their id is unknown
    duplicate_id_rows: int = 0  # rows whose id was already used by an earlier row (added as new objects)
    id_check: bool = False    # whether ids were checked (the zone already has objects)
    issues: list = field(default_factory=list)
    map_name: str = ''


def _parse_row(row, header, columns, line):
    """(values, csv_id, name, colname) or an Issue for the first problem in the row."""
    need = max(columns[n] for n in CSV_COLUMNS) + 1
    if len(row) < need:
        return Issue('short_row', f'Line {line}: the row has {len(row)} columns, but the header has {len(header)}; '
                     f'at least {need} are needed.', line=line)
    raw = row[columns['id']]
    try:
        number = float(raw)
        if not number.is_integer():
            raise ValueError
        csv_id = int(number)
    except (ValueError, OverflowError):
        return Issue('bad_id', f'Line {line}: column id = {raw!r} is not an integer.', line=line, column='id', value=raw)
    values = []
    for column in CSV_COLUMNS[1:10]:
        raw = row[columns[column]]
        try:
            value = float(raw)
        except ValueError:
            return Issue('bad_number', f'Line {line}: column {column} = {raw!r} is not a number.', line=line, column=column, value=raw)
        if not math.isfinite(value):
            return Issue('not_finite', f'Line {line}: column {column} = {raw!r} is not a finite number.', line=line, column=column, value=raw)
        values.append(value)
    name = row[columns['objname']]
    if not name.strip():
        return Issue('empty_objname', f'Line {line}: objname is empty.', line=line, column='objname')
    return tuple(values), csv_id, name, row[columns['colname']]


def _transform_differs(ob, loc, rot, scale):
    matrix = ob.matrix_world if ob.parent else ob.matrix_basis
    ob_loc, ob_rot, ob_scale = matrix.decompose()
    for a, b in zip((*ob_loc, *ob_scale), (*loc, *scale)):
        if abs(a - b) > 1e-5 + 1e-6 * abs(b):
            return True
    return ob_rot.rotation_difference(Euler(rot, 'XYZ').to_quaternion()).angle > 1e-4


def build_plan(p, progress=lambda *args: None):
    if p.library_coll is None:
        raise ValueError('Library collection is not set.')
    if p.map_coll is None:
        raise ValueError('Map collection is not set.')
    path = bpy.path.abspath(p.placement_csv)
    if not p.placement_csv or not os.path.isfile(path):
        raise ValueError(f'Placement CSV does not exist: {path or "(not set)"}')
    zone = effective_zone(p)
    if not zone:
        raise ValueError('Zone name is empty.')
    if map_state(zone) == STATE_BEFORE:
        raise ValueError(f'{zone} is showing the original map. Re-apply the imported map before importing again.')
    plan = Plan(zone, map_name=p.map_coll.name)
    issues = plan.issues
    exact, norm, seen, non_mesh = {}, {}, set(), {}
    first_of = {}
    for c in walk_library(p):
        for i, ob in enumerate(c.objects):
            if ob in seen:
                continue
            seen.add(ob)
            if ob.type != 'MESH':
                non_mesh[ob.name] = ob.type
            else:
                exact[ob.name] = ob.data
                name = normalize(ob.name, p.name_mode)
                if name in norm:
                    plan.duplicates += 1
                    issues.append(Issue('duplicate_library_name', f'Library has several objects named {name!r} after name normalization '
                                        f'({first_of[name]}, {ob.name}); the first one ({first_of[name]}) is used.', severity='warning'))
                else:
                    norm[name] = ob.data
                    first_of[name] = ob.name
            if i % 512 == 0:
                yield
        yield
    for c in walk_collections(p.map_coll):
        plan.collections.setdefault(c.name, c)
        yield
    plan.path_index = map_collection_paths(p.map_coll)
    for i, ob in enumerate(bpy.data.objects):
        plan.object_names.add(ob.name)
        if ob.get(ZONE_KEY) == zone:
            plan.old.append(ob)
        if i % 1024 == 0:
            yield
    known = {}
    for ob in plan.old:
        value = ob.get(CSV_ID_KEY)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer():
            known.setdefault(int(value), ob)
    if plan.old and not known:
        raise ValueError(f'{zone} has {len(plan.old)} objects but none has ub_csv_id. Run Export Zone CSV with this version first.')
    plan.id_check = bool(known)
    claimed = {}  # csv id -> first line that used it
    hints = {}
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if header is None:
            raise ValueError('Placement CSV is empty.')
        columns = {name: i for i, name in enumerate(header)}
        missing = set(CSV_COLUMNS) - columns.keys()
        if missing:
            raise ValueError(f'Missing CSV columns: {", ".join(sorted(missing))}. Found: {", ".join(header) or "(none)"}')
        for number, row in enumerate(reader, 1):
            line = reader.line_num
            parsed = _parse_row(row, header, columns, line)
            if isinstance(parsed, Issue):
                plan.invalid += 1
                issues.append(parsed)
            else:
                values, csv_id, name, colname = parsed
                matched = None
                skip = False
                if plan.id_check and csv_id != NEW_MESH_ID:
                    matched = known.get(csv_id)
                    if matched is None:
                        plan.unknown_id_rows += 1
                        skip = True
                        issues.append(Issue('unknown_id', f'Line {line}: id {csv_id} (objname {name!r}) matches no exported object of '
                                            f'zone {zone}; the row was not used. Export Zone CSV again if the zone changed.',
                                            severity='warning', line=line, column='id', value=str(csv_id)))
                    elif csv_id in claimed:
                        plan.duplicate_id_rows += 1
                        issues.append(Issue('duplicate_id', f'Line {line}: id {csv_id} was already used by line {claimed[csv_id]}; '
                                            f'this row creates a new object (a copy made in Houdini?).', severity='warning',
                                            line=line, column='id', value=str(csv_id)))
                        matched = None
                    else:
                        claimed[csv_id] = line
                if not skip:
                    mesh = exact.get(name)
                    if mesh is None:
                        mesh = norm.get(normalize(name, p.name_mode))
                    if mesh is None:
                        plan.unmatched.add(name)
                        plan.missing_rows += 1
                        if name not in hints:
                            close = difflib.get_close_matches(normalize(name, p.name_mode), list(norm), n=3) if len(hints) < 20 else []
                            hints[name] = close
                        if name in non_mesh:
                            extra = f' A Library object with this name exists, but it is a {non_mesh[name]}, not a mesh.'
                        elif hints[name]:
                            extra = ' Similar Library names: ' + ', '.join(hints[name]) + '.'
                        elif csv_id == NEW_MESH_ID:
                            extra = ' It is a new mesh (id -1): run Import New Meshes first.'
                        else:
                            extra = ' No similar name in Library.'
                        if matched is not None:
                            plan.kept_unresolved.add(matched)
                            extra += f' The existing object {matched.name} was left unchanged.'
                        issues.append(Issue('missing_mesh', f'Line {line}: objname {name!r} was not found in Library '
                                            f'(name mode: {p.name_mode}).{extra}', line=line, column='objname', value=name))
                    else:
                        tx, ty, tz, rx, ry, rz, sx, sy, sz = values
                        factor = math.pi / 180.0
                        plan.rows.append((mesh, name, (tx, ty, tz), (rx * factor, ry * factor, rz * factor), (sx, sy, sz), colname))
                        plan.row_ob.append(matched)
                        plan.row_line.append(line)
                        if csv_id == NEW_MESH_ID:
                            plan.added += 1
                        if colname:
                            if matched is None:
                                resolve_colname(plan, p.map_coll, colname)  # rows that update an object resolve it only if it must move
                            if any(not part for part in colname.split(COLNAME_SEPARATOR)) and COLNAME_SEPARATOR in colname:
                                issues.append(Issue('odd_colname', f'Line {line}: colname {colname!r} has an empty path segment; '
                                                    f'it is used as one collection name.', severity='warning', line=line,
                                                    column='colname', value=colname))
            if number % 256 == 0:
                progress('Planning CSV', number, number)
                yield
    # Collections of the zone's objects, in the order the exporter looks at them (all collections, then scene roots).
    if not p.map_coll.is_editable:
        raise ValueError('Map collection is not editable.')
    for ob in plan.old:
        if not ob.is_editable:
            raise ValueError(f'Old object is not editable: {ob.name}')
    old_set = set(plan.old)
    roots = {scene.collection for scene in bpy.data.scenes}
    for c in (*bpy.data.collections, *roots):
        for i, ob in enumerate(c.objects):
            if ob in old_set:
                plan.owners.setdefault(ob, []).append(c)
            if i % 1024 == 0:
                yield
        yield
    for ob, owners in plan.owners.items():
        for c in owners:
            if not c.is_editable:
                raise ValueError(f'Old collection is not editable: {c.name} (holds {ob.name})')
    parents, root_set = build_parent_index(p.map_coll)
    map_name = p.map_coll.name

    def parts_of(colname):
        return colname_parts(colname, map_name) if colname else ()

    claimed_obs = {ob for ob in plan.row_ob if ob is not None} | plan.kept_unresolved
    plan.retired = [ob for ob in plan.old if ob not in claimed_obs]
    for i, ob in enumerate(plan.row_ob):
        if ob is None:
            plan.adds.append(i)
            continue
        mesh, name, loc, rot, scale, colname = plan.rows[i]
        owners = plan.owners.get(ob, [])
        current = collection_colname(owners[0], p.map_coll, parents, root_set) if owners else None
        collection_changed = current is None or parts_of(current) != parts_of(colname)
        if collection_changed and colname:
            resolve_colname(plan, p.map_coll, colname)
        if ob.data != mesh or _transform_differs(ob, loc, rot, scale) or collection_changed:
            plan.moved.append(i)
            if collection_changed:
                plan.collection_moves.add(i)
        else:
            plan.unchanged.append(ob)
        if i % 1024 == 0:
            yield
    plan.unchanged.extend(ob for ob in plan.old if ob in plan.kept_unresolved)
    for path_text in sorted('/'.join(parts) for parts in plan.new_collections if '/'.join(parts) in plan.name_conflicts):
        issues.append(Issue('name_conflict', f'Collection {path_text!r}: the name {path_text.split(COLNAME_SEPARATOR)[-1]!r} is already used '
                            f'by another collection in this file, so Blender names the new one with a suffix (.001).', severity='warning'))
    return plan


def publish_plan(p, plan):
    errors, warnings = placement_report.counts(plan.issues)
    p.plan_unchanged = len(plan.unchanged)
    p.plan_moved = len(plan.moved)
    p.plan_archive = len(plan.retired)
    p.plan_create = len(plan.adds)
    p.plan_invalid = plan.invalid
    p.plan_missing_rows = plan.missing_rows
    p.plan_missing = len(plan.unmatched)
    names = sorted(plan.unmatched)
    p.plan_names = ', '.join(names[:5]) + (f' …and {len(names)-5} more' if len(names) > 5 else '')
    p.plan_zone = plan.zone
    p.plan_collections = len(plan.new_collections)
    p.plan_added = plan.added
    p.plan_unknown_id = plan.unknown_id_rows
    p.plan_id_check = plan.id_check
    p.plan_errors = errors
    p.plan_warnings = warnings
    p.plan_ready = True


def plan_summary(plan):
    return (f'{plan.zone}: unchanged {len(plan.unchanged)}, moved {len(plan.moved)}, retired {len(plan.retired)}, '
            f'added {len(plan.adds)}, skipped {plan.missing_rows} (not in Library), invalid rows {plan.invalid}, '
            f'new meshes {plan.added}, unknown id {plan.unknown_id_rows}')


class MRT_OT_ReplaceZone(ChunkedOperator, bpy.types.Operator):
    bl_description = ('Dry Run ONなら計画だけ確認します。OFFなら、CSVと照らして、動いたObjectはその場で移動し、'
                      '使わなくなったObjectは退避用Collectionへ階層のまま移し、新しいObjectを作ります。元のマップへ復元できます')
    bl_idname = 'mrt.replace_zone'
    bl_label = 'Preview Placement / Replace Zone'

    def work(self, context):
        p = context.scene.mrt_props
        p.plan_ready = False
        plan = yield from build_plan(p, self.progress)
        publish_plan(p, plan)
        summary = plan_summary(plan)
        placement_report.publish(summary, plan.issues)
        if plan.duplicates:
            self.report({'WARNING'}, f'{plan.duplicates} duplicate normalized Library names; first match used.')
        if plan.name_conflicts:
            shown = sorted(plan.name_conflicts)
            self.report({'WARNING'}, 'Collection names already used elsewhere; the new ones get a suffix: '
                        + ', '.join(shown[:5]) + (f' …and {len(shown) - 5} more' if len(shown) > 5 else ''))
        if plan.duplicate_id_rows:
            self.report({'WARNING'}, f'{plan.duplicate_id_rows} rows repeat an id; they create new objects.')
        if p.dry_run:
            self.result = 'Preview ' + summary
            return
        scene, view_layer = context.scene, context.view_layer
        zone = plan.zone
        journal = Journal()
        allocator = NameAllocator(plan.object_names)
        moved_obs = [plan.row_ob[i] for i in plan.moved]
        touched = set(moved_obs) | set(plan.retired)
        states, hidden_objects = [], []
        original_active = view_layer.objects.active
        for i, ob in enumerate(view_layer.objects):
            hidden = ob.hide_get()
            if hidden:
                hidden_objects.append(ob)
            if ob in touched:
                states.append((ob, hidden, ob.select_get()))
            if i % 512 == 0:
                yield
        parents, root_set = build_parent_index(p.map_coll)
        owners = plan.owners
        committed = False
        try:
            made, attach = {}, []
            for path in sorted(plan.new_collections):  # a parent path sorts before its children
                c = bpy.data.collections.new(path[-1])
                journal.created_collection(c)
                made[path] = c
                if path[:-1] in made:
                    made[path[:-1]].children.link(c)  # both new: link while detached to avoid view-layer resync
                else:
                    attach.append((plan.path_index[path[:-1]] if len(path) > 1 else p.map_coll, c))
                yield
            for colname, path in plan.colname_new.items():
                plan.collections[colname] = made[path]
            for n, i in enumerate(plan.adds):
                mesh, name, loc, rot, scale, colname = plan.rows[i]
                ob = bpy.data.objects.new(allocator.take(name), mesh)
                journal.created_object(ob)
                ob.location = loc
                ob.rotation_mode = 'XYZ'
                ob.rotation_euler = rot
                ob.scale = scale
                ob[ZONE_KEY] = zone
                ob[RUN_KEY] = json.dumps({'zone': zone, 'before': None})
                c = plan.collections[colname] if colname else p.map_coll
                c.objects.link(ob)
                self.progress('Creating linked instances', n + 1, len(plan.adds))
                yield
            for parent, c in attach:
                parent.children.link(c)
                yield
            for n, i in enumerate(plan.moved):
                ob = plan.row_ob[i]
                mesh, name, loc, rot, scale, colname = plan.rows[i]
                old_spec = read_run(ob)
                before = old_spec['before'] if old_spec and old_spec.get('zone') == zone and 'before' in old_spec else capture(ob, owners.get(ob, []), scene.collection)
                journal.transform(ob)
                ob.rotation_mode = 'XYZ'
                ob.location, ob.rotation_euler, ob.scale = loc, rot, scale
                if ob.data != mesh:
                    ob.data = mesh
                if i in plan.collection_moves:
                    target = plan.collections[colname] if colname else p.map_coll
                    if target not in owners.get(ob, []):
                        journal.link(target, ob)  # link first: the object never has no collection, so its Base keeps its flags
                    for c in list(owners.get(ob, [])):
                        if c != target:
                            journal.unlink(c, ob)
                write_run(journal, ob, {'zone': zone, 'before': before})
                self.progress('Moving changed objects', n + 1, len(plan.moved))
                yield
            if plan.retired or moved_obs or plan.adds:
                archive = ensure_archive(scene, view_layer, zone, journal)
            for n, ob in enumerate(plan.retired):
                old_spec = read_run(ob)
                before = old_spec['before'] if old_spec and old_spec.get('zone') == zone and 'before' in old_spec else capture(ob, owners.get(ob, []), scene.collection)
                first = owners[ob][0] if owners.get(ob) else None
                cn = collection_colname(first, p.map_coll, parents, root_set) if first is not None else ''
                parts = colname_parts(cn, plan.map_name) if cn else ()
                apply_absent(journal, ob, archive, zone, parts, owners)
                write_run(journal, ob, {'zone': zone, 'before': before, 'after': None, 'stash': '/'.join(parts)})
                self.progress('Retiring unused objects', n + 1, len(plan.retired))
                yield
            if plan.retired or moved_obs or plan.adds:
                journal.prop(archive, STATE_KEY)
                archive[STATE_KEY] = STATE_AFTER
            view_layer.update()  # a single explicit update, outside the creation loops
            committed = True
        except BaseException as exc:
            if not committed:
                self.progress('Rolling back', 0, len(journal.items) + len(journal.created_objects))
                yield from journal.rollback()
                # Membership/exclude changes recreate Bases and may lose their temporary hide and selection flags.
                for ob, hidden, selected in states:
                    if hidden or selected:  # a re-created Base starts visible and unselected
                        ob.hide_set(hidden)
                        ob.select_set(selected)
                    yield
                for ob in hidden_objects:
                    ob.hide_set(True)
                    yield
                view_layer.objects.active = original_active
                self._error = f'Rolled back {len(journal.created_objects)} new objects. ' + (self._error or str(exc) or 'Operation failed.')
            raise
        self.result = 'Replaced ' + summary
