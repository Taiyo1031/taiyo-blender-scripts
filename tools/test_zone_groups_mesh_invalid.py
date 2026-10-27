import bpy,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
from zone_groups import mesh_volume as M

def check(mesh,label):
    try:
        for _ in M.build(mesh,{}):pass
    except M.MeshError as e:print('PASS',label,str(e));return
    raise AssertionError('Invalid mesh accepted: '+label)

bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=12,major_radius=.57,minor_radius=.91)
check(bpy.context.object.data,'self intersecting spindle')
bpy.ops.mesh.primitive_cube_add();cube=bpy.context.object
cube.data.vertices[0].co=cube.data.vertices[1].co;cube.data.update();check(cube.data,'degenerate face')
bpy.ops.mesh.primitive_cube_add();a=bpy.context.object
bpy.ops.mesh.primitive_cube_add(location=(4,0,0));b=bpy.context.object
a.select_set(True);b.select_set(True);cube.select_set(False)
bpy.ops.object.join();check(bpy.context.object.data,'disconnected surfaces')
print('INVALID_MESH_PASS')
