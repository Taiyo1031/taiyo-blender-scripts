bl_info = {
    "name": "Replace Selected with Active",
    "author": "Taiyo",
    "version": (2, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Replace",
    "description": "選択オブジェクトをアクティブオブジェクトのコピーにすげ替えます",
    "category": "Object",
}

import bpy


# ─────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────

def get_object_collection(obj, scene):
    """obj が所属する最初のコレクションを返す（なければシーンルート）"""
    if obj is None:
        return scene.collection

    if obj.name in scene.collection.objects:
        return scene.collection

    for col in scene.collection.children_recursive:
        if obj.name in col.objects:
            return col

    return scene.collection


def copy_transform_options(new_obj, target, props):
    """チェックされたトランスフォーム要素だけ target から new_obj へコピー"""
    if props.copy_location:
        new_obj.location = target.location.copy()

    if props.copy_rotation:
        new_obj.rotation_euler = target.rotation_euler.copy()

    if props.copy_scale:
        new_obj.scale = target.scale.copy()


# ─────────────────────────────────────────
#  Properties
# ─────────────────────────────────────────

class REPSEL_Props(bpy.types.PropertyGroup):
    replace_targets: bpy.props.BoolProperty(
        name="ターゲットを削除してすげ替え",
        description="配置先の選択オブジェクトを削除し、アクティブオブジェクトのコピーに置き換えます",
        default=True,
    )

    delete_source: bpy.props.BoolProperty(
        name="すげ替え後に元オブジェクトも削除",
        description="すげ替え処理後、元として使ったアクティブオブジェクトも削除します",
        default=False,
    )

    copy_location: bpy.props.BoolProperty(
        name="位置",
        description="ターゲットの位置をコピーします",
        default=True,
    )

    copy_rotation: bpy.props.BoolProperty(
        name="回転",
        description="ターゲットの回転をコピーします",
        default=True,
    )

    copy_scale: bpy.props.BoolProperty(
        name="スケール",
        description="ターゲットのスケールをコピーします",
        default=False,
    )


# ─────────────────────────────────────────
#  Operator
# ─────────────────────────────────────────

class REPSEL_OT_execute(bpy.types.Operator):
    """選択オブジェクトをアクティブオブジェクトのコピーにすげ替え"""
    bl_idname = "object.repsel_execute"
    bl_label = "すげ替え実行"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        active = context.active_object
        targets = [o for o in context.selected_objects if o != active]
        return active is not None and len(targets) >= 1

    def execute(self, context):
        props = context.scene.repsel_props
        active = context.active_object
        targets = [o for o in context.selected_objects if o != active]

        if active is None:
            self.report({'WARNING'}, "すげ替え元が選択されていません")
            return {'CANCELLED'}

        if not targets:
            self.report({'WARNING'}, "すげ替え対象が選択されていません")
            return {'CANCELLED'}

        # すげ替え元が所属するコレクションを取得
        active_collection = get_object_collection(active, context.scene)
        active_collection_name = active_collection.name

        created = []

        for target in targets:
            # アクティブオブジェクトを内部的にコピー
            new_obj = active.copy()

            # メッシュなどのデータも独立コピー
            if active.data:
                new_obj.data = active.data.copy()

            # すげ替え元と同じコレクションに追加
            active_collection.objects.link(new_obj)

            # ターゲットのトランスフォームをコピー
            copy_transform_options(new_obj, target, props)

            # 名前を少し分かりやすくする
            new_obj.name = f"{active.name}_replace"

            created.append(new_obj)

            # ここが「すげ替え」体感の本体
            # 元からそこにあったターゲットオブジェクトを削除
            if props.replace_targets:
                bpy.data.objects.remove(target, do_unlink=True)

        # すげ替え元も削除する場合
        if props.delete_source:
            bpy.data.objects.remove(active, do_unlink=True)

        # 選択をすげ替え後のオブジェクトに切り替え
        bpy.ops.object.select_all(action='DESELECT')

        for obj in created:
            obj.select_set(True)

        if created:
            context.view_layer.objects.active = created[-1]

        replace_text = " / ターゲット削除" if props.replace_targets else " / ターゲット保持"
        source_text = " / 元オブジェクト削除" if props.delete_source else ""

        self.report(
            {'INFO'},
            f"{len(created)} 個すげ替え → {active_collection_name}{replace_text}{source_text}"
        )

        return {'FINISHED'}


# ─────────────────────────────────────────
#  Panel
# ─────────────────────────────────────────

class REPSEL_PT_panel(bpy.types.Panel):
    bl_label = "選択をすげ替え"
    bl_idname = "REPSEL_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Replace"

    def draw(self, context):
        layout = self.layout
        props = context.scene.repsel_props
        active = context.active_object
        targets = [o for o in context.selected_objects if o is not None and o != active]
        active_col = get_object_collection(active, context.scene) if active else None

        # ── ステータス ──────────────────────
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.85

        if active:
            col.label(text=f"すげ替え元:  {active.name}", icon='OBJECT_DATA')
        else:
            col.label(text="すげ替え元:  未選択", icon='ERROR')

        col.label(
            text=f"すげ替え対象: {len(targets)} 個",
            icon='CHECKMARK' if targets else 'ERROR',
        )

        col.label(
            text=f"追加先:  {active_col.name}" if active_col else "追加先:  －",
            icon='OUTLINER_COLLECTION',
        )

        layout.separator(factor=0.5)

        # ── すげ替え設定 ─────────────────────
        box = layout.box()
        box.label(text="すげ替え設定", icon='MODIFIER')

        box.prop(props, "replace_targets")
        box.prop(props, "delete_source")

        layout.separator(factor=0.5)

        # ── コピーする要素 ─────────────────────
        box = layout.box()
        box.label(text="引き継ぐトランスフォーム", icon='PROPERTIES')

        row = box.row(align=True)
        row.scale_y = 1.3
        row.prop(props, "copy_location", toggle=True)
        row.prop(props, "copy_rotation", toggle=True)
        row.prop(props, "copy_scale", toggle=True)

        layout.separator(factor=0.5)

        # ── 実行ボタン ─────────────────────
        col = layout.column()
        col.scale_y = 1.8
        col.enabled = active is not None and len(targets) >= 1

        col.operator(
            "object.repsel_execute",
            text="選択オブジェクトをすげ替え",
            icon='FILE_REFRESH',
        )

        # ── ヒント ─────────────────────────
        layout.separator(factor=0.5)

        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.75

        col.label(text="① すげ替えたい対象を複数選択", icon='BLANK1')
        col.label(text="② 置き換え元を最後に選択", icon='BLANK1')
        col.label(text="③ 選択オブジェクトをすげ替え を押す", icon='BLANK1')

        layout.separator(factor=0.5)

        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.75
        col.label(text="内部的にはコピーを作成しますが、", icon='INFO')
        col.label(text="体感としては対象を置き換える動作です。", icon='BLANK1')


# ─────────────────────────────────────────
#  Register
# ─────────────────────────────────────────

classes = (
    REPSEL_Props,
    REPSEL_OT_execute,
    REPSEL_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.repsel_props = bpy.props.PointerProperty(type=REPSEL_Props)


def unregister():
    del bpy.types.Scene.repsel_props

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()