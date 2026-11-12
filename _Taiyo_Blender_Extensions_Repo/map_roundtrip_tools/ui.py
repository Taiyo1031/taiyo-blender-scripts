import bpy
from .placement import effective_zone
from .constants import FBX_DEFAULTS


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
        for name in ('library_coll', 'map_coll', 'new_mesh_coll_name'):
            box.prop(p, name)
        box.label(text='New meshes go under Library, at the origin.')
        box = layout.box()
        box.label(text='Return Files')
        box.label(text='Return Folder is a reference, not an automatic import.')
        for name in ('return_dir', 'placement_csv', 'mesh_fbx', 'name_mode', 'if_exists'):
            box.prop(p, name)
        box = layout.box()
        box.label(text='Replace Zone')
        box.prop(p, 'zone_override')
        box.label(text=effective_zone(p) + (' from CSV name' if not p.zone_override else ''))
        box.prop(p, 'old_mode', expand=True)
        box.prop(p, 'dry_run')
        plan = box.box()
        if p.plan_ready:
            plan.label(text=f'{p.old_mode.title()} {p.plan_archive} objects tagged ub_zone={p.plan_zone}')
            if p.old_mode == 'ARCHIVE':
                plan.label(text='to _Replaced_' + p.plan_zone)
            plan.label(text=f'Create {p.plan_create} linked instances')
            plan.label(text=f'Invalid rows {p.plan_invalid}; new collections {p.plan_collections}')
            plan.label(text=f'New meshes (id -1): {p.plan_added}')
            if p.plan_unknown_id:
                row = plan.row()
                row.alert = True
                row.label(text=f'Skipped {p.plan_unknown_id} rows with an unknown id')
            if not p.plan_id_check:
                plan.label(text='ID check off: this zone has no ub_csv_id (exported by an older version)')
            if p.plan_missing:
                row = plan.row()
                row.alert = True
                row.label(text=f'{p.plan_missing} names not found in Library: {p.plan_names}')
        else:
            plan.label(text='Run Preview Placement to see the plan.')
        plan.label(text=f'Imported {p.plan_new_meshes_imported} meshes this session' if p.plan_new_meshes_imported else 'No meshes imported yet')
        box.operator('mrt.import_meshes')
        row = box.row()
        row.alert = p.old_mode == 'DELETE' and not p.dry_run
        row.operator('mrt.replace_zone', text='Preview Placement' if p.dry_run else 'Replace Zone')
