"""Import a zone: archive the zone's original objects, delete the objects of an earlier import, place every CSV row (reversibly)."""
import csv
import difflib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
import bpy
from . import placement_report
from .constants import ZONE_KEY, COLNAME_SEPARATOR, CSV_COLUMNS, RUN_KEY
from .chunked import Cancelled, ChunkedOperator
from .journal import (Journal, STATE_AFTER, STATE_BEFORE, STATE_KEY, apply_absent, capture,
                      ensure_archive, find_layer, map_state, read_run, write_run)  # noqa: F401 (find_layer is re-exported)
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
    """The zone selected in the panels ('' for All Zones or none). One read: the enum scans every empty."""
    choice = p.zone_choice
    return '' if choice in ('', 'ALL') else choice


def made_by_import(ob, zone):
    """True for an object that an import created (ub_run says it did not exist in the original map; also 0.6-0.9 Replace)."""
    spec = read_run(ob)
    return bool(spec) and spec.get('zone') == zone and 'before' in spec and spec['before'] is None


@dataclass
class Plan:
    zone: str
    rows: list = field(default_factory=list)        # (mesh, name, loc, rot, scale, colname) for each CSV row that is placed
    row_line: list = field(default_factory=list)    # parallel to rows: the CSV line
    originals: list = field(default_factory=list)   # objects tagged with the zone that no import made: archived
    previous: list = field(default_factory=list)    # objects an earlier import made (in the Map or stashed in the archive): deleted last
    owners: dict = field(default_factory=dict)      # original object -> its collections, in export order
    collections: dict = field(default_factory=dict)
    new_collections: set = field(default_factory=set)  # tuples of names, relative to the Map collection
    colname_new: dict = field(default_factory=dict)  # colname -> tuple of names that has to be created
    path_index: dict = field(default_factory=dict)  # tuple of names -> existing collection below Map
    name_conflicts: set = field(default_factory=set)  # new paths whose name is already used elsewhere
    unmatched: set = field(default_factory=set)
    missing_rows: int = 0     # rows whose objname is not in Library
    invalid: int = 0          # rows that could not be read
    duplicates: int = 0
    unused_rows: int = 0      # rows with use = 0 (they place nothing)
    object_names: set = field(default_factory=set)
    issues: list = field(default_factory=list)
    map_name: str = ''


def _parse_row(row, header, columns, line):
    """(values, name, colname, use) or an Issue for the first problem in the row.

    The id column is not used any more (the zone is replaced as a whole). The optional column `use` is 1 (or empty / missing)
    to place the row and 0 to place nothing for it."""
    need = max(columns[n] for n in CSV_COLUMNS) + 1
    if len(row) < need:
        return Issue('short_row', f'Line {line}: the row has {len(row)} columns, but the header has {len(header)}; '
                     f'at least {need} are needed.', line=line)
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
            return Issue('bad_use', f'Line {line}: column use = {raw!r} must be 0 (do not place) or 1 (place).', line=line, column='use', value=raw)
        use = int(number)
    return tuple(values), name, row[columns['colname']], use


