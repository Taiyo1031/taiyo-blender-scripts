import os
import re
import time
import bpy
from .chunked import ChunkedOperator
from .constants import FBX_ARGUMENTS

# Verified by an export/import content check in tools/test_map_roundtrip_tools.py.
USE_TEMP_OVERRIDE = True


def safe_name(name):
    return re.sub(r'[^A-Za-z0-9_-]', '_', name) or '_'


def unique_path(folder, name, reserved, next_suffix=None):
    base = safe_name(name)
    path = os.path.join(folder, base + '.fbx')
    index = (next_suffix or {}).get(base, 2)
    while path in reserved or os.path.exists(path):
        path = os.path.join(folder, f'{base}_{index}.fbx')
        index += 1
    reserved.add(path)
    if next_suffix is not None:
        next_suffix[base] = index
    return path, path != os.path.join(folder, base + ".fbx")


class MRT_OT_ExportFBX(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.export_fbx'
    bl_label = 'Export FBX'

    def work(self, context):
        p = context.scene.mrt_props
        selected = tuple(context.selected_objects)
        meshes = tuple(ob for ob in selected if ob.type == 'MESH')
        if not meshes:
            raise ValueError('No mesh objects selected.')
        if p.fbx_axis_forward.lstrip('-') == p.fbx_axis_up.lstrip('-'):
            raise ValueError('Forward and Up axes must be different.')
        if not p.fbx_out_dir:
            raise ValueError('Output Folder is empty.')
        folder = bpy.path.abspath(p.fbx_out_dir)
        os.makedirs(folder, exist_ok=True)
        active = context.view_layer.objects.active
        args = {arg: getattr(p, key) for key, arg in FBX_ARGUMENTS.items()}
        args.update(object_types={'MESH'}, use_selection=True, add_leaf_bones=False, bake_anim=False, path_mode='AUTO')
        groups = [(ob.name, (ob,)) for ob in meshes] if p.fbx_files == 'PER_OBJECT' else [(p.zone_name, meshes)]
        reserved, jobs = set(), []
        collisions = 0
        next_suffix = {}
        for name, objects in groups:
            path, collision = unique_path(folder, name, reserved, next_suffix)
            collisions += collision
            jobs.append((path, objects))
        if collisions:
            self.report({'WARNING'}, f'{collisions} filenames received a numeric suffix.')
        previous = selected
        started = time.perf_counter()
        exported = 0
        try:
            for path, objects in jobs:
                if USE_TEMP_OVERRIDE:
                    with context.temp_override(selected_objects=list(objects), selected_editable_objects=list(objects), active_object=objects[0], object=objects[0]):
                        result = bpy.ops.export_scene.fbx(filepath=path, **args)
                else:
                    for ob in previous:
                        ob.select_set(False)
                    for ob in objects:
                        ob.select_set(True)
                    context.view_layer.objects.active = objects[0]
                    previous = objects
                    result = bpy.ops.export_scene.fbx(filepath=path, **args)
                if 'FINISHED' not in result:
                    raise RuntimeError(f'FBX export failed: {path}')
                exported += 1
                self.progress('Exported', exported, len(jobs))
                yield
        finally:
            if not USE_TEMP_OVERRIDE:
                for ob in previous:
                    ob.select_set(False)
                for ob in selected:
                    ob.select_set(True)
                context.view_layer.objects.active = active
            p.last_export = f'{exported} files in {time.perf_counter() - started:.3f}s'
        self.result = 'Exported ' + p.last_export
