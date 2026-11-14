# Map Roundtrip 詳細使用書

**対象version: Map Roundtrip Tools 0.10.0 / Blender 4.5.0以上**

## 1. 担当する機能

ゾーン管理・Empty編集・範囲選択・ゾーンCSV・FBX入出力・配置復元は、すべて `N > Map Roundtrip` で行います。**Unreal Bridge Toolsを有効にする必要はありません。**

Unreal Bridge Tools 2.3.3は2.2.20相当の元の機能へ戻しました。従来のCollection/Scene CSV、Collision Tag、Filters、Presets用です。Selectedスコープ・Zone UI・ゾーンタグ付けはUBTから取り除きました。

作業前に.blendを保存してください。Import（ゾーンの入れ替え）は、Ctrl+Zで1回分を取り消せます。

## 2. Zoneを登録して範囲を作る

操作は `N > Map Roundtrip > Zones`（最上部）で行います。上から次の順に並んでいます。

```text
Zones
  [ZONE_A ▾] [✎] [＋]                  操作するゾーン。✎はゾーン名の変更、＋はNew Zone
  [Map Collection | All Scene Meshes]  対象Meshの範囲（Map Collectionのときだけ Map 欄）
  ▾ 1. Define Range   Add Selected Objects / Merge Distance / Add Empty / Register Selected Empties
  ▸ Zone Empties      Emptyの一覧・検索・選択（折りたたみ）
  ▸ 2. Check          Select Meshes In Zone（折りたたみ）
  ▾ 3. Export CSV     CSV Output Folder / Name Normalize / Export ZONE_A.csv
  ▸ Advanced          Zone Prefix（折りたたみ）
```

1. `Zones`の`＋`（New Zone）を押し、`Zone Name`に `ZONE_A` などを入力します。
2. 一番上の`Zone`で操作するゾーンを選びます。この`Zone`は、Export・Import・Helperを含む全パネルで共通です（各パネルの先頭に、いまのゾーンとマップの状態が出ます）。新規登録直後はEmptyがない空のゾーンです。
3. 範囲を作ります。方法は2通りです。
   - **A. 選択したObjectからまとめて作る（おすすめ）**: ゾーンに入れたいMeshを3Dビューで選択し、`1. Define Range > Add Selected Objects`を押します。
   - **B. 手で作る**: `Add Empty`で新しい箱を作るか、既存Emptyを選び `Register Selected Empties` で登録します。

**ゾーン名の変更**: `Zone`欄の横の✎（Rename Zone）で、選んだゾーンの名前を変えられます。ゾーンのEmpty、ゾーンに属するObject（`ub_zone`、`ub_run`）、退避用の`_Replaced_<ゾーン名>`とその中のCollectionの名前も一緒に更新します。同じ名前のゾーンやCollectionが既にあるときは、何も変えずに止まります。Ctrl+Zで戻せます。**CSVのファイル名は自動では変わりません**が、Importは`Zone`の選択だけを使うので、ファイル名がずれても問題ありません。

別ゾーンもNew Zoneで登録します。ゾーン一覧と所属は.blendに保存されます。旧UBTで作ったEmptyと登録済みゾーンも読み取れます。旧UBTのAdd/Subtract・登録解除状態を保持します。旧UBTが無効でも利用できます。

### Add Selected Objects（選択Meshをまとめてゾーンへ追加）

選択中のMeshの原点にCube Emptyを自動で作り、現在のゾーンへ追加します。`Zone`が`All Zones`の間は押せません。追加先のゾーンを選んでください。

