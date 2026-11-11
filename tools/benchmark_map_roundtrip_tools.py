"""Background benchmarks. JSON output path can be passed after --."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
import map_roundtrip_tools as mrt
import unreal_bridge_tools as ubt
from map_roundtrip_tools import placement
from map_roundtrip_tools.zones import collect_zone_boxes, points_of, inside_mask

spec = importlib.util.spec_from_file_location('bench_scene', ROOT / '_Taiyo_Blender_Extensions_Repo/map_roundtrip_tools/tools/bench_make_scene.py')
bench_scene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench_scene)
TEMP = Path(tempfile.mkdtemp(prefix='mrt-bench-'))
output = Path(sys.argv[sys.argv.index('--')+1]) if '--' in sys.argv else Path('/tmp/map_roundtrip_benchmark.json')
results = {'blender': bpy.app.version_string, 'runs': [], 'temp':str(TEMP)}


def drain(g):
    while True:
        try:
            next(g)
        except StopIteration as end:
            return end.value


def run(n):
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    lib, mapc, objects = bench_scene.make_scene(50, n, 4)
    bpy.context.view_layer.update()
    p, u = bpy.context.scene.mrt_props, bpy.context.scene.ubt_props
    row = {'count':n}
    for o in objects:
        o.select_set(True)
    bpy.ops.mrt.new_zone(name=f'ZONE_{n}')
    p.zone_csv_dir = str(TEMP)
    u.collection = None
    u.filters.clear()
    u.name_mode = 'numeric_suffix'
    u.export_path = str(TEMP / f'ZONE_{n}.csv')
    u.tag_zone = True
    t = time.perf_counter()
    bpy.ops.mrt.export_zone_csv()
    row['csv_selected_seconds'] = time.perf_counter()-t
    u.scope = 'recursive'
    u.collection = mapc
    t = time.perf_counter()
    bpy.ops.ubt.export_csv()
    row['csv_collection_seconds'] = time.perf_counter()-t
    p.placement_csv = u.export_path
    p.zone_override = ''
    p.old_mode = 'ARCHIVE'
    p.dry_run = True
    t = time.perf_counter()
    plan = drain(placement.build_plan(p))
    row['plan_seconds'] = time.perf_counter()-t
    assert len(plan.rows) == len(plan.old) == n
    p.dry_run = False
    # Measure actual phases separately while using the production generator.
    class H:
        _error = ''
        def report(self, *args): pass
        def progress(self, phase, done, total): self.phase = phase
    h = H()
    g = placement.MRT_OT_ReplaceZone.work(h, bpy.context)
    times = {}
    max_step = 0
    t = time.perf_counter()
    while True:
        begin = time.perf_counter()
        phase = getattr(h, 'phase', 'Plan')
        try:
            next(g)
        except StopIteration:
            break
        elapsed = time.perf_counter()-begin
        times[phase] = times.get(phase, 0) + elapsed
        max_step = max(max_step, elapsed)
    row['replace_seconds'] = time.perf_counter()-t
    row['phases'] = times
    row['max_uninterruptible_step_seconds'] = max_step
    assert sum(o.get('ub_zone') == f'ZONE_{n}' for o in bpy.data.objects) == n
    results['runs'].append(row)
    output.write_text(json.dumps(results, indent=2))
    print('BENCH_RESULT', json.dumps(row), flush=True)


mrt.register()
ubt.register()
for n in (10000, 30000, 60000):
    run(n)
# Pure numpy membership for 100k origins and all boxes, separate extraction time.
pts = np.ones((100000,4),dtype=np.float64)
pts[:,:3] = np.random.default_rng(42).uniform(-100,100,(100000,3))
zones = collect_zone_boxes(bpy.context.scene, 'ZONE_')
t = time.perf_counter()
for boxes in zones.values():
    inside_mask(pts,boxes)
results['numpy_100k_seconds'] = time.perf_counter()-t
output.write_text(json.dumps(results,indent=2))
print('BENCH_COMPLETE',output,results['numpy_100k_seconds'],flush=True)
ubt.unregister()
mrt.unregister()
