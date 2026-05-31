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

- 16個の Extensions パッケージを `blender --command extension validate` で検証
- 各パッケージをzip化して `docs/extensions/` に出力
- `blender --command extension server-generate --repo-dir docs/extensions --html` で `index.json` と `index.html` を生成

## GitHub / Pages 運用

- GitHubリポジトリ名は `taiyo-blender-scripts` を基本にします。
- GitHub Pagesの公開元は `main` branch の `/docs` を想定します。
- Private repositoryでGitHub Pagesが使えない場合は、BlenderからRemote Repositoryとして使う目的を優先してPublicに切り替えます。
- GitHub CLIの認証が切れている場合は、`gh auth login -h github.com` を先に実行してください。

## 配布前チェック

- `find . -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store'` で不要物を確認します。
- `docs/extensions/` にzipが16個あることを確認します。
- `docs/extensions/index.json` と `docs/extensions/index.html` が生成されていることを確認します。
- 可能ならBlenderのPreferencesからRemote Repositoryに `index.json` URLを追加して確認します。

## 今後の注意事項

- 新しい注意点、失敗した手順、Blenderバージョン差分、配布時の落とし穴はここに追記してください。
- SynologyDrive上で `Stale NFS file handle` が出ることがあります。読み取りが不安定な場合は、少し待って再実行してください。
- Codexのsandbox内で `./tools/build_extensions.sh` からBlenderを子プロセス起動すると、環境によってMetal初期化でセグフォすることがあります。同じ `blender --background --command extension ...` を直接実行すると通る場合があります。
- `./tools/build_extensions.sh` は最初に `docs/extensions/*.zip`、`index.json`、`index.html` を削除してから validate/build を始めます。途中でBlenderがセグフォした場合、配布フォルダが空になるので、そのままコミットしないでください。必要なら `git archive` や `git checkout` で既存の `docs/extensions` を復元してから作業を続けます。
- 一部アドオンだけ手動で配布更新する場合は、対象zipを作り直したあと、`docs/extensions/index.json` の `archive_size` と `archive_hash` を実ファイルの `wc -c` / `shasum -a 256` に合わせます。`index.html` のサイズ表示とBuilt時刻も更新し、最後にindexの値と実zipが一致することを確認してください。
