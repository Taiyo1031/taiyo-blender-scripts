import bpy, math, pathlib, importlib, json, os
from mathutils import Quaternion
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
Z.register()
R=Z.runtime
s=bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o,do_unlink=True)
s.name='Taiyo Object Groups - Playground'
s.zg.groups.clear(); R.CACHE.clear()

def select(obs):
    for o in bpy.context.selected_objects:o.select_set(False)
    for o in obs:o.select_set(True)
    bpy.context.view_layer.objects.active=obs[0] if obs else None

def group(name,color,obs=None):
    bpy.ops.zg.group_new(); g=R.active(s); g.name=name; g.color=color
    if obs is not None: select(obs); bpy.ops.zg.add_selected()
    return g

def text(body,xy,size=.42,color=(.7,.8,.9,1)):
    c=bpy.data.curves.new(body,'FONT'); c.body=body; c.size=size; c.align_x='CENTER'; c.extrude=.001
    o=bpy.data.objects.new(body,c); s.collection.objects.link(o); o.location=(*xy,.03); o.color=color; o.hide_select=True
    return o

def piece(name,x,y,kind=0):
    if kind==0:bpy.ops.mesh.primitive_cube_add(size=.65,location=(x,y,.4))
    elif kind==1:bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.38,location=(x,y,.4))
    else:bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=.33,depth=.7,location=(x,y,.4))
    o=bpy.context.object; o.name=name; o.color=(.32,.36,.43,1)
    if kind!=0:
        for p in o.data.polygons:p.use_smooth=True
    return o

