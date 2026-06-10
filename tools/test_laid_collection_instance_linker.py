import importlib.util
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "_Taiyo_Blender_Extensions_Repo" / "laid_collection_instance_linker"
ADDON_PATH = ADDON_DIR / "__init__.py"


def load_addon():
    module_name = "laid_collection_instance_linker_test"
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


def new_collection(name, parent):
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def new_mesh_object(name, data_name, collection, location=(0.0, 0.0, 0.0)):
    mesh = bpy.data.meshes.new(data_name)
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.matrix_world = Matrix.Translation(location)
    return obj


def generated_objects(output, kind=None):
    objects = []
    seen = set()

    def visit(collection):
        for obj in collection.objects:
            if obj.as_pointer() in seen:
                continue
            seen.add(obj.as_pointer())
            if obj.get("LCIL_generated"):
                if kind is None or obj.get("LCIL_generated_kind") == kind:
                    objects.append(obj)
        for child in collection.children:
            visit(child)

    visit(output)
    return objects


def assert_vector_close(actual, expected):
    assert (actual - expected).length < 1e-5, (actual, expected)


def main():
    addon = load_addon()
    addon.register()
    try:
        reset_scene()
        scene_root = bpy.context.scene.collection

        laid_map = new_collection("Laid_MAP", scene_root)
        map_nested = new_collection("Map_Nested", laid_map)
        individual = new_collection("Laid_Individual", scene_root)
        individual_nested = new_collection("Individual_Nested", individual)

        wall_target = new_collection("Wall_A", individual_nested)
        wall_target.color_tag = "COLOR_04"
        wall_part = new_mesh_object(
            "WallPart",
            "WallPartMesh",
            wall_target,
            location=(1.0, 2.0, 3.0),
        )

        roof_target = new_collection("Roof_A", individual_nested)
        roof_target.color_tag = "COLOR_05"
        roof_part = new_mesh_object(
            "RoofPart",
            "RoofPartMesh",
            roof_target,
            location=(0.0, 4.0, 0.0),
        )

        duplicate_target_a = new_collection("Duplicate", individual_nested)
        new_mesh_object("DuplicatePartA", "DuplicateMeshA", duplicate_target_a)
        duplicate_parent = new_collection("Duplicate_Parent", individual)
        duplicate_target_b = new_collection("Duplicate.001", duplicate_parent)
        new_mesh_object("DuplicatePartB", "DuplicateMeshB", duplicate_target_b)

        wall_source = new_mesh_object(
            "Wall_A.001",
            "UnrelatedWallMesh",
            map_nested,
            location=(10.0, 20.0, 30.0),
        )
        roof_source = new_mesh_object(
            "Wrong_Roof_Object",
            "Roof_A.003",
            map_nested,
            location=(-5.0, 1.0, 2.0),
        )
        missing_source = new_mesh_object(
            "Missing_A",
            "MissingMesh",
            map_nested,
        )
        duplicate_source = new_mesh_object(
            "Duplicate.100",
            "DuplicateSourceMesh",
            map_nested,
        )
        curve_data = bpy.data.curves.new("GuideCurve", "CURVE")
        curve_source = bpy.data.objects.new("Guide", curve_data)
        map_nested.objects.link(curve_source)

        settings = bpy.context.scene.lcil_settings
        settings.laid_map_collection = laid_map
        settings.individual_root = individual
        settings.output_collection_name = "Generated_SIM_Map"
        settings.name_source = "OBJECT_THEN_MESH"
        settings.ignore_numeric_suffix = True
        settings.only_mesh_objects = True
        settings.group_by_target = True

        result = bpy.ops.lcil.preview_link()
        assert result == {"FINISHED"}, result
        assert settings.preview_linked == 2, settings.preview_linked
        assert settings.preview_missing == 1, settings.preview_missing
        assert settings.preview_duplicate == 1, settings.preview_duplicate
        assert settings.preview_skipped == 1, settings.preview_skipped

        assert wall_source["LCIL_link_status"] == "LINKED"
        assert wall_source["LCIL_link_match_key"] == "Wall_A"
        assert wall_source["LCIL_link_source_name_field"] == "OBJECT_NAME"
        assert wall_source["LCIL_link_collection_name"] == wall_target.name
        assert roof_source["LCIL_link_status"] == "LINKED"
        assert roof_source["LCIL_link_match_key"] == "Roof_A"
        assert roof_source["LCIL_link_source_name_field"] == "MESH_DATA_NAME"
        assert missing_source["LCIL_link_status"] == "MISSING"
        assert "LCIL_link_collection_name" not in missing_source
        assert duplicate_source["LCIL_link_status"] == "DUPLICATE"
        assert curve_source["LCIL_link_status"] == "SKIPPED"

        result = bpy.ops.lcil.select_issue_objects()
        assert result == {"FINISHED"}, result
        selected_names = {obj.name for obj in bpy.context.selected_objects}
        assert selected_names == {missing_source.name, duplicate_source.name}, selected_names

        result = bpy.ops.lcil.generate_instances()
        assert result == {"FINISHED"}, result
        output = bpy.data.collections["Generated_SIM_Map"]
        instances = generated_objects(output, "COLLECTION_INSTANCE_EMPTY")
        assert len(instances) == 2, [obj.name for obj in instances]

        wall_group = output.children.get(f"GRP_{wall_target.name}")
        roof_group = output.children.get(f"GRP_{roof_target.name}")
        assert wall_group is not None
        assert roof_group is not None
        assert wall_group.color_tag == "COLOR_04"
        assert roof_group.color_tag == "COLOR_05"

        wall_empty = next(
            obj
            for obj in instances
            if obj["LCIL_target_collection"] == wall_target.name
        )
        roof_empty = next(
            obj
            for obj in instances
            if obj["LCIL_target_collection"] == roof_target.name
        )
        assert wall_empty.instance_collection == wall_target
        assert roof_empty.instance_collection == roof_target
        assert_vector_close(
            wall_empty.matrix_world.translation,
            wall_source.matrix_world.translation,
        )
        assert_vector_close(
            roof_empty.matrix_world.translation,
            roof_source.matrix_world.translation,
        )

        manual = bpy.data.objects.new("Manual_Output_Object", None)
        output.objects.link(manual)
        old_instance_pointers = {obj.as_pointer() for obj in instances}
        result = bpy.ops.lcil.generate_instances()
        assert result == {"FINISHED"}, result
        instances = generated_objects(output, "COLLECTION_INSTANCE_EMPTY")
        assert len(instances) == 2
        assert not old_instance_pointers.intersection(
            {obj.as_pointer() for obj in instances}
        )
        assert manual.name in output.objects

        result = bpy.ops.lcil.realize_instances()
        assert result == {"FINISHED"}, result
        assert not generated_objects(output, "COLLECTION_INSTANCE_EMPTY")
        realized = generated_objects(output, "REALIZED_OBJECT")
        assert len(realized) == 2, [obj.name for obj in realized]

        realized_wall = next(
            obj
            for obj in realized
            if obj["LCIL_target_collection"] == wall_target.name
        )
        realized_roof = next(
            obj
            for obj in realized
            if obj["LCIL_target_collection"] == roof_target.name
        )
        assert realized_wall.data == wall_part.data
        assert realized_roof.data == roof_part.data
        assert_vector_close(
            realized_wall.matrix_world.translation,
            wall_source.matrix_world.translation
            + wall_part.matrix_world.translation,
        )
        assert_vector_close(
            realized_roof.matrix_world.translation,
            roof_source.matrix_world.translation
            + roof_part.matrix_world.translation,
        )

        result = bpy.ops.lcil.generate_instances()
        assert result == {"FINISHED"}, result
        assert not generated_objects(output, "REALIZED_OBJECT")
        assert len(generated_objects(output, "COLLECTION_INSTANCE_EMPTY")) == 2
        assert manual.name in output.objects

        result = bpy.ops.lcil.delete_generated_empties()
        assert result == {"FINISHED"}, result
        assert not generated_objects(output, "COLLECTION_INSTANCE_EMPTY")
        assert manual.name in output.objects
        assert wall_source.name in bpy.data.objects
        assert wall_target.name in bpy.data.collections

        print("CW_Laid Collection Instance Linker integration test passed")
    finally:
        addon.unregister()


if __name__ == "__main__":
    main()
