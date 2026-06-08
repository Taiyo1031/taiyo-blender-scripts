import bpy


def collection_paths(target_collection):
    paths = set()
    for scene in bpy.data.scenes:
        root = scene.collection
        prefix = (scene.name, root.name)
        if root == target_collection:
            paths.add(" / ".join(prefix))
        _walk_collection_paths(root, target_collection, prefix, {root.name}, paths)
    return sorted(paths)


def object_collection_paths(obj):
    paths = set()
    for collection in obj.users_collection:
        paths.update(collection_paths(collection))
    return sorted(paths)


def _walk_collection_paths(parent, target, prefix, ancestors, paths):
    for child in parent.children:
        if child.name in ancestors:
            continue
        child_path = (*prefix, child.name)
        if child == target:
            paths.add(" / ".join(child_path))
        _walk_collection_paths(child, target, child_path, {*ancestors, child.name}, paths)
