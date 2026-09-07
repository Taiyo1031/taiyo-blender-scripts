bl_info = {
    'name': 'Hierarchy Restriction Manager',
    'author': 'Taiyo',
    'version': (1, 0, 0),
    'blender': (4, 5, 5),
    'location': '3D Viewport > Sidebar > Hierarchy',
    'description': 'Apply, preview and restore restriction states across Collection hierarchies',
    'category': 'Scene',
}

import bpy
from bpy.props import PointerProperty
from . import state, operators, ui

CLASSES = state.CLASSES + operators.CLASSES + ui.CLASSES


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.hrm_settings = PointerProperty(type=state.HRM_Settings)
    bpy.types.OUTLINER_MT_collection.append(operators.outliner_menu)
    for handlers, callback in ((bpy.app.handlers.load_pre, state.before_load),
                               (bpy.app.handlers.undo_post, state.undo_redo),
                               (bpy.app.handlers.redo_post, state.undo_redo),
                               (bpy.app.handlers.depsgraph_update_post, state.scene_updated)):
        if callback not in handlers:
            handlers.append(callback)
    if not bpy.app.timers.is_registered(state.auto_refresh_tick):
        bpy.app.timers.register(state.auto_refresh_tick, persistent=True)


def unregister():
    if state.ACTIVE:
        state.ACTIVE.abort_now()
    state.clear_runtime()
    if bpy.app.timers.is_registered(state.auto_refresh_tick):
        bpy.app.timers.unregister(state.auto_refresh_tick)
    for handlers, callback in ((bpy.app.handlers.load_pre, state.before_load),
                               (bpy.app.handlers.undo_post, state.undo_redo),
                               (bpy.app.handlers.redo_post, state.undo_redo),
                               (bpy.app.handlers.depsgraph_update_post, state.scene_updated)):
        if callback in handlers:
            handlers.remove(callback)
    bpy.types.OUTLINER_MT_collection.remove(operators.outliner_menu)
    del bpy.types.Scene.hrm_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
