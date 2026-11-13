# Map Roundtrip 詳細使用書

**対象version: Map Roundtrip Tools 0.7.2 / Blender 4.5.0以上**

## 1. 担当する機能

ゾーン管理・Empty編集・範囲選択・ゾーンCSV・FBX入出力・配置復元は、すべて `N > Map Roundtrip` で行います。**Unreal Bridge Toolsを有効にする必要はありません。**

Unreal Bridge Tools 2.3.3は2.2.20相当の元の機能へ戻しました。従来のCollection/Scene CSV、Collision Tag、Filters、Presets用です。Selectedスコープ・Zone UI・ゾーンタグ付けはUBTから取り除きました。

作業前に.blendを保存してください。大量配置のReplaceはUndo履歴を作りません。

## 2. Zoneを登録して範囲を作る

操作は `N > Map Roundtrip > Zones`（最上部）で行います。上から次の順に並んでいます。

```text
Zones
  [ZONE_A ▾] [＋]                      操作するゾーン。＋はNew Zone
  [Map Collection | All Scene Meshes]  対象Meshの範囲（Map Collectionのときだけ Map 欄）
  ▾ 1. Define Range   Add Selected Objects / Merge Distance / Add Empty / Register Selected Empties
  ▸ Zone Empties      Emptyの一覧・検索・選択（折りたたみ）
  ▸ 2. Check          Select Meshes In Zone（折りたたみ）
  ▾ 3. Export CSV     CSV Output Folder / Name Normalize / Export ZONE_A.csv
  ▸ Advanced          Zone Prefix（折りたたみ）
```

1. `Zones`の`＋`（New Zone）を押し、`Zone Name`に `ZONE_A` などを入力します。
2. 一番上の`Zone`で操作するゾーンを選びます。新規登録直後はEmptyがない空のゾーンです。
3. 範囲を作ります。方法は2通りです。
   - **A. 選択したObjectからまとめて作る（おすすめ）**: ゾーンに入れたいMeshを3Dビューで選択し、`1. Define Range > Add Selected Objects`を押します。
   - **B. 手で作る**: `Add Empty`で新しい箱を作るか、既存Emptyを選び `Register Selected Empties` で登録します。

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
- **×**：登録のみ解除します。Object本体は削除しません。
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
- ゾーンの範囲にMeshが1つも入らないときはエラーになり、空のファイルは作りません。
- 読み取り専用Objectがある場合のエラーや、ESC中断では、既存CSVと元のタグを保持します。
- 進捗と残り時間が表示されます。ESCで中断できます。
- 範囲を変えても過去のub_zoneタグは自動で消しません。既に出力したゾーンを縮小した場合は、Replaceの旧対象件数を確認してください。

0.2.0までの「先にSelect Meshes In Zoneで選んでからExport Selected CSV」は不要になりました。

書き出した各行の`id`（各CSV内の1から始まる通し番号）は、そのMeshのカスタムプロパティ`ub_csv_id`にも保存されます。`ub_zone`と同じく正常終了時だけで、失敗・ESC中断では元の値に戻ります。CSVの列（12列）は変わりません。Houdiniから戻すときの判定に使います（8章）。

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

## 8. Houdiniから戻す

`N > Map Roundtrip > Import` パネルで行います。作業前に`.blend`を保存してください。

1. **Collections**で`Library`（元のMeshの置き場。子Collectionも探します）と`Map`（配置先）を指定します。例ForExport_Dirty_1／Laid_MAP_1。名前は自由です。
2. **戻りのCSVを先に指定します**（`Placement CSV`）。追加Meshの置き場所を、このCSVの`colname`から決めるためです。
3. **Replace Zone**の`Zone`を元のタグ（例ZONE_A）に合わせます。CSV出力成功時にはこの欄にもZone名が設定されます。空欄なら戻りCSV名を使います。
4. `Dry Run`ONのまま**Preview Placement**を押し、計画とエラー・警告を確認します（後述）。
5. 新しいMeshがある場合だけ、`Mesh FBX`を指定して**Import New Meshes**を実行します。
6. もう一度Previewで確認し、`Dry Run`をOFFにして**Replace Zone**を実行します。
7. 結果が違ったら、**Restore Original Map**で最初のマップへ戻せます。ボタンは、`N`キーのサイドバー > `Map Roundtrip` > **Import** > `Replace Zone`欄の、`Replace Zone`ボタンのすぐ下にあります。**Replace Zoneを1回実行すると表示されます**（Dry Runのままでは出ません）。Ctrl+Zでも、Replace Zone 1回分を取り消せます。

CSV名を`ZONE_A_return.csv`に変えて返す場合も、`Zone`はZONE_Aのままにしてください。`id`で対応づけるObjectは、その`Zone`の`ub_zone`を持つものです。