- **対象**: 選択中の**Meshだけ**です。Meshでない選択は無視し、件数を表示します。
- **原点にEmptyを作る**: 各Meshの原点が範囲に入るEmpty（Add）を作ります。
- **近ければ1つにまとめる**: `Merge Distance`（既定1 m）の格子で近い原点を1つのEmptyにまとめます。`0`なら1個ずつ作ります。
- **他のObjectを含めない**: 選択していないMeshの原点がEmptyの範囲に入る場合は、自動でEmptyを分割します。未選択のMeshと原点がほぼ同じで分けられないObjectには、Emptyを作らず警告と件数を出します。
- **Emptyの置き先**: 作ったEmptyは、元のMeshがいるCollectionへ入ります（ネストしたCollectionも、シーンの最上位も同じ）。近い原点を1つにまとめたEmptyの元のMeshが複数のCollectionにまたがるときは、最も多いCollectionへ入ります。同数なら、シーンの中で先に並ぶCollectionです。まとめたEmptyのうち、複数のCollectionにまたがったものの数が、結果表示の`mixed-collection empties N`に出ます。複数のCollectionに入っているMeshは、シーンの中で最初に見つかる1つを使います。シーンにつながっていないCollectionや、編集できない（リンクされた）Collectionには入れず、シーンの最上位へ入れます。
- **重複しない**: すでにそのゾーンの範囲に入っているObjectには新しいEmptyを作りません。2回押しても増えません。既存のSubtractで除かれるObjectは `removed by Subtract` として件数に出ます。
- **判定する相手**: 未選択Meshの判定は`Mesh Candidates`（Map Collection / All Scene Meshes）に従います。
- **結果表示**: `Added N objects to ZONE_A with M empties; skipped ...; unseparable ...; removed by Subtract ...; ignored non-mesh ...; mixed-collection empties ...` の形で、状況表示の行に出ます。
- **進捗とキャンセル**: 進捗と残り時間が出ます。ESCで中断すると、作ったEmptyをすべて取り消します。Ctrl+Zで元に戻せます。
- **見え方**: 1つのObjectだけのEmptyは範囲がとても小さく（約2 mm）、3Dビューでは点にしか見えません。確認は`Zone Empties`の一覧、または`Select Zone Empties`で行います。広げたいときはEmptyを選んで`S`で拡大してください。

### 新しいEmpty

Add Emptyは3Dカーソル位置にCube Emptyを作り、選択・アクティブにします。繰り返すと1ゾーンに複数の箱を追加できます。初期display size=1は各軸の半径1です。`G`で移動、`R`で回転、`S`で拡大して範囲を作ります。

### 既存のEmpty

Zoneを選び、ビューポート／OutlinerでEmptyを選択してRegister Selected Emptiesを押します。名前は変更せず、Cube表示にします。位置・回転・スケールは保持します。別ZoneのEmptyを登録すると所属が移ります。名前がZONE_から始まらなくても登録できます。

### 一覧の操作（Zone Empties）

`Zone Empties`を開くと、ゾーンを構成するEmptyの一覧と検索欄があります。

- **Search**: 名前で絞り込みます（大小文字は区別しません）。
- **Empty名ボタン**：そのEmptyを選択して編集します。
- **Add / Subtract**：追加／くり抜きの役割を変更します。
- **ゴミ箱アイコン**（0.8.0）：登録を外し、**Empty本体も削除します**（以前の×は登録のみ解除でした）。Ctrl+Zで戻せます。範囲だけ残したいときは、削除せずにEmptyの`Zone Enabled`を使ってください。
- 数が多いときは先頭50件だけ表示し、`... and N more` と出ます。Searchで絞り込んでください。

## 3. ゾーンの中身を確認する・まとめて選択する

目的によってボタンを分けています。`Select Meshes In Zone`は`2. Check`にあります。

| ボタン | 選ぶ対象 | All Zonesを選んだ場合 |
|---|---|---|
| **Select Zone Empties**（Zone Empties内） | 選択中のゾーンを構成するEmpty | 全ゾーンのEmptyをまとめて選択 |
| **Select Meshes In Zone**（2. Check） | ゾーン範囲内に原点が入るMesh | 全ゾーンの範囲に入るMeshをまとめて選択 |

箱をまとめて移動・拡大したいときはSelect Zone Emptiesを使います。範囲の中身を目で確かめたいときはSelect Meshes In Zoneを使います。**CSVの書き出しにこの選択は不要です**（5章）。非表示・選択禁止のObjectは選択せず、件数を報告します。

Mesh選択の `Mesh Candidates` は次の2通りです。`Zones`の上部で切り替え、確認とCSV書き出しの両方に使われます。

- **Map Collection**：指定したMapとその子CollectionのMeshを候補にします。
- **All Scene Meshes**：現在SceneのMeshを候補にします。

