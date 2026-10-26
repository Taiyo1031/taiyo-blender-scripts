import bpy
from . import runtime as R
from .properties import TYPES
from .operations import ZG_Operator

class ZG_UL_groups(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True); row.prop(item,'color',text='')
        row.label(text='M' if item.source=='MANUAL' else 'V')
        row.prop(item,'name',text='',emboss=False)
        row.label(text=str(item.last_evaluated_count)+(' *' if item.dirty else ''))
        for field,icon in [('show','RESTRICT_VIEW'),('selectable','RESTRICT_SELECT')]:
            op=row.operator('zg.row_restriction',text='',icon=icon+('_OFF' if getattr(item,field) else '_ON'),emboss=False)
            op.uid=item.uid; op.field=field
class ZG_UL_volumes(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True); row.prop(item,'operation',text=''); row.prop(item,'controller',text='')
        if not item.controller: row.label(text='Missing',icon='ERROR')
class ZG_PT_main(bpy.types.Panel):
    bl_label='Groups'; bl_idname='ZG_PT_main'; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='Groups'
    def draw(self,context):
        layout=self.layout; s=context.scene.zg; rt=R.get(context.scene)
        layout.label(text='Taiyo Object Groups 1.0.0')
        if context.mode!='OBJECT': layout.label(text='Object Mode required',icon='INFO')
        if R.ACTIVE: layout.label(text=rt.progress or 'Updating… Esc to cancel',icon='TIME')
        if rt.warning: layout.label(text=rt.warning,icon='ERROR')
        layout.enabled=R.ACTIVE is None and context.mode=='OBJECT'
        if not s.groups:
            layout.label(text='No groups yet'); layout.operator('zg.group_new',icon='ADD'); return
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
        else: layout.label(text='Volume group: use Empty volumes in Members')
        row=layout.row(align=True)
        for mode,label in [('SET','Select'),('EXTEND','Extend'),('DESELECT','Deselect')]: row.operator('zg.select_members',text=label).mode=mode
        layout.operator('zg.select_groups_of_selection',icon='GROUP')
class ZG_PT_members(bpy.types.Panel):
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
        col=row.column(align=True); col.operator_menu_enum('zg.volume_add','shape',text='',icon='ADD')
        col.operator('zg.volume_remove',text='',icon='REMOVE'); col.separator(); col.operator('zg.fit_to_selection',text='',icon='SHADING_BBOX')
        if 0<=r.volume_index<len(r.volumes) and r.volumes[r.volume_index].controller:
            obj=r.volumes[r.volume_index].controller; box=layout.box()
            box.prop(obj,'empty_display_type',text='Shape'); box.prop(obj,'empty_display_size',text='Size'); box.prop(obj,'scale',text='Scale')
        layout.prop(r,'eval_mode',text='Test'); layout.label(text='Object Types'); row=layout.row(align=True)
        for t,icon in zip(TYPES,['OUTLINER_OB_MESH','OUTLINER_OB_LIGHT','OUTLINER_OB_CAMERA','OUTLINER_OB_CURVE','OUTLINER_OB_EMPTY','OBJECT_DATA']): row.prop(r,'t_'+t,text='',icon=icon,toggle=True)
        layout.prop(context.scene.zg,'fit_margin'); layout.label(text='Update Behavior'); layout.prop(g,'update_mode',expand=True)
        row=layout.row(); row.operator('zg.evaluate',icon='FILE_REFRESH'); row.label(text=f'{g.last_evaluated_count} members')
        if g.dirty: layout.label(text='Dirty: previous count; evaluation required',icon='INFO')
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
        layout.separator(); layout.operator('zg.color_toggle',text='Group Colors',depress=s.color_enabled,icon='COLOR')
        col=layout.column(); col.enabled=s.color_enabled; col.prop(s,'color_rule')
        if s.color_rule=='OVERLAP': col.prop(s,'overlap_color')
        layout.operator('zg.object_color',icon='SHADING_SOLID')
class ZG_OT_region_active(bpy.types.Operator):
    bl_idname='zg.region_active'; bl_label='Active Region'
    index:bpy.props.IntProperty()
    def execute(self,context):
        g=R.active(context.scene)
        if g and 0<=self.index<len(g.regions): g.active_region_index=self.index
        return {'FINISHED'}
class ZG_OT_row_restriction(ZG_Operator,bpy.types.Operator):
    bl_idname='zg.row_restriction'; bl_label='Group Restriction'; action='restriction'
    __annotations__=dict(ZG_Operator.__annotations__)
    uid:bpy.props.StringProperty()
    def work(self,context):
        s=context.scene.zg; previous=s.active_index
        match=next((i for i,g in enumerate(s.groups) if g.uid==self.uid),None)
        if match is None: raise ValueError('Group no longer exists')
        s.active_index=match
        yield from super().work(context)
        s.active_index=previous
CLASSES=(ZG_UL_groups,ZG_UL_volumes,ZG_PT_main,ZG_PT_members,ZG_PT_visibility,ZG_OT_region_active,ZG_OT_row_restriction)
