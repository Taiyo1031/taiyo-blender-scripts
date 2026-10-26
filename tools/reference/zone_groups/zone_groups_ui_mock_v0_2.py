bl_info = {
    "name": "Zone Groups (UI Mock v0.2)",
    "author": "OpenAI / prototype based on previous LG mock",
    "version": (0, 2, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar (N) > Groups",
    "description": "Collection-less group manager UI prototype: Manual/Volume, Duplicate, same-mode Merge",
    "category": "Object",
}

"""ZONE GROUPS — UI PROTOTYPE, NOT A PRODUCTION GROUP MANAGER.

Blender 4.5.10+ targeted (bl_info uses the minimum supported 4.5 series).

WORKS FOR THIS UI DEMO:
    * Add, remove, rename, reorder, duplicate and merge group *records*.
    * Merge dialog only lists groups with the SAME source mode as the active group.
    * Duplicate copies the chosen group's settings; Volume Empty objects are
      duplicated so their shapes can be edited independently.
    * Same-mode Merge adds the source's volume references to the destination
      and deletes only the source GROUP RECORD (not its Empty objects).
    * Add/remove actual Blender Empty volumes to/from group records.
    * Change color, source mode, UI settings and list rows.

MOCK ONLY / NOT IMPLEMENTED:
    * Real object group membership, Manual Add/Remove Selected and selection.
    * Volume intersection / containment evaluation, and membership counters.
    * Actual viewport/render visibility, selection lock and Isolate.
    * Group merge semantics for boolean ADD/EXCLUDE volumes; concatenation is
      for the UI demo and MUST NOT be assumed to give a correct spatial union.
    * Update mode watchers, performance optimization, undo for simulation.

No CSV/file export; no BOTH mode. Does not create grouping Collections.
"""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList


# -----------------------------------------------------------------------------
# Data model — scene-owned UI records only. No actual object membership yet.
# -----------------------------------------------------------------------------


def _poll_empty(_self, obj):
    return obj is not None and obj.type == 'EMPTY'


class LG_VolumeItem(PropertyGroup):
    obj: PointerProperty(
        name="Empty",
        type=bpy.types.Object,
        poll=_poll_empty,
    )
    op: EnumProperty(
        name="Operation",
        items=[
            ('ADD', "Add", "Include this volume", 'ADD', 0),
            ('EXCLUDE', "Exclude", "Subtract this volume", 'REMOVE', 1),
        ],
        default='ADD',
    )


class LG_GroupItem(PropertyGroup):
    name: StringProperty(name="Group Name", default="Group")
    color: FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, min=0.0, max=1.0,
        default=(0.90, 0.50, 0.20),
    )
    show: BoolProperty(name="Viewport", default=True,
                       description="UI preview only; object visibility is not implemented")
    selectable: BoolProperty(name="Selectable", default=True,
                             description="UI preview only; selection lock is not implemented")
    render: BoolProperty(name="Render", default=True,
                         description="UI preview only; render visibility is not implemented")
    member_count: IntProperty(name="Preview Count", default=0, min=0,
                              description="Mock data only; NOT a real membership count")
    dirty: BoolProperty(name="Needs Update", default=False,
                        description="UI marker only; no automatic detection implemented")
    source: EnumProperty(
        name="Membership",
        description="How this group determines its members",
        items=[
            ('MANUAL', "Manual", "Membership assigned explicitly"),
            ('VOLUME', "Volume", "Membership determined from Empty volumes"),
        ],
        default='MANUAL',
    )
    eval_mode: EnumProperty(
        name="Test",
        items=[
            ('ORIGIN', "Origin", "Test the object's origin"),
            ('BOUNDS_CENTER', "Bounds Center", "Test the bounding-box center"),
            ('FULLY_INSIDE', "Fully Inside", "Entire bounding box inside the volume"),
            ('ANY_OVERLAP', "Any Overlap", "Any overlap with the volume"),
        ],
        default='ORIGIN',
    )
    update_mode: EnumProperty(
        name="Update Behavior",
        items=[
            ('MANUAL', "Manual", "Only update when Evaluate is pressed"),
            ('DIRTY', "On Demand", "Mark dirty until a requested evaluation"),
            ('LIVE', "Live", "Re-evaluate automatically"),
        ],
        default='DIRTY',
    )
    t_mesh: BoolProperty(name="Mesh", default=True)
    t_light: BoolProperty(name="Light", default=True)
    t_camera: BoolProperty(name="Camera", default=True)
    t_curve: BoolProperty(name="Curve", default=True)
    t_empty: BoolProperty(name="Empty", default=True)
    t_other: BoolProperty(name="Other", default=True)
    volumes: CollectionProperty(type=LG_VolumeItem)
    volume_index: IntProperty(default=0, min=0)


