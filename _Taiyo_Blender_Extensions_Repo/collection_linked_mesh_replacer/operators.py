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
    settings.preview_multiple = 0


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
    confidence = first.get("confidence", "Exact")
    settings.result_confidence = (
        confidence if len(candidates) == 1 else f"{confidence} / Multiple"
    )


def _multiple_match_message(target_name, candidates):
    names = ", ".join(candidate["object_name"] for candidate in candidates[:5])
    if len(candidates) > 5:
        names += ", ..."
    return (
        f"Multiple matches for {target_name}: {len(candidates)} candidates. "
        f"Using first: {candidates[0]['object_name']} ({names})"
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


def _compensate_bbox_scale(matrix, target_signature, source_signature):
    adjusted = matrix.copy()
    target_size = target_signature.get("bbox_size", ())
    source_size = source_signature.get("bbox_size", ())
    if len(target_size) != 3 or len(source_size) != 3:
        return adjusted

    for axis in range(3):
        source_value = abs(float(source_size[axis]))
        target_value = abs(float(target_size[axis]))
        if source_value <= 1.0e-12 or target_value <= 1.0e-12:
            continue
        adjusted.col[axis][0] *= target_value / source_value
        adjusted.col[axis][1] *= target_value / source_value
        adjusted.col[axis][2] *= target_value / source_value
    return adjusted


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


def _hide_object_safely(obj, view_layer):
    obj.hide_viewport = True
    obj.hide_render = True
    if obj.name not in view_layer.objects:
        return
    try:
        obj.hide_set(True, view_layer=view_layer)
    except RuntimeError:
        pass


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
        _hide_object_safely(target, context.view_layer)
        for collection in list(target.users_collection):
            if collection != backup:
                collection.objects.unlink(target)
    elif mode == "DELETE":
        bpy.data.objects.remove(target, do_unlink=True)
    elif mode == "HIDE":
        _hide_object_safely(target, context.view_layer)


def _replace_object(context, target, settings, candidates=None):
    target_signature = cache.mesh_signature(target.data)
    if candidates is None:
        _signature, candidates = cache.find_candidates(target)
    _set_match_result(settings, target, candidates)
    if not candidates:
        return "NOT_FOUND", None

    source = cache.resolve_source_object(candidates[0])
    if source is None or source.type != "MESH" or source.data is None:
        return "FAILED", None

    source_signature = cache.mesh_signature(source.data)
    match_kind = candidates[0].get("match_kind", "EXACT")
    if settings.verify_match and match_kind != "MANUAL":
        if match_kind.startswith("THOROUGH"):
            verified = (
                cache.thorough_mesh_match_kind(target.data, source.data)
                is not None
            )
        else:
            verified = cache.signatures_match(
                target_signature,
                source_signature,
                match_kind,
            )
        if not verified:
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
        if match_kind in {"EXACT", "MANUAL"}:
            new_obj.matrix_world = target_matrix
        else:
            new_obj.matrix_world = _compensate_bbox_scale(
                target_matrix,
                target_signature,
                source_signature,
            )
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


def _select_replacement(context, settings, new_obj):
    if not settings.select_new_objects:
        return
    bpy.ops.object.select_all(action="DESELECT")
    new_obj.hide_set(False)
    new_obj.select_set(True)
    context.view_layer.objects.active = new_obj


def _active_target(operator, context, settings):
    target = context.active_object
    if target is None or target.type != "MESH" or target.data is None:
        operator.report({"ERROR"}, "Active object is not a Mesh")
        return None
    if not _is_valid_target(target, settings):
        operator.report({"WARNING"}, "Active object is in the Source Collection")
        return None
    return target


def _set_preview_results(settings, selected, candidates_by_pointer):
    _clear_single_match_result(settings)
    settings.preview_items.clear()
    settings.preview_index = 0
    matched = 0
    not_found = 0
    skipped = 0
    multiple = 0

    for obj in selected:
        item = settings.preview_items.add()
        item.target_name = obj.name if obj else ""
        if not _is_valid_target(obj, settings):
            item.confidence = "Skipped"
            skipped += 1
            continue

        candidates = candidates_by_pointer.get(obj.as_pointer(), [])
        item.candidate_count = len(candidates)
        if not candidates:
            item.confidence = "Not Found"
            not_found += 1
            continue

        first = candidates[0]
        item.match_name = first["object_name"]
        item.source_mesh = first["mesh_name"]
        item.using_first = len(candidates) > 1
        confidence = first.get("confidence", "Exact")
        item.confidence = (
            confidence if len(candidates) == 1 else f"{confidence} / Multiple"
        )
        matched += 1
        if len(candidates) > 1:
            multiple += 1

        if obj == bpy.context.active_object:
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
    settings.preview_multiple = multiple


def _prepare_selected_preview(operator, context, settings):
    if settings.source_collection is None:
        operator.report({"ERROR"}, "No Source Collection selected")
        return None, None

    selected = list(context.selected_objects)
    if not selected:
        _clear_match_result(settings)
        operator.report({"WARNING"}, "No objects selected")
        return None, None

    status = cache.cache_status(
        settings.source_collection,
        settings.recursive_search,
    )
    rebuilt = False
    if status == "NOT_BUILT":
        if not settings.auto_rebuild_on_no_match:
            operator.report({"ERROR"}, "Cache is not built")
            return None, None
        cache.build_cache(
            settings.source_collection,
            settings.recursive_search,
        )
        rebuilt = True
    elif status == "OUTDATED":
        operator.report({"WARNING"}, "Cache is outdated")

    def collect_candidates():
        result = {}
        missing = False
        for obj in selected:
            if not _is_valid_target(obj, settings):
                continue
            _signature, candidates = cache.find_candidates(obj)
            result[obj.as_pointer()] = candidates
            if not candidates:
                missing = True
        return result, missing

    candidates_by_pointer, missing = collect_candidates()
    if (
        missing
        and settings.auto_rebuild_on_no_match
        and not rebuilt
    ):
        cache.build_cache(
            settings.source_collection,
            settings.recursive_search,
        )
        candidates_by_pointer, _missing = collect_candidates()
        rebuilt = True

    _set_preview_results(settings, selected, candidates_by_pointer)
    return selected, candidates_by_pointer


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
                {"WARNING"},
                _multiple_match_message(target.name, candidates),
            )
        else:
            self.report({"INFO"}, f"Match found: {candidates[0]['object_name']}")
        return {"FINISHED"}


