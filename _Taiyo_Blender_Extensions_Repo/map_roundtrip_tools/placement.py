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
from .constants import ARCHIVED_KEY, ZONE_KEY, COLNAME_SEPARATOR, CSV_COLUMNS, CSV_ID_KEY, NEW_MESH_ID, RUN_KEY
from .chunked import ChunkedOperator
from .journal import (Journal, STATE_AFTER, STATE_BEFORE, STATE_KEY, apply_absent, capture,
                      ensure_archive, find_layer, map_state, read_run, set_tags, write_run)  # noqa: F401 (find_layer is re-exported)
from .placement_report import Issue

INTENDED_NAME_KEY = 'mrt_intended_name'  # the name the CSV asked for, when Blender added a suffix (UNI -> UNI.001)
ACTUAL_NAME_KEY = 'mrt_actual_name'      # the suffixed name at creation; the tag is ignored once the collection is renamed


def collection_label(collection):
    """The name a collection has in a CSV colname: the requested name for a collection that Replace created with a suffix."""
    intended = collection.get(INTENDED_NAME_KEY)
    if intended and collection.get(ACTUAL_NAME_KEY) == collection.name:
        return intended
    return collection.name


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
        names.append(collection_label(node))
        node = parents.get(node)
    if any(COLNAME_SEPARATOR in name for name in names):
        return collection_label(collection)
    return COLNAME_SEPARATOR.join(reversed(names))


def map_collection_paths(map_coll):
    """{(name, ...): collection} for every collection below the Map collection."""
    index, stack, seen, suffixed = {}, [(map_coll, ())], set(), []
    while stack:
        c, path = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        if path:
            if path[-1] == c.name:
                index.setdefault(path, c)
            else:
                suffixed.append((path, c))  # a collection found by the name that was asked for, not its own: second choice
        stack.extend((child, path + (collection_label(child),)) for child in reversed(tuple(c.children)))
    for path, c in suffixed:
        index.setdefault(path, c)
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
    retired: list = field(default_factory=list)     # zone objects whose row says use = 0
    remove_marks: dict = field(default_factory=dict)  # zone object -> first CSV line with use = 0
    not_in_csv: list = field(default_factory=list)  # zone objects without any row: left exactly as they are
    unused_rows: int = 0      # rows with use = 0 (they place nothing)
    resurrected: set = field(default_factory=set)   # objects an earlier Replace retired, whose id now has a use = 1 row: they come back
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
    new_rows: int = 0         # all rows with id -1, found in the Library or not
    unknown_id_rows: int = 0  # rows skipped because their id is unknown
    duplicate_id_rows: int = 0  # rows whose id was already used by an earlier row (added as new objects)
    id_check: bool = False    # whether ids were checked (the zone already has objects)
    issues: list = field(default_factory=list)
    map_name: str = ''


def _parse_row(row, header, columns, line):
    """(values, csv_id, name, colname, use) or an Issue for the first problem in the row.

    The optional column `use` is 1 (or empty / missing) to use the row and 0 to remove the object with that id."""
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
    use = 1
    if 'use' in columns and columns['use'] < len(row) and row[columns['use']].strip():
        raw = row[columns['use']]
        try:
            number = float(raw)
        except ValueError:
            number = None
        if number not in (0.0, 1.0):
            return Issue('bad_use', f'Line {line}: column use = {raw!r} must be 0 (remove) or 1 (use).', line=line, column='use', value=raw)
        use = int(number)
    return tuple(values), csv_id, name, row[columns['colname']], use


