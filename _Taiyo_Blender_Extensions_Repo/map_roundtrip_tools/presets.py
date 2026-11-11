import json
import math
import os
import tempfile
import bpy
from bpy.props import StringProperty
from .constants import BUILTIN_PRESET, FBX_DEFAULTS

PATH_OVERRIDE = None
_ENUM_ITEMS = []
_ENUM_RETIRED = []
ENUMS = dict(fbx_apply_scalings={'FBX_SCALE_NONE', 'FBX_SCALE_UNITS', 'FBX_SCALE_CUSTOM', 'FBX_SCALE_ALL'},
             fbx_axis_forward={'X', 'Y', 'Z', '-X', '-Y', '-Z'}, fbx_axis_up={'X', 'Y', 'Z', '-X', '-Y', '-Z'},
             fbx_smoothing={'OFF', 'FACE', 'EDGE'}, fbx_vertex_colors={'NONE', 'SRGB', 'LINEAR'})


def path():
    return PATH_OVERRIDE or os.path.join(bpy.utils.user_resource('CONFIG', path='map_roundtrip_tools', create=True), 'presets.json')


def validate(values):
    values = values if isinstance(values, dict) else {}
    result = {}
    for key, default in FBX_DEFAULTS.items():
        value = values.get(key, default)
        if key in ENUMS:
            valid = isinstance(value, str) and value in ENUMS[key]
        elif isinstance(default, bool):
            valid = isinstance(value, bool)
        else:
            valid = type(value) in (int, float) and math.isfinite(value) and value > 0
        result[key] = value if valid else default
    return result


def load():
    try:
        with open(path(), encoding='utf-8') as f:
            raw = json.load(f)
        return {k: validate(v) for k, v in raw.items() if isinstance(k, str) and k != BUILTIN_PRESET} if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def save(values):
    target = path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(target), suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(values, f, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    refresh()


def refresh():
    global _ENUM_ITEMS
    _ENUM_RETIRED.append(_ENUM_ITEMS)
    _ENUM_ITEMS = [(BUILTIN_PRESET, BUILTIN_PRESET, '', 0)] + [(n, n, '', i + 1) for i, n in enumerate(sorted(load()))]


def preset_items(self, context):
    if not _ENUM_ITEMS:
        refresh()
    return _ENUM_ITEMS


def apply_selected(self, context):
    values = FBX_DEFAULTS if self.fbx_preset == BUILTIN_PRESET else load().get(self.fbx_preset, FBX_DEFAULTS)
    for key, value in validate(values).items():
        setattr(self, key, value)


class MRT_OT_SavePreset(bpy.types.Operator):
    bl_description = '現在のAdvanced設定を名前付きで保存します'
    bl_idname = 'mrt.save_preset'
    bl_label = 'Save FBX Preset'
    preset_name: StringProperty(name='Name')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.preset_name.strip()
        if not name or name == BUILTIN_PRESET:
            self.report({'ERROR'}, 'Choose a nonempty user preset name; built-in preset is read-only.')
            return {'CANCELLED'}
        p = context.scene.mrt_props
        values = load()
        values[name] = {k: getattr(p, k) for k in FBX_DEFAULTS}
        try:
            save(values)
            p.fbx_preset = name
        except OSError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class MRT_OT_DeletePreset(bpy.types.Operator):
    bl_description = '選択したユーザープリセットを削除します。組み込み設定は削除できません'
    bl_idname = 'mrt.delete_preset'
    bl_label = 'Delete FBX Preset'

    def execute(self, context):
        p = context.scene.mrt_props
        if p.fbx_preset != BUILTIN_PRESET:
            values = load()
            values.pop(p.fbx_preset, None)
            try:
                save(values)
                p.fbx_preset = BUILTIN_PRESET
            except OSError as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        return {'FINISHED'}
