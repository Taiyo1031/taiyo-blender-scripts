"""Small RNA settings and transient caches. No per-object scene properties."""
import time
from types import SimpleNamespace
import bpy
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty)
from bpy.types import AddonPreferences, PropertyGroup
from .definitions import RESTRICTIONS, MODES, MATCH_MODES

ACTIVE = None
SOLOS = {}
CLIPBOARD = None
PREVIEWS = {}
LAST = {}
AUTO_DUE = 0.0


def scene_key(scene):
    return scene.as_pointer()


def solo_key(scene, layer):
    return (scene.as_pointer(), layer.as_pointer())


def changed(self, context):
    global AUTO_DUE
    self.dirty = True
    AUTO_DUE = time.monotonic() + 0.6


def remember(self, context):
    changed(self, context)
    collection = self.target
    if collection is None:
        return
    for i in reversed(range(len(self.recent))):
        if self.recent[i].collection is None or self.recent[i].collection == collection:
            self.recent.remove(i)
    self.recent.add().collection = collection
    self.recent.move(len(self.recent) - 1, 0)
    while len(self.recent) > 10:
        self.recent.remove(len(self.recent) - 1)


OBJECT_TYPES = [(item.identifier, item.name, item.description) for item in bpy.types.Object.bl_rna.properties['type'].enum_items]


class HRM_CollectionRef(PropertyGroup):
    collection: PointerProperty(type=bpy.types.Collection)


class HRM_Settings(PropertyGroup):
    target: PointerProperty(type=bpy.types.Collection, name='Collection', description='Root of the hierarchy to modify', update=remember)
    view_layer: StringProperty(name='View Layer', description='Empty means the current View Layer; global restrictions affect all View Layers', update=changed)
    recent: CollectionProperty(type=HRM_CollectionRef)
    favorites: CollectionProperty(type=HRM_CollectionRef)
    include_root: BoolProperty(name='Include Root', default=True, description='Change the root Collection itself; Object scope is independent', update=changed)
    child_collections: BoolProperty(name='Child Collections', default=True, description='Change descendant Collection flags within the traversal depth', update=changed)
    objects: BoolProperty(name='Objects', default=True, description='Change objects linked directly to traversed, matching Collections, including root objects', update=changed)
    traversal: EnumProperty(name='Traversal', items=[('RECURSIVE', 'All Descendants', ''), ('DIRECT', 'Direct Children', 'Root and depth 1'), ('DEPTH', 'Depth Limit', 'Root is depth 0')], default='RECURSIVE', update=changed)
    depth: IntProperty(name='Maximum Depth', default=3, min=0, max=10000, update=changed)
    use_filters: BoolProperty(name='Enable Filters', default=False, update=changed)
    collection_include: StringProperty(name='Include', update=changed)
    collection_exclude: StringProperty(name='Exclude', update=changed)
    collection_match: EnumProperty(name='Collection Match', items=MATCH_MODES, update=changed)
    object_include: StringProperty(name='Include', update=changed)
    object_exclude: StringProperty(name='Exclude', update=changed)
    object_match: EnumProperty(name='Object Match', items=MATCH_MODES, update=changed)
    case_sensitive: BoolProperty(name='Case Sensitive', update=changed)
    object_types: EnumProperty(name='Object Types', items=OBJECT_TYPES, options={'ENUM_FLAG'}, description='Empty selection means all object types', update=changed)
    branch_behavior: EnumProperty(name='Filter Failure', items=[('ITEM', 'Skip Item Only', 'Skip this Collection and its direct objects; continue to children'), ('BRANCH', 'Skip Entire Branch', 'Do not traverse children of nonmatching Collections')], update=changed)
    dirty: BoolProperty(default=True, options={'SKIP_SAVE'})
    statistics_detail: EnumProperty(name='Statistics', items=[('FAST', 'Fast Counts', ''), ('DETAILED', 'Detailed Preview', 'Read all supported states and estimate property changes')], update=changed)
    solo_mode: EnumProperty(name='Solo Mode', items=[('VISIBLE', 'Viewport Visibility', 'Temporary visibility in the chosen View Layer'), ('VIEWPORT', 'Viewport Enabled', 'Global viewport flags; affects other scenes using these Collections'), ('RENDER', 'Render', 'Global render flags'), ('BOTH', 'Viewport + Render', 'Viewport and global render flags')])
    preset_name: StringProperty(name='Preset Name', default='My Setup')
    preset_include_target: BoolProperty(name='Include Target in Preset', default=False)
    show_target_extras: BoolProperty(name='Recent & Favorites')
    show_scope: BoolProperty(name='Scope')
    show_restrictions: BoolProperty(name='Detailed Restrictions')
    show_filters: BoolProperty(name='Filters')
    show_presets: BoolProperty(name='Presets & Copy / Paste')
    show_statistics: BoolProperty(name='Statistics')
    show_performance: BoolProperty(name='Performance')
    show_last: BoolProperty(name='Last Operation')
    message: StringProperty(options={'SKIP_SAVE'})


