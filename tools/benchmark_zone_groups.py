"""Cooperative evaluation and restriction timing on shared-mesh Objects."""
import bpy, sys, pathlib, time, json, resource
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
from zone_groups import runtime as R, operations as O
Z.register(); R.MUTATING+=1
for o in list(bpy.data.objects): bpy.data.objects.remove(o,do_unlink=True)
mesh=bpy.data.meshes.new('Benchmark cube'); mesh.from_pydata([(-.1,-.1,-.1),(.1,.1,.1)],[],[])
s=bpy.context.scene; g=O.new_group(s,'Benchmark'); g.source='VOLUME'; r=R.region(g)
volumes=[]
for i in range(10):
    o=bpy.data.objects.new('Controller',None); s.collection.objects.link(o); o.empty_display_type='CUBE' if i%2==0 else 'SPHERE'
    o.empty_display_size=25; o.location=(i*10,10,0); volumes.append(o)
objects=[]; results=[]
def measured(generator):
    R.STATS['slice_max_ms']=0; start=time.perf_counter(); ticks=0
    while not R.tick_job(generator): ticks+=1
    return {'ms':(time.perf_counter()-start)*1000,'max_slice_ms':R.STATS['slice_max_ms'],'ticks':ticks}
for count,nvol in [(1000,2),(10000,4),(50000,10)]:
    for i in range(len(objects),count):
        o=bpy.data.objects.new(f'Object{i}',mesh); s.collection.objects.link(o)
        o.location=(i%250,(i//250)%200,0); objects.append(o)
    r.volumes.clear()
    for o in volumes[:nvol]: r.volumes.add().controller=o
    bpy.context.view_layer.update(); R.invalidate(s)
    before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    cold=measured(R.evaluation(s,explicit=True))
    after=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    g.show=False; hide=measured(R.apply_style(s)); g.show=True; show=measured(R.apply_style(s))
    writes=R.STATS['writes']; unchanged=measured(R.apply_style(s)); assert R.STATS['writes']==writes
    start=time.perf_counter(); tx=O.Transaction(s); transaction_ms=(time.perf_counter()-start)*1000; tx.complete()
    objects[0].location.x+=.5; bpy.context.view_layer.update(); R.invalidate(s,{objects[0]})
    incremental=measured(R.evaluation(s,explicit=True))
    results.append({'objects':count,'volumes':nvol,'members':len(R.get(s).members[g.uid]),'cold':cold,'incremental':incremental,'hide':hide,'show':show,'no_change':unchanged,'transaction_setup_ms':transaction_ms,'peak_ram_delta_bytes':after-before})
    print('BENCH',json.dumps(results[-1]),flush=True)
    if count==10000:
        manual=O.new_group(s,'Overlapping full selection')
        for item in objects: manual.manual_members.add().obj=item
        R.drain(R.evaluation(s)); manual.show=False
        full_hide=measured(R.apply_style(s)); manual.show=True
        full_show=measured(R.apply_style(s))
        results[-1]['overlap_10000_hide']=full_hide; results[-1]['overlap_10000_show']=full_show
        print('FULL_VISIBILITY',json.dumps({'hide':full_hide,'show':full_show}),flush=True)
        s.zg.groups.remove(1); R.drain(R.evaluation(s))
R.MUTATING-=1
pathlib.Path('/tmp/zone_groups_benchmark.json').write_text(json.dumps(results,indent=2))
