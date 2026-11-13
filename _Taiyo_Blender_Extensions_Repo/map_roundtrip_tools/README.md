# Map Roundtrip Tools

**対象version: 0.7.0 / Blender 4.5.0以上**

ゾーン管理・配置CSV・HoudiniとのFBX往復・リンク複製での配置復元を担当するExtensionです。Unreal Bridge Toolsなしで利用できます。

[詳細使用書：Zone登録からCSV・FBX・配置復元まで](WORKFLOW_JA.md)

## 基本操作

`View3D > Sidebar (N) > Map Roundtrip > Zones`（最上部）で、上から順に操作します。

1. **ゾーンを選ぶ**: 一番上の`Zone`（＋でNew Zone）。
2. **1. Define Range**: ゾーンに入れたいMeshを選んで **Add Selected Objects**。各Meshの原点にCube Emptyが自動で作られ、近い原点は`Merge Distance`以内で1つにまとまります。未選択のMeshが範囲に入らないよう自動で分割します。手で作るなら`Add Empty`／`Register Selected Empties`。各EmptyのAdd／Subtractで範囲を合成できます。
3. **2. Check**（折りたたみ）: **Select Meshes In Zone**で範囲内のMeshを確認用に選択。
4. **3. Export CSV**: **Export ZONE_A.csv**。**選択に関係なく**、`Zone`で選んだゾーンの範囲内のMeshを`ゾーン名.csv`へ出力します。`All Zones`ならゾーンごとに別ファイル。正常終了時だけ同じ名前のub_zoneタグを付与します。

`Zone Empties`（折りたたみ）にはEmptyの一覧・検索・`Select Zone Empties`があります。

CSVの12列、ワールド座標、XYZ回転の度数、名前正規化は維持します。Mesh CandidatesでMap配下／現在Sceneを選べます。旧UBTの登録ゾーン・EmptyのAdd/Subtract・登録解除状態も読み取れます。

0.6.0からの変更（動作が変わります）:
- **Replace Zoneは差分更新**になりました。`ub_csv_id`で元のObjectと対応づけ、変わっていないObjectは触らず、動いたObjectはその場で更新し、使わなくなったObjectは`_Replaced_ZONE_A`へ元の階層のまま退避し、新しいものだけ作ります。`Delete`は廃止しました。`ub_csv_id`の無いゾーンは、先にExport Zone CSVをやり直します。
- **Restore Original Map / Re-apply Imported Map**で、最初のマップと取り込み後のマップを切り替えられます。
- **追加Mesh**: `New Meshes To`で取り込み先を選べます。`Placement CSV`を先に指定すると、`colname`の階層を取り込み先の中に再現します。
- **Previewのエラー**を、CSVの行・列・値・理由まで出します。全件は`MRT Placement Report`（Textエディター）に書きます。
- **Helperパネル**を追加しました。Library/FromHoudiniのObjectがMapでどう使われているかを調べ、選択できます。
詳しくは[詳細使用書](WORKFLOW_JA.md)の8章と10章。0.6.0のZIPは詳細使用書の「過去バージョン」にあります。

0.5.1からの変更: Add Selected Objectsで作るEmptyが、シーンのルートではなく、元のMeshがいるCollectionへ入ります。まとめたEmptyの元のMeshが複数のCollectionにまたがるときは、多いほう（同数ならシーンで先のCollection）へ入り、件数をステータスに出します。詳しくは[詳細使用書](WORKFLOW_JA.md)。

0.5.0からの変更: コードの動作は同じで、使用書に「Houdiniで変えた内容の扱い」（移動・削除・追加Mesh・引き継がれないもの）を追記しました。

0.4.0からの変更: CSVの`colname`が、Map Collectionからの階層パス（例 `Area1/Rocks`）になりました。Replace Zoneは、Mapの下に無いCollectionを入れ子のまま作り、元の階層へ戻します。パスの無い旧CSVは従来どおり名前だけで探します。詳しくは[詳細使用書](WORKFLOW_JA.md)の「Collectionの階層」。

