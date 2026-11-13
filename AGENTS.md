# AGENTS.md

このファイルは、Codex や他のエージェントがこのワークスペースで作業するときに最初に参照する運用メモです。新しく分かった注意点や、次回以降に守ってほしいことはここへ追記してください。

## このリポジトリの目的

- これは Taiyo のBlender Extensions配布リポジトリです。
- GitHub Pagesで `docs/extensions/index.json` を公開し、Blender 4.2以降の Remote Repository として使います。
- Blender の Remote Repository には GitHub リポジトリURLではなく、配布用 `index.json` のURLを登録します。
- Remote Repository URL:

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

## 現在の基本構造

```text
repo/
├─ docs/extensions/                 # GitHub Pagesで公開する配布物
├─ _Taiyo_Blender_Extensions_Repo/   # Extension zipを作る元データ
├─ tools/                           # ビルドスクリプト
├─ _legacy_single_file_addons/       # 旧・単体.py版の保管場所
├─ README.md
└─ AGENTS.md
```

## 編集時の基本方針

- 通常の修正対象は `_Taiyo_Blender_Extensions_Repo/*` です。ここをBlender Extensions用の source of truth として扱います。
- 配布対象は `_Taiyo_Blender_Extensions_Repo` 内の現行版です。旧版、バックアップ、キャッシュ、作業中ファイルをzipに含めないでください。
- `_legacy_single_file_addons` は旧形式の単体 `.py` インストール用アドオンの保管場所です。Remote Repository運用では使いません。ユーザーから明示されない限り、ここを積極的に更新しなくて構いません。
- 日本語の使用書やREADMEは利用者向けの大事なドキュメントです。コード変更で操作や表示場所が変わったら、該当READMEも更新してください。
- GitHubで公開するExtensionの仕様書・使用書・READMEには対象versionを明記し、`bl_info`と`blender_manifest.toml`のversionへ揃えてください。後方互換のないメジャー更新では、利用可能な直近旧メジャー版ZIPへのリンクを仕様書末尾の「過去バージョン」に残してください。
- Blender API依存の変更では、対象Blenderバージョンを `blender_manifest.toml` とREADMEの両方で確認してください。
- 新しいExtensionを追加したら、`_Taiyo_Blender_Extensions_Repo/taiyo_extension_manager/__init__.py` の `TAG_ALIASES` と `DESCRIPTION_ALIASES` にも追加してください。マネージャーのタグ検索はRemote Repositoryのmanifestから動的に一覧を作りますが、日本語タグ、用途タグ、短い日英説明はここで補強します。
- Extension追加時のタグは、英語の用途語だけでなく、日本語の検索語も入れます。例: `csv`, `export`, `collection`, `uv`, `unreal`, `名前整理`, `書き出し`, `衝突`, `寸法`。
- 新しいExtensionの `blender_manifest.toml` には、`website` をREADMEまたは使用書へ向けてください。Taiyo Extension Managerの `Manual` ボタンはこのURLを使います。`GitHub` ボタンはExtension IDからソースフォルダURLを自動生成します。
- Taiyo Extension Manager自体を変更した場合は、`bl_info`、`blender_manifest.toml`、`docs/extensions/index.json`、配布zip名のversionを揃え、古いmanager zipを残さないでください。

## 配布ビルド手順

通常は次を実行します。

```sh
./tools/build_extensions.sh
```

このスクリプトは以下を行います。

- 28個の Extensions パッケージを `blender --command extension validate` で検証
- 各パッケージをzip化して `docs/extensions/` に出力
- `blender --command extension server-generate --repo-dir docs/extensions --html` で `index.json` と `index.html` を生成

## GitHub / Pages 運用

