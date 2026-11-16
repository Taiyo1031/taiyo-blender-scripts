"""Run with Blender --background --factory-startup --python-exit-code 1 --python
 tools/benchmark_blend_reference_graph_whole_file.py -- --objects 20000 --materials 1000.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_Taiyo_Blender_Extensions_Repo"))
from blend_reference_graph.graph import GraphData, export_graph_data
from blend_reference_graph.scanner import whole_file_scanner
from blend_reference_graph.version import VERSION


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects", type=nonnegative, default=20000)
    parser.add_argument("--materials", type=nonnegative, default=1000)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def fixture(args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.data.collections.new("Benchmark")
    bpy.context.scene.collection.children.link(collection)
    materials = []
    for index in range(args.materials):
        material = bpy.data.materials.new(f"Material_{index:06d}")
        material.use_nodes = True
        materials.append(material)
    meshes = []
    for index in range(min(args.objects, max(1, args.materials))):
        mesh = bpy.data.meshes.new(f"Mesh_{index:06d}")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        if materials:
            mesh.materials.append(materials[index % len(materials)])
        meshes.append(mesh)
    group = bpy.data.node_groups.new("SharedGeometry", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = group.nodes.new("NodeGroupInput")
    target = group.nodes.new("NodeGroupOutput")
    group.links.new(source.outputs["Geometry"], target.inputs["Geometry"])
    for index in range(args.objects):
        obj = bpy.data.objects.new(f"Object_{index:06d}", meshes[index % len(meshes)])
        collection.objects.link(obj)
        obj.modifiers.new("SharedGeometry", "NODES").node_group = group
    bpy.context.view_layer.update()
    assert len(bpy.data.objects) == args.objects
    assert len(bpy.data.materials) == args.materials


class TimedData:
    def __init__(self):
        self.calls = []
        self.result = None

    def __getattr__(self, name):
        return getattr(bpy.data, name)

    def user_map(self, *args, **kwargs):
        start = time.perf_counter()
        self.result = bpy.data.user_map(*args, **kwargs)
        self.calls.append(time.perf_counter() - start)
        return self.result


def main():
    args = arguments()
    print(f"BRG {VERSION} / Blender {bpy.app.version_string} / {platform.platform()}", flush=True)
    print(f"Fixture: objects={args.objects}, materials={args.materials}, shared GN modifier on every object", flush=True)
    start = time.perf_counter()
    fixture(args)
    setup_seconds = time.perf_counter() - start
    print(f"Fixture ready: {setup_seconds:.6f} s", flush=True)

    graph = GraphData()
    options = whole_file_scanner.ScanOptions()
    timed_data = TimedData()
    proxy = SimpleNamespace(data=timed_data, types=bpy.types)
    intervals = []
    stages = defaultdict(lambda: {"calls": 0, "seconds": 0.0, "max_seconds": 0.0})
    iterator = whole_file_scanner.iter_scan(graph, options)
    start = time.perf_counter()
    previous = start
    with patch.object(whole_file_scanner, "bpy", proxy):
        while True:
            try:
                _, message = next(iterator)
            except StopIteration:
                tail_seconds = time.perf_counter() - previous
                break
            now = time.perf_counter()
            interval = now - previous
            previous = now
            intervals.append((interval, message))
            stage = stages[message]
            stage["calls"] += 1
            stage["seconds"] += interval
            stage["max_seconds"] = max(stage["max_seconds"], interval)
    scan_seconds = time.perf_counter() - start
    assert len(timed_data.calls) == 1, timed_data.calls
    longest = max(intervals, default=(0.0, ""))

    key_types = Counter()
    pairs = Counter()
    for block, users in timed_data.result.items():
        key_types[block.bl_rna.identifier] += 1
        for user in users:
            pairs[f"{user.bl_rna.identifier} -> {block.bl_rna.identifier}"] += 1
    timed_data.result = None
    with tempfile.TemporaryDirectory(prefix="brg_benchmark_") as folder:
        start = time.perf_counter()
        _, payload = export_graph_data(graph, {"version": VERSION}, folder, compact=True)
        export_seconds = time.perf_counter() - start
        json_bytes = (Path(folder) / "graph_data.json").stat().st_size
        js_bytes = (Path(folder) / "graph_data.js").stat().st_size
        with (Path(folder) / "graph_data.json").open(encoding="utf-8") as handle:
            decoded = json.load(handle)
        assert len(decoded["nodes"]) == len(payload["nodes"])
        assert len(decoded["edges"]) == len(payload["edges"])

    report = {
        "version": VERSION, "blender": bpy.app.version_string,
        "requested": vars(args), "setup_seconds": setup_seconds,
        "options": vars(options), "iter_scan_seconds": scan_seconds,
        "yield_count": len(intervals), "max_yield_interval_seconds": longest[0],
        "max_yield_interval_ending_message": longest[1],
        "intervals_over_30ms": sum(seconds > 0.030 for seconds, _ in intervals),
        "completion_tail_seconds": tail_seconds,
        "yield_intervals_by_ending_message": dict(stages),
        "user_map_calls": len(timed_data.calls), "user_map_seconds": sum(timed_data.calls),
        "user_map_keys_by_rna_type": dict(sorted(key_types.items())),
        "user_map_reference_pairs_by_rna_type": dict(sorted(pairs.items())),
        "node_count": len(payload["nodes"]), "edge_count": len(payload["edges"]),
        "type_counts": payload["meta"]["type_counts"], "truncated": payload["meta"]["truncated"],
        "compact_json_bytes": json_bytes, "graph_data_js_bytes": js_bytes,
        "export_seconds": export_seconds,
    }
    print("Intervals include measurement overhead; ending-message buckets can span stage boundaries.")
    print("user_map is timed inside iter_scan; raw pair counts precede graph deduplication/exclusions.")
    print("The timing wrapper retains the raw user_map until scan completion for its breakdown.")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
