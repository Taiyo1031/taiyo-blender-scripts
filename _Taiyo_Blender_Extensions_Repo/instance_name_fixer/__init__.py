"""
Instance Name Fixer v0 (確認用)
Blender 4.5.9 LTS 対応

コレクションインスタンスの名前を、インスタンス元のコレクション名に揃えるツール。
.001 などの数字サフィックスはそのまま保持。
"""

import bpy
import re

bl_info = {
    "name": "Instance Name Fixer",
    "author": "Taiyo",
    "version": (0, 1, 1),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar > Name Fixer",
    "description": "コレクションインスタンスの名前をインスタンス元に揃える",
    "category": "Object",
}

# ── ユーティリティ ─────────────────────────────────────────────

def get_base_name(name: str) -> str:
    """
    Blender の重複サフィックス (.001, .002 …) を除いたベース名を返す。
    例: "SM_StPr_Gasyou_A.001" → "SM_StPr_Gasyou_A"
    """
    return re.sub(r'\.\d{3,}$', '', name)


def get_numeric_suffix(name: str) -> str:
    """
    .001 などのサフィックス部分だけ返す。なければ空文字。
    """
    m = re.search(r'(\.\d{3,})$', name)
    return m.group(1) if m else ''


def collect_rename_targets(context) -> list[dict]:
    """
    シーン内のコレクションインスタンスを走査し、
    名前がインスタンス元コレクションと一致しないものをリストアップ。
    戻り値: [{"obj": obj, "current": str, "proposed": str}, ...]
    """
    targets = []
    for obj in context.scene.objects:
        if obj.instance_type != 'COLLECTION' or obj.instance_collection is None:
            continue

        src_name = obj.instance_collection.name   # インスタンス元のコレクション名
        cur_name = obj.name                        # 現在のオブジェクト名

        cur_base   = get_base_name(cur_name)
        cur_suffix = get_numeric_suffix(cur_name)

        # ベース名が一致していれば問題なし（サフィックスのみの差は許容）
        if cur_base == src_name:
            continue

        # 提案名: インスタンス元名 + 既存サフィックス（あれば）
        proposed = src_name + cur_suffix

        targets.append({
            "obj":      obj,
            "current":  cur_name,
            "proposed": proposed,
        })

    return targets


# ── オペレーター ──────────────────────────────────────────────

class INF_OT_Scan(bpy.types.Operator):
    """シーンを走査して修正が必要なインスタンスをリストアップ"""
    bl_idname = "inf.scan"
    bl_label  = "スキャン"

    def execute(self, context):
        props = context.scene.inf_props

        # 既存リストをクリア
        props.rename_items.clear()

        targets = collect_rename_targets(context)
        for t in targets:
            item = props.rename_items.add()
            item.obj_name      = t["obj"].name
            item.proposed_name = t["proposed"]

        self.report({'INFO'}, f"{len(targets)} 件の修正候補を検出しました")
        return {'FINISHED'}


class INF_OT_Execute(bpy.types.Operator):
    """プレビューに表示された名前変更を実行"""
    bl_idname  = "inf.execute"
    bl_label   = "名前変更を実行"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.inf_props
        renamed = 0

        for item in props.rename_items:
            obj = bpy.data.objects.get(item.obj_name)
            if obj is None:
                continue
            obj.name = item.proposed_name
            renamed += 1

        # 実行後にリストをリフレッシュ
        props.rename_items.clear()

        self.report({'INFO'}, f"{renamed} 件の名前を変更しました")
        return {'FINISHED'}


# ── プロパティ ────────────────────────────────────────────────

class INF_RenameItem(bpy.types.PropertyGroup):
    obj_name:      bpy.props.StringProperty(name="現在の名前")
    proposed_name: bpy.props.StringProperty(name="変更後の名前")


class INF_Props(bpy.types.PropertyGroup):
    rename_items: bpy.props.CollectionProperty(type=INF_RenameItem)
    show_scan_section: bpy.props.BoolProperty(
        name="STEP 1 ─ スキャン",
        default=True,
    )
    show_preview_section: bpy.props.BoolProperty(
        name="STEP 2 ─ 修正候補プレビュー",
        default=True,
    )
    show_execute_section: bpy.props.BoolProperty(
        name="STEP 3 ─ 実行",
        default=True,
    )


# ── UI パネル ────────────────────────────────────────────────

def draw_foldout_box(layout, props, prop_name: str, title: str, icon: str):
    is_open = getattr(props, prop_name)
    box = layout.box()
    header = box.row(align=True)
    header.prop(
        props,
        prop_name,
        text="",
        icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT',
        emboss=False,
    )
    header.label(text=title, icon=icon)
    return box if is_open else None


class INF_PT_Panel(bpy.types.Panel):
    bl_label       = "Instance Name Fixer"
    bl_idname      = "INF_PT_Panel"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "Name Fixer"

    def draw(self, context):
        layout = self.layout
        props  = context.scene.inf_props

        # ── STEP 1: スキャン
        box = draw_foldout_box(
            layout,
            props,
            "show_scan_section",
            "STEP 1 ─ スキャン",
            'VIEWZOOM',
        )
        if box:
            box.operator("inf.scan", icon='FILE_REFRESH')

        # ── STEP 2: プレビュー
        box2 = draw_foldout_box(
            layout,
            props,
            "show_preview_section",
            "STEP 2 ─ 修正候補プレビュー",
            'PREVIEW_RANGE',
        )

        if box2:
            if len(props.rename_items) == 0:
                box2.label(text="（候補なし）", icon='INFO')
            else:
                col = box2.column(align=True)
                for item in props.rename_items:
                    row = col.row(align=True)
                    row.label(text=item.obj_name,      icon='OBJECT_DATA')
                    row.label(text="→")
                    row.label(text=item.proposed_name, icon='CHECKMARK')

        # ── STEP 3: 実行
        box3 = draw_foldout_box(
            layout,
            props,
            "show_execute_section",
            "STEP 3 ─ 実行",
            'PLAY',
        )
        if box3:
            row = box3.row()
            row.enabled = len(props.rename_items) > 0
            row.operator("inf.execute", icon='CHECKMARK')


# ── 登録 ─────────────────────────────────────────────────────

classes = [
    INF_RenameItem,
    INF_Props,
    INF_OT_Scan,
    INF_OT_Execute,
    INF_PT_Panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.inf_props = bpy.props.PointerProperty(type=INF_Props)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.inf_props


if __name__ == "__main__":
    register()