### Replace Zoneの動き（差分更新）

Replace Zoneは、戻りCSVの各行を、書き出し時に保存した`ub_csv_id`で元のObjectと対応づけて、**変わったものだけ**を更新します。

| 状態 | Replace Zoneの結果 |
|---|---|
| 変わっていない（位置・回転・拡大・Mesh・Collectionが同じ） | 何もしません。モディファイア・Custom Properties・親子関係はそのまま残ります。 |
| Houdiniで**動かした**（位置・回転・拡大）／Meshを差し替えた／別のCollectionへ移した | **同じObjectをその場で更新します**（Custom Propertiesなどは残ります）。更新前の状態は保存されます。 |
| Houdiniで**削除した**（その`id`の行がCSVにない） | 退避用のCollection`_Replaced_ZONE_A`へ、**元と同じ階層のまま**移します。 |
| 新しく追加した（`id`が-1）／`id`が重複した行（Houdiniで複製した） | 新しいObjectを作ります。 |
| `id`が書き出し時に無かった行 | 使いません（件数を警告します）。 |
| `objname`がLibraryに無い行で、既存のObjectを指す | そのObjectは**変えずに残し**、エラーとして報告します（削除扱いにはしません）。 |

- **削除はしません**。`Delete`の選択肢はなくなり、使わなくなったObjectはいつも退避されます。
- **ub_csv_idが必要です**。ゾーンのObjectに`ub_csv_id`が1つも無いときは、`Run Export Zone CSV with this version first.`というエラーになります。先に**Export Zone CSV**をやり直してください。ゾーンに1つもObjectが無いときは、すべての行を新しいObjectとして作ります。
- **退避用のCollection**: `_Replaced_ZONE_A`は`Scene Collection`の直下に作られ、View Layerから除外されます。中は、元のCollectionと同じ階層を`名前 [ZONE_A]`というCollectionで再現します（Blenderは同じ名前のCollectionを持てないためです）。`ub_zone`タグは外れ、`ub_archived_from=ZONE_A`が付きます。
- **進捗とキャンセル**: 進捗と残り時間が出ます。ESCで中断すると、すべて元に戻ります。

### 最初のマップへ戻す・もう一度適用する

Blenderの中には、Houdiniに出す前の**元のマップ**と、Replace Zone後の**取り込み後のマップ**の2つの状態が残ります。`Replace Zone`を実行すると、Importパネルに次が出ます。

- **Restore Original Map**: 最初のReplace Zoneの前の状態へ戻します。動かしたObjectは元の位置・Mesh・Collectionへ、退避したObjectは元のCollectionへ戻り、新しく作ったObjectは`_Replaced_ZONE_A`へ移ります。
- **Re-apply Imported Map**: 取り込み後のマップへ戻します。何度でも切り替えられます。

- 元のマップを表示している間は、Replace Zoneはできません（先にRe-applyしてください）。
- 取り込み後のObjectを手で動かしたり編集してから切り替えても、その状態は取り込み後のマップに保たれます。
- 2回目以降のReplace Zoneでも、戻る先は**最初のReplace Zoneの前**です。
- 範囲外などでCollectionが無くなっているときは、`Map`に入れて件数を報告します。
- 切り替えもESCで取り消せます。

### 追加Meshの取り込み（Import New Meshes）

- **取り込み先**: `New Meshes To`で、取り込み先のCollectionを選べます。空欄なら`Library`の下の`FromHoudini`（無ければ作成）です。`Library`の外のCollection（例 `NewOBJs`）でも構いません。Preview/Replace/Helperは`Library`と`New Meshes To`の両方からMeshを探します（0.7.1。0.7.0では外にあると`added 0`になりました）。Mapの中のCollectionは探しません。
- **FBXの変換**: HoudiniのFBX（Y-up・cm）は、取り込むと「X回転90度・スケール0.01」を持つObjectになります。配置にはMeshデータだけを使うため、この変換をMeshデータへ焼き込み、Libraryと同じ（Z-up・m・Objectの変換なし）にします（0.7.2。0.7.1までは新しいMeshの向き・大きさ・位置がずれました）。結果欄に`FBX transform baked into N meshes`と出ます。
- **構造**: `Placement CSV`が指定してあれば、追加Meshを使う行の`colname`の階層を、取り込み先の中に再現します（例 `Area2/NewRocks` → 取り込み先の中の`Area2 [FromHoudini]` > `NewRocks [FromHoudini]`）。無い階層は作り、ある階層は再利用します。`colname`が空欄、またはCSVが無いMeshは、取り込み先の直下に並びます。
- **`colname`が複数ある**: 同じ追加Meshを、`colname`が違う複数の行が使っているときは**警告**を出し、最も多い`colname`を使います（同数ならCSVで先に出る行）。
- ESCや失敗では、作ったCollectionも含めて取り込み前に戻ります。