## 4. AddとSubtract

```text
ZONE_A =（Addの箱① ＋ Addの箱②）－（Subtractの箱③ ＋ Subtractの箱④）
```

箱の順序は関係ありません。Subtractは同じゾーンだけに作用します。Subtractだけのゾーンは空です。判定するのはMeshの原点で、形状やバウンディングボックスの交差ではありません。Mesh自体を切断するBooleanでもありません。編集後は`2. Check > Select Meshes In Zone`で中身を確認してください。CSVは範囲を直接使います。

従来のZONE_A / ZONE_A.001というCube Emptyは同じゾーンとして自動検出します。Zone Prefixはこの検出用です。UI登録したEmptyは名前の接頭辞に依存しません。

## 5. ゾーンCSVを書き出す

**一番上の`Zone`で選んだゾーンの範囲内にあるMesh**を書き出します。Meshを選択しておく必要はありません。

1. 一番上の`Zone`で書き出すゾーン（例ZONE_A）を選びます。
2. `Mesh Candidates`（Map Collection / All Scene Meshes）を確認します。Map Collectionのときは`Map`も指定します。
3. `3. Export CSV`で`CSV Output Folder`を指定します。例 `//houdini_io/out`。
4. Libraryの名前に合う `Name Normalize` を指定します。通常はRemove Numeric Suffixです。
5. **Export ZONE_A.csv**（ボタンにはゾーン名が出ます）を押します。

ゾーン範囲内のMeshが **ZONE_A.csv** へ出力され、正常終了時だけ `ub_zone=ZONE_A` が付きます。ファイル名とタグは選んだZone名に揃います。非表示・選択禁止のMeshも出力に含まれます。CSVは従来と同じ12列、ワールド座標、XYZ回転の度数、小数6桁です。

- **All Zones**を選ぶと、ボタンは **Export CSV (every zone)** になり、ゾーンごとに別ファイル（ZONE_A.csv、ZONE_B.csv…）を出力します。複数のゾーンの範囲に入るMeshは、名前順で最初のゾーンのCSVだけに入ります。
- **1つのObjectは1つのゾーンだけに属します。** 複数のゾーンの範囲に入るMeshは、名前順で最初のゾーンのCSVにだけ入ります。ゾーンを個別に書き出しても同じ規則で、後ろのゾーンでは外れ、件数が結果表示に出ます（`left to that zone`）。重なりは`2. Check`の`Select Meshes In Zone`で確認できます。
- ゾーンの範囲にMeshが1つも入らないときはエラーになり、空のファイルは作りません。
- 読み取り専用Objectがある場合のエラーや、ESC中断では、既存CSVと元のタグを保持します。
- 進捗と残り時間が表示されます。ESCで中断できます。
- 範囲を変えても過去のub_zoneタグは自動で消しません。既に出力したゾーンを縮小した場合は、Replaceの旧対象件数を確認してください。

0.2.0までの「先にSelect Meshes In Zoneで選んでからExport Selected CSV」は不要になりました。

書き出した各行の`id`（各CSV内の1から始まる通し番号）は、そのMeshのカスタムプロパティ`ub_csv_id`にも保存されます。`ub_zone`と同じく正常終了時だけで、失敗・ESC中断では元の値に戻ります。CSVの列（12列）は変わりません。Houdiniから戻すときの照合には、0.10.0から使いません（8章）。

CSVの`colname`には、MeshがいるCollectionの**階層パス**が入ります。パスは`Map`に指定したCollectionの下からで、`/`で区切ります（例 `Area1/Rocks`）。Map直下のMeshは空欄です。Mapの外のCollectionにいるMeshは、シーンの最上位からのパス（例 `Other/Deep`）になります。`Map`が未指定のときも、シーンの最上位からのパスです。Collection名に`/`が含まれるときは、曖昧になるため名前だけを書きます。複数のCollectionに入っているMeshは、最初に見つかった1つだけを書きます。

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

## 8. Houdiniから戻す（Import）

`N > Map Roundtrip > Import` パネルで行います。作業前に`.blend`を保存してください。

