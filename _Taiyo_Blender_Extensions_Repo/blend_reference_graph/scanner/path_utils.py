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


class CollectionPathCache:
    def __init__(self, build=True):
        self.paths = {}
        self.memberships = {}
        if build:
            for _ in self.iter_build():
                pass

    def iter_build(self):
        self.paths.clear()
        self.memberships.clear()
        seen = set()
        for scene in bpy.data.scenes:
            stack = [(scene.collection, (scene.name, scene.collection.name), frozenset())]
            while stack:
                collection, prefix, ancestors = stack.pop()
                if collection in ancestors:
                    continue
                self.paths.setdefault(collection, set()).add(" / ".join(prefix))
                seen.add(collection)
                for child in collection.children:
                    stack.append((child, (*prefix, child.name), ancestors | {collection}))
                    yield None
                yield None
        for collection in bpy.data.collections:
            seen.add(collection)
            yield None
        for collection in seen:
            for obj in collection.objects:
                self.memberships.setdefault(obj, []).append(collection)
                yield None

    def collection_paths(self, collection):
        return sorted(self.paths.get(collection, ()))

    def object_paths(self, obj):
        return sorted({path for collection in self.memberships.get(obj, ())
                       for path in self.paths.get(collection, ())})
