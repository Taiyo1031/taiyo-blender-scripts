bl_info = {
    "name": "Taiyo Extension Manager",
    "author": "Taiyo",
    "version": (1, 0, 8),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar(N) > Taiyo",
    "description": "Install, update, and uninstall Taiyo Blender Extensions from a side panel.",
    "category": "System",
}

import os

import addon_utils
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel


REMOTE_REPO_URL = "https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json"
REPO_NAME = "Taiyo Blender Scripts"
REPO_MODULE = "taiyo_blender_scripts"
GITHUB_REPO_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts"
SOURCE_ROOT_URL = GITHUB_REPO_URL + "/tree/main/_Taiyo_Blender_Extensions_Repo"
DOCUMENTATION_URL = (
    GITHUB_REPO_URL
    + "/blob/main/_Taiyo_Blender_Extensions_Repo/taiyo_extension_manager/README.md"
)
SELF_ID = "taiyo_extension_manager"

TAG_ALIASES = {
    "attribute_csv_exporter": (
        "attribute", "attributes", "csv", "data", "export", "mesh", "spreadsheet",
        "table", "属性", "書き出し", "メッシュ", "表",
    ),
    "blend_reference_graph": (
        "asset", "bone", "collection", "constraint", "dependency", "graph", "geometry-nodes",
        "mesh", "node", "reference", "viewer", "visualize",
        "参照", "依存", "グラフ", "ノード", "メッシュ", "コレクション", "制約", "確認",
    ),
    "collection_mesh_merge_fbx_exporter": (
        "alembic", "abc", "collection", "combine", "export", "fbx", "merge", "usd",
        "asset", "batch", "pipeline", "統合", "書き出し", "コレクション", "アセット",
    ),
    "collection_linked_mesh_replacer": (
        "asset", "batch", "cache", "collection", "duplicate", "linked", "match",
        "mesh", "replace", "shape", "swap",
        "アセット", "キャッシュ", "コレクション", "メッシュ", "形状", "置換", "差し替え",
    ),
    "collection_number_to_mesh_name": (
        "collection", "cleanup", "mesh", "name", "number", "rename", "renaming",
        "整理", "番号", "名前", "名前整理", "リネーム", "メッシュ",
    ),
    "custom_properties_batch_editor": (
        "asset", "batch", "custom-property", "data", "metadata", "object", "mesh",
        "material", "preset", "property", "search", "tag",
        "一括編集", "検索", "カスタムプロパティ", "メタデータ", "タグ", "素材",
    ),
    "export_selected_names_csv": (
        "csv", "export", "list", "name", "names", "object", "selected", "spreadsheet",
        "一覧", "選択", "名前", "書き出し", "リスト",
    ),
    "gn_parameter_csv_exporter": (
        "csv", "export", "geometry-nodes", "gn", "modifier", "nodes", "parameter",
        "spreadsheet", "ジオメトリノード", "ノード", "パラメータ", "書き出し",
    ),
    "instance_name_fixer": (
        "collection", "fix", "instance", "name", "rename", "sync", "cleanup",
        "インスタンス", "コレクション", "名前", "名前整理", "修正",
    ),
    "map_link_tools": (
        "batch", "cleanup", "collection", "duplicate", "instance", "link", "map",
        "mesh", "name", "rename", "shared", "sync", "users",
        "マップ", "リンク", "共有", "インスタンス", "名前", "名前整理", "メッシュ", "リネーム",
    ),
    "move_selected_to_own_collections": (
        "collection", "move", "organize", "selected", "sort", "cleanup",
        "移動", "整理", "選択", "コレクション", "片付け",
    ),
    "modular_asset_renamer": (
        "asset", "batch", "choice", "dimensions", "index", "module", "name",
        "naming", "preset", "rename", "unreal",
        "アセット", "一括", "寸法", "名前", "名前整理", "命名", "連番", "リネーム",
    ),
    "overlap_selector": (
        "collision", "detect", "overlap", "review", "select", "selection", "check",
        "重なり", "衝突", "選択", "検出", "確認",
    ),
    "proportional_dimensions": (
        "dimensions", "measure", "proportion", "scale", "size", "transform",
        "寸法", "比率", "スケール", "サイズ", "変形",
    ),
    "rb_instance_helper": (
        "collection", "instance", "physics", "rb", "rigid-body", "simulation",
        "物理", "剛体", "リジッドボディ", "インスタンス", "シミュレーション",
    ),
    "replace_selected_with_active": (
        "active", "copy", "duplicate", "replace", "selected", "swap",
        "置換", "選択", "アクティブ", "コピー", "差し替え",
    ),
    "taiyo_extension_manager": (
        "available", "filter", "install", "installed", "manager", "search", "tag",
        "uninstall", "update", "管理", "検索", "タグ", "インストール", "更新",
    ),
    "unreal_bridge_tools": (
        "collision", "csv", "export", "pcg", "transform", "ue", "ue5", "unreal",
        "engine", "bridge", "アンリアル", "衝突", "コリジョン", "書き出し",
    ),
    "uv_channel_placement_tool": (
        "channel", "grid", "island", "placement", "slot", "uv", "uvs",
        "uv配置", "グリッド", "スロット", "島", "配置",
    ),
    "vertex_color_material_painter": (
        "color", "edit-mode", "face", "id", "material", "paint", "painter",
        "vertex", "vertex-color", "カラー", "頂点カラー", "マテリアル", "ペイント", "面",
    ),
    "viewport_export_selected_meshes": (
        "camera", "export", "image", "mesh", "render", "screenshot", "thumbnail",
        "viewport", "画像", "書き出し", "ビューポート", "サムネイル", "レンダー",
    ),
}

