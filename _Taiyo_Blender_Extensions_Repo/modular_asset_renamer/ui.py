from bpy.types import Panel, UIList

from . import naming, preset_utils


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/modular_asset_renamer/README.md"
)


def _active_module(settings):
    if not settings.modules:
        return None
    return settings.modules[min(settings.module_index, len(settings.modules) - 1)]


def _draw_separator_controls(layout, module):
    layout.prop(module, "separator_after")
    row = layout.row(align=True)
    row.label(text="Quick:")
    for label, value in (
        ("none", ""),
        ("_", "_"),
        ("-", "-"),
        ("x", "x"),
        (".", "."),
    ):
        operator = row.operator("mar.set_separator", text=label)
        operator.value = value


def _repair_choice_module(module):
    if module.module_type != "CHOICE":
        return

    seen = set()
    option_id_map = {}
    for option in module.choice_options:
        old_id = option.option_id
        new_id = preset_utils.unique_choice_option_id(old_id, seen)
        seen.add(new_id)
        option_id_map[old_id] = new_id
        if old_id != new_id:
            option.option_id = new_id

    if module.choice_current in option_id_map:
        module.choice_current = option_id_map[module.choice_current]

    option_ids = [option.option_id for option in module.choice_options]
    if option_ids and module.choice_current not in option_ids:
        module.choice_current = option_ids[0]


class MAR_UL_modules(UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        index,
    ):
        row = layout.row(align=True)
        row.label(text=f"{index + 1:02d}")
        row.label(
            text=item.module_type.replace("_", " ").title(),
            icon="CHECKBOX_HLT" if item.enabled else "CHECKBOX_DEHLT",
        )
        summary = naming.module_summary(item)
        row.label(text=summary[:42])
        row.label(text=f"Sep: {item.separator_after or 'none'}")


