# Map Roundtrip 詳細使用書

**対象version: Map Roundtrip Tools 0.2.0 / Blender 4.5.0以上**

## 1. 担当する機能

ゾーン管理・Empty編集・範囲選択・ゾーンCSV・FBX入出力・配置復元は、すべて `N > Map Roundtrip` で行います。**Unreal Bridge Toolsを有効にする必要はありません。**

Unreal Bridge Tools 2.3.3は2.2.20相当の元の機能へ戻しました。従来のCollection/Scene CSV、Collision Tag、Filters、Presets用です。Selectedスコープ・Zone UI・ゾーンタグ付けはUBTから取り除きました。

作業前に.blendを保存してください。大量配置のReplaceはUndo履歴を作りません。

## 2. Zoneを登録する

1. `Map Roundtrip > Zones > New Zone`を押します。
2. `Zone Name`に `ZONE_A` などを入力します。
3. `Zone`一覧で操作するゾーンを選びます。新規登録直後はEmptyがない空のゾーンです。
4. `Add Empty`で新しい箱を作るか、既存Emptyを選び `Register Selected Empties` で登録します。

別ゾーンもNew Zoneで登録します。ゾーン一覧と所属は.blendに保存されます。旧UBTで作ったEmptyと登録済みゾーンも読み取れます。旧UBTのAdd/Subtract・登録解除状態を保持します。旧UBTが無効でも利用できます。

### 新しいEmpty

Add Emptyは3Dカーソル位置にCube Emptyを作り、選択・アクティブにします。繰り返すと1ゾーンに複数の箱を追加できます。初期display size=1は各軸の半径1です。`G`で移動、`R`で回転、`S`で拡大して範囲を作ります。

### 既存のEmpty

Zoneを選び、ビューポート／OutlinerでEmptyを選択してRegister Selected Emptiesを押します。名前は変更せず、Cube表示にします。位置・回転・スケールは保持します。別ZoneのEmptyを登録すると所属が移ります。名前がZONE_から始まらなくても登録できます。

### 一覧の操作

- **Empty名ボタン**：そのEmptyを選択して編集します。
- **Add / Subtract**：追加／くり抜きの役割を変更します。
- **×**：登録のみ解除します。Object本体は削除しません。

## 3. ゾーンをまとめて選択する

目的によってボタンを分けています。

| ボタン | 選ぶ対象 | All Zonesを選んだ場合 |
|---|---|---|
| **Select Zone Empties** | 選択中のゾーンを構成するEmpty | 全ゾーンのEmptyをまとめて選択 |
| **Select Meshes In Zone** | ゾーン範囲内に原点が入るMesh | 全ゾーンの範囲に入るMeshをまとめて選択 |

箱をまとめて移動・拡大したいときはSelect Zone Emptiesを使います。Houdiniへ送る配置を選ぶときはSelect Meshes In Zoneを使います。非表示・選択禁止のObjectは選択せず、件数を報告します。

Mesh選択の `Mesh Candidates` は次の2通りです。

- **Map Collection**：指定したMapとその子CollectionのMeshを候補にします。
- **All Scene Meshes**：現在SceneのMeshを候補にします。

## 4. AddとSubtract

```text
ZONE_A =（Addの箱① ＋ Addの箱②）－（Subtractの箱③ ＋ Subtractの箱④）
```

箱の順序は関係ありません。Subtractは同じゾーンだけに作用します。Subtractだけのゾーンは空です。判定するのはMeshの原点で、形状やバウンディングボックスの交差ではありません。Mesh自体を切断するBooleanでもありません。編集後はSelect Meshes In Zoneを実行し直してください。

従来のZONE_A / ZONE_A.001というCube Emptyは同じゾーンとして自動検出します。Zone Prefixはこの検出用です。UI登録したEmptyは名前の接頭辞に依存しません。

## 5. ゾーンCSVを書き出す

