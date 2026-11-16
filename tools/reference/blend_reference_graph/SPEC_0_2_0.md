# Blend Reference Graph 0.2.0 仕様書(実装担当: Codex / レビュー: Claude)

対象: `_Taiyo_Blender_Extensions_Repo/blend_reference_graph/`(現行 0.1.5、Blender 4.2以上、最低動作確認 4.5.9)。
Blender実行ファイル: `/Applications/Blender4.5.9.app/Contents/MacOS/Blender`(PATHに `blender` は無い)。

## 0. 作業ルール(必ず守る)
- 作業ブランチは `feature/brg-whole-file`。**commit / push / ブランチ切替はしない**(Claudeが行う)。
- 触ってよい範囲は、各タスクに書かれたファイルだけ。`_legacy_single_file_addons/`、他のExtension、`docs/extensions/` は触らない。
- 既存の公開名(関数名・Operator idname・HTML要素id・JS関数名)は**消さない/改名しない**。追加のみ。既存テスト `tools/test_blend_reference_graph.py` は `viewer.js/html/css` の文字列を部分一致で検査するため、改名すると落ちる。
- 既存のNode IDは、localデータでは変えない(`Object:Name` 等)。
- Blender起動は直接実行する(`tools/build_extensions.sh` 経由はしない。Codex sandbox内ではMetal初期化でsegfaultすることがある)。Blenderが落ちる/起動できない場合は、**推測で直さず**、その旨と出力をそのまま報告する。
- Blender 4.5では `event.timer` は無い。Modalは `event.type == "TIMER"`。`register()` 内で `bpy.data.scenes` を走査しない(`_RestrictData`)。
- `bpy.ops` をPythonから呼んでもUndoは積まれない(`'EXEC_DEFAULT', True` が必要)。この機能はUndoを必要としない(読み取り専用スキャン)。
- 生成物(`__pycache__`、`.pyc`、`.DS_Store`)を残さない。
- テストの名前照合は**厳密一致**で書く(`in` の部分一致は `X.001` で誤合格する)。
- 日本語でREADMEを書く。コード中のコメントは最小限。
- 仕様と食い違う点・できなかった点は、勝手に仕様を変えず、最後の報告に必ず書く。

## 0b. 実行単位(最重要)
この仕様書は A / D / B / C の4タスクを含むが、**Codexには1回の実行で1タスクだけ**を頼む。プロンプトに書かれたタスク以外は、この仕様書に書いてあっても**実装しない**。ファイルは、そのタスクの「ファイル:」に列挙されたものだけを触る。終わったら止まって報告する(次のタスクへ進まない)。順序: A → D → B → C。

## 0c. 実行環境の注意
- Codex sandbox(workspace-write)では、Blenderが起動できない/落ちる、ローカルソケットを開けない、システムtempへ書けない場合がある。**環境が原因で失敗したテストは、コードを曲げて回避せず、出力をそのまま報告する**。Claudeが後で実行して検証する。
- 一時ファイルはリポジトリ内の無視されるフォルダではなく、テスト内で `tempfile` を使う。リポジトリに生成物を残さない。

## 1. 全体像
2つの新機能。
1. **Whole File スキャン**: 開いている .blend 全体(全データブロック+主要な内部参照)を1つのグラフにする。時間がかかってよい。Blenderを固めない(進捗表示つきmodal)。
2. **Live Viewer 再スキャン**: ブラウザのビューアで選んだノードを中心に、Blenderへ再スキャンを依頼し、結果を同じビューアに反映する。

ビューアは種類別クラスタ(概要モード)で全体を表示し、クリックで展開する。