- GitHubリポジトリ名は `taiyo-blender-scripts` を基本にします。
- GitHub Pagesの公開元は `main` branch の `/docs` を想定します。
- Private repositoryでGitHub Pagesが使えない場合は、BlenderからRemote Repositoryとして使う目的を優先してPublicに切り替えます。
- GitHub CLIの認証が切れている場合は、`gh auth login -h github.com` を先に実行してください。
- ユーザーから「pushしない」「コミットしない」などの明示的な指定がない場合、実装・検証後はcommitしてpushまで進めます。作業ツリーに無関係な差分がある場合は混ぜず、必要なら対象範囲を確認してから進めます。
- Codex環境で `git` がPATHにない場合は、まず `powershell -ExecutionPolicy Bypass -File tools/git.ps1 ...` を使います。このラッパーは `.codex-tools/MinGit` のPATHと `GIT_EXEC_PATH` を補完するため、HTTPSのfetch/pushにも使えます。
- それでも `git` / `gh` が使えずGitHubコネクタが使える場合は、そこで止めず、GitHub Git Data API相当の `create_blob` / `create_tree` / `create_commit` / `update_ref` を使ってcommitとpushを行います。配布更新ではローカルの `docs/extensions` 状態を優先し、古いzipの削除、新zipの追加、`index.json` / `index.html` の更新を同じcommitにまとめます。

## 配布前チェック

- `find . -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store'` で不要物を確認します。
- `docs/extensions/index.json` の配布パッケージが28個あることを確認します。Blender側の古いRepository indexキャッシュが旧zipを参照する場合があるため、直近旧バージョンの互換用zipをindexに載せずに残すことがあります。この場合、zip実ファイル数は28個より多くても問題ありません。
- `docs/extensions/index.json` と `docs/extensions/index.html` が生成されていることを確認します。
- 可能ならBlenderのPreferencesからRemote Repositoryに `index.json` URLを追加して確認します。

## 今後の注意事項

- 新しい注意点、失敗した手順、Blenderバージョン差分、配布時の落とし穴はここに追記してください。
- SynologyDrive上で `Stale NFS file handle` が出ることがあります。読み取りが不安定な場合は、少し待って再実行してください。
- Codexのsandbox内で `./tools/build_extensions.sh` からBlenderを子プロセス起動すると、環境によってMetal初期化でセグフォすることがあります。同じ `blender --background --command extension ...` を直接実行すると通る場合があります。
- `./tools/build_extensions.sh` は互換用zipを一時退避したあと、`docs/extensions/*.zip`、`index.json`、`index.html` を削除してから validate/build を始め、index生成後に互換用zipを復元します。途中でBlenderがセグフォした場合、互換用以外の配布フォルダが空になるので、そのままコミットしないでください。必要なら `git archive` や `git checkout` で既存の `docs/extensions` を復元してから作業を続けます。
- 一部アドオンだけ手動で配布更新する場合は、対象zipを作り直したあと、`docs/extensions/index.json` の `archive_size` と `archive_hash` を実ファイルの `wc -c` / `shasum -a 256` に合わせます。`index.html` のサイズ表示とBuilt時刻も更新し、最後にindexの値と実zipが一致することを確認してください。
- 旧バージョンzipを削除すると、Blenderがキャッシュ済みの古い `index.json` から旧zipを読みに行ってHTTP 404になることがあります。更新直後は少なくとも直近旧バージョンzipを `docs/extensions/` に残し、`server-generate` は最新zipだけで実行したあと、必要な旧zipを復元してpushします。
- Windowsの標準インストールでは `C:/Program Files/Blender Foundation/Blender 4.5/blender.exe` を利用できます。`tools/build_extensions.sh` はmacOS版に加えてBlender 4.2〜4.5のWindows標準パスも探索します。
- Blend Reference Graphの統合テストは `blender --background --python tools/test_blend_reference_graph.py` で実行します。
- Custom Properties Batch Editorの統合テストは `blender --background --python tools/test_custom_properties_batch_editor.py` で実行します。
- Collection Linked Mesh Replacerの統合テストは `blender --background --python tools/test_collection_linked_mesh_replacer.py` で実行します。
- CSV Mesh Instancerの統合・負荷テストは `blender --background --python tools/test_csv_mesh_instancer.py` で実行します。
- Modular Asset Renamerの統合テストは `blender --background --python tools/test_modular_asset_renamer.py` で実行します。
- Taiyo Extension Managerのフィルター・並び替え統合テストは `blender --background --python tools/test_taiyo_extension_manager.py` で実行します。
- Laid Collection Instance Linkerの統合テストは `blender --background --python tools/test_laid_collection_instance_linker.py` で実行します。
- Vertex Color Material Painterの統合テストは `blender --background --python tools/test_vertex_color_material_painter.py` で実行します。
- Unreal Bridge Toolsの統合テストは `blender --background --python tools/test_unreal_bridge_tools.py` で実行します。
- `tools/build_extensions.sh` はRepository index生成後に `tools/add_extension_update_metadata.py` を実行し、各packageの最終Git更新時刻を `taiyo_updated_at` として `docs/extensions/index.json` に追記します。マネージャーの `Recently Updated` はこの値を使います。

