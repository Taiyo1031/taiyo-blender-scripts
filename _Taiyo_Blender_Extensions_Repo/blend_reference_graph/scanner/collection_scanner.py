from .id_utils import id_key
from .object_scanner import object_id
from .path_utils import collection_paths


def collection_id(collection):
    return f"Collection:{id_key(collection)}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_collection_node(graph, collection, filters, path_cache=None):
    if collection_id(collection) in graph.nodes or not _allowed(filters, "COLLECTION"):
        return
    path_cache = path_cache or getattr(graph, "path_cache", None)
    paths = path_cache.collection_paths(collection) if path_cache else collection_paths(collection)
    graph.add_node(
        collection_id(collection),
        "COLLECTION",
        collection.name,
        f"COL {collection.name}",
        path=paths[0] if paths else "",
        details={
            "objects": [obj.name for obj in collection.objects],
            "children": [child.name for child in collection.children],
            "paths": paths,
        },
    )


def add_object_collections(graph, obj, filters):
    cache = getattr(graph, "path_cache", None)
    collections = cache.memberships.get(obj, ()) if cache else obj.users_collection
    for collection in collections:
        add_collection_node(graph, collection, filters)
        graph.add_edge(collection_id(collection), object_id(obj), "contains", "contains")
        for child in collection.children:
            add_collection_node(graph, child, filters)
            graph.add_edge(collection_id(collection), collection_id(child), "child_collection", "child collection")
