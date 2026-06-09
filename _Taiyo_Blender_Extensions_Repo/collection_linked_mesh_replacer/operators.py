import bpy
from mathutils import Vector

from . import cache


def _clear_match_result(settings):
    _clear_single_match_result(settings)
    settings.preview_items.clear()
    settings.preview_index = 0
    settings.preview_matched = 0
    settings.preview_not_found = 0
    settings.preview_skipped = 0


def _clear_single_match_result(settings):
    settings.result_selected = ""
    settings.result_match = ""
    settings.result_source_mesh = ""
    settings.result_confidence = "Not Searched"
    settings.result_candidates = 0


def _set_match_result(settings, target, candidates):
    settings.result_selected = target.name if target else ""
    settings.result_candidates = len(candidates)
    if not candidates:
        settings.result_match = ""
        settings.result_source_mesh = ""
        settings.result_confidence = "Not Found"
        return

    first = candidates[0]
    settings.result_match = first["object_name"]
    settings.result_source_mesh = first["mesh_name"]
    settings.result_confidence = (
        "Exact" if len(candidates) == 1 else "Multiple Matches"
    )


def _cache_ready(operator, settings):
    if settings.source_collection is None:
        operator.report({"ERROR"}, "No Source Collection selected")
        return False
    status = cache.cache_status(
        settings.source_collection,
        settings.recursive_search,
    )
    if status == "NOT_BUILT":
        operator.report({"ERROR"}, "Cache is not built")
        return False
    if status == "OUTDATED":
        operator.report({"WARNING"}, "Cache is outdated")
    return True


def _is_valid_target(obj, settings):
    if obj is None or obj.type != "MESH" or obj.data is None:
        return False
    if settings.ignore_source_objects and cache.object_is_in_source(
        obj,
        settings.source_collection,
        settings.recursive_search,
    ):
        return False
    return True


def _world_bbox_center(obj):
    if not obj.bound_box:
        return obj.matrix_world.translation.copy()
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return sum(corners, Vector()) / len(corners)


def _collection_in_scene(scene, collection):
    if scene.collection == collection:
        return True
    return any(
        child.as_pointer() == collection.as_pointer()
        for child in scene.collection.children_recursive
    )


def _backup_collection(scene, name):
    clean_name = name.strip() or "_MeshReplace_Backup"
    collection = bpy.data.collections.get(clean_name)
    if collection is None:
        collection = bpy.data.collections.new(clean_name)
    if not _collection_in_scene(scene, collection):
        scene.collection.children.link(collection)
    return collection


def _unique_backup_name(name):
    base = f"{name}_backup"
    if bpy.data.objects.get(base) is None:
        return base
    index = 1
    while bpy.data.objects.get(f"{base}.{index:03d}") is not None:
        index += 1
    return f"{base}.{index:03d}"


def _handle_original(context, target, settings):
    mode = settings.original_mode
    if mode == "BACKUP":
        backup = _backup_collection(
            context.scene,
            settings.backup_collection_name,
        )
        target.name = _unique_backup_name(target.name)
        if target.name not in backup.objects:
            backup.objects.link(target)
        for collection in list(target.users_collection):
            if collection != backup:
                collection.objects.unlink(target)
        target.hide_set(True)
        target.hide_render = True
    elif mode == "DELETE":
        bpy.data.objects.remove(target, do_unlink=True)
    elif mode == "HIDE":
        target.hide_set(True)
        target.hide_render = True


def _replace_object(context, target, settings):
    target_signature, candidates = cache.find_candidates(target)
    _set_match_result(settings, target, candidates)
    if not candidates:
        return "NOT_FOUND", None

    source = cache.resolve_source_object(candidates[0])
    if source is None or source.type != "MESH" or source.data is None:
        return "FAILED", None

    if settings.verify_match:
        source_signature = cache.mesh_signature(source.data)
        if not cache.signatures_match(target_signature, source_signature):
            return "FAILED", None

    target_name = target.name
    target_matrix = target.matrix_world.copy()
    target_center = _world_bbox_center(target)
    target_parent = target.parent
    target_parent_inverse = target.matrix_parent_inverse.copy()
    target_collections = list(target.users_collection)
    if not target_collections:
        target_collections = [context.scene.collection]

    new_obj = source.copy()
    new_obj.data = source.data
    new_obj.parent = target_parent
    new_obj.matrix_parent_inverse = target_parent_inverse

    for collection in target_collections:
        collection.objects.link(new_obj)

    if settings.keep_transform:
        new_obj.matrix_world = target_matrix
    context.view_layer.update()

    if settings.adjust_bbox_center:
        difference = target_center - _world_bbox_center(new_obj)
        adjusted_matrix = new_obj.matrix_world.copy()
        adjusted_matrix.translation += difference
        new_obj.matrix_world = adjusted_matrix
        context.view_layer.update()

    _handle_original(context, target, settings)
    new_obj.name = source.name if settings.rename_to_source else target_name
    return "REPLACED", new_obj