DESCRIPTION_ALIASES = {
    "attribute_csv_exporter": {
        "ja": "選択メッシュの属性をCSVに書き出します。",
        "en": "Export selected mesh attributes to CSV.",
    },
    "blend_reference_graph": {
        "ja": "Object、Mesh、Collection、Constraint、Geometry Nodesの参照関係をHTMLグラフで確認します。",
        "en": "Visualize object, mesh, collection, constraint, and Geometry Nodes references as an HTML graph.",
    },
    "collection_mesh_merge_fbx_exporter": {
        "ja": "対象コレクションを統合し、FBX/USD/Alembicで書き出します。",
        "en": "Export target collections as merged FBX, USD, or Alembic files.",
    },
    "collection_linked_mesh_replacer": {
        "ja": "形状が一致するCollection内の正規Meshへlinked duplicateで差し替えます。",
        "en": "Replace meshes with linked duplicates matched from a source collection.",
    },
    "collection_number_to_mesh_name": {
        "ja": "コレクション番号を付け、メッシュデータ名を整理します。",
        "en": "Number collections and rename their mesh data.",
    },
    "custom_properties_batch_editor": {
        "ja": "Object、Mesh、MaterialのCustom Propertiesを一括編集・検索します。",
        "en": "Batch edit and search custom properties on objects, meshes, and materials.",
    },
    "export_selected_names_csv": {
        "ja": "選択オブジェクト名をCSVに書き出します。",
        "en": "Export selected object names to a CSV file.",
    },
    "gn_parameter_csv_exporter": {
        "ja": "Geometry Nodesモディファイアの入力値をCSVに書き出します。",
        "en": "Export Geometry Nodes modifier input parameters to CSV.",
    },
    "instance_name_fixer": {
        "ja": "コレクションインスタンス名をインスタンス元に揃えます。",
        "en": "Match collection instance names to their source collections.",
    },
    "map_link_tools": {
        "ja": "マップ制作向けにリンク配置、共有Mesh、Collection Instance、名前整理をまとめて扱います。",
        "en": "Organize linked map objects, shared mesh data, collection instances, and names.",
    },
    "move_selected_to_own_collections": {
        "ja": "選択オブジェクトを名前に対応した子コレクションへ移動します。",
        "en": "Move selected objects into matching child collections.",
    },
    "modular_asset_renamer": {
        "ja": "モジュール式の命名ルールで選択ObjectとMesh Dataを一括リネームします。",
        "en": "Build modular naming rules and batch rename selected objects and mesh data.",
    },
    "overlap_selector": {
        "ja": "シーン内の重なりオブジェクトを検出して確認できます。",
        "en": "Detect and review overlapping objects in the scene.",
    },
    "proportional_dimensions": {
        "ja": "XYZ比率を保ったまま、指定寸法へ均等スケールします。",
        "en": "Scale selected objects to a target dimension while preserving proportions.",
    },
    "rb_instance_helper": {
        "ja": "リンクCollection Instance向けのRigid Body作業を補助します。",
        "en": "Help rigid-body workflows for linked Collection Instances.",
    },
    "replace_selected_with_active": {
        "ja": "選択オブジェクトをアクティブオブジェクトのコピーで置き換えます。",
        "en": "Replace selected objects with copies of the active object.",
    },
    "taiyo_extension_manager": {
        "ja": "Taiyo製Extensionをサイドバーから管理します。",
        "en": "Manage Taiyo extensions from the sidebar.",
    },
    "unreal_bridge_tools": {
        "ja": "Unreal Engine PCG向けにTransformやCollisionタグを書き出します。",
        "en": "Export transforms and collision tags for Unreal Engine PCG.",
    },
    "uv_channel_placement_tool": {
        "ja": "選択UVやメッシュ島をプリセットのグリッド位置へ配置します。",
        "en": "Place selected UVs or mesh islands into predefined grid slots.",
    },
    "vertex_color_material_painter": {
        "ja": "編集モードで選択面にマテリアルIDカラーをペイントします。",
        "en": "Paint selected edit-mode faces with material ID colors.",
    },
    "viewport_export_selected_meshes": {
        "ja": "選択メッシュを現在のビューポートから1つずつ画像出力します。",
        "en": "Export selected mesh objects one by one from the current viewport.",
    },
}

