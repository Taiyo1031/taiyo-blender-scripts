import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

from ..properties import ADDON_ID


def get_addon_preferences(context):
    addon = context.preferences.addons.get(ADDON_ID)
    if addon:
        return addon.preferences
    return SimpleNamespace(output_mode="TEMP", custom_output_folder="")


def resolve_output_folder(context, preferences=None):
    preferences = preferences or get_addon_preferences(context)
    if preferences.output_mode == "CUSTOM":
        raw_path = (preferences.custom_output_folder or "").strip()
        if not raw_path:
            raise ValueError("Custom output folder is not set in the add-on preferences.")
        folder = Path(bpy.path.abspath(raw_path)).expanduser()
    else:
        folder = Path(tempfile.gettempdir()) / "blend_reference_graph" / str(os.getpid())
    return ensure_output_folder(folder)


def ensure_output_folder(raw_path):
    folder = Path(raw_path).resolve()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / f".brg_write_test_{os.getpid()}"
        with probe.open("w", encoding="utf-8") as handle:
            handle.write("ok")
        probe.unlink()
    except OSError as exc:
        raise OSError(f"Output folder is not writable: {folder}") from exc
    return folder


def export_graph_data(graph, meta, output_folder):
    folder = ensure_output_folder(output_folder)
    payload = graph.as_payload(meta)
    output_path = folder / "graph_data.js"
    json_path = folder / "graph_data.json"
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("window.BRG_GRAPH_DATA = ")
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write(";\n")
    return str(output_path), payload
