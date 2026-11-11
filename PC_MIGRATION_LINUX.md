# Linux移行・開発引き継ぎ

更新日: **2026-11-12（日本時間）**。Taiyo Blender Scriptsを別のLinux PCで引き継ぐ本人・開発エージェント向け。

この資料は、GitHubからの取得・日々の同期・検証・pushと、これまでのBlender開発で重視されてきたことをまとめたものです。まず本書と[AGENTS.md](AGENTS.md)を読み、個別ExtensionのREADME・manifestで現在の仕様を確認してください。本書の状態・versionは作成時点の記録です。以後の明示的な依頼と最新コードを優先します。

## 1. 最初に把握すること

| 項目 | 内容 |
|---|---|
| GitHub | [Taiyo1031/taiyo-blender-scripts](https://github.com/Taiyo1031/taiyo-blender-scripts) |
| 基本ブランチ | `main` |
| 編集元 | `_Taiyo_Blender_Extensions_Repo/` |
| 配布物 | `docs/extensions/`のZIP・index.json・index.html |
| ビルド | `tools/build_extensions.sh`（現行28パッケージ） |
| 旧形式 | `_legacy_single_file_addons/`。明示依頼がなければ通常の修正対象外 |
| 公開方式 | GitHub Pages。想定設定は`main`の`/docs` |

Blenderへ登録するのはGitHubのプロジェクトURLではなく、[Remote Repositoryのindex.json](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json)です。

Linuxへの移行完了は、cloneできたことだけではありません。最新ソースの取得、本人アカウントでのpush権限確認、必要データの移送、Blenderでの導入・対象テストまで確認します。push権限は実際の必要な変更をpushして確認し、確認目的だけの空commitは不要です。

## 2. これまでの要望と作業の進め方

### 根拠と読み方

このチャットで確認できた以下の7チャットのメッセージ、および現行コード・使用書を根拠にしています。全チャット・全履歴を網羅した分析ではありません。タイトルだけを根拠にせず、本人の発言を確認しています。元チャットの閲覧権限がない新PCでも読めるよう、必要な意味をここに残しています。

| 番号 | チャット名 | 短い発言例 |
|---|---|---|
| C1 | Map Roundtripを作成 | 「先に認識合わせ」「ホバーした時にヒントを出すように」「もう少し詳しい使い方をgithubにあげて」 |
| C2 | Taiyo Object Groups 1.1.0｜Mesh Volume・UI整理 | 「パフォーマンス優先」「UI全体が揺れる挙動」「現在6マンオブジェクトのシーン」 |
| C3 | CSV Mesh Instancerを追加 | 「折りたためるコンパクトな票が欲しい」「必要、ボタンひとつ」 |
| C4 | 類似アドオンを調査 | 「まだ作成しなくていい　確認だけ」「このプロジェクト内にない？」「使いやすさをメインに」 |
| C5 | Unreal Bridge CSV高速化 | 「6マンオブジェクト書き出しの時に数分」「残り何分か書いて星」 |
| C6 | アドオン構成を整理 | 「数が多くなってきたので整理整頓したい」 |
| C7 | 新しい管理ウィンドウを設計 | 「ジャンルごとにフォルダ分けして探しやすく」「他のところをクリックすると消えてしまう」 |

引用は短い抜粋です。誤字の意味は周辺の会話で判断します。以下は性格の評価ではなく、作業を円滑にするための記録です。

### 明示された要望

| 観点 | 次の担当が実行すること | 根拠 |
|---|---|---|
| 大量データと性能 | 実用規模で処理完了まで計測する。単にUIが動くことを合格条件にしない。総時間・長い処理区間・進捗・残り時間を区別する | C2、C5 |
| シンプルなUI | 日常の入口を簡単にし、詳細は折りたたむ。検索、1ボタンで対象選択・表示、具体的なホバーヒントを設ける。更新時にUIが跳ねる問題も修正対象 | C1、C2、C3 |
| 変更を見て判断 | CSVやMeshの差分をコンパクトな表で示し、採用・維持を判断できるようにする。C3ではTransformとMeshを別々に選べることを明示 | C3 |
| 実機確認 | 実際のBlender画面で使えるか確認する。C2ではアドオン導入済みのデモと体験できる.blendファイルを希望 | C2、C3 |
| 詳しい日本語使用書 | 操作場所、順序、用語の意味、対象versionをGitHubに掲載。非互換メジャー更新では旧メジャー最新版ZIPへのリンクを仕様書末尾に残す | C1、C3、AGENTS.md |
| 認識合わせ | 「確認だけ」「一旦プラン」「先に認識合わせ」の段階は調査・計画に留める。既存リポジトリ内の類似機能も確認する | C1、C3、C4 |
| 作業完了 | 明示的な除外がなければ、必要な検証・配布更新・commit・pushまで行い、使用場所とGitHubリンクを提示する。無関係な差分を含めない | AGENTS.md、C1の既存変更を保持する選択、C2・C3 |

「シンプルにしたい」は、必要機能を勝手に削除する意味にしません。C1では標準FBX画面をメインにし、個別一括出力を折りたたんで残すことを本人が選択しています。

### 複数の会話から読み取れる傾向（推定）

- **説明し直さず続けたい**：C1・C2・C3では短い追加指示や「進めて」で改善を積み重ねています。直前の合意と未完了項目を保持し、作業を再開する対応が適しています。
- **実際の制作で使えることを重視**：C2の6万Object不具合、C3の再import時の名前、C5の実行時間など、現場の症状から修正依頼が出ています。抽象的な成功説明より、再現条件・変更後の挙動・実測が役立ちます。
- **誤字は文脈で補う**：C3の「票」は変更表、C5の「星」は「ほしい」と読めます。毎回表記の確認をせず、意味が大きく分岐する点だけ質問する対応が適しています。
- **進捗と完了が分かる説明が役立つ**：C2の「今どんな感じ？」、C5の残り時間表示の要望から、長時間作業では完了済み・次の作業・制約を短く知らせることが有効と考えられます。

これらは推定です。本人の新しい指定に優先させず、過去の依頼から未依頼の機能追加や外部送信を正当化しません。

### 案件固有の指定

- **後方互換の廃止**：C3のCSV Mesh Instancerでは不要と指定されました。他Extensionへ一律に適用しません。旧ZIPをindex外に残すHTTP 404対策と、コード上の後方互換は別です。
- **Discord通知**：C2では節目・完了の通知を依頼されました。新しい案件での送信は、その案件の明示的な指示に従います。Webhookやトークンは公開文書へ移さず、必要時に別途安全に設定します。
- **使用量回復後の再開**：C2での指定日時に一度だけ再開する依頼は過去の単発依頼です。新PCで自動再開を再設定しません。取得できない残りトークン数を推測で報告しません。
- **デモとインストール**：C2のDownloadsへのデモ作成・アドオン導入は、その時の明示依頼です。移行先でのインストール先や既存設定を無断で上書きしません。

## 3. 現在の状態と残っている相談

2026-11-12、移行資料作成前のローカル`main`は`ef4821f`でした。下表はmanifestと現行実装・検証文書を照合した記録です。新PCではfetch後の実ファイルを再確認してください。

| 対象 | 現行version / 最低Blender | 実装済み・確認先 |
|---|---|---|
| Unreal Bridge Tools | 2.3.2 / 4.5.0 | SceneのZone登録、既存Empty登録、複数Add/Subtract、ホバーヒント。[README](_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/README.md) |
| Map Roundtrip Tools | 0.1.1 / 4.5.0 | 標準FBX画面をメインにし、個別一括出力はAdvancedへ。CSV往復・Zone復元。[詳細使用書](_Taiyo_Blender_Extensions_Repo/map_roundtrip_tools/WORKFLOW_JA.md) |
| Taiyo Object Groups | 1.1.2 / 4.5.9 | Mesh Volume、Isolate、表示色の一括更新通知。[検証結果](_Taiyo_Blender_Extensions_Repo/zone_groups/TEST_RESULTS.md) |
| CSV Mesh Instancer | 3.0.2 / 4.5.9 | 過去チャットにはv2の差分確認仕様もあるが、そのまま現行仕様と扱わない。[現行README](_Taiyo_Blender_Extensions_Repo/csv_mesh_instancer/README.md)を優先 |
| Taiyo Extension Manager | 1.0.17 / 4.2.0 | NパネルのTaiyoタブ、検索・タグ・状態フィルター・並び替え。[README](_Taiyo_Blender_Extensions_Repo/taiyo_extension_manager/README.md) |

### 性能と未検証範囲

今回の文書作成ではBlenderテストを再実行していません。以下は保存済み報告の抜粋です。Linuxでの保証値ではありません。

| 試験 | 測定環境・対象版 | 過去の結果 |
|---|---|---|
| Map RoundtripのReplace 6万件 | macOS arm64、Blender 4.5.9、MRT 0.1.0 / UBT 2.3.0 | 全体282.516秒、最長単一step 3.878秒。生成の線形性・最大0.5秒の応答目標は未達 |
| Object GroupsのIsolate 6万共有Mesh Object | macOS arm64、Blender 4.5.9、1.1.2 | Isolate 3.73秒、解除2.63秒、Cancel要求後の復元6.72秒、Undo/Redo PASS |
| Object Groupsの一括色・制限更新 | macOS arm64、Blender 4.5.9 / 5.2.2、1.1.2 | 200 Objectで元Objectと評価済みObjectの両方を確認。4.5.10実機・Linux・本人の制作Sceneは未検証 |

詳細と制約は[Map Roundtrip検証報告](_Taiyo_Blender_Extensions_Repo/map_roundtrip_tools/VALIDATION.md)と[Object Groups検証結果](_Taiyo_Blender_Extensions_Repo/zone_groups/TEST_RESULTS.md)を参照。測定値を他のversion・OSへ転用しません。Houdini／Unreal内の動作もBlender内テストだけで検証済みとはしません。

### 未実装の相談事項

C6・C7では、アドオンの数が増えたため、**他の場所をクリックしても閉じない専用Managerウィンドウ**と**ジャンル別の整理**が希望されています。現行ManagerはNパネルで、この構想は未実装です。過去のアシスタントが提案した具体的レイアウト・分類は、すべて本人が承認済みとは扱いません。

これは移行に含める開発作業ではなく、再相談する候補です。未追跡の`ADDON_STRUCTURE.md`には16パッケージ時点の古い情報があり、現行28件の一覧や仕様の根拠には使いません。

## 4. 移行元PCで済ませること

1. `git status --short --branch`と`git diff`で未完了変更を確認する。必要な変更だけを検証・commit・pushする。
2. Gitに含まれない必要ファイルを別途バックアップし、Linuxへコピーする。制作.blend、外部リンクMesh、CSV、FBX、テクスチャ、デモ、元チャットの添付仕様書が対象候補。
3. 絶対パス・大文字小文字・外部ライブラリ参照をLinux側で確認する。元のSynologyDriveパスや`/Applications/...`はそのまま使えない。
4. 移行先で検証できるまで元PCのデータを保持する。同じ`.git`フォルダを2台から同時に共有編集する運用は避け、各PCでcloneしGitHub経由で同期する。

作成開始時点の未追跡ファイルは次の2つでした。本資料のcommitには含めません。必要なら内容を確認して個別に移送してください。

```text
ADDON_STRUCTURE.md
tools/reference/zone_groups/results/ui_10000_restrictions_timeout.json
```

cloneで移るのはpush済みのGit管理対象です。未push commit、未追跡・除外ファイル、`.codex-tools/`などのローカルツール、Blenderの設定・インストール済みExtension、GitHub認証、通知設定、チャット履歴・添付資料は別途扱います。このMarkdownで必要な文脈を引き継ぎます。

## 5. Linuxの初期準備とclone

### ツールと認証

ディストリビューションは未指定です。Git・GitHub CLI（`gh`）・Bash・Python 3を、そのOSの導入方法で用意します。Python 3は下記の配布物チェックに使用します。Blenderは必要なExtensionの最低versionを満たすLinux版を用意し、取得先は[Blender公式](https://www.blender.org/download/)を使います。起動に必要なOSライブラリや画面環境は移行先で確認します。

```bash
git --version
gh --version
bash --version
python3 --version
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

本人の書込権限があるアカウントで認証します。ログインはブラウザで行い、認証情報を資料へ貼り付けません。参照: [gh auth login](https://cli.github.com/manual/gh_auth_login)、[gh auth setup-git](https://cli.github.com/manual/gh_auth_setup-git)。

### プロジェクト取得

以下の保存先は例です。既にclone済みなら再cloneせず、次節の同期を使います。

```bash
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
git clone https://github.com/Taiyo1031/taiyo-blender-scripts.git
cd taiyo-blender-scripts
git remote -v
git branch --show-current
git status --short --branch
```

新規cloneの基本ブランチは`main`です。異なる場合は状態を確認してから`git switch main`を実行します。GitHubのDownload ZIPではGit履歴・remoteが付かないため、開発継続にはcloneを使います。

commit作成者は本人の値を設定します。メールはGitHubで使用する確認済みアドレス、または本人のnoreplyアドレスへ置き換えてください。下記はこのリポジトリ内だけに設定します。

```bash
git config user.name "Taiyo"
git config user.email "YOUR_GITHUB_EMAIL"
```

## 6. 毎回の同期、commit、push

### 作業前

```bash
cd "$HOME/Projects/taiyo-blender-scripts"
git status --short --branch
git diff
git diff --cached
```

未commit変更があれば先に内容と所有する作業を確認し、必要な変更をcommitするかリポジトリ外に退避します。`git reset --hard`や`git clean -fd`で消さないでください。状態が整理できたら:

```bash
git switch main
git pull --ff-only origin main
```

`--ff-only`は履歴が分岐していると停止します。自動でマージcommitを作らない同期方法です。[Git公式: git pull](https://git-scm.com/docs/git-pull)

### 作業後

変更に応じたテスト・使用書更新・必要な配布ビルドを済ませてから、対象を明示してステージします。以下は今回のような文書変更の例です。

```bash
git diff --check
git diff -- README.md PC_MIGRATION_LINUX.md
git add -- README.md PC_MIGRATION_LINUX.md
git diff --cached --stat
git diff --cached
git commit -m "Document Linux migration and development handoff"
git push origin main
git status --short --branch
```

新規ファイルは通常の`git diff`には出ないため、追加前にも中身を読みます。ステージ済みに無関係なファイルがあれば、内容を保持したまま対象ファイルだけ`git restore --staged -- <パス>`で外します。`git add .`で全部を混ぜないでください。既存の実行ビット差分は`git -c core.fileMode=false status`と比較し、必要な実行権限変更まで無条件に無視する設定にはしません。

push後は次のPCでpullしてから作業します。2台で同じ箇所を同時に編集しないことが基本です。

### 同期・pushが拒否された場合

- **認証エラー**: `gh auth status --hostname github.com`で本人のログインと権限を確認し、必要なら再ログインする。
- **push拒否／fast-forward不可**: まず`git fetch origin`、`git log --oneline --left-right main...origin/main`で双方のcommitを確認する。強制pushで上書きしない。
- **自分だけの未push commitがある**: 作業ツリーを整理し、`git branch backup-before-sync`で復帰点を作ってから`git rebase origin/main`する。このブランチ名が既存なら別名を使う。公開済みcommitを書き換える用途には使わない。
- **rebase競合**: `git status`に出たファイルの両方の意図を確認して修正し、対象を`git add -- <パス>`、`git rebase --continue`。判断できなければ`git rebase --abort`で戻す。成功後は影響するテスト・配布物を再確認して通常pushする。

## 7. LinuxでのBlenderと配布ビルド

### 実行ファイルを指定する

現行ビルドスクリプトはmacOS・Windowsのパスを探索し、LinuxのPATH上の`blender`は自動探索しません。Linuxでは**`BLENDER_BIN`に実行可能なファイルの絶対パスを明示**します。

PATHにBlenderを導入済みなら、以下を順番に実行し、空のパスやversion違いがないことを確認します。

```bash
export BLENDER_BIN="$(command -v blender)"
test -n "$BLENDER_BIN" && test -x "$BLENDER_BIN"
"$BLENDER_BIN" --version
```

見つからない場合は、展開・インストールした実際の場所へ設定します。次はパスの例なので、実在する場所へ置き換えてください。

```bash
export BLENDER_BIN="/opt/blender/blender"
"$BLENDER_BIN" --version
```

このexportは現在のターミナルに有効です。別ターミナルでは再設定します。Object Groups・CSV Mesh Instancerを含める場合は最低4.5.9。過去の本人環境には4.5.10の報告がありますが、今回Linux上の特定versionでの動作確認はしていません。

### 変更対象を検証する

リポジトリ直下から実行します。以下は対象別の例で、変更に関係するものを選びます。UIテストにはデスクトップの画面環境が必要です。`--factory-startup`を使うテストは、制作中のセッションとは別プロセスで実行します。

```bash
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_tools.py
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 --python tools/test_unreal_bridge_zone_registry.py
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 --python tools/test_csv_mesh_instancer.py
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 --python tools/test_zone_groups_display_sync.py
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 --python tools/test_taiyo_extension_manager.py
```

実UI・大規模性能・Cancel/Undoについては[AGENTS.md](AGENTS.md)記載の対象テストと各検証文書を使います。Linux移行時は小規模で導入・基本操作を確認してから大規模データへ進み、OS・CPU・Blender version・件数と未実行項目を記録します。

### 配布物を生成する

Extensionを変更した場合に実施します。文書だけの変更では不要です。versionをコード・manifest・使用書で揃え、新規Extensionの場合はManagerの日英検索情報・Manual URLとビルド対象も更新します。

ビルド前に既存の配布物を退避します。下記で表示した退避先を控えてください。

```bash
distribution_backup_dir="$(mktemp -d /tmp/taiyo-distribution-backup.XXXXXX)"
cp -a docs/extensions "$distribution_backup_dir/"
printf '%s\n' "$distribution_backup_dir"
bash tools/build_extensions.sh
```

スクリプトは互換ZIPを一時退避し、既存ZIP・indexを削除してからビルドします。失敗時に配布フォルダが欠落した状態をcommitしないでください。失敗した出力も必要なら別途退避し、バックアップと比較して復旧します。自分の未commit配布変更がないことを確認できない限り、Git版で一括上書きしません。既知のmacOS MetalクラッシュをLinuxの原因と決め付けず、ログから切り分けます。

ビルドはvalidate、ZIP作成、server-generate、`taiyo_updated_at`追記を行います。旧ZIPは古いindexキャッシュの404回避用にindex外へ残すことがあります。Manager旧ZIPの扱いはAGENTS.mdの例外規則に従います。

### 配布前チェック

リポジトリ直下で実行します。28件は作成時点の件数で、新規追加時はビルド対象と併せて見直します。

```bash
find _Taiyo_Blender_Extensions_Repo -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store'
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path('docs/extensions')
index = json.loads((root / 'index.json').read_text())
items = index['data']
assert len(items) == 28, len(items)
assert len({item['id'] for item in items}) == len(items)
assert (root / 'index.html').is_file()
for item in items:
    archive_url = item['archive_url']
    assert archive_url.startswith('./'), archive_url
    archive = root / archive_url[2:]
    assert archive.is_file(), archive
    assert archive.stat().st_size == item['archive_size'], archive
    assert 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest() == item['archive_hash'], archive
    assert isinstance(item.get('taiyo_updated_at'), int) and item['taiyo_updated_at'] > 0, item['id']
print('PASS: 28 packages, HTML, ZIP size/hash, update timestamps')
PY
git diff --check
```

ZIP実ファイル数は互換用を含むので28個超でも問題ありません。ZIP内には旧版・キャッシュ・作業ファイルを含めず、コード・manifestとindexのversion、index.htmlのリンク・サイズも確認します。手動で一部だけ更新する場合のハッシュ・サイズ・Built時刻更新はAGENTS.md参照。

## 8. GitHub PagesとBlenderで公開確認

push後、リポジトリのSettings → Pagesで公開元が`main`／`/docs`か確認します。設定は想定値であり、本資料作成時にGitHub上の設定を変更したわけではありません。

1. [配布一覧](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.html)と[index.json](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json)が更新され、対象versionが表示されることを確認する。反映待ちならGitHubのデプロイ状態を見る。
2. index内の対象ZIPのリンクが取得できることを確認する。
3. LinuxのBlenderで`Preferences > Get Extensions > Repositories > Add Remote Repository`から上記index.jsonを登録する。
4. Repositoryを更新して対象Extensionを導入・更新し、有効化する。対象READMEに従いパネル・基本操作を確認する。

既に登録済みなら重複追加せず更新します。古いindexキャッシュが旧ZIPを参照する場合もあるため、互換ZIPを不用意に削除しません。ソースcloneだけではBlenderにアドオンはインストールされません。

## 9. 新PCのエージェントへ貼る依頼文

```text
Taiyo Blender Scriptsの開発を、このLinux PCで引き継いでください。

最初にPC_MIGRATION_LINUX.mdとAGENTS.mdを読み、Git状態・remote・現在の
ブランチ・未commit/未追跡ファイルを確認してください。既存の作業を保持し、
安全に同期できる状態ならGitHubの最新を取り込んでください。

Blender実行ファイルとversionを確認し、LinuxではBLENDER_BINを明示します。
必要な制作データや外部参照が移っているか、今回の作業に必要な範囲で確認してください。

私は大量Objectでの速度と安定性、シンプルな操作、検索、ホバーヒント、
具体的な日本語使用書を重視します。変更対象の実UI・描画反映・Cancel/復元も確認し、
性能は実用規模で測定してください。過去のmacOS測定値をLinuxの保証にしないでください。

「確認だけ」「一旦プラン」「先に認識合わせ」と言ったときは実装せず、
「進めて」は直前に合意した作業の続きとして受け取ってください。
短い追加指示は文脈で理解し、大きく仕様が分かれる点だけ確認してください。

実装を依頼した作業では、対象ソースと必要な使用書・version・配布物を更新し、
検証後、明示的に止めていなければ対象変更だけをcommit・pushまで進めてください。
完了時は、何が使えるようになったか、操作場所、検証結果・未検証・性能制約、
GitHubの使用書/commitリンクを短くまとめてください。

過去のManager専用ウィンドウ等の相談を勝手に実装しないでください。
過去案件の後方互換廃止・Discord通知・予約再開を新しい案件へ自動適用しないでください。
Webhookや認証情報を公開ファイル・ログへ書かないでください。

まず移行状態・不足している準備・直近の未完了事項を整理してください。
次の具体的な開発対象はこのチャットで指定します。
```