- Hierarchy Restriction Managerの統合テストは `blender --background --factory-startup --python-exit-code 1 --python tools/test_hierarchy_restriction_manager.py`。UIでのUndo/Redo/Cancelは `tools/ui_test_hierarchy_restriction_manager.py`、負荷計測は `tools/benchmark_hierarchy_restriction_manager.py` を使います。
- Blender 4.5のEventには `timer` 属性がありません。Modal処理は `event.type == "TIMER"` で進めます。Collectionのexclude/global hide_viewport変更ではObjectの一時hide状態が消えることがあるため、Cancel/Solo復元では直接書いた値以外の消失状態も補償します。
- HRMはObject Modeでのみ制限変更を実行します。Blender 4.5のEdit Mode UndoではCollection/Object制限が戻らないことをUIテストで確認済みです。勝手なモード切替で回避しないでください。

- Taiyo Object Groupsの統合テストは `blender --background --factory-startup --python-exit-code 1 --python tools/test_zone_groups.py`。UIのLive/Undo/Cancelは `tools/ui_test_zone_groups.py` と `tools/ui_test_zone_groups_undo.py`、負荷測定は `tools/benchmark_zone_groups.py`。最低対応はBlender 4.5.9。
- macOSの `/usr/bin/git` がXcodeライセンス未同意で失敗しても `/Library/Developer/CommandLineTools/usr/bin/git` が利用できる場合があります。Synology由来の実行ビット差分は `git -c core.fileMode=false status` で内容差分と区別し、無関係なmode変更をcommitに含めないでください。
- Blender Extensionのregister()は `_RestrictData` 内で実行されるため、登録時に `bpy.data.scenes` を走査しないでください。大規模Sceneの `obj.name in scene.objects` の反復は遅いため、更新時にObject集合を構築して照合します。

- Taiyo Object Groupsの復元情報はObject側の `zg_baseline` に保存し、Sceneの所有UUIDで競合を防ぎます。大量の復元対象をSceneのObject PointerPropertyリストへ追加すると、依存関係更新の負荷が増えるため避けます。

- Taiyo Object Groups 1.1.0のMesh回帰は `tools/test_zone_groups_mesh.py` と `tools/test_zone_groups_mesh_invalid.py`、実UIは `tools/ui_test_zone_groups_mesh_undo.py` / `tools/ui_test_zone_groups_mesh_live.py`。OperatorはObjectのPointerPropertyを保持できないため、Mesh選択ダイアログではScene内の名前を指定し、実行時に参照を解決します。

- Taiyo Object Groups 1.1.1の6万Object実UI回帰は `tools/ui_test_zone_groups_isolate_large.py`。hide_viewport変更とhide_getの読取りをObjectごとに交互実行するとView Layer再同期が極端に重くなります。状態は変更前に読み、一括RNA適用と分割Cancel復元を維持してください。

- Taiyo Object Groupsの一括色/制限変更は `tools/test_zone_groups_display_sync.py` で元Objectとevaluated_getの両方を検証します。Object collectionのforeach_setは描画用ID更新通知が不足するため、変更Objectのupdate_tagを省略しないでください。

