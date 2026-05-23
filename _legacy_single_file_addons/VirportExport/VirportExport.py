bl_info = {
    "name": "Viewport Export Selected Meshes (AutoFit Temp Camera / Project Format / Overwrite)",
    "author": "ChatGPT",
    "version": (1, 5, 1),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Viewport Export",
    "description": "Create a temp camera from current viewport (no camera_to_view poll issues), force the viewport to render from that temp camera view, auto-fit each selected mesh, export via Viewport Render(OpenGL). Uses project format, overwrites, shows progress.",
    "category": "Render",
}

import bpy
import os
import math
from mathutils import Vector


# =========================
# Utilities
# =========================
def safe_filename(name: str) -> str:
    return bpy.path.clean_name(name)


def format_to_ext(file_format: str) -> str:
    fmt = (file_format or "").upper()
    mapping = {
        "PNG": ".png",
        "JPEG": ".jpg",
        "JPG": ".jpg",
        "TIFF": ".tif",
        "BMP": ".bmp",
        "TARGA": ".tga",
        "TARGA_RAW": ".tga",
        "OPEN_EXR": ".exr",
        "OPEN_EXR_MULTILAYER": ".exr",
        "HDR": ".hdr",
        "DPX": ".dpx",
        "CINEON": ".cin",
        "JP2": ".jp2",
        "WEBP": ".webp",
    }
    return mapping.get(fmt, ".png")


def force_ui_redraw():
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass


def set_status_text(context, text):
    ws = getattr(context, "workspace", None)
    if ws and hasattr(ws, "status_text_set"):
        ws.status_text_set(text)


def get_view3d_override(context):
    """
    Sidebarのボタンは通常 'そのView3D' から実行されるので、
    まず context.area を優先して取りに行く（安定性UP）。
    見つからない場合だけ window から探索。
    """
    win = context.window
    if not win:
        return None

    def build_override(area):
        if not area or area.type != "VIEW_3D":
            return None
        space = area.spaces.active
        if not space or space.type != "VIEW_3D":
            return None
        r3d = space.region_3d
        if not r3d:
            return None
        for region in area.regions:
            if region.type == "WINDOW":
                return {
                    "window": win,
                    "screen": win.screen,
                    "area": area,
                    "region": region,
                    "space_data": space,
                    "region_data": r3d,
                    "scene": context.scene,
                    "view_layer": context.view_layer,
                }
        return None

    # 1) まず今のエリア
    ov = build_override(getattr(context, "area", None))
    if ov:
        return ov

    # 2) fallback: 最初に見つかったView3D
    for area in win.screen.areas:
        ov = build_override(area)
        if ov:
            return ov

    return None


def store_region3d_state(space):
    r3d = space.region_3d
    return {
        "view_perspective": r3d.view_perspective,
        "view_location": r3d.view_location.copy(),
        "view_rotation": r3d.view_rotation.copy(),
        "view_distance": r3d.view_distance,
        "view_camera_zoom": getattr(r3d, "view_camera_zoom", 0),
        "view_camera_offset": getattr(r3d, "view_camera_offset", (0.0, 0.0)),
    }


def restore_region3d_state(space, state):
    r3d = space.region_3d
    r3d.view_perspective = state["view_perspective"]
    r3d.view_location = state["view_location"]
    r3d.view_rotation = state["view_rotation"]
    r3d.view_distance = state["view_distance"]
    if hasattr(r3d, "view_camera_zoom"):
        r3d.view_camera_zoom = state["view_camera_zoom"]
    if hasattr(r3d, "view_camera_offset"):
        r3d.view_camera_offset = state["view_camera_offset"]


def bbox_world_points(obj):
    return [obj.matrix_world @ Vector(c) for c in obj.bound_box]


def camera_axes_world(cam_obj):
    rot = cam_obj.matrix_world.to_3x3()
    right = rot @ Vector((1, 0, 0))
    up = rot @ Vector((0, 1, 0))
    forward = rot @ Vector((0, 0, -1))  # camera looks -Z
    return right, up, forward


def render_aspect(scene):
    r = scene.render
    x = r.resolution_x * r.pixel_aspect_x
    y = r.resolution_y * r.pixel_aspect_y
    return (y / x) if x != 0 else 1.0


# =========================
# Temp Camera (NO camera_to_view)
# =========================
def create_temp_camera_from_view(context, name="VPEX_TempCam", match_view_lens=True):
    """
    camera_to_view はpollが厳しいので使わない。
    RegionView3D.view_matrix を反転して camera.matrix_world に直接適用する。
    """
    scene = context.scene
    ov = get_view3d_override(context)
    if ov is None:
        return None, None

    space = ov["space_data"]
    r3d = ov["region_data"]

    cam_data = bpy.data.cameras.new(name)
    cam_obj = bpy.data.objects.new(name, cam_data)

    coll = context.collection if context.collection else scene.collection
    coll.objects.link(cam_obj)

    if match_view_lens and hasattr(space, "lens"):
        cam_data.lens = space.lens

    if getattr(r3d, "view_perspective", "") == "ORTHO":
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(0.01, r3d.view_distance * 2.0)
    else:
        cam_data.type = "PERSP"

    cam_obj.matrix_world = r3d.view_matrix.inverted()

    old_cam = scene.camera
    scene.camera = cam_obj

    return cam_obj, old_cam


