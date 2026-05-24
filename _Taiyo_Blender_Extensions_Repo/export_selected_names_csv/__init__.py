bl_info = {
    "name": "Export Selected Object Names to CSV",
    "author": "ChatGPT",
    "version": (1, 0, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Selected CSV Export",
    "description": "Export selected object names to CSV file",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/export_selected_names_csv/%E3%82%A4%E3%83%B3%E3%82%B9%E3%82%BF%E3%83%B3%E3%82%B9%E3%83%98%E3%83%AB%E3%83%8F%E3%82%9A%E3%83%BC_%E9%81%B8%E6%8A%9E%E3%82%AA%E3%83%95%E3%82%99%E3%82%B7%E3%82%99%E3%82%A7%E3%82%AF%E3%83%88%E5%90%8DCSV%E6%9B%B8%E3%81%8D%E5%87%BA%E3%81%97_%E5%AE%8C%E5%85%A8%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy
import csv
import os


# =========================
# Operator
# =========================
class OBJECT_OT_export_selected_names_csv(bpy.types.Operator):
    bl_idname = "object.export_selected_names_csv"
    bl_label = "Export Selected to CSV"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.selected_csv_export_props
        filepath = bpy.path.abspath(props.filepath)

        if not context.selected_objects:
            self.report({"WARNING"}, "選択オブジェクトがありません")
            return {"CANCELLED"}

        # 拡張子を必ず .csv にする
        if not filepath.lower().endswith(".csv"):
            filepath += ".csv"

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["name"])
            for obj in context.selected_objects:
                writer.writerow([obj.name])

        self.report({"INFO"}, f"CSV書き出し完了: {filepath}")
        return {"FINISHED"}


# =========================
# Properties
# =========================
class SelectedCSVExportProperties(bpy.types.PropertyGroup):
    filepath: bpy.props.StringProperty(
        name="Save Path",
        description="CSVの保存先",
        subtype="FILE_PATH",
        default="//selected_objects.csv",
    )


# =========================
# Panel (Sidebar)
# =========================
class VIEW3D_PT_selected_csv_export(bpy.types.Panel):
    bl_label = "Selected CSV Export"
    bl_idname = "VIEW3D_PT_selected_csv_export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Selected CSV Export"

    def draw(self, context):
        layout = self.layout
        props = context.scene.selected_csv_export_props

        layout.prop(props, "filepath")
        layout.operator(
            OBJECT_OT_export_selected_names_csv.bl_idname,
            icon="EXPORT"
        )


# =========================
# Register
# =========================
class SELCsv_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    SELCsv_AddonPreferences,
    OBJECT_OT_export_selected_names_csv,
    SelectedCSVExportProperties,
    VIEW3D_PT_selected_csv_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.selected_csv_export_props = bpy.props.PointerProperty(
        type=SelectedCSVExportProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.selected_csv_export_props


if __name__ == "__main__":
    register()
