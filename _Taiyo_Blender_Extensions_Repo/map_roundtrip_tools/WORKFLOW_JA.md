# Map Roundtrip 詳細使用書

**対象version: Map Roundtrip Tools 0.1.1 / Unreal Bridge Tools 2.3.2 / Blender 4.5.0以上**

## 1. どのパネルを使う？

| 作業 | パネル |
|---|---|
| Zone登録・Emptyで範囲編集・配置CSV出力 | `N > Unreal Bridge Tools` |
| FBX出力・HoudiniからのMesh取込・CSVから配置を復元 | `N > Map Roundtrip` |

作業前に.blendを保存してください。大量配置のReplaceはUndo履歴を作りません。ZoneのEmpty追加・登録・解除には通常のUndoがあります。

## 2. 最初の準備

`Map Roundtrip > Import > Collections`に次を指定します。

- **Library**：配置の元になるMesh Objectの保管場所。例 `ForExport_Dirty_1`。
- **Map**：配置を復元するCollection。例 `Laid_MAP_1`。
- **New Meshes To**：追加Meshを置くLibrary内の子Collection名。既定 `FromHoudini`。

名前をそのまま使う必要はありません。実際のCollectionを指定してください。LibraryとMapは別の役割です。

## 3. Zoneはどう指定する？

### 新しいZoneをUIに登録する

1. `Unreal Bridge Tools > Zones > New Zone`を押します。
2. `Zone Name`へ **ZONE_A** などを入力して確定します。
3. `Zone`一覧に登録され、そのZoneが選ばれます。この時点では空のZoneです。
4. `Add Empty`で範囲を作るか、次の「既存Emptyの登録」を行います。

別のZoneはもう一度New Zoneで `ZONE_B` などを登録します。Zone一覧は.blendに保存されます。**Zoneを選ぶだけでは、まだMeshの選択もCSV出力も実行しません。**

### 新しい範囲Emptyを追加する

1. `Zone`で登録先を選びます。
2. `Add Empty`を押します。
3. 3Dカーソルの位置にCube Emptyが追加され、選択・アクティブになります。
4. `G`で移動、`S`で拡大、`R`で回転して範囲を調整します。初期display size=1は、各軸の半径1の箱です。

Add Emptyを繰り返すと同じZoneに複数の箱を作れます。All Zonesの状態からAdd Emptyを押す従来の作成ダイアログも利用できます。

### すでにあるEmptyを登録する

1. `Zone`で登録先（例ZONE_A）を選びます。
2. ビューポート／Outlinerで登録したいEmptyを選択します。複数選択できます。
3. `Register Selected Empties`を押します。

Object名は変えません。表示をCubeへ変更し、位置・回転・スケールを保持します。名前が `ZONE_` から始まらなくてもUI登録できます。別Zone所属のEmptyを登録すると所属を変更します。Meshは登録対象になりません。

### 一覧から編集・登録解除する

- 一覧の**Empty名ボタン**：そのEmptyを選択して編集します。非表示・選択禁止なら先に解除してください。
- **Add / Subtract**：範囲を足す／くり抜く役割を変更します。
- **×**：Zone登録だけを解除します。Empty本体は削除しません。再度Register Selected Emptiesで登録できます。

明示登録した所属はカスタムプロパティ `zone` に保存します。従来の `ZONE_A` / `ZONE_A.001` のようなCube Emptyは自動検出も継続します。Zone Prefixはこの自動検出に使う接頭辞です。

## 4. AddとSubtractの使い分け

```text
ZONE_A =（Addの箱① ＋ Addの箱②）－（Subtractの箱③ ＋ Subtractの箱④）
```

Addの範囲をすべて合成してから、Subtractの合成範囲を引きます。箱の並び順は関係ありません。Subtractは所属Zoneにだけ作用し、別Zoneの範囲を削りません。SubtractしかないZoneは空の範囲です。

判定するのは**Mesh Objectの原点**です。形状の一部が箱にかかっていても、原点が外なら選ばれません。Mesh自体を切断するBooleanではありません。範囲の編集後はSelect In Zoneを実行し直します。

## 5. Zoneの配置をCSVへ書き出す

1. `Scope = Recursive`、`Target Collection = Mapの配置Collection`にします。
2. `Zones > Zone = ZONE_A`を選びます。
3. `Select In Zone`を押し、選択数を確認します。空のZoneなら先にEmptyを登録してください。
4. **ScopeをSelectedへ変更**します。SelectedのままSelect In Zoneは実行できません。
5. `Name Normalize`をLibraryの名前に合う設定にします。通常はRemove Numeric Suffixで配置名末尾の`.001`等を除きます。
6. `Export CSV`のパスを、例 `//houdini_io/out/ZONE_A.csv`にします。
7. `Tag Exported Objects (ub_zone)`をONにし、`CSV zone tag: ZONE_A`の表示を確認してExport CSVを実行します。

