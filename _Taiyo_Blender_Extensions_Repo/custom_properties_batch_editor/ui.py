from bpy.types import Panel, UIList

from . import property_utils, target_utils


def _draw_typed_value(layout, data, property_type, prefix=""):
    property_name = {
        "STRING": f"{prefix}string_value",
        "INT": f"{prefix}int_value",
        "FLOAT": f"{prefix}float_value",
        "BOOL": f"{prefix}bool_value",
    }[property_type]
    layout.prop(data, property_name)


def _delete_candidate_count(context, settings):
    valid, name_or_error = property_utils.validate_property_name(
        settings.delete_property_name
    )
    if not valid:
        return 0
    expected = None
    if settings.delete_mode == "VALUE":
        expected = property_utils.get_typed_value(
            settings,
            settings.delete_property_type,
            prefix="delete_",
        )
    records, _skipped = target_utils.get_target_records(context, settings)
    count = 0
    for record in records:
        if not property_utils.has_custom_property(record.target, name_or_error):
            continue
        if settings.delete_mode == "VALUE" and not property_utils.values_equal(
            record.target[name_or_error],
            expected,
            settings.delete_property_type,
            case_sensitive=True,
        ):
            continue
        count += 1
    return count


class CPBE_UL_property_summary(UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.label(text=item.property_name, icon="PROPERTIES")
        row.label(text=item.value_type)
        row.label(text=item.value_preview)
        row.label(text=str(item.target_count))


class CPBE_UL_preset_properties(UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        row = layout.row(align=True)
        row.label(text=item.property_name or "(unnamed)", icon="DOT")
        row.label(text=item.property_type)
        row.label(text=property_utils.format_value(property_utils.get_item_typed_value(item)))


class CPBE_PT_main(Panel):
    bl_label = "Custom Properties Batch Editor"
    bl_idname = "CPBE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Custom Props"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        records, skipped = target_utils.get_target_records(context, settings)
        layout.label(
            text=f"{settings.target_type.title()} Targets: {len(records)}",
            icon="PROPERTIES",
        )
        if skipped:
            layout.label(text=f"Filtered / incompatible: {len(skipped)}", icon="INFO")


class CPBE_ChildPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Custom Props"
    bl_parent_id = "CPBE_PT_main"


class CPBE_PT_target(CPBE_ChildPanel, Panel):
    bl_label = "Target"
    bl_idname = "CPBE_PT_target"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        layout.prop(settings, "target_type")
        layout.prop(settings, "scope")
        layout.prop(settings, "include_hidden")
        layout.prop(settings, "include_disabled_viewport")
        if settings.target_type == "MESH":
            layout.prop(settings, "unique_data_only")


class CPBE_PT_add_edit(CPBE_ChildPanel, Panel):
    bl_label = "Add / Edit Property"
    bl_idname = "CPBE_PT_add_edit"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        layout.prop(settings, "property_name")
        layout.prop(settings, "property_type")
        _draw_typed_value(layout, settings, settings.property_type)
        layout.prop(settings, "operation_mode")
        layout.operator("cpbe.apply_property", icon="CHECKMARK")


class CPBE_PT_search(CPBE_ChildPanel, Panel):
    bl_label = "Search / Select"
    bl_idname = "CPBE_PT_search"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        layout.prop(settings, "search_property_name")
        layout.prop(settings, "search_match_mode")
        if settings.search_match_mode == "EQUALS":
            layout.prop(settings, "search_property_type")
            _draw_typed_value(
                layout,
                settings,
                settings.search_property_type,
                prefix="search_",
            )
            if settings.search_property_type == "STRING":
                layout.prop(settings, "case_sensitive")
        elif settings.search_match_mode == "CONTAINS":
            layout.prop(settings, "search_string_value")
            layout.prop(settings, "case_sensitive")

        row = layout.row(align=True)
        op = row.operator("cpbe.search_property", text="Print Result", icon="VIEWZOOM")
        op.select_results = False
        op = row.operator("cpbe.search_property", text="Select Results", icon="RESTRICT_SELECT_OFF")
        op.select_results = True
        if context.mode != "OBJECT":
            layout.label(text="Search selection requires Object Mode.", icon="ERROR")


class CPBE_PT_delete(CPBE_ChildPanel, Panel):
    bl_label = "Delete Property"
    bl_idname = "CPBE_PT_delete"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        layout.prop(settings, "delete_property_name")
        layout.prop(settings, "delete_mode")
        if settings.delete_mode == "VALUE":
            layout.prop(settings, "delete_property_type")
            _draw_typed_value(
                layout,
                settings,
                settings.delete_property_type,
                prefix="delete_",
            )
        layout.label(text=f"Matching Targets: {_delete_candidate_count(context, settings)}")
        layout.prop(settings, "confirm_delete")
        row = layout.row()
        row.enabled = settings.confirm_delete
        row.operator("cpbe.delete_property", icon="TRASH")


class CPBE_PT_property_list(CPBE_ChildPanel, Panel):
    bl_label = "Property List"
    bl_idname = "CPBE_PT_property_list"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        layout.prop(settings, "property_list_mode")
        layout.operator("cpbe.refresh_property_list", icon="FILE_REFRESH")
        layout.template_list(
            "CPBE_UL_property_summary",
            "",
            settings,
            "property_summaries",
            settings,
            "property_summary_index",
            rows=6,
        )


class CPBE_PT_presets(CPBE_ChildPanel, Panel):
    bl_label = "Presets"
    bl_idname = "CPBE_PT_presets"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings

        layout.prop(settings, "selected_preset")
        row = layout.row(align=True)
        row.operator("cpbe.apply_preset", icon="CHECKMARK")
        row.operator("cpbe.load_preset_to_editor", icon="IMPORT")
        row.operator("cpbe.delete_preset", text="", icon="TRASH")

        layout.separator()
        layout.label(text="Preset Editor")
        layout.prop(settings, "preset_name")
        layout.operator("cpbe.add_preset_item", icon="ADD")
        layout.template_list(
            "CPBE_UL_preset_properties",
            "",
            settings,
            "preset_properties",
            settings,
            "preset_property_index",
            rows=5,
        )
        row = layout.row(align=True)
        row.operator("cpbe.remove_preset_item", text="Remove", icon="REMOVE")
        row.operator("cpbe.clear_preset_items", text="Clear", icon="X")

        index = settings.preset_property_index
        if 0 <= index < len(settings.preset_properties):
            item = settings.preset_properties[index]
            box = layout.box()
            box.prop(item, "property_name")
            box.prop(item, "property_type")
            _draw_typed_value(box, item, item.property_type)

        layout.operator("cpbe.save_preset", icon="FILE_TICK")
        row = layout.row(align=True)
        row.operator("cpbe.import_presets", icon="IMPORT")
        row.operator("cpbe.export_presets", icon="EXPORT")


class CPBE_PT_log(CPBE_ChildPanel, Panel):
    bl_label = "Result / Log"
    bl_idname = "CPBE_PT_log"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.cpbe_settings
        box = layout.box()
        box.label(text=f"Target Type: {settings.result_target_type}")
        box.label(text=f"Scanned: {settings.result_scanned}")
        box.label(text=f"Changed: {settings.result_changed}")
        box.label(text=f"Skipped: {settings.result_skipped}")
        box.label(text=f"Failed: {settings.result_failed}")

        lines = settings.log_text.splitlines()
        for line in lines[5:13]:
            layout.label(text=line)
        if len(lines) > 13:
            layout.label(text=f"... {len(lines) - 13} more line(s)")
        layout.operator("cpbe.copy_log", icon="COPYDOWN")
