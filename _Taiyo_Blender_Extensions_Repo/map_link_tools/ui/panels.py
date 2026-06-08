from bpy.types import Panel


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
            box.operator("maplink.remove_suffix_selected", icon="SORTALPHA")
            box.operator("maplink.object_name_to_mesh_name", icon="MESH_DATA")
            box.operator("maplink.mesh_name_to_object_name", icon="OBJECT_DATA")

        if draw_foldout(layout, settings, "show_check", "Check"):
            box = layout.box()
            row = box.row(align=True)
            row.prop(settings, "collection_a", text="A")
            op = row.operator("maplink.select_unlinked_in_collection", text="Select Unlinked", icon="RESTRICT_SELECT_OFF")
            op.side = "A"

            row = box.row(align=True)
            row.prop(settings, "collection_b", text="B")
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
            row.prop(settings, "replace_collection", text="Collection")
            row.operator("maplink.set_replace_collection_from_active_layer", text="Set", icon="OUTLINER_COLLECTION")
            box.operator("maplink.replace_selected_with_collection_instance", icon="OUTLINER_OB_GROUP_INSTANCE")

            box.separator(factor=0.5)
            box.prop(settings, "matching_mesh_collection", text="Mesh Collection")
            box.operator("maplink.replace_collection_instances_with_matching_mesh", icon="MESH_DATA")
