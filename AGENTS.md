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

- 22個の Extensions パッケージを `blender --command extension validate` で検証
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
- `docs/extensions/index.json` の配布パッケージが22個あることを確認します。Blender側の古いRepository indexキャッシュが旧zipを参照する場合があるため、直近旧バージョンの互換用zipをindexに載せずに残すことがあります。この場合、zip実ファイル数は22個より多くても問題ありません。
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
- Modular Asset Renamerの統合テストは `blender --background --python tools/test_modular_asset_renamer.py` で実行します。
- Taiyo Extension Managerのフィルター・並び替え統合テストは `blender --background --python tools/test_taiyo_extension_manager.py` で実行します。
- Laid Collection Instance Linkerの統合テストは `blender --background --python tools/test_laid_collection_instance_linker.py` で実行します。
- Vertex Color Material Painterの統合テストは `blender --background --python tools/test_vertex_color_material_painter.py` で実行します。
- `tools/build_extensions.sh` はRepository index生成後に `tools/add_extension_update_metadata.py` を実行し、各packageの最終Git更新時刻を `taiyo_updated_at` として `docs/extensions/index.json` に追記します。マネージャーの `Recently Updated` はこの値を使います。
