import bpy


def iter_collection_objects(collection):
    if collection is None:
        return

    seen = set()

    def walk(coll):
        for obj in coll.objects:
            key = obj.as_pointer()
            if key in seen:
                continue
            seen.add(key)
            yield obj
        for child in coll.children:
            yield from walk(child)

    yield from walk(collection)


def iter_collection_tree(collection):
    if collection is None:
        return
    yield collection
    for child in collection.children:
        yield from iter_collection_tree(child)


def iter_layer_collections_for_collection(context, collection):
    root = getattr(context.view_layer, "layer_collection", None)
    if root is None or collection is None:
        return

    def walk(layer_collection):
        if layer_collection.collection == collection:
            yield layer_collection
        for child in layer_collection.children:
            yield from walk(child)

    yield from walk(root)


def iter_layer_collection_tree(context):
    root = getattr(context.view_layer, "layer_collection", None)
    if root is None:
        return

    def walk(layer_collection):
        yield layer_collection
        for child in layer_collection.children:
            yield from walk(child)

    yield from walk(root)


def mesh_objects_in_collection(collection):
    return [
        obj for obj in iter_collection_objects(collection)
        if obj.type == "MESH" and obj.data is not None
    ]


def mesh_data_set(collection):
    return {
        obj.data for obj in mesh_objects_in_collection(collection)
        if obj.data is not None
    }


def deselect_view_layer_objects(context):
    for obj in context.view_layer.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass


def select_objects(context, objects):
    deselect_view_layer_objects(context)
    selected = 0
    skipped = 0
    active_set = False
    view_layer_names = {obj.name for obj in context.view_layer.objects}

    for obj in objects:
        if obj.name not in view_layer_names:
            skipped += 1
            continue
        try:
            obj.select_set(True)
            if not active_set:
                context.view_layer.objects.active = obj
                active_set = True
            selected += 1
        except RuntimeError:
            skipped += 1

    return selected, skipped


def direct_user_collections(obj, fallback_context=None):
    collections = list(getattr(obj, "users_collection", []) or [])
    if collections:
        return collections
    if fallback_context is not None and fallback_context.collection is not None:
        return [fallback_context.collection]
    return []


def active_layer_collection(context):
    layer_collection = getattr(context.view_layer, "active_layer_collection", None)
    return getattr(layer_collection, "collection", None)


def link_object_to_collections(obj, collections, fallback_context=None):
    linked = False
    for collection in collections:
        if collection is None:
            continue
        try:
            collection.objects.link(obj)
            linked = True
        except RuntimeError:
            pass
    if not linked and fallback_context is not None:
        fallback_context.collection.objects.link(obj)


def replace_object_keep_layout(context, target, replacement_data=None, instance_collection=None):
    old_name = target.name
    old_matrix = target.matrix_world.copy()
    old_parent = target.parent
    old_parent_inverse = target.matrix_parent_inverse.copy()
    old_collections = direct_user_collections(target, context)
    old_hide_viewport = target.hide_viewport
    old_hide_render = target.hide_render
    old_hide_select = target.hide_select

    temp_name = old_name + ".maplink_tmp"
    new_obj = bpy.data.objects.new(temp_name, replacement_data)
    if instance_collection is not None:
        new_obj.empty_display_type = "CUBE"
        new_obj.empty_display_size = 1.0
        new_obj.instance_type = "COLLECTION"
        new_obj.instance_collection = instance_collection

    link_object_to_collections(new_obj, old_collections, context)
    new_obj.parent = old_parent
    new_obj.matrix_parent_inverse = old_parent_inverse
    new_obj.matrix_world = old_matrix
    new_obj.hide_viewport = old_hide_viewport
    new_obj.hide_render = old_hide_render
    new_obj.hide_select = old_hide_select

    bpy.data.objects.remove(target, do_unlink=True)
    new_obj.name = old_name
    try:
        new_obj.select_set(True)
    except RuntimeError:
        pass
    return new_obj
