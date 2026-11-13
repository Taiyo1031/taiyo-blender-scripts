# Map Roundtrip Tools

**対象version: 0.9.2 / Blender 4.5.0以上**

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

0.9.1からの変更（0.9.2、不具合の修正）: ①前のReplace Zoneで`use`が0として退避したObjectを、新しいCSVの`use`が1の行で**戻せる**ようになりました。以前は、退避済みのObjectは`unknown id`として使われず、新しいCSVを適用する手段がありませんでした（Restore Original Mapの後はReplaceも止まります）。退避済みのObjectは、`_Replaced_<ゾーン名>`からMapへ戻り、行の位置・Mesh・Collectionで更新されます。②Restore Original Map / Re-apply Imported Mapを一度でも行うと、前のReplaceで作ったObjectを`id`が-1の行へ対応づけられず、Replaceのたびに重複して作っていました。実シーンのコピーでは、退避済みの屋根瓦428個が戻り、Replaceは約2.7秒でした。

0.9.0からの変更（0.9.1、不具合の修正）: ①Replace Zoneを同じCSVで繰り返すと、`id`が-1の行のObjectが毎回増えていました。前回のReplaceで作ったObjectを`id`が-1の行へ対応づけて更新します。②名前が衝突して`.001`が付いたCollectionが、毎回「移動」と判定され、新しいCollectionも作られていました。頼んだ名前を覚えて、同じCollectionとして扱います。③回転が変わっていないObjectが「移動」と数えられることがありました（同じ回転でも、四元数の符号が逆だと差が360度と出ていました）。実シーンのコピーでは、Replace後のPreviewが`moved 139`、`added 8`から、どちらも0になりました。

0.8.1からの変更（0.9.0、**動作の変更**）: 戻りCSVに`use`列（`1`＝使う、`0`＝元のマップから消す）を足せるようになりました。消す（`_Replaced_<ゾーン名>`へ退避する）のは、`use`が`0`の行の`id`のObjectだけです。**戻りCSVに行が無い`id`のObjectは、動かさず、そのまま残します**（これまでは退避していました）。`use`が`0`の行は何も置かず、警告も出しません。`use`列が無いCSVは、すべて使う行として読みます。Previewには`Retire N (use 0: M rows)`と`Not in CSV, left as they are: N`が出ます。大量退避の警告`many_retired`はなくなりました。

0.8.0からの変更（0.8.1、表示の修正）: Previewの`New meshes (id -1)`が、Libraryにまだ無い新しいMeshの行を数えず、`id`が-1の行が数個あっても`0`と出ていました。`0 of 8 rows`のように、`id`が-1の行の数と、Libraryにあって置けるMeshの数を並べて出し、足りないときは「Import New Meshesを実行してください」と赤字で案内します。

0.7.2からの変更（0.8.0）:
- **Convert Houdini FBX to Blender size**（チェックボックス、**既定OFF**）: HoudiniのFBXが持つ回転・スケールをMeshデータへ焼き込み、Blenderのサイズ・向きにそろえます。HoudiniのFBXを取り込むときは、チェックを入れてください（0.7.2は常にONでした）。
- **Archive To**: 退避用の`_Replaced_<ゾーン名>` Collectionを作る場所を指定できます（空欄はシーンの最上位）。
- **Rename Zone**: `Zone`欄の横の✎で、ゾーン名を変更できます。Empty・Object・退避用Collectionも一緒に更新します。
- **Emptyの登録解除でEmptyも削除**します（一覧のゴミ箱アイコン。Ctrl+Zで戻せます）。
- **Previewの案内**: `id = -1`の行は必ず「新しいMeshです」と案内、Libraryの重複名は名前ごとに1件、ゾーンの大半が退避されるときは警告。

0.7.1からの変更（追加の修正）:
- **Ctrl+Z（Undo）**で、Replace Zone・Restore・Import New Meshesを1回分ずつ取り消せます。以前は、退避したObjectの`ub_zone`などのカスタムプロパティが戻らず、中途半端な状態になりました。
- **ボタンの位置**: Import パネルの`Replace Zone`欄で、`Import New Meshes`・`Replace Zone`・**`Restore Original Map`**（Replaceを1回行うと出ます）を、警告リストより上へ移しました。サイドバーをスクロールしなくても押せます。

0.7.1からの変更（不具合の修正）: Houdini（Y-up・cm）のFBXから取り込んだ新しいMeshが、CSVの位置に置かれず、向きが違い、100倍の大きさになる問題を直しました。FBXのObjectは「X回転90度・スケール0.01」を持ち、Meshデータは元の座標のままです。配置はMeshデータだけを使うため、取り込み時にこの変換をMeshデータへ焼き込み、Libraryと同じ（Z-up・m・変換なし）にしました。

0.7.0からの変更（不具合の修正）: `New Meshes To`を`Library`の外のCollection（例 `NewOBJs`）にしたとき、取り込んだMeshがPreview/Replaceで「Libraryに無い」と判定され、`added 0`になる問題を直しました。`New Meshes To`もLibraryと同じ検索対象です（Mapの中は対象外）。HelperもそのCollectionを含めて調べ、大規模シーンでの照合も高速にしました。

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