_AUTO_SYNC_DONE = False


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


def _value(item, name, default=None):
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _package_state(repo, pkg_id, item_local=None):
    if repo is None:
        return False, False

    module_name = _module_name(repo, pkg_id)
    loaded_default, loaded_state = addon_utils.check(module_name)
    installed = bool(item_local is not None or loaded_default or loaded_state)

    directory = getattr(repo, "directory", "")
    if directory:
        installed = installed or os.path.isdir(os.path.join(directory, pkg_id))

    return installed, bool(loaded_state)


def _version_tuple(version):
    parts = []
    for part in str(version or "").replace("-", ".").split("."):
        number = ""
        for char in part:
            if not char.isdigit():
                break
            number += char
        parts.append(int(number or 0))
    return tuple(parts)


def _is_outdated(item_local, item_remote):
    if item_local is None or item_remote is None:
        return False
    return _version_tuple(_value(item_remote, "version")) > _version_tuple(_value(item_local, "version"))


def _tags_for(pkg_id, item):
    tags = set(TAG_ALIASES.get(pkg_id, ()))
    raw_tags = _value(item, "tags", ()) or ()
    tags.update(str(tag).casefold() for tag in raw_tags)

    for field in (pkg_id, _value(item, "name", ""), _value(item, "tagline", "")):
        for token in str(field).replace("_", " ").replace("-", " ").split():
            token = token.strip(".,:;()[]{}").casefold()
            if token:
                tags.add(token)

    return tuple(sorted(tags))


def _search_text_for(pkg_id, item, tags):
    descriptions = DESCRIPTION_ALIASES.get(pkg_id, {})
    return " ".join(
        (
            pkg_id,
            str(_value(item, "name", "")),
            str(_value(item, "tagline", "")),
            descriptions.get("ja", ""),
            descriptions.get("en", ""),
            " ".join(tags),
        )
    ).casefold()


