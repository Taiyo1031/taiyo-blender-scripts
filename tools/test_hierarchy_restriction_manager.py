"""Blender integration tests. Run with --background --factory-startup --python this_file."""
import sys
import tempfile
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
import hierarchy_restriction_manager as addon
from hierarchy_restriction_manager import engine, state, operators, presets
from hierarchy_restriction_manager.definitions import modes_with, KEYS


def fixture():
    scene = bpy.data.scenes.new('HRM_Test')
    bpy.context.window.scene = scene
    root = bpy.data.collections.new('Root')
    child = bpy.data.collections.new('Wall_Child')
    grand = bpy.data.collections.new('Wall_Grand')
    other = bpy.data.collections.new('Other')
    scene.collection.children.link(root)
    scene.collection.children.link(other)
    root.children.link(child)
    child.children.link(grand)
    mesh = bpy.data.meshes.new('HRM_Mesh')
    a = bpy.data.objects.new('Wall_A', mesh)
    b = bpy.data.objects.new('Wall_B_proxy', None)
    c = bpy.data.objects.new('Wall_C', mesh)
    o = bpy.data.objects.new('Other_O', mesh)
    root.objects.link(a)
    child.objects.link(b)
    grand.objects.link(c)
    other.objects.link(o)
    child.objects.link(a)  # duplicate Object link
    layer = scene.view_layers[0]
    second = scene.view_layers.new('Other View Layer')
    layer.update()
    return scene, root, child, grand, other, a, b, c, o, layer, second


def lc(layer, collection):
    stack = [layer.layer_collection]
    result = []
    while stack:
        item = stack.pop()
        if item.collection == collection:
            result.append(item)
        stack.extend(item.children)
    return result


def job(root, layer, values, **kwargs):
    cfg = engine.Config(root, layer, modes_with(values), **kwargs)
    result = engine.Job(cfg)
    for _ in result.run():
        pass
    return result


def raw_fixture(f):
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    values = {}
    for item in (root, child, grand, other, a, b, c, o):
        for prop in ('hide_viewport', 'hide_render', 'hide_select'):
            values[(item, prop)] = getattr(item, prop)
    for collection in (root, child, grand, other):
        for l in lc(layer, collection):
            for prop in ('exclude', 'hide_viewport', 'holdout', 'indirect_only'):
                values[(l, prop)] = getattr(l, prop)
    for obj in (a, b, c, o):
        if obj.name in layer.objects:
            values[(obj, '@hide')] = obj.hide_get(view_layer=layer)
    return values


def assert_snapshot(values, layer):
    for (target, prop), value in values.items():
        actual = target.hide_get(view_layer=layer) if prop == '@hide' else getattr(target, prop)
        assert actual == value, (target, prop, value, actual)


def test_modes():
    mapping = {'included': ('L', 'exclude', True), 'selectable': ('C', 'hide_select', True),
        'visible': ('L', 'hide_viewport', True), 'viewport_enabled': ('C', 'hide_viewport', True),
        'holdout': ('L', 'holdout', False), 'indirect_only': ('L', 'indirect_only', False),
        'render_enabled': ('C', 'hide_render', True)}
    for key, (kind, prop, inverted) in mapping.items():
        for mode in ('KEEP', 'ON', 'OFF', 'INVERT'):
            f = fixture()
            scene, root, child, grand, other, a, b, c, o, layer, second = f
            target = lc(layer, root)[0] if kind == 'L' else root
            setattr(target, prop, True)
            before_second = getattr(lc(second, root)[0], prop) if kind == 'L' else None
            result = job(root, layer, {key: mode}, child_collections=False, objects=False)
            expect = True if mode == 'KEEP' else False if mode == 'INVERT' else ((mode == 'OFF') if inverted else (mode == 'ON'))
            assert getattr(target, prop) == expect, (key, mode)
            if kind == 'L':
                assert getattr(lc(second, root)[0], prop) == before_second
            if mode == 'KEEP':
                assert result.stats.scanned == 0 and result.stats.writes == 0
    print('PASS seven restriction mappings and four modes')


