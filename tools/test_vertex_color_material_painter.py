import importlib.util
import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "_Taiyo_Blender_Extensions_Repo" / "vertex_color_material_painter"
ADDON_PATH = ADDON_DIR / "__init__.py"


def load_addon():
    module_name = "vertex_color_material_painter_test"
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
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def new_mesh_object(name, mesh=None):
    if mesh is None:
        mesh = bpy.data.meshes.new(f"{name}Mesh")
        mesh.from_pydata(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [],
            [(0, 1, 2)],
        )

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def select_only(obj):
    for candidate in bpy.context.view_layer.objects:
        candidate.select_set(False)

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def main():
    addon = load_addon()
    addon.register()

    try:
        reset_scene()
        scene = bpy.context.scene

        shared_mesh = bpy.data.meshes.new("VCMPSharedMesh")
        shared_mesh.from_pydata(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [],
            [(0, 1, 2)],
        )
        shared_a = new_mesh_object("VCMPSharedA", shared_mesh)
        shared_b = new_mesh_object("VCMPSharedB", shared_mesh)
        shared_mesh.attributes.new("remove_point", 'FLOAT', 'POINT')

        scene.vcmp_remove_target_object = shared_a
        scene.vcmp_remove_attribute_name = "remove_point"
        result = bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT')
        assert result == {'FINISHED'}, result
        assert shared_mesh.attributes.get("remove_point") is None
        assert shared_b.data.attributes.get("remove_point") is None

        try:
            addon._remove_mesh_attribute(shared_a, "remove_point")
        except ValueError:
            pass
        else:
            raise AssertionError("Missing attributes must not be silently removed.")

        edit_object = new_mesh_object("VCMPEdit")
        edit_object.data.attributes.new("remove_corner", 'FLOAT_COLOR', 'CORNER')
        select_only(edit_object)
        bpy.ops.object.mode_set(mode='EDIT')

        scene.vcmp_remove_target_object = edit_object
        scene.vcmp_remove_attribute_name = "remove_corner"
        result = bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT')
        assert result == {'FINISHED'}, result
        assert edit_object.data.attributes.get("remove_corner") is None

        bpy.ops.object.mode_set(mode='OBJECT')
        print("Vertex Color Material Painter integration tests passed.")
    finally:
        addon.unregister()
        reset_scene()


if __name__ == "__main__":
    main()