def _manual_url(pkg_id, item):
    return _value(item, "website", "") or "{:s}/{:s}/README.md".format(SOURCE_ROOT_URL, pkg_id)


def _source_url(pkg_id):
    return "{:s}/{:s}".format(SOURCE_ROOT_URL, pkg_id)


def _archive_url(item):
    archive = _value(item, "archive_url", "")
    if archive.startswith("./"):
        return REMOTE_REPO_URL.rsplit("/", 1)[0] + "/" + archive[2:]
    return archive


def _description_for(pkg_id, tagline, prefs):
    language = prefs.language if prefs else "AUTO"
    descriptions = DESCRIPTION_ALIASES.get(pkg_id, {})

    if language == "JA":
        return descriptions.get("ja") or tagline
    if language == "EN":
        return descriptions.get("en") or tagline
    return tagline or descriptions.get("en") or descriptions.get("ja") or ""


def _save_user_preferences():
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass


def _repo_manifests(repo):
    if repo is None:
        return {}, {}

    try:
        from bl_pkg import repo_cache_store_ensure
        from bl_pkg.bl_extension_ops import repo_cache_store_refresh_from_prefs

        repo_cache_store = repo_cache_store_ensure()
        repo_cache_store_refresh_from_prefs(repo_cache_store)

        local = repo_cache_store.refresh_local_from_directory(
            directory=repo.directory,
            error_fn=print,
            ignore_missing=True,
        )
        remote = repo_cache_store.refresh_remote_from_directory(
            directory=repo.directory,
            error_fn=print,
            force=False,
        )
        return local or {}, remote or {}
    except Exception as ex:
        print("Taiyo Extension Manager: repository cache unavailable:", ex)
        return {}, {}


def _refresh_repo_cache(repo, force=True):
    if repo is None:
        return False

    try:
        from bl_pkg import repo_cache_store_ensure
        from bl_pkg.bl_extension_ops import repo_cache_store_refresh_from_prefs

        repo_cache_store = repo_cache_store_ensure()
        repo_cache_store_refresh_from_prefs(repo_cache_store)
        repo_cache_store.refresh_local_from_directory(
            directory=repo.directory,
            error_fn=print,
            ignore_missing=True,
        )
        repo_cache_store.refresh_remote_from_directory(
            directory=repo.directory,
            error_fn=print,
            force=force,
        )
        return True
    except Exception as ex:
        print("Taiyo Extension Manager: cache refresh skipped:", ex)
        return False


def _sync_repo_safely(context, repo, repo_index, report_fn=None):
    if repo is None:
        return False

    synced = False
    try:
        if bpy.ops.extensions.repo_sync.poll():
            bpy.ops.extensions.repo_sync(repo_directory=repo.directory)
            synced = True
    except Exception as ex:
        if report_fn:
            report_fn({"WARNING"}, "Remote sync skipped: {:s}".format(str(ex)))
        else:
            print("Taiyo Extension Manager: remote sync skipped:", ex)

    _refresh_repo_cache(repo, force=True)
    return synced


def _package_rows(repo):
    local_manifest, remote_manifest = _repo_manifests(repo)
    pkg_ids = sorted(set(local_manifest.keys()) | set(remote_manifest.keys()))

    rows = []
    for pkg_id in pkg_ids:
        item_local = local_manifest.get(pkg_id)
        item_remote = remote_manifest.get(pkg_id)
        item = item_remote or item_local
        if item is None or _value(item, "type", "add-on") != "add-on":
            continue

        tags = _tags_for(pkg_id, item)
        installed, enabled = _package_state(repo, pkg_id, item_local)
        rows.append(
            {
                "id": pkg_id,
                "item": item,
                "local": item_local,
                "remote": item_remote,
                "name": _value(item, "name", pkg_id),
                "tagline": _value(item, "tagline", ""),
                "version": _value(item, "version", ""),
                "local_version": _value(item_local, "version", ""),
                "tags": tags,
                "search_text": _search_text_for(pkg_id, item, tags),
                "installed": installed,
                "enabled": enabled,
                "outdated": _is_outdated(item_local, item_remote),
            }
        )

    return rows


