"""Cooperative HRM benchmarks. JSON output outside the repository is passed after --."""
import json
import resource
import sys
import time
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
import hierarchy_restriction_manager as addon
from hierarchy_restriction_manager import engine, operators, state
from hierarchy_restriction_manager.definitions import modes_with

output = Path(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv else Path('/tmp/hrm-benchmark.json')
results = []
root = bpy.data.collections.new('HRM Benchmark')
bpy.context.scene.collection.children.link(root)
layer = bpy.context.view_layer
count = 0
collection = None


def measure(cfg, label, preview=False):
    job = engine.Job(cfg, preview=preview, detailed=False)
    it = job.run()
    ticks, max_tick, longest_write_tick = 0, 0, 0
    start = time.perf_counter()
    while True:
        tick_start = time.perf_counter()
        try:
            for i in range(1000):
                next(it)
                if time.perf_counter() - tick_start >= 0.008:
                    break
        except StopIteration:
            break
        tick = time.perf_counter() - tick_start
        max_tick = max(max_tick, tick)
        ticks += 1
    elapsed = time.perf_counter() - start
    result = dict(label=label, objects=count, seconds=round(elapsed, 4), max_tick_ms=round(max_tick*1000, 3),
                  ticks=ticks, writes=job.stats.writes, unique_objects=job.stats.objects,
                  rss_peak_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 1))
    results.append(result)
    output.write_text(json.dumps(results, indent=2))
    print('BENCH', json.dumps(result), flush=True)
    job.journal.clear()
    return result


def measure_cancel():
    settings = bpy.context.scene.hrm_settings
    settings.target = root
    settings.include_root = settings.child_collections = False
    settings.render_enabled = 'OFF'
    session = operators.Session(bpy.context, 'APPLY', True)
    state.ACTIVE = session
    while session.stats.writes < count // 2:
        assert not session.finished
        session.step()
    writes = session.stats.writes
    requested = time.perf_counter()
    session.cancel_requested = True
    session.step()
    first_tick = time.perf_counter() - requested
    assert session.canceling
    while not session.finished:
        session.step()
    elapsed = time.perf_counter() - requested
    assert state.ACTIVE is None and session.stats.errors == 0
    assert all(not obj.hide_render for child in root.children for obj in child.objects)
    result = dict(label='cancel_half_applied', objects=count, restored_writes=writes,
                  first_rollback_tick_ms=round(first_tick * 1000, 3), restore_seconds=round(elapsed, 4),
                  rss_peak_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, 1))
    results.append(result)
    output.write_text(json.dumps(results, indent=2))
    print('BENCH', json.dumps(result), flush=True)


if '--structure' in sys.argv:
    for target_count in (100, 1000, 10000):
        while len(root.children) < target_count:
            i = len(root.children)
            child = bpy.data.collections.new(f'HRM_Collection_{i:05d}')
            root.children.link(child)
            for j in range(10):
                child.objects.link(bpy.data.objects.new(f'HRM_Structure_{i:05d}_{j}', None))
                count += 1
        result = measure(engine.Config(root, layer, modes_with({'holdout': 'INVERT'}), objects=False), f'holdout_{target_count}_collections')
        assert result['unique_objects'] == 0
    deep_root = bpy.data.collections.new('HRM Deep')
    parent = deep_root
    for depth in range(1100):
        child = bpy.data.collections.new(f'HRM_Depth_{depth:04d}')
        parent.children.link(child)
        parent = child
    bpy.context.scene.collection.children.link(deep_root)
    result = measure(engine.Config(deep_root, layer, modes_with({'render_enabled': 'OFF'}), objects=False), 'depth_1100')
    assert result['writes'] == 1101
    print('HRM STRUCTURE BENCHMARK COMPLETE', flush=True)
    sys.exit(0)

addon.register()
for total in (10000, 50000, 100000, 250000, 500000):
    start = time.perf_counter()
    while count < total:
        if count % 1000 == 0:
            collection = bpy.data.collections.new('Chunk')
            root.children.link(collection)
        obj = bpy.data.objects.new(f'HRM_Object_{count:06d}', None)
        collection.objects.link(obj)
        count += 1
    print('FIXTURE', count, round(time.perf_counter() - start, 2), flush=True)
    if '--cancel-only' in sys.argv:
        measure_cancel()
        continue
    cfg = engine.Config(root, layer, modes_with({'render_enabled': 'OFF'}), include_root=False, child_collections=False)
    measure(cfg, 'render_off')
    result = measure(cfg, 'unchanged_render_off')
    assert result['writes'] == 0
    measure(engine.Config(root, layer, modes_with({})), 'all_keep')
    measure(cfg, 'fast_count', preview=True)
    filtered = engine.Config(root, layer, modes_with({'render_enabled': 'INVERT'}), include_root=False, child_collections=False,
                             use_filters=True, object_include='HRM_Object', object_match='REGEX')
    measure(filtered, 'regex_invert')
    measure_cancel()
addon.unregister()
print('HRM BENCHMARK COMPLETE', flush=True)
