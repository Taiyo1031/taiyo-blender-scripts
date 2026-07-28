bl_info = {
    "name": "Mesh Attribute Batch Remover",
    "author": "Taiyo",
    "version": (1, 0, 0),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar(N) > Attr Remove",
    "description": "Remove one named mesh attribute from many objects",
    "category": "Mesh",
}

import bpy
from bpy.props import EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/mesh_attribute_batch_remover/README.md"
)

SCOPE_ITEMS = (
    (
        "SELECTED",
        "Selected Objects",
        "Remove the attribute from selected mesh objects",
    ),
    (
        "SCENE",
        "All Scene Objects",
        "Remove the attribute from every mesh object in the current scene",
    ),
)


def _target_objects(context, scope):
    candidates = context.scene.objects if scope == "SCENE" else context.selected_objects
    return [
        obj
        for obj in candidates
        if obj is not None and obj.type == "MESH" and obj.data is not None
    ]


def _unique_mesh_entries(objects):
    entries = []
    entries_by_pointer = {}

    for obj in objects:
        mesh = obj.data
        pointer = mesh.as_pointer()
        entry = entries_by_pointer.get(pointer)

        if entry is None:
            entry = {
                "mesh": mesh,
                "target_object_count": 0,
                "outside_object_count": 0,
            }
            entries_by_pointer[pointer] = entry
            entries.append(entry)

        entry["target_object_count"] += 1

    if not entries:
        return entries

    target_object_pointers = {obj.as_pointer() for obj in objects}
    for obj in bpy.data.objects:
        if obj.as_pointer() in target_object_pointers:
            continue
        if obj.type != "MESH" or obj.data is None:
            continue

        entry = entries_by_pointer.get(obj.data.as_pointer())
        if entry is not None:
            entry["outside_object_count"] += 1

    return entries


def _attribute_is_removable(attribute):
    return not (
        getattr(attribute, "is_internal", False)
        or getattr(attribute, "is_required", False)
    )


def _build_preview(context):
    settings = context.scene.mabr_settings
    attribute_name = settings.attribute_name.strip()
    objects = _target_objects(context, settings.scope)
    mesh_entries = _unique_mesh_entries(objects)

    preview = {
        "attribute_name": attribute_name,
        "scope": settings.scope,
        "objects": objects,
        "mesh_entries": mesh_entries,
        "target_object_count": len(objects),
        "unique_mesh_count": len(mesh_entries),
        "attribute_count": 0,
        "protected_attribute_count": 0,
        "non_editable_mesh_count": 0,
        "outside_shared_object_count": 0,
        "shared_mesh_count": 0,
        "error": "",
    }

    if context.mode != "OBJECT":
        preview["error"] = "Object Modeで実行してください。"
        return preview
    if not attribute_name:
        preview["error"] = "削除するAttribute名を入力してください。"
        return preview
    if not objects:
        if settings.scope == "SCENE":
            preview["error"] = "現在のSceneにMeshオブジェクトがありません。"
        else:
            preview["error"] = "選択中のMeshオブジェクトがありません。"
        return preview

    for entry in mesh_entries:
        mesh = entry["mesh"]
        outside_count = entry["outside_object_count"]
        if outside_count:
            preview["outside_shared_object_count"] += outside_count
            preview["shared_mesh_count"] += 1

        if not getattr(mesh, "is_editable", True):
            preview["non_editable_mesh_count"] += 1
            continue

        attribute = mesh.attributes.get(attribute_name)
        if attribute is None:
            continue
        if _attribute_is_removable(attribute):
            preview["attribute_count"] += 1
        else:
            preview["protected_attribute_count"] += 1

    return preview


def _no_removable_attribute_message(preview):
    attribute_name = preview["attribute_name"]
    if preview["protected_attribute_count"]:
        return f"'{attribute_name}' は内部属性または必須属性のため削除できません。"
    if preview["non_editable_mesh_count"]:
        return (
            f"編集可能なMeshに削除可能なAttributeがありません: {attribute_name}"
        )
    return f"削除可能なAttributeが見つかりません: {attribute_name}"


def _remove_named_attribute(context):
    preview = _build_preview(context)

    if preview["error"]:
        raise ValueError(preview["error"])
    if preview["attribute_count"] == 0:
        raise ValueError(_no_removable_attribute_message(preview))

    deleted_attribute_count = 0
    processed_mesh_count = 0
    failed_attribute_count = 0

    for entry in preview["mesh_entries"]:
        mesh = entry["mesh"]
        if not getattr(mesh, "is_editable", True):
            continue

        attribute = mesh.attributes.get(preview["attribute_name"])
        if attribute is None or not _attribute_is_removable(attribute):
            continue

        try:
            mesh.attributes.remove(attribute)
        except RuntimeError:
            failed_attribute_count += 1
            continue

        mesh.update()
        deleted_attribute_count += 1
        processed_mesh_count += 1

    return {
        "deleted_attribute_count": deleted_attribute_count,
        "processed_mesh_count": processed_mesh_count,
        "skipped_mesh_count": preview["unique_mesh_count"] - processed_mesh_count,
        "failed_attribute_count": failed_attribute_count,
    }