def _status_matches(row, status_filter):
    if status_filter == "INSTALLED":
        return row["installed"]
    if status_filter == "ENABLED":
        return row["installed"] and row["enabled"]
    if status_filter == "DISABLED":
        return row["installed"] and not row["enabled"]
    if status_filter == "AVAILABLE":
        return not row["installed"]
    if status_filter == "UPDATES":
        return row["outdated"]
    return True


def _filtered_rows(rows, search, tag_filter, status_filter):
    search = (search or "").strip().casefold()
    tag_terms = [term.casefold() for term in (tag_filter or "").replace(",", " ").split() if term.strip()]

    visible = []
    for row in rows:
        if not _status_matches(row, status_filter):
            continue
        if search and search not in row["search_text"]:
            continue
        if tag_terms and not all(any(term in tag for tag in row["tags"]) for term in tag_terms):
            continue
        visible.append(row)

    return visible


def _auto_sync_once():
    global _AUTO_SYNC_DONE

    if _AUTO_SYNC_DONE:
        return None
    _AUTO_SYNC_DONE = True

    context = bpy.context
    prefs = _addon_prefs(context)
    if prefs is None or not prefs.auto_sync:
        return None

    repo, repo_index = _find_taiyo_repo(context)
    if repo is None:
        return None

    _sync_repo_safely(context, repo, repo_index)

    return None


class TAYMAN_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or __name__

    language: EnumProperty(
        name="Language",
        description="Language used in the Taiyo Extension Manager panel",
        items=[
            ("AUTO", "Auto", "Use the language from each extension manifest"),
            ("JA", "日本語", "Prefer Japanese when available"),
            ("EN", "English", "Prefer English when available"),
        ],
        default="AUTO",
    )
    auto_sync: BoolProperty(
        name="Auto Sync",
        description="Sync the Taiyo repository automatically once when Blender starts",
        default=True,
    )
    show_tags: BoolProperty(
        name="Show Tags",
        description="Show compact tag text under each extension",
        default=False,
    )
    show_descriptions: BoolProperty(
        name="Show Descriptions",
        description="Show one compact description line for each extension",
        default=True,
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "language")
        layout.prop(self, "auto_sync")
        layout.prop(self, "show_descriptions")
        layout.prop(self, "show_tags")
        op = layout.operator("wm.url_open", text="GitHub Repository", icon="URL")
        op.url = GITHUB_REPO_URL
        op = layout.operator("wm.url_open", text="Manager Manual", icon="HELP")
        op.url = DOCUMENTATION_URL


class TAYMAN_OT_AddRepository(Operator):
    bl_idname = "tayman.add_repository"
    bl_label = "Add Taiyo Repository"
    bl_description = "Add the Taiyo Blender Scripts remote repository to Blender"
    bl_options = {"REGISTER"}

    def execute(self, context):
        repo, repo_index = _find_taiyo_repo(context)
        if repo is not None:
            self.report({"INFO"}, "Taiyo repository is already registered.")
        else:
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
            _repo, repo_index = _find_taiyo_repo(context)

        if repo is not None:
            _sync_repo_safely(context, repo, repo_index, self.report)

        self.report({"INFO"}, "Taiyo repository is ready.")
        return {"FINISHED"}


