"""Run in a separate factory-startup UI; save evidence to /tmp and quit."""
import json
import sys
import time
import traceback
from pathlib import Path
import bpy
import addon_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
addon_utils.enable('hierarchy_restriction_manager', default_set=True)
bpy.context.preferences.view.show_splash = False
from hierarchy_restriction_manager import state
LOG = Path('/tmp/hrm-ui-results.json')
results = []
started = time.monotonic()
root = bpy.data.collections.new('HRM UI Validation')
bpy.context.scene.collection.children.link(root)
for i in range(3000):
    obj = bpy.data.objects.new(f'HRM_UI_{i:04}', None)
    root.objects.link(obj)
settings = bpy.context.scene.hrm_settings
settings.target = root
prefs = state.preferences(bpy.context)
prefs.confirm_large = False
prefs.progress_interval = 100
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
area.spaces.active.show_region_ui = True
stage = 'start'


def record(name, ok):
    results.append({'test': name, 'passed': bool(ok)})
    LOG.write_text(json.dumps(results, indent=2))
    if not ok:
        raise AssertionError(name)


def obj():
    return bpy.data.objects['HRM_UI_0000']


def context():
    return bpy.context.temp_override(area=area, region=next(r for r in area.regions if r.type == 'WINDOW'))


def tick():
    global stage
    try:
        if time.monotonic() - started > 90:
            raise TimeoutError(f'{stage}: active={state.ACTIVE is not None}; stats={vars(state.ACTIVE.stats) if state.ACTIVE else None}')
        if stage == 'start':
            with context():
                bpy.ops.ed.undo_push(message='HRM UI fixture')
                result = bpy.ops.hrm.run('INVOKE_DEFAULT', action='RENDER_OFF')
            record('modal started', result == {'RUNNING_MODAL'})
            stage = 'applied'
        elif stage == 'applied' and state.ACTIVE is None:
            record('modal applied all objects', all(o.hide_render for o in bpy.data.collections['HRM UI Validation'].objects))
            with context():
                bpy.ops.ed.undo()
            stage = 'undone'
        elif stage == 'undone':
            record('one native Undo restores batch', not obj().hide_render)
            with context():
                bpy.ops.ed.redo()
            stage = 'redone'
        elif stage == 'redone' and state.ACTIVE is None:
            record('native Redo restores batch', obj().hide_render)
            with context():
                bpy.ops.hrm.run('INVOKE_DEFAULT', action='RENDER_ON')
            stage = 'cancel'
        elif stage == 'cancel' and state.ACTIVE and state.ACTIVE.journal:
            state.ACTIVE.cancel_requested = True
            stage = 'canceled'
        elif stage == 'canceled' and state.ACTIVE is None:
            record('modal Cancel fully restores batch', all(o.hide_render for o in bpy.data.collections['HRM UI Validation'].objects))
            prefs = state.preferences(bpy.context)
            prefs.confirm_large = True
            prefs.threshold = 1000
            with context():
                bpy.ops.hrm.run('INVOKE_DEFAULT', action='RENDER_ON')
            stage = 'confirm'
        elif stage == 'confirm' and state.ACTIVE and state.ACTIVE.waiting:
            record('confirmation before any writes', len(state.ACTIVE.journal) == 0 and obj().hide_render)
            bpy.ops.hrm.control(action='CONFIRM')
            stage = 'confirmed'
        elif stage == 'confirmed' and state.ACTIVE is None:
            record('confirmed batch completes', not obj().hide_render)
            with context():
                bpy.ops.object.mode_set(mode='EDIT')
                result = bpy.ops.hrm.run('INVOKE_DEFAULT', action='RENDER_OFF', confirmed=True)
                record('Edit Mode blocks writes without changing mode', result == {'CANCELLED'} and not obj().hide_render and bpy.context.mode == 'EDIT_MESH')
                bpy.ops.object.mode_set(mode='OBJECT')
            with context():
                bpy.ops.hrm.run('INVOKE_DEFAULT', action='HIDE', confirmed=True)
            stage = 'hidden'
        elif stage == 'hidden' and state.ACTIVE is None:
            record('temporary visibility applied', obj().hide_get(view_layer=bpy.context.view_layer))
            with context():
                bpy.ops.ed.undo()
            stage = 'unhidden'
        elif stage == 'unhidden':
            record('native Undo restores temporary visibility', not obj().hide_get(view_layer=bpy.context.view_layer))
            settings = bpy.context.scene.hrm_settings
            settings.use_filters = True
            settings.object_include = 'HRM_UI_*'
            settings.object_match = 'WILDCARD'
            settings.object_types = {'EMPTY'}
            settings.favorites.add().collection = settings.target
            settings.target.name = 'HRM UI Renamed'
            bpy.ops.wm.save_as_mainfile(filepath='/tmp/hrm-ui-persistence.blend')
            stage = 'reopen'
        elif stage == 'reopen':
            bpy.ops.wm.open_mainfile(filepath='/tmp/hrm-ui-persistence.blend')
            bpy.app.timers.register(after_load, first_interval=0.5)
            return None
        return 0.05
    except Exception:
        results.append({'error': traceback.format_exc(), 'stage': stage})
        LOG.write_text(json.dumps(results, indent=2))
        print(traceback.format_exc(), flush=True)
        if state.ACTIVE:
            state.ACTIVE.abort_now()
        bpy.ops.wm.quit_blender()
        return None


def after_load():
    global area
    try:
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        settings = bpy.context.scene.hrm_settings
        record('saved target follows Collection rename', settings.target.name == 'HRM UI Renamed')
        record('scope, filters and favorites persist', settings.object_types == {'EMPTY'} and settings.object_match == 'WILDCARD' and settings.favorites[-1].collection == settings.target)
        record('load clears runtime caches', not state.SOLOS and not state.PREVIEWS and state.CLIPBOARD is None)
        settings.show_restrictions = False
        settings.show_scope = False
        settings.use_filters = False
        for region in area.regions:
            if region.type == 'UI':
                region.active_panel_category = 'Hierarchy'
        area.tag_redraw()
        def screenshot():
            with context():
                bpy.ops.screen.screenshot(filepath='/tmp/hrm-ui.png')
            print('HRM UI TESTS PASSED', flush=True)
            bpy.ops.wm.quit_blender()
            return None
        bpy.app.timers.register(screenshot, first_interval=1)
    except Exception:
        results.append({'error': traceback.format_exc(), 'stage': 'after_load'})
        LOG.write_text(json.dumps(results, indent=2))
        print(traceback.format_exc(), flush=True)
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1)