1. 個別のZone（例ZONE_A）を選びます。
2. Mesh CandidatesとMapを指定して **Select Meshes In Zone** を押します。
3. 必要ならMeshの選択を手動で絞ります。
4. `CSV Output Folder`を指定します。例 `//houdini_io/out`。
5. Libraryの名前に合う `Name Normalize` を指定します。通常はRemove Numeric Suffixです。
6. **Export Selected CSV** を押します。

選択Meshだけを **ZONE_A.csv** へ出力し、正常終了時だけ `ub_zone=ZONE_A` を付けます。ファイル名とタグは現在のZone名に揃います。CSVは従来と同じ12列、ワールド座標、XYZ回転の度数、小数6桁です。UBTのScope切り替えは不要です。

All Zonesは選択用です。ゾーン別CSVを出すときは個別ゾーンを選んでください。選択ゼロ・読み取り専用ObjectなどのエラーやESC中断では、既存CSVと元のタグを保持します。

範囲を変えても過去のub_zoneタグは自動で消しません。既に出力したゾーンを縮小した場合は、Replaceの旧対象件数を確認してください。

## 6. Exchange Folderとは

BlenderとHoudiniで受け渡す場所の**参考メモ**です。変更しても各パスは連動せず、作成・監視・自動取込もしません。Return Folderも同様です。

`//`は、保存した.blendからの相対パスです。

```text
Project/
  map.blend
  houdini_io/
    out/ZONE_A.csv      ← CSV Output Folderで指定する出力
    out/fbx/           ← 個別一括FBXのOutput Folderの例
    in/ZONE_A.csv      ← Placement CSVで指定する戻りファイル
    in/new_meshes.fbx  ← Mesh FBXで指定する追加Mesh
```

実際に使うパスはCSV Output Folder、標準FBX画面の保存先、補助機能のOutput Folder、Placement CSV、Mesh FBXです。

## 7. FBXと標準プリセット

Libraryの必要なMeshを選択して **Export FBX (Blender)** を押します。Blender標準のファイル画面で保存先・設定・標準プリセットを選べます。既定は選択Meshのみ、頂点カラーLinearです。

PathsのFBX Nameは初期ファイル名と補助機能Combinedの名前です。ゾーンの所属や置換タグを変える欄ではありません。

Objectごとの個別FBX一括出力は **Advanced / Batch Export** を開き、Files=Per Objectにします。標準Batch ModeにはObjectごとの自動分割がないため、この補助機能を残しています。標準プリセットと補助機能のJSONプリセットは別です。

Unreal用の個別SMなら、配置Objectではなく原点に置いたLibrary本体を選んで出力します。

## 8. Houdiniから戻す

1. Import > Collectionsで **Library** と **Map** を指定します。例ForExport_Dirty_1／Laid_MAP_1。名前は自由です。
2. 新しいMeshがある場合だけMesh FBXを指定し、Import New Meshesを実行します。既定の入れ先はLibrary/FromHoudiniです。
3. 戻りのPlacement CSVを指定します。
4. Replace ZoneのZoneを元のタグ（例ZONE_A）に合わせます。CSV出力成功時にはこの欄にもZone名が設定されます。空欄なら戻りCSV名を使用します。
5. Dry Run ONでPreview Placementを確認し、OFFにしてReplace Zoneを実行します。

Archiveは旧配置を保持して退避します。Deleteは明示選択時だけ削除します。旧対象はMap配下だけでなく、全データの同じub_zoneを持つObjectです。CSV名をZONE_A_return.csvに変えて返す場合も、置換タグはZONE_Aを維持してください。

## 9. ヒント・注意

ボタンや入力欄にマウスを置くとヒントが出ます。出ない場合はPreferences > InterfaceのTooltips設定を確認してください。選択操作はObject Modeで実行します。

性能測定は[検証報告](VALIDATION.md)を参照してください。0.1.0の6万件Replaceは約282.5秒で、生成の非線形性と分割不能な同期が残っています。担当アドオンを移しても、この配置生成の制約が解消したわけではありません。
