"""Zones panels: order, fixed rows, capped empty list. Uses a recording stub layout."""
import importlib
from pathlib import Path
import sys
import time
import types
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
ui = importlib.import_module('map_roundtrip_tools.ui_zones')
from map_roundtrip_tools.constants import ZONE_NAME_KEY
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
LAYOUTS = {'row', 'column', 'box', 'split', 'column_flow', 'grid_flow'}


class Rec:
    def __init__(self, log):
        object.__setattr__(self, '_log', log)

    def __setattr__(self, name, value):  # enabled, scale_y, operator_context ...
        self._log.append(('set:' + name, (value,), {}))

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self._log.append((name, args, kwargs))
            if name in LAYOUTS:
                return Rec(self._log)
            if name == 'operator':
                return types.SimpleNamespace()
            return None
        return call


def draw(panel):
    log = []
    stub = types.SimpleNamespace(layout=Rec(log))
    panel.draw(stub, bpy.context)
    return log


def ops(log):
    return [kw.get('operator', a[0]) if False else a[0] for name, a, kw in log if name == 'operator']


def calls(log, name):
    return [(a, kw) for n, a, kw in log if n == name]


# --- panel classes and hierarchy
expected = ['MRT_PT_Zones', 'MRT_PT_ZoneRange', 'MRT_PT_ZoneEmpties', 'MRT_PT_ZoneCheck', 'MRT_PT_ZoneCSV', 'MRT_PT_ZoneAdvanced']
for name in expected:
    assert issubclass(getattr(ui, name), bpy.types.Panel), name
parent = ui.MRT_PT_Zones
assert parent.bl_idname == 'MRT_PT_zones' and parent.bl_category == 'Map Roundtrip'
children = [getattr(ui, n) for n in expected[1:]]
assert all(c.bl_parent_id == 'MRT_PT_zones' for c in children)
assert [c.bl_order for c in children] == sorted(c.bl_order for c in children)
assert ui.MRT_PT_ZoneRange.bl_label.startswith('1.') and ui.MRT_PT_ZoneCheck.bl_label.startswith('2.') and ui.MRT_PT_ZoneCSV.bl_label.startswith('3.')
for c in (ui.MRT_PT_ZoneEmpties, ui.MRT_PT_ZoneCheck, ui.MRT_PT_ZoneAdvanced):
    assert 'DEFAULT_CLOSED' in c.bl_options
assert 'DEFAULT_CLOSED' not in getattr(ui.MRT_PT_ZoneRange, 'bl_options', set())
assert 'DEFAULT_CLOSED' not in getattr(ui.MRT_PT_ZoneCSV, 'bl_options', set())

# --- scene: one zone with many empties
bpy.data.batch_remove(ids=list(bpy.data.objects))
p.zones.clear()
assert bpy.ops.mrt.new_zone(name='ZONE_A') == {'FINISHED'}
for i in range(5000):
    e = bpy.data.objects.new(f'E{i:04d}', None)
    e.empty_display_type = 'CUBE'
    e[ZONE_NAME_KEY] = 'ZONE_A'
    scene.collection.objects.link(e)
p.zone_choice = 'ZONE_A'
p.zone_scope = 'MAP'

# parent: selector, always-one status row, no progress when idle
log = draw(ui.MRT_PT_Zones)
assert ('zone_choice' in [a[1] for n, a, kw in log if n == 'prop']), 'zone selector'
assert 'mrt.new_zone' in ops(log)
assert any(n == 'prop' and a[1] == 'map_coll' for n, a, kw in log), 'map collection shown for MAP scope'
assert len(calls(log, 'label')) == 1 and not calls(log, 'progress')
p.zone_scope = 'SCENE'
assert not any(n == 'prop' and a[1] == 'map_coll' for n, a, kw in draw(ui.MRT_PT_Zones))
p.running = True
log = draw(ui.MRT_PT_Zones)
assert calls(log, 'progress') and not calls(log, 'label')
p.running = False

# range panel: primary button first, then helpers
log = draw(ui.MRT_PT_ZoneRange)
assert ops(log)[0] == 'mrt.add_objects_to_zone'
assert set(ops(log)) == {'mrt.add_objects_to_zone', 'mrt.add_zone_empty', 'mrt.register_zone_empties'}
assert any(n == 'prop' and a[1] == 'merge_distance' for n, a, kw in log)

# empties panel: capped list even with 5000 empties, and search narrows it
start = time.perf_counter()
log = draw(ui.MRT_PT_ZoneEmpties)
elapsed = time.perf_counter() - start
rows = [a for n, a, kw in log if n == 'operator' and a[0] == 'mrt.zone_empty_action']
assert len(rows) == 100, len(rows)  # 50 empties x (select + unregister)
assert any('more' in kw.get('text', '') for n, a, kw in log if n == 'label'), 'overflow hint'
assert elapsed < 1.0, elapsed
p.zone_empty_filter = 'e0042'
log = draw(ui.MRT_PT_ZoneEmpties)
assert len([1 for n, a, kw in log if n == 'operator' and a[0] == 'mrt.zone_empty_action']) == 2
assert any('1 empties' in kw.get('text', '') or '1 empty' in kw.get('text', '') for n, a, kw in log if n == 'label')
p.zone_empty_filter = 'no-such-empty'
log = draw(ui.MRT_PT_ZoneEmpties)
assert not [1 for n, a, kw in log if n == 'operator' and a[0] == 'mrt.zone_empty_action']
assert any('No Empty' in kw.get('text', '') for n, a, kw in log if n == 'label')
p.zone_empty_filter = ''

# check panel: fixed result row
p.zone_result = ''
log = draw(ui.MRT_PT_ZoneCheck)
assert ops(log) == ['mrt.select_in_zone'] and len(calls(log, 'label')) == 1
p.zone_result = 'Result: ZONE_A 3'
assert calls(draw(ui.MRT_PT_ZoneCheck), 'label')[0][1]['text'] == 'Result: ZONE_A 3'

# CSV panel: button text follows the Zone selector
log = draw(ui.MRT_PT_ZoneCSV)
button = [kw for n, a, kw in log if n == 'operator' and a[0] == 'mrt.export_zone_csv'][0]
assert button['text'] == 'Export ZONE_A.csv'
p.zone_choice = 'ALL'
button = [kw for n, a, kw in draw(ui.MRT_PT_ZoneCSV) if n == 'operator'][0]
assert button['text'] == 'Export CSV (every zone)'
for key in ('zone_csv_dir', 'name_mode'):
    assert any(n == 'prop' and a[1] == key for n, a, kw in log), key

# advanced panel
assert any(n == 'prop' and a[1] == 'zone_prefix' for n, a, kw in draw(ui.MRT_PT_ZoneAdvanced))
print('ZONES_UI_LAYOUT_TESTS_PASSED', flush=True)
mrt.unregister()