**Importは、ゾーンの入れ替えです。** 選んだゾーンの元のObjectをすべて退避し、戻りCSVの全行を新しく配置します。書き出したCSVと戻りのCSVが多少違っても問題は起きません（`id`では照合しません）。**戻りCSVには、ゾーンの全Objectの行を入れてください。** CSVにないObjectも、退避されてマップから消えます。

### 手順

1. **Zone**: Importパネルの`Zone`リストで、入れ替えるゾーンを選びます（`Zones`パネルと同じZoneです。All Zonesは選べません）。CSVのファイル名とゾーン名は関係ありません。
2. **Collections**: `Library`（元のMeshの置き場。子Collectionも探します）と`Map`（配置先）を指定します。`Library`・`Map`・`New Meshes To`・`Archive To`の欄には、コレクションの色タグが付いたアイコンが出ます。
3. **Return Files**: `Placement CSV`（戻りのCSV）を指定します。追加Meshの置き場所を、このCSVの`colname`から決めるため、先に指定します。
4. 追加Meshがある場合だけ、`Mesh FBX`を指定して**Import New Meshes**を実行します。HoudiniのFBXは、`Convert Houdini FBX to Blender size`にチェックを入れてください。
5. `Dry Run`ONのまま**Preview Import**を押し、計画を確認します（後述）。
6. `Dry Run`をOFFにして**Import Zone**を実行します。
7. 結果が違ったら、**Restore Original Map**で元のマップへ戻せます。Ctrl+Zでも、Import 1回分を取り消せます。

全パネルの先頭に、いま操作しているゾーンと、そのマップの状態（`original` / `the imported CSV is shown` / `the ORIGINAL is shown`）が出ます。

### Importの動き（全置換）

| 対象 | Importの結果 |
|---|---|
| ゾーンの**元のObject**（`ub_zone`が付いていて、Importで作ったものではない） | すべて`_Replaced_<ゾーン名>`へ、**元と同じ階層のまま**退避します（`Archive To`で場所を指定。空欄はシーンの最上位）。CSVにないObjectも退避されます。 |
| **前回のImportで作ったObject**（このゾーンの2回目以降のImport） | **削除します**。元のObjectは退避に残っているので、いつでも元のマップへ戻せます。取り込み後に手で編集した内容は失われます。 |
| CSVの各行 | 新しいObjectとして置きます。`use`が0の行は何も置きません。 |
| 別のゾーンのObject | 触りません。 |

- 元のマップが表示中（`Restore Original Map`の後）でも、Importできます。このときは、退避中の前回のImportのObjectを削除し、元のObjectを退避して、CSVの全行を置きます。
- **置けない行があるとImportは実行されません**（そのObjectが消えてしまうため）。`objname`がLibraryにないMesh、読めない行、置く行が0件のCSVが対象です。先に`Import New Meshes`を実行するか、CSVを直してください。意図して飛ばすときは、`Skip rows that cannot be placed`をONにします（置く行が0件のときは、ONでも止まります）。
- CSVの行数が、ゾーンの今のObject数の半分に満たないときは、警告`fewer_rows`が出ます。部分的なCSVでImportすると、残りが退避されます。
- **処理の順序と取り消し**: 配置と退避をすべて済ませてから、最後に前回のImportのObjectを削除します。ESCや失敗では、配置と退避の前の状態へ戻ります。削除は1個あたり約10ミリ秒かかるため、小さな単位で進め、画面は止まりません。**削除が始まった後は、ESCでは中断できません**（途中で止めると、前回の分が重複して残るためです）。
- Importで作ったObjectの名前は、前回と同じ名前（`Rock`・`Rock.001`…）になります。退避中の元のObjectが名前を使っている間は、接尾辞が付きます。
- 旧版（0.6〜0.9）のReplaceで作ったObjectは、「前回のImportで作ったObject」として扱い、削除します。旧版が退避したObjectは、退避のまま残ります。

### 最初のマップへ戻す・もう一度適用する

Blenderの中には、Houdiniに出す前の**元のマップ**と、Import後の**取り込み後のマップ**の2つの状態が残ります。Importを実行すると、Importパネルに次が出ます。

