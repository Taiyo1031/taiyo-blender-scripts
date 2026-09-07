"""The panel displays settings and cached results only; never walks scene hierarchies."""
import textwrap
import bpy
from bpy.types import Panel
from . import state
from .definitions import RESTRICTIONS, KEYS, QUICK, PRESETS


def fold(layout, settings, field):
    row = layout.row()
    row.alignment = 'LEFT'
    row.prop(settings, field, icon='TRIA_DOWN' if getattr(settings, field) else 'TRIA_RIGHT', emboss=False)
    return getattr(settings, field)


def lines(layout, context, text):
    scale = getattr(context.preferences.system, 'ui_scale', context.preferences.view.ui_scale)
    width = max(18, int(((context.region.width if context.region else 320) - 40 * scale) / (7.5 * scale)))
    for line in textwrap.wrap(text, width=width):
        layout.label(text=line)


def run(layout, action, label, icon='PLAY'):
    op = layout.operator('hrm.run', text=label, icon=icon)
    op.action = action
    return op


def prepare(layout, action, label, icon='NONE'):
    op = layout.operator('hrm.settings', text=label, icon=icon)
    op.action = action
    return op


def refs(layout, entries):
    for item in entries:
        collection = item.collection
        if collection:
            op = layout.operator('hrm.target', text=collection.name, icon='OUTLINER_COLLECTION')
            op.action, op.name = 'NAMED', collection.name
            op.library = collection.library.filepath if collection.library else ''