def build_plan(p, progress=lambda *args: None):
    if p.library_coll is None:
        raise ValueError('Library collection is not set.')
    if p.map_coll is None:
        raise ValueError('Map collection is not set.')
    zone = effective_zone(p)
    if not zone:
        raise ValueError('Choose the zone to import into (the Zone list at the top; not All Zones).')
    path = bpy.path.abspath(p.placement_csv)
    if not p.placement_csv or not os.path.isfile(path):
        raise ValueError(f'Placement CSV does not exist: {path or "(not set)"}')
    if p.archive_coll is not None:
        scene = bpy.context.scene
        if p.archive_coll != scene.collection and p.archive_coll not in scene.collection.children_recursive:
            raise ValueError(f'Archive To ({p.archive_coll.name}) is not in this scene.')
        if p.archive_coll in set(walk_collections(p.map_coll)) | set(walk_library(p)):
            raise ValueError(f'Archive To ({p.archive_coll.name}) must be outside the Map and the Library, '
                             f'or archived objects would count as placed or as Library meshes.')
        if not p.archive_coll.is_editable:
            raise ValueError(f'Archive To ({p.archive_coll.name}) is not editable.')
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
                    dup_names.setdefault(name, []).append(ob.name)
                else:
                    norm[name] = ob.data
                    first_of[name] = ob.name
            if i % 512 == 0:
                yield
        yield
    for name, obj_names in dup_names.items():
        issues.append(Issue('duplicate_library_name', f'Library has several objects named {name!r} after name normalization: '
                            f'{", ".join([first_of[name], *obj_names])}; the first one ({first_of[name]}) is used.', severity='warning'))
    for c in walk_collections(p.map_coll):
        plan.collections.setdefault(c.name, c)
        yield
    plan.path_index = map_collection_paths(p.map_coll)
    for i, ob in enumerate(bpy.data.objects):
        plan.object_names.add(ob.name)
        if made_by_import(ob, zone):
            plan.previous.append(ob)
        elif ob.get(ZONE_KEY) == zone:
            plan.originals.append(ob)
        if i % 1024 == 0:
            yield
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
                values, name, colname, use = parsed
                if not use:
                    plan.unused_rows += 1
                else:
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
                        else:
                            extra = ' No similar name in Library.'
                        extra += ' If it is a new mesh from Houdini, run Import New Meshes first.'
                        issues.append(Issue('missing_mesh', f'Line {line}: objname {name!r} was not found in Library '
                                            f'(name mode: {p.name_mode}).{extra} The row cannot be placed.', line=line, column='objname', value=name))
                    else:
                        tx, ty, tz, rx, ry, rz, sx, sy, sz = values
                        factor = math.pi / 180.0
                        plan.rows.append((mesh, name, (tx, ty, tz), (rx * factor, ry * factor, rz * factor), (sx, sy, sz), colname))
                        plan.row_line.append(line)
                        if colname:
                            resolve_colname(plan, p.map_coll, colname)
                            if any(not part for part in colname.split(COLNAME_SEPARATOR)) and COLNAME_SEPARATOR in colname:
                                issues.append(Issue('odd_colname', f'Line {line}: colname {colname!r} has an empty path segment; '
                                                    f'it is used as one collection name.', severity='warning', line=line,
                                                    column='colname', value=colname))
            if number % 256 == 0:
                progress('Planning CSV', number, number)
                yield
    if not p.map_coll.is_editable:
        raise ValueError('Map collection is not editable.')
    for ob in (*plan.originals, *plan.previous):
        if not ob.is_editable:
            raise ValueError(f'Object is not editable: {ob.name}')
    # Collections of the zone's original objects, in the order the exporter looks at them (all collections, then scene roots).
    old_set = set(plan.originals)
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
                raise ValueError(f'Collection is not editable: {c.name} (holds {ob.name})')
    existing = len(plan.originals) + len(plan.previous)
    if existing and len(plan.rows) * 2 < existing:
        issues.append(Issue('fewer_rows', f'The CSV places {len(plan.rows)} objects, but {zone} has {existing}. '
                            f'Everything the CSV does not list is archived or deleted: is this the whole zone?', severity='warning'))
    for path_text in sorted('/'.join(parts) for parts in plan.new_collections if '/'.join(parts) in plan.name_conflicts):
        issues.append(Issue('name_conflict', f'Collection {path_text!r}: the name {path_text.split(COLNAME_SEPARATOR)[-1]!r} is already used '
                            f'by another collection in this file, so Blender names the new one with a suffix (.001).', severity='warning'))
    return plan


def blocking_problem(p, plan):
    """'' when the import may run, else one sentence that says why not (nothing is changed)."""
    skipped = plan.invalid + plan.missing_rows
    if not plan.rows:
        return (f'The CSV has no row to place ({plan.unused_rows} rows have use = 0, {skipped} rows cannot be used). '
                f'Importing would only archive {plan.zone}.')
    if skipped and not p.skip_bad_rows:
        return (f'{plan.missing_rows} rows have no Library mesh and {plan.invalid} rows cannot be read: their objects would disappear. '
                f'Run Import New Meshes or fix the CSV, or turn on "Skip rows that cannot be placed".')
    return ''


def publish_plan(p, plan):
    errors, warnings = placement_report.counts(plan.issues)
    p.plan_archive = len(plan.originals)
    p.plan_delete = len(plan.previous)
    p.plan_create = len(plan.rows)
    p.plan_unused_rows = plan.unused_rows
    p.plan_invalid = plan.invalid
    p.plan_missing_rows = plan.missing_rows
    p.plan_missing = len(plan.unmatched)
    names = sorted(plan.unmatched)
    p.plan_names = ', '.join(names[:5]) + (f' …and {len(names)-5} more' if len(names) > 5 else '')
    p.plan_zone = plan.zone
    p.plan_collections = len(plan.new_collections)
    p.plan_block = blocking_problem(p, plan)
    p.plan_errors = errors
    p.plan_warnings = warnings
    p.plan_ready = True