GROUP_SETTINGS = (
    'color', 'show', 'selectable', 'render', 'member_count', 'dirty',
    'source', 'eval_mode', 'update_mode',
    't_mesh', 't_light', 't_camera', 't_curve', 't_empty', 't_other',
)


def active_group(context):
    scene = context.scene
    index = scene.lg_active_index
    if 0 <= index < len(scene.lg_groups):
        return scene.lg_groups[index]
    return None


def unique_group_name(scene, proposed):
    names = {g.name for g in scene.lg_groups}
    if proposed not in names:
        return proposed
    number = 2
    while f"{proposed}.{number:03d}" in names:
        number += 1
    return f"{proposed}.{number:03d}"


def copy_group_settings(src, dest):
    for prop in GROUP_SETTINGS:
        setattr(dest, prop, getattr(src, prop))


def _link_new_empty(context, obj):
    # Linking an Object to an EXISTING Blender collection is necessary to make
    # the Empty visible in the scene. The add-on does not create collections.
    target = context.collection or context.scene.collection
    target.objects.link(obj)


# Dynamic enum uses stable global storage: Blender stores string references.
_MERGE_ITEM_CACHE = []


def _merge_candidates(_operator, context):
    global _MERGE_ITEM_CACHE
    if context is None or active_group(context) is None:
        _MERGE_ITEM_CACHE = [("NONE", "No compatible groups", "", 0)]
        return _MERGE_ITEM_CACHE
    scene = context.scene
    current = scene.lg_active_index
    current_mode = scene.lg_groups[current].source
    _MERGE_ITEM_CACHE = [
        (f"IDX_{index}", f"{group.name} ({group.source.title()})",
         "Merge this group into the active group", index)
        for index, group in enumerate(scene.lg_groups)
        if index != current and group.source == current_mode
    ]
    if not _MERGE_ITEM_CACHE:
        _MERGE_ITEM_CACHE = [("NONE", "No compatible groups", "", 0)]
    return _MERGE_ITEM_CACHE


def has_compatible_merge_group(context):
    group = active_group(context)
    if group is None:
        return False
    scene = context.scene
    return any(
        other.source == group.source and i != scene.lg_active_index
        for i, other in enumerate(scene.lg_groups)
    )


# -----------------------------------------------------------------------------
# Operators: real GROUP RECORD modifications for mock UI demonstration
# -----------------------------------------------------------------------------


class LG_OT_group_new(Operator):
    bl_idname = "lg.group_new"
    bl_label = "New Group"
    bl_description = "Create a new group record"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        name = unique_group_name(scene, "Group")
        group = scene.lg_groups.add()
        group.name = name
        scene.lg_active_index = len(scene.lg_groups) - 1
        return {'FINISHED'}


class LG_OT_group_remove(Operator):
    bl_idname = "lg.group_remove"
    bl_label = "Remove Group"
    bl_description = "Delete the active group record; do not delete any scene objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_group(context) is not None

    def execute(self, context):
        scene = context.scene
        index = scene.lg_active_index
        scene.lg_groups.remove(index)
        scene.lg_active_index = max(0, min(index, len(scene.lg_groups) - 1))
        return {'FINISHED'}


class LG_OT_group_move(Operator):
    bl_idname = "lg.group_move"
    bl_label = "Move Group"
    bl_description = "Change group list order"
    bl_options = {'REGISTER', 'UNDO'}

    direction: EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")])

    @classmethod
    def poll(cls, context):
        return active_group(context) is not None

    def execute(self, context):
        scene = context.scene
        i = scene.lg_active_index
        j = i - 1 if self.direction == 'UP' else i + 1
        if 0 <= j < len(scene.lg_groups):
            scene.lg_groups.move(i, j)
            scene.lg_active_index = j
        return {'FINISHED'}