def delete_camera(cam_obj):
    if not cam_obj:
        return
    cam_data = cam_obj.data
    for coll in list(cam_obj.users_collection):
        coll.objects.unlink(cam_obj)
    bpy.data.objects.remove(cam_obj, do_unlink=True)
    if cam_data and cam_data.users == 0:
        bpy.data.cameras.remove(cam_data)


# =========================
# AutoFit camera to object
# =========================
def autofit_camera_to_object(scene, cam_obj, obj, margin=0.90):
    cam = cam_obj.data
    pts_w = bbox_world_points(obj)

    right, up, forward = camera_axes_world(cam_obj)

    # --- 1) center in camera plane (x/y) ---
    inv = cam_obj.matrix_world.inverted()
    pts_c = [inv @ p for p in pts_w]

    center_c = Vector((0, 0, 0))
    for p in pts_c:
        center_c += p
    center_c /= len(pts_c)

    cam_obj.location += right * center_c.x + up * center_c.y

    # --- 2) fit size (distance or ortho_scale) ---
    inv = cam_obj.matrix_world.inverted()
    pts_c = [inv @ p for p in pts_w]

    m = max(0.10, min(0.99, float(margin)))

    if cam.type == "ORTHO":
        max_x = max(abs(p.x) for p in pts_c)
        max_y = max(abs(p.y) for p in pts_c)
        asp = render_aspect(scene)

        need_scale_x = (2.0 * max_x) / m
        need_scale_y = (2.0 * max_y) / (m * asp) if asp != 0 else (2.0 * max_y) / m
        cam.ortho_scale = max(cam.ortho_scale, need_scale_x, need_scale_y)
        return True

    # PERSP
    tanx = math.tan(cam.angle_x * 0.5)
    tany = math.tan(cam.angle_y * 0.5)

    slacks = []
    depths = []

    for p in pts_c:
        depth = -p.z
        depths.append(depth)
        if depth <= 1e-6:
            return False

        req = max(abs(p.x) / tanx, abs(p.y) / tany) / m
        slacks.append(depth - req)

    min_slack = min(slacks)
    min_depth = min(depths)

    clip_safe = cam.clip_start * 1.1
    max_forward = max(0.0, min_depth - clip_safe)

    if min_slack < 0.0:
        cam_obj.location -= forward * (-min_slack)  # move back
    else:
        cam_obj.location += forward * min(min_slack, max_forward)  # move forward safely

    return True


# =========================
# Properties
# =========================
class VPEXPORT_Props(bpy.types.PropertyGroup):
    output_dir: bpy.props.StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        default="//viewport_exports/",
    )
    solo_export: bpy.props.BoolProperty(
        name="Solo (hide others)",
        description="書き出し中、同じViewLayer内の他オブジェクトを一時的に非表示にする",
        default=True,
    )

    temp_cam_name: bpy.props.StringProperty(
        name="Temp Camera Name",
        default="VPEX_TempCam",
    )
    delete_temp_camera: bpy.props.BoolProperty(
        name="Delete Temp Camera After",
        default=True,
    )
    match_view_lens: bpy.props.BoolProperty(
        name="Match Viewport Lens",
        default=True,
    )
    fit_margin: bpy.props.FloatProperty(
        name="Fit Margin",
        description="画角に収める余白（0.90=10%余白）",
        default=0.90,
        min=0.10,
        max=0.99,
    )