## 2. データモデル(`graph/graph_model.py` ほか)
- `GraphData.add_node(..., group=None)` を追加。`group` は種類クラスタ名(既定は `type`)。ペイロードの各ノードに `"group"` を含める。既存引数は互換。
- 新ノード型(追加のみ): `SCENE` `WORLD` `CAMERA` `LIGHT` `CURVE` `TEXT` `FONT` `SOUND` `PARTICLE` `TEXTURE` `OTHER`。
- `ALL_FILTERS` と ビューアの `colors` / `typeOrder` にも追加(忘れるとグレー)。
- `meta` に追加: `scope`(`"TARGET"` / `"WHOLE_FILE"` / `"NODE"`)、`version`(`version.py` から)、`scan_seconds`、`type_counts`(型→件数)、`truncated`(上限で打ち切った項目の説明リスト。無ければ空)。
- **ノードID**: `scanner/id_utils.py`(新規)に `id_key(idblock)` — localは `name`、linked(`library` あり)は `f"{name} [lib:{library.name}]"`(`library.name` は `bpy.data.libraries` 内で一意。ファイル名のbasenameは同名別フォルダで衝突するので使わない)。既存の `object_id/mesh_id/collection_id/armature_id/node_group_id` と animation/geonodes の `Material:` `Image:` `Action:` 等のID生成をこれ経由にする。**localのIDは従来と同じ文字列のまま**。
- `graph_exporter.export_graph_data` は `compact: bool` 引数を取り、`compact=True` のとき `indent=None, separators=(",", ":")`(`graph_data.json` と `.js` 両方)。Whole File / ノード中心スキャンは `compact=True`。

## 3. タスク A: Python バックエンド(Whole File スキャン)
ファイル: `scanner/id_utils.py`(新), `scanner/whole_file_scanner.py`(新), `scanner/*.py`(id_key化), `graph/graph_model.py`, `graph/graph_exporter.py`, `graph/graph_builder.py`, `graph/__init__.py`, `properties.py`, `version.py`(新), `operators.py`, `panels.py`, `__init__.py`, `blender_manifest.toml`(versionのみ 0.2.0 へ), `tools/test_blend_reference_graph_whole_file.py`(新)。

### 3.1 `version.py`
`VERSION = "0.2.0"` と `VERSION_TUPLE = (0, 2, 0)`。`operators.py` のハードコード `"0.1.5"`、`__init__.py` の `bl_info["version"]`、`blender_manifest.toml` の `version` を 0.2.0 へ揃える(bl_infoは `register` 前に評価されるためタプルを直書きでよいが、テストで3箇所の一致を確認する)。

### 3.2 `scanner/whole_file_scanner.py`
```python
class ScanOptions: include_internals=True; include_bones=False; max_bones=2000; node_limit_per_type=None
def iter_scan(graph, options) -> Iterator[tuple[float, str]]   # 進捗(0.0-1.0)とメッセージをyield。呼び出し側が時間予算で進める
def run_to_end(graph, options)                                  # テスト用: 最後まで回す
```
段階(各段階の途中でも適宜 yield。1回のyield間の仕事量は数千要素程度に抑える):
1. **ノード作成**: 下表のIDコレクションを走査し、`group` と `details`(`users` `use_fake_user` `orphan`=`users==0 and not use_fake_user`、linked時 `library`)を持つノードを作る。埋め込みID(`idblock.is_embedded_data` が真。Material/World/Light/Textureの `node_tree`、Sceneの compositor 等)は独立ノードにしない。**`node_tree.id_data` は所有者ではなくnode_tree自身を返す(Blender 4.5.9で確認済み)ので使わない。** 所有者辞書 `embedded_owner` を1回だけ作る(`materials/worlds/lights/textures/linestyles/scenes` の `.node_tree`、存在すれば `scenes[*].compositing_node_group`、`.grease_pencils` など)。`user_map` が返す埋め込みIDは、この辞書で所有者IDへ付け替えてからエッジにする。`WindowManager` / `WorkSpace` / `Screen` はユーザーデータではないので、`user_map` のキーにも使用側にも**出さない**(これらはノード化せず、エッジも作らない)。
2. **エッジ**: `bpy.data.user_map()` を**1回**呼ぶ(`value` = そのIDを使うIDの集合)。`user → id` のエッジを作る。relation は既定 `references`、label は `uses`。既知の組(Object→Mesh/Curve/Armature等のdata=`uses_data`、Collection→Object=`contains`、Collection→Collection=`child_collection`、Object→Material=`uses_material`、Scene→Collection、Object→Object親子=`child_of`)は適切なrelationとlabelに洗練する。自己参照(所有者へ付け替えた後の自己ループを含む)は捨てる。
3. **内部参照**(`include_internals`):各Objectに対し既存の `constraint_scanner.add_object_constraints` / `geonodes_scanner.add_geometry_nodes_modifiers` / `animation_scanner.add_object_animation_refs`(driver) を再利用。`include_bones` がTrueのときだけ `object_scanner.add_armature_and_bones`。Boneは合計 `max_bones` 件で打ち切り、`meta.truncated` に記録。
4. **Library**: `library_scanner.add_library_links_for_graph`(対象型の表を新ノード型に合わせて拡張。名前だけでなく `id_key` で解決)。