text('TAIYO  /  OBJECT GROUPS',(0,6.3),.85,(.88,.94,1,1))
text('Interactive playground  |  Blender 5.2.2  |  Add-on 1.1.0',(0,5.45),.32)
text('01  MANUAL',(-9,4.1),.52,(.1,.65,1,1))
text('02  LIVE BOX',(0,4.1),.52,(.15,.85,.38,1))
text('03  SPHERE - EXCLUDE',(9,4.1),.52,(.35,.5,1,1))
manual=[piece('Manual_%02d'%i,-11+(i%5),2.4-(i//5)*1.2,i%3) for i in range(20)]
a=group('01 Manual / Cyan',(.04,.55,.9,1),manual[:13]); auid=a.uid
b=group('02 Manual / Orange',(1,.28,.04,1),manual[7:]); buid=b.uid
for cx,prefix in [(0,'Box'),(9,'Sphere')]:
    for y in range(7):
        for x in range(7):piece('%s_%02d_%02d'%(prefix,x,y),cx+(x-3)*.85,(y-3)*.85,(x+y)%3)
g=group('03 Live / Box',(.06,.72,.23,1)); bpy.ops.zg.membership_mode(value='VOLUME')
g.update_mode='LIVE'; region=R.region(g)
region.t_curve=False;region.t_other=False;region.t_light=False;region.t_camera=False
bpy.ops.zg.volume_add(shape='CUBE'); box=region.volumes[-1].controller
box.name='MOVE ME - Live Box (G X)';box.location=(0,0,.4);box.scale=(1.8,2,1);box.empty_display_size=1; box.show_in_front=True
boxuid=g.uid
g=group('04 Live / Sphere minus Box',(.14,.3,.95,1));bpy.ops.zg.membership_mode(value='VOLUME')
g.update_mode='LIVE';region=R.region(g)
region.t_curve=False;region.t_other=False;region.t_light=False;region.t_camera=False
bpy.ops.zg.volume_add(shape='SPHERE');sphere=region.volumes[-1].controller
sphere.name='MOVE ME - Sphere ADD';sphere.location=(9,0,.4);sphere.scale=(2.6,2.6,1.3);sphere.empty_display_size=1;sphere.show_in_front=True
bpy.ops.zg.volume_add(shape='CUBE');exclude=region.volumes[-1].controller
exclude.name='MOVE ME - EXCLUDE hole';exclude.location=(9,0,.4);exclude.scale=(.95,.95,1);exclude.empty_display_size=1;exclude.show_in_front=True
region.volumes[-1].operation='EXCLUDE'
text('Cyan + Orange = Magenta',(-9,-3.6),.31)
text('Move the wire box: G, X',(0,-3.6),.31)
text('Gray center = excluded',(9,-3.6),.31)
text('N sidebar > Groups  /  Global Settings: colors, show all',(0,-4.75),.36)
text('Start: selected L Mesh > G > X > move > click. Ctrl+Z to undo.',(0,-5.4),.32)

text('04  CONCAVE MESH',(-6,-7),.52,(.65,.25,1,1))
text('05  THROUGH HOLE MESH',(6,-7),.52,(1,.6,.1,1))
for cx in (-6,6):
    for y in range(9):
        for x in range(9):piece('Mesh sample',cx+(x-4)*.65,-10.5+(y-4)*.65,(x+y)%3)
outline=[(-2,-2),(2,-2),(2,0),(0,0),(0,2),(-2,2)];n=len(outline)
mesh=bpy.data.meshes.new('Closed concave L')
mesh.from_pydata([(x,y,z) for z in (-.5,1.3) for x,y in outline],[],[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)])
mesh.update();l=bpy.data.objects.new('MOVE ME - Concave Mesh L',mesh);s.collection.objects.link(l);l.location=(-6,-10.5,0);l.display_type='WIRE';l.show_in_front=True;l.hide_render=True
mg=group('05 Mesh / Concave L',(.55,.12,.95,1));bpy.ops.zg.membership_mode(value='VOLUME');mg.update_mode='LIVE'
r=R.region(mg);r.t_curve=False;r.t_other=False
bpy.ops.zg.volume_mesh(mesh_name=l.name)
bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=8,major_radius=1.8,minor_radius=.65,location=(6,-10.5,.4))
torus=bpy.context.object;torus.name='MOVE ME - Torus Mesh';torus.display_type='WIRE';torus.show_in_front=True;torus.hide_render=True
mg=group('06 Mesh / Torus',(.95,.5,.06,1));bpy.ops.zg.membership_mode(value='VOLUME');mg.update_mode='LIVE'
r=R.region(mg);r.t_curve=False;r.t_other=False
bpy.ops.zg.volume_mesh(mesh_name=torus.name)
text('Gray notch stays outside',(-6,-14),.32)
text('Gray center stays outside',(6,-14),.32)

bpy.context.view_layer.update(); R.invalidate(s);bpy.ops.zg.evaluate()
s.zg.color_rule='OVERLAP';bpy.ops.zg.color_toggle()
rt=R.get(s)
assert len(rt.members[auid]&rt.members[buid])==6
assert tuple(manual[8].color)==(1,0,1,1)
original=set(rt.members[boxuid]);box.location.x+=1.5;bpy.context.view_layer.update();R.invalidate(s);bpy.ops.zg.evaluate()
assert set(rt.members[boxuid])!=original
box.location.x-=1.5;bpy.context.view_layer.update();R.invalidate(s);bpy.ops.zg.evaluate()
s.zg.active_index=0;bpy.ops.zg.isolate();assert any(o.hide_viewport for o in bpy.data.objects if o.type=='MESH')
bpy.ops.zg.show_all();assert all(not o.hide_viewport for o in bpy.data.objects)
s.zg.active_index=4;select([l])
s.world.color=(.035,.035,.035)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            space=area.spaces.active;space.show_region_ui=True
            space.shading.type='SOLID';space.shading.color_type='OBJECT';space.shading.light='STUDIO'
            space.shading.show_shadows=True;space.shading.show_cavity=True;space.shading.cavity_type='BOTH'
            space.shading.background_type='VIEWPORT';space.shading.background_color=(.018,.025,.04)
            space.overlay.show_floor=False;space.overlay.show_axis_x=False;space.overlay.show_axis_y=False
            space.region_3d.view_distance=45;space.region_3d.view_location=(1,-4,0);space.region_3d.view_rotation=Quaternion((1,0,0),math.radians(15));space.region_3d.view_perspective='ORTHO'
readme='''# Taiyo Object Groups 1.1.0 体験デモ
作成: このMacの Blender 5.2.2 LTS。
アドオンはインストール・有効化済み。Nパネルの「Groups」を開きます。

1. 下段左のL字Meshを選択済みです。G → X → マウスを動かして確定。少し待つと紫色の対象が変わります。Liveは操作が約300ms落ち着いてから更新します。
2. 左は2つのManualグループです。6個のマゼンタは複数所属です。一覧上部の全体設定で Overlap を Top Group に変更すると上のグループの色が優先されます。リストの上下矢印で優先順位を変更できます。
3. 上段右はSphereのADDから小さいBoxのEXCLUDEを引いた領域です。中央の灰色Objectは除外されています。Outlinerの「MOVE ME - EXCLUDE hole」を選択して G → X で動かしてください。
下段右はトーラスMeshです。中央の貫通穴はメンバーになりません。Membersの+から既存の閉じたMeshを登録できます。MeshはOrigin／Bounds CenterのみでModifierは無視します。
4. 一覧でグループを選択し Select でメンバーを選択、一覧行の Isolate で対象だけ表示、全体設定の Show All で戻せます。モニター/矢印アイコンで表示/選択を制限できます。
5. Manualグループを選択し、Objectを選んで Add Selected / Remove Selected を試せます。元Objectは削除されません。
6. Group Colors をOFFにすると元の灰色へ戻ります。再度ONでグループ色になります。
7. EmptyだけのグループではMembersでTestをOrigin / Bounds Center / Fully Inside / Any Overlapに切り替えて、枠の境界での違いを確認できます。
8. Duplicate Groupで複製、同じ所属方式のグループはMerge Groupsで統合できます。

Ctrl+Zで操作をUndo。全体を最初に戻すには File > Revert（未保存の変更は破棄されます）。
3D内の説明文字は選択不可、Volumeの型フィルター対象外です。
このデモは280個のサンプルMeshと2個のMesh Volumeです。性能限界テストではありません。
このファイルを別PCで使う場合は同梱ZIPをPreferences > Get Extensions > Install from Diskで導入してください。
元の正式検証対象は4.5.9 LTS。本デモは5.2.2で基本操作を確認して作成しています。
'''
t=bpy.data.texts.new('はじめに_README');t.write(readme)
out=pathlib.Path.home()/'Downloads'/('Taiyo_Object_Groups_1.1.0_Demo_'+bpy.app.version_string.split()[0]);out.mkdir(exist_ok=True)
path=out/os.environ.get('ZG_DEMO_FILENAME','Taiyo_Object_Groups_Demo.blend')
assert not path.exists(), 'Demo already exists, do not overwrite'
(out/'体験ガイド.md').write_text(readme)
import shutil
shutil.copy2(pathlib.Path(__file__).resolve().parents[1]/'docs/extensions/zone_groups-1.1.0.zip',out/'zone_groups-1.1.0.zip')
bpy.ops.wm.save_as_mainfile(filepath=str(path))
print('DEMO_SAVED',path)
print('GROUP_COUNTS',[(g.name,g.last_evaluated_count) for g in s.zg.groups])
print('DEMO_CHECKS_PASS: overlap color, volume move, isolate, show all')
