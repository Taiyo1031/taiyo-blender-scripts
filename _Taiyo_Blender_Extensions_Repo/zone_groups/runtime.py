"""Scene caches and cooperative evaluation. No RNA writes from draw callbacks."""
import time
import uuid
import json
import traceback
from collections import defaultdict
import bpy
import numpy as np
from bpy.app.handlers import persistent
from . import geometry, mesh_volume
from .properties import TYPES

CACHE = {}
MUTATING = 0
ACTIVE = None
ENABLED = False
STATS = {'evaluations': 0, 'writes': 0, 'handler_max_ms': 0., 'slice_max_ms': 0.}
now = time.perf_counter

class SceneCache:
    def __init__(self):
        self.members = {}
        self.owned = None
        self.reverse = defaultdict(set)
        self.records = {}
        self.controllers = {}
        self.mesh_cache = {}
        self.mesh_dirty = set()
        self.failed_generation = -1
        self.ui_signature = None
        self.data_users = defaultdict(set)
        self.generation = 0
        self.pending = None  # None = full evaluation; set = changed Objects
        self.changed_at = now()
        self.style_pending = False
        self.style_stamp = 0.
        self.count = -1
        self.scene_objects = set()
        self.progress = ''
        self.warning = ''
        self.selection = ()
        self.selection_label = 'In: —'
        self.selected_count = 0

def alive(obj):
    try:
        return obj is not None and obj.as_pointer() != 0
    except ReferenceError:
        return False

def ensure_owner(scene):
    if not scene.zg.owner_uid:
        scene.zg.owner_uid = str(uuid.uuid4())
    for other in bpy.data.scenes:
        if other != scene and other.as_pointer() in CACHE and other.zg.owner_uid == scene.zg.owner_uid:
            scene.zg.owner_uid = str(uuid.uuid4())
            break

def get(scene):
    key = scene.as_pointer()
    if key not in CACHE:
        CACHE[key] = SceneCache()
        CACHE[key].style_pending = bool(scene.zg.groups)
    return CACHE[key]

def active(scene):
    s = scene.zg
    return s.groups[s.active_index] if 0 <= s.active_index < len(s.groups) else None

def region(group):
    if not group.regions:
        r = group.regions.add(); r.uid = str(uuid.uuid4())
    group.active_region_index = min(max(group.active_region_index, 0), len(group.regions)-1)
    return group.regions[group.active_region_index]

def invalidate(scene, objects=None):
    rt = get(scene)
    rt.generation += 1
    rt.changed_at = now()
    if objects is None:
        rt.pending = None
    elif rt.pending is not None:
        rt.pending.update(objects)
    for g in scene.zg.groups:
        if g.source == 'VOLUME':
            g.dirty = True
    rt.selection = ()

def object_type(obj):
    return {'MESH':'mesh','LIGHT':'light','CAMERA':'camera','CURVE':'curve',
            'CURVES':'curve','SURFACE':'curve','FONT':'curve','EMPTY':'empty'}.get(obj.type,'other')

def record(obj, bounds=True):
    matrix = np.array(obj.matrix_world, dtype=np.float64)
    origin = matrix[:3,3]
    corners = None
    if bounds:
        box = np.array(obj.bound_box, dtype=np.float64)
        if np.all(box == -1):
            corners = np.repeat(origin[None,:], 8, axis=0)
        else:
            lo, hi = box.min(axis=0), box.max(axis=0)
            local = (hi+lo)/2 + geometry.SIGNS*(hi-lo)/2
            corners = geometry.transform(local, matrix)
    return (origin, corners, object_type(obj), matrix)

def controller_signature(obj):
    return (tuple(v for row in obj.matrix_world for v in row), obj.type, obj.data.as_pointer() if obj.data else 0, obj.empty_display_type, obj.empty_display_size)