| グループ(type) | bpy.data コレクション |
|---|---|
| OBJECT | objects |
| MESH | meshes |
| ARMATURE | armatures |
| CURVE | curves, metaballs, lattices, grease_pencils(存在すれば) |
| COLLECTION | collections |
| MATERIAL | materials |
| IMAGE | images |
| NODEGROUP | node_groups |
| ACTION | actions |
| SCENE | scenes |
| WORLD | worlds |
| CAMERA | cameras |
| LIGHT | lights |
| TEXT | texts |
| FONT | fonts |
| SOUND | sounds |
| PARTICLE | particles |
| TEXTURE | textures |
| LIBRARY | libraries |
| OTHER | 上記以外で存在するID(`brushes` `palettes` `workspaces`は除外。ユーザー資産ではないため) |

コレクションが存在しないBlenderバージョン(`grease_pencils` 等)は `getattr(bpy.data, name, None)` で飛ばす。Blender 4.2〜5.x の差で落ちないこと。

### 3.2b 性能上の必須事項(既存スキャナを全Objectへ再利用するための前提)
既存スキャナは「1 target用」の作りで、そのまま全Objectに回すと遅い。以下を必ず直す(単一targetの挙動は変えない)。
- `object_scanner.add_object_node` は `add_node` が重複を弾く**前**に `object_collection_paths(obj)`(全sceneのCollection木を毎回走査)を呼ぶ。→ ノードが既にあれば**先に return**。さらに、スキャン1回につき **Collection→パス一覧のマップを1度だけ**作り(`path_utils` に `CollectionPathCache` のようなものを追加し、`add_object_node` / `add_collection_node` が任意で受け取る。未指定なら従来どおりの走査)、Whole File/ノード中心スキャンはそれを使う。
- `geonodes_scanner.add_node_group_internal_refs` は呼び出しごとに `visited` を作り直す。→ 同じnode groupを使う2万Objectで毎回再走査になる。**スキャン全体で共有する `visited`**(引数で渡す。未指定なら従来どおり)にする。
- `animation_scanner` の `_iter_animation_owners` / `add_incoming_driver_users` など全Object走査の箇所をWhole Fileから**繰り返し呼ばない**(Whole Fileでは全Objectを1回だけ走査する専用経路にする)。
- Whole File全体で `obj.name in scene.objects` や Objectごとの `users_collection` の繰り返しを避ける(AGENTS.mdにある既知の遅さ)。Collectionの所属は `collection.objects` を1回ずつ走査して辞書化する。
- 目標の目安: Object 2万・Material 1千でスキャン完了までに主スレッドが1回に占有する時間が約30msを超えないよう、適切な粒度でyieldする(超える箇所はベンチで報告)。

### 3.3 ノード中心スキャン `graph_builder.build_node_graph(context, node_id, mode, depth, options)`(ジェネレータ版 `iter_build_node_graph`)
- node_id の先頭が `Object:` → 既存の `build_graph` 相当(`_expand_object`)を使う(Boneは `Bone:<armature>:<bone>` で既存のBone経路)。
- それ以外の型 → Whole Fileの「ノード作成+エッジ」を全体で作ったのち、node_idから**BFS**(`mode`: `USES`=出方向、`USED_BY`=入方向、`BOTH`、`depth` 1〜5)で部分グラフを切り出す。起点が見つからなければ `ValueError("Node not found: ...")`。
- どちらも `meta.target_id=node_id`、`meta.scope="NODE"`。Safe Deleteノードは従来どおりtarget範囲で付ける。
- node_id → データブロックの解決は `scanner/id_utils.py` の `resolve_node_id(node_id)`(`id_key` の逆引き。大量のIDでも1回の辞書構築で済むようにする)。