def test_objects_and_scope():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    result = job(root, layer, {'render_enabled': 'OFF'}, include_root=False, child_collections=False, traversal='DIRECT')
    assert a.hide_render and b.hide_render and not c.hide_render and not o.hide_render
    assert not root.hide_render and not child.hide_render
    assert result.stats.objects == 2 and result.stats.object_links == 3 and result.stats.writes == 2
    result = job(root, layer, {'render_enabled': 'INVERT'}, include_root=False, child_collections=False, traversal='DIRECT')
    assert not a.hide_render and not b.hide_render  # duplicate A toggled once
    result = job(root, layer, {'render_enabled': 'OFF'}, include_root=False, child_collections=False,
        use_filters=True, object_include='Wall_*', object_exclude='*_proxy', object_match='WILDCARD', object_types={'MESH'})
    assert a.hide_render and c.hide_render and not b.hide_render and not o.hide_render
    result = job(root, layer, {'selectable': 'OFF'}, traversal='DEPTH', depth=0)
    assert root.hide_select and a.hide_select and not b.hide_select and not child.hide_select
    result = job(root, layer, {'visible': 'OFF'}, include_root=False, child_collections=False)
    assert a.hide_get(view_layer=layer) and not a.hide_get(view_layer=second)
    print('PASS Object deduplication, scope, depth, filters, per-View-Layer visibility')


def test_pruning_and_shared_collections():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    result = job(root, layer, {'render_enabled': 'OFF'}, use_filters=True, collection_include='Wall', branch_behavior='ITEM')
    assert not root.hide_render and child.hide_render and grand.hide_render
    child.hide_render = grand.hide_render = False
    result = job(root, layer, {'render_enabled': 'OFF'}, use_filters=True, collection_include='Wall', branch_behavior='BRANCH')
    assert not child.hide_render and not grand.hide_render
    other.children.link(child)
    layer.update()
    assert len(lc(layer, child)) == 2
    result = job(child, layer, {'holdout': 'ON'}, objects=False)
    assert all(l.holdout for l in lc(layer, child))
    lc(layer, child)[0].holdout = False
    cfg = engine.Config(child, layer, modes_with({}))
    generator = engine.snapshot_root(cfg)
    try:
        while True:
            next(generator)
    except StopIteration as done:
        values, mixed = done.value
    assert values['holdout'] == 'KEEP' and 'Holdout' in mixed
    print('PASS branch pruning and multiply-linked Collection states')


def test_show_excluded_and_rollback():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    lc(layer, root)[0].exclude = True
    root.hide_viewport = True
    a.hide_viewport = True
    result = job(root, layer, {'included': 'ON', 'viewport_enabled': 'ON', 'visible': 'ON'})
    assert not lc(layer, root)[0].exclude and not root.hide_viewport and not a.hide_viewport
    assert a.name in layer.objects and not a.hide_get(view_layer=layer)
    a.hide_set(True, view_layer=layer)
    before = raw_fixture(f)
    result = job(root, layer, {'visible': 'OFF', 'included': 'OFF', 'viewport_enabled': 'OFF', 'render_enabled': 'OFF', 'holdout': 'ON'})
    assert result.stats.errors == 0, result.stats.messages
    for _ in engine.restore_changes(result.journal, result.stats):
        pass
    layer.update()
    assert_snapshot(before, layer)
    print('PASS excluded hierarchy Show and complete reverse-order rollback')


