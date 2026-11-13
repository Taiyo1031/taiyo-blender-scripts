import bpy
from .zones import zone_empties, zone_name

MAX_EMPTY_ROWS = 50


class MRT_PT_Zones(bpy.types.Panel):
    bl_label = 'Zones'
    bl_idname = 'MRT_PT_zones'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_order = -10

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'

        row = layout.row()
        row.prop(p, 'zone_choice', text='')
        row.operator('mrt.rename_zone', text='', icon='GREASEPENCIL')
        row.operator('mrt.new_zone', text='', icon='ADD')

        layout.prop(p, 'zone_scope', expand=True)
        if p.zone_scope == 'MAP':
            layout.prop(p, 'map_coll')

        if p.running:
            layout.progress(factor=p.progress, type='BAR', text='Working | ESC cancels')
        else:
            layout.label(text=p.status or ' ')


class MRT_PT_ZoneRange(bpy.types.Panel):
    bl_label = '1. Define Range'
    bl_idname = 'MRT_PT_zone_range'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_parent_id = 'MRT_PT_zones'
    bl_order = 1

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout
        layout.enabled = not p.running

        n = sum(ob.type == 'MESH' for ob in context.selected_objects)
        layout.label(text=f'Selected Meshes  {n}')

        row = layout.row()
        row.scale_y = 1.4
        row.operator('mrt.add_objects_to_zone', text='Add Selected Objects', icon='PIVOT_BOUNDBOX')

        layout.prop(p, 'merge_distance')

        row = layout.row(align=True)
        row.operator('mrt.add_zone_empty', text='Add Empty', icon='EMPTY_AXIS')
        row.operator('mrt.register_zone_empties', text='Register Selected Empties', icon='IMPORT')


class MRT_PT_ZoneEmpties(bpy.types.Panel):
    bl_label = 'Zone Empties'
    bl_idname = 'MRT_PT_zone_empties'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_parent_id = 'MRT_PT_zones'
    bl_order = 2
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout

        layout.prop(p, 'zone_empty_filter', icon='VIEWZOOM')
        layout.operator('mrt.select_zone_empties', text='Select Zone Empties', icon='RESTRICT_SELECT_OFF')

        # p.zone_choice rebuilds its enum items (a scan of every empty) on each read: read it once.
        choice = p.zone_choice
        empties = [(zone_name(e), e) for e in zone_empties(context.scene, p.zone_prefix)]
        if choice != 'ALL':
            empties = [item for item in empties if item[0] == choice]
        if p.zone_empty_filter:
            filter_lower = p.zone_empty_filter.lower()
            empties = [item for item in empties if filter_lower in item[1].name.lower()]
        empties.sort(key=lambda item: (item[0], item[1].name))

        shown_total = len(empties)
        displayed_empties = empties[:MAX_EMPTY_ROWS]
        rest = shown_total - MAX_EMPTY_ROWS

        layout.label(text=f'{shown_total} empties')

        if not displayed_empties:
            layout.label(text='No Empty. Add one or register one.', icon='INFO')
        else:
            count = 0
            previous_name = None

            for name, e in displayed_empties:
                # Show zone label when switching zones (for ALL mode only)
                if choice == 'ALL' and previous_name != name:
                    layout.label(text=name)
                    previous_name = name

                row = layout.row(align=True)
                row.enabled = e.is_editable
                op = row.operator('mrt.zone_empty_action', text=e.name, icon='EMPTY_AXIS')
                op.object_name, op.action = e.name, 'SELECT'
                row.prop(e, 'mrt_zone_operation', text='')
                op = row.operator('mrt.zone_empty_action', text='', icon='TRASH')
                op.object_name, op.action = e.name, 'UNREGISTER'

                count += 1
                if count >= MAX_EMPTY_ROWS:
                    break

            if rest > 0:
                layout.label(text=f'... and {rest} more. Use Search to narrow down.', icon='INFO')


class MRT_PT_ZoneCheck(bpy.types.Panel):
    bl_label = '2. Check'
    bl_idname = 'MRT_PT_zone_check'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_parent_id = 'MRT_PT_zones'
    bl_order = 3
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout

        layout.operator('mrt.select_in_zone', text='Select Meshes In Zone', icon='RESTRICT_SELECT_OFF')

        layout.label(text=p.zone_result or ' ')


class MRT_PT_ZoneCSV(bpy.types.Panel):
    bl_label = '3. Export CSV'
    bl_idname = 'MRT_PT_zone_csv'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_parent_id = 'MRT_PT_zones'
    bl_order = 4

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout

        layout.prop(p, 'zone_csv_dir')
        layout.prop(p, 'name_mode')

        row = layout.row()
        row.scale_y = 1.3
        choice = p.zone_choice  # one read: each read rebuilds the enum items
        if choice == 'ALL':
            text = 'Export CSV (every zone)'
        else:
            text = f'Export {choice}.csv'
        row.enabled = not p.running and choice != ''
        row.operator('mrt.export_zone_csv', text=text, icon='EXPORT')

        layout.label(text='Meshes inside the zone are exported. Selection is not used.')


class MRT_PT_ZoneAdvanced(bpy.types.Panel):
    bl_label = 'Advanced'
    bl_idname = 'MRT_PT_zone_advanced'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_parent_id = 'MRT_PT_zones'
    bl_order = 5
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout

        layout.prop(p, 'zone_prefix')
