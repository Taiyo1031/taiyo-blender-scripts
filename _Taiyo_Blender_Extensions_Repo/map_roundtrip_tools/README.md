# Map Roundtrip Tools

**対象version: 0.2.0 / Blender 4.5.0以上**

ゾーン管理・配置CSV・HoudiniとのFBX往復・リンク複製での配置復元を担当するExtensionです。Unreal Bridge Toolsなしで利用できます。

[詳細使用書：Zone登録からCSV・FBX・配置復元まで](WORKFLOW_JA.md)

## 基本操作

`View3D > Sidebar (N) > Map Roundtrip > Zones`でNew Zoneを作り、Add EmptyまたはRegister Selected Emptiesで範囲を登録します。各EmptyのAdd／Subtractで範囲を合成できます。

- **Select Zone Empties**：ゾーンを構成するEmptyをまとめて選択。All Zonesなら全ゾーンのEmpty。
- **Select Meshes In Zone**：ゾーン内に原点が入るMeshをまとめて選択。All Zonesなら全範囲。
- **Export Selected CSV**：選択Meshをゾーン名.csvへ出力。正常終了時だけ同じ名前のub_zoneタグを付与。

CSVの12列、ワールド座標、XYZ回転の度数、名前正規化は維持します。Mesh CandidatesでMap配下／現在Sceneを選べます。旧UBTの登録ゾーン・EmptyのAdd/Subtract・登録解除状態も読み取れます。

## FBXとImport

通常はExport FBX (Blender)でBlender標準の設定・プリセット画面を使用します。個別一括出力はAdvanced / Batch Exportにあります。

ImportではLibrary（元Mesh）とMap（配置先）を指定します。追加Meshがある場合だけImport New Meshesを実行し、Placement CSVをPreviewしてからReplace Zoneを実行します。既定Archiveは旧配置を保持します。作業前に.blendを保存してください。大量処理のUndo履歴は作りません。

Exchange Folder／Return Folderは参考欄です。パス自動連動やファイル監視はありません。

## 検証

- 基本配置・FBX・ゾーンCSV：`tools/test_map_roundtrip_tools.py`
- Add/Subtract・10万点判定：`tools/test_map_roundtrip_zones.py`
- 登録・保存復元：`tools/test_map_roundtrip_zone_registry.py`
- 旧データ移行・Empty一括選択：`tools/test_map_roundtrip_zone_migration.py`
- 実UI：`tools/ui_test_map_roundtrip_zones.py`、`tools/ui_test_map_roundtrip_native_fbx.py`

[過去の性能測定と制約](VALIDATION.md)。0.1.0では6万件Replace約282.5秒でした。0.2.0でも配置生成アルゴリズムは同じです。
