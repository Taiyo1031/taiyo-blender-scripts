"""Plan first; create linked objects; commit archive/delete last."""
import csv
import math
import os
import re
from dataclasses import dataclass, field
import bpy
from .constants import ZONE_KEY, ARCHIVED_KEY, CSV_COLUMNS
from .chunked import ChunkedOperator


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


def effective_zone(p):
    return p.zone_override.strip() or os.path.splitext(os.path.basename(bpy.path.abspath(p.placement_csv)))[0]


@dataclass
class Plan:
    zone: str
    rows: list = field(default_factory=list)
    old: list = field(default_factory=list)
    collections: dict = field(default_factory=dict)
    new_collections: set = field(default_factory=set)
    unmatched: set = field(default_factory=set)
    missing_rows: int = 0
    invalid: int = 0
    duplicates: int = 0
    memberships: list = field(default_factory=list)
    object_names: set = field(default_factory=set)


def build_plan(p, progress=lambda *args: None):
    if p.library_coll is None:
        raise ValueError('Library collection is not set.')
    if p.map_coll is None:
        raise ValueError('Map collection is not set.')
    path = bpy.path.abspath(p.placement_csv)
    if not p.placement_csv or not os.path.isfile(path):
        raise ValueError('Placement CSV does not exist.')
    zone = effective_zone(p)
    if not zone:
        raise ValueError('Zone name is empty.')
    plan = Plan(zone)
    exact, norm, seen = {}, {}, set()
    for c in walk_collections(p.library_coll):
        for i, ob in enumerate(c.objects):
            if ob not in seen and ob.type == 'MESH':
                seen.add(ob)
                exact[ob.name] = ob.data
                name = normalize(ob.name, p.name_mode)
                if name in norm:
                    plan.duplicates += 1
                else:
                    norm[name] = ob.data
            if i % 512 == 0:
                yield
        yield
    for c in walk_collections(p.map_coll):
        plan.collections.setdefault(c.name, c)
        yield
    with open(path, newline='', encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        columns = {name: i for i, name in enumerate(header)}
        missing = set(CSV_COLUMNS) - columns.keys()
        if missing:
            raise ValueError('Missing CSV columns: ' + ', '.join(sorted(missing)))
        indices = [columns[n] for n in CSV_COLUMNS[1:10]]
        for number, row in enumerate(reader, 1):
            try:
                values = tuple(float(row[i]) for i in indices)
                if not all(math.isfinite(v) for v in values):
                    raise ValueError('Non-finite transform')
                name, colname = row[columns['objname']], row[columns['colname']]
            except (ValueError, IndexError):
                plan.invalid += 1
            else:
                mesh = exact.get(name)
                if mesh is None:
                    mesh = norm.get(normalize(name, p.name_mode))
                if mesh is None:
                    plan.unmatched.add(name)
                    plan.missing_rows += 1
                else:
                    tx, ty, tz, rx, ry, rz, sx, sy, sz = values
                    factor = math.pi / 180.0
                    plan.rows.append((mesh, name, (tx, ty, tz), (rx * factor, ry * factor, rz * factor), (sx, sy, sz), colname))
                    if colname and colname not in plan.collections:
                        plan.new_collections.add(colname)
            if number % 256 == 0:
                progress('Planning CSV', number, number)
                yield
    for i, ob in enumerate(bpy.data.objects):
        plan.object_names.add(ob.name)
        if ob.get(ZONE_KEY) == zone:
            plan.old.append(ob)
        if i % 1024 == 0:
            yield
    # Snapshot membership by collection, never per-object users_collection.
    if not p.map_coll.is_editable:
        raise ValueError('Map collection is not editable.')
    for ob in plan.old:
        if not ob.is_editable:
            raise ValueError(f'Old object is not editable: {ob.name}')
    old_set = set(plan.old)
    roots = {scene.collection for scene in bpy.data.scenes}
    for c in (*bpy.data.collections, *roots):
        members = []
        for i, ob in enumerate(c.objects):
            if ob in old_set:
                members.append(ob)
            if i % 1024 == 0:
                yield
        if members:
            if not c.is_editable:
                raise ValueError(f'Old collection is not editable: {c.name}')
            plan.memberships.append((c, members))
        yield
    return plan


def publish_plan(p, plan):
    p.plan_archive = len(plan.old)
    p.plan_create = len(plan.rows)
    p.plan_invalid = plan.invalid
    p.plan_missing_rows = plan.missing_rows
    p.plan_missing = len(plan.unmatched)
    names = sorted(plan.unmatched)
    p.plan_names = ', '.join(names[:5]) + (f' …and {len(names)-5} more' if len(names) > 5 else '')
    p.plan_zone = plan.zone
    p.plan_collections = len(plan.new_collections)
    p.plan_ready = True


def find_layer(root, collection):
    pending = [root]
    while pending:
        layer = pending.pop()
        if layer.collection == collection:
            return layer
        pending.extend(layer.children)
    return None


class MRT_OT_ReplaceZone(ChunkedOperator, bpy.types.Operator):
    bl_description = 'Dry Run ONなら計画のみ確認。OFFなら同じub_zoneの旧配置を退避または削除して新配置を作ります'
    bl_idname = 'mrt.replace_zone'
    bl_label = 'Preview Placement / Replace Zone'

    def work(self, context):
        p = context.scene.mrt_props
        p.plan_ready = False
        plan = yield from build_plan(p, self.progress)
        publish_plan(p, plan)
        if plan.duplicates:
            self.report({'WARNING'}, f'{plan.duplicates} duplicate normalized Library names; first match used.')
        if p.dry_run:
            self.result = f'Preview {plan.zone}: {len(plan.rows)} instances, {len(plan.old)} old objects, {plan.invalid} invalid rows'
            return
        created, collections, archived, unlinked, remapped_tags = [], [], [], [], []
        archive = None
        archive_created = False
        archive_layer = None
        prior_exclude = None
        committed = False
        old_mode = p.old_mode
        allocator = NameAllocator(plan.object_names)
        old_tags = {ob: (ARCHIVED_KEY in ob, ob.get(ARCHIVED_KEY)) for ob in plan.old}
        old_set = set(plan.old)
        old_states, hidden_objects = [], []
        original_active = context.view_layer.objects.active
        for i, ob in enumerate(context.view_layer.objects):
            hidden = ob.hide_get()
            if hidden:
                hidden_objects.append(ob)
            if ob in old_set:
                old_states.append((ob, hidden, ob.select_get()))
            if i % 512 == 0:
                yield
        try:
            for name in sorted(plan.new_collections):
                c = bpy.data.collections.new(name)
                collections.append(c)
                # Fill new collections while detached to avoid view-layer resync.
                plan.collections[name] = c
                yield
            for i, (mesh, name, loc, rot, scale, colname) in enumerate(plan.rows):
                ob = bpy.data.objects.new(allocator.take(name), mesh)
                created.append(ob)
                ob.location = loc
                ob.rotation_mode = 'XYZ'
                ob.rotation_euler = rot
                ob.scale = scale
                ob[ZONE_KEY] = plan.zone
                c = plan.collections[colname] if colname else p.map_coll
                c.objects.link(ob)
                self.progress('Creating linked instances', i + 1, len(plan.rows))
                yield
            for c in collections:
                p.map_coll.children.link(c)
                yield
            # A single explicit update, outside the creation loop.
            context.view_layer.update()
            if old_mode == 'ARCHIVE' and plan.old:
                archive_name = '_Replaced_' + plan.zone
                archive = context.scene.collection.children.get(archive_name)
                if archive is None:
                    archive = bpy.data.collections.new(archive_name)
                    archive_created = True
                    context.scene.collection.children.link(archive)
                archive_layer = find_layer(context.view_layer.layer_collection, archive)
                if archive_layer:
                    prior_exclude = archive_layer.exclude
                    archive_layer.exclude = True
                archive_members = set(archive.objects)
                for i, ob in enumerate(plan.old):
                    if ob not in archive_members:
                        archive.objects.link(ob)
                        archived.append(ob)
                    self.progress('Archiving', i + 1, len(plan.old))
                    yield
                for c, members in plan.memberships:
                    if c == archive:
                        continue
                    for ob in members:
                        c.objects.unlink(ob)
                        unlinked.append((c, ob))
                        yield
                for ob in plan.old:
                    remapped_tags.append(ob)
                    ob[ARCHIVED_KEY] = plan.zone
                    del ob[ZONE_KEY]
                    yield
            elif old_mode == 'DELETE' and plan.old:
                # Final irreversible operation. No cancellable step follows.
                bpy.data.batch_remove(ids=plan.old)
            committed = True
        except BaseException as exc:
            if not committed:
                # Cancellation is deferred while restoration is in progress.
                self.progress('Rolling back', 0, len(created) + len(unlinked))
                for c, ob in reversed(unlinked):
                    c.objects.link(ob)
                    yield
                for ob in remapped_tags:
                    ob[ZONE_KEY] = plan.zone
                    existed, value = old_tags[ob]
                    if existed:
                        ob[ARCHIVED_KEY] = value
                    elif ARCHIVED_KEY in ob:
                        del ob[ARCHIVED_KEY]
                    yield
                for ob in archived:
                    archive.objects.unlink(ob)
                    yield
                # Batches keep rollback responsive as well.
                for start in range(0, len(created), 512):
                    bpy.data.batch_remove(ids=created[start:start + 512])
                    yield
                if collections:
                    bpy.data.batch_remove(ids=collections)
                if archive_created:
                    bpy.data.collections.remove(archive)
                elif archive_layer is not None and prior_exclude is not None:
                    archive_layer.exclude = prior_exclude
                # Membership/exclude changes recreate Bases and may lose their
                # temporary hide and selection flags. All reads preceded writes.
                for ob, hidden, selected in old_states:
                    ob.hide_set(hidden)
                    ob.select_set(selected)
                    yield
                for ob in hidden_objects:
                    ob.hide_set(True)
                    yield
                context.view_layer.objects.active = original_active
                self._error = f'Rolled back {len(created)} objects. ' + (self._error or str(exc) or 'Operation failed.')
            raise
        self.result = (f'Replaced {plan.zone}: created {len(created)}, '
                       f'{"archived" if old_mode == "ARCHIVE" else "deleted"} {len(plan.old)}, '
                       f'skipped {plan.missing_rows} (not in Library), invalid rows {plan.invalid}')