class LG_OT_group_duplicate(Operator):
    bl_idname = "lg.group_duplicate"
    bl_label = "Duplicate Group"
    bl_description = "Duplicate the active group, settings and volume Empties (UI mock)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_group(context) is not None

    def execute(self, context):
        scene = context.scene
        original = active_group(context)
        # Resolve name BEFORE inserting the new group.
        new_name = unique_group_name(scene, original.name + " Copy")
        duplicate = scene.lg_groups.add()
        duplicate.name = new_name
        copy_group_settings(original, duplicate)

        if original.source == 'VOLUME':
            for vol in original.volumes:
                new_vol = duplicate.volumes.add()
                new_vol.op = vol.op
                if vol.obj is not None:
                    # Independent Empty: modifications do not affect original.
                    empty_copy = vol.obj.copy()
                    empty_copy.name = f"Vol_{new_name}"
                    _link_new_empty(context, empty_copy)
                    new_vol.obj = empty_copy
            duplicate.volume_index = min(
                original.volume_index, max(0, len(duplicate.volumes) - 1)
            )
        scene.lg_active_index = len(scene.lg_groups) - 1
        self.report({'INFO'}, f"Created mock duplicate: {new_name}")
        return {'FINISHED'}


class LG_OT_group_merge(Operator):
    bl_idname = "lg.group_merge"
    bl_label = "Merge Groups"
    bl_description = "Merge another group of the SAME mode into the active group"
    bl_options = {'REGISTER', 'UNDO'}

    target_group: EnumProperty(
        name="Merge From",
        description="Only groups with the same Manual/Volume mode appear",
        items=_merge_candidates,
    )

    @classmethod
    def poll(cls, context):
        return has_compatible_merge_group(context)

    def invoke(self, context, _event):
        choices = [item[0] for item in _merge_candidates(self, context)
                   if item[0] != 'NONE']
        if not choices:
            self.report({'WARNING'}, "No other group with the same mode")
            return {'CANCELLED'}
        self.target_group = choices[0]
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        target = active_group(context)
        layout.label(text=f"Destination: {target.name} [{target.source.title()}]")
        layout.prop(self, "target_group")
        layout.separator()
        layout.label(text="Source group record will be removed.", icon='INFO')
        layout.label(text="Objects and Empty volumes are NOT deleted.")
        if target.source == 'VOLUME':
            layout.label(text="Spatial membership merge is not implemented.", icon='ERROR')

    def execute(self, context):
        scene = context.scene
        dest_idx = scene.lg_active_index
        try:
            src_idx = int(self.target_group.removeprefix("IDX_"))
        except (TypeError, ValueError, AttributeError):
            self.report({'ERROR'}, "Choose a valid source group")
            return {'CANCELLED'}
        if (src_idx == dest_idx
                or not (0 <= src_idx < len(scene.lg_groups))
                or not (0 <= dest_idx < len(scene.lg_groups))):
            self.report({'ERROR'}, "Invalid merge target")
            return {'CANCELLED'}

        dest = scene.lg_groups[dest_idx]
        src = scene.lg_groups[src_idx]
        if dest.source != src.source:
            self.report({'ERROR'}, "Merge requires matching modes: Manual+Manual or Volume+Volume")
            return {'CANCELLED'}

        # PREVIEW COUNTS ONLY. Real membership is intentionally not implemented.
        dest.member_count += src.member_count
        dest.dirty = dest.dirty or src.dirty
        if dest.source == 'VOLUME':
            # NOTE: For true spatial membership semantics, merely appending
            # ADD/EXCLUDE records is not a generally correct boolean union.
            # This is for checking the mock layout and button workflow only.
            for vol in src.volumes:
                new_vol = dest.volumes.add()
                new_vol.obj = vol.obj
                new_vol.op = vol.op
            dest.dirty = True

        src_name = src.name
        dest_name = dest.name
        scene.lg_groups.remove(src_idx)
        scene.lg_active_index = dest_idx - (1 if src_idx < dest_idx else 0)
        self.report({'INFO'}, f"Mock merge complete: {src_name} -> {dest_name}")
        return {'FINISHED'}


class LG_OT_dummy_data(Operator):
    bl_idname = "lg.dummy_data"
    bl_label = "Create Demo Groups"
    bl_description = "Create sample Manual and Volume groups to preview the UI"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.scene.lg_groups) == 0

    def execute(self, context):
        scene = context.scene
        # Mock member_count values are DISPLAY EXAMPLES, not memberships.
        samples = [
            ("階段エリア", 'VOLUME', (0.90, 0.50, 0.20), 128, True),
            ("廊下", 'VOLUME', (0.30, 0.70, 0.90), 342, False),
            ("教室A", 'MANUAL', (0.40, 0.80, 0.40), 87, False),
            ("教室B", 'MANUAL', (0.80, 0.40, 0.70), 64, False),
            ("ライト一式", 'MANUAL', (0.95, 0.85, 0.30), 23, False),
        ]
        for name, mode, color, count, dirty in samples:
            g = scene.lg_groups.add()
            g.name, g.source, g.color = name, mode, color
            g.member_count, g.dirty = count, dirty
        scene.lg_active_index = 0
        return {'FINISHED'}