class MAR_UL_choice_options(UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        layout.prop(item, "value", text="", emboss=False, icon="DOT")


class MAR_UL_preview(UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_propname,
        _index,
    ):
        row = layout.row(align=True)
        icon = {
            naming.STATUS_OK: "CHECKMARK",
            naming.STATUS_DUPLICATE: "ERROR",
            naming.STATUS_EMPTY: "ERROR",
            naming.STATUS_INVALID: "ERROR",
            naming.STATUS_SKIPPED: "INFO",
        }.get(item.status, "DOT")
        row.label(text=item.old_name[:28], icon=icon)
        row.label(text=">")
        row.label(text=item.new_name[:34] or "(empty)")
        row.label(text=item.status)


class MAR_PT_main(Panel):
    bl_label = "Modular Asset Renamer"
    bl_idname = "MAR_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Rename Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mar_settings

        box = layout.box()
        box.label(text="Main Actions", icon="PLAY")
        row = box.row(align=True)
        row.operator("mar.preview", icon="VIEWZOOM")
        row.operator("mar.apply", icon="CHECKMARK")
        box.operator("mar.revert", icon="LOOP_BACK")

        choice_modules = [
            module
            for module in settings.modules
            if module.module_type == "CHOICE"
        ]
        if choice_modules:
            box = layout.box()
            box.label(text="Quick Controls", icon="OPTIONS")
            for module in choice_modules:
                _repair_choice_module(module)
                row = box.row(align=True)
                row.label(text=module.choice_label or "Choice")
                if module.choice_options:
                    row.prop(module, "choice_current", text="")
                    if not module.enabled:
                        row.label(text="Disabled", icon="HIDE_OFF")
                else:
                    row.label(text="No options", icon="ERROR")
                    operator = row.operator("mar.add_choice_option", text="Add Option")
                    operator.module_id = module.module_id

        box = layout.box()
        box.label(text="Presets", icon="PRESET")
        box.prop(settings, "selected_preset")
        row = box.row(align=True)
        row.operator("mar.load_preset", text="Load", icon="IMPORT")
        row.operator("mar.save_preset", text="Save", icon="FILE_TICK")
        row.operator("mar.save_preset_as", text="Save As New", icon="ADD")
        box.operator("mar.delete_preset", icon="TRASH")
        row = box.row(align=True)
        row.operator("mar.export_presets", icon="EXPORT")
        row.operator("mar.import_presets", icon="IMPORT")

        box = layout.box()
        box.label(text="Naming Modules", icon="LINENUMBERS_ON")
        if settings.modules:
            box.template_list(
                "MAR_UL_modules",
                "",
                settings,
                "modules",
                settings,
                "module_index",
                rows=6,
            )
        else:
            box.label(text="No modules yet.", icon="INFO")

        row = box.row(align=True)
        for module_type, label in (
            ("TEXT", "Text"),
            ("CHOICE", "Choice"),
            ("DIMENSIONS", "Dimensions"),
        ):
            operator = row.operator("mar.add_module", text=f"+ {label}")
            operator.module_type = module_type
        row = box.row(align=True)
        for module_type, label in (
            ("INDEX", "Index"),
            ("ORIGINAL_NAME", "Original Name"),
            ("COLLECTION_NAME", "Collection Name"),
        ):
            operator = row.operator("mar.add_module", text=f"+ {label}")
            operator.module_type = module_type

        row = box.row(align=True)
        row.operator("mar.remove_module", text="Remove", icon="REMOVE")
        up = row.operator("mar.move_module", text="", icon="TRIA_UP")
        up.direction = "UP"
        down = row.operator("mar.move_module", text="", icon="TRIA_DOWN")
        down.direction = "DOWN"
        row.operator("mar.duplicate_module", text="Duplicate", icon="DUPLICATE")
        box.operator("mar.toggle_module", icon="HIDE_OFF")

        module = _active_module(settings)
        box = layout.box()
        box.label(text="Module Detail Editor", icon="PREFERENCES")
        if module is None:
            box.label(text="Select or add a module.", icon="INFO")
        else:
            box.prop(module, "enabled")
            box.prop(module, "display_name")
            if module.module_type == "TEXT":
                box.prop(module, "text_value")
            elif module.module_type == "CHOICE":
                _repair_choice_module(module)
                box.prop(module, "choice_label")
                if not module.choice_options:
                    box.label(text="Choice has no options.", icon="ERROR")
                box.template_list(
                    "MAR_UL_choice_options",
                    "",
                    module,
                    "choice_options",
                    module,
                    "choice_option_index",
                    rows=4,
                )
                row = box.row(align=True)
                row.operator("mar.add_choice_option", icon="ADD")
                row.operator("mar.remove_choice_option", icon="REMOVE")
                up = row.operator("mar.move_choice_option", text="", icon="TRIA_UP")
                up.direction = "UP"
                down = row.operator("mar.move_choice_option", text="", icon="TRIA_DOWN")
                down.direction = "DOWN"
                box.prop(module, "choice_current")
            elif module.module_type == "DIMENSIONS":
                box.prop(module, "axis_order")
                box.prop(module, "dimension_unit")
                box.prop(module, "axis_separator")
                box.prop(module, "decimal_places")
                box.prop(module, "round_mode")
                box.prop(module, "add_unit_suffix")
                box.prop(module, "add_axis_labels")
                box.prop(module, "remove_trailing_zeros")
            elif module.module_type == "INDEX":
                box.prop(module, "start_number")
                box.prop(module, "padding")
                box.prop(module, "sort_mode")
            elif module.module_type == "ORIGINAL_NAME":
                box.prop(module, "original_mode")
                box.prop(module, "original_strip_suffix")
                if module.original_mode == "SPLIT":
                    box.prop(module, "original_delimiter")
                    box.prop(module, "original_part_index")
            elif module.module_type == "COLLECTION_NAME":
                box.prop(module, "collection_source")
                box.prop(module, "collection_strip_suffix")
            _draw_separator_controls(box, module)

        box = layout.box()
        box.label(text="Preview", icon="VIEWZOOM")
        if settings.preview_items:
            box.template_list(
                "MAR_UL_preview",
                "",
                settings,
                "preview_items",
                settings,
                "preview_index",
                rows=6,
            )
            index = min(settings.preview_index, len(settings.preview_items) - 1)
            item = settings.preview_items[index]
            if item.message:
                box.label(text=item.message[:100], icon="INFO")
        else:
            box.label(text="Press Preview Selected to generate results.", icon="INFO")

        box = layout.box()
        box.label(text="Options", icon="OPTIONS")
        box.prop(settings, "rename_object")
        box.prop(settings, "rename_mesh_data")
        box.prop(settings, "strip_blender_numeric_suffix")
        box.prop(settings, "error_if_name_exists")
        row = box.row()
        row.enabled = not settings.error_if_name_exists
        row.prop(settings, "auto_resolve_duplicates")
        box.prop(settings, "store_original_name")
        box.prop(settings, "rename_only_mesh_objects")
        box.prop(settings, "skip_hidden_objects")
        box.prop(settings, "skip_locked_objects")
        box.prop(settings, "replace_spaces")
        box.prop(settings, "remove_invalid_characters")

        box = layout.box()
        box.label(text="Utility / Safety", icon="LOCKED")
        box.label(text=f"Selected: {len(context.selected_objects)}")
        box.label(text=f"Last valid targets: {settings.last_target_count}")
        if settings.last_warning:
            box.label(text=settings.last_warning[:110], icon="ERROR")
        if settings.history_items:
            box.label(
                text=f"Last rename history: {len(settings.history_items)} name(s)",
                icon="RECOVER_LAST",
            )
        row = box.row(align=True)
        row.operator("mar.clear_preview", icon="X")
        row.operator("mar.clear_history", icon="TRASH")
        operator = box.operator("wm.url_open", text="Open User Guide", icon="URL")
        operator.url = DOCUMENTATION_URL
