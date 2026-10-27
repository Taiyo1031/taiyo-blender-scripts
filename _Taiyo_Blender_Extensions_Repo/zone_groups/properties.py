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
    return obj.type == self.kind

class ZG_ObjectRef(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object)

class ZG_Volume(bpy.types.PropertyGroup):
    kind: EnumProperty(name='Volume Type', description='Empty primitive or raw closed Mesh reference', items=[('EMPTY','Empty','Box or Sphere Empty'),('MESH','Mesh','Closed raw Mesh; modifiers ignored')], default='EMPTY', update=changed)
    controller: PointerProperty(description='Referenced Volume Object; removal only unlinks this reference', type=bpy.types.Object, poll=controller_poll, update=changed)
    operation: EnumProperty(description='ADD includes points; EXCLUDE subtracts points within this Region', items=[('ADD','ADD','Include'),('EXCLUDE','EXCLUDE','Subtract within this Region')], update=changed)

class ZG_Region(bpy.types.PropertyGroup):
    uid: StringProperty()
    eval_mode: EnumProperty(description='Spatial test: Mesh supports only Origin and Bounds Center', items=[('ORIGIN','Origin','Object origin; fastest'),
        ('BOUNDS_CENTER','Bounds Center','Original Object bounding box center'),
        ('FULLY_INSIDE','Fully Inside','All corners inside one volume'),
        ('ANY_OVERLAP','Any Overlap','Bounding box touches volume; slower')], update=changed)
    volumes: CollectionProperty(type=ZG_Volume)
    volume_index: IntProperty()
    t_mesh: BoolProperty(name='Mesh', description='Include Mesh Objects as membership candidates; Volume controllers are excluded', default=True, update=changed)
    t_light: BoolProperty(name='Light', description='Include Light Objects as membership candidates; Volume controllers are excluded', default=True, update=changed)
    t_camera: BoolProperty(name='Camera', description='Include Camera Objects as membership candidates; Volume controllers are excluded', default=True, update=changed)
    t_curve: BoolProperty(name='Curve', description='Include Curve Objects as membership candidates; Volume controllers are excluded', default=True, update=changed)
    t_empty: BoolProperty(name='Empty', description='Include Empty Objects as membership candidates; Volume controllers are excluded', default=False, update=changed)
    t_other: BoolProperty(name='Other', description='Include Other Objects as membership candidates; Volume controllers are excluded', default=True, update=changed)

class ZG_Group(bpy.types.PropertyGroup):
    uid: StringProperty()
    name: StringProperty(default='Group', description='Logical group name; Object and Collection names are unchanged')
    source: EnumProperty(description='Manual references or spatial Volume membership', items=[('MANUAL','Manual','Explicit references'),('VOLUME','Volume','Spatial membership')])
    color: FloatVectorProperty(name='Color', description='Color for this group when global Group Colors is enabled', subtype='COLOR', size=4, min=0, max=1, default=(.12,.45,.8,1), update=style_changed)
    show: BoolProperty(default=True)
    selectable: BoolProperty(default=True)
    render: BoolProperty(default=True)
    update_mode: EnumProperty(items=[('MANUAL','Manual','Evaluate explicitly'),('DIRTY','On Demand','Evaluate before member operations'),('LIVE','Live','Debounced evaluation')], default='DIRTY', description='When spatial membership is recalculated', update=changed)
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
    color_enabled: BoolProperty(name='Group Colors', description='Apply group colors to member Objects in all groups; disable to restore original colors', update=style_changed)
    color_rule: EnumProperty(name='Overlap', description='Color policy for Objects belonging to multiple groups', items=[('TOP','Top Group','First group in list wins'),('OVERLAP','Overlap Color','Two or more memberships use a shared color')], update=style_changed)
    overlap_color: FloatVectorProperty(name='Overlap Color', description='Shared color for Objects belonging to two or more groups', subtype='COLOR', size=4, min=0,max=1,default=(1,0,1,1), update=style_changed)
    isolate_uid: StringProperty()
    fit_margin: FloatProperty(name='Margin', description='Extra padding in Blender units for Fit to Selection', default=.01, min=0)

CLASSES = (ZG_ObjectRef, ZG_Volume, ZG_Region, ZG_Group, ZG_Baseline, ZG_Settings)
