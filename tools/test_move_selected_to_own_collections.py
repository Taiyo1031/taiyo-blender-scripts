import importlib.util
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "_Taiyo_Blender_Extensions_Repo" / "move_selected_to_own_collections" / "__init__.py"


def load_addon():
    spec = importlib.util.spec_from_file_location("move_selected_to_own_collections_test", ADDON_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def main():
    addon = load_addon()
    addon.register()
    try:
        reset_scene()

        parent = bpy.data.collections.new("Assets")
        bpy.context.scene.collection.children.link(parent)

        mesh = bpy.data.meshes.new("ChairMesh")
        obj = bpy.data.objects.new("Chair", mesh)
        parent.objects.link(obj)

        bpy.context.view_layer.update()
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        settings = bpy.context.scene.msoc_settings
        settings.apply_collection_color = True
        settings.collection_color_tag = "COLOR_05"

        result = bpy.ops.object.move_selected_to_own_collections()
        assert result == {"FINISHED"}, result

        target = parent.children.get("Chair")
        assert target is not None, "Expected child collection named after the object"
        assert target.color_tag == "COLOR_05", target.color_tag
        assert obj.name in target.objects, "Expected object to move into the target collection"
        assert obj.name not in parent.objects, "Expected object to be unlinked from the parent collection"
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