class CLMR_OT_thorough_find_match(bpy.types.Operator):
    bl_idname = "clmr.thorough_find_match"
    bl_label = "Thorough Check Active"
    bl_description = (
        "Bypass the cache and compare the active mesh against every source mesh "
        "with tolerant geometry checks"
    )

    def execute(self, context):
        settings = context.scene.clmr_settings
        if settings.source_collection is None:
            self.report({"ERROR"}, "No Source Collection selected")
            return {"CANCELLED"}

        target = _active_target(self, context, settings)
        if target is None:
            return {"CANCELLED"}

        _signature, candidates = cache.find_candidates_thorough(
            target,
            settings.source_collection,
            settings.recursive_search,
        )
        _set_match_result(settings, target, candidates)
        if not candidates:
            self.report({"WARNING"}, "No match found after thorough check")
            return {"FINISHED"}

        if len(candidates) > 1:
            self.report(
                {"WARNING"},
                _multiple_match_message(target.name, candidates),
            )
        else:
            self.report(
                {"INFO"},
                f"Thorough match found: {candidates[0]['object_name']}",
            )
        return {"FINISHED"}


class CLMR_OT_thorough_replace_active(bpy.types.Operator):
    bl_idname = "clmr.thorough_replace_active"
    bl_label = "Thorough Replace Active"
    bl_description = (
        "Scan every source mesh with tolerant checks and replace the active object"
    )
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = context.scene.clmr_settings
        if settings.source_collection is None:
            self.report({"ERROR"}, "No Source Collection selected")
            return {"CANCELLED"}

        target = _active_target(self, context, settings)
        if target is None:
            return {"CANCELLED"}

        _signature, candidates = cache.find_candidates_thorough(
            target,
            settings.source_collection,
            settings.recursive_search,
        )
        if not candidates:
            _set_match_result(settings, target, candidates)
            self.report({"WARNING"}, "No match found after thorough check")
            return {"CANCELLED"}

        status, new_obj = _replace_object(
            context,
            target,
            settings,
            candidates=candidates,
        )
        if status != "REPLACED":
            self.report({"ERROR"}, "Thorough match verification failed")
            return {"CANCELLED"}

        _select_replacement(context, settings, new_obj)
        level = {"WARNING"} if len(candidates) > 1 else {"INFO"}
        self.report(
            level,
            f"Thorough replacement completed: {new_obj.name}",
        )
        return {"FINISHED"}


