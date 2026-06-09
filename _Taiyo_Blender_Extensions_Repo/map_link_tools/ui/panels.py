from bpy.types import Panel


COLLECTION_COLOR_ICONS = {
    "COLOR_01": "COLLECTION_COLOR_01",
    "COLOR_02": "COLLECTION_COLOR_02",
    "COLOR_03": "COLLECTION_COLOR_03",
    "COLOR_04": "COLLECTION_COLOR_04",
    "COLOR_05": "COLLECTION_COLOR_05",
    "COLOR_06": "COLLECTION_COLOR_06",
    "COLOR_07": "COLLECTION_COLOR_07",
    "COLOR_08": "COLLECTION_COLOR_08",
}


def collection_icon(collection):
    if collection is None:
        return "OUTLINER_COLLECTION"
    return COLLECTION_COLOR_ICONS.get(collection.color_tag, "OUTLINER_COLLECTION")


def collection_prop(layout, settings, prop_name, text):
    collection = getattr(settings, prop_name)
    layout.prop(settings, prop_name, text=text, icon=collection_icon(collection))


def draw_foldout(layout, settings, prop_name, label):
    row = layout.row(align=True)
    row.alignment = "LEFT"
    opened = getattr(settings, prop_name)
    row.prop(
        settings,
        prop_name,
        text=label,
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
        emboss=False,
    )
    return opened


class VIEW3D_PT_map_link_tools(Panel):
    bl_label = "Map Link Tools"
    bl_idname = "VIEW3D_PT_map_link_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Map Link Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.maplink_settings

        if draw_foldout(layout, settings, "show_rename", "Rename"):
            box = layout.box()
            box.prop(settings, "rename_unselected_conflicts")
            box.operator("maplink.remove_suffix_selected", icon="SORTALPHA")
            box.operator("maplink.object_name_to_mesh_name", icon="MESH_DATA")
            box.operator("maplink.mesh_name_to_object_name", icon="OBJECT_DATA")

        if draw_foldout(layout, settings, "show_check", "Check"):
            box = layout.box()
            row = box.row(align=True)
            collection_prop(row, settings, "collection_a", "A")
            op = row.operator("maplink.select_unlinked_in_collection", text="Select Unlinked", icon="RESTRICT_SELECT_OFF")
            op.side = "A"

            row = box.row(align=True)
            collection_prop(row, settings, "collection_b", "B")
            op = row.operator("maplink.select_unlinked_in_collection", text="Select Unlinked", icon="RESTRICT_SELECT_OFF")
            op.side = "B"

            box.operator("maplink.check_collection_mesh_links", icon="LINKED")
            if settings.check_result_message:
                box.label(text=settings.check_result_message, icon="INFO")

        if draw_foldout(layout, settings, "show_replace", "Replace"):
            box = layout.box()
            box.prop(settings, "use_mesh_instance")
            box.operator("maplink.replace_selected_with_active_object", icon="DUPLICATE")

            box.separator(factor=0.5)
            row = box.row(align=True)
            collection_prop(row, settings, "replace_collection", "Collection")
            row.operator("maplink.set_replace_collection_from_active_layer", text="Set", icon="OUTLINER_COLLECTION")
            box.operator("maplink.replace_selected_with_collection_instance", icon="OUTLINER_OB_GROUP_INSTANCE")

            box.separator(factor=0.5)
            collection_prop(box, settings, "matching_mesh_collection", "Mesh Collection")
            box.operator("maplink.replace_collection_instances_with_matching_mesh", icon="MESH_DATA")

        if draw_foldout(layout, settings, "show_helper", "Helper"):
            box = layout.box()
            collection_prop(box, settings, "helper_collection", "Collection")
            box.prop(settings, "helper_make_selectable")
            box.operator("maplink.unhide_helper_collection", icon="HIDE_OFF")
            box.operator("maplink.make_helper_collection_selectable", icon="RESTRICT_SELECT_OFF")
            if settings.helper_result_message:
                box.label(text=settings.helper_result_message, icon="INFO")

        if settings.is_running or settings.operation_message:
            box = layout.box()
            box.label(text=settings.operation_name or "Operation", icon="TIME")
            if settings.total_count:
                box.label(text=f"Processed: {settings.processed_count} / {settings.total_count}")
                box.label(text=f"Progress: {settings.progress_percent:.1f}%")
            else:
                box.label(text=f"Processed: {settings.processed_count}")
            if settings.operation_message:
                box.label(text=settings.operation_message, icon="INFO")
            row = box.row(align=True)
            row.enabled = settings.is_running
            row.operator("maplink.cancel_operation", icon="CANCEL")
