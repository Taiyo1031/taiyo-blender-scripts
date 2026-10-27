import bpy
from . import runtime as R
from .properties import TYPES
from .operations import ZG_Operator

class ZG_UL_groups(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True); row.prop(item,'color',text='')
        row.label(text='M' if item.source=='MANUAL' else 'V')
        row.prop(item,'name',text='',emboss=False)
        count=row.row(); count.ui_units_x=3; count.label(text=str(item.last_evaluated_count))
        status=row.row(); status.ui_units_x=1; status.label(text='',icon='TIME' if item.dirty else 'CHECKMARK')
        op=row.operator('zg.row_isolate',text='',icon='SOLO_ON' if data.isolate_uid==item.uid else 'SOLO_OFF',depress=data.isolate_uid==item.uid); op.uid=item.uid
        for field,icon in [('show','RESTRICT_VIEW'),('selectable','RESTRICT_SELECT')]:
            op=row.operator('zg.row_restriction',text='',icon=icon+('_OFF' if getattr(item,field) else '_ON'),emboss=False)
            op.uid=item.uid; op.field=field
class ZG_UL_volumes(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True); row.label(text='',icon='MESH_DATA' if item.kind=='MESH' else 'EMPTY_DATA'); row.prop(item,'operation',text=''); row.prop(item,'controller',text='')
        op=row.operator('zg.volume_select',text='',icon='RESTRICT_SELECT_OFF'); op.index=index
class ZG_PT_main(bpy.types.Panel):
    bl_label='Groups'; bl_idname='ZG_PT_main'; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='Groups'
    def draw(self,context):
        layout=self.layout; s=context.scene.zg; rt=R.get(context.scene)
        layout.label(text='Taiyo Object Groups 1.1.0')
        global_box=layout.box(); global_box.label(text='Global Settings / All Groups')
        controls=global_box.column(); controls.enabled=R.ACTIVE is None and context.mode=='OBJECT'
        controls.operator('zg.color_toggle',text='Group Colors',depress=s.color_enabled,icon='COLOR')
        controls.prop(s,'color_rule',text='Overlap')
        color=controls.row(); color.enabled=s.color_enabled and s.color_rule=='OVERLAP'; color.prop(s,'overlap_color')
        controls.operator('zg.object_color',icon='SHADING_SOLID'); controls.operator('zg.show_all')
        status=layout.row(align=True)
        status.label(text='Updating…' if R.ACTIVE else ('Object Mode required' if context.mode!='OBJECT' else 'Ready'),icon='TIME' if R.ACTIVE else 'INFO')
        cancel=status.row(); cancel.enabled=R.ACTIVE is not None; cancel.operator('zg.cancel_job',text='',icon='CANCEL')
        detail=layout.row(); detail.label(text='Warning: see details' if rt.warning else 'No warnings',icon='ERROR' if rt.warning else 'CHECKMARK'); detail.operator('zg.status_details',text='',icon='INFO')

        layout=layout.column()
        layout.enabled=R.ACTIVE is None and context.mode=='OBJECT'
        create=layout.row(align=True); create.operator('zg.group_new',text='New')
        selected=create.row(); selected.enabled=bool(context.selected_objects); selected.operator('zg.group_from_selection',text='From Selection')
        if not s.groups:
            layout.label(text='No groups yet'); return
        row=layout.row(); row.template_list('ZG_UL_groups','',s,'groups',s,'active_index',rows=6)
        col=row.column(align=True); col.operator('zg.group_new',text='',icon='ADD'); col.operator('zg.group_remove',text='',icon='REMOVE')
        col.separator(); col.operator('zg.group_duplicate',text='',icon='DUPLICATE'); col.separator()
        col.operator('zg.group_move',text='',icon='TRIA_UP').direction='UP'
        col.operator('zg.group_move',text='',icon='TRIA_DOWN').direction='DOWN'
        g=R.active(context.scene)
        if not g: return
        row=layout.row(align=True); row.operator('zg.group_duplicate',icon='DUPLICATE')
        merge=row.row(); merge.enabled=any(x.uid!=g.uid and x.source==g.source for x in s.groups)
        merge.operator('zg.group_merge',icon='MOD_BOOLEAN')
        box=layout.box(); box.label(text=f'Active: {g.name} [{g.source.title()}]')
        box.label(text=f'Selected: {rt.selected_count} object(s)'); box.label(text=rt.selection_label)
        if g.source=='MANUAL':
            row=layout.row(align=True); row.operator('zg.add_selected'); row.operator('zg.remove_selected')
        else: layout.label(text='Volume references: open Members below')
        row=layout.row(align=True)
        for mode,label in [('SET','Select'),('EXTEND','Extend'),('DESELECT','Deselect')]: row.operator('zg.select_members',text=label).mode=mode
        layout.operator('zg.select_groups_of_selection',icon='GROUP')
