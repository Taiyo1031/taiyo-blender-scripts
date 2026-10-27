bl_info = {'name':'Taiyo Object Groups','author':'Taiyo','version':(1,1,2),'blender':(4,5,9),
           'location':'3D Viewport > Sidebar > Groups','description':'Logical spatial groups with reversible colors and restrictions','category':'Object'}
import bpy
from . import properties, runtime, operations, ui
CLASSES=properties.CLASSES+tuple(operations.CLASSES)+ui.CLASSES
HANDLERS=((bpy.app.handlers.depsgraph_update_post,runtime.depsgraph_update),
          (bpy.app.handlers.save_pre,runtime.before_save),
          (bpy.app.handlers.load_pre,runtime.before_load),(bpy.app.handlers.load_post,runtime.reset),
          (bpy.app.handlers.undo_pre,runtime.before_load),(bpy.app.handlers.undo_post,runtime.reset),
          (bpy.app.handlers.redo_pre,runtime.before_load),(bpy.app.handlers.redo_post,runtime.reset))
def register():
    if runtime.ENABLED: return
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.zg=bpy.props.PointerProperty(type=properties.ZG_Settings)
    bpy.types.Object.zg_baseline=bpy.props.PointerProperty(type=properties.ZG_Baseline)
    for handlers,callback in HANDLERS:
        if callback not in handlers: handlers.append(callback)
    runtime.ENABLED=True
    bpy.app.timers.register(runtime.timer,first_interval=.1,persistent=True)
    runtime.CACHE.clear()
def unregister():
    if not runtime.ENABLED: return
    runtime.ENABLED=False
    if runtime.ACTIVE:
        job=runtime.ACTIVE
        callback=getattr(job,'callback',None)
        if callback and bpy.app.timers.is_registered(callback): bpy.app.timers.unregister(callback)
        job.abort()
    if bpy.app.timers.is_registered(runtime.timer): bpy.app.timers.unregister(runtime.timer)
    runtime.MUTATING+=1
    try:
        for scene in bpy.data.scenes: runtime.drain(runtime.apply_style(scene,restore_only=True))
    finally: runtime.MUTATING-=1
    for handlers,callback in HANDLERS:
        if callback in handlers: handlers.remove(callback)
    runtime.CACHE.clear()
    del bpy.types.Object.zg_baseline
    del bpy.types.Scene.zg
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
