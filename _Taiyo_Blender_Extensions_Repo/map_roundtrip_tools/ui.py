import bpy
from . import placement_report
from .placement import effective_zone
from .constants import FBX_DEFAULTS
from .journal import STATE_AFTER, STATE_BEFORE, map_state

MAX_ISSUE_ROWS = 5


class MRT_PT_Export(bpy.types.Panel):
    bl_label = 'Export'
    bl_idname = 'MRT_PT_export'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        col = layout.column()
        col.enabled = not p.running
        box = col.box()
        box.label(text='Paths')
        box.prop(p, 'exchange_dir')
        box.label(text='Reference only; set actual file paths separately.', icon='INFO')
        box.prop(p, 'zone_name')
        box.label(text='Zone selection and CSV: use the Zones panel above.')
        box = col.box()
        box.label(text='FBX Export')
        box.label(text=f'Selected Meshes  {sum(ob.type == "MESH" for ob in context.selected_objects)}')
        box.operator('mrt.export_fbx_native', icon='EXPORT')
        box.label(text='Settings and presets open in Blender file browser.')
        col.prop(p, 'show_batch_export', icon='TRIA_DOWN' if p.show_batch_export else 'TRIA_RIGHT', emboss=False)
        if p.show_batch_export:
            box = col.box()
            box.label(text='FBX Export')
            box.prop(p, 'fbx_preset')
            row = box.row(align=True)
            row.operator('mrt.save_preset', text='', icon='ADD')
            row.operator('mrt.delete_preset', text='', icon='X')
            box.label(text=f'Selected Meshes  {sum(ob.type == "MESH" for ob in context.selected_objects)}')
            box.prop(p, 'fbx_files', expand=True)
            box.prop(p, 'fbx_out_dir')
            box = col.box()
            box.label(text='Advanced')
            for key in FBX_DEFAULTS:
                if key == 'fbx_axis_forward':
                    row = box.row(align=True)
                    row.prop(p, key)
                    row.prop(p, 'fbx_axis_up')
                elif key != 'fbx_axis_up':
                    box.prop(p, key)
            col.operator('mrt.export_fbx')
            col.label(text='Last export: ' + p.last_export)
        if p.status:
            layout.label(text=p.status)
        if p.running:
            layout.progress(factor=p.progress, type='BAR', text='Working | ESC cancels')


class MRT_PT_Import(bpy.types.Panel):
    bl_label = 'Import'
    bl_idname = 'MRT_PT_import'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        layout.enabled = not p.running
        box = layout.box()
        box.label(text='Collections')
        for name in ('library_coll', 'map_coll', 'new_mesh_coll', 'archive_coll'):
            box.prop(p, name)
        box.label(text='New meshes go to New Meshes To (default: below Library).')
        box.label(text='Objects with use = 0 in the CSV go to _Replaced_<Zone> in Archive To (default: scene root).')
        box = layout.box()
        box.label(text='Return Files')
        box.label(text='Return Folder is a reference, not an automatic import.')
        for name in ('return_dir', 'placement_csv', 'mesh_fbx', 'convert_houdini_fbx', 'name_mode', 'if_exists'):
            box.prop(p, name)
        box = layout.box()
        box.label(text='Replace Zone')
        box.prop(p, 'zone_override')
        zone = effective_zone(p)
        box.label(text=zone + (' from CSV name' if not p.zone_override else ''))
        box.prop(p, 'dry_run')
        box.operator('mrt.import_meshes')
        state = map_state(zone)
        row = box.row()
        row.enabled = state != STATE_BEFORE
        row.operator('mrt.replace_zone', text='Preview Placement' if p.dry_run else 'Replace Zone')
        if state:
            showing_imported = state == STATE_AFTER
            box.label(text='Map shows: ' + ('the imported map' if showing_imported else 'the ORIGINAL map (Replace is off)'))
            op = box.operator('mrt.switch_map_state', text='Restore Original Map' if showing_imported else 'Re-apply Imported Map')
            op.target = 'BEFORE' if showing_imported else 'AFTER'
            op.zone = zone
        plan = box.box()
        if p.plan_ready:
            plan.label(text=f'Unchanged {p.plan_unchanged}; Moved {p.plan_moved}' + (f' (incl. {p.plan_resurrected} brought back from the archive)' if p.plan_resurrected else ''))
            plan.label(text=f'Retire {p.plan_archive} (use 0: {p.plan_unused_rows} rows) to _Replaced_{p.plan_zone}; Add {p.plan_create}')
            plan.label(text=f'Not in CSV, left as they are: {p.plan_not_in_csv}')
            plan.label(text=f'Invalid rows {p.plan_invalid}; new collections {p.plan_collections}')
            plan.label(text=f'New meshes (id -1): {p.plan_added} of {p.plan_new_rows} rows')
            if p.plan_new_rows > p.plan_added:
                row = plan.row()
                row.alert = True
                row.label(text=f'{p.plan_new_rows - p.plan_added} new mesh rows are not in Library yet: run Import New Meshes')
            if p.plan_unknown_id:
                row = plan.row()
                row.alert = True
                row.label(text=f'Skipped {p.plan_unknown_id} rows with an unknown id')
            if p.plan_missing:
                row = plan.row()
                row.alert = True
                row.label(text=f'{p.plan_missing} names not found in Library: {p.plan_names}')
            if p.plan_errors or p.plan_warnings:
                row = plan.row()
                row.alert = bool(p.plan_errors)
                row.label(text=f'{p.plan_errors} errors (row not used), {p.plan_warnings} warnings')
                for message in placement_report.first_lines(placement_report.LAST_ISSUES, MAX_ISSUE_ROWS):
                    plan.label(text=message if len(message) <= 110 else message[:107] + '...')
                plan.label(text=f'Full list: Text "{placement_report.REPORT_TEXT}"')
        else:
            plan.label(text='Run Preview Placement to see the plan.')
        plan.label(text=f'Imported {p.plan_new_meshes_imported} meshes this session' if p.plan_new_meshes_imported else 'No meshes imported yet')