def evaluation(scene, groups=None, explicit=False):
    """Stage complete sets then publish together; yields between bounded chunks."""
    global MUTATING
    ensure_owner(scene)
    rt = get(scene)
    targets = list(groups) if groups is not None else list(scene.zg.groups)
    needed = [g for g in targets if g.source == 'VOLUME' and (g.dirty or g.uid not in rt.members)]
    blocked = [g.name for g in needed if g.update_mode == 'MANUAL' and not explicit]
    if blocked:
        raise ValueError('Evaluate required (Manual update): ' + ', '.join(blocked))
    generation = rt.generation
    controllers = {}
    for g in scene.zg.groups:
        for r in g.regions:
            for v in r.volumes:
                if v.controller:
                    controllers[v.controller] = controller_signature(v.controller)
    rt.controllers = controllers
    count = len(scene.objects)
    full = rt.pending is None or rt.count != count or any(g.uid not in rt.members for g in needed)
    require_bounds = any(r.eval_mode != 'ORIGIN' for g in needed for r in g.regions)
    objects = []
    # Membership in Scene is checked once per candidate. Never materialize the
    # full RNA collection in one timer callback.
    if rt.count != count or rt.pending is None:
        scene_objects = set()
        for i, obj in enumerate(scene.objects):
            scene_objects.add(obj)
            if i % 256 == 0: yield
        rt.scene_objects = scene_objects
        if rt.owned is not None: rt.owned.intersection_update(scene_objects)
        # Drop deleted references before reading any cached RNA pointer.
        retained={}
        for i,(o,rec) in enumerate(rt.records.items()):
            if alive(o) and o in scene_objects:retained[o]=rec
            if i%128==0:yield
        rt.records=retained
        rt.data_users.clear()
    source = scene.objects if full else rt.pending
    if needed:
        for i, obj in enumerate(source):
            if alive(obj) and obj in rt.scene_objects and obj not in controllers:
                objects.append(obj)
                rt.records[obj] = record(obj, require_bounds)
                if obj.data:
                    rt.data_users[obj.data].add(obj)
            if i % 32 == 0:
                yield
    staged = {}
    warnings = set()
    for group in targets:
        if group.source == 'MANUAL':
            members = set()
            for i, ref in enumerate(group.manual_members):
                if ref.obj and ref.obj in rt.scene_objects:
                    members.add(ref.obj)
                if i % 128 == 0:
                    yield
            staged[group.uid] = members
    changed = set(objects)
    for group in needed:
        result = set() if full else (rt.members.get(group.uid, set()) & rt.scene_objects) - changed
        for r in group.regions:
            volumes = []
            for v in r.volumes:
                obj = v.controller
                if not obj or obj not in rt.scene_objects:
                    if v.kind=='MESH': raise ValueError('Missing Mesh Volume reference')
                    warnings.add('Missing Controller'); continue
                if obj.type == 'MESH':
                    if r.eval_mode not in {'ORIGIN','BOUNDS_CENTER'}:
                        raise ValueError('Mesh Volume supports Origin / Bounds Center only')
                    if obj.data in rt.mesh_dirty:
                        if obj.data in rt.mesh_cache and not (yield from mesh_volume.unchanged(obj.data,rt.mesh_cache[obj.data])):
                            rt.mesh_cache.pop(obj.data,None)
                        rt.mesh_dirty.discard(obj.data)
                    if obj.data not in rt.mesh_cache:
                        rt.progress='Validating Mesh: '+obj.name
                        try: rt.mesh_cache[obj.data] = yield from mesh_volume.build(obj.data, STATS)
                        except ValueError as error: raise ValueError(obj.name+': '+str(error)) from error
                elif obj.type != 'EMPTY' or obj.empty_display_type not in {'CUBE','SPHERE'}:
                    warnings.add('Unsupported Controller shape'); continue
                matrix = np.array(obj.matrix_world, dtype=np.float64)
                try:
                    inv = np.linalg.inv(matrix)
                except np.linalg.LinAlgError:
                    if obj.type=='MESH': raise ValueError('Zero scale Mesh Volume: '+obj.name)
                    warnings.add('Zero scale Controller'); continue
                volumes.append((v.operation, inv, 'MESH' if obj.type=='MESH' else obj.empty_display_type, rt.mesh_cache[obj.data] if obj.type=='MESH' else obj.empty_display_size))
            if not any(v[0] == 'ADD' for v in volumes):
                continue
            step = 4 if r.eval_mode == 'ANY_OVERLAP' or any(v[2]=='MESH' for v in volumes) else 128
            allowed = {t for t in TYPES if getattr(r, 't_'+t)}
            for offset in range(0, len(objects), step):
                batch = [o for o in objects[offset:offset+step] if rt.records[o][2] in allowed]
                if not batch:
                    yield; continue
                origins = np.array([rt.records[o][0] for o in batch])
                bounds = None if not require_bounds else np.array([rt.records[o][1] for o in batch])
                add = np.zeros(len(batch), dtype=bool)
                exclude = add.copy()
                for op, inv, shape, size in volumes:
                    if shape=='MESH':
                        points=origins if r.eval_mode=='ORIGIN' else bounds.mean(axis=1)
                        hit=size.contains(geometry.transform(points,inv))
                    else: hit = geometry.predicate(origins, bounds, inv, shape, size, r.eval_mode)
                    if op == 'ADD': add |= hit
                    else: exclude |= hit
                    yield
                result.update(o for o, hit in zip(batch, add & ~exclude) if hit)
                rt.progress = f'Evaluating {group.name}: {min(offset+step,len(objects))}/{len(objects)}'
        staged[group.uid] = result
    if rt.generation != generation:
        raise InterruptedError('Scene changed during evaluation; retry')
    valid = {g.uid for g in scene.zg.groups}
    members = {uid: items for uid, items in rt.members.items() if uid in valid}
    members.update(staged)
    reverse = defaultdict(set)
    for uid, items in members.items():
        for i, obj in enumerate(items):
            reverse[obj].add(uid)
            if i % 256 == 0: yield
    if rt.generation != generation:
        raise InterruptedError('Scene changed during evaluation; retry')
    rt.members, rt.reverse = members, reverse
    for g in targets:
        if g.uid in staged:
            g.last_evaluated_count = len(staged[g.uid]); g.dirty = False
    if all(not g.dirty for g in scene.zg.groups if g.source == 'VOLUME'):
        rt.pending = set()
    rt.count = count
    rt.warning = '; '.join(sorted(warnings))
    rt.selection = ()
    rt.progress = ''
    if needed: STATS['evaluations'] += 1
    yield

