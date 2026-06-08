# Taiyo Blender Scripts

Taiyo用のBlender Extensions配布リポジトリです。

このリポジトリは、GitHub Pagesで `docs/extensions/index.json` を公開し、Blender 4.2以降の Remote Repository として使うことを主目的にしています。

## Blenderから使う

Blender側では次のURLをRemote Repositoryとして登録します。

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

登録場所:

```text
Preferences > Get Extensions > Repositories > Add Remote Repository
```

## フォルダ構造

```text
repo/
├─ docs/extensions/                 # GitHub Pagesで公開する配布物
│  ├─ index.json                    # Blender Remote Repository が読むファイル
│  ├─ index.html                    # ブラウザ確認用の一覧
│  └─ *.zip                         # 各Extensionの配布zip
│
├─ _Taiyo_Blender_Extensions_Repo/   # Extension zipを作る元データ
│  └─ */                            # 各アドオンパッケージ
│     ├─ blender_manifest.toml
│     ├─ __init__.py
│     └─ README.md / 使用書
│
├─ tools/
│  └─ build_extensions.sh           # validate/build/index生成
│
├─ _legacy_single_file_addons/       # 旧・単体.pyインストール用の保管場所
├─ AGENTS.md                        # エージェント向け運用メモ
└─ README.md
```

Remote Repositoryとして必須なのは `docs/extensions/index.json` と `docs/extensions/*.zip` です。通常の開発では `_Taiyo_Blender_Extensions_Repo` を編集し、ビルド結果を `docs/extensions` に出力します。

`_legacy_single_file_addons` は旧形式の単体 `.py` アドオンを残すための保管場所です。Remote Repository運用では使いません。

## 配布ファイルの更新

通常は次を実行します。

```sh
./tools/build_extensions.sh
```

このコマンドは以下を行います。

- `_Taiyo_Blender_Extensions_Repo` 内の17個のパッケージを validate
- 各パッケージをzip化して `docs/extensions/` に出力
- `docs/extensions/index.json` と `docs/extensions/index.html` を生成

## Extension一覧

| Extension ID | 表示名 | ひとことで |
|---|---|---|
| `attribute_csv_exporter` | Attribute CSV Exporter | メッシュ属性をCSV化 |
| `collection_number_to_mesh_name` | Collection Number To Mesh Name | コレクション番号でMeshデータ名を整理 |
| `collection_mesh_merge_fbx_exporter` | Collection Mesh Merge FBX Exporter | コレクションごとに統合FBXを書き出し |
| `export_selected_names_csv` | Export Selected Object Names to CSV | 選択名をCSV化 |
| `gn_parameter_csv_exporter` | GN Parameter CSV Exporter | Geometry Nodes入力値をCSV化 |
| `instance_name_fixer` | Instance Name Fixer | インスタンス名を整理 |
| `map_link_tools` | Map Link Tools | リンク配置・共有Mesh・名前整理 |
| `move_selected_to_own_collections` | Move Objects to Own Collections | 選択を個別コレクションへ整理 |
| `overlap_selector` | Overlap Object Selector | 重なりオブジェクトを検出・選択 |
| `proportional_dimensions` | Proportional Dimensions | 比率維持で寸法合わせ |
| `rb_instance_helper` | RB Instance Helper | インスタンス用Rigid Body補助 |
| `replace_selected_with_active` | Replace Selected with Active | 選択をアクティブで置き換え |
| `taiyo_extension_manager` | Taiyo Extension Manager | Taiyo製Extensionをサイドバーから管理 |
| `uv_channel_placement_tool` | UV Channel Placement Tool | UVをスロット配置 |
| `unreal_bridge_tools` | Unreal Bridge Tools | Unreal Engine用CSVを書き出し |
| `vertex_color_material_painter` | Vertex Color Material Painter | 選択面にマテリアルIDカラーをペイント |
| `viewport_export_selected_meshes` | Viewport Export Selected Meshes | 選択メッシュを画像化 |

## GitHub Pages

GitHub Pagesは `main` ブランチの `/docs` から公開する想定です。

Private repositoryでPagesが使えない場合は、BlenderからRemote Repositoryとして使える状態を優先してPublicへ切り替えます。
