import sys
from pathlib import Path

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "_Taiyo_Blender_Extensions_Repo"
sys.path.insert(0, str(SOURCE_ROOT))

import collection_linked_mesh_replacer
from collection_linked_mesh_replacer import cache


PREFIX = "CLMR_Test_"


CUBE_VERTICES = [
    (-1.0, -1.0, -1.0),
    (1.0, -1.0, -1.0),
    (1.0, 1.0, -1.0),
    (-1.0, 1.0, -1.0),
    (-1.0, -1.0, 1.0),
    (1.0, -1.0, 1.0),
    (1.0, 1.0, 1.0),
    (-1.0, 1.0, 1.0),
]
CUBE_FACES = [
    (0, 1, 2, 3),
    (4, 7, 6, 5),
    (0, 4, 5, 1),
    (1, 5, 6, 2),
    (2, 6, 7, 3),
    (4, 0, 3, 7),
]


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def create_mesh(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def translated_reordered_cube(name, offset):
    order = list(reversed(range(len(CUBE_VERTICES))))
    old_to_new = {old: new for new, old in enumerate(order)}
    vertices = [
        tuple(CUBE_VERTICES[index][axis] + offset[axis] for axis in range(3))
        for index in order
    ]
    faces = [
        tuple(old_to_new[index] for index in face)
        for face in CUBE_FACES
    ]
    return create_mesh(name, vertices, faces)


def link_object(name, mesh, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def select_only(*objects, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or (objects[0] if objects else None)


def bbox_center(obj):
    return sum(
        (obj.matrix_world @ type(obj.location)(corner) for corner in obj.bound_box),
        type(obj.location)(),
    ) / 8.0


def main():
    collection_linked_mesh_replacer.register()
    try:
        reset_scene()

        source_root = bpy.data.collections.new(PREFIX + "Source")
        source_child = bpy.data.collections.new(PREFIX + "SourceChild")
        target_collection = bpy.data.collections.new(PREFIX + "Targets")
        bpy.context.scene.collection.children.link(source_root)
        bpy.context.scene.collection.children.link(target_collection)
        source_root.children.link(source_child)
        source_root.color_tag = "COLOR_05"

        source_mesh = create_mesh(
            PREFIX + "CanonicalMesh",
            CUBE_VERTICES,
            CUBE_FACES,
        )
        source_a = link_object(PREFIX + "SourceA", source_mesh, source_root)
        source_b = link_object(PREFIX + "SourceB", source_mesh, source_child)

        target_mesh = translated_reordered_cube(
            PREFIX + "TargetMesh",
            (4.0, -3.0, 2.0),
        )
        target = link_object(PREFIX + "PlacedWall", target_mesh, target_collection)
        target.matrix_world = (
            Matrix.Translation((10.0, 20.0, 30.0))
            @ Matrix.Rotation(0.35, 4, "Z")
        )
        bpy.context.view_layer.update()
        original_center = bbox_center(target)

        settings = bpy.context.scene.clmr_settings
        settings.source_collection = source_root
        settings.recursive_search = True
        settings.adjust_bbox_center = True
        settings.original_mode = "BACKUP"

        assert bpy.ops.clmr.build_cache() == {"FINISHED"}
        assert cache.cache_status(source_root, True) == "VALID"
        assert cache.CACHE["cached_object_count"] == 2
        assert cache.CACHE["unique_mesh_count"] == 1
        assert cache.CACHE["duplicated_signature_count"] == 1

        select_only(target)
        assert bpy.ops.clmr.find_match() == {"FINISHED"}
        assert settings.result_confidence == "Multiple Matches"
        assert settings.result_candidates == 2
        assert settings.result_match == source_a.name

        assert bpy.ops.clmr.replace_selected() == {"FINISHED"}
        replacement = bpy.context.active_object
        assert replacement is not None
        assert replacement.data == source_a.data
        assert replacement.name == PREFIX + "PlacedWall"
        assert replacement.name in target_collection.objects
        assert (bbox_center(replacement) - original_center).length < 1.0e-5

        backup = bpy.data.collections.get("_MeshReplace_Backup")
        assert backup is not None
        assert target.name in backup.objects
        assert target.name not in target_collection.objects
        assert target.hide_get()

        extra_source = link_object(
            PREFIX + "ExtraSource",
            source_mesh,
            source_root,
        )
        assert cache.cache_status(source_root, True) == "OUTDATED"
        bpy.data.objects.remove(extra_source, do_unlink=True)
        assert bpy.ops.clmr.build_cache() == {"FINISHED"}

        batch_mesh = translated_reordered_cube(
            PREFIX + "BatchMesh",
            (-2.0, 1.0, 5.0),
        )
        batch_target = link_object(
            PREFIX + "BatchTarget",
            batch_mesh,
            target_collection,
        )
        triangle_mesh = create_mesh(
            PREFIX + "TriangleMesh",
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [(0, 1, 2)],
        )
        no_match = link_object(
            PREFIX + "NoMatch",
            triangle_mesh,
            target_collection,
        )
        batch_target_pointer = batch_target.as_pointer()
        settings.original_mode = "DELETE"
        select_only(batch_target, no_match, source_b, active=batch_target)

        assert bpy.ops.clmr.replace_all_selected("EXEC_DEFAULT") == {"FINISHED"}
        assert settings.batch_replaced == 1
        assert settings.batch_not_found == 1
        assert settings.batch_skipped == 1
        assert bpy.data.objects.get(PREFIX + "BatchTarget") is not None
        assert all(
            obj.as_pointer() != batch_target_pointer
            for obj in bpy.data.objects
        )
        assert bpy.data.objects.get(PREFIX + "NoMatch") is no_match

        assert bpy.ops.clmr.clear_cache() == {"FINISHED"}
        assert cache.cache_status(source_root, True) == "NOT_BUILT"
        print("Collection Linked Mesh Replacer integration tests passed")
    finally:
        collection_linked_mesh_replacer.unregister()


main()