### 3.4 Operator `brg.scan_whole_file`(modal)
- `bl_options = {"REGISTER"}`。`invoke` でジェネレータ作成、`window_manager.event_timer_add(0.05)`、`wm.progress_begin(0, 100)`。
- `modal`: `event.type == "TIMER"` のたびに **時間予算 約30ms** だけ `next()` で進める。進捗を `wm.progress_update` と `settings.status_message` に反映し、エリアを再描画。`ESC` または `RIGHTMOUSE` でキャンセル(何も書き出さず、`status_message="Cancelled"`)。
- 完了時: `meta` を作り(`scan_seconds` 含む)`export_graph_data(..., compact=True)`、ビューアファイルをコピー、`settings` のカウント更新。`settings.open_viewer_after_scan` が真ならビューアを開く(Live Viewerが有効ならそのURL。§4)。
- 例外は `report({"ERROR"}, ...)`、`progress_end` と timer解除を `finally` で必ず行う。
- Properties(`BRG_Settings`に追加): `include_internals`(既定True) / `include_bones`(既定False) / `max_bones`(既定2000, 100〜50000) / `open_viewer_after_scan`(既定True) / `scan_progress`(0-100, 表示用)。
- Panel: 既存ボックスは変更しない。新ボックス「Whole File」に上記プロパティ、`brg.scan_whole_file` ボタン、進捗/件数/所要時間。

### 3.5 テスト `tools/test_blend_reference_graph_whole_file.py`
`blender --background --factory-startup --python-exit-code 1 --python tools/test_blend_reference_graph_whole_file.py` で通ること。内容:
- 全グループ(OBJECT/MESH/COLLECTION/MATERIAL/IMAGE/NODEGROUP/ACTION/SCENE/WORLD/CAMERA/LIGHT/CURVE/TEXT/FONT/SOUND/PARTICLE/TEXTURE)のダミーIDを作り、**全てノード化**されること。
- `user_map` 由来のエッジ(Object→Mesh、Collection→Object、Material使用 等)が出ること。ダングリングエッジが無いこと。
- orphan: users==0のMaterialは `details.orphan == True`、fake user付きは False。
- linked同名の衝突: 別の一時 .blend を `bpy.data.libraries.write` で作って `libraries.load(link=True)` し、同名のlocalとlinkedの両方がノード化されIDが異なること(`Name` と `Name [lib:<library.name>]`)。
- `include_internals` ON/OFF で constraint/modifier/driver ノードの有無が変わること。`include_bones` と `max_bones` による打ち切りと `meta.truncated`。
- ジェネレータの途中で止めてもグラフが壊れず、何も書き出されないこと(ESC相当)。
- `build_node_graph` が Object起点と 非Object起点(Material)の両方で、`mode` と `depth` に応じた部分グラフを返し、不正node_idで `ValueError`。
- ペイロード: `compact` のJSONがパース可能で `group` を持つ。
- version 3箇所(version.py / bl_info / manifest)の一致。
- 既存 `tools/test_blend_reference_graph.py` も通ること。

## 4. タスク D: Live Viewer(ローカルHTTPサーバー + 再スキャン)
ファイル: `live/__init__.py`, `live/server.py`, `live/controller.py`(新), `operators.py`, `panels.py`, `properties.py`, `__init__.py`, `blender_manifest.toml`(`[permissions]` 追加), `tools/test_blend_reference_graph_live_server.py`(新)。

### 4.1 サーバー(`live/server.py`)
- `http.server.ThreadingHTTPServer` を **`127.0.0.1` のみ**にバインド(ポートは空きポートをOSに選ばせる `("127.0.0.1", 0)`)。デーモンスレッド。
- 起動時にランダムtoken(`secrets.token_urlsafe(24)`)。URL: `http://127.0.0.1:<port>/<token>/viewer.html`。tokenが違うパスは**403**。
- **Hostヘッダ検証**(`127.0.0.1:<port>` か `localhost:<port>` のみ。違えば **421**。DNS rebinding対策)。**POSTはOriginヘッダ検証**(無い or `http://127.0.0.1:<port>` / `http://localhost:<port>` のみ許可。違えば **403**)。
- 静的配信は**許可リスト**のみ: `viewer.html` `viewer.css` `viewer.js` `graph_data.js` `graph_data.json`(出力フォルダから)。他は **404**。ディレクトリトラバーサル不可。`Cache-Control: no-store`。
- API(JSON、`Content-Type: application/json`):
  - `GET  /<token>/api/status` → `{"state": "idle|queued|running|done|error|cancelled", "progress": 0-1, "message": str, "request_id": int, "error": str|null, "version": "0.2.0"}`
  - `POST /<token>/api/rescan` 本文 `{"scope": "NODE"|"WHOLE_FILE", "node_id": str, "mode": "USES"|"USED_BY"|"BOTH", "depth": 1-5}`。本文サイズ上限 16KB(超過は **413**)、スキーマ検証(不正は **400** と理由)。実行中/待機中は **409**。受理は **202** と `{"request_id": n}`。
  - `POST /<token>/api/cancel` → 実行中のスキャンを取り消す。
