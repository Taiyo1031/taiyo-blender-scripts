"""Regression: Live timer survives .blend loads. Use --factory-startup."""
import pathlib, sys, tempfile
import bpy
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / '_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
Z.register()
assert bpy.app.timers.is_registered(Z.runtime.timer)
with tempfile.TemporaryDirectory(prefix='taiyo_groups_load_') as temp:
    filepath = str(pathlib.Path(temp) / 'reload.blend')
    bpy.ops.wm.save_as_mainfile(filepath=filepath)
    for i in range(2):
        bpy.ops.wm.open_mainfile(filepath=filepath)
        assert bpy.app.timers.is_registered(Z.runtime.timer), 'Live timer lost after file load'
Z.unregister()
assert not bpy.app.timers.is_registered(Z.runtime.timer)
print('PASS: Live timer survives repeated file loads and unregisters cleanly')
