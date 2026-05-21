# AGENTS.md

このファイルは、Codex や他のエージェントがこのワークスペースで作業するときに最初に参照する運用メモです。新しく分かった注意点や、次回以降に守ってほしいことはここへ追記してください。

## このリポジトリの目的

- これは Taiyo のカスタム Blender scripts / add-ons を管理するリポジトリです。
- ルート直下の各フォルダには、単体アドオン版の `.py`、README、詳細使用書があります。
- `_Taiyo_Blender_Extensions_Repo` は Blender 4.2 以降の Extensions 用パッケージ群です。
- Blender の Remote Repository には GitHub リポジトリ URL ではなく、配布用 `index.json` の URL を登録します。

## 編集時の基本方針

- 既存フォルダ構成を大きく変えないでください。整理が必要な場合は、先に目的と移動先を明確にします。
- 単体アドオン版 `.py` と `_Taiyo_Blender_Extensions_Repo/*/__init__.py` は同期対象です。片方だけ直した場合は、もう片方も確認してください。
- 配布対象は `_Taiyo_Blender_Extensions_Repo` 内の現行版です。旧版、バックアップ、キャッシュ、作業中ファイルを zip に含めないでください。
- 日本語の使用書や README は利用者向けの大事なドキュメントです。コード変更で操作や表示場所が変わったら、該当 README も更新してください。
- Blender API 依存の変更では、対象 Blender バージョンを `blender_manifest.toml` と README の両方で確認してください。

## 配布ビルド手順

通常は次を実行します。

```sh
./tools/build_extensions.sh
```

このスクリプトは以下を行います。

- 9個の Extensions パッケージを `blender --command extension validate` で検証
- 各パッケージを zip 化して `docs/extensions/` に出力
- `blender --command extension server-generate --repo-dir docs/extensions --html` で `index.json` と `index.html` を生成

Blender 側で使う Remote Repository URL:

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

## GitHub / Pages 運用

- GitHub リポジトリ名は `taiyo-blender-scripts` を基本にします。
- 最初は Private リポジトリで作成します。
- Private repository で GitHub Pages が使えない場合は、Blender から Remote Repository として使う目的を優先して Public に切り替えます。
- GitHub Pages の公開元は `main` branch の `/docs` を想定します。
- GitHub CLI の認証が切れている場合は、`gh auth login -h github.com` を先に実行してください。
- 初回作成コマンドは `git init -b main`、`git add .`、`git commit -m "Prepare Blender extension repository"`、`gh repo create Taiyo1031/taiyo-blender-scripts --private --source=. --remote=origin --push` を想定します。

## 配布前チェック

- `find . -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store'` で不要物を確認します。
- `docs/extensions/` に zip が9個あることを確認します。
- `docs/extensions/index.json` と `docs/extensions/index.html` が生成されていることを確認します。
- 可能なら Blender の Preferences から Remote Repository に `index.json` URL を追加して確認します。

## 今後の注意事項

- 新しい注意点、失敗した手順、Blender バージョン差分、配布時の落とし穴はここに追記してください。
- SynologyDrive 上で `Stale NFS file handle` が出ることがあります。読み取りが不安定な場合は、少し待って再実行してください。
- Codex の sandbox 内で `./tools/build_extensions.sh` から Blender を子プロセス起動すると、環境によって Metal 初期化でセグフォすることがあります。同じ `blender --background --command extension ...` を直接実行すると通る場合があります。
- `./tools/build_extensions.sh` は最初に `docs/extensions/*.zip`、`index.json`、`index.html` を削除してから validate/build を始めます。途中で Blender がセグフォした場合、配布フォルダが空になるので、そのままコミットしないでください。必要なら `git archive` や `git checkout` で既存の `docs/extensions` を復元してから作業を続けます。
- 一部アドオンだけ手動で配布更新する場合は、対象zipを作り直したあと、`docs/extensions/index.json` の `archive_size` と `archive_hash` を実ファイルの `wc -c` / `shasum -a 256` に合わせます。`index.html` のサイズ表示と Built 時刻も更新し、最後に index の値と実zipが一致することを確認してください。