# =========================
# Operator
# =========================
class RENDER_OT_viewport_export_selected_meshes_autofit(bpy.types.Operator):
    bl_idname = "render.viewport_export_selected_meshes_autofit"
    bl_label = "Export Selected Meshes (Auto-Fit Temp Camera)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        props = scene.vpexport_props
        wm = context.window_manager

        selected_meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if not selected_meshes:
            self.report({"WARNING"}, "選択中にメッシュがありません")
            return {"CANCELLED"}

        ov = get_view3d_override(context)
        if ov is None:
            self.report({"ERROR"}, "VIEW_3Dが見つかりません（3Dビューが開いている状態で実行してください）")
            return {"CANCELLED"}

        out_dir = bpy.path.abspath(props.output_dir)
        os.makedirs(out_dir, exist_ok=True)

        ext = format_to_ext(scene.render.image_settings.file_format)

        view_layer = context.view_layer
        targets = [obj for obj in selected_meshes if view_layer.objects.get(obj.name) is not None]
        if not targets:
            self.report({"WARNING"}, "選択メッシュがすべてViewLayer外のため処理できませんでした")
            return {"CANCELLED"}

        # --- backups ---
        original_filepath = scene.render.filepath
        view_state = store_region3d_state(ov["space_data"])

        space = ov["space_data"]
        r3d = ov["region_data"]

        # View3Dの「ローカルカメラ」設定を退避（これが超重要）
        old_use_local_cam = getattr(space, "use_local_camera", False)
        old_local_cam = getattr(space, "camera", None)

        old_scene_cam = scene.camera

        # create temp camera aligned to current viewport (no poll)
        temp_cam, prev_cam = create_temp_camera_from_view(
            context,
            name=props.temp_cam_name,
            match_view_lens=props.match_view_lens
        )
        if temp_cam is None:
            self.report({"ERROR"}, "Temp Cameraの作成に失敗しました")
            return {"CANCELLED"}

        # ViewLayer objects (after camera is linked)
        layer_objects = list(view_layer.objects)
        original_hide = {obj.name: obj.hide_get() for obj in layer_objects}

        # ★ここが今回の要点：このView3Dが「必ずTempCamを見る」ように強制
        if hasattr(space, "use_local_camera"):
            space.use_local_camera = True
        if hasattr(space, "camera"):
            space.camera = temp_cam

        total = len(targets)
        wm.progress_begin(0, total)
        set_status_text(context, f"AutoFit Export: 0 / {total}")
        force_ui_redraw()

        try:
            # カメラビューに切り替え（view_cameraはpollが緩いのでOK）
            # もし環境差で失敗しても、view_perspective='CAMERA' を直接入れて保険にする
            with bpy.context.temp_override(**ov):
                try:
                    bpy.ops.view3d.view_camera()
                except Exception:
                    r3d.view_perspective = "CAMERA"

            for idx, obj in enumerate(targets, start=1):
                wm.progress_update(idx)
                set_status_text(context, f"AutoFit Export: {idx} / {total} | {obj.name}")
                force_ui_redraw()

                # solo hide (viewlayer only; do not hide temp camera)
                if props.solo_export:
                    for o in layer_objects:
                        if o == temp_cam:
                            continue
                        o.hide_set(True)
                    obj.hide_set(False)

                # fit camera
                ok = autofit_camera_to_object(scene, temp_cam, obj, margin=props.fit_margin)
                if not ok:
                    self.report({"WARNING"}, f"AutoFit失敗（カメラ後方の可能性）: {obj.name}")

                # overwrite
                filename = safe_filename(obj.name) + ext
                scene.render.filepath = os.path.join(out_dir, filename)

                # ★Viewport Render(OpenGL) from THIS VIEW3D, now forced to TempCam camera view
                with bpy.context.temp_override(**ov):
                    bpy.ops.render.opengl(write_still=True)

                force_ui_redraw()

        finally:
            set_status_text(context, None)
            wm.progress_end()

            # restore render filepath
            scene.render.filepath = original_filepath

            # restore hide
            for o in layer_objects:
                o.hide_set(original_hide.get(o.name, False))

            # restore viewport view state
            restore_region3d_state(space, view_state)

            # restore local camera settings
            if hasattr(space, "camera"):
                space.camera = old_local_cam
            if hasattr(space, "use_local_camera"):
                space.use_local_camera = old_use_local_cam

            # restore scene camera
            scene.camera = old_scene_cam if old_scene_cam else prev_cam

            # delete temp camera
            if props.delete_temp_camera:
                delete_camera(temp_cam)

        self.report({"INFO"}, f"完了: {total} 個を書き出し（AutoFit / 上書き）しました")
        return {"FINISHED"}


# =========================
# Panel
# =========================
class VIEW3D_PT_viewport_export(bpy.types.Panel):
    bl_label = "Viewport Export"
    bl_idname = "VIEW3D_PT_viewport_export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Viewport Export"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.vpexport_props

        layout.prop(props, "output_dir")
        layout.prop(props, "solo_export")
        layout.separator()
        layout.label(text=f"Project Format: {scene.render.image_settings.file_format}")
        layout.separator()

        layout.label(text="Auto-Fit Temp Camera")
        layout.prop(props, "temp_cam_name")
        layout.prop(props, "match_view_lens")
        layout.prop(props, "fit_margin")
        layout.prop(props, "delete_temp_camera")
        layout.operator(RENDER_OT_viewport_export_selected_meshes_autofit.bl_idname, icon="CAMERA_DATA")


# =========================
# Register
# =========================
classes = (
    VPEXPORT_Props,
    RENDER_OT_viewport_export_selected_meshes_autofit,
    VIEW3D_PT_viewport_export,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.vpexport_props = bpy.props.PointerProperty(type=VPEXPORT_Props)


def unregister():
    del bpy.types.Scene.vpexport_props
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
