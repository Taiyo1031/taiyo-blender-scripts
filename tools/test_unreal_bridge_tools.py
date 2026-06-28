import csv
import importlib.util
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "_Taiyo_Blender_Extensions_Repo" / "unreal_bridge_tools"
ADDON_PATH = ADDON_DIR / "__init__.py"


def load_addon():
    module_name = "unreal_bridge_tools_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ADDON_PATH,
        submodule_search_locations=[str(ADDON_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def reset_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def new_mesh_object(name, mesh, collection, location=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, mesh)
    obj.matrix_world = Matrix.Translation(location)
    collection.objects.link(obj)
    return obj


def bind_operator_methods(addon, harness_type):
    for name in (
        "_initialize",
        "_make_iterator",
        "_open_export_file",
        "_queue_export_row",
        "_flush_row_buffer",
        "_close_export_file",
        "_process_tick",
        "_process_one",
        "_resolve_name",
        "_adjust_items_per_tick",
        "_progress_percent",
        "_eta_seconds",
        "_update_progress",
        "_try_restart_to_temp",
        "_finish",
    ):
        setattr(harness_type, name, getattr(addon.UBT_OT_ExportCSV, name))


def main():
    addon = load_addon()
    addon.register()
    temp_dir = Path(tempfile.mkdtemp(prefix="ubt-test-"))
    addon.preset_utils.USER_PRESET_PATH_OVERRIDE = str(temp_dir / "presets.json")
    try:
        reset_scene()
        scene_root = bpy.context.scene.collection
        collection = bpy.data.collections.new("UBT_Test")
        scene_root.children.link(collection)

        mesh = bpy.data.meshes.new("Mesh")
        mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
            [],
            [(0, 1, 2)],
        )
        keep = new_mesh_object("KeepBox.001", mesh, collection, (1, 2, 3))
        new_mesh_object("SkipBox.001", mesh, collection)

        settings = bpy.context.scene.ubt_props
        settings.collection = collection
        settings.scope = "recursive"
        settings.select_visible_only = False
        settings.case_sensitive = True
        settings.name_mode = "numeric_suffix"
        settings.export_mode = "responsive"
        settings.export_path = str(temp_dir / "ubt_export_test.csv")
        include = settings.filters.add()
        include.mode = "include"
        include.text = "Keep"
        exclude = settings.filters.add()
        exclude.mode = "exclude"
        exclude.text = "Never"

        result = bpy.ops.ubt.save_preset_as(preset_name="Preset A")
        assert result == {"FINISHED"}, result
        assert addon.preset_utils.find_preset(
            addon.preset_utils.load_presets(),
            "Preset A",
        )

        settings.scope = "all"
        settings.collection = None
        settings.select_visible_only = True
        settings.case_sensitive = False
        settings.name_mode = "keep_raw"
        settings.export_mode = "fast_locked"
        settings.export_path = ""
        settings.filters.clear()
        settings.selected_preset = "Preset A"

        result = bpy.ops.ubt.load_preset()
        assert result == {"FINISHED"}, result
        assert settings.scope == "recursive"
        assert settings.collection == collection
        assert settings.select_visible_only is False
        assert settings.case_sensitive is True
        assert settings.name_mode == "numeric_suffix"
        assert settings.export_mode == "responsive"
        assert settings.export_path.endswith("ubt_export_test.csv")
        assert [(item.mode, item.text) for item in settings.filters] == [
            ("include", "Keep"),
            ("exclude", "Never"),
        ]

        settings.export_path = str(temp_dir / "updated_export.csv")
        result = bpy.ops.ubt.save_preset()
        assert result == {"FINISHED"}, result
        saved = addon.preset_utils.find_preset(
            addon.preset_utils.load_presets(),
            "Preset A",
        )
        assert saved["export_path"].endswith("updated_export.csv")

        exported_presets = temp_dir / "unreal_bridge_tools_presets.json"
        result = bpy.ops.ubt.export_presets(filepath=str(exported_presets))
        assert result == {"FINISHED"}, result
        assert exported_presets.exists()

        result = bpy.ops.ubt.delete_preset()
        assert result == {"FINISHED"}, result
        assert addon.preset_utils.load_presets() == []

        result = bpy.ops.ubt.import_presets(filepath=str(exported_presets))
        assert result == {"FINISHED"}, result
        assert addon.preset_utils.find_preset(
            addon.preset_utils.load_presets(),
            "Preset A",
        )

        missing = dict(saved)
        missing["collection_name"] = "Missing_Collection"
        missing_name = addon.preset_utils.load_preset_into_settings(
            settings,
            missing,
        )
        assert missing_name == "Missing_Collection"
        assert settings.collection is None
        settings.collection = collection
        settings.export_path = str(temp_dir / "ubt_export_test.csv")

        result = bpy.ops.ubt.export_csv()
        assert result == {"FINISHED"}, result
        with open(settings.export_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert rows[0] == [
            "id",
            "tx",
            "ty",
            "tz",
            "rx",
            "ry",
            "rz",
            "sx",
            "sy",
            "sz",
            "objname",
            "colname",
        ]
        assert len(rows) == 2, rows
        assert rows[1][10] == "KeepBox", rows[1]
        assert rows[1][11] == "UBT_Test", rows[1]

        settings.filters.clear()
        hidden = new_mesh_object("HiddenBox", mesh, collection)
        hidden.hide_set(True)
        settings.select_visible_only = True
        settings.export_path = str(temp_dir / "ubt_visible_only_export_test.csv")
        result = bpy.ops.ubt.export_csv()
        assert result == {"FINISHED"}, result
        with open(settings.export_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert "HiddenBox" not in {row[10] for row in rows[1:]}, rows
        assert {row[10] for row in rows[1:]} == {"KeepBox", "SkipBox"}, rows
        hidden.hide_set(False)
        settings.select_visible_only = False

        settings.export_mode = "fast_locked"
        settings.export_path = str(temp_dir / "ubt_adaptive_export_test.csv")
        for index in range(600):
            new_mesh_object(f"BatchBox_{index:03d}", mesh, collection)

        class ModalHarness:
            _timer = None

            @staticmethod
            def report(_level, _message):
                pass

        bind_operator_methods(addon, ModalHarness)
        operator = ModalHarness()
        init_result = operator._initialize(bpy.context)
        assert init_result is None, init_result
        assert operator._lock_ui is True
        assert operator._seconds_per_tick == addon.EXPORT_FAST_SECONDS_PER_TICK
        assert settings.export_running is True
        assert settings.export_total == len(collection.objects), settings.export_total
        initial_batch = operator._items_per_tick
        for _ in range(8):
            has_more = operator._process_tick(bpy.context)
            operator._update_progress(bpy.context, force=True)
            if not has_more:
                break
        assert operator._items_per_tick > initial_batch
        assert operator._progress_percent() > 0.0
        assert operator._eta_seconds() is not None
        assert settings.export_progress > 0.0
        assert settings.export_processed > 0
        assert settings.export_exported > 0
        operator._finish(bpy.context)
        assert settings.export_running is False
        assert settings.export_progress == 1.0
        assert settings.export_status.startswith("Exported ")
        assert operator._row_buffer == []
        with open(settings.export_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert len(rows) == len(collection.objects) + 1, len(rows)

        settings.export_path = str(temp_dir / "ubt_large_buffer_export_test.csv")
        for index in range(4600):
            new_mesh_object(f"LargeBatchBox_{index:04d}", mesh, collection)
        result = bpy.ops.ubt.export_csv()
        assert result == {"FINISHED"}, result
        with open(settings.export_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert len(rows) == len(collection.objects) + 1, len(rows)
        assert settings.export_exported == len(collection.objects)
        assert settings.export_items_per_second > 0.0

        assert keep.name in bpy.data.objects
        print("Unreal Bridge Tools integration test passed")
    finally:
        addon.preset_utils.USER_PRESET_PATH_OVERRIDE = None
        addon.unregister()


if __name__ == "__main__":
    main()