def plan_summary(plan):
    return (f'{plan.zone}: archive {len(plan.originals)} original objects, delete {len(plan.previous)} from the earlier import, '
            f'place {len(plan.rows)} (use 0 rows {plan.unused_rows}), skipped {plan.missing_rows} (not in Library), invalid rows {plan.invalid}, '
            f'new collections {len(plan.new_collections)}')


class MRT_OT_ReplaceZone(ChunkedOperator, bpy.types.Operator):
    bl_description = ('Dry Run ONなら計画だけ確認します。OFFなら、ゾーンの元のObjectをすべて退避用Collectionへ移し、前回の取り込みで作ったObjectを削除して、'
                      'CSVの全行を配置します。CSVにないObjectも退避されます。元のマップへ復元できます')
    bl_idname = 'mrt.replace_zone'
    undo_push = True

    def wants_undo(self, context):
        return not context.scene.mrt_props.dry_run  # Preview changes nothing
    bl_label = 'Preview Import / Import Zone'

    def _past_cancel(self):
        """One yield that ignores ESC: the import is committed, so it has to finish (a half-deleted earlier import would be duplicated)."""
        try:
            yield
        except Cancelled:
            self._error = ''

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
        if p.dry_run:
            self.result = 'Preview ' + summary + (f' | BLOCKED: {p.plan_block}' if p.plan_block else '')
            return
        if p.plan_block:
            raise ValueError(p.plan_block)
        scene, view_layer = context.scene, context.view_layer
        zone = plan.zone
        journal = Journal()
        stale = {ob.name for ob in plan.previous}
        allocator = NameAllocator(plan.object_names - stale)  # these names are free again once the earlier import is deleted
        touched = set(plan.originals)
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
            created = []  # (object, the name it should end up with)
            for n, (mesh, name, loc, rot, scale, colname) in enumerate(plan.rows):
                wanted = allocator.take(name)
                ob = bpy.data.objects.new(wanted, mesh)
                journal.created_object(ob)
                created.append((ob, wanted))
                ob.location = loc
                ob.rotation_mode = 'XYZ'
                ob.rotation_euler = rot
                ob.scale = scale
                ob[ZONE_KEY] = zone
                ob[RUN_KEY] = json.dumps({'zone': zone, 'before': None})
                c = plan.collections[colname] if colname else p.map_coll
                c.objects.link(ob)
                self.progress('Placing CSV rows', n + 1, len(plan.rows))
                yield
            for parent, c in attach:
                parent.children.link(c)
                yield
            archive = ensure_archive(scene, view_layer, zone, journal, p.archive_coll)
            for n, ob in enumerate(plan.originals):
                old_spec = read_run(ob)
                before = old_spec['before'] if old_spec and old_spec.get('zone') == zone and isinstance(old_spec.get('before'), dict) \
                    else capture(ob, owners.get(ob, []), scene.collection)
                first = owners[ob][0] if owners.get(ob) else None
                cn = collection_colname(first, p.map_coll, parents, root_set) if first is not None else ''
                parts = colname_parts(cn, plan.map_name) if cn else ()
                apply_absent(journal, ob, archive, zone, parts, owners)
                write_run(journal, ob, {'zone': zone, 'before': before, 'after': None, 'stash': '/'.join(parts)})
                self.progress('Archiving original objects', n + 1, len(plan.originals))
                yield
            journal.prop(archive, STATE_KEY)
            archive[STATE_KEY] = STATE_AFTER
            view_layer.update()  # a single explicit update, outside the creation loops
            committed = True
            # Past the point of no return: the earlier import's objects are deleted, which cannot be rolled back. Deleting costs
            # about 10 ms per object in a big scene, so it runs in small steps (the UI stays alive) and ESC no longer cancels.
            step, total, done = 16, len(plan.previous), 0
            while done < total:
                started = time.perf_counter()
                bpy.data.batch_remove(ids=plan.previous[done:done + step])
                done += step
                step = max(8, min(1024, int(step * .25 / max(time.perf_counter() - started, 1e-3))))
                self.progress('Deleting the earlier import (ESC no longer cancels)', min(done, total), total)
                yield from self._past_cancel()
            if plan.previous:
                for n, (ob, wanted) in enumerate(created):
                    if ob.name != wanted:
                        ob.name = wanted
                    if n % 2048 == 2047:
                        yield from self._past_cancel()
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
        self.result = 'Imported ' + summary