class TAYMAN_OT_RefreshRepository(Operator):
    bl_idname = "tayman.refresh_repository"
    bl_label = "Refresh Taiyo Repository"
    bl_description = "Safely sync and reload the Taiyo repository package list"
    bl_options = {"REGISTER"}

    def execute(self, context):
        repo, repo_index = _find_taiyo_repo(context)
        if repo is None:
            self.report({"ERROR"}, "Taiyo repository is not registered.")
            return {"CANCELLED"}

        _sync_repo_safely(context, repo, repo_index, self.report)
        self.report({"INFO"}, "Reloaded Taiyo repository.")
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

        if self.pkg_id == SELF_ID and self.action == "DISABLE":
            self.report({"WARNING"}, "The manager cannot disable itself from this panel.")
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
        if self.pkg_id == SELF_ID:
            self.report({"WARNING"}, "The manager cannot uninstall itself from this panel.")
            return {"CANCELLED"}

        repo, repo_index = _find_taiyo_repo(context)
        if repo is None:
            self.report({"ERROR"}, "Taiyo repository is not registered.")
            return {"CANCELLED"}

        result = bpy.ops.extensions.package_uninstall(repo_directory=repo.directory, pkg_id=self.pkg_id)
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
        layout.use_property_split = False
        layout.use_property_decorate = False

        wm = context.window_manager
        prefs = _addon_prefs(context)
        repo, repo_index = _find_taiyo_repo(context)

        toolbar = layout.row(align=True)
        toolbar.operator("wm.url_open", text="GitHub", icon="URL").url = GITHUB_REPO_URL
        toolbar.operator("wm.url_open", text="Manual", icon="HELP").url = DOCUMENTATION_URL
        toolbar.operator("tayman.copy_repository_url", text="", icon="COPYDOWN")

        if prefs:
            prefs_row = layout.row(align=True)
            prefs_row.prop(prefs, "language", text="")
            prefs_row.prop(prefs, "auto_sync", text="", icon="FILE_REFRESH")

        repo_box = layout.box()
        row = repo_box.row(align=True)
        row.label(text=REPO_NAME, icon="URL")

        if repo is None:
            repo_box.label(text="Repository not registered.", icon="ERROR")
            repo_box.operator("tayman.add_repository", text="Add Repository", icon="ADD")
            return

        row.label(text="Ready", icon="CHECKMARK")
        row.operator("tayman.refresh_repository", text="", icon="FILE_REFRESH")

        filters = layout.box()
        filters.prop(wm, "tayman_search", text="", icon="VIEWZOOM")
        filters.prop(wm, "tayman_tag_filter", text="Tag")
        filters.prop(wm, "tayman_status_filter", text="Status")

        rows = _package_rows(repo)
        visible_rows = _filtered_rows(
            rows,
            wm.tayman_search,
            wm.tayman_tag_filter,
            wm.tayman_status_filter,
        )
        installed_count = sum(1 for row_data in rows if row_data["installed"])
        update_count = sum(1 for row_data in rows if row_data["outdated"])

        summary = layout.row(align=True)
        summary.label(text="{:d}/{:d} installed".format(installed_count, len(rows)), icon="PACKAGE")
        if update_count:
            summary.label(text="{:d} update".format(update_count), icon="IMPORT")
        summary.label(text="{:d} shown".format(len(visible_rows)), icon="FILTER")

        if not rows:
            layout.label(text="Press Refresh to load package data.", icon="INFO")
            return

        if not visible_rows:
            layout.label(text="No matching extensions.", icon="INFO")
            return

        for row_data in visible_rows:
            self._draw_package(layout, repo, row_data, prefs)

    def _draw_package(self, layout, repo, row_data, prefs):
        item = row_data["item"]
        pkg_id = row_data["id"]
        installed = row_data["installed"]
        enabled = row_data["enabled"]
        outdated = row_data["outdated"]

        box = layout.box()
        header = box.row(align=True)
        header.scale_y = 0.85
        header.label(text=row_data["name"], icon="PLUGIN")

        version_text = "v{:s}".format(row_data["version"])
        if outdated:
            version_text = "v{:s} -> {:s}".format(row_data["local_version"], row_data["version"])
        header.label(text=version_text)

        if prefs is None or prefs.show_descriptions:
            desc = _description_for(pkg_id, row_data["tagline"], prefs)
            if desc:
                desc_row = box.row()
                desc_row.scale_y = 0.75
                desc_row.label(text=desc[:92])

        if prefs and prefs.show_tags and row_data["tags"]:
            tag_row = box.row()
            tag_row.scale_y = 0.7
            tag_row.label(text="tags: " + " / ".join(row_data["tags"][:8]))

        status = box.row(align=True)
        status.scale_y = 0.85
        if outdated:
            status.label(text="Update available", icon="IMPORT")
        elif installed and enabled:
            status.label(text="Installed", icon="CHECKMARK")
        elif installed:
            status.label(text="Disabled", icon="PAUSE")
        else:
            status.label(text="Available", icon="ADD")

        links = status.row(align=True)
        links.alignment = "RIGHT"
        links.operator("wm.url_open", text="GitHub", icon="URL").url = _source_url(pkg_id)
        links.operator("wm.url_open", text="Manual", icon="HELP").url = _manual_url(pkg_id, item)

        actions = box.row(align=True)
        actions.scale_y = 0.9

        if installed:
            if outdated:
                op = actions.operator("extensions.package_install", text="Update", icon="IMPORT")
                op.repo_directory = repo.directory
                op.pkg_id = pkg_id
                op.enable_on_install = True

            if pkg_id != SELF_ID:
                op = actions.operator(
                    "tayman.set_addon_enabled",
                    text="Disable" if enabled else "Enable",
                    icon="HIDE_ON" if enabled else "HIDE_OFF",
                )
                op.pkg_id = pkg_id
                op.action = "DISABLE" if enabled else "ENABLE"

                op = actions.operator("tayman.uninstall_package", text="Uninstall", icon="TRASH")
                op.pkg_id = pkg_id
            else:
                actions.label(text="Manager", icon="LOCKED")
        else:
            op = actions.operator("extensions.package_install", text="Install", icon="IMPORT")
            op.repo_directory = repo.directory
            op.pkg_id = pkg_id
            op.enable_on_install = True

        archive = _archive_url(item)
        if archive:
            actions.operator("wm.url_open", text="", icon="DOWNARROW_HLT").url = archive


