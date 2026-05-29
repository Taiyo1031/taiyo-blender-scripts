bl_info = {
    "name": "Taiyo Extension Manager",
    "author": "Taiyo",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar(N) > Taiyo",
    "description": "Install and uninstall Taiyo Blender Extensions from a side panel.",
    "category": "System",
}

import os
import textwrap

import addon_utils
import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel


REMOTE_REPO_URL = "https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json"
REPO_NAME = "Taiyo Blender Scripts"
REPO_MODULE = "taiyo_blender_scripts"
DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/taiyo_extension_manager/README.md"
)

MANAGED_PACKAGES = (
    {
        "id": "attribute_csv_exporter",
        "name": "Attribute CSV Exporter",
        "version": "1.8.3",
        "min_blender": (4, 5, 9),
        "ja": "選択メッシュの属性をCSVに書き出します。",
        "en": "Export selected mesh attributes to CSV.",
    },
    {
        "id": "collection_number_to_mesh_name",
        "name": "Collection Number To Mesh Name",
        "version": "1.0.1",
        "min_blender": (4, 2, 0),
        "ja": "コレクション番号を付け、メッシュデータ名を整理します。",
        "en": "Number collections and rename their mesh data.",
    },
    {
        "id": "collection_mesh_merge_fbx_exporter",
        "name": "Collection Mesh Merge FBX Exporter",
        "version": "0.3.0",
        "min_blender": (4, 2, 0),
        "ja": "対象コレクションを統合し、FBX/USD/Alembicで書き出します。",
        "en": "Export target collections as merged FBX, USD, or Alembic files.",
    },
    {
        "id": "export_selected_names_csv",
        "name": "Export Selected Object Names to CSV",
        "version": "1.0.1",
        "min_blender": (4, 2, 0),
        "ja": "選択オブジェクト名をCSVに書き出します。",
        "en": "Export selected object names to a CSV file.",
    },
    {
        "id": "gn_parameter_csv_exporter",
        "name": "GN Parameter CSV Exporter",
        "version": "1.1.1",
        "min_blender": (4, 2, 0),
        "ja": "Geometry Nodesモディファイアの入力値をCSVに書き出します。",
        "en": "Export Geometry Nodes modifier input parameters to CSV.",
    },
    {
        "id": "instance_name_fixer",
        "name": "Instance Name Fixer",
        "version": "0.1.2",
        "min_blender": (4, 5, 9),
        "ja": "コレクションインスタンス名をインスタンス元に揃えます。",
        "en": "Match collection instance names to their source collections.",
    },
    {
        "id": "move_selected_to_own_collections",
        "name": "Move Objects to Own Collections",
        "version": "1.2.1",
        "min_blender": (4, 2, 0),
        "ja": "選択オブジェクトを名前に対応した子コレクションへ移動します。",
        "en": "Move selected objects into matching child collections.",
    },
    {
        "id": "overlap_selector",
        "name": "Overlap Object Selector",
        "version": "1.2.2",
        "min_blender": (4, 2, 0),
        "ja": "シーン内の重なりオブジェクトを検出して確認できます。",
        "en": "Detect and review overlapping objects in the scene.",
    },
    {
        "id": "proportional_dimensions",
        "name": "Proportional Dimensions",
        "version": "1.0.1",
        "min_blender": (4, 2, 0),
        "ja": "XYZ比率を保ったまま、指定寸法へ均等スケールします。",
        "en": "Scale selected objects to a target dimension while preserving proportions.",
    },
    {
        "id": "rb_instance_helper",
        "name": "RB Instance Helper",
        "version": "1.3.3",
        "min_blender": (4, 5, 9),
        "ja": "リンクCollection Instance向けのRigid Body作業を補助します。",
        "en": "Help rigid-body workflows for linked Collection Instances.",
    },
    {
        "id": "replace_selected_with_active",
        "name": "Replace Selected with Active",
        "version": "3.0.1",
        "min_blender": (4, 2, 0),
        "ja": "選択オブジェクトをアクティブオブジェクトのコピーで置き換えます。",
        "en": "Replace selected objects with copies of the active object.",
    },
    {
        "id": "uv_channel_placement_tool",
        "name": "UV Channel Placement Tool",
        "version": "2.6.2",
        "min_blender": (4, 4, 0),
        "ja": "選択UVやメッシュ島をプリセットのグリッド位置へ配置します。",
        "en": "Place selected UVs or mesh islands into predefined grid slots.",
    },
    {
        "id": "unreal_bridge_tools",
        "name": "Unreal Bridge Tools",
        "version": "2.2.15",
        "min_blender": (4, 2, 0),
        "ja": "Unreal Engine PCG向けにTransformやCollisionタグを書き出します。",
        "en": "Export transforms and collision tags for Unreal Engine PCG.",
    },
    {
        "id": "viewport_export_selected_meshes",
        "name": "Viewport Export Selected Meshes",
        "version": "1.5.3",
        "min_blender": (4, 2, 0),
        "ja": "選択メッシュを現在のビューポートから1つずつ画像出力します。",
        "en": "Export selected mesh objects one by one from the current viewport.",
    },
)