def baseline_values(b):
    return {'owner':b.owner, 'mask':b.mask, 'viewport':b.viewport,'select':b.select,'render':b.render,
            'color':tuple(b.color), 'hidden_layers':b.hidden_layers}

def restore_hidden(obj, scene, encoded):
    for name in json.loads(encoded):
        layer = scene.view_layers.get(name)
        if layer and obj.name in layer.objects:
            obj.hide_set(True, view_layer=layer)

def apply_style(scene, journal=None, restore_only=False):
    ensure_owner(scene)
    rt = get(scene); settings = scene.zg
    if rt.owned is None:
        rt.owned = set()
        for i,obj in enumerate(scene.objects):
            if obj.zg_baseline.owner == settings.owner_uid and obj.zg_baseline.mask:
                rt.owned.add(obj)
            if i % 128 == 0: yield
    baselines = {o:o.zg_baseline for o in rt.owned if alive(o) and o.zg_baseline.mask}
    ordered = {g.uid:(i,g) for i,g in enumerate(settings.groups)}
    # Union construction is bounded by tracked objects, never scene size except Isolate.
    candidates = set(baselines) | set(rt.reverse)
    if settings.isolate_uid and not restore_only:
        for i, obj in enumerate(scene.objects):
            candidates.add(obj)
            if i % 256 == 0: yield
    isolated = rt.members.get(settings.isolate_uid,set())
    layer_objects = []
    needs_layers = bool(settings.isolate_uid) or any(not g.show for g in settings.groups) or any(b.mask & 1 for b in baselines.values())
    if candidates and needs_layers:
        for layer in scene.view_layers:
            objects = set()
            for i, obj in enumerate(layer.objects):
                objects.add(obj)
                if i % 256 == 0: yield
            layer_objects.append((layer, objects))
    for i, obj in enumerate(candidates):
        yield  # RNA flag writes can be expensive on large dependency graphs.
        if not alive(obj): continue
        if obj.zg_baseline.mask and obj.zg_baseline.owner != settings.owner_uid:
            rt.warning = f'Shared Object managed by another Scene: {obj.name}'
            continue
        if not obj.is_editable:
            rt.warning = 'Read-only Object skipped: ' + obj.name
            continue
        groups = [ordered[u][1] for u in rt.reverse.get(obj,()) if u in ordered]
        b = baselines.get(obj)
        desired = {}
        if not restore_only:
            if settings.isolate_uid:
                if obj not in isolated: desired[1] = True
            elif any(not g.show for g in groups): desired[1] = True
            if any(not g.selectable for g in groups): desired[2] = True
            if any(not g.render for g in groups): desired[4] = True
            if settings.color_enabled and groups:
                desired[8] = tuple(settings.overlap_color) if settings.color_rule == 'OVERLAP' and len(groups)>1 else tuple(min(groups,key=lambda g:ordered[g.uid][0]).color)
        if not desired and not b: continue
        if journal is not None and obj not in journal:
            journal[obj] = (obj.hide_viewport,obj.hide_select,obj.hide_render,tuple(obj.color),
                            [l.name for l, objects in layer_objects if obj in objects and obj.hide_get(view_layer=l)], baseline_values(obj.zg_baseline))
        if b is None:
            b = obj.zg_baseline; b.owner = settings.owner_uid; baselines[obj] = b; rt.owned.add(obj)
        for bit, attr, saved in ((1,'hide_viewport','viewport'),(2,'hide_select','select'),(4,'hide_render','render'),(8,'color','color')):
            if bit in desired:
                if not b.mask & bit:
                    setattr(b, saved, getattr(obj,attr)); b.mask |= bit
                    if bit == 1:
                        b.hidden_layers = json.dumps([l.name for l, objects in layer_objects if obj in objects and obj.hide_get(view_layer=l)])
                value = desired[bit]
            elif b.mask & bit:
                value = getattr(b,saved); b.mask &= ~bit
            else: continue
            old = tuple(obj.color) if bit == 8 else getattr(obj,attr)
            new = tuple(value) if bit == 8 else value
            if old != new:
                setattr(obj,attr,value); STATS['writes'] += 1
                if bit == 1 and b.hidden_layers != '[]': restore_hidden(obj,scene,b.hidden_layers)
        if i % 8 == 0: yield
        if not b.mask:
            b.owner = ''
            rt.owned.discard(obj)
    rt.style_pending = False