- サーバーはBlender APIに**一切触らない**。リクエストを `queue.Queue` / ロック付き状態へ入れるだけ。

### 4.2 コントローラ(`live/controller.py`)
- `start(context)` / `stop()` / `is_running()` / `url()`、`pump()`。
- `pump()` は `bpy.app.timers.register(pump, first_interval=0.1, persistent=True)` で定期実行(サーバー起動中のみ。`stop()` で解除)。1回の呼び出しで **約30ms** だけジェネレータを進め、状態(progress/message)を更新。完了したら `export_graph_data(compact=True)` と `meta` 書き出し、state=`done`。例外は state=`error`。`pump()` は**テストから直接呼べる**素の関数にする(戻り値は次回実行までの秒数 or None)。
- スキャンは §3 の `iter_scan` / `iter_build_node_graph` を再利用。`scope=WHOLE_FILE` は Whole File、`NODE` はノード中心。
- 停止タイミング: パネルの「Stop Live Viewer」、アドオン `unregister()`、`bpy.app.handlers.load_pre`(別のblendを開く前。古いデータを見せない)。再起動時にtokenとポートは新しくなる。
- 起動の設定: アドオン設定に `live_viewer`(既定True)を追加。**Falseなら従来どおり `file://` で開く**(ボタンはビューア側で無効化)。

### 4.3 Operators / Panel
- `brg.open_viewer` / `brg.update_and_open_viewer` / `brg.scan_whole_file` の完了時: `live_viewer` が真ならサーバーを起動(未起動なら)してそのURLを `webbrowser.open`、偽なら従来の `file://`。
- 新 Operator `brg.stop_live_viewer`。パネルに Live Viewer の状態(URL/稼働中)と停止ボタン。
- **`blender_manifest.toml`** に `[permissions]` を追加。`map_roundtrip_tools/blender_manifest.toml` の形式を確認し同じ書き方で、理由文は**短く**(目安 64文字以内、末尾に句読点を付けない。例: `network = "Local viewer server on 127.0.0.1"`)。長さや末尾の制約は `extension validate` を正とし、通らなければ短くする。`blender --background --command extension validate` が通ること。

### 4.4 テスト `tools/test_blend_reference_graph_live_server.py`
バックグラウンドBlenderではタイマーが回らないため、**別スレッドからHTTPを打ち、主スレッドで `controller.pump()` を回す**形にする。確認項目: 正常系(Object中心/Material中心/WHOLE_FILE の rescan→`/api/status`がdone→`graph_data.js` に `scope` と `target_id` が反映)、token誤り403、Host不正421、Origin不正403、許可外パス404、トラバーサル404、本文サイズ413、不正本文400、実行中409、cancel、不正node_idで state=`error` かつ message、`stop()` 後に接続できないこと、`127.0.0.1` 以外で待ち受けていないこと(`getsockname`)。

## 5. タスク B: ビューア(概要モード + 再スキャンUI)
ファイル: `html/viewer.html` `html/viewer.css` `html/viewer.js`。**既存の単一target表示(`meta.scope` が無い/`TARGET`/`NODE`)の見た目と挙動は変えない。** `meta.scope === "WHOLE_FILE"` のときだけ概要モード。

### 5.1 概要モード
- 種類(`node.group`)ごとの大きな箱(種類名・件数・orphan件数)を `typeOrder` に従ってグリッド配置。クリックで展開/折りたたみ。展開すると中身を固定列数のグリッドで表示。1クラスタの表示上限は 500件(超過分は「+N more — use filter/search」と表示し、検索ヒットや選択は上限外でも描画に含める)。
- 折りたたみ中は箱同士のエッジを件数で集約(線の太さ=件数、ラベル=件数)。展開中の箱の内側のノード同士は実エッジ。他の箱とのエッジは「表示中ノード」と「集約箱」の間に描く。
- 凡例を**型フィルター**(チェックボックス)に。「Orphanのみ」トグル。「すべて展開/すべて折りたたみ」。
- 既存の検索/Details/JSON出力/選択/ボックス選択/パン・ズームは概要モードでも動作。検索ヒットのあるクラスタは自動展開して該当ノードへフォーカス。

