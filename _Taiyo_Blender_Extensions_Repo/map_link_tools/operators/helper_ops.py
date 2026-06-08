from bpy.types import Operator

from ..utils.collections import (
    iter_collection_tree,
    iter_layer_collections_for_collection,
    iter_collection_objects,
)


def _target_collection(context):
    collection = context.scene.maplink_settings.helper_collection
    if collection is None:
        return None
    return collection


def unhide_collection_tree(context, collection, make_selectable=False):
    collections = list(iter_collection_tree(collection))
    objects = list(iter_collection_objects(collection))
    layer_collections = []
    for coll in collections:
        layer_collections.extend(iter_layer_collections_for_collection(context, coll))

    for layer_collection in layer_collections:
        layer_collection.exclude = False
        layer_collection.hide_viewport = False

    for coll in collections:
        coll.hide_viewport = False
        if make_selectable:
            coll.hide_select = False

    for obj in objects:
        obj.hide_viewport = False
        try:
            obj.hide_set(False)
        except RuntimeError:
            pass
        if make_selectable:
            obj.hide_select = False

    return len(collections), len(objects), len(layer_collections)


def make_collection_tree_selectable(context, collection):
    collections = list(iter_collection_tree(collection))
    objects = list(iter_collection_objects(collection))

    for coll in collections:
        coll.hide_select = False

    for obj in objects:
        obj.hide_select = False

    return len(collections), len(objects)


class MAPLINK_OT_unhide_helper_collection(Operator):
    bl_idname = "maplink.unhide_helper_collection"
    bl_label = "Unhide Collection + Objects"
    bl_description = "Unhide the selected collection tree and all objects inside it"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = _target_collection(context)
        if collection is None:
            self.report({"WARNING"}, "Set a Helper Collection.")
            return {"CANCELLED"}

        settings = context.scene.maplink_settings
        coll_count, obj_count, layer_count = unhide_collection_tree(
            context,
            collection,
            make_selectable=settings.helper_make_selectable,
        )
        message = (
            f"Unhid {coll_count} collection(s), {obj_count} object(s), "
            f"{layer_count} layer collection(s)."
        )
        if settings.helper_make_selectable:
            message += " Made selectable."
        settings.helper_result_message = message
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MAPLINK_OT_make_helper_collection_selectable(Operator):
    bl_idname = "maplink.make_helper_collection_selectable"
    bl_label = "Make Collection + Objects Selectable"
    bl_description = "Make the selected collection tree and all objects inside it selectable"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = _target_collection(context)
        if collection is None:
            self.report({"WARNING"}, "Set a Helper Collection.")
            return {"CANCELLED"}

        settings = context.scene.maplink_settings
        coll_count, obj_count = make_collection_tree_selectable(context, collection)
        message = f"Made selectable: {coll_count} collection(s), {obj_count} object(s)."
        settings.helper_result_message = message
        self.report({"INFO"}, message)
        return {"FINISHED"}