def _transform_differs(ob, loc, rot, scale):
    matrix = ob.matrix_world if ob.parent else ob.matrix_basis
    ob_loc, ob_rot, ob_scale = matrix.decompose()
    for a, b in zip((*ob_loc, *ob_scale), (*loc, *scale)):
        if abs(a - b) > 1e-5 + 1e-6 * abs(b):
            return True
    angle = ob_rot.rotation_difference(Euler(rot, 'XYZ').to_quaternion()).angle
    # q and -q are the same rotation: the difference then comes out as 2*pi instead of 0
    return min(angle, 2 * math.pi - angle) > 1e-4


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
    if p.archive_coll is not None:
        scene = bpy.context.scene
        if p.archive_coll != scene.collection and p.archive_coll not in scene.collection.children_recursive:
            raise ValueError(f'Archive To ({p.archive_coll.name}) is not in this scene.')
        if p.archive_coll in set(walk_collections(p.map_coll)) | set(walk_library(p)):
            raise ValueError(f'Archive To ({p.archive_coll.name}) must be outside the Map and the Library, '
                             f'or retired objects would count as placed or as Library meshes.')
        if not p.archive_coll.is_editable:
            raise ValueError(f'Archive To ({p.archive_coll.name}) is not editable.')
    if map_state(zone) == STATE_BEFORE:
        raise ValueError(f'{zone} is showing the original map. Re-apply the imported map before importing again.')
    plan = Plan(zone, map_name=p.map_coll.name)
    issues = plan.issues
    exact, norm, seen, non_mesh = {}, {}, set(), {}
    first_of = {}
    dup_names = {}  # normalized name -> list of object names with that normalization
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
                    # Store the object names for later warning creation.
                    dup_names.setdefault(name, []).append(ob.name)
                else:
                    norm[name] = ob.data
                    first_of[name] = ob.name
            if i % 512 == 0:
                yield
        yield
    # Now create warnings for duplicates (one per name).
    for name, obj_names in dup_names.items():
        issues.append(Issue('duplicate_library_name', f'Library has several objects named {name!r} after name normalization: '
                            f'{", ".join([first_of[name], *obj_names])}; the first one ({first_of[name]}) is used.', severity='warning'))
    for c in walk_collections(p.map_coll):
        plan.collections.setdefault(c.name, c)
        yield
    plan.path_index = map_collection_paths(p.map_coll)
    retired_by_id = {}  # csv id -> object that an earlier Replace retired (use 0); a use = 1 row for it brings it back
    for i, ob in enumerate(bpy.data.objects):
        plan.object_names.add(ob.name)
        if ob.get(ZONE_KEY) == zone:
            plan.old.append(ob)
        elif ob.get(ARCHIVED_KEY) == zone:
            value = ob.get(CSV_ID_KEY)
            spec = read_run(ob)
            # only an object that Replace retired: it has the state it had in the original map and is absent after the import
            if (spec and spec.get('zone') == zone and isinstance(spec.get('before'), dict) and 'after' in spec and spec['after'] is None
                    and isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer()):
                retired_by_id.setdefault(int(value), ob)
        if i % 1024 == 0:
            yield
    known = {}
    for ob in plan.old:
        value = ob.get(CSV_ID_KEY)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer():
            known.setdefault(int(value), ob)
    if plan.old and not known:
        raise ValueError(f'{zone} has {len(plan.old)} objects but none has ub_csv_id. Run Export Zone CSV with this version first.')
    plan.id_check = bool(known or retired_by_id)
    fresh = {}  # mesh -> objects that an earlier Replace made from id -1 rows (no exported id yet), in name order
    for ob in plan.old:
        if ob.get(CSV_ID_KEY) is None:
            spec = read_run(ob)
            # 'after' may exist: Restore Original Map / Re-apply Imported Map store it for the objects they switch
            if spec and spec.get('zone') == zone and 'before' in spec and spec['before'] is None:
                fresh.setdefault(ob.data, []).append(ob)
    for objects in fresh.values():
        objects.sort(key=lambda o: o.name)
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
                values, csv_id, name, colname, use = parsed
                if not use:
                    plan.unused_rows += 1
                    matched = known.get(csv_id) if plan.id_check and csv_id != NEW_MESH_ID else None  # a retired object has nothing left to remove
                    if matched is not None:
                        plan.remove_marks.setdefault(matched, line)
                    if number % 256 == 0:
                        progress('Planning CSV', number, number)
                        yield
                    continue
                if csv_id == NEW_MESH_ID:
                    plan.new_rows += 1
                matched = None
                skip = False
                if plan.id_check and csv_id != NEW_MESH_ID:
                    matched = known.get(csv_id)
                    if matched is None and csv_id in retired_by_id:
                        matched = retired_by_id[csv_id]
                        plan.resurrected.add(matched)
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
                        elif csv_id != NEW_MESH_ID:
                            extra = ' No similar name in Library.'
                        else:
                            extra = ''
                        if csv_id == NEW_MESH_ID and name not in non_mesh:  # also when similar names are listed
                            extra += ' It is a new mesh (id -1): run Import New Meshes first.'
                        if matched is not None:
                            plan.kept_unresolved.add(matched)
                            extra += f' The existing object {matched.name} was left unchanged.'
                        issues.append(Issue('missing_mesh', f'Line {line}: objname {name!r} was not found in Library '
                                            f'(name mode: {p.name_mode}).{extra}', line=line, column='objname', value=name))
                    else:
                        tx, ty, tz, rx, ry, rz, sx, sy, sz = values
                        factor = math.pi / 180.0
                        rot = (rx * factor, ry * factor, rz * factor)
                        if csv_id == NEW_MESH_ID and fresh.get(mesh):
                            # Replace was run before with this row: update that object instead of making another one
                            candidates = fresh[mesh]
                            matched = next((ob for ob in candidates if not _transform_differs(ob, (tx, ty, tz), rot, (sx, sy, sz))), candidates[0])
                            candidates.remove(matched)
                        plan.rows.append((mesh, name, (tx, ty, tz), rot, (sx, sy, sz), colname))
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
    plan.resurrected &= {ob for ob in plan.row_ob if ob is not None}  # a row without a Library mesh leaves its object retired
    for ob in (*plan.old, *plan.resurrected):
        if not ob.is_editable:
            raise ValueError(f'Old object is not editable: {ob.name}')
    old_set = set(plan.old) | plan.resurrected
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
    left = sum(len(objects) for objects in fresh.values())
    if left:
        issues.append(Issue('unmatched_added', f'{left} objects made by an earlier Replace have no matching id -1 row in this CSV; '
                            f'they were left as they are.', severity='warning'))
    for ob, line in plan.remove_marks.items():
        if ob in claimed_obs:
            issues.append(Issue('use_conflict', f'Line {line}: {ob.name} has use = 0 here, but another row with use = 1 uses the same id; '
                                f'the object was kept.', severity='warning', line=line, column='use', value='0'))
    plan.retired = [ob for ob in plan.old if ob in plan.remove_marks and ob not in claimed_obs]
    plan.not_in_csv = [ob for ob in plan.old if ob not in claimed_obs and ob not in plan.remove_marks]

    for i, ob in enumerate(plan.row_ob):
        if ob is None:
            plan.adds.append(i)
            continue
        mesh, name, loc, rot, scale, colname = plan.rows[i]
        owners = plan.owners.get(ob, [])
        current = collection_colname(owners[0], p.map_coll, parents, root_set) if owners else None
        collection_changed = current is None or parts_of(current) != parts_of(colname) or ob in plan.resurrected
        if collection_changed and colname:
            resolve_colname(plan, p.map_coll, colname)
        if ob.data != mesh or _transform_differs(ob, loc, rot, scale) or collection_changed or ob in plan.resurrected:
            plan.moved.append(i)
            if collection_changed:
                plan.collection_moves.add(i)
        else:
            plan.unchanged.append(ob)
        if i % 1024 == 0:
            yield
    plan.unchanged.extend(ob for ob in plan.old if ob in plan.kept_unresolved)
    plan.unchanged.extend(plan.not_in_csv)
    for path_text in sorted('/'.join(parts) for parts in plan.new_collections if '/'.join(parts) in plan.name_conflicts):
        issues.append(Issue('name_conflict', f'Collection {path_text!r}: the name {path_text.split(COLNAME_SEPARATOR)[-1]!r} is already used '
                            f'by another collection in this file, so Blender names the new one with a suffix (.001).', severity='warning'))
    return plan


