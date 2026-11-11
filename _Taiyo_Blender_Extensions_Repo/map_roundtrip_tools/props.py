import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from .constants import BUILTIN_PRESET
from .presets import preset_items, apply_selected


def enum(items):
    return [(s, s.replace('_', ' ').title(), '') for s in items]


class MRT_Props(bpy.types.PropertyGroup):
    exchange_dir: StringProperty(name='Exchange Folder', subtype='DIR_PATH', default='//houdini_io')
    zone_name: StringProperty(name='Zone Name', default='ZONE_A')
    fbx_preset: EnumProperty(name='Preset', items=preset_items, update=apply_selected)
    fbx_files: EnumProperty(name='Files', items=[('PER_OBJECT', 'Per Object', ''), ('COMBINED', 'Combined', '')], default='PER_OBJECT')
    fbx_out_dir: StringProperty(name='Output Folder', subtype='DIR_PATH', default='//houdini_io/out/fbx')
    fbx_scale: FloatProperty(name='Scale', default=1, min=.000001)
    fbx_apply_scalings: EnumProperty(name='Apply Scalings', items=[('FBX_SCALE_NONE', 'All Local', ''), ('FBX_SCALE_UNITS', 'FBX Units Scale', ''), ('FBX_SCALE_CUSTOM', 'FBX Custom Scale', ''), ('FBX_SCALE_ALL', 'FBX All', '')], default='FBX_SCALE_UNITS')
    fbx_axis_forward: EnumProperty(name='Forward', items=enum(['X', 'Y', 'Z', '-X', '-Y', '-Z']), default='-Z')
    fbx_axis_up: EnumProperty(name='Up', items=enum(['X', 'Y', 'Z', '-X', '-Y', '-Z']), default='Y')
    fbx_apply_modifiers: BoolProperty(name='Apply Modifiers', default=True)
    fbx_smoothing: EnumProperty(name='Smoothing', items=enum(['OFF', 'FACE', 'EDGE']), default='FACE')
    fbx_vertex_colors: EnumProperty(name='Vertex Colors', items=enum(['NONE', 'SRGB', 'LINEAR']), default='LINEAR')
    fbx_triangulate: BoolProperty(name='Triangulate', default=False)
    fbx_tangent: BoolProperty(name='Tangent Space', default=False)
    fbx_apply_transform: BoolProperty(name='Apply Transform', default=False)
    library_coll: PointerProperty(name='Library', type=bpy.types.Collection)
    map_coll: PointerProperty(name='Map', type=bpy.types.Collection)
    new_mesh_coll_name: StringProperty(name='New Meshes To', default='FromHoudini')
    return_dir: StringProperty(name='Return Folder', subtype='DIR_PATH', default='//houdini_io/in')
    placement_csv: StringProperty(name='Placement CSV', subtype='FILE_PATH')
    mesh_fbx: StringProperty(name='Mesh FBX', subtype='FILE_PATH')
    name_mode: EnumProperty(name='Name Normalize', items=[('keep_raw', 'Keep Raw', ''), ('numeric_suffix', 'Remove Numeric Suffix (.001+)', ''), ('trim_after_dot', 'Trim After Dot', '')], default='numeric_suffix')
    if_exists: EnumProperty(name='If Exists', items=enum(['SKIP', 'UPDATE']), default='SKIP')
    zone_override: StringProperty(name='Zone')
    old_mode: EnumProperty(name='Old Objects', items=enum(['ARCHIVE', 'DELETE']), default='ARCHIVE')
    dry_run: BoolProperty(name='Dry Run', default=True)
    plan_ready: BoolProperty(default=False, options={'SKIP_SAVE'})
    plan_archive: IntProperty(default=0, options={'SKIP_SAVE'})
    plan_create: IntProperty(default=0, options={'SKIP_SAVE'})
    plan_invalid: IntProperty(default=0, options={'SKIP_SAVE'})
    plan_missing: IntProperty(default=0, options={'SKIP_SAVE'})
    plan_missing_rows: IntProperty(default=0, options={'SKIP_SAVE'})
    plan_collections: IntProperty(default=0, options={'SKIP_SAVE'})
    plan_zone: StringProperty(options={'SKIP_SAVE'})
    plan_names: StringProperty(options={'SKIP_SAVE'})
    plan_new_meshes_imported: IntProperty(default=0, options={'SKIP_SAVE'})
    last_export: StringProperty(default='none', options={'SKIP_SAVE'})
    running: BoolProperty(default=False, options={'SKIP_SAVE'})
    cancel_requested: BoolProperty(default=False, options={'SKIP_SAVE'})
    progress: FloatProperty(default=0, options={'SKIP_SAVE'})
    status: StringProperty(options={'SKIP_SAVE'})
    max_tick: FloatProperty(default=0, options={'SKIP_SAVE'})
