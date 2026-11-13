"""Rename a zone: registry, empties, objects, ub_run, the `_Replaced_<zone>` archive and its mirror collections."""
import json
import bpy
from bpy.props import StringProperty
from .constants import ARCHIVED_KEY, RUN_KEY, ZONE_KEY, ZONE_NAME_KEY
from .journal import archive_name, read_run
from .mirror import MIRROR_KEY, MIRROR_TAG_KEY, mirror_name
from .placement import walk_collections
from .zones import ensure_zone, zone_editable, zone_name


def _is_zone_empty(ob, prefix):
    return (ob.type == 'EMPTY' and ob.empty_display_type == 'CUBE'
            and (ZONE_NAME_KEY in ob or ob.name.startswith(prefix)))


def _mirrors_in_archive(archive, zone):
    """Mirror collections below the archive that carry this zone's tag (the archive itself is not one)."""
    return [c for c in walk_collections(archive)
            if c != archive and c.get(MIRROR_TAG_KEY) == zone and isinstance(c.get(MIRROR_KEY), str)]


def rename_problems(p, old, new):
    """'' when the zone can be renamed, otherwise one sentence that says why. Changes nothing."""
    new = new.strip()
    if not old or old == 'ALL':
        return 'Choose a zone first (not All Zones).'
    if not new or new == 'ALL':
        return 'Choose a nonempty zone name other than ALL.'
    if new == old:
        return 'The new name is the same as the current one.'
    if any(z.name == new for z in p.zones) or any(
            _is_zone_empty(ob, p.zone_prefix) and zone_name(ob) == new for ob in bpy.data.objects):
        return f'A zone named {new} already exists.'
    if bpy.data.collections.get(archive_name(new)) is not None:
        return f'A collection named {archive_name(new)} already exists.'
    archive = bpy.data.collections.get(archive_name(old))
    if archive is not None:
        for c in _mirrors_in_archive(archive, old):
            taken = bpy.data.collections.get(mirror_name(c[MIRROR_KEY], new))
            if taken is not None and taken != c:
                return f'A collection named {taken.name} already exists.'
    return ''


def rename_zone(p, old, new):
    """Rename after rename_problems() returned ''. Returns {'empties': n, 'objects': n, 'collections': n}."""
    new = new.strip()
    entries = [z for z in p.zones if z.name == old]
    for z in entries:
        z.name = new
    if not entries:
        ensure_zone(p, new)
    empties = objects = collections = 0
    for ob in bpy.data.objects:
        zone_empty = _is_zone_empty(ob, p.zone_prefix) and zone_name(ob) == old
        changed_object = False
        if zone_empty:
            ob[ZONE_NAME_KEY] = new
            empties += 1
        if ob.get(ZONE_KEY) == old:
            ob[ZONE_KEY] = new
            changed_object = True
        if ob.get(ARCHIVED_KEY) == old:
            ob[ARCHIVED_KEY] = new
            changed_object = True
        spec = read_run(ob)
        if spec and spec.get('zone') == old:
            spec['zone'] = new
            ob[RUN_KEY] = json.dumps(spec)
            changed_object = True
        if zone_empty or changed_object:
            ob.update_tag()  # a property-only edit is not tracked by Undo without this
        objects += changed_object
    archive = bpy.data.collections.get(archive_name(old))
    if archive is not None:
        mirrors = _mirrors_in_archive(archive, old)  # listed before anything is renamed
        archive.name = archive_name(new)
        collections += 1
        for c in mirrors:
            c[MIRROR_TAG_KEY] = new
            c.name = mirror_name(c[MIRROR_KEY], new)
            collections += 1
    if p.zone_override.strip() == old:
        p.zone_override = new
    p.zone_choice = new
    p.zone_result = ''
    return {'empties': empties, 'objects': objects, 'collections': collections}


class MRT_OT_RenameZone(bpy.types.Operator):
    bl_idname = 'mrt.rename_zone'
    bl_label = 'Rename Zone'
    bl_description = '選んだゾーンの名前を変更します。ゾーンのEmpty・Object・退避用Collectionの名前も一緒に更新します。CSVのファイル名は変わりません'
    bl_options = {'REGISTER', 'UNDO'}
    old_name: StringProperty(name='Zone', description='変更前のゾーン名')
    new_name: StringProperty(name='New Name', description='変更後のゾーン名。例：ZONE_B。配置CSVのファイル名と揃えると便利です')

    @classmethod
    def poll(cls, context):
        return zone_editable(context)

    def invoke(self, context, event):
        if not self.old_name:
            self.old_name = context.scene.mrt_props.zone_choice  # one read: the enum scans every empty
        self.new_name = self.old_name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        p = context.scene.mrt_props
        old, new = self.old_name, self.new_name.strip()
        problem = rename_problems(p, old, new)
        if problem:
            self.report({'ERROR'}, problem)
            return {'CANCELLED'}
        counts = rename_zone(p, old, new)
        self.report({'INFO'}, f'Renamed {old} to {new}: {counts["empties"]} empties, '
                              f'{counts["objects"]} objects, {counts["collections"]} collections.')
        return {'FINISHED'}