def test_preview_readonly_and_invalid():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    before = raw_fixture(f)
    cfg = engine.Config(root, layer, modes_with({'render_enabled': 'OFF'}))
    preview = engine.Job(cfg, preview=True, detailed=True)
    for _ in preview.run():
        pass
    assert_snapshot(before, layer)
    assert preview.stats.writes == 6 and preview.stats.objects == 3
    with tempfile.TemporaryDirectory() as temp:
        file = str(Path(temp) / 'library.blend')
        bpy.data.libraries.write(file, {other})
        with bpy.data.libraries.load(file, link=True) as (src, dst):
            dst.collections = [other.name]
        linked = dst.collections[0]
        scene.collection.children.link(linked)
        result = job(linked, layer, {'render_enabled': 'OFF'})
        assert result.stats.readonly >= 1, vars(result.stats)
        assert not linked.hide_render
        override_collection = linked.override_hierarchy_create(scene, layer, do_fully_editable=True)
        override = override_collection.objects[0]
        assert override.override_library and engine.writable(override, 'hide_render')
        result = job(override_collection, layer, {'render_enabled': 'OFF'}, include_root=False, child_collections=False)
        assert override.hide_render and result.stats.errors == 0
    try:
        job(root, layer, {'render_enabled': 'OFF'}, use_filters=True, object_include='[', object_match='REGEX')
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid regex accepted')
    print('PASS read-only library, writable Library Override, nonmutating detailed preview, invalid regex')


def test_operators_cancel_solo_presets():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    settings = scene.hrm_settings
    settings.target = root
    settings.render_enabled = 'OFF'
    assert bpy.ops.hrm.run(action='UNLOCK', confirmed=True) == {'FINISHED'}
    assert not a.hide_render and not root.hide_render  # quick action must not use pending Render setting
    session = operators.Session(bpy.context, 'APPLY', True)
    state.ACTIVE = session
    while not session.journal:
        next(session.generator)
    session.cancel_requested = True
    while not session.finished:
        session.step()
    assert not a.hide_render and not root.hide_render and state.ACTIVE is None
    assert bpy.ops.hrm.run(action='COPY') == {'FINISHED'}
    assert state.CLIPBOARD
    assert bpy.ops.hrm.settings(action='PASTE') == {'FINISHED'}
    assert bpy.ops.hrm.run(action='REFRESH') == {'FINISHED'}
    assert state.PREVIEWS.get(state.scene_key(scene))
    before = raw_fixture(f)
    a.hide_set(True, view_layer=layer)
    before = raw_fixture(f)
    assert bpy.ops.hrm.run(action='SOLO', confirmed=True) == {'FINISHED'}
    assert lc(layer, other)[0].hide_viewport and a.hide_get(view_layer=layer)
    settings.target = other
    assert bpy.ops.hrm.run(action='SOLO', confirmed=True) == {'FINISHED'}
    assert lc(layer, root)[0].hide_viewport and not lc(layer, other)[0].hide_viewport
    assert bpy.ops.hrm.run(action='RESTORE', confirmed=True) == {'FINISHED'}
    assert_snapshot(before, layer)
    settings.target = root
    settings.render_enabled = 'OFF'
    saved = presets.capture(settings)
    settings.render_enabled = 'KEEP'
    assert 'loaded' in presets.apply(settings, saved)
    assert settings.render_enabled == 'OFF'
    with tempfile.TemporaryDirectory() as temp:
        original = presets.path
        presets.path = lambda: Path(temp) / 'presets.json'
        try:
            assert bpy.ops.hrm.settings(action='SAVE', name='Fixture') == {'FINISHED'}
            assert 'Fixture' in presets.read()
            assert bpy.ops.hrm.settings(action='DELETE', name='Fixture') == {'FINISHED'}
            assert not presets.read()
        finally:
            presets.path = original
    settings.target = child
    settings.target = root
    assert len(settings.recent) == 3 and settings.recent[0].collection == root
    assert bpy.ops.hrm.target(action='FAVORITE') == {'FINISHED'}
    assert settings.favorites[0].collection == root
    print('PASS Quick Actions independence, mid-operation Cancel, Solo re-target/Restore, presets/history')