class HRM_PT_main(Panel):
    bl_label = 'Hierarchy Restriction Manager'
    bl_idname = 'HRM_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Hierarchy'

    def draw(self, context):
        layout, settings = self.layout, context.scene.hrm_settings
        prefs = state.preferences(context)
        active = state.ACTIVE
        can_apply = context.mode == 'OBJECT'
        if not can_apply:
            lines(layout.box(), context, 'Switch to Object Mode to apply restrictions with Undo. Target and Preview remain available.')
        if active:
            box = layout.box()
            box.label(text='HRM — ' + ('Restoring' if active.canceling else 'Working'), icon='TIME')
            lines(box, context, active.stats.phase)
            box.label(text=f'Processed {active.stats.candidates:,} | Changed {active.stats.writes:,}')
            if active.waiting:
                box.label(text='Large Undo may use substantial RAM.', icon='INFO')
                op = box.operator('hrm.control', text='Confirm Apply', icon='CHECKMARK')
                op.action = 'CONFIRM'
            row = box.row()
            row.enabled = not active.canceling
            row.operator('hrm.control', text='Cancel & Restore', icon='CANCEL')
        body = layout.column()
        body.enabled = active is None
        box = body.box()
        box.label(text='Target', icon='OUTLINER_COLLECTION')
        row = box.row(align=True)
        row.prop(settings, 'target', text='')
        row.operator('hrm.target', text='', icon='SOLO_ON').action = 'FAVORITE'
        box.operator('hrm.target', text='Use Active Collection', icon='EYEDROPPER').action = 'ACTIVE'
        box.operator('hrm.target', text='Use Object Collection', icon='OBJECT_DATA').action = 'OBJECT'
        row = box.row(align=True)
        row.prop_search(settings, 'view_layer', context.scene, 'view_layers', text='Layer')
        prepare(row, 'CURRENT_LAYER', '', 'LOOP_BACK')
        if not settings.view_layer:
            box.label(text='Current View Layer: ' + context.view_layer.name)
        if fold(box, settings, 'show_target_extras'):
            box.label(text='Favorites')
            refs(box, settings.favorites)
            box.label(text='Recent Targets')
            refs(box, settings.recent)
        tools = body.column()
        tools.enabled = settings.target is not None and can_apply
        box = tools.box()
        box.label(text='Quick Actions — apply immediately', icon='PLAY')
        for left, right in [('SHOW', 'HIDE'), ('UNLOCK', 'LOCK'), ('RENDER_ON', 'RENDER_OFF')]:
            # One button per row stays legible in a narrow sidebar.
            run(box, left, QUICK[left][0], {'SHOW': 'HIDE_OFF', 'UNLOCK': 'RESTRICT_SELECT_OFF', 'RENDER_ON': 'RESTRICT_RENDER_OFF'}[left])
            run(box, right, QUICK[right][0], {'HIDE': 'HIDE_ON', 'LOCK': 'RESTRICT_SELECT_ON', 'RENDER_OFF': 'RESTRICT_RENDER_ON'}[right])
        box = body.box()
        scope = ', '.join(label for enabled, label in [(settings.include_root, 'Root'), (settings.child_collections, 'Child Collections'), (settings.objects, 'Objects')] if enabled) or 'Nothing'
        lines(box, context, 'Affect: ' + scope)
        box.label(text={'RECURSIVE': 'All descendant depths', 'DIRECT': 'Root + depth 1', 'DEPTH': f'Root through depth {settings.depth}'}[settings.traversal])
        if settings.use_filters:
            box.label(text='Filters Active', icon='FILTER')
        if fold(box, settings, 'show_scope'):
            for field in ('include_root', 'child_collections', 'objects', 'traversal'):
                box.prop(settings, field)
            if settings.traversal == 'DEPTH':
                box.prop(settings, 'depth')
        box = body.box()
        row = box.row()
        row.enabled = bool(settings.target) and can_apply
        run(row, 'SOLO', 'Solo Hierarchy', 'SOLO_ON')
        layer = context.scene.view_layers.get(settings.view_layer) if settings.view_layer else context.view_layer
        row = box.row()
        row.enabled = can_apply and bool(layer and state.SOLOS.get(state.solo_key(context.scene, layer)))
        run(row, 'RESTORE', 'Restore Solo', 'LOOP_BACK')
        box.prop(settings, 'solo_mode', text='Mode')
        if layer and state.SOLOS.get(state.solo_key(context.scene, layer)):
            lines(box, context, 'Solo active. Restore before saving if you want the original visibility in the saved file.')
        if settings.message:
            lines(body.box(), context, settings.message)
        if fold(body, settings, 'show_restrictions'):
            box = body.box()
            lines(box, context, 'Prepare changes, then Apply. Keep leaves each flag unchanged.')
            for definition in RESTRICTIONS:
                row = box.row()
                row.enabled = (settings.include_root or settings.child_collections or any(kind == 'O' for kind, _ in definition.targets) and settings.objects)
                if prefs.compact:
                    row.prop(settings, definition.key, text=definition.label, icon=definition.icon)
                else:
                    col = row.column(align=True)
                    col.label(text=definition.label + (' (Collections)' if len(definition.targets) == 1 else ''), icon=definition.icon)
                    col.row(align=True).prop(settings, definition.key, expand=True)
            row = box.row()
            row.enabled = can_apply and bool(settings.target) and any(getattr(settings, key) != 'KEEP' for key in KEYS)
            run(row, 'APPLY', 'Apply to Hierarchy', 'CHECKMARK')
            prepare(box, 'RESET', 'Reset Settings to Keep', 'LOOP_BACK')
            lines(box, context, 'Only stored flags change. An ancestor outside the target can still block visibility.')
        if fold(body, settings, 'show_filters'):
            box = body.box()
            box.prop(settings, 'use_filters')
            col = box.column()
            col.enabled = settings.use_filters
            for prefix, title in [('collection', 'Collection Names'), ('object', 'Object Names')]:
                col.label(text=title)
                col.prop(settings, prefix + '_match', text='Match')
                col.prop(settings, prefix + '_include')
                col.prop(settings, prefix + '_exclude')
            col.prop(settings, 'case_sensitive')
            col.label(text='Object Types (none = all)')
            col.prop(settings, 'object_types')
            col.prop(settings, 'branch_behavior')
        if fold(body, settings, 'show_presets'):
            box = body.box()
            box.label(text='Load Settings — then Apply')
            for action, (label, _) in PRESETS.items():
                prepare(box, action, label)
            run(box, 'MATCH', 'Match Root to Settings', 'COPYDOWN')
            run(box, 'COPY', 'Copy Root Restrictions', 'COPYDOWN')
            row = box.row()
            row.enabled = state.CLIPBOARD is not None
            prepare(row, 'PASTE', 'Paste to Settings', 'PASTEDOWN')
            if state.CLIPBOARD:
                lines(box, context, 'Copied: ' + state.CLIPBOARD['source'])
            box.separator()
            prepare(box, 'BROWSE', 'Browse Presets', 'PRESET')
            box.prop(settings, 'preset_name')
            box.prop(settings, 'preset_include_target')
            row = box.row(align=True)
            prepare(row, 'SAVE', 'Save')
            prepare(row, 'LOAD', 'Load')
            prepare(row, 'DELETE', 'Delete')
        if fold(body, settings, 'show_statistics'):
            box = body.box()
            box.prop(settings, 'statistics_detail')
            run(box, 'REFRESH', 'Refresh', 'FILE_REFRESH')
            preview = state.PREVIEWS.get(state.scene_key(context.scene))
            if preview:
                stats, detailed = preview
                if settings.dirty:
                    box.label(text='Statistics may be outdated', icon='ERROR')
                for label, count in [('Collections', stats.collections), ('Object Links', stats.object_links), ('Unique Objects', stats.objects)]:
                    box.label(text=f'{label}: {count:,}')
                if detailed:
                    box.label(text=f'Estimated items changed: {stats.modified:,}')
                    box.label(text=f'Estimated property changes: {stats.writes:,}')
                    for definition in RESTRICTIONS:
                        off, on = stats.distributions[definition.key]
                        label = 'Mixed' if off and on else 'All On' if on else 'All Off' if off else 'N/A'
                        box.label(text=f'{definition.label}: {label}')
                        box.label(text=f'   On {on:,} / Off {off:,}')
            else:
                box.label(text='Press Refresh to count the hierarchy')
        if fold(body, settings, 'show_performance'):
            box = body.box()
            if isinstance(prefs, bpy.types.AddonPreferences):
                for field in ('performance', 'compact', 'confirm_large', 'threshold', 'progress_interval', 'auto_refresh', 'show_timer', 'debug'):
                    box.prop(prefs, field)
            else:
                lines(box, context, 'Global options appear after installing the Extension.')
        if fold(body, settings, 'show_last'):
            stats = state.LAST.get(state.scene_key(context.scene))
            if stats:
                box = body.box()
                for label, field in [('Items changed', 'modified'), ('Properties changed', 'writes'), ('Unchanged properties', 'unchanged'), ('Read-only skipped', 'readonly'), ('Unavailable', 'missing'), ('Errors', 'errors')]:
                    box.label(text=f'{label}: {getattr(stats, field):,}')
                if prefs.show_timer:
                    box.label(text=f'Time: {stats.duration:.3f}s')
                for message in stats.messages:
                    lines(box, context, message)
                prepare(box, 'COPY_REPORT', 'Copy Report', 'COPYDOWN')


CLASSES = (HRM_PT_main,)