def publish_plan(p, plan):
    errors, warnings = placement_report.counts(plan.issues)
    p.plan_unchanged = len(plan.unchanged)
    p.plan_moved = len(plan.moved)
    p.plan_archive = len(plan.retired)
    p.plan_not_in_csv = len(plan.not_in_csv)
    p.plan_resurrected = len(plan.resurrected)
    p.plan_unused_rows = plan.unused_rows
    p.plan_create = len(plan.adds)
    p.plan_invalid = plan.invalid
    p.plan_missing_rows = plan.missing_rows
    p.plan_missing = len(plan.unmatched)
    names = sorted(plan.unmatched)
    p.plan_names = ', '.join(names[:5]) + (f' …and {len(names)-5} more' if len(names) > 5 else '')
    p.plan_zone = plan.zone
    p.plan_collections = len(plan.new_collections)
    p.plan_added = plan.added
    p.plan_new_rows = plan.new_rows
    p.plan_unknown_id = plan.unknown_id_rows
    p.plan_id_check = plan.id_check
    p.plan_errors = errors
    p.plan_warnings = warnings
    p.plan_ready = True


def plan_summary(plan):
    return (f'{plan.zone}: unchanged {len(plan.unchanged)} (not in CSV {len(plan.not_in_csv)}), moved {len(plan.moved)} (brought back from the archive {len(plan.resurrected)}), retired {len(plan.retired)} (use 0 rows {plan.unused_rows}), '
            f'added {len(plan.adds)}, skipped {plan.missing_rows} (not in Library), invalid rows {plan.invalid}, '
            f'new meshes {plan.added} of {plan.new_rows} rows with id -1, unknown id {plan.unknown_id_rows}')


class MRT_OT_ReplaceZone(ChunkedOperator, bpy.types.Operator):
    bl_description = ('Dry Run ONなら計画だけ確認します。OFFなら、CSVと照らして、動いたObjectはその場で移動し、'
                      'CSVの`use`列が0のObjectは退避用Collectionへ階層のまま移し、新しいObjectを作ります。CSVに行が無いObjectは動かしません。元のマップへ復元できます')
    bl_idname = 'mrt.replace_zone'
    undo_push = True

    def wants_undo(self, context):
        return not context.scene.mrt_props.dry_run  # Preview changes nothing
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
                if c.name != path[-1]:  # Blender added a suffix: remember the name the CSV asked for
                    c[INTENDED_NAME_KEY] = path[-1]
                    c[ACTUAL_NAME_KEY] = c.name
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
                write_run(journal, ob, {'zone': zone, 'before': before})  # no 'after': the object is present in the imported map
                if ob in plan.resurrected:  # it was retired by an earlier Replace: it is part of the zone again
                    set_tags(journal, ob, {ZONE_KEY: zone, ARCHIVED_KEY: None})
                self.progress('Moving changed objects', n + 1, len(plan.moved))
                yield
            if plan.retired or moved_obs or plan.adds:
                archive = ensure_archive(scene, view_layer, zone, journal, p.archive_coll)
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
