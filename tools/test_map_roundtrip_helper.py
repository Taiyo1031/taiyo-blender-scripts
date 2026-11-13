"""Helper panel: how Library / FromHoudini objects are used in Map.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_helper.py
"""
import importlib
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools import helper
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props


def drain(g):
    while True:
        try:
            next(g)
        except StopIteration as done:
            return done.value


def coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def mesh(name):
    m = bpy.data.meshes.new(name)
    m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    return m


def obj(name, data, collection, zone=None):
    ob = bpy.data.objects.new(name, data)
    collection.objects.link(ob)
    if zone:
        ob['ub_zone'] = zone
    return ob


bpy.data.batch_remove(ids=list(bpy.data.objects))
lib = coll('Library', scene.collection)
fh = coll('FromHoudini', lib)
mapc = coll('Map', scene.collection)
area = coll('Area1', mapc)
rock_a, rock_b, new_c = mesh('RockA'), mesh('RockB'), mesh('NewC')
lib_a, lib_b = obj('RockA', rock_a, lib), obj('RockB', rock_b, lib)
lib_c = obj('NewC', new_c, fh)
inst_a = [obj(f'a{i}', rock_a, area, 'ZONE_A') for i in range(3)] + [obj('a3', rock_a, mapc, 'ZONE_B')]
inst_c = [obj('c0', new_c, mapc), obj('c1', new_c, mapc)]
other = obj('Elsewhere', rock_b, scene.collection)  # not in Map: must not count as a use
p.library_coll, p.map_coll = lib, mapc
bpy.context.view_layer.update()


def select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def selected():
    return {o.name for o in bpy.context.view_layer.objects if o.select_get()}


def test_scan_and_usage():
    usage = drain(helper.scan_usage(p))
    a, b, c = (helper.usage_of(usage, o) for o in (lib_a, lib_b, lib_c))
    assert a['count'] == 4 and a['collections'] == {'Area1': 3, 'Map': 1}, a
    assert a['zones'] == {'ZONE_A': 3, 'ZONE_B': 1}, a
    assert b['count'] == 0 and c['count'] == 2 and c['collections'] == {'Map': 2}, (b, c)
    assert [o.name for o in helper.unused(usage)] == ['RockB']
    assert {o.name for o in helper.library_of(usage, inst_a[0])} == {'RockA'}
    assert helper.library_of(usage, other) == [] or {o.name for o in helper.library_of(usage, other)} == {'RockB'}
    print('PASS scan_usage / usage_of / unused / library_of')


def test_operators():
    assert bpy.ops.mrt.helper_scan() == {'FINISHED'}
    select([lib_a])
    assert bpy.ops.mrt.helper_select_usage() == {'FINISHED'}
    assert selected() == {'a0', 'a1', 'a2', 'a3'}, selected()
    select([inst_c[0]])
    assert bpy.ops.mrt.helper_select_library() == {'FINISHED'}
    assert selected() == {'NewC'}, selected()
    assert bpy.ops.mrt.helper_select_unused() == {'FINISHED'}
    assert selected() == {'RockB'}, selected()
    assert bpy.ops.mrt.helper_report() == {'FINISHED'}
    text = bpy.data.texts['MRT Usage Report'].as_string()
    assert 'RockA' in text and 'Area1' in text and 'ZONE_A' in text and 'RockB' in text, text
    print('PASS select usage / select library / select unused / report')


def test_select_usage_requires_scan_and_selection():
    helper.USAGE = None
    select([lib_a])
    try:
        bpy.ops.mrt.helper_select_usage()
    except RuntimeError as exc:
        assert 'Scan' in str(exc), str(exc)
    else:
        raise AssertionError('select usage must ask for a scan first')
    print('PASS selecting usage without a scan reports an error')


class Layout:
    """Accepts any layout call; row(), box(), column() return the same recorder."""
    def __init__(self):
        self.texts = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            if 'text' in kwargs:
                self.texts.append(kwargs['text'])
            return self
        return call

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_panel_draws():
    helper.USAGE = None
    for state in ('not scanned', 'scanned'):
        if state == 'scanned':
            assert bpy.ops.mrt.helper_scan() == {'FINISHED'}
        select([lib_a])
        panel = helper.MRT_PT_Helper
        layout = Layout()
        fake = type('FakePanel', (), {'layout': layout})()
        panel.draw(fake, bpy.context)
        assert layout.texts, state
    assert any('RockA' in t or '4' in t for t in layout.texts), layout.texts
    print('PASS the panel draws before and after a scan')


for test in (test_scan_and_usage, test_operators, test_select_usage_requires_scan_and_selection, test_panel_draws):
    test()
mrt.unregister()
print('MRT_HELPER_PASSED')