class LG_OT_volume_add(Operator):
    bl_idname = "lg.volume_add"
    bl_label = "Add Volume"
    bl_description = "Create an Empty at the 3D cursor and link it to this group"
    bl_options = {'REGISTER', 'UNDO'}

    shape: EnumProperty(
        name="Shape",
        items=[
            ('CUBE', "Box", "Box volume", 'MESH_CUBE', 0),
            ('SPHERE', "Sphere", "Sphere volume", 'MESH_UVSPHERE', 1),
        ],
        default='CUBE',
    )

    @classmethod
    def poll(cls, context):
        g = active_group(context)
        return g is not None and g.source == 'VOLUME'

    def execute(self, context):
        group = active_group(context)
        empty = bpy.data.objects.new(f"Vol_{group.name}", None)
        empty.empty_display_type = self.shape
        empty.empty_display_size = 1.0
        empty.location = context.scene.cursor.location
        _link_new_empty(context, empty)
        item = group.volumes.add()
        item.obj = empty
        group.volume_index = len(group.volumes) - 1
        group.dirty = True
        return {'FINISHED'}


class LG_OT_volume_remove(Operator):
    bl_idname = "lg.volume_remove"
    bl_label = "Remove Volume Reference"
    bl_description = "Unlink the selected volume from the group; preserve the Empty object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        g = active_group(context)
        return (g is not None and g.source == 'VOLUME'
                and 0 <= g.volume_index < len(g.volumes))

    def execute(self, context):
        group = active_group(context)
        group.volumes.remove(group.volume_index)
        group.volume_index = max(0, min(group.volume_index, len(group.volumes) - 1))
        group.dirty = True
        return {'FINISHED'}


# Nonfunctional operations kept visible for UI evaluation.
class LG_MockOp(Operator):
    bl_options = {'REGISTER'}

    def execute(self, _context):
        self.report({'INFO'}, f"[UI MOCK - not implemented] {self.bl_label}")
        return {'FINISHED'}


class LG_OT_add_selected(LG_MockOp):
    bl_idname = "lg.add_selected"
    bl_label = "Add Selected"
    bl_description = "MOCK: Add selected objects to the Manual group"

    @classmethod
    def poll(cls, context):
        g = active_group(context)
        return g is not None and g.source == 'MANUAL'


class LG_OT_remove_selected(LG_MockOp):
    bl_idname = "lg.remove_selected"
    bl_label = "Remove Selected"
    bl_description = "MOCK: Remove selected objects from the Manual group"

    @classmethod
    def poll(cls, context):
        g = active_group(context)
        return g is not None and g.source == 'MANUAL'


class LG_OT_select_members(LG_MockOp):
    bl_idname = "lg.select_members"
    bl_label = "Select Members"
    bl_description = "MOCK: Select members of the active group"

    mode: EnumProperty(items=[
        ('SET', "Select", "Replace the selection"),
        ('EXTEND', "Extend", "Add group to selection"),
        ('DESELECT', "Deselect", "Remove group from selection"),
    ], default='SET')


class LG_OT_select_groups_of_selection(LG_MockOp):
    bl_idname = "lg.select_groups_of_selection"
    bl_label = "Expand to Groups"
    bl_description = "MOCK: Select every member of all selected objects' groups"


class LG_OT_isolate(LG_MockOp):
    bl_idname = "lg.isolate"
    bl_label = "Isolate"
    bl_description = "MOCK: Show only members of the active group"


class LG_OT_show_all(LG_MockOp):
    bl_idname = "lg.show_all"
    bl_label = "Show All"
    bl_description = "MOCK: Restore all group visibility"


class LG_OT_fit_to_selection(LG_MockOp):
    bl_idname = "lg.fit_to_selection"
    bl_label = "Fit to Selection"
    bl_description = "MOCK: Fit a new Empty volume to selected objects"

    @classmethod
    def poll(cls, context):
        g = active_group(context)
        return g is not None and g.source == 'VOLUME'


class LG_OT_evaluate(LG_MockOp):
    bl_idname = "lg.evaluate"
    bl_label = "Evaluate"
    bl_description = "MOCK: Recalculate Volume members; not actually implemented"

    @classmethod
    def poll(cls, context):
        g = active_group(context)
        return g is not None and g.source == 'VOLUME'


