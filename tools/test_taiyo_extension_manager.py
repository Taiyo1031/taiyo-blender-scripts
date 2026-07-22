import importlib.util
import json
import os
import sys
import tempfile
from types import SimpleNamespace

import bpy
from bl_pkg.bl_extension_utils import PkgManifest_Normalized


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANAGER_PATH = os.path.join(
    ROOT,
    "_Taiyo_Blender_Extensions_Repo",
    "taiyo_extension_manager",
    "__init__.py",
)


def load_manager():
    module_name = "taiyo_extension_manager_test"
    spec = importlib.util.spec_from_file_location(module_name, MANAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_row(
    pkg_id,
    name,
    tags,
    updated_at,
    *,
    installed=False,
    enabled=False,
    outdated=False,
):
    return {
        "id": pkg_id,
        "name": name,
        "tags": tuple(tags),
        "updated_at": updated_at,
        "installed": installed,
        "enabled": enabled,
        "outdated": outdated,
        "search_text": " ".join((pkg_id, name, *tags)).casefold(),
    }


def test_filters_and_sorting(manager):
    rows = [
        make_row("alpha", "Alpha", ("csv", "export"), 100, installed=True, enabled=True),
        make_row("beta", "Beta", ("csv", "mesh"), 300, outdated=True),
        make_row("gamma", "Gamma", ("mesh", "export"), 200),
    ]

    selected = manager.TAG_FILTER_SEPARATOR.join(("csv", "mesh"))
    assert manager._selected_tags(selected) == ("csv", "mesh")
    assert [row["id"] for row in manager._filtered_rows(rows, "", selected, "ALL")] == ["beta"]
    assert [row["id"] for row in manager._filtered_rows(rows, "gamma", "", "ALL")] == ["gamma"]
    assert [row["id"] for row in manager._sorted_rows(rows, "UPDATED_DESC")] == [
        "beta",
        "gamma",
        "alpha",
    ]
    assert [row["id"] for row in manager._sorted_rows(rows, "NAME_DESC")] == [
        "gamma",
        "beta",
        "alpha",
    ]
    assert [row["id"] for row in manager._sorted_rows(rows, "STATUS")] == [
        "beta",
        "alpha",
        "gamma",
    ]

    manager._update_tag_filter_items(rows, ("csv",))
    item_ids = [item[0] for item in manager._tag_filter_items(None, None)]
    assert "csv" not in item_ids
    assert {"export", "mesh"}.issubset(item_ids)


def test_release_timestamp_cache(manager):
    with tempfile.TemporaryDirectory() as temp_dir:
        private_dir = os.path.join(temp_dir, ".blender_ext")
        os.makedirs(private_dir)
        index_path = os.path.join(private_dir, "index.json")
        with open(index_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "data": [
                        {"id": "alpha", manager.RELEASE_TIMESTAMP_KEY: 123},
                        {"id": "missing"},
                    ]
                },
                handle,
            )

        repo = SimpleNamespace(directory=temp_dir)
        assert manager._release_times(repo) == {"alpha": 123}
        assert manager._format_release_date(123)


def test_csv_mesh_instancer_metadata(manager):
    tags = set(manager.TAG_ALIASES["csv_mesh_instancer"])
    assert {
        "csv", "diff", "houdini", "id", "import", "instance", "mesh", "review",
        "stable-id", "zone", "配置", "読み込み", "差分", "検索",
    }.issubset(tags)
    descriptions = manager.DESCRIPTION_ALIASES["csv_mesh_instancer"]
    assert descriptions["en"]
    assert descriptions["ja"]


def test_distributed_index_metadata(manager):
    index_path = os.path.join(ROOT, "docs", "extensions", "index.json")
    with open(index_path, "r", encoding="utf-8") as handle:
        index_data = json.load(handle)

    errors = []
    items = index_data["data"]
    assert len(items) == 24
    assert all(item.get(manager.RELEASE_TIMESTAMP_KEY, 0) > 0 for item in items)
    for item in items:
        normalized = PkgManifest_Normalized.from_dict_with_error_fn(
            item,
            pkg_idname=item["id"],
            pkg_block=None,
            error_fn=errors.append,
        )
        assert normalized is not None
    assert not errors


def test_registration_and_tag_operators(manager):
    manager.register()
    try:
        wm = bpy.context.window_manager
        manager._update_tag_filter_items(
            [make_row("alpha", "Alpha", ("csv", "mesh"), 100)],
            (),
        )
        assert bpy.ops.tayman.add_tag_filter(tag="csv") == {"FINISHED"}
        manager._set_selected_tags(wm, (*manager._selected_tags(wm.tayman_tag_filter), "mesh"))
        assert manager._selected_tags(wm.tayman_tag_filter) == ("csv", "mesh")

        assert bpy.ops.tayman.remove_tag_filter(tag="csv") == {"FINISHED"}
        assert manager._selected_tags(wm.tayman_tag_filter) == ("mesh",)

        assert bpy.ops.tayman.clear_tag_filters() == {"FINISHED"}
        assert wm.tayman_tag_filter == ""
        assert hasattr(bpy.types.WindowManager, "tayman_sort_mode")
    finally:
        manager.unregister()


def main():
    manager = load_manager()
    test_filters_and_sorting(manager)
    test_release_timestamp_cache(manager)
    test_csv_mesh_instancer_metadata(manager)
    test_distributed_index_metadata(manager)
    test_registration_and_tag_operators(manager)
    print("Taiyo Extension Manager tests passed")


if __name__ == "__main__":
    main()
