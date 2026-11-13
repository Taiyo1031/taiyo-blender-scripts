"""Switch a zone between its original map (before the first Replace Zone) and the imported map."""
import bpy
from bpy.props import EnumProperty, StringProperty
from .chunked import ChunkedOperator
from .journal import (Journal, STATE_AFTER, STATE_BEFORE, STATE_KEY, apply_absent, apply_present, archive_name, capture,
                      read_run, write_run)
from .placement import build_parent_index, collection_colname, colname_parts, effective_zone


class MRT_OT_SwitchMapState(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.switch_map_state'
    bl_label = 'Switch Map State'
    bl_description = ('ゾーンの状態を、最初のマップ（Replace Zone の前）とHoudiniから戻したマップの間で切り替えます。'
                      '動かしたObjectは元の位置へ、退避したObjectは元のCollectionへ、新しく作ったObjectは退避用Collectionへ移します。何度でも切り替えられます')

    target: EnumProperty(name='Show', items=[('BEFORE', 'Original', ''), ('AFTER', 'Imported', '')], default='BEFORE')
    zone: StringProperty(name='Zone', default='', description='空欄なら置換ゾーン欄の名前')

    def work(self, context):
        p = context.scene.mrt_props
        scene = context.scene
        zone = self.zone or effective_zone(p)
        if not zone:
            raise ValueError('Zone name is empty.')
        archive = bpy.data.collections.get(archive_name(zone))
        if archive is None:
            raise ValueError(f'Nothing to switch: {zone} has not been replaced.')
        want = STATE_BEFORE if self.target == 'BEFORE' else STATE_AFTER
        state = archive.get(STATE_KEY, STATE_AFTER)
        label = 'original' if want == STATE_BEFORE else 'imported'
        if state == want:
            raise ValueError(f'{zone} already shows the {label} map.')
        fallback = p.map_coll or scene.collection
        specs = {}
        for i, ob in enumerate(bpy.data.objects):
            spec = read_run(ob)
            if spec is not None and spec.get('zone') == zone:
                specs[ob] = spec
            if i % 1024 == 0:
                yield
        if not specs:
            raise ValueError(f'No object of {zone} has a saved state.')
        owners = {}
        roots = {s.collection for s in bpy.data.scenes}
        for c in (*bpy.data.collections, *roots):
            for i, ob in enumerate(c.objects):
                if ob in specs:
                    owners.setdefault(ob, []).append(c)
                if i % 1024 == 0:
                    yield
            yield
        parents, root_set = build_parent_index(p.map_coll)
        journal = Journal()
        changed = missing = 0
        try:
            for n, (ob, spec) in enumerate(specs.items()):
                before = spec.get('before')
                after = spec.get('after', True)  # True = present, saved when the imported map was left
                if state == STATE_AFTER:
                    present_now = after is not None
                    if present_now:
                        spec['after'] = capture(ob, owners.get(ob, []), scene.collection)
                    goal = before
                else:
                    present_now = before is not None
                    goal = spec.get('after')
                    if goal is True:
                        continue
                if goal is None:
                    if not present_now:
                        continue
                    first = owners[ob][0] if owners.get(ob) else None
                    cn = collection_colname(first, p.map_coll, parents, root_set) if first is not None else ''
                    parts = colname_parts(cn, p.map_coll.name if p.map_coll else '') if cn else ()
                    spec['stash'] = '/'.join(parts)
                    apply_absent(journal, ob, archive, zone, parts, owners)
                else:
                    missing += apply_present(journal, ob, goal, scene, fallback, owners)
                write_run(journal, ob, spec)
                changed += 1
                self.progress('Switching map state', n + 1, len(specs))
                yield
            journal.prop(archive, STATE_KEY)
            archive[STATE_KEY] = want
            context.view_layer.update()
        except BaseException as exc:
            self.progress('Rolling back', 0, len(journal.items))
            yield from journal.rollback()
            self._error = 'Rolled back. ' + (self._error or str(exc) or 'Operation failed.')
            raise
        note = f'; {missing} collections no longer exist (used Map instead)' if missing else ''
        self.result = f'{zone}: showing the {label} map ({changed} objects switched){note}'