def _repo_url_key(url):
    url = (url or "").strip().rstrip("/")
    if url.endswith("/index.json"):
        url = url[: -len("/index.json")]
    return url


def _find_taiyo_repo(context):
    target_key = _repo_url_key(REMOTE_REPO_URL)
    repos = context.preferences.extensions.repos

    for index, repo in enumerate(repos):
        if getattr(repo, "use_remote_url", False):
            if _repo_url_key(getattr(repo, "remote_url", "")) == target_key:
                return repo, index

    for index, repo in enumerate(repos):
        if getattr(repo, "module", "") == REPO_MODULE or getattr(repo, "name", "") == REPO_NAME:
            return repo, index

    return None, -1


def _addon_prefs(context):
    addon = context.preferences.addons.get(__package__ or __name__)
    return addon.preferences if addon else None


def _module_name(repo, pkg_id):
    return "bl_ext.{:s}.{:s}".format(repo.module, pkg_id)


def _package_state(repo, pkg_id):
    if repo is None:
        return False, False

    module_name = _module_name(repo, pkg_id)
    loaded_default, loaded_state = addon_utils.check(module_name)
    installed = bool(loaded_default or loaded_state)

    directory = getattr(repo, "directory", "")
    if directory:
        installed = installed or os.path.isdir(os.path.join(directory, pkg_id))

    return installed, bool(loaded_state)


def _version_supported(pkg):
    return tuple(bpy.app.version[:3]) >= pkg["min_blender"]


def _label_pair(pkg, language):
    if language == "JA":
        return (pkg["ja"],)
    if language == "EN":
        return (pkg["en"],)
    return (pkg["ja"], pkg["en"])


def _draw_wrapped(layout, text, width=42, icon="NONE"):
    lines = textwrap.wrap(text, width=width) or [text]
    for index, line in enumerate(lines):
        if index == 0 and icon != "NONE":
            layout.label(text=line, icon=icon)
        else:
            layout.label(text=line)


def _save_user_preferences():
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass


class TAYMAN_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or __name__

    language: EnumProperty(
        name="Language",
        description="Language used in the Taiyo Extension Manager panel",
        items=[
            ("BOTH", "日本語 + English", "Show Japanese and English descriptions"),
            ("JA", "日本語", "Show Japanese descriptions"),
            ("EN", "English", "Show English descriptions"),
        ],
        default="BOTH",
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "language")
        op = layout.operator("wm.url_open", text="Open Manager README", icon="URL")
        op.url = DOCUMENTATION_URL


class TAYMAN_OT_AddRepository(Operator):
    bl_idname = "tayman.add_repository"
    bl_label = "Add Taiyo Repository"
    bl_description = "Add the Taiyo Blender Scripts remote repository to Blender"
    bl_options = {"REGISTER"}

    def execute(self, context):
        repo, _repo_index = _find_taiyo_repo(context)
        if repo is not None:
            self.report({"INFO"}, "Taiyo repository is already registered.")
            return {"FINISHED"}

        repos = context.preferences.extensions.repos
        try:
            repo = repos.new(
                name=REPO_NAME,
                module=REPO_MODULE,
                remote_url=REMOTE_REPO_URL,
                source="USER",
            )
        except TypeError:
            repo = repos.new(name=REPO_NAME, module=REPO_MODULE, remote_url=REMOTE_REPO_URL)

        if hasattr(repo, "use_cache"):
            repo.use_cache = True

        _save_user_preferences()
        self.report({"INFO"}, "Added Taiyo repository. Press Refresh to sync packages.")
        return {"FINISHED"}


class TAYMAN_OT_CopyRepositoryURL(Operator):
    bl_idname = "tayman.copy_repository_url"
    bl_label = "Copy Repository URL"
    bl_description = "Copy the Taiyo remote repository URL"
    bl_options = {"REGISTER"}

    def execute(self, context):
        context.window_manager.clipboard = REMOTE_REPO_URL
        self.report({"INFO"}, "Copied Taiyo repository URL.")
        return {"FINISHED"}