### 5.2 性能(既存の問題の解消も含む。目標: 2万ノード/6万エッジの合成データでFit・展開・検索・ドラッグが実用速度)
- id→DOM要素 / id→隣接エッジ の `Map` を作り、`nodeElement` / `updateEdgesForNode` / `refreshSelection` の `querySelectorAll` 全走査をやめる。
- 検索は事前に小文字化したインデックス(`name`/`type`/`path`/`details`値を連結)を1度だけ作って `includes`。
- 描画するのは表示中のノードとそのエッジだけ。ズームが小さい(`scale < 0.5`)ときはエッジラベルとノードの副テキストを描かない/非表示(CSSクラスで一括切替)。
- `fitView` の最小スケール(0.22)制限は概要モードでは緩和(0.02まで)、ズームの下限も同様。
- 重い処理で画面が固まらないよう、展開時の描画はチャンクで(`requestAnimationFrame` 等)。

### 5.3 Live Viewer 連携UI(`meta.scope` に関わらず、サーバー経由で開いている時のみ有効)
- ツールバーに: **「Re-scan from selection」**(ちょうど1ノード選択中のみ有効、キー `R`)、`mode` セレクト(Uses/Used By/Both)、`depth` セレクト(1〜5)、**「Whole file」**、**「Back」**。
- 「Re-scan from selection」→ `POST api/rescan {scope:"NODE", node_id, mode, depth}`。受理後 `GET api/status` を0.5秒間隔でポーリングし、進捗とメッセージを表示、`done` で `location.reload()`、`error` ならメッセージ表示(ビューアは壊さない)。「Whole file」は `scope:"WHOLE_FILE"`。「Back」は直前のリクエストを `sessionStorage` の履歴(最大20件)から再実行。スキャン中は「キャンセル」で `api/cancel`。
- `file://` で開いている/サーバーが無い場合は、これらのボタンを `disabled` にしてツールチップとヒント(「Blender の Live Viewer で開くと使えます」)を出す。判定は `location.protocol === "http:"` かつ `api/status` が200。
- 既存のキーボードショートカット(`/ f b n p h j k l + - 0 Space Esc`)と衝突しないこと。`R` は検索入力中は無効。
- 新要素のidは `rescan-node` `rescan-mode` `rescan-depth` `rescan-whole` `rescan-back` `rescan-status`。

### 5.4 検証(タスクBの完了条件)
- `tools/test_blend_reference_graph.py` の文字列検査が通る(既存の関数名・idを残す)。
- 合成データ生成スクリプト `tools/reference/blend_reference_graph/make_synthetic_graph.py`(2万ノード/6万エッジの `graph_data.js` を出力、`scope: "WHOLE_FILE"`)を作る。ビューアはClaudeがブラウザで実機確認するため、Codexは JS構文チェック(`node --check` が使えれば)まで。

## 6. タスク C: ドキュメント・ベンチ
ファイル: `README.md`(blend_reference_graph), `tools/benchmark_blend_reference_graph_whole_file.py`(新)。
- READMEに対象version(0.2.0)を明記し、Whole Fileの使い方・範囲・限界(巨大blendは時間がかかる、Bone上限、検出しない参照:ViewLayer・Modifier内の一部など、Safe Deleteは従来どおりtarget範囲のみ)、Live Viewer(ローカルのみ・token・外部送信なし・`network`権限の理由・`file://`では再スキャン不可)、ビューアの新操作とショートカット `R` を日本語で書く。0.2.0は後方互換あり(過去バージョン節は不要)。
- ベンチ: `--python` 引数で件数を変えられる(既定: Object 2万 / Material 1千)。`iter_scan` の所要時間、yield回数と最大yield間隔、JSONサイズ、`user_map` の時間と内訳を出力。数値は推測で書かず、実測値だけを報告に書く。

## 7. 受け入れ基準(まとめ)
- 3つのテスト(既存/Whole File/Live Server)が `--factory-startup --python-exit-code 1` で全通過。
- `blender --background --factory-startup --command extension validate _Taiyo_Blender_Extensions_Repo/blend_reference_graph` が通る(または、Blenderが落ちる場合は報告)。
- 既存機能(Use Selected / Update Graph Data / Open Viewer / Update + Open Viewer)が従来どおり動く。
- 最後の報告に: 変更ファイル一覧、実行したコマンドと結果(そのまま)、仕様と違う点、できなかった点。
