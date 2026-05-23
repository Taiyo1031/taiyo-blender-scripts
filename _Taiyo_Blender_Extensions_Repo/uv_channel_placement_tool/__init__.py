# UV Channel Placement Tool - v2.6（プリセット循環ボタン + インデックス表示）

bl_info = {
    "name": "UV Channel Placement Tool",
    "author": "ChatGPT",
    "version": (2, 6, 1),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > UV Tools",
    "description": "Place selected UVs or mesh islands to predefined grid slots with presets",
    "category": "UV"
}

import bpy
import bmesh
import random
from mathutils import Vector


def ensure_edit_mesh_context(operator, context):
    obj = context.object
    if obj is None or obj.type != 'MESH':
        operator.report({'ERROR'}, "No mesh object selected")
        return None
    if obj.mode != 'EDIT':
        operator.report({'WARNING'}, "Edit Modeで実行してください")
        return None
    return obj


# ─────────────────────────────────────────────
# プリセット構造
class UVSlotPreset(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Preset Name")
    label_0: bpy.props.StringProperty(default="Slot 0")
    label_1: bpy.props.StringProperty(default="Slot 1")
    label_2: bpy.props.StringProperty(default="Slot 2")
    label_3: bpy.props.StringProperty(default="Slot 3")
    label_4: bpy.props.StringProperty(default="Slot 4")
    label_5: bpy.props.StringProperty(default="Slot 5")
    label_6: bpy.props.StringProperty(default="Slot 6")
    label_7: bpy.props.StringProperty(default="Slot 7")

class UVManualProperties(bpy.types.PropertyGroup):
    uv_map_index: bpy.props.IntProperty(name="UV Map Index", default=2, min=0)
    uv_map_name: bpy.props.StringProperty(name="UV Map Name", default="ID")
    label_0: bpy.props.StringProperty(default="Slot 0")
    label_1: bpy.props.StringProperty(default="Slot 1")
    label_2: bpy.props.StringProperty(default="Slot 2")
    label_3: bpy.props.StringProperty(default="Slot 3")
    label_4: bpy.props.StringProperty(default="Slot 4")
    label_5: bpy.props.StringProperty(default="Slot 5")
    label_6: bpy.props.StringProperty(default="Slot 6")
    label_7: bpy.props.StringProperty(default="Slot 7")

class UVRandomProperties(bpy.types.PropertyGroup):
    uv_map_index: bpy.props.IntProperty(name="UV Map Index", default=3, min=0)
    uv_map_name: bpy.props.StringProperty(name="UV Map Name", default="ID")

# ─────────────────────────────────────────────
# プリセット登録・削除・反映・循環
class UV_OT_AddSlotPreset(bpy.types.Operator):
    bl_idname = "uv.add_slot_preset"
    bl_label = "Add Current Labels as Preset"
    def execute(self, context):
        name = context.scene.uv_preset_input_name.strip()
        if not name:
            self.report({'WARNING'}, "Preset name is empty")
            return {'CANCELLED'}
        props = context.scene.uv_manual_props
        new = context.scene.uv_slot_presets.add()
        new.name = name
        for i in range(8):
            setattr(new, f"label_{i}", getattr(props, f"label_{i}"))
        context.scene.uv_slot_preset_enum = str(len(context.scene.uv_slot_presets) - 1)
        return {'FINISHED'}

class UV_OT_RemoveSlotPreset(bpy.types.Operator):
    bl_idname = "uv.remove_slot_preset"
    bl_label = "Remove Selected Preset"
    def execute(self, context):
        idx = int(context.scene.uv_slot_preset_enum)
        presets = context.scene.uv_slot_presets
        if 0 <= idx < len(presets):
            presets.remove(idx)
            context.scene.uv_slot_preset_enum = "0"
        return {'FINISHED'}

class UV_OT_NextPreset(bpy.types.Operator):
    bl_idname = "uv.next_slot_preset"
    bl_label = "Next Preset"
    def execute(self, context):
        total = len(context.scene.uv_slot_presets)
        if total == 0:
            return {'CANCELLED'}
        current = int(context.scene.uv_slot_preset_enum)
        context.scene.uv_slot_preset_enum = str((current + 1) % total)
        return {'FINISHED'}

def get_preset_enum(self, context):
    return [(str(i), f"{i+1} {p.name}", "") for i, p in enumerate(context.scene.uv_slot_presets)]

def update_preset_labels_enum(self, context):
    idx = int(context.scene.uv_slot_preset_enum)
    if 0 <= idx < len(context.scene.uv_slot_presets):
        preset = context.scene.uv_slot_presets[idx]
        props = context.scene.uv_manual_props
        for i in range(8):
            setattr(props, f"label_{i}", getattr(preset, f"label_{i}"))

# ─────────────────────────────────────────────
# UV配置クラス（省略せず維持）
class UV_OT_MoveToSlot(bpy.types.Operator):
    bl_idname = "uv.move_to_slot"
    bl_label = "Move UVs to Slot"
    bl_options = {'REGISTER', 'UNDO'}
    slot_index: bpy.props.IntProperty()
    def execute(self, context):
        obj = ensure_edit_mesh_context(self, context)
        if obj is None:
            return {'CANCELLED'}
        props = context.scene.uv_manual_props
        uv_index = props.uv_map_index
        uv_name = props.uv_map_name
        mesh = obj.data
        if uv_index >= len(mesh.uv_layers):
            self.report({'ERROR'}, f"UV index {uv_index} not found")
            return {'CANCELLED'}
        mesh.uv_layers[uv_index].name = uv_name
        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv[uv_index]
        target_size = 0.005
        target_x = self.slot_index / 8.0 + 1.0 / 16.0
        target_y = 1.0 - 1.0 / 16.0
        for face in bm.faces:
            if face.select:
                for loop in face.loops:
                    luv = loop[uv_layer]
                    luv.uv = Vector((target_x, target_y)) + (luv.uv - Vector((0.5, 0.5))) * target_size
        bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}