class CLMR_OT_replace_active_manual(bpy.types.Operator):
    bl_idname = "clmr.replace_active_manual"
    bl_label = "Replace Active Manually"
    bl_description = (
        "Replace the active object using the manually specified Mesh Object"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.clmr_settings
        target = _active_target(self, context, settings)
        if target is None:
            return {"CANCELLED"}

        source = settings.manual_source_object
        if source is None or source.type != "MESH" or source.data is None:
            self.report({"ERROR"}, "Select a Manual Source Object")
            return {"CANCELLED"}
        if source.as_pointer() == target.as_pointer():
            self.report({"ERROR"}, "Manual source cannot be the active target")
            return {"CANCELLED"}

        source_signature = cache.mesh_signature(source.data)
        candidates = [
            {
                "object_name": source.name,
                "object_ref": source,
                "mesh_name": source.data.name,
                **source_signature,
                "match_kind": "MANUAL",
                "confidence": "Manual",
            }
        ]
        status, new_obj = _replace_object(
            context,
            target,
            settings,
            candidates=candidates,
        )
        if status != "REPLACED":
            self.report({"ERROR"}, "Manual replacement failed")
            return {"CANCELLED"}

        _select_replacement(context, settings, new_obj)
        self.report(
            {"INFO"},
            f"Manually replaced with: {source.name}",
        )
        return {"FINISHED"}


class CLMR_OT_find_selected(bpy.types.Operator):
    bl_idname = "clmr.find_selected"
    bl_label = "Find"
    bl_description = "Find source matches for every selected object and show the list"

    def execute(self, context):
        settings = context.scene.clmr_settings
        selected, _candidates = _prepare_selected_preview(
            self,
            context,
            settings,
        )
        if selected is None:
            return {"CANCELLED"}

        level = {"WARNING"} if (
            settings.preview_not_found or settings.preview_multiple
        ) else {"INFO"}
        self.report(
            level,
            (
                f"Found: {settings.preview_matched}, "
                f"Not Found: {settings.preview_not_found}, "
                f"Skipped: {settings.preview_skipped}, "
                f"Multiple: {settings.preview_multiple}"
            ),
        )
        return {"FINISHED"}


class CLMR_OT_replace_all_selected(bpy.types.Operator):
    bl_idname = "clmr.replace_all_selected"
    bl_label = "Replace"
    bl_description = "Replace every selected mesh object that has a source match"
    bl_options = {"REGISTER", "UNDO"}

    target_count: bpy.props.IntProperty(default=0, options={"HIDDEN"})

    def invoke(self, context, event):
        settings = context.scene.clmr_settings
        selected, _candidates = _prepare_selected_preview(
            self,
            context,
            settings,
        )
        if selected is None:
            return {"CANCELLED"}
        self.target_count = settings.preview_matched
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        settings = context.scene.clmr_settings
        layout = self.layout
        layout.label(
            text=(
                f"Matched: {settings.preview_matched} / "
                f"Not Found: {settings.preview_not_found} / "
                f"Skipped: {settings.preview_skipped}"
            ),
            icon="FILE_REFRESH",
        )
        if settings.preview_multiple:
            layout.label(
                text=f"Multiple Candidate Targets: {settings.preview_multiple}",
                icon="ERROR",
            )
        layout.template_list(
            "CLMR_UL_preview_results",
            "",
            settings,
            "preview_items",
            settings,
            "preview_index",
            rows=min(10, max(3, len(settings.preview_items))),
        )
        layout.label(
            text=f"Replace {self.target_count} matched selected objects?",
            icon="QUESTION",
        )

    def execute(self, context):
        settings = context.scene.clmr_settings
        selected, candidates_by_pointer = _prepare_selected_preview(
            self,
            context,
            settings,
        )
        if selected is None:
            return {"CANCELLED"}

        created = []
        replaced = 0
        not_found = 0
        failed = 0
        skipped = 0
        multiple = 0

        for target in selected:
            if not _is_valid_target(target, settings):
                skipped += 1
                continue
            candidates = candidates_by_pointer.get(target.as_pointer(), [])
            if len(candidates) > 1:
                multiple += 1
            try:
                status, new_obj = _replace_object(
                    context,
                    target,
                    settings,
                    candidates=candidates,
                )
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
        settings.batch_multiple = multiple

        if settings.select_new_objects:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in created:
                obj.hide_set(False)
                obj.select_set(True)
            if created:
                context.view_layer.objects.active = created[-1]

        self.report(
            {"WARNING"} if multiple else {"INFO"},
            (
                f"Replaced: {replaced}, Not Found: {not_found}, "
                f"Failed: {failed}, Skipped: {skipped}, Multiple: {multiple}"
            ),
        )
        return {"FINISHED"}
