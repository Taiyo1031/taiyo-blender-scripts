bl_info = {
    "name": "Replace Selected with Active",
    "author": "Taiyo",
    "version": (3, 0, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Replace",
    "description": "Replace selected objects with copies of the active object",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/replace_selected_with_active/Replace_Selected_with_Active_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy


# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────

def get_object_collection(obj, scene):
    """Return the first collection that contains obj (falls back to scene root)."""
    if obj is None:
        return scene.collection

    if obj.name in scene.collection.objects:
        return scene.collection

    for col in scene.collection.children_recursive:
        if obj.name in col.objects:
            return col

    return scene.collection


def copy_transform_options(new_obj, target, props):
    """Copy only the transform components that are checked in props."""
    if props.copy_location:
        new_obj.location = target.location.copy()

    if props.copy_rotation:
        new_obj.rotation_euler = target.rotation_euler.copy()

    if props.copy_scale:
        new_obj.scale = target.scale.copy()


# ─────────────────────────────────────────
#  Properties
# ─────────────────────────────────────────

class REPSEL_Props(bpy.types.PropertyGroup):

    placement_mode: bpy.props.EnumProperty(
        name="Placement Collection",
        description="Choose which collection the replacement copies are added to",
        items=[
            (
                "ACTIVE",
                "Active Object's Collection",
                "Add copies to the collection that the active (source) object belongs to",
                'OBJECT_DATA',
                0,
            ),
            (
                "TARGET",
                "Target Object's Collection",
                "Add each copy to the collection that its corresponding target object belongs to",
                'OUTLINER_COLLECTION',
                1,
            ),
        ],
        default="ACTIVE",
    )

    replace_targets: bpy.props.BoolProperty(
        name="Delete Targets After Replace",
        description="Remove the original selected objects and replace them with copies of the active object",
        default=True,
    )

    delete_source: bpy.props.BoolProperty(
        name="Delete Source After Replace",
        description="Remove the active (source) object after the replace operation is complete",
        default=False,
    )

    copy_location: bpy.props.BoolProperty(
        name="Location",
        description="Inherit the target's world location",
        default=True,
    )

    copy_rotation: bpy.props.BoolProperty(
        name="Rotation",
        description="Inherit the target's world rotation",
        default=True,
    )

    copy_scale: bpy.props.BoolProperty(
        name="Scale",
        description="Inherit the target's world scale",
        default=False,
    )


# ─────────────────────────────────────────
#  Operator
# ─────────────────────────────────────────

class REPSEL_OT_execute(bpy.types.Operator):
    """Replace selected objects with copies of the active object"""
    bl_idname = "object.repsel_execute"
    bl_label = "Replace Selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        active = context.active_object
        targets = [o for o in context.selected_objects if o != active]
        return active is not None and len(targets) >= 1

    def execute(self, context):
        props = context.scene.repsel_props
        active = context.active_object
        targets = [o for o in context.selected_objects if o != active]

        if active is None:
            self.report({'WARNING'}, "No source object selected.")
            return {'CANCELLED'}

        if not targets:
            self.report({'WARNING'}, "No target objects selected.")
            return {'CANCELLED'}

        # Collection used when ACTIVE mode is selected
        active_collection = get_object_collection(active, context.scene)

        created = []

        for target in targets:
            # Determine destination collection based on mode
            if props.placement_mode == "TARGET":
                dest_collection = get_object_collection(target, context.scene)
            else:  # ACTIVE
                dest_collection = active_collection

            # Duplicate the active object (object + data both independent)
            new_obj = active.copy()
            if active.data:
                new_obj.data = active.data.copy()

            # Link into the destination collection
            dest_collection.objects.link(new_obj)

            # Inherit transform from target
            copy_transform_options(new_obj, target, props)

            # Name the new object
            new_obj.name = f"{active.name}_replace"

            created.append((new_obj, dest_collection.name))

            # Remove the original target if requested
            if props.replace_targets:
                bpy.data.objects.remove(target, do_unlink=True)

        # Optionally remove the source object
        if props.delete_source:
            bpy.data.objects.remove(active, do_unlink=True)

        # Update selection to the newly created objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj, _ in created:
            obj.select_set(True)
        if created:
            context.view_layer.objects.active = created[-1][0]

        # Build report string
        mode_text = "→ Active's collection" if props.placement_mode == "ACTIVE" else "→ Each target's collection"
        target_text = " | targets removed" if props.replace_targets else " | targets kept"
        source_text = " | source removed" if props.delete_source else ""

        self.report(
            {'INFO'},
            f"{len(created)} object(s) replaced  {mode_text}{target_text}{source_text}",
        )

        return {'FINISHED'}


# ─────────────────────────────────────────
#  Panel
# ─────────────────────────────────────────

class REPSEL_PT_panel(bpy.types.Panel):
    bl_label = "Replace Selected"
    bl_idname = "REPSEL_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Replace"

    def draw(self, context):
        layout = self.layout
        props = context.scene.repsel_props
        active = context.active_object
        targets = [o for o in context.selected_objects if o is not None and o != active]

        # ── Status ──────────────────────────────────
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.85

        if active:
            col.label(text=f"Source:   {active.name}", icon='OBJECT_DATA')
        else:
            col.label(text="Source:   None selected", icon='ERROR')

        col.label(
            text=f"Targets:  {len(targets)} object(s)",
            icon='CHECKMARK' if targets else 'ERROR',
        )

        # "Destination" label changes with mode
        if props.placement_mode == "ACTIVE":
            active_col = get_object_collection(active, context.scene) if active else None
            dest_label = active_col.name if active_col else "—"
        else:
            dest_label = "(Each target's collection)"

        col.label(
            text=f"Destination:  {dest_label}",
            icon='OUTLINER_COLLECTION',
        )

        layout.separator(factor=0.5)

        # ── Replace Settings ─────────────────────────
        box = layout.box()
        box.label(text="Replace Settings", icon='MODIFIER')
        box.prop(props, "replace_targets")
        box.prop(props, "delete_source")

        layout.separator(factor=0.5)

        # ── Placement Mode ───────────────────────────
        box = layout.box()
        box.label(text="Placement Collection", icon='OUTLINER_COLLECTION')
        col = box.column(align=True)
        col.prop(props, "placement_mode", expand=True)

        layout.separator(factor=0.5)

        # ── Transform Inherit ────────────────────────
        box = layout.box()
        box.label(text="Inherit Transform", icon='PROPERTIES')
        row = box.row(align=True)
        row.scale_y = 1.3
        row.prop(props, "copy_location", toggle=True)
        row.prop(props, "copy_rotation", toggle=True)
        row.prop(props, "copy_scale", toggle=True)

        layout.separator(factor=0.5)

        # ── Execute Button ───────────────────────────
        col = layout.column()
        col.scale_y = 1.8
        col.enabled = active is not None and len(targets) >= 1
        col.operator(
            "object.repsel_execute",
            text="Replace Selected Objects",
            icon='FILE_REFRESH',
        )

        layout.separator(factor=0.5)

        # ── Usage Hint ───────────────────────────────
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.75
        col.label(text="① Select one or more target objects", icon='BLANK1')
        col.label(text="② Shift-click the source object last", icon='BLANK1')
        col.label(text="③ Press  Replace Selected Objects", icon='BLANK1')

        layout.separator(factor=0.5)

        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.75
        col.label(text="Internally creates copies of the source,", icon='INFO')
        col.label(text="but behaves as an in-place replacement.", icon='BLANK1')


# ─────────────────────────────────────────
#  Register
# ─────────────────────────────────────────

class REPSEL_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    REPSEL_AddonPreferences,
    REPSEL_Props,
    REPSEL_OT_execute,
    REPSEL_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.repsel_props = bpy.props.PointerProperty(type=REPSEL_Props)


def unregister():
    del bpy.types.Scene.repsel_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()