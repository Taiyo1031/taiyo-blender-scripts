"""Create deterministic Whole File viewer data without importing Blender.

Usage: python3 make_synthetic_graph.py /tmp/brg-preview/graph_data.js
Copy viewer.html, viewer.css and viewer.js beside the generated file to view it.
With no output argument, a new system temporary directory is used.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import tempfile


TYPES = (
    "OBJECT", "MESH", "MATERIAL", "COLLECTION", "ARMATURE", "BONE",
    "CONSTRAINT", "MODIFIER", "GEONODES", "NODEGROUP", "IMAGE", "ACTION",
    "DRIVER", "LIBRARY", "SCENE", "WORLD", "CAMERA", "LIGHT", "CURVE",
    "TEXT", "FONT", "SOUND", "PARTICLE", "TEXTURE", "OTHER",
)
WEIGHTS = (60, 20, 5, 4) + (1,) * (len(TYPES) - 4)


def make_graph(node_count=20_000, edge_count=60_000, seed=2020):
    rng = random.Random(seed)
    nodes = []
    for index in range(node_count):
        node_type = TYPES[index] if index < len(TYPES) else rng.choices(TYPES, WEIGHTS)[0]
        name = f"{node_type.title()}_{index:05d}"
        orphan = index % 17 == 0
        nodes.append({
            "id": f"{node_type.title()}:{name}", "type": node_type,
            "group": node_type, "name": name, "label": name,
            "path": f"Synthetic/Area_{index % 32:02d}/{name}",
            "details": {"users": 0, "use_fake_user": index % 19 == 0 and not orphan,
                        "orphan": orphan, "sample": index, "note": f"search_sample_{index:05d}"},
        })
    candidates = [index for index, node in enumerate(nodes) if not node["details"]["orphan"]]
    if edge_count > len(candidates) * (len(candidates) - 1):
        raise ValueError("Too many edges for the number of non-orphan nodes")
    edges = []
    seen = set()
    while len(edges) < edge_count:
        source, target = rng.sample(candidates, 2)
        if (source, target) in seen:
            continue
        seen.add((source, target))
        nodes[target]["details"]["users"] += 1
        edges.append({"from": nodes[source]["id"], "to": nodes[target]["id"],
                      "relation": "references", "label": "uses"})
    for node in nodes:
        details = node["details"]
        details["orphan"] = details["users"] == 0 and not details["use_fake_user"]
    return {
        "meta": {"scope": "WHOLE_FILE", "version": "0.2.0", "target_id": "",
                 "target_name": "Synthetic whole file", "mode": "BOTH", "depth": 2,
                 "node_count": len(nodes), "edge_count": len(edges),
                 "type_counts": dict(Counter(node["type"] for node in nodes)),
                 "scan_seconds": 0.0, "truncated": [], "synthetic_seed": seed},
        "nodes": nodes, "edges": edges,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, help="Output graph_data.js path")
    parser.add_argument("--nodes", type=int, default=20_000)
    parser.add_argument("--edges", type=int, default=60_000)
    parser.add_argument("--seed", type=int, default=2020)
    args = parser.parse_args()
    if args.nodes < 0 or args.edges < 0:
        parser.error("Node and edge counts must be non-negative")
    try:
        payload = make_graph(args.nodes, args.edges, args.seed)
    except ValueError as error:
        parser.error(str(error))
    output = args.output or Path(tempfile.mkdtemp(prefix="brg-synthetic-")) / "graph_data.js"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("window.BRG_GRAPH_DATA = " + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{output}: {len(payload['nodes'])} nodes, {len(payload['edges'])} edges")


if __name__ == "__main__":
    main()