def test_all_solo_modes_and_viewlayer_recovery():
    for mode in ('VISIBLE', 'VIEWPORT', 'RENDER', 'BOTH'):
        f = fixture()
        scene, root, child, grand, other, a, b, c, o, layer, second = f
        settings = scene.hrm_settings
        settings.target = root
        settings.solo_mode = mode
        o.hide_set(True, view_layer=layer)
        o.hide_set(True, view_layer=second)
        a.hide_set(True, view_layer=layer)
        before = raw_fixture(f)
        assert bpy.ops.hrm.run(action='SOLO', confirmed=True) == {'FINISHED'}
        assert bpy.ops.hrm.run(action='RESTORE', confirmed=True) == {'FINISHED'}
        assert_snapshot(before, layer)
        assert o.hide_get(view_layer=second), mode
        settings.target = root
        assert bpy.ops.hrm.run(action='SOLO', confirmed=True) == {'FINISHED'}
        settings.target = other
        session = operators.Session(bpy.context, 'SOLO', True)
        state.ACTIVE = session
        before_cancel = raw_fixture(f)
        while not session.journal:
            next(session.generator)
        session.cancel_requested = True
        while not session.finished:
            session.step()
        assert_snapshot(before_cancel, layer)
        assert bpy.ops.hrm.run(action='RESTORE', confirmed=True) == {'FINISHED'}
        assert_snapshot(before, layer)
    print('PASS all Solo modes, cross-View-Layer hide recovery, canceled Solo retarget')


def test_saving_targets_and_stale_references():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    settings = scene.hrm_settings
    settings.target = root
    settings.preset_include_target = True
    saved = presets.capture(settings)
    settings.target = child
    presets.apply(settings, saved)
    assert settings.target == root
    settings.view_layer = 'Missing Layer'
    assert bpy.ops.hrm.run(action='SHOW') == {'CANCELLED'}
    settings.view_layer = ''
    cfg = engine.Config(child, layer, modes_with({'render_enabled': 'OFF'}))
    bpy.data.collections.remove(child)
    try:
        engine.Job(cfg)
    except engine.InvalidTarget:
        pass
    else:
        raise AssertionError('Deleted Collection accepted')
    empty = bpy.data.collections.new('Empty target')
    scene.collection.children.link(empty)
    assert job(empty, layer, {'render_enabled': 'OFF'}).stats.writes == 1
    print('PASS preset target resolution, stale View Layer, deleted/empty target')


def test_solo_direct_ancestor_objects_and_missing_target_restore():
    f = fixture()
    scene, root, child, grand, other, a, b, c, o, layer, second = f
    direct = bpy.data.objects.new('Direct Scene Object', None)
    scene.collection.objects.link(direct)
    settings = scene.hrm_settings
    settings.target = child
    settings.use_filters = True
    settings.object_match = 'REGEX'
    settings.object_include = '['  # Solo and Restore ignore unrelated pending filters.
    layer.update()
    assert bpy.ops.hrm.run(action='SOLO', confirmed=True) == {'FINISHED'}
    assert direct.hide_get(view_layer=layer)
    assert not a.hide_get(view_layer=layer)  # also linked inside target
    assert not b.hide_get(view_layer=layer)
    settings.target = None
    assert bpy.ops.hrm.run(action='RESTORE', confirmed=True) == {'FINISHED'}
    assert not direct.hide_get(view_layer=layer)
    print('PASS Solo ancestor direct objects, shared target objects, Restore with no target')


def main():
    addon.register()
    for test in (test_modes, test_objects_and_scope, test_pruning_and_shared_collections,
                 test_show_excluded_and_rollback, test_preview_readonly_and_invalid,
                 test_operators_cancel_solo_presets, test_all_solo_modes_and_viewlayer_recovery, test_saving_targets_and_stale_references, test_solo_direct_ancestor_objects_and_missing_target_restore):
        test()
    addon.unregister()
    addon.register()
    addon.unregister()
    assert not hasattr(bpy.types.Scene, 'hrm_settings')
    print('ALL HRM INTEGRATION TESTS PASSED')


if __name__ == '__main__':
    main()