# -----------------------------------------------------------------------------
# UI Lists
# -----------------------------------------------------------------------------


class LG_UL_groups(UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            swatch = row.row(align=True)
            swatch.ui_units_x = 1.0
            swatch.prop(item, "color", text="")
            row.label(text="M" if item.source == 'MANUAL' else "V")
            row.prop(item, "name", text="", emboss=False)
            right = row.row(align=True)
            right.alignment = 'RIGHT'
            right.label(text=str(item.member_count),
                        icon='FILE_REFRESH' if item.dirty else 'NONE')
            row.prop(item, "show", text="", emboss=False,
                     icon='RESTRICT_VIEW_OFF' if item.show else 'RESTRICT_VIEW_ON')
            row.prop(item, "selectable", text="", emboss=False,
                     icon=('RESTRICT_SELECT_OFF' if item.selectable
                           else 'RESTRICT_SELECT_ON'))
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='GROUP')


class LG_UL_volumes(UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        row = layout.row(align=True)
        obj = item.obj
        if obj is None:
            row.label(text="(missing Empty)", icon='ERROR')
        else:
            shape_icon = {
                'CUBE': 'MESH_CUBE', 'SPHERE': 'MESH_UVSPHERE'
            }.get(obj.empty_display_type, 'EMPTY_AXIS')
            row.label(text=obj.name, icon=shape_icon)
        row.prop(item, "op", text="")


# -----------------------------------------------------------------------------
# Panels
# -----------------------------------------------------------------------------


class LG_PT_main(Panel):
    bl_label = "Groups"
    bl_idname = "LG_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Groups"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text="Zone Groups  |  UI prototype", icon='GROUP')

        if not scene.lg_groups:
            box = layout.box()
            box.label(text="No groups yet", icon='INFO')
            box.operator("lg.group_new", text="New Group", icon='ADD')
            box.operator("lg.dummy_data", text="Create Demo Groups", icon='FILE_NEW')
            return

        row = layout.row()
        row.template_list("LG_UL_groups", "", scene, "lg_groups",
                          scene, "lg_active_index", rows=6)
        col = row.column(align=True)
        col.operator("lg.group_new", text="", icon='ADD')
        col.operator("lg.group_remove", text="", icon='REMOVE')
        col.separator()
        col.operator("lg.group_duplicate", text="", icon='DUPLICATE')
        col.separator()
        col.operator("lg.group_move", text="", icon='TRIA_UP').direction = 'UP'
        col.operator("lg.group_move", text="", icon='TRIA_DOWN').direction = 'DOWN'

        group = active_group(context)
        if group is None:
            return

        row = layout.row(align=True)
        row.operator("lg.group_duplicate", text="Duplicate Group", icon='DUPLICATE')
        merge_row = row.row(align=True)
        merge_row.enabled = has_compatible_merge_group(context)
        merge_row.operator("lg.group_merge", text="Merge Groups", icon='MOD_BOOLEAN')
        if not has_compatible_merge_group(context):
            layout.label(text="Merge: another group of the same mode required", icon='INFO')

        box = layout.box()
        box.label(text=f"Active: {group.name} [{group.source.title()}]")
        box.label(text=f"Selected: {len(context.selected_objects)} object(s)")
        box.label(text="Object membership not implemented (mock)", icon='INFO')

        col = layout.column(align=True)
        if group.source == 'MANUAL':
            row = col.row(align=True)
            row.operator("lg.add_selected", text="Add Selected", icon='ADD')
            row.operator("lg.remove_selected", text="Remove Selected", icon='REMOVE')
        else:
            col.label(text="Volume group: use Empty volumes in Members")

        row = col.row(align=True)
        row.operator("lg.select_members", text="Select", icon='SELECT_SET').mode = 'SET'
        row.operator("lg.select_members", text="Extend", icon='SELECT_EXTEND').mode = 'EXTEND'
        row.operator("lg.select_members", text="Deselect", icon='SELECT_SUBTRACT').mode = 'DESELECT'
        col.operator("lg.select_groups_of_selection", text="Expand to Groups", icon='GROUP')