- **Restore Original Map**: 退避した元のObjectを元の位置・Collectionへ戻し、Importで作ったObjectは退避用Collectionへ隠します。
- **Re-apply Imported Map**: 取り込み後のマップへ戻します。何度でも切り替えられます。
- 取り込み後のObjectを手で動かしたり編集してから切り替えても、その状態は取り込み後のマップに保たれます。
- 元のマップを表示したまま、もう一度Importすることもできます（上の表）。
- 切り替えもESCで取り消せます。


### 追加Meshの取り込み（Import New Meshes）

- **取り込み先**: `New Meshes To`で、取り込み先のCollectionを選べます。空欄なら`Library`の下の`FromHoudini`（無ければ作成）です。`Library`の外のCollection（例 `NewOBJs`）でも構いません。Preview/Import/Helperは`Library`と`New Meshes To`の両方からMeshを探します（0.7.1。0.7.0では外にあると`added 0`になりました）。Mapの中のCollectionは探しません。
- **FBXの変換**: HoudiniのFBX（Y-up・cm）は、取り込むと「X回転90度・スケール0.01」を持つObjectになります。配置にはMeshデータだけを使うため、`Convert Houdini FBX to Blender size`にチェックを入れると、この変換をMeshデータへ焼き込み、Libraryと同じ（Z-up・m・Objectの変換なし）にします。**既定はOFF**で、OFFのときはFBXの内容をそのまま取り込みます（HoudiniのFBXを取り込むときは、チェックを入れてください。入れないと、新しいMeshの向き・大きさ・位置がずれます）。ONのとき、結果欄に`FBX transform baked into N meshes`と出ます。変換済みのFBXでは、ONでも何も変わりません。
- **構造**: `Placement CSV`が指定してあれば、追加Meshを使う行の`colname`の階層を、取り込み先の中に再現します（例 `Area2/NewRocks` → 取り込み先の中の`Area2 [FromHoudini]` > `NewRocks [FromHoudini]`）。無い階層は作り、ある階層は再利用します。`colname`が空欄、またはCSVが無いMeshは、取り込み先の直下に並びます。
- **`colname`が複数ある**: 同じ追加Meshを、`colname`が違う複数の行が使っているときは**警告**を出し、最も多い`colname`を使います（同数ならCSVで先に出る行）。
- ESCや失敗では、作ったCollectionも含めて取り込み前に戻ります。

### Collectionの階層

戻りCSVの`colname`は、次の順で配置先のCollectionに解決されます。

1. `Map`の下に、その名前のCollectionがあれば、そこへ配置します（階層が無い旧CSVも、この方法で従来どおり動きます）。
2. そうでなければ`colname`を`/`区切りの階層パスとして読み、`Map`の下で同じ階層をたどります。途中のCollectionが無ければ、入れ子のまま新しく作ります。例えば`Area1/Trees`は、`Area1`が既にあれば、その下に`Trees`だけを作ります。
3. 空欄は`Map`直下へ配置します。`Map/Area1`のように、先頭が`Map`の名前のパスは、その`Map`を除いて読みます。
4. `//`のように空の区切りを含む`colname`は、パスではなく1つの名前として扱います。

Importは全行を新しく置くので、無い階層だけを作ります。Previewの`new collections N`は、新しく作るCollectionの数です。

- **名前の衝突**: Blenderでは、Collection名は1つのファイル内で重複できません。新しく作る名前が既に使われているときは、Blenderが`.001`などの接尾辞を付けます。Previewと実行時に警告を出します。
- **元の場所には戻りません**: Mapの外にあったCollectionへ新しいObjectを置くときは、`Map`の下に作られます。

### CSVの列

- 必須の12列: `id, tx, ty, tz, rx, ry, rz, sx, sy, sz, objname, colname`。`id`は読みますが、使いません（整数でなくても構いません）。
- `use`列（任意）: `1`か空欄か列なしは置く、`0`は何も置きません（警告も出しません）。`0`と`1`以外の値は`bad_use`のエラーで、その行は使いません。
- Houdiniが付けるその他の列（`ptnum`・`Zone`など）は無視します。

### Previewのエラー・警告の見方

Preview Importは、CSVの**行・列・値・理由**を出します。パネルに最初の5件（エラーを先に）が出て、全件はTextエディターの`MRT Placement Report`に書かれます。**エラー**はその行を使わなかったもの、**警告**は使ったか、見落としやすいことの知らせです。パネルには、`Archive N`（退避する元のObject）、`Delete N`（削除する前回のImport）、`Place N`（置く行）が出ます。