class ZG_PT_members(bpy.types.Panel):
    bl_options={'DEFAULT_CLOSED'}
    bl_label='Members'; bl_idname='ZG_PT_members'; bl_parent_id='ZG_PT_main'
    bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='Groups'
    @classmethod
    def poll(cls,context): return R.active(context.scene) is not None
    def draw(self,context):
        layout=self.layout; g=R.active(context.scene); layout.enabled=R.ACTIVE is None and context.mode=='OBJECT'
        layout.label(text='Membership Mode'); row=layout.row(align=True)
        for value in ('MANUAL','VOLUME'): row.operator('zg.membership_mode',text=value.title(),depress=g.source==value).value=value
        if g.source=='MANUAL':
            layout.label(text=f'{g.last_evaluated_count} members'); layout.label(text='Use Add Selected / Remove Selected above'); return
        if not g.regions: return
        if len(g.regions)>1:
            layout.label(text='Regions combine with OR')
            row=layout.row(align=True)
            for i,r in enumerate(g.regions): row.operator('zg.region_active',text=f'Region {i+1}',depress=i==g.active_region_index).index=i
        r=g.regions[min(max(g.active_region_index,0),len(g.regions)-1)]
        row=layout.row(); row.template_list('ZG_UL_volumes','',r,'volumes',r,'volume_index',rows=3)
        col=row.column(align=True); col.menu('ZG_MT_add_volume',text='',icon='ADD')
        col.operator('zg.volume_remove',text='',icon='REMOVE'); col.separator(); col.operator('zg.fit_to_selection',text='',icon='SHADING_BBOX')
        if 0<=r.volume_index<len(r.volumes) and r.volumes[r.volume_index].controller:
            obj=r.volumes[r.volume_index].controller; box=layout.box()
            if obj.type=='EMPTY':
                row=box.row(align=True)
                for shape,label in [('CUBE','Box'),('SPHERE','Sphere')]:
                    op=row.operator('zg.volume_shape',text=label,depress=obj.empty_display_type==shape); op.shape=shape
                box.prop(obj,'empty_display_size',text='Size')
            else: box.label(text='Raw Mesh; modifiers ignored')
            box.prop(obj,'scale',text='Scale')
        if any(v.kind=='MESH' for v in r.volumes):
            row=layout.row(align=True)
            for value,label in [('ORIGIN','Origin'),('BOUNDS_CENTER','Bounds Center')]:
                row.operator('zg.mesh_test',text=label,depress=r.eval_mode==value).value=value
        else: layout.prop(r,'eval_mode',text='Test')
        layout.label(text='Object Types'); row=layout.row(align=True)
        for t,icon in zip(TYPES,['OUTLINER_OB_MESH','OUTLINER_OB_LIGHT','OUTLINER_OB_CAMERA','OUTLINER_OB_CURVE','OUTLINER_OB_EMPTY','OBJECT_DATA']): row.prop(r,'t_'+t,text='',icon=icon,toggle=True)
        layout.prop(context.scene.zg,'fit_margin'); layout.label(text='Update Behavior'); layout.prop(g,'update_mode',expand=True)
        row=layout.row(); row.operator('zg.evaluate',icon='FILE_REFRESH'); row.label(text=f'{g.last_evaluated_count} members')
        layout.label(text='Dirty: previous count' if g.dirty else 'Membership up to date',icon='TIME' if g.dirty else 'CHECKMARK')