0.3.0からの変更: CSVの`id`をMeshの`ub_csv_id`に保存し、Houdiniから戻すときに使います。`id=-1`は追加Mesh、書き出し時に無かった`id`の行は使いません。ゾーンに`ub_csv_id`が無い旧版の書き出しは、従来どおり判定しません。詳しくは[詳細使用書](WORKFLOW_JA.md)の「idの扱い」。

0.2.0からの変更: CSV出力は「選択したMesh」から「ゾーン範囲内のMesh」へ変わりました。Export Selected CSVの前にSelect Meshes In Zoneを押す手順は不要です。[0.2.0のZIP](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/map_roundtrip_tools-0.2.0.zip)

## FBXとImport

通常はExport FBX (Blender)でBlender標準の設定・プリセット画面を使用します。個別一括出力はAdvanced / Batch Exportにあります。

ImportではLibrary（元Mesh）とMap（配置先）を指定します。追加Meshがある場合だけImport New Meshesを実行し、Placement CSVをPreviewしてからReplace Zoneを実行します。動いたObjectはその場で更新し、使わなくなったObjectは退避し、いつでも最初のマップへ戻せます。作業前に.blendを保存してください。大量処理のUndo履歴は作りません。

Exchange Folder／Return Folderは参考欄です。パス自動連動やファイル監視はありません。

## 検証

- 基本配置・FBX・ゾーンCSV（旧UBT互換のタグ復元を含む）：`tools/test_map_roundtrip_tools.py`
- ゾーン範囲のCSV（選択に依存しない・All Zones・復元）：`tools/test_map_roundtrip_zone_csv.py`
- Replace Zoneの差分更新・復元・Previewのエラー詳細・Importパネル：`tools/test_map_roundtrip_restore.py`
- 追加Meshの取り込み先とcolname階層：`tools/test_map_roundtrip_mesh_import_paths.py`
- Helperパネル：`tools/test_map_roundtrip_helper.py`
- 実UI（物理ESC・Replace・Restore・Re-apply）：`tools/ui_test_map_roundtrip_tools.py`、60k実測：`tools/benchmark_map_roundtrip_diff.py`
- Add Selected ObjectsのEmptyの置き先Collection（各Collection・多数決・同数・複数所属・ESC取り消し）：`tools/test_map_roundtrip_empty_collection.py`
- colnameの階層パス（書き出し・解決・入れ子の作成・名前の衝突・ロールバック・往復）：`tools/test_map_roundtrip_colname_path.py`
- CSVのid（`ub_csv_id`保存・`-1`・不明id・旧版ゾーン・往復）：`tools/test_map_roundtrip_csv_id.py`（`-- import` / `-- export`で片側だけ実行）
- Add Selected Objects（まとめ・分割・混入防止・ロールバック・座標が大きい場合）：`tools/test_mrt_zone_from_objects.py`、`tools/test_map_roundtrip_add_objects.py`
- Zones UIの構成・固定行・Empty一覧の上限：`tools/test_map_roundtrip_ui_layout.py`
- Add/Subtract・10万点判定：`tools/test_map_roundtrip_zones.py`
- 登録・保存復元：`tools/test_map_roundtrip_zone_registry.py`
- 旧データ移行・Empty一括選択：`tools/test_map_roundtrip_zone_migration.py`
- 実UI（ESC・Undo/Redo・描画）：`tools/ui_test_map_roundtrip_add_objects.py`、`tools/ui_test_map_roundtrip_zones.py`、`tools/ui_test_map_roundtrip_native_fbx.py`
- 6万Objectの実測：`tools/benchmark_map_roundtrip_add_objects.py`

[過去の性能測定と制約](VALIDATION.md)。0.1.0では6万件Replace約282.5秒でした。0.7.0では、Replace Zoneを差分更新にして処理の流れを変えました（6万件の実測は検証報告）。
