"""Run from Blender's Text Editor. Creates a deterministic linked-mesh map."""
import random
import time
import bpy

LIB_COUNT = 50
MAP_COUNT = 60000
ZONE_COUNT = 4


def make_scene(lib_count=LIB_COUNT, map_count=MAP_COUNT, zone_count=ZONE_COUNT):
    rng = random.Random(42)
    started = time.perf_counter()
    lib = bpy.data.collections.new('ForExport_Dirty_1')
    mapc = bpy.data.collections.new('Laid_MAP_1')
    meshes = []
    verts = [(-.5,-.5,-.5), (.5,-.5,-.5), (.5,.5,-.5), (-.5,.5,-.5),
             (-.5,-.5,.5), (.5,-.5,.5), (.5,.5,.5), (-.5,.5,.5)]
    faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    for i in range(lib_count):
        mesh = bpy.data.meshes.new(f'Asset_{i:03}')
        mesh.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new(f'Asset_{i:03}', mesh)
        lib.objects.link(ob)
        meshes.append(mesh)
    library_seconds = time.perf_counter() - started
    children = [bpy.data.collections.new(n) for n in ('Rocks', 'Trees', 'Props')]
    objects = []
    t = time.perf_counter()
    for i in range(map_count):
        mesh = meshes[i % len(meshes)]
        ob = bpy.data.objects.new(f'{mesh.name}.{i // lib_count + 1:03d}', mesh)
        ob.location = (rng.uniform(-100,100), rng.uniform(-100,100), rng.uniform(-20,20))
        ob.rotation_euler = (0,0,rng.uniform(-3.14,3.14))
        ob.scale = (rng.uniform(.5,2),) * 3
        children[i % 3].objects.link(ob)
        objects.append(ob)
    for c in children:
        mapc.children.link(c)
    bpy.context.scene.collection.children.link(lib)
    bpy.context.scene.collection.children.link(mapc)
    placement_seconds = time.perf_counter() - t
    for i in range(zone_count):
        e = bpy.data.objects.new('ZONE_' + chr(65+i), None)
        e.empty_display_type = 'CUBE'
        e.empty_display_size = 50
        e.location = ((i % 2)*100-50, (i // 2)*100-50, 0)
        bpy.context.scene.collection.objects.link(e)
    e = bpy.data.objects.new('ZONE_A.001', None)
    e.empty_display_type = 'CUBE'
    e.empty_display_size = 8
    e.location = (80,80,0)
    bpy.context.scene.collection.objects.link(e)
    bpy.context.view_layer.update()
    if hasattr(bpy.context.scene, 'mrt_props'):
        bpy.context.scene.mrt_props.library_coll = lib
        bpy.context.scene.mrt_props.map_coll = mapc
    if hasattr(bpy.context.scene, 'ubt_props'):
        bpy.context.scene.ubt_props.collection = mapc
    print(f'BENCH_SCENE library={library_seconds:.3f}s map={placement_seconds:.3f}s total={time.perf_counter()-started:.3f}s', flush=True)
    return lib, mapc, objects


if __name__ == '__main__':
    make_scene()