- Map Roundtrip Tools 0.1.0とUnreal Bridge Tools 2.3.0の回帰は `blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_tools.py`。実UIのESC復元は `blender --factory-startup --enable-event-simulate --python tools/ui_test_map_roundtrip_tools.py`、性能測定は `tools/benchmark_map_roundtrip_tools.py`。詳細結果はMap RoundtripのVALIDATION.mdを参照してください。
- Map RoundtripのPreviewは配置を変更せず、実行時にplanを再作成します。Archiveは全データ内の同じub_zoneを対象にします。復元には元Collection所属・タグ・除外状態も必要です。
- Blender 4.5.9 / 5.2.2では `wm.fbx_import` とFBX exporterのtemp_override選択上書きを往復テストで確認済みです。Object作成の非線形遅延と最終依存グラフ同期は別々に測定し、Collection link自体と混同しないでください。



- Map Roundtrip 0.7.0がゾーン登録・Empty管理・Add/Subtract・Mesh/Empty一括選択・ゾーンCSV・選択ObjectからのEmpty自動作成(Add Selected Objects)を担当します。UBT 2.3.3は2.2.20相当へ復元。旧UBTのゾーン情報はMRTが互換読取りし、register時のScene走査はしません。CSVは`Zone`で選んだゾーン範囲内のMeshを選択に関係なく`<Zone>.csv`へ出力し(All Zonesはゾーンごと、名前順で先勝ち)、成功時のみub_zoneを更新します。

- Blender 5.xの実行時RNAプロパティはdict型ID Property参照だけでは旧値を読めない場合があります。MRTの旧データ移行は非表示の互換スキーマを使い、登録後timer/load_postで登録ゾーン名を引き継ぎます。両アドオンの有効/無効化順はtools/test_map_roundtrip_addon_lifecycle.pyで確認します。

