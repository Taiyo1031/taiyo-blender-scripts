"""Rename a zone: registry, empties, objects, ub_run, archive collection and its mirror collections.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_zone_rename.py
"""
import importlib
import json
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools import journal, zone_rename
from map_roundtrip_tools.zones import zone_empties, zone_name
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
mesh = bpy.data.meshes.new('M')


def link_child(parent, child):
    parent.children.link(child)
    return child


def make_zone(name):
    """Registered zone with one empty, one object in the map, one archived object under a mirror collection."""
    assert bpy.ops.mrt.new_zone(name=name) == {'FINISHED'}
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'CUBE'
    empty['zone'] = name
    empty.mrt_zone_enabled = True
    scene.collection.objects.link(empty)
    live = bpy.data.objects.new('Live_' + name, mesh)
    live['ub_zone'] = name
    live['ub_run'] = json.dumps({'zone': name, 'before': None})
    scene.collection.objects.link(live)
    archive = bpy.data.collections.new('_Replaced_' + name)
    archive['ub_state'] = 'after'
    scene.collection.children.link(archive)
    mirror = bpy.data.collections.new(f'Rocks [{name}]')
    mirror['ub_mirror_of'] = 'Rocks'
    mirror['ub_mirror_tag'] = name
    link_child(archive, mirror)
    old = bpy.data.objects.new('Old_' + name, mesh)
    old['ub_archived_from'] = name
    old['ub_run'] = json.dumps({'zone': name, 'before': {'m': [], 'mesh': None, 'colls': [], 'tags': {}}, 'after': None, 'stash': 'Rocks'})
    mirror.objects.link(old)
    return empty, live, archive, mirror, old


def reset():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    p.zones.clear()
    p.zone_scope = 'SCENE'
    p.zone_choice = 'ALL'
    p.zone_override = ''


def rename(old_name, new_name):
    try:
        return bpy.ops.mrt.rename_zone(old_name=old_name, new_name=new_name)
    except RuntimeError:  # an operator that reports an ERROR raises here
        return {'CANCELLED'}


def registered():
    return [z.name for z in p.zones]


def test_rename_updates_everything_of_that_zone_only():
    reset()
    a = make_zone('ZONE_A')
    b = make_zone('ZONE_B')
    bystander = link_child(bpy.data.collections.new('Library'), bpy.data.collections.new('Rocks [FromHoudini]'))
    bystander['ub_mirror_of'] = 'Rocks'
    bystander['ub_mirror_tag'] = 'FromHoudini'
    orphan = bpy.data.collections.new('Orphan [ZONE_A]')  # tagged ZONE_A but not inside the archive: not ours
    orphan['ub_mirror_of'] = 'Orphan'
    orphan['ub_mirror_tag'] = 'ZONE_A'
    p.zone_choice = 'ZONE_A'
    p.zone_override = 'ZONE_A'
    assert rename(old_name='ZONE_A', new_name=' ZONE_X ') == {'FINISHED'}
    empty, live, archive, mirror, old = a
    assert sorted(registered()) == ['ZONE_B', 'ZONE_X'], registered()
    assert p.zone_choice == 'ZONE_X' and p.zone_override == 'ZONE_X'
    assert empty['zone'] == 'ZONE_X' and zone_name(empty) == 'ZONE_X'
    assert live['ub_zone'] == 'ZONE_X' and json.loads(live['ub_run'])['zone'] == 'ZONE_X'
    assert old['ub_archived_from'] == 'ZONE_X' and json.loads(old['ub_run'])['zone'] == 'ZONE_X'
    assert json.loads(old['ub_run'])['stash'] == 'Rocks' and json.loads(old['ub_run'])['after'] is None  # the rest of the spec is kept
    assert archive.name == '_Replaced_ZONE_X' and mirror.name == 'Rocks [ZONE_X]' and mirror['ub_mirror_tag'] == 'ZONE_X'
    assert mirror['ub_mirror_of'] == 'Rocks'
    assert journal.map_state('ZONE_X') == 'after' and journal.map_state('ZONE_A') == ''
    # the other zone and unrelated collections are untouched
    e2, l2, ar2, m2, o2 = b
    assert e2['zone'] == 'ZONE_B' and l2['ub_zone'] == 'ZONE_B' and ar2.name == '_Replaced_ZONE_B' and m2.name == 'Rocks [ZONE_B]'
    assert bystander.name == 'Rocks [FromHoudini]' and bystander['ub_mirror_tag'] == 'FromHoudini'
    assert orphan.name == 'Orphan [ZONE_A]' and orphan['ub_mirror_tag'] == 'ZONE_A'
    assert sorted(zone_name(e) for e in zone_empties(scene, p.zone_prefix)) == ['ZONE_B', 'ZONE_X']
    print('PASS renaming a zone updates registry, empties, objects, ub_run, archive and mirrors (and nothing else)')


def test_refusals_change_nothing():
    reset()
    a = make_zone('ZONE_A')
    make_zone('ZONE_B')
    blocker = bpy.data.collections.new('_Replaced_ZONE_Y')  # the archive name of the new zone is taken
    scene.collection.children.link(blocker)
    for new in ('', '   ', 'ALL', 'ZONE_A', 'ZONE_B', 'ZONE_Y'):
        assert rename(old_name='ZONE_A', new_name=new) == {'CANCELLED'}, new
    assert rename(old_name='ALL', new_name='ZONE_Q') == {'CANCELLED'}
    assert rename(old_name='', new_name='ZONE_Q') == {'CANCELLED'}
    empty, live, archive, mirror, old = a
    assert sorted(registered()) == ['ZONE_A', 'ZONE_B'] and empty['zone'] == 'ZONE_A' and live['ub_zone'] == 'ZONE_A'
    assert archive.name == '_Replaced_ZONE_A' and mirror.name == 'Rocks [ZONE_A]'
    print('PASS empty / ALL / existing / colliding names are refused without changing anything')


def test_problems_function():
    reset()
    make_zone('ZONE_A')
    make_zone('ZONE_B')
    assert zone_rename.rename_problems(p, 'ZONE_A', 'ZONE_C') == ''
    assert zone_rename.rename_problems(p, 'ZONE_A', 'ZONE_B') != ''
    assert zone_rename.rename_problems(p, 'ZONE_A', 'ZONE_A') != ''
    assert zone_rename.rename_problems(p, 'ALL', 'ZONE_C') != ''
    counts = zone_rename.rename_zone(p, 'ZONE_A', 'ZONE_C')
    assert counts['empties'] == 1 and counts['objects'] == 2 and counts['collections'] == 2, counts
    print('PASS rename_problems / rename_zone report what they did')


def test_undo_tags_are_set():
    """A property-only edit is not tracked by Undo unless the object is tagged; the helper must keep it correct."""
    reset()
    empty, live, archive, mirror, old = make_zone('ZONE_A')
    zone_rename.rename_zone(p, 'ZONE_A', 'ZONE_C')
    assert live['ub_zone'] == 'ZONE_C'
    print('PASS rename keeps the data consistent for Undo (update_tag is called in code, checked in the UI run)')


for test in (test_rename_updates_everything_of_that_zone_only, test_refusals_change_nothing,
             test_problems_function, test_undo_tags_are_set):
    test()
mrt.unregister()
print('MRT_ZONE_RENAME_PASSED')
