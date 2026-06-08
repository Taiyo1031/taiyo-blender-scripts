from .object_scanner import object_id
from .path_utils import collection_paths


def collection_id(collection):
    return f"Collection:{collection.name}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_collection_node(graph, collection, filters):
    if not _allowed(filters, "COLLECTION"):
        return
    paths = collection_paths(collection)
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
    for collection in obj.users_collection:
        add_collection_node(graph, collection, filters)
        graph.add_edge(collection_id(collection), object_id(obj), "contains", "contains")
        for child in collection.children:
            add_collection_node(graph, child, filters)
            graph.add_edge(collection_id(collection), collection_id(child), "child_collection", "child collection")
