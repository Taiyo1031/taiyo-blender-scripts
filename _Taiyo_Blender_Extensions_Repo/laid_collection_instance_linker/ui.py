import bpy


STATUS_ICONS = {
    "LINKED": "CHECKMARK",
    "MISSING": "ERROR",
    "DUPLICATE": "DUPLICATE",
    "SKIPPED": "FORWARD",
}


class LCIL_UL_preview_results(bpy.types.UIList):
    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        if not data.show_issues_only:
            return [self.bitflag_filter_item] * len(items), []
        flags = [
            self.bitflag_filter_item
            if item.status in {"MISSING", "DUPLICATE"}
            else 0
            for item in items
        ]
        return flags, []

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
            row.label(
                text=item.status,
                icon=STATUS_ICONS.get(item.status, "INFO"),
            )
            row.label(text=item.object_name, icon="OBJECT_DATA")
            row.label(text=item.match_key or "-")
            row.label(text=item.target_collection or "-")
            color_icon = (
                f"COLLECTION_{item.color_tag}"
                if item.color_tag.startswith("COLOR_")
                else "OUTLINER_COLLECTION"
            )
            row.label(text="", icon=color_icon)
            operator = row.operator(
                "lcil.select_object",
                text="",
                icon="RESTRICT_SELECT_OFF",
            )
            operator.object_name = item.object_name
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.status, icon=STATUS_ICONS.get(item.status, "INFO"))


class LCIL_PT_main(bpy.types.Panel):
    bl_label = "CW_Laid Collection Instance Linker"
    bl_idname = "LCIL_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Laid Linker"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.lcil_settings

        box = layout.box()
        box.label(text="Collections", icon="OUTLINER_COLLECTION")
        box.prop(settings, "laid_map_collection")
        box.prop(settings, "individual_root")
        box.prop(settings, "output_collection_name")

        box = layout.box()
        box.label(text="Match Settings", icon="VIEWZOOM")
        box.prop(settings, "name_source")
        box.prop(settings, "ignore_numeric_suffix")
        box.prop(settings, "only_mesh_objects")
        box.prop(settings, "group_by_target")
        box.prop(settings, "instance_prefix")

        column = layout.column(align=True)
        column.scale_y = 1.2
        column.operator("lcil.preview_link", icon="VIEWZOOM")
        column.operator("lcil.generate_instances", icon="OUTLINER_OB_GROUP_INSTANCE")

        box = layout.box()
        box.label(text="Preview Results", icon="PREVIEW_RANGE")
        box.prop(settings, "show_issues_only")
        if settings.preview_items:
            box.label(
                text=(
                    f"Linked {settings.preview_linked}  "
                    f"Missing {settings.preview_missing}  "
                    f"Duplicate {settings.preview_duplicate}  "
                    f"Skipped {settings.preview_skipped}"
                )
            )
            box.template_list(
                "LCIL_UL_preview_results",
                "",
                settings,
                "preview_items",
                settings,
                "preview_index",
                rows=min(10, max(3, len(settings.preview_items))),
            )
            box.operator(
                "lcil.select_issue_objects",
                icon="RESTRICT_SELECT_OFF",
            )
            if settings.preview_index < len(settings.preview_items):
                item = settings.preview_items[settings.preview_index]
                if item.detail:
                    detail = box.box()
                    detail.label(text=f"Detail: {item.detail}", icon="INFO")
        else:
            box.label(text="Press Preview / Link to inspect matches")

        box = layout.box()
        box.label(text="Generated Instances", icon="OUTLINER_OB_GROUP_INSTANCE")
        box.operator("lcil.realize_instances", icon="DUPLICATE")
        box.operator("lcil.delete_generated_empties", icon="TRASH")
