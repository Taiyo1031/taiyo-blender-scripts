# Map Roundtrip Tools

**対象version: 0.1.0 / Blender 4.5.0以上**

巨大マップの一部をHoudiniで加工して戻すためのExtensionです。配置CSVはUnreal Bridge Tools 2.3.0で書き出し、戻ったCSVをMesh共有のリンク複製として再生成します。両アドオンは独立して有効化できます。Houdini／Unreal側の実装・座標変換は含みません。

## 使い方

1. 作業前に`.blend`を保存してください。大量処理のUndo履歴は作りません。
2. Unreal Bridge Toolsでライブラリ名に対応するName Normalizeを指定し、`Zones > Select In Zone`で対象を選びます。ScopeをSelectedへ変更し、`ZONE_A.csv`へ出力します。Tag Exported ObjectsはONにします。
3. HoudiniへCSVと必要なFBXを渡し、同じ12列の配置CSVと追加MeshのFBXを返してもらいます。
4. `View3D > Sidebar (N) > Map Roundtrip > Import`でLibraryとMapを指定します。ポインターは既定で未指定です。通常は`ForExport_Dirty_1`と`Laid_MAP_1`を指定します。
5. 追加Meshがある場合はMesh FBXを指定し、Import New Meshesを押します。入れ先はLibrary/FromHoudini。原点外のTransformは保持して警告します。
6. Placement CSVを指定し、Dry Run ONのままPreview Placementで件数と未解決名を確認します。Zone未指定ならCSVファイル名を使います。
7. Dry RunをOFFにしてReplace Zoneを実行します。既定のArchiveは旧配置をシーン直下の`_Replaced_<zone>`へ退避し、現在のView Layerから除外します。Deleteは明示選択した場合だけです。

## CSVと配置

```text
id,tx,ty,tz,rx,ry,rz,sx,sy,sz,objname,colname
```

UTF-8・カンマ区切り、Blenderワールド座標（Z-up）、XYZ回転の度数です。idは無視します。objnameはLibrary配下のMesh Object名を完全一致→正規化一致の順で検索し、colnameはMap配下を再帰検索します。空ならMap直下、未知ならMap直下に新規作成します。名前正規化の既定はnumeric_suffix。不正・非有限数値行と未解決名はスキップして件数を報告します。欠落列は実行を中止します。

新配置は親なし・Mesh共有です。`ub_zone`を付け、旧対象は**全bpy.data.objectsから同じタグのもの**を集めます。Map配下に限定しないため、Previewの旧対象件数を確認してください。Archive時は`ub_zone`を削除し`ub_archived_from`を付けます。繰り返し実行では直前の配置が置換されます。

## FBX Export

選択MeshだけをPer ObjectまたはCombinedで出力します。Combinedの名前はZone Nameです。ファイル名の英数字・`_`・`-`以外は`_`にし、既存ファイルや衝突には`_2`以降を付けます。中断までに作成したFBXは残ります。

既定はScale=1、FBX Units Scale、Forward=-Z、Up=Y、Apply Modifiers ON、Smoothing=Face、**Vertex Colors=Linear**、Triangulate／Tangent Space／Apply Transform OFFです。Advanced全項目はJSONプリセットへ保存できます。組み込みUnreal SM (Default)は変更・削除できません。保存先はBlender CONFIG/map_roundtrip_tools/presets.jsonです。

追加Meshの同名処理はSKIPが既定。UPDATEは`user_remap`により**そのMeshを共有する全Object**へ変更が波及します。複製マテリアルは既存の同基本名を優先して再利用します。

Exchange FolderとReturn Folderは参考パスです。明示した各入出力パスを自動変更しません。FBX出力フォルダーが作れない場合は中止します。

## 進捗・中断

timerの時間予算は約0.3秒、進捗更新は約0.18秒間隔です。実行中はUI操作をロックし、ESCで中断できます。配置作成・Archive途中の中断は新規Object／Collectionを除去し、旧所属・タグを復元します。復元中は再中断を受け付けません。Deleteは最終確定処理です。

**性能目標は一部未達です。** Blender 4.5.9で6万件のReplaceは約282.5秒、最長の単一stepは約3.88秒でした。生成時間は線形ではありません。

FBXオペレーター呼び出し・依存グラフの最終同期・batch_removeはBlender側の一括APIであり、呼び出し途中のESCを処理できません。実測結果は[検証報告](VALIDATION.md)を参照してください。

## 検証の実行

- `blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_tools.py`
- `blender --background --factory-startup --python-exit-code 1 --python tools/benchmark_map_roundtrip_tools.py`
- `blender --factory-startup --enable-event-simulate --python tools/ui_test_map_roundtrip_tools.py`

同梱tools/bench_make_scene.pyはText Editorで実行できます。LIB_COUNT／MAP_COUNT／ZONE_COUNTを変更して再現シーンを作成します。