class UV_OT_RandomIslandPlacement(bpy.types.Operator):
    bl_idname = "uv.random_island_placement"
    bl_label = "Place All Islands Randomly"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        obj = ensure_edit_mesh_context(self, context)
        if obj is None:
            return {'CANCELLED'}
        props = context.scene.uv_random_props
        uv_index = props.uv_map_index
        uv_name = props.uv_map_name
        mesh = obj.data
        if uv_index >= len(mesh.uv_layers):
            self.report({'ERROR'}, f"UV index {uv_index} not found")
            return {'CANCELLED'}
        mesh.uv_layers[uv_index].name = uv_name
        bm = bmesh.from_edit_mesh(mesh)
        uv_layer = bm.loops.layers.uv[uv_index]
        visited = set()
        islands = []
        for face in bm.faces:
            if face in visited:
                continue
            stack = [face]
            island = []
            while stack:
                f = stack.pop()
                if f in visited:
                    continue
                visited.add(f)
                island.append(f)
                for edge in f.edges:
                    for linked_face in edge.link_faces:
                        if linked_face not in visited:
                            stack.append(linked_face)
            islands.append(island)
        target_size = 0.005
        for island in islands:
            slot_index = random.randint(0, 7)
            target_x = slot_index / 8.0 + 1.0 / 16.0
            target_y = 1.0 - 1.0 / 16.0
            for face in island:
                for loop in face.loops:
                    luv = loop[uv_layer]
                    luv.uv = Vector((target_x, target_y)) + (luv.uv - Vector((0.5, 0.5))) * target_size
        bmesh.update_edit_mesh(mesh)
        return {'FINISHED'}

# ─────────────────────────────────────────────
# UI パネル
class UV_PT_PlacementPanel(bpy.types.Panel):
    bl_label = "UV Channel Placement Tool"
    bl_idname = "UV_PT_PlacementPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'UV Tools'
    def draw(self, context):
        layout = self.layout
        props = context.scene.uv_manual_props

        row = layout.row(align=True)
        row.prop(context.scene, "uv_slot_preset_enum", text="Preset")
        row.operator("uv.next_slot_preset", text="▶")

        layout.prop(context.scene, "uv_preset_input_name", text="Name")
        row = layout.row(align=True)
        row.operator("uv.add_slot_preset", text="Add Current")
        row.operator("uv.remove_slot_preset", text="Remove")

        box = layout.box()
        box.label(text="Manual Slot Placement", icon='GRID')
        box.prop(props, "uv_map_index")
        box.prop(props, "uv_map_name")
        for i in range(8):
            row = box.row()
            row.operator("uv.move_to_slot", text=f"Slot {i}").slot_index = i
            row.prop(props, f"label_{i}", text="")

        box2 = layout.box()
        box2.label(text="Random Placement", icon='RNDCURVE')
        box2.prop(context.scene.uv_random_props, "uv_map_index")
        box2.prop(context.scene.uv_random_props, "uv_map_name")
        box2.operator("uv.random_island_placement", text="Place All Islands Randomly")

# ─────────────────────────────────────────────
# 登録・解除
classes = [
    UVSlotPreset,
    UVManualProperties,
    UVRandomProperties,
    UV_OT_AddSlotPreset,
    UV_OT_RemoveSlotPreset,
    UV_OT_NextPreset,
    UV_OT_MoveToSlot,
    UV_OT_RandomIslandPlacement,
    UV_PT_PlacementPanel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.uv_manual_props = bpy.props.PointerProperty(type=UVManualProperties)
    bpy.types.Scene.uv_random_props = bpy.props.PointerProperty(type=UVRandomProperties)
    bpy.types.Scene.uv_slot_presets = bpy.props.CollectionProperty(type=UVSlotPreset)
    bpy.types.Scene.uv_slot_preset_enum = bpy.props.EnumProperty(items=get_preset_enum, update=update_preset_labels_enum)
    bpy.types.Scene.uv_preset_input_name = bpy.props.StringProperty(name="Preset Name", default="MyPreset")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.uv_manual_props
    del bpy.types.Scene.uv_random_props
    del bpy.types.Scene.uv_slot_presets
    del bpy.types.Scene.uv_slot_preset_enum
    del bpy.types.Scene.uv_preset_input_name

if __name__ == "__main__":
    register()
    