### Collectionの階層

戻りCSVの`colname`は、次の順で配置先のCollectionに解決されます。

1. `Map`の下に、その名前のCollectionがあれば、そこへ配置します（階層が無い旧CSVも、この方法で従来どおり動きます）。
2. そうでなければ`colname`を`/`区切りの階層パスとして読み、`Map`の下で同じ階層をたどります。途中のCollectionが無ければ、入れ子のまま新しく作ります。例えば`Area1/Trees`は、`Area1`が既にあれば、その下に`Trees`だけを作ります。
3. 空欄は`Map`直下へ配置します。`Map/Area1`のように、先頭が`Map`の名前のパスは、その`Map`を除いて読みます。
4. `//`のように空の区切りを含む`colname`は、パスではなく1つの名前として扱います。

新しいCollectionを作るのは、新しいObjectを置くときと、Objectを別のCollectionへ移すときだけです。位置が変わっていないObjectを、Collectionの解決のためだけに移すことはありません（Mapの外のCollectionにいるObjectも動きません）。Previewの`new collections N`は、新しく作るCollectionの数です。

- **名前の衝突**: Blenderでは、Collection名は1つのファイル内で重複できません。新しく作る名前が既に使われているときは、Blenderが`.001`などの接尾辞を付けます。Previewと実行時に警告を出します。
- **元の場所には戻りません**: Mapの外にあったCollectionへ新しいObjectを置くときは、`Map`の下に作られます。

### idの扱い

- `id`が**-1**の行は、Houdiniで新しく追加したMeshです。`objname`がLibraryのMeshと一致する場合だけ配置し、一致しなければ「Libraryに無い名前」として報告します（先にImport New Meshesを実行します）。
- `id`が、書き出し時のどのObjectの`ub_csv_id`にも一致しない行（-1以外）は**使用しません**。`unknown id N`として件数が出ます。
- 同じ`id`の行が2つ以上あるときは、最初の行を元のObjectに対応づけ、残りは新しいObjectとして作り、警告します。
- `id`が整数でない行（空欄・文字・1.5など）は`invalid rows`に数えて使いません。`1.0`や`-1.0`は整数として読みます。
- `id`の照合は、そのゾーンの`ub_zone`を持つObjectの`ub_csv_id`だけで行います。他のゾーンのidは数えません。
- Replace Zoneで作った新しいObjectには`ub_csv_id`は付きません。同じゾーンをもう一度Houdiniへ送るときは、先にExport Zone CSVをやり直してください。

### Previewのエラー・警告の見方

Preview Placementは、CSVの**行・列・値・理由**を出します。パネルに最初の5件（エラーを先に）が出て、全件はTextエディターの`MRT Placement Report`に書かれます。**エラー**はその行を使わなかったもの、**警告**は使ったか、見落としやすいことの知らせです。

| 内容 | 例 |
|---|---|
| 数値が読めない | `Line 3: column tx = 'abc' is not a number.` |
| 有限でない値 | `Line 4: column sz = 'nan' is not a finite number.` |
| `id`が整数でない | `Line 5: column id = 'x' is not an integer.` |
| 列が足りない | `Line 6: the row has 4 columns, but the header has 12; at least 12 are needed.` |
| `objname`が空 | `Line 9: objname is empty.` |
| Libraryに無い名前 | 近い名前（`Similar Library names: ...`）、同名だがMeshでないObject（`it is a EMPTY, not a mesh`）、新しいMesh（`run Import New Meshes first`）、既存Objectを残したこと、のどれかを添えます。 |
| 不明な`id`／重複した`id` | 警告。どの行の`id`で、どの行と重なるかを出します。 |
| `colname`の問題 | 空の区切りを含む（警告）、名前が衝突する（警告）。 |
| Libraryで名前が重複 | 正規化した名前が複数のObjectに一致し、最初を使ったこと（警告）。 |

ファイル全体の問題は、エラーで止まります: CSVが空／列が足りない（見つかった列も表示）／ファイルが無い（パスも表示）／`Library`・`Map`が未設定／編集できないObjectやCollection／`ub_csv_id`が無い／元のマップを表示中。

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

古い動作が必要なときだけ使用してください。0.6.0は、Replace Zoneが全作り直しで`Delete`を選べた最後の版です。0.2.0は、CSV出力が「選択したMesh」だった版です。

- [Map Roundtrip Tools 0.6.0（ZIP）](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/map_roundtrip_tools-0.6.0.zip)
- [Map Roundtrip Tools 0.2.0（ZIP）](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/map_roundtrip_tools-0.2.0.zip)