classes = (
    TAYMAN_AddonPreferences,
    TAYMAN_OT_AddRepository,
    TAYMAN_OT_RefreshRepository,
    TAYMAN_OT_CopyRepositoryURL,
    TAYMAN_OT_SetAddonEnabled,
    TAYMAN_OT_UninstallPackage,
    TAYMAN_PT_Manager,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.WindowManager.tayman_search = StringProperty(
        name="Search",
        description="Search by name, id, description, or inferred tags",
        default="",
    )
    bpy.types.WindowManager.tayman_tag_filter = StringProperty(
        name="Tag",
        description="Filter by tags such as csv, export, uv, unreal, collection, 名前整理, 衝突",
        default="",
    )
    bpy.types.WindowManager.tayman_status_filter = EnumProperty(
        name="Status",
        description="Filter extensions by install/update state",
        items=[
            ("ALL", "All", "Show all extensions"),
            ("INSTALLED", "Installed", "Show installed extensions"),
            ("ENABLED", "Enabled", "Show installed and enabled extensions"),
            ("DISABLED", "Disabled", "Show installed but disabled extensions"),
            ("AVAILABLE", "Available", "Show extensions not installed yet"),
            ("UPDATES", "Updates", "Show installed extensions with updates"),
        ],
        default="ALL",
    )

    if not bpy.app.background:
        bpy.app.timers.register(_auto_sync_once, first_interval=2.0)


def unregister():
    if hasattr(bpy.types.WindowManager, "tayman_status_filter"):
        del bpy.types.WindowManager.tayman_status_filter
    if hasattr(bpy.types.WindowManager, "tayman_tag_filter"):
        del bpy.types.WindowManager.tayman_tag_filter
    if hasattr(bpy.types.WindowManager, "tayman_search"):
        del bpy.types.WindowManager.tayman_search

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
