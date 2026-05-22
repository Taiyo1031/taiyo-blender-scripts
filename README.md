# Taiyo Blender Scripts

このフォルダには、Taiyo用のBlenderカスタムアドオンと使用書が入っています。

## 読み方
- 各ツールの概要と最短手順は、各フォルダの `README.md` を見てください。
- 詳細な説明やトラブルシューティングは、各フォルダ内の既存の詳細使用書を見てください。
- Blender 4.2以降の拡張機能リポジトリ用パッケージは `_Taiyo_Blender_Extensions_Repo` にまとめています。
- エージェント向けの運用メモや注意事項は `AGENTS.md` に追記していきます。

## Blenderから使う

Blender 4.2以降では、GitHub Pagesで公開された静的Extensionsリポジトリを登録して使います。

Remote Repository URL:

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

Blender側では `Preferences > Get Extensions > Repositories > Add Remote Repository` から上記URLを追加します。

配布ファイルを更新する場合:

```sh
./tools/build_extensions.sh
```

このコマンドは `_Taiyo_Blender_Extensions_Repo` 内の各パッケージを検証し、`docs/extensions/` にzip、`index.json`、`index.html`を生成します。

GitHub Pagesは `main` ブランチの `/docs` から公開する想定です。PrivateリポジトリでPagesが使えない場合は、Blenderから直接登録できる状態を優先してPublicへ切り替えます。

## GitHub初期化メモ

まだGitHub CLIの認証が切れている場合は、先に次を実行します。

```sh
gh auth login -h github.com
```

初回リポジトリ作成の想定コマンド:

```sh
git init -b main
git add .
git commit -m "Prepare Blender extension repository"
gh repo create Taiyo1031/taiyo-blender-scripts --private --source=. --remote=origin --push
```

その後、GitHub Pagesを `main` ブランチの `/docs` から公開します。

## 目的から探す

| やりたいこと | 使うツール | できること | 主な出力・結果 | 詳細 |
|---|---|---|---|---|
| メッシュ属性をCSVに出したい | `attribute_csv_exporter` | 選択したメッシュの属性をCSVに書き出すアドオンです。Geometry Nodesやモディファイア適用後の評価済みメッシュにも対応します。 | 属性CSV | `attribute_csv_exporter/README.md` |
| Geometry Nodesの入力値を一覧化したい | `ExportModefireParametor` | 選択オブジェクトのGeometry Nodesモディファイア入力パラメータをCSVに書き出すアドオンです。 | パラメータCSV | `ExportModefireParametor/README.md` |
| 選択オブジェクト名だけをCSVにしたい | `ExportNameAsCSV` | 選択中のオブジェクト名をCSVへ書き出すシンプルなアドオンです。 | 名前CSV | `ExportNameAsCSV/README.md` |
| コレクションインスタンス名を整理したい | `instance_name_fixer` | コレクションインスタンスの名前を、参照元コレクション名に揃えるアドオンです。`.001` などの番号サフィックスは保持します。 | オブジェクト名の修正 | `instance_name_fixer/README.md` |
| 選択オブジェクトを個別コレクションへ整理したい | `Move_Selected_to_Own_Collections` | 選択オブジェクトごとに、元コレクション内へオブジェクト名と同じ名前のコレクションを作成または再利用して移動します。 | 個別コレクション整理 | `Move_Selected_to_Own_Collections/README.md` |
| 比率を保ったまま寸法を合わせたい | `proportional_dimensions` | 指定したX/Y/Z寸法を基準に、選択オブジェクトを縦横比を保ったまま均等スケールするアドオンです。 | 均等スケール済みオブジェクト | `proportional_dimensions/README.md` |
| コレクションインスタンスでRigid Bodyを使いたい | `RB_Instance_Helper` | リンクされたコレクションインスタンス用にRigid Body向けプロキシメッシュを作り、更新、ベイク、転送まで扱う補助アドオンです。 | プロキシ、ベイク、転送結果 | `RB_Instance_Helper/README.md` |
| 選択オブジェクトを別モデルに置き換えたい | `Replace_Selected_with_Active` | 選択オブジェクトを、アクティブオブジェクトのコピーに置き換えるアドオンです。位置、回転、スケールの引き継ぎを選べます。 | 置き換え済みオブジェクト | `Replace_Selected_with_Active/README.md` |
| UVを決まったスロットへ移動したい | `UVMatSlots_Ver2_6` | 選択UVまたはUVアイランドを、8つの定義済みスロットへ移動するUV編集用アドオンです。 | UV座標の変更 | `UVMatSlots_Ver2_6/README.md` |
| 選択メッシュを画像で書き出したい | `VirportExport` | 選択メッシュを1つずつ現在のビューポート見た目で画像書き出しするアドオンです。一時カメラで自動フィットします。 | オブジェクト別画像 | `VirportExport/README.md` |

## ツール一覧

| フォルダ | ツール名 | 表示場所 | ひとことで |
|---|---|---|---|
| `attribute_csv_exporter` | Attribute CSV Exporter | `View3D > Sidebar (N) > Attr CSV` | メッシュ属性をCSV化 |
| `ExportModefireParametor` | GN Parameter CSV Exporter | `View3D > Sidebar (N) > GN CSV Export` | Geometry Nodes入力値をCSV化 |
| `ExportNameAsCSV` | Export Selected Object Names to CSV | `View3D > Sidebar > Selected CSV Export` | 選択名をCSV化 |
| `instance_name_fixer` | Instance Name Fixer | `View3D > Sidebar > Name Fixer` | インスタンス名を整理 |
| `Move_Selected_to_Own_Collections` | Move Objects to Own Collections | `View3D > Sidebar (N) > Collection Tools` | 選択を個別コレクションへ整理 |
| `proportional_dimensions` | Proportional Dimensions | `View3D > Sidebar(N) > 比率寸法` | 比率維持で寸法合わせ |
| `RB_Instance_Helper` | RB Instance Helper | `View3D > N-panel > RB Helper` | インスタンス用Rigid Body補助 |
| `Replace_Selected_with_Active` | Replace Selected with Active | `View3D > Sidebar > Replace` | 選択をアクティブで置き換え |
| `UVMatSlots_Ver2_6` | UV Channel Placement Tool | `View3D > Sidebar > UV Tools` | UVをスロット配置 |
| `VirportExport` | Viewport Export Selected Meshes | `View3D > Sidebar > Viewport Export` | 選択メッシュを画像化 |

## Blender拡張機能リポジトリ
- リポジトリフォルダ: `_Taiyo_Blender_Extensions_Repo`
- Blender側の表示名: `Taiyo Blender Scripts`
- 配布対象は、各ツールで明示した現行版 `.py` です。旧版やバックアップファイルはリポジトリに含めていません。
- `_Taiyo_Blender_Extensions_Repo` をBlender 4.2以降のExtensions配布用のsource of truthとして扱います。