for definition in RESTRICTIONS:
    suffix = 'Chosen View Layer' if definition.layer_only else 'Global: affects all View Layers'
    HRM_Settings.__annotations__[definition.key] = EnumProperty(name=definition.label, items=MODES, default='KEEP',
        description=f'{definition.label}. {suffix}. Statistics show stored states, not inherited visibility.', update=changed)


class HRM_Preferences(AddonPreferences):
    bl_idname = __package__
    compact: BoolProperty(name='Compact Restriction UI', default=False)
    performance: EnumProperty(name='Performance', items=[('AUTO', 'Auto', 'Count targets before applying'), ('DETAILED', 'Detailed', 'Analyze states before applying'), ('FAST', 'Fast', 'Stream without counting; still supports progress and Cancel')])
    confirm_large: BoolProperty(name='Confirm Large Operations', default=True)
    threshold: IntProperty(name='Confirmation Threshold', default=50000, min=1)
    progress_interval: IntProperty(name='Progress Item Interval', default=1000, min=100, max=10000)
    auto_refresh: BoolProperty(name='Auto Refresh Statistics', default=False, description='Refresh after HRM settings change; manual Refresh remains available after scene edits')
    show_timer: BoolProperty(name='Show Operation Timer', default=True)
    debug: BoolProperty(name='Debug Performance', default=False)

    def draw(self, context):
        for name in ('compact', 'performance', 'confirm_large', 'threshold', 'progress_interval', 'auto_refresh', 'show_timer', 'debug'):
            self.layout.prop(self, name)


def preferences(context):
    addon = context.preferences.addons.get(__package__)
    if addon:
        return addon.preferences
    return SimpleNamespace(compact=False, performance='AUTO', confirm_large=True, threshold=50000,
                           progress_interval=1000, auto_refresh=False, show_timer=True, debug=False)


def clear_runtime():
    global CLIPBOARD, AUTO_DUE
    SOLOS.clear()
    PREVIEWS.clear()
    LAST.clear()
    CLIPBOARD = None
    AUTO_DUE = 0


@persistent
def before_load(_):
    if ACTIVE:
        ACTIVE.abort_now()
    clear_runtime()


@persistent
def undo_redo(_):
    clear_runtime()


@persistent
def scene_updated(scene, depsgraph):
    if ACTIVE is None and hasattr(scene, 'hrm_settings') and not scene.hrm_settings.dirty:
        scene.hrm_settings.dirty = True


def auto_refresh_tick():
    global AUTO_DUE
    if ACTIVE is None and AUTO_DUE and time.monotonic() >= AUTO_DUE:
        AUTO_DUE = 0
        context = bpy.context
        if context.window and hasattr(context.scene, 'hrm_settings'):
            settings = context.scene.hrm_settings
            if preferences(context).auto_refresh and settings.target:
                try:
                    bpy.ops.hrm.run('INVOKE_DEFAULT', action='REFRESH')
                except (RuntimeError, ValueError):
                    pass
    return 0.3


CLASSES = (HRM_CollectionRef, HRM_Settings, HRM_Preferences)