class MABR_Settings(PropertyGroup):
    scope: EnumProperty(
        name="Scope",
        description="Mesh Attributeを削除する対象範囲",
        items=SCOPE_ITEMS,
        default="SELECTED",
    )
    attribute_name: StringProperty(
        name="Attribute Name",
        description="大文字小文字を区別して完全一致で削除するMesh Attribute名",
        default="",
    )


class MABR_OT_remove_attribute(Operator):
    bl_idname = "mabr.remove_attribute"
    bl_label = "Remove Attribute"
    bl_description = "指定名のMesh Attributeを対象Objectから一括削除します"
    bl_options = {"REGISTER", "UNDO"}

    preview_target_object_count: IntProperty(options={"HIDDEN"})
    preview_unique_mesh_count: IntProperty(options={"HIDDEN"})
    preview_attribute_count: IntProperty(options={"HIDDEN"})
    preview_protected_attribute_count: IntProperty(options={"HIDDEN"})
    preview_non_editable_mesh_count: IntProperty(options={"HIDDEN"})
    preview_outside_shared_object_count: IntProperty(options={"HIDDEN"})
    preview_shared_mesh_count: IntProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def invoke(self, context, event):
        preview = _build_preview(context)

        if preview["error"]:
            self.report({"ERROR"}, preview["error"])
            return {"CANCELLED"}
        if preview["attribute_count"] == 0:
            self.report({"ERROR"}, _no_removable_attribute_message(preview))
            return {"CANCELLED"}

        self.preview_target_object_count = preview["target_object_count"]
        self.preview_unique_mesh_count = preview["unique_mesh_count"]
        self.preview_attribute_count = preview["attribute_count"]
        self.preview_protected_attribute_count = preview[
            "protected_attribute_count"
        ]
        self.preview_non_editable_mesh_count = preview[
            "non_editable_mesh_count"
        ]
        self.preview_outside_shared_object_count = preview[
            "outside_shared_object_count"
        ]
        self.preview_shared_mesh_count = preview["shared_mesh_count"]
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        layout = self.layout
        attribute_name = context.scene.mabr_settings.attribute_name.strip()

        layout.label(
            text=f"'{attribute_name}' を一括削除します。",
            icon="ERROR",
        )
        layout.label(
            text=(
                f"Target Objects: {self.preview_target_object_count} / "
                f"Unique Meshes: {self.preview_unique_mesh_count}"
            ),
            icon="MESH_DATA",
        )
        layout.label(
            text=f"Attributes to Remove: {self.preview_attribute_count}",
            icon="TRASH",
        )

        if self.preview_non_editable_mesh_count:
            layout.label(
                text=(
                    f"Non-editable Meshes: "
                    f"{self.preview_non_editable_mesh_count}"
                ),
                icon="LOCKED",
            )
        if self.preview_protected_attribute_count:
            layout.label(
                text=(
                    f"Protected Attributes: "
                    f"{self.preview_protected_attribute_count}"
                ),
                icon="LOCKED",
            )
        if self.preview_outside_shared_object_count:
            layout.label(
                text=(
                    f"対象外Object {self.preview_outside_shared_object_count}個も "
                    f"{self.preview_shared_mesh_count}個の共有Mesh経由で影響を受けます。"
                ),
                icon="LINKED",
            )

    def execute(self, context):
        try:
            result = _remove_named_attribute(context)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        report_type = {"WARNING"} if result["failed_attribute_count"] else {"INFO"}
        self.report(
            report_type,
            (
                f"{result['deleted_attribute_count']} Attribute / "
                f"{result['processed_mesh_count']} Meshから削除しました。"
                f" スキップMesh: {result['skipped_mesh_count']} / "
                f"失敗Attribute: {result['failed_attribute_count']}"
            ),
        )
        return {"FINISHED"}


class MABR_PT_main(Panel):
    bl_label = "Mesh Attribute Batch Remover"
    bl_idname = "MABR_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Attr Remove"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mabr_settings

        layout.prop(settings, "scope")

        active_object = context.view_layer.objects.active
        if (
            active_object is not None
            and active_object.type == "MESH"
            and active_object.data is not None
        ):
            layout.prop_search(
                settings,
                "attribute_name",
                active_object.data,
                "attributes",
                text="Attribute Name",
            )
        else:
            layout.prop(settings, "attribute_name", text="Attribute Name")

        if context.mode != "OBJECT":
            layout.label(text="Object Modeで実行してください。", icon="INFO")

        row = layout.row()
        row.enabled = context.mode == "OBJECT"
        row.operator(MABR_OT_remove_attribute.bl_idname, icon="TRASH")


classes = (
    MABR_Settings,
    MABR_OT_remove_attribute,
    MABR_PT_main,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mabr_settings = PointerProperty(type=MABR_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "mabr_settings"):
        del bpy.types.Scene.mabr_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