class CLMR_OT_build_cache(bpy.types.Operator):
    bl_idname = "clmr.build_cache"
    bl_label = "Build / Update Cache"
    bl_description = "Scan the source collection and build the mesh signature index"

    def execute(self, context):
        settings = context.scene.clmr_settings
        if settings.source_collection is None:
            self.report({"ERROR"}, "No Source Collection selected")
            return {"CANCELLED"}

        result = cache.build_cache(
            settings.source_collection,
            settings.recursive_search,
        )
        _clear_match_result(settings)
        self.report(
            {"INFO"},
            (
                f"Cache built: {result['cached_object_count']} objects, "
                f"{result['unique_mesh_count']} unique meshes"
            ),
        )
        return {"FINISHED"}


class CLMR_OT_clear_cache(bpy.types.Operator):
    bl_idname = "clmr.clear_cache"
    bl_label = "Clear Cache"
    bl_description = "Clear the in-memory mesh signature cache"

    def execute(self, context):
        cache.clear_cache()
        _clear_match_result(context.scene.clmr_settings)
        self.report({"INFO"}, "Mesh replacement cache cleared")
        return {"FINISHED"}


class CLMR_OT_find_match(bpy.types.Operator):
    bl_idname = "clmr.find_match"
    bl_label = "Find Match"
    bl_description = "Find a matching source object for the active mesh object"

    def execute(self, context):
        settings = context.scene.clmr_settings
        if not _cache_ready(self, settings):
            return {"CANCELLED"}

        target = context.active_object
        if target is None or target.type != "MESH" or target.data is None:
            self.report({"ERROR"}, "Active object is not a Mesh")
            return {"CANCELLED"}
        if not _is_valid_target(target, settings):
            self.report({"WARNING"}, "Active object is in the Source Collection")
            return {"CANCELLED"}

        _signature, candidates = cache.find_candidates(target)
        _set_match_result(settings, target, candidates)
        if not candidates:
            self.report({"WARNING"}, "No match found")
            return {"FINISHED"}

        if len(candidates) > 1:
            self.report(
                {"INFO"},
                f"Found {len(candidates)} matches; using {candidates[0]['object_name']}",
            )
        else:
            self.report({"INFO"}, f"Match found: {candidates[0]['object_name']}")
        return {"FINISHED"}


class CLMR_OT_preview_selected(bpy.types.Operator):
    bl_idname = "clmr.preview_selected"
    bl_label = "Preview Selected"
    bl_description = "Preview source matches for all selected mesh objects"

    def execute(self, context):
        settings = context.scene.clmr_settings
        if not _cache_ready(self, settings):
            return {"CANCELLED"}

        _clear_single_match_result(settings)
        settings.preview_items.clear()
        settings.preview_index = 0
        matched = 0
        not_found = 0
        skipped = 0

        if not context.selected_objects:
            self.report({"WARNING"}, "No objects selected")
            settings.preview_matched = 0
            settings.preview_not_found = 0
            settings.preview_skipped = 0
            return {"CANCELLED"}

        for obj in context.selected_objects:
            item = settings.preview_items.add()
            item.target_name = obj.name if obj else ""

            if obj is None or obj.type != "MESH" or obj.data is None:
                item.confidence = "Skipped"
                skipped += 1
                continue

            if not _is_valid_target(obj, settings):
                item.confidence = "Skipped"
                skipped += 1
                continue

            _signature, candidates = cache.find_candidates(obj)
            item.candidate_count = len(candidates)
            if not candidates:
                item.confidence = "Not Found"
                not_found += 1
                continue

            first = candidates[0]
            item.match_name = first["object_name"]
            item.source_mesh = first["mesh_name"]
            item.confidence = (
                "Exact" if len(candidates) == 1 else "Multiple Matches"
            )
            matched += 1

            if obj == context.active_object:
                _set_match_result(settings, obj, candidates)

        if settings.preview_items and not settings.result_selected:
            first_item = settings.preview_items[0]
            settings.result_selected = first_item.target_name
            settings.result_match = first_item.match_name
            settings.result_source_mesh = first_item.source_mesh
            settings.result_confidence = first_item.confidence or "Not Found"
            settings.result_candidates = first_item.candidate_count

        settings.preview_matched = matched
        settings.preview_not_found = not_found
        settings.preview_skipped = skipped
        if matched == 0:
            self.report(
                {"WARNING"},
                (
                    f"Previewed: {len(settings.preview_items)}, no matches "
                    f"({not_found} not found, {skipped} skipped)"
                ),
            )
            return {"FINISHED"}

        self.report(
            {"INFO"},
            (
                f"Previewed: {len(settings.preview_items)}, Matched: {matched}, "
                f"Not Found: {not_found}, Skipped: {skipped}"
            ),
        )
        return {"FINISHED"}


