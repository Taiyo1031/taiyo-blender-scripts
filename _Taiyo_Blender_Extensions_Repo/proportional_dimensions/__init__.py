bl_info = {
    "name": "Proportional Dimensions N-Panel",
    "author": "ChatGPT",
    "version": (1, 0, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar(N) > 比率寸法",
    "description": "指定したX/Y/Z寸法を基準に、選択オブジェクトを縦横比を保ったまま均等スケールします。",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/proportional_dimensions/README.md"

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Operator, Panel, PropertyGroup


EPSILON = 1e-8


def _get_target_dimension(props, axis_index: int) -> float:
    if axis_index == 0:
        return props.target_x
    if axis_index == 1:
        return props.target_y
    return props.target_z


def _set_target_dimensions_from_object(props, obj):
    dims = obj.dimensions
    props.target_x = dims.x
    props.target_y = dims.y
    props.target_z = dims.z


class PDIM_Properties(PropertyGroup):
    target_x: FloatProperty(
        name="X",
        description="このX寸法になるように、XYZ比率を保って均等スケールします",
        default=1.0,
        min=0.0,
        precision=4,
        step=1,
        subtype="DISTANCE",
        unit="LENGTH",
    )
    target_y: FloatProperty(
        name="Y",
        description="このY寸法になるように、XYZ比率を保って均等スケールします",
        default=1.0,
        min=0.0,
        precision=4,
        step=1,
        subtype="DISTANCE",
        unit="LENGTH",
    )
    target_z: FloatProperty(
        name="Z",
        description="このZ寸法になるように、XYZ比率を保って均等スケールします",
        default=1.0,
        min=0.0,
        precision=4,
        step=1,
        subtype="DISTANCE",
        unit="LENGTH",
    )
    apply_to_selected: BoolProperty(
        name="選択中すべてに適用",
        description="OFFならアクティブオブジェクトのみ。ONなら選択中の編集可能な全オブジェクトに適用します",
        default=False,
    )


class PDIM_OT_LoadCurrentDimensions(Operator):
    bl_idname = "pdim.load_current_dimensions"
    bl_label = "現在寸法を読み込み"
    bl_description = "アクティブオブジェクトの現在のDimensionsを入力欄に読み込みます"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        props = context.scene.pdim_props
        obj = context.object
        _set_target_dimensions_from_object(props, obj)
        self.report({"INFO"}, f"現在寸法を読み込みました: {obj.name}")
        return {"FINISHED"}


class PDIM_OT_UniformScaleToDimension(Operator):
    bl_idname = "pdim.uniform_scale_to_dimension"
    bl_label = "比率維持で寸法変更"
    bl_description = "指定軸の寸法を基準に、XYZ比率を保ったまま均等スケールします"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(
        name="基準軸",
        items=[
            ("X", "X", "X寸法を基準にします"),
            ("Y", "Y", "Y寸法を基準にします"),
            ("Z", "Z", "Z寸法を基準にします"),
        ],
        default="X",
    )

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        props = context.scene.pdim_props
        axis_index = {"X": 0, "Y": 1, "Z": 2}[self.axis]
        target_dim = _get_target_dimension(props, axis_index)

        if target_dim <= EPSILON:
            self.report({"ERROR"}, "目標寸法は0より大きい値にしてください。")
            return {"CANCELLED"}

        if props.apply_to_selected:
            objects = [obj for obj in context.selected_editable_objects if obj is not None]
        else:
            objects = [context.object]

        if not objects:
            self.report({"ERROR"}, "対象オブジェクトがありません。")
            return {"CANCELLED"}

        scaled_count = 0
        skipped = []

        for obj in objects:
            current_dim = obj.dimensions[axis_index]
            if abs(current_dim) <= EPSILON:
                skipped.append(obj.name)
                continue

            factor = target_dim / current_dim

            # ScaleをXYZ同じ倍率で掛けることで、Dimensionsの比率を維持する。
            obj.scale.x *= factor
            obj.scale.y *= factor
            obj.scale.z *= factor
            scaled_count += 1

        context.view_layer.update()

        # アクティブオブジェクトの変更後寸法を入力欄に再読み込みして、UI表示を同期する。
        if context.object is not None:
            _set_target_dimensions_from_object(props, context.object)

        if skipped:
            self.report(
                {"WARNING"},
                f"{scaled_count}個を変更。{len(skipped)}個は{self.axis}寸法が0のためスキップ: {', '.join(skipped[:5])}",
            )
        else:
            self.report({"INFO"}, f"{scaled_count}個のオブジェクトを{self.axis}基準で均等スケールしました。")

        return {"FINISHED"}


class PDIM_PT_ProportionalDimensionsPanel(Panel):
    bl_label = "比率維持 Dimensions"
    bl_idname = "PDIM_PT_proportional_dimensions_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "比率寸法"

    def draw(self, context):
        layout = self.layout
        props = context.scene.pdim_props
        obj = context.object

        if obj is None:
            layout.label(text="オブジェクトを選択してください。", icon="INFO")
            return

        layout.label(text=f"Active: {obj.name}", icon="OBJECT_DATA")

        box = layout.box()
        box.label(text="現在のDimensions", icon="DRIVER_DISTANCE")
        col = box.column(align=True)
        col.label(text=f"X: {obj.dimensions.x:.6g}")
        col.label(text=f"Y: {obj.dimensions.y:.6g}")
        col.label(text=f"Z: {obj.dimensions.z:.6g}")

        layout.operator("pdim.load_current_dimensions", icon="IMPORT")

        box = layout.box()
        box.label(text="目標寸法を入力して基準軸を押す", icon="FULLSCREEN_ENTER")

        row = box.row(align=True)
        row.prop(props, "target_x")
        op = row.operator("pdim.uniform_scale_to_dimension", text="X基準")
        op.axis = "X"

        row = box.row(align=True)
        row.prop(props, "target_y")
        op = row.operator("pdim.uniform_scale_to_dimension", text="Y基準")
        op.axis = "Y"

        row = box.row(align=True)
        row.prop(props, "target_z")
        op = row.operator("pdim.uniform_scale_to_dimension", text="Z基準")
        op.axis = "Z"

        layout.prop(props, "apply_to_selected")

        if props.apply_to_selected:
            layout.label(text=f"対象: 選択中 {len(context.selected_editable_objects)} 個", icon="RESTRICT_SELECT_OFF")
        else:
            layout.label(text="対象: アクティブのみ", icon="OBJECT_DATA")

        layout.separator()
        layout.label(text="例: Xを500mmにしたい場合")
        layout.label(text="X欄に500mm → X基準")


class PDIM_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    PDIM_AddonPreferences,
    PDIM_Properties,
    PDIM_OT_LoadCurrentDimensions,
    PDIM_OT_UniformScaleToDimension,
    PDIM_PT_ProportionalDimensionsPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pdim_props = bpy.props.PointerProperty(type=PDIM_Properties)


def unregister():
    if hasattr(bpy.types.Scene, "pdim_props"):
        del bpy.types.Scene.pdim_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
