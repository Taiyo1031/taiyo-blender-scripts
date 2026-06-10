from bpy.types import Panel, UIList

from . import naming


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


def _draw_choice_current(layout, module):
    try:
        layout.prop(module, "choice_current", text="")
        return True
    except Exception:
        layout.label(text="Choice data needs repair.", icon="ERROR")
        operator = layout.operator("mar.repair_choice_modules", text="Repair")
        operator.module_id = module.module_id
        return False


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


class MAR_UL_dimension_parts(UIList):
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
        row.prop(item, "axis", text="")
        row.prop(item, "separator_after", text="After")


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
                row = box.row(align=True)
                row.label(text=module.choice_label or "Choice")
                if module.choice_options:
                    _draw_choice_current(row, module)
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
                if module.choice_options:
                    _draw_choice_current(box, module)
            elif module.module_type == "DIMENSIONS":
                if not module.dimension_parts:
                    box.label(text="Dimensions has no parts.", icon="ERROR")
                box.template_list(
                    "MAR_UL_dimension_parts",
                    "",
                    module,
                    "dimension_parts",
                    module,
                    "dimension_part_index",
                    rows=4,
                )
                row = box.row(align=True)
                row.operator_menu_enum(
                    "mar.add_dimension_part",
                    "axis",
                    text="Add Part",
                    icon="ADD",
                )
                row.operator(
                    "mar.remove_dimension_part",
                    text="Remove",
                    icon="REMOVE",
                )
                up = row.operator(
                    "mar.move_dimension_part",
                    text="",
                    icon="TRIA_UP",
                )
                up.direction = "UP"
                down = row.operator(
                    "mar.move_dimension_part",
                    text="",
                    icon="TRIA_DOWN",
                )
                down.direction = "DOWN"
                box.prop(module, "dimension_unit")
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
            box.label(text=f"New Name: {item.new_name or '(empty)'}")
            row = box.row(align=True)
            row.operator("mar.copy_preview_name", text="Copy Name", icon="COPYDOWN")
            row.operator(
                "mar.copy_all_preview_names",
                text="Copy All",
                icon="COPYDOWN",
            )
            box.operator(
                "mar.select_preview_name_matches",
                text="Select Same Name",
                icon="RESTRICT_SELECT_OFF",
            )
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