class ZG_PT_visibility(bpy.types.Panel):
    bl_label='Visibility'; bl_idname='ZG_PT_visibility'; bl_parent_id='ZG_PT_main'
    bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='Groups'; bl_options={'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls,context): return R.active(context.scene) is not None
    def draw(self,context):
        layout=self.layout; g=R.active(context.scene); s=context.scene.zg
        layout.enabled=R.ACTIVE is None and context.mode=='OBJECT'; row=layout.row(align=True)
        for field,label in [('show','Viewport'),('selectable','Select'),('render','Render')]: row.operator('zg.restriction',text=label,depress=getattr(g,field)).field=field
        row=layout.row(align=True); row.operator('zg.isolate',depress=bool(s.isolate_uid)); row.operator('zg.show_all')
class ZG_OT_region_active(bpy.types.Operator):
    bl_description='Choose the Region to edit; independent Regions combine with OR'
    bl_idname='zg.region_active'; bl_label='Active Region'
    index:bpy.props.IntProperty()
    def execute(self,context):
        g=R.active(context.scene)
        if g and 0<=self.index<len(g.regions): g.active_region_index=self.index
        return {'FINISHED'}
class ZG_OT_row_restriction(ZG_Operator,bpy.types.Operator):
    bl_description='Toggle this row group viewport or selection restriction; membership in another restricted group still restricts the Object'
    bl_idname='zg.row_restriction'; bl_label='Group Restriction'; action='restriction'
    __annotations__=dict(ZG_Operator.__annotations__)
    uid:bpy.props.StringProperty()
    def work(self,context):
        s=context.scene.zg; previous=s.active_index
        match=next((i for i,g in enumerate(s.groups) if g.uid==self.uid),None)
        if match is None: raise ValueError('Group no longer exists')
        s.active_index=match
        try: yield from super().work(context)
        finally: s.active_index=previous

class ZG_MT_add_volume(bpy.types.Menu):
    bl_label='Add Volume'
    def draw(self,context):
        for shape,label in [('CUBE','Empty Box'),('SPHERE','Empty Sphere')]:
            self.layout.operator('zg.volume_add',text=label).shape=shape
        self.layout.operator('zg.volume_mesh')

class ZG_OT_row_isolate(ZG_Operator,bpy.types.Operator):
    bl_idname='zg.row_isolate'; bl_label='Isolate Group'; action='isolate'
    bl_description='Show only this row group; click again to restore or another row to switch'
    __annotations__={**ZG_Operator.__annotations__,**ZG_OT_row_restriction.__annotations__}
    def work(self,context):
        s=context.scene.zg; previous=s.active_index
        match=next((i for i,g in enumerate(s.groups) if g.uid==self.uid),None)
        if match is None: raise ValueError('Group no longer exists')
        s.active_index=match
        try: yield from ZG_Operator.work(self,context)
        finally: s.active_index=previous

class ZG_OT_volume_select(bpy.types.Operator):
    bl_idname='zg.volume_select'; bl_label='Select Volume Object'
    bl_description='Select this Volume controller in the current View Layer; hidden or locked Objects are not modified'
    bl_options={'REGISTER','UNDO'}
    index:bpy.props.IntProperty(description='Volume row to select')
    @classmethod
    def poll(cls,context): return context.mode=='OBJECT' and R.ACTIVE is None
    def execute(self,context):
        g=R.active(context.scene)
        if not g: return {'CANCELLED'}
        r=R.region(g)
        obj=r.volumes[self.index].controller if 0<=self.index<len(r.volumes) else None
        reason=('Missing Volume reference' if not obj else
                'Volume is outside this View Layer' if obj.name not in context.view_layer.objects else
                'Volume is locked for selection' if obj.hide_select else
                'Volume is hidden' if not obj.visible_get(view_layer=context.view_layer) else '')
        if reason: self.report({'WARNING'},reason); return {'CANCELLED'}
        for selected in context.selected_objects: selected.select_set(False)
        obj.select_set(True); context.view_layer.objects.active=obj; r.volume_index=self.index
        return {'FINISHED'}

class ZG_OT_volume_shape(bpy.types.Operator):
    bl_idname='zg.volume_shape'; bl_label='Volume Shape'
    bl_description='Set the selected Empty Volume to a supported Box or Sphere shape'
    bl_options={'REGISTER','UNDO'}
    shape:bpy.props.EnumProperty(items=[('CUBE','Box','Box Volume'),('SPHERE','Sphere','Sphere Volume')])
    @classmethod
    def poll(cls,context): return context.mode=='OBJECT' and R.ACTIVE is None
    def execute(self,context):
        g=R.active(context.scene)
        if not g:return {'CANCELLED'}
        r=R.region(g)
        if not 0<=r.volume_index<len(r.volumes):return {'CANCELLED'}
        obj=r.volumes[r.volume_index].controller
        if not obj or obj.type!='EMPTY':return {'CANCELLED'}
        obj.empty_display_type=self.shape; R.invalidate(context.scene)
        return {'FINISHED'}

class ZG_OT_mesh_test(bpy.types.Operator):
    bl_idname='zg.mesh_test'; bl_label='Mesh Membership Test'
    bl_description='Use the Object origin or original bounding-box center for closed Mesh containment'
    bl_options={'REGISTER','UNDO'}
    value:bpy.props.EnumProperty(items=[('ORIGIN','Origin','Object origin'),('BOUNDS_CENTER','Bounds Center','Original bounding-box center')])
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and R.ACTIVE is None
    def execute(self,context):
        g=R.active(context.scene)
        if not g:return {'CANCELLED'}
        R.region(g).eval_mode=self.value
        return {'FINISHED'}

class ZG_OT_cancel_job(bpy.types.Operator):
    bl_idname='zg.cancel_job'; bl_label='Cancel Update'
    bl_description='Cancel the running operation and restore its settings and applied changes; Esc also cancels'
    def execute(self,context):
        if R.ACTIVE:R.ACTIVE.cancel_requested=True
        return {'FINISHED'}

class ZG_OT_status_details(bpy.types.Operator):
    bl_idname='zg.status_details'; bl_label='Update Details'
    bl_description='Show complete update progress and warnings without resizing the main panel'
    def execute(self,context):return {'FINISHED'}
    def invoke(self,context,event):return context.window_manager.invoke_popup(self,width=500)
    def draw(self,context):
        import textwrap
        rt=R.get(context.scene)
        for message in (rt.progress or 'No update in progress',rt.warning or 'No warnings'):
            for line in textwrap.wrap(message,70):self.layout.label(text=line)

CLASSES=(ZG_UL_groups,ZG_UL_volumes,ZG_MT_add_volume,ZG_PT_main,ZG_PT_members,ZG_PT_visibility,
         ZG_OT_region_active,ZG_OT_row_restriction,ZG_OT_row_isolate,ZG_OT_volume_select,
         ZG_OT_volume_shape,ZG_OT_mesh_test,ZG_OT_cancel_job,ZG_OT_status_details)
