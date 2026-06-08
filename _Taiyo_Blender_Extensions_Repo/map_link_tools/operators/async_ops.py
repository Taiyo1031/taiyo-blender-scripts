from bpy.types import Operator


class MAPLINK_OT_cancel_operation(Operator):
    bl_idname = "maplink.cancel_operation"
    bl_label = "Cancel Operation"
    bl_description = "Cancel the current Map Link Tools operation after the current tick"

    def execute(self, context):
        settings = context.scene.maplink_settings
        if not settings.is_running:
            self.report({"INFO"}, "No Map Link Tools operation is running.")
            return {"CANCELLED"}
        settings.cancel_requested = True
        self.report({"INFO"}, "Cancel requested.")
        return {"FINISHED"}