def drain(generator):
    for _ in generator: pass

def tick_job(generator, budget=.005):
    start = now()
    try:
        while now()-start < budget: next(generator)
    except StopIteration:
        return True
    finally:
        STATS['slice_max_ms'] = max(STATS['slice_max_ms'], (now()-start)*1000)
    return False

@persistent
def depsgraph_update(scene, depsgraph):
    if MUTATING or not ENABLED or not hasattr(scene,'zg') or not scene.zg.groups: return
    start = now(); rt = get(scene)
    # Bulk rebuilds (Undo, dependency graph changes) must not do thousands of
    # matrix conversions in a synchronous handler. Defer a full evaluation.
    if len(depsgraph.updates) > 256:
        rt.mesh_dirty.update(rt.mesh_cache)
        invalidate(scene)
        STATS['handler_max_ms'] = max(STATS['handler_max_ms'],(now()-start)*1000)
        return
    for update in depsgraph.updates:
        item=update.id.original
        if update.is_updated_geometry:
            data=item.data if isinstance(item,bpy.types.Object) and item.type=='MESH' else item
            if data in rt.mesh_cache:
                rt.mesh_dirty.add(data); invalidate(scene)
    if len(scene.objects) != rt.count:
        invalidate(scene)
    else:
        dirty = set(); full = False
        for update in depsgraph.updates:
            item = update.id.original
            if isinstance(item, bpy.types.Object):
                if item in rt.controllers:
                    if rt.controllers[item] != controller_signature(item): full = True
                elif item not in rt.scene_objects:
                    full = True
                elif update.is_updated_transform or update.is_updated_geometry:
                    rec = rt.records.get(item)
                    matrix = np.array(item.matrix_world)
                    if rec is None or update.is_updated_geometry or not np.array_equal(matrix, rec[3]): dirty.add(item)
            elif update.is_updated_geometry:
                dirty.update(rt.data_users.get(item,()))
        if full: invalidate(scene)
        elif dirty: invalidate(scene,dirty)
    STATS['handler_max_ms'] = max(STATS['handler_max_ms'],(now()-start)*1000)