| 内容 | 例 |
|---|---|
| 数値が読めない | `Line 3: column tx = 'abc' is not a number.` |
| 有限でない値 | `Line 4: column sz = 'nan' is not a finite number.` |
| 列が足りない | `Line 6: the row has 4 columns, but the header has 12; at least 12 are needed.` |
| `objname`が空 | `Line 9: objname is empty.` |
| Libraryに無い名前 | 近い名前（`Similar Library names: ...`）、同名だがMeshでないObject、新しいMeshかもしれないこと（`run Import New Meshes first`）のどれかを添えます。この行は置けず、Importは止まります。 |
| `colname`の問題 | 空の区切りを含む（警告）、名前が衝突する（警告）。名前が衝突して`.001`が付いたCollectionは、頼んだ名前を覚えており、次のPreviewでも同じ名前として見つけます。 |
| Libraryで名前が重複 | 正規化した名前が複数のObjectに一致し、最初を使ったこと（警告。名前ごとに1件で、該当するObjectをすべて並べます）。 |
| `use`の値 | `0`と`1`以外（エラー`bad_use`）。 |
| CSVの行が少ない | `The CSV places N objects, but ZONE_A has M. ...`（警告`fewer_rows`）。 |

ファイル全体の問題は、エラーで止まります: Zoneが未選択（All Zones）／CSVが空／列が足りない／ファイルが無い／`Library`・`Map`が未設定／編集できないObjectやCollection。


## 9. ヒント・注意

ボタンや入力欄にマウスを置くとヒントが出ます。出ない場合はPreferences > InterfaceのTooltips設定を確認してください。選択操作はObject Modeで実行します。

性能測定は[検証報告](VALIDATION.md)を参照してください。0.1.0の6万件Replaceは約282.5秒で、生成の非線形性と分割不能な同期が残っています。担当アドオンを移しても、この配置生成の制約が解消したわけではありません。

## 10. ヘルパー（使われ方の確認）

`N > Map Roundtrip` の一番下の**Helper**パネル（初期は閉じています）で、Library（FromHoudiniを含む）のObjectが、Mapの中でどう使われているかを調べます。使われているかどうかは、**Meshデータの共有**で判定します。

1. **Scan Usage**: LibraryとMapを一度走査します。大量のObjectでも進捗が出て、ESCで中断できます。シーンを変えたら、もう一度実行してください。
2. 結果の1行（`Scanned: N library objects, M map instances, K unused`）が出ます。
3. Libraryのうち、選択中のObject（なければアクティブ。最大5つ）の使用数と、使われているCollection（多い順に最大3つ）が出ます。Map内のObjectを選ぶと、元のLibrary Objectが出ます。
4. ボタン:
   - **Select Usage in Map**: 選択中のLibrary Objectを使っているMap内のObjectを選択します。
   - **Select Library Object**: 選択中のMap内のObjectの、元のLibrary Objectを選択します。
   - **Select Unused Library Objects**: Mapで1つも使われていないLibrary Objectを選択します。
   - **Write Usage Report**: Textエディターの`MRT Usage Report`に、Library Objectごとの使用数・Collection・ゾーンを書きます。

Scan Usageを実行する前の選択操作は、`Run Scan Usage first.`と表示されます。

## 過去バージョン

古い動作が必要なときだけ使用してください。**0.9.2は、Replace Zoneが差分更新（`ub_csv_id`で照合し、CSVにない`id`はそのまま残す）だった最後の版です。** 0.6.0は、Replace Zoneが全作り直しで`Delete`を選べた最後の版です。0.2.0は、CSV出力が「選択したMesh」だった版です。

- [Map Roundtrip Tools 0.9.2（ZIP）](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/map_roundtrip_tools-0.9.2.zip)
- [Map Roundtrip Tools 0.6.0（ZIP）](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/map_roundtrip_tools-0.6.0.zip)
- [Map Roundtrip Tools 0.2.0（ZIP）](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/map_roundtrip_tools-0.2.0.zip)
