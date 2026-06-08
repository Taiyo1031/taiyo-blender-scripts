from bpy.types import Panel


class VIEW3D_PT_blend_reference_graph(Panel):
    bl_label = "Blend Reference Graph"
    bl_idname = "VIEW3D_PT_blend_reference_graph"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Blend Ref Graph"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.brg_settings

        box = layout.box()
        box.label(text="Target", icon="RESTRICT_SELECT_OFF")
        box.operator("brg.use_selected", icon="EYEDROPPER")
        if settings.target_name:
            box.label(text=f"Type: {settings.target_type}")
            box.label(text=f"Name: {settings.target_name}")
        else:
            box.label(text="No target selected", icon="INFO")

        box = layout.box()
        box.label(text="Scan", icon="VIEWZOOM")
        box.prop(settings, "scan_mode", expand=True)
        box.prop(settings, "depth")

        box = layout.box()
        box.label(text="Filters", icon="FILTER")
        col = box.column(align=True)
        col.prop(settings, "include_objects")
        col.prop(settings, "include_meshes")
        col.prop(settings, "include_collections")
        col.prop(settings, "include_armatures")
        col.prop(settings, "include_bones")
        col.prop(settings, "include_constraints")
        col.prop(settings, "include_geonodes")
        col.prop(settings, "include_node_groups")
        col.prop(settings, "include_materials")
        col.prop(settings, "include_images")

        box = layout.box()
        box.label(text="Actions", icon="PLAY")
        box.operator("brg.update_and_open_viewer", icon="FILE_REFRESH")
        row = box.row(align=True)
        row.operator("brg.update_graph_data", icon="FILE_TICK")
        row.operator("brg.open_viewer", icon="URL")

        box = layout.box()
        box.label(text="Output", icon="FILE_FOLDER")
        box.prop(settings, "output_folder")
        box.prop(settings, "viewer_file")

        box = layout.box()
        box.label(text="Status", icon="INFO")
        box.label(text=f"Last Update: {settings.last_update}")
        box.label(text=f"Nodes: {settings.node_count}  Edges: {settings.edge_count}")
        if settings.status_message:
            box.label(text=settings.status_message)