@persistent
def reset(*_):
    global ACTIVE
    if ACTIVE is not None:
        ACTIVE.cancel_requested = True
    CACHE.clear()
    for scene in bpy.data.scenes:
        if hasattr(scene,'zg'):
            for g in scene.zg.groups: g.dirty = True
            settings = scene.zg
            rt = get(scene)
            rt.style_pending = bool(settings.groups)
            rt.style_stamp = now()

@persistent
def before_load(*_):
    global ACTIVE
    if ACTIVE is not None:
        ACTIVE.abort()
    CACHE.clear()

def selection_summary(scene):
    rt=get(scene)
    if bpy.context.scene != scene: return
    selected=tuple(bpy.context.selected_objects)
    key=tuple(o.as_pointer() for o in selected)
    if key == rt.selection: return
    rt.selection=key; rt.selected_count=len(selected)
    sets=[rt.reverse.get(o,set()) for o in selected]
    common=set.intersection(*(set(s) for s in sets)) if sets else set()
    names=[g.name for g in scene.zg.groups if g.uid in common]
    mixed=bool(sets and any(s != sets[0] for s in sets))
    rt.selection_label=('Common: ' if len(selected)>1 else 'In: ')+(' / '.join(names) or 'None')+(' | Mixed membership' if mixed else '')
    if any(g.dirty and g.source=='VOLUME' for g in scene.zg.groups): rt.selection_label+=' (Dirty)'

@persistent
def before_save(*_):
    # Saving an incomplete restriction batch would persist a partial transaction.
    if ACTIVE is not None:
        ACTIVE.cancel_requested=True
        ACTIVE.abort()

def timer():
    if not ENABLED: return None
    scene=bpy.context.scene
    if scene is None or not hasattr(scene,'zg'): return .2
    rt=get(scene)
    selection_summary(scene)
    signature=(rt.progress,rt.warning,rt.selection_label,rt.selected_count,ACTIVE is not None,
               tuple((g.uid,g.name,g.dirty,g.last_evaluated_count) for g in scene.zg.groups))
    if signature!=rt.ui_signature:
        rt.ui_signature=signature
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type=='VIEW_3D': area.tag_redraw()
    if ACTIVE is not None: return .1
    if bpy.context.mode != 'OBJECT': return .1
    live=[g for g in scene.zg.groups if g.source=='VOLUME' and g.update_mode=='LIVE' and g.dirty]
    if rt.failed_generation!=rt.generation and ((live and now()-rt.changed_at>=.3) or (rt.style_pending and now()-rt.style_stamp>=.3)):
        from .operations import BackgroundJob
        BackgroundJob.start(scene, live)
    return .1
