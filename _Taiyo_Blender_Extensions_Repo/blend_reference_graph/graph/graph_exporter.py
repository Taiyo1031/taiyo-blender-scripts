import json
import os

import bpy


def ensure_output_folder(raw_path):
    folder = bpy.path.abspath(raw_path or "//blend_reference_graph/")
    os.makedirs(folder, exist_ok=True)
    return folder


def export_graph_data(graph, meta, output_folder):
    folder = ensure_output_folder(output_folder)
    payload = graph.as_payload(meta)
    output_path = os.path.join(folder, "graph_data.js")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("window.BRG_GRAPH_DATA = ")
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write(";\n")
    return output_path, payload
