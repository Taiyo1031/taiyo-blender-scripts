import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

TYPES = ('mesh', 'light', 'camera', 'curve', 'empty', 'other')

def changed(self, context):
    from . import runtime
    if runtime.MUTATING:
        return
    scene = self.id_data
    if isinstance(scene, bpy.types.Scene):
        runtime.invalidate(scene)

def style_changed(self, context):
    from . import runtime
    if not runtime.MUTATING and isinstance(self.id_data, bpy.types.Scene):
        rt = runtime.get(self.id_data)
        rt.style_pending = True
        rt.style_stamp = runtime.now()

def controller_poll(self, obj):
    return obj.type == 'EMPTY'

class ZG_ObjectRef(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object)

class ZG_Volume(bpy.types.PropertyGroup):
    controller: PointerProperty(type=bpy.types.Object, poll=controller_poll, update=changed)
    operation: EnumProperty(items=[('ADD','ADD','Include'),('EXCLUDE','EXCLUDE','Subtract within this Region')], update=changed)

class ZG_Region(bpy.types.PropertyGroup):
    uid: StringProperty()
    eval_mode: EnumProperty(items=[('ORIGIN','Origin','Object origin; fastest'),
        ('BOUNDS_CENTER','Bounds Center','Original Object bounding box center'),
        ('FULLY_INSIDE','Fully Inside','All corners inside one volume'),
        ('ANY_OVERLAP','Any Overlap','Bounding box touches volume; slower')], update=changed)
    volumes: CollectionProperty(type=ZG_Volume)
    volume_index: IntProperty()
    t_mesh: BoolProperty(name='Mesh', default=True, update=changed)
    t_light: BoolProperty(name='Light', default=True, update=changed)
    t_camera: BoolProperty(name='Camera', default=True, update=changed)
    t_curve: BoolProperty(name='Curve', default=True, update=changed)
    t_empty: BoolProperty(name='Empty', default=False, update=changed)
    t_other: BoolProperty(name='Other', default=True, update=changed)

class ZG_Group(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty(default='Group')
    source: EnumProperty(items=[('MANUAL','Manual','Explicit references'),('VOLUME','Volume','Spatial membership')])
    color: FloatVectorProperty(name='Color', subtype='COLOR', size=4, min=0, max=1, default=(.12,.45,.8,1), update=style_changed)
    show: BoolProperty(default=True)
    selectable: BoolProperty(default=True)
    render: BoolProperty(default=True)
    update_mode: EnumProperty(items=[('MANUAL','Manual','Evaluate explicitly'),('DIRTY','On Demand','Evaluate before member operations'),('LIVE','Live','Debounced evaluation')], default='DIRTY', update=changed)
    manual_members: CollectionProperty(type=ZG_ObjectRef)
    regions: CollectionProperty(type=ZG_Region)
    active_region_index: IntProperty()
    last_evaluated_count: IntProperty()
    dirty: BoolProperty(default=True)

class ZG_Baseline(bpy.types.PropertyGroup):
    owner: StringProperty()
    mask: IntProperty()
    viewport: BoolProperty()
    select: BoolProperty()
    render: BoolProperty()
    color: FloatVectorProperty(size=4, default=(1,1,1,1))
    # hide_viewport can clear per-layer temporary hide state.
    hidden_layers: StringProperty(default='[]')

class ZG_Settings(bpy.types.PropertyGroup):
    schema_version: IntProperty(default=1)
    groups: CollectionProperty(type=ZG_Group)
    active_index: IntProperty()
    owner_uid: StringProperty()
    color_enabled: BoolProperty(name='Group Colors', update=style_changed)
    color_rule: EnumProperty(name='Overlap', items=[('TOP','Top Group','First group in list wins'),('OVERLAP','Overlap Color','Two or more memberships use a shared color')], update=style_changed)
    overlap_color: FloatVectorProperty(name='Overlap Color', subtype='COLOR', size=4, min=0,max=1,default=(1,0,1,1), update=style_changed)
    isolate_uid: StringProperty()
    fit_margin: FloatProperty(name='Margin', default=.01, min=0)

CLASSES = (ZG_ObjectRef, ZG_Volume, ZG_Region, ZG_Group, ZG_Baseline, ZG_Settings)