class CLMR_OT_replace_selected(bpy.types.Operator):
    bl_idname = "clmr.replace_selected"
    bl_label = "Replace Selected"
    bl_description = "Replace the active object with a linked copy of its source match"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.clmr_settings
        if not _cache_ready(self, settings):
            return {"CANCELLED"}

        target = context.active_object
        if target is None or target.type != "MESH" or target.data is None:
            self.report({"ERROR"}, "Active object is not a Mesh")
            return {"CANCELLED"}
        if not _is_valid_target(target, settings):
            self.report({"WARNING"}, "Active object is in the Source Collection")
            return {"CANCELLED"}

        status, new_obj = _replace_object(context, target, settings)
        if status == "NOT_FOUND":
            self.report({"WARNING"}, "No match found")
            return {"CANCELLED"}
        if status != "REPLACED":
            self.report({"ERROR"}, "Match verification failed")
            return {"CANCELLED"}

        if settings.select_new_objects:
            bpy.ops.object.select_all(action="DESELECT")
            new_obj.hide_set(False)
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj

        self.report({"INFO"}, f"Replaced with linked mesh: {new_obj.name}")
        return {"FINISHED"}


class CLMR_OT_replace_all_selected(bpy.types.Operator):
    bl_idname = "clmr.replace_all_selected"
    bl_label = "Replace All Selected"
    bl_description = "Replace every selected mesh object that has a source match"
    bl_options = {"REGISTER", "UNDO"}

    target_count: bpy.props.IntProperty(default=0, options={"HIDDEN"})

    def invoke(self, context, event):
        settings = context.scene.clmr_settings
        self.target_count = sum(
            1
            for obj in context.selected_objects
            if _is_valid_target(obj, settings)
        )
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        self.layout.label(
            text=f"Replace {self.target_count} selected mesh objects?",
            icon="QUESTION",
        )

    def execute(self, context):
        settings = context.scene.clmr_settings
        if not _cache_ready(self, settings):
            return {"CANCELLED"}

        selected = list(context.selected_objects)
        created = []
        replaced = 0
        not_found = 0
        failed = 0
        skipped = 0

        for target in selected:
            if not _is_valid_target(target, settings):
                skipped += 1
                continue
            try:
                status, new_obj = _replace_object(context, target, settings)
            except (ReferenceError, RuntimeError, ValueError):
                failed += 1
                continue

            if status == "REPLACED":
                replaced += 1
                created.append(new_obj)
            elif status == "NOT_FOUND":
                not_found += 1
            else:
                failed += 1

        settings.batch_replaced = replaced
        settings.batch_not_found = not_found
        settings.batch_failed = failed
        settings.batch_skipped = skipped

        if settings.select_new_objects:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in created:
                obj.hide_set(False)
                obj.select_set(True)
            if created:
                context.view_layer.objects.active = created[-1]

        self.report(
            {"INFO"},
            (
                f"Replaced: {replaced}, Not Found: {not_found}, "
                f"Failed: {failed}, Skipped: {skipped}"
            ),
        )
        return {"FINISHED"}