**重要：ub_zoneはZoneドロップダウンではなく、CSVのファイル名から決まります。** ZONE_Aを選んでも出力先がTest.csvならタグはTestです。Zone名とCSV名を揃えてください。Zoneを切り替えてもファイルパスは自動変更しません。

All Zonesは全Zoneの選択結果をまとめますが、CSV列にZone列は追加しません。Zone別に往復する場合はZONE_A.csv、ZONE_B.csvを別々に出力します。名前順に重なる範囲が解決されます。

過去のCSV出力で付いたub_zoneは、Emptyの編集や登録解除では自動で消しません。既に書き出したZoneを縮小した場合、Replace前に旧対象件数も確認してください。

## 6. Exchange Folderって何？

**BlenderとHoudiniでファイルを受け渡すフォルダーの参考メモ**です。既定 `//houdini_io` の `//` は、保存した.blendファイルの場所からの相対パスです。

例：

```text
Project/
  map.blend
  houdini_io/             ← Exchange Folderの参考例
    out/
      ZONE_A.csv         ← UBTのExport CSVで指定
      fbx/               ← 補助FBX出力のOutput Folderで指定
    in/
      ZONE_A.csv         ← MRTのPlacement CSVで指定
      new_meshes.fbx     ← MRTのMesh FBXで指定
```

Exchange Folderを変えても、他のパスは連動しません。この欄だけでフォルダー作成・コピー・ファイル監視・自動取込は行いません。Return Folderも同じく参考欄です。**実際に使うのはExport CSV、標準FBX画面の保存先、補助機能のOutput Folder、Placement CSV、Mesh FBXです。**

## 7. FBXはBlender標準UIから書き出す

1. Libraryの必要なMeshを選択します。Unrealの個別SM用なら、配置Objectではなく原点に置いたLibrary本体を選びます。
2. `Map Roundtrip > Export > Export FBX (Blender)`を押します。
3. Blender標準のファイル選択・FBX設定画面が開きます。保存先とファイル名をここで決めます。
4. 標準UIの設定とプリセットを使って書き出します。初期設定は選択Meshのみ、Vertex Colors=Linearです。

PathsのFBX Nameは標準画面の**初期ファイル名**と補助機能Combinedの名前に使います。範囲選択やub_zoneタグを設定する欄ではありません。標準画面での設定変更は、その標準オペレーター側で扱い、補助機能の独自JSONプリセットへは同期しません。

### Objectごとの個別FBXを一括出力したい場合

`Advanced / Batch Export`を開き、Files=Per Object、Output Folder等を指定して内部のExport FBXを押します。こちらは従来の補助機能です。独自のPreset／Advanced設定はこの折りたたみに残しています。

Blender標準のBatch ModeはScene／Collection単位で、Objectごとの自動分割はありません。標準プリセットと補助機能のJSONプリセットは別です。

## 8. Houdiniから戻して配置を復元する

1. Houdiniは同じ12列のCSVを返します。CSVはBlenderのワールド座標、XYZ回転の度数です。
2. 新しいLibrary Meshがある場合だけ、Mesh FBXを指定してImport New Meshesを実行します。
3. Placement CSVを指定します。Import > Replace ZoneのZoneを**元のCSVタグと同じZONE_A**にします。空欄なら戻りCSVのファイル名を使います。
4. Dry Run ONでPreview Placementを押します。旧対象、新規件数、未解決名を確認します。
5. Dry RunをOFFにしてReplace Zoneを実行します。既定Archiveは旧配置を保持して退避します。

戻りファイル名をZONE_A_return.csvへ変えた場合、Zoneは空欄にせずZONE_Aと明示してください。ImportのZoneは**置換タグ**であり、Empty一覧を直接読む欄ではありません。旧対象はMap配下に限らず、全データの同じub_zoneを持つObjectです。

## 9. ホバーヒントとよくある疑問

- ボタンや入力欄にマウスを置くとヒントが出ます。出ない場合はBlenderのPreferences > InterfaceのTooltips設定も確認してください。
- Zoneに何も選べない：New Zoneで登録し、EmptyをAddまたはRegisterしてください。
- Select In Zoneが動かない：Object Mode、Scope=Recursive等、候補Collectionの設定を確認してください。
- 範囲内なのにMeshが選ばれない：原点、Subtract、非表示／選択禁止を確認してください。
- ImportのZoneを選んだのに範囲が変わらない：ImportのZoneはタグ指定です。EmptyはUnreal Bridge Tools側で編集します。
- 本格的な大量配置には時間がかかります。0.1.0の実測では6万件Replace約282.5秒でした。UI整理で生成性能の制約を解消したわけではありません。[検証報告](VALIDATION.md)を参照してください。