- Map Roundtrip 0.7.0の回帰: `blender --background --factory-startup --python-exit-code 1 --python` で `tools/test_mrt_zone_from_objects.py`(純numpy)、`test_map_roundtrip_add_objects.py`、`test_map_roundtrip_zone_csv.py`、`test_map_roundtrip_ui_layout.py`、既存の`test_map_roundtrip_tools.py` `_zones.py` `_zone_registry.py` `_zone_migration.py` `_addon_lifecycle.py`。実UIは`blender --factory-startup --enable-event-simulate --python tools/ui_test_map_roundtrip_add_objects.py`(`MRT_SHOT_DIR`でスクリーンショット保存)、6万件の実測は`tools/benchmark_map_roundtrip_add_objects.py`。
- Blenderの行列(`matrix_world`と`inverted()`)はfloat32です。ゾーン箱の端にある点は、座標が大きいほど(約490で5e-6相当の誤差)範囲外へ落ちます。箱を作るときは`zone_from_objects.float32_margin`のように座標の大きさに比例する余白を足してください。`pad`を固定値にしないこと。
- `scene.mrt_props.zone_choice`はEnumPropertyの動的itemsで、**読むたびに全Emptyを走査します**。UIの描画やループの中で何度も読まず、ローカル変数へ1回だけ代入してください(5,000個で1回22秒かかった実例あり)。
- Undo(`ed.undo`)後はData blockが読み込み直されるため、UIテストでは`scene`や`props`の参照を保持せず、都度`bpy.context.scene`から取得します。
- パネルは登録順に並びます。Zonesとそのサブパネルを`__init__.py`の`classes`でExport/Importより前に登録してください(`bl_order`だけでは先頭になりません)。
- macOSのBashには`timeout`コマンドがありません。GUIのBlenderテストはスクリプト内のタイムアウトで終了させます。
- `zone_choice`の読み取りコストはゾーン内Emptyの数に比例します(実測 5,000個で4.5ms、3万個で27ms。Blender 4.5.9 / M1 Pro)。Add Selected Objectsで3万個を超えるEmptyを作る使い方では、パネル再描画ごとに複数回読まれて重くなります。必要になったら`zone_items`のキャッシュ(Empty数・登録数・接頭辞をキーに、短い有効期限つき)を検討してください。
- LM Studioの委譲でレビューだけを任せる場合は、レポートMarkdownを`target`にしたタスクとして実行できます。ただし指摘は仕様と食い違う断定や存在しない問題が混ざります(2026-11-12の実績: 16件中、実バグ0件)。必ず実コードと再現で確認してから修正してください。
- Map Roundtrip 0.4.0: CSV書き出しは各行の`id`をObjectの`ub_csv_id`(ub_zoneと同じトランザクション)へ保存します。戻りCSVでは`id=-1`が追加Mesh、対象ゾーンのub_csv_idに無いidは使用しません。ゾーンにub_csv_idが無ければ判定しません。`tools/test_map_roundtrip_csv_id.py`は`-- import` / `-- export`で片側だけ実行できます。LM Studioのクロスレビューは、無関係な行の書き換えや節の削除を入れることがあるため、必ずdiffを確認してください。
- Map Roundtrip 0.5.0: CSVの`colname`はMap Collectionからの階層パス(`/`区切り、例 `Area1/Rocks`。Map直下は空欄、Map外はシーン最上位から)。取り込みは、Mapの下の同名Collection(旧CSV)→階層パスの順に解決し、無い階層を入れ子で作ります(`placement.resolve_colname`)。新しいCollection名が他で使われていると`.001`が付くため警告します。`tools/test_map_roundtrip_colname_path.py`で確認します。
- Map Roundtrip 0.6.0: Add Selected Objectsは新しいEmptyを元のMeshのCollection(シーンにつながるCollectionのうち、子→シーンルートの順で最初に見つかるもの)へ入れます。まとめたEmptyは多数決(同数はシーン順)。Collectionの所属は`_owners`でCollection単位に読みます(Objectごとの`users_collection`は6万件で遅いため避ける)。`tools/test_map_roundtrip_empty_collection.py`で確認します。
- Map Roundtrip 0.7.0: Replace Zoneは`ub_csv_id`で対応づける差分更新です(変更なしは触らない/動いたものはその場で更新/CSVに行が無いものは`_Replaced_<Zone>`へミラーCollection(`<名前> [<Zone>]`、`ub_mirror_of`)で階層ごと退避/新規は作成)。`Delete`は廃止。復元は`journal.py`(Journal=ESC/失敗時の巻き戻し、`ub_run`=Objectごとの元の状態JSON、アーカイブCollectionの`ub_state`が`after`/`before`)と`restore.py`(`mrt.switch_map_state`)。`ub_run.after`が無い=取り込み後に存在、`null`=取り込み後は不在、最初に切り替えるとき現在の状態を保存します。Collectionの付け替えは**link→unlinkの順**にします(unlinkが先だとBaseが作り直されて選択/非表示が失われ、`hide_set`で復元すると2万件で68秒かかりました)。エラーは`placement_report.Issue`(行・列・値・理由)に集めます。追加Meshの置き場は`mirror.mirror_path`。回帰は`tools/test_map_roundtrip_restore.py` `_mesh_import_paths.py` `_helper.py`、実UIは`tools/ui_test_map_roundtrip_tools.py`、6万件は`tools/benchmark_map_roundtrip_diff.py`。
- LM Studioに複数のタスクを並列で渡すと、同じパッケージを`register()`するテストが互いの未完成のファイルで落ちます。クラスの継承(`ChunkedOperator`は`bpy.types.Operator`と併用)など基本の誤りは、仕様書に書くか、先に確認してください。生成されたコードは、削除された行・未定義の変数・仕様と違う選択(`colnames[0]`など)を含むことがあり、今回も`mesh_import.py`は作り直しました。
- Map Roundtrip 0.7.1: `New Meshes To`はLibraryの外でもよく、PreviewのMesh検索(`placement.walk_library`)は`Library`と`New Meshes To`の両方を探します(Mapの中は除外)。Helperも同じ関数を使います。実シーンのコピーで確認するときは、blendに保存されたパスが別PCのもの(`G:\...`)なので、`mesh_fbx`と`placement_csv`を手元のパスへ差し替えてから実行します。
- Map Roundtrip 0.7.2: HoudiniのFBX(Y-up/cm)をBlenderへ取り込むと、Objectは回転X 90度・スケール0.01で、Meshデータは元の座標のままです。配置はMeshデータだけを使うため、Import New Meshesは取り込み時にObjectの`matrix_basis`をMeshデータへ焼き込みます(負のスケールは法線を反転)。`matrix_world`は取り込み直後に古いことがあるので、親を外した後は`matrix_basis`を読んでください。
