import bpy

from . import cache


STATUS_LABELS = {
    "NOT_BUILT": ("Not Built", "INFO"),
    "VALID": ("Valid", "CHECKMARK"),
    "OUTDATED": ("Outdated", "ERROR"),
}


def _status(settings):
    return cache.cache_status(
        settings.source_collection,
        settings.recursive_search,
    )


class CLMR_PT_source(bpy.types.Panel):
    bl_label = "Collection Linked Mesh Replacer"
    bl_idname = "CLMR_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mesh Replace"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.clmr_settings
        layout.prop(settings, "source_collection")

        box = layout.box()
        if settings.source_collection is None:
            box.label(text="Select a Source Collection", icon="ERROR")
            return

        box.label(
            text=f"Collection Color: {cache.color_tag_label(settings.source_collection)}",
            icon="COLOR",
        )
        status = _status(settings)
        label, icon = STATUS_LABELS[status]
        box.label(text=f"Cache Status: {label}", icon=icon)
        box.label(
            text=(
                f"Cached: {cache.CACHE.get('cached_object_count', 0)} objects / "
                f"{cache.CACHE.get('unique_mesh_count', 0)} unique meshes"
            ),
            icon="MESH_DATA",
        )


class CLMR_PT_actions(bpy.types.Panel):
    bl_label = "Main Actions"
    bl_idname = "CLMR_PT_actions"
    bl_parent_id = "CLMR_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.clmr_settings
        ready = bool(cache.CACHE) and settings.source_collection is not None

        column = layout.column(align=True)
        column.enabled = ready
        column.scale_y = 1.25
        column.operator("clmr.find_match", icon="VIEWZOOM")
        column.operator("clmr.preview_selected", icon="VIEWZOOM")
        column.operator("clmr.replace_selected", icon="FILE_REFRESH")
        column.operator("clmr.replace_all_selected", icon="DUPLICATE")


class CLMR_PT_match_result(bpy.types.Panel):
    bl_label = "Match Result"
    bl_idname = "CLMR_PT_match_result"
    bl_parent_id = "CLMR_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.clmr_settings
        box = layout.box()
        box.label(text=f"Selected: {settings.result_selected or '-'}")
        box.label(text=f"Match: {settings.result_match or 'Not Found'}")
        box.label(text=f"Source Mesh: {settings.result_source_mesh or '-'}")
        box.label(text=f"Confidence: {settings.result_confidence}")
        box.label(text=f"Candidates: {settings.result_candidates}")
        if settings.result_candidates > 1:
            box.label(text="Multiple candidates: using first match", icon="ERROR")

        if settings.preview_items:
            layout.separator(factor=0.5)
            box = layout.box()
            box.label(text="Selected Preview", icon="VIEWZOOM")
            box.label(
                text=(
                    f"Matched: {settings.preview_matched} / "
                    f"Not Found: {settings.preview_not_found} / "
                    f"Skipped: {settings.preview_skipped}"
                )
            )
            if settings.preview_multiple:
                box.label(
                    text=f"Multiple Candidate Targets: {settings.preview_multiple}",
                    icon="ERROR",
                )
            box.template_list(
                "CLMR_UL_preview_results",
                "",
                settings,
                "preview_items",
                settings,
                "preview_index",
                rows=min(8, max(2, len(settings.preview_items))),
            )


class CLMR_PT_fallback(bpy.types.Panel):
    bl_label = "Fallback / Manual"
    bl_idname = "CLMR_PT_fallback"
    bl_parent_id = "CLMR_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.clmr_settings
        active = context.active_object
        active_is_mesh = (
            active is not None
            and active.type == "MESH"
            and active.data is not None
        )

        box = layout.box()
        box.label(text="Slow Thorough Search", icon="VIEWZOOM")
        box.label(text="Bypasses cache and scans every source mesh")
        row = box.row(align=True)
        row.enabled = settings.source_collection is not None and active_is_mesh
        row.operator("clmr.thorough_find_match", icon="VIEWZOOM")
        row.operator("clmr.thorough_replace_active", icon="FILE_REFRESH")

        box = layout.box()
        box.label(text="Manual Replacement", icon="EYEDROPPER")
        box.label(text=f"Active Target: {active.name if active_is_mesh else '-'}")
        box.prop(settings, "manual_source_object")
        row = box.row()
        row.enabled = (
            active_is_mesh
            and settings.manual_source_object is not None
            and settings.manual_source_object != active
        )
        row.operator("clmr.replace_active_manual", icon="FILE_REFRESH")


class CLMR_UL_preview_results(bpy.types.UIList):
    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.target_name or "-", icon="OBJECT_DATA")
            match_text = item.match_name or item.confidence or "-"
            row.label(text=f"-> {match_text}")
            if item.candidate_count:
                icon_name = "ERROR" if item.using_first else "INFO"
                row.label(text=str(item.candidate_count), icon=icon_name)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.target_name[:8])


class CLMR_PT_cache(bpy.types.Panel):
    bl_label = "Cache"
    bl_idname = "CLMR_PT_cache"
    bl_parent_id = "CLMR_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.clmr_settings
        status = _status(settings)
        label, icon = STATUS_LABELS[status]

        column = layout.column(align=True)
        column.label(text=f"Status: {label}", icon=icon)
        column.label(
            text=f"Cached Objects: {cache.CACHE.get('cached_object_count', 0)}"
        )
        column.label(
            text=f"Unique Meshes: {cache.CACHE.get('unique_mesh_count', 0)}"
        )
        column.label(
            text=(
                "Duplicated Signatures: "
                f"{cache.CACHE.get('duplicated_signature_count', 0)}"
            )
        )
        column.label(text=f"Last Built: {cache.CACHE.get('built_time', '-')}")

        row = layout.row(align=True)
        row.operator("clmr.build_cache", icon="FILE_REFRESH")
        row.operator("clmr.clear_cache", icon="TRASH")


class CLMR_PT_settings(bpy.types.Panel):
    bl_label = "Settings"
    bl_idname = "CLMR_PT_settings"
    bl_parent_id = "CLMR_PT_source"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.clmr_settings

        box = layout.box()
        box.label(text="Match Settings", icon="VIEWZOOM")
        box.prop(settings, "match_method")
        box.prop(settings, "verify_match")
        box.prop(settings, "recursive_search")

        box = layout.box()
        box.label(text="Transform", icon="ORIENTATION_GLOBAL")
        box.prop(settings, "keep_transform")
        box.prop(settings, "adjust_bbox_center")

        box = layout.box()
        box.label(text="Original Object", icon="OBJECT_DATA")
        box.prop(settings, "original_mode")
        if settings.original_mode == "BACKUP":
            box.prop(settings, "backup_collection_name")

        box = layout.box()
        box.label(text="Advanced", icon="PREFERENCES")
        box.prop(settings, "multiple_matches")
        box.prop(settings, "ignore_source_objects")
        box.prop(settings, "select_new_objects")
        box.prop(settings, "rename_to_source")