class TAYMAN_OT_SetAddonEnabled(Operator):
    bl_idname = "tayman.set_addon_enabled"
    bl_label = "Set Taiyo Add-on Enabled"
    bl_description = "Enable or disable an installed Taiyo extension"
    bl_options = {"REGISTER", "UNDO"}

    pkg_id: StringProperty()
    action: EnumProperty(
        items=[
            ("ENABLE", "Enable", "Enable the installed extension"),
            ("DISABLE", "Disable", "Disable the installed extension"),
        ],
        default="ENABLE",
    )

    def execute(self, context):
        repo, _repo_index = _find_taiyo_repo(context)
        if repo is None:
            self.report({"ERROR"}, "Taiyo repository is not registered.")
            return {"CANCELLED"}

        module_name = _module_name(repo, self.pkg_id)
        try:
            if self.action == "ENABLE":
                addon_utils.enable(module_name, default_set=True)
                self.report({"INFO"}, "Enabled {:s}.".format(self.pkg_id))
            else:
                addon_utils.disable(module_name, default_set=True)
                self.report({"INFO"}, "Disabled {:s}.".format(self.pkg_id))
        except Exception as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        _save_user_preferences()
        return {"FINISHED"}


class TAYMAN_OT_UninstallPackage(Operator):
    bl_idname = "tayman.uninstall_package"
    bl_label = "Uninstall Taiyo Extension"
    bl_description = "Disable and uninstall an installed Taiyo extension"
    bl_options = {"REGISTER", "UNDO"}

    pkg_id: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        repo, repo_index = _find_taiyo_repo(context)
        if repo is None or repo_index < 0:
            self.report({"ERROR"}, "Taiyo repository is not registered.")
            return {"CANCELLED"}

        result = bpy.ops.extensions.package_uninstall(repo_index=repo_index, pkg_id=self.pkg_id)
        _save_user_preferences()
        return result


class TAYMAN_PT_Manager(Panel):
    bl_label = "Taiyo Add-on Manager"
    bl_idname = "TAYMAN_PT_manager"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Taiyo"

    def draw(self, context):
        layout = self.layout
        prefs = _addon_prefs(context)
        language = prefs.language if prefs else "BOTH"
        repo, repo_index = _find_taiyo_repo(context)

        row = layout.row(align=True)
        if prefs:
            row.prop(prefs, "language", text="")
        row.operator("tayman.copy_repository_url", text="", icon="COPYDOWN")

        box = layout.box()
        box.label(text=REPO_NAME, icon="URL")
        _draw_wrapped(box, REMOTE_REPO_URL, width=36)

        if repo is None:
            box.label(text="Repository not registered.", icon="ERROR")
            box.label(text="リポジトリ未登録です。", icon="INFO")
            box.operator("tayman.add_repository", text="Add Repository", icon="ADD")
            return

        row = box.row(align=True)
        row.label(text="Registered / 登録済み", icon="CHECKMARK")
        refresh = row.operator("extensions.repo_sync", text="", icon="FILE_REFRESH")
        refresh.repo_index = repo_index

        installed_count = 0
        for pkg in MANAGED_PACKAGES:
            installed, _enabled = _package_state(repo, pkg["id"])
            if installed:
                installed_count += 1

        layout.label(
            text="Installed: {:d} / {:d}".format(installed_count, len(MANAGED_PACKAGES)),
            icon="PACKAGE",
        )

        for pkg in MANAGED_PACKAGES:
            installed, enabled = _package_state(repo, pkg["id"])
            supported = _version_supported(pkg)

            item = layout.box()
            header = item.row(align=True)
            header.label(text=pkg["name"], icon="PLUGIN")
            header.label(text="v{:s}".format(pkg["version"]))

            for text in _label_pair(pkg, language):
                _draw_wrapped(item, text, width=44)

            status = item.row(align=True)
            if not supported:
                version = ".".join(str(part) for part in pkg["min_blender"])
                status.label(text="Requires Blender {:s}+".format(version), icon="ERROR")
            elif installed and enabled:
                status.label(text="Installed / Enabled", icon="CHECKMARK")
            elif installed:
                status.label(text="Installed / Disabled", icon="PAUSE")
            else:
                status.label(text="Not Installed", icon="IMPORT")

            actions = item.row(align=True)
            actions.enabled = supported

            if installed:
                op = actions.operator(
                    "tayman.set_addon_enabled",
                    text="Disable" if enabled else "Enable",
                    icon="HIDE_ON" if enabled else "HIDE_OFF",
                )
                op.pkg_id = pkg["id"]
                op.action = "DISABLE" if enabled else "ENABLE"

                op = actions.operator("tayman.uninstall_package", text="Uninstall", icon="TRASH")
                op.pkg_id = pkg["id"]
            else:
                op = actions.operator("extensions.package_install", text="Install", icon="IMPORT")
                op.repo_index = repo_index
                op.pkg_id = pkg["id"]
                op.enable_on_install = True


classes = (
    TAYMAN_AddonPreferences,
    TAYMAN_OT_AddRepository,
    TAYMAN_OT_CopyRepositoryURL,
    TAYMAN_OT_SetAddonEnabled,
    TAYMAN_OT_UninstallPackage,
    TAYMAN_PT_Manager,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