class LG_PT_members(Panel):
    bl_label = "Members"
    bl_idname = "LG_PT_members"
    bl_parent_id = "LG_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Groups"

    @classmethod
    def poll(cls, context):
        return active_group(context) is not None

    def draw(self, context):
        layout = self.layout
        group = active_group(context)
        layout.label(text="Membership Mode")
        layout.prop(group, "source", expand=True)

        if group.source == 'VOLUME':
            row = layout.row()
            row.template_list("LG_UL_volumes", "", group, "volumes",
                              group, "volume_index", rows=3)
            col = row.column(align=True)
            col.operator_menu_enum("lg.volume_add", "shape", text="", icon='ADD')
            col.operator("lg.volume_remove", text="", icon='REMOVE')
            col.separator()
            col.operator("lg.fit_to_selection", text="", icon='SHADING_BBOX')

            if 0 <= group.volume_index < len(group.volumes):
                volume = group.volumes[group.volume_index]
                if volume.obj is not None:
                    box = layout.box()
                    props = box.column(align=True)
                    props.prop(volume.obj, "empty_display_type", text="Shape")
                    props.prop(volume.obj, "empty_display_size", text="Size")
                    props.prop(volume.obj, "scale", text="Scale")

            layout.prop(group, "eval_mode")
            layout.label(text="Object Types")
            row = layout.row(align=True)
            row.prop(group, "t_mesh", text="", icon='OUTLINER_OB_MESH', toggle=True)
            row.prop(group, "t_light", text="", icon='OUTLINER_OB_LIGHT', toggle=True)
            row.prop(group, "t_camera", text="", icon='OUTLINER_OB_CAMERA', toggle=True)
            row.prop(group, "t_curve", text="", icon='OUTLINER_OB_CURVE', toggle=True)
            row.prop(group, "t_empty", text="", icon='OUTLINER_OB_EMPTY', toggle=True)
            row.prop(group, "t_other", text="", icon='OBJECT_DATA', toggle=True)

            layout.separator()
            layout.label(text="Update Behavior (UI only)")
            layout.prop(group, "update_mode", expand=True)
            row = layout.row(align=True)
            row.operator("lg.evaluate", text="Evaluate", icon='FILE_REFRESH')
            row.label(text=f"{group.member_count} (mock)")
            if group.dirty:
                layout.label(text="Needs evaluation (mock status)", icon='ERROR')
        else:
            layout.label(text="Use Add Selected / Remove Selected above")
            layout.label(text=f"{group.member_count} members (mock count)")


class LG_PT_visibility(Panel):
    bl_label = "Visibility"
    bl_idname = "LG_PT_visibility"
    bl_parent_id = "LG_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Groups"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return active_group(context) is not None

    def draw(self, context):
        layout = self.layout
        group = active_group(context)
        row = layout.row(align=True)
        row.prop(group, "show", text="Viewport", toggle=True,
                 icon='RESTRICT_VIEW_OFF' if group.show else 'RESTRICT_VIEW_ON')
        row.prop(group, "selectable", text="Select", toggle=True,
                 icon=('RESTRICT_SELECT_OFF' if group.selectable
                       else 'RESTRICT_SELECT_ON'))
        row.prop(group, "render", text="Render", toggle=True,
                 icon='RESTRICT_RENDER_OFF' if group.render else 'RESTRICT_RENDER_ON')
        row = layout.row(align=True)
        row.operator("lg.isolate", text="Isolate", icon='SOLO_OFF')
        row.operator("lg.show_all", text="Show All")
        layout.label(text="Visibility controls: UI preview only", icon='INFO')


# -----------------------------------------------------------------------------
# Register / unregister
# -----------------------------------------------------------------------------


CLASSES = (
    LG_VolumeItem,
    LG_GroupItem,
    LG_OT_group_new,
    LG_OT_group_remove,
    LG_OT_group_move,
    LG_OT_group_duplicate,
    LG_OT_group_merge,
    LG_OT_dummy_data,
    LG_OT_volume_add,
    LG_OT_volume_remove,
    LG_OT_add_selected,
    LG_OT_remove_selected,
    LG_OT_select_members,
    LG_OT_select_groups_of_selection,
    LG_OT_isolate,
    LG_OT_show_all,
    LG_OT_fit_to_selection,
    LG_OT_evaluate,
    LG_UL_groups,
    LG_UL_volumes,
    LG_PT_main,
    LG_PT_members,
    LG_PT_visibility,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lg_groups = CollectionProperty(type=LG_GroupItem)
    bpy.types.Scene.lg_active_index = IntProperty(default=0)


def unregister():
    if hasattr(bpy.types.Scene, "lg_active_index"):
        del bpy.types.Scene.lg_active_index
    if hasattr(bpy.types.Scene, "lg_groups"):
        del bpy.types.Scene.lg_groups
    for cls in reversed(CLASSES):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
