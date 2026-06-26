# Vertex Color Material Painter

Blender 4.5.9 LTS 用の面単位 Color Attribute ペイント補助アドオンです。

Edit Mode で選択している面、または Object Mode で選択している複数 Mesh オブジェクト全体に、`.blend` ごとに保存した用途別カラーをワンクリックで塗れます。Houdini など外部DCCへ渡すための、木・ガラス・金属などの識別色付けを想定しています。

## 場所

`3D Viewport > Sidebar(N) > VC Painter > Material Vertex Color Painter`

## 基本仕様

- Paint Attribute 名と新規作成時の型は UI で変更できます。
- 初期名は `mat_color` です。
- 新規作成時の既定型は `BYTE_COLOR` です。
- Color Attribute が存在しない場合は自動作成します。
- 作成できる Color Attribute は `BYTE_COLOR` / `CORNER` または `FLOAT_COLOR` / `CORNER` です。
- 既存Attributeがある場合は、UIの型指定ではなく既存Attributeの型を使います。
- カラーリストは `.blend` ファイル内の Scene プロパティとして保存されます。
- `Import JSON`で外部JSONや同梱テンプレートからColor Listを読み込み、現在のリストを置き換えられます。
- `Export JSON`で現在のColor Listを、再ImportできるJSONテンプレート形式で書き出せます。
- Edit Mode ではアクティブな Mesh の選択面だけを塗ります。
- Edit Mode / Object Mode では、カラー行ごとの選択ボタンで同じ色の面を再選択できます。
- Object Modeの `Select Painted Faces` は選択中Meshを対象にし、スキャンをタイマーで分割してUIフリーズを避けます。
- 選択系ボタンは実行前のModeを維持します。Object Modeから実行した場合はObject Mode、Edit Modeから実行した場合はEdit Modeのままです。
- `Select Unknown Color Objects` で、Color Listに存在しない色を持つMesh Objectをまとめて選択できます。
- Object Mode では選択中の Mesh オブジェクトそれぞれの全フェイスを塗ります。
- Attribute HelperのCopyで、Paint Attribute全体を別のColor Attributeへコピーできます。
- Attribute HelperのCopyは `BYTE_COLOR` と `FLOAT_COLOR` の相互コピーに対応します。
- Attribute HelperのRemoveで、選択中の複数Meshから条件に一致するAttributeを一括削除できます。
- Attribute HelperのRemoveは `Use Remove Helper` をONにしたときだけ、選択Mesh数・一致Attribute数・共有Mesh警告をパネル上でライブ表示します。重いシーンではOFFのまま実行できます。
- 削除条件は `Same Name`、`Data Type`、`Domain`、`Type + Domain`、`All Removable` の5種類です。
- 内部Attributeと必須Attributeは削除対象から常に除外されます。
- Edit ModeとObject Modeで同じ線形RGBA値を書き込み、`BYTE_COLOR`でも同じ色になります。
- `Auto Fix Selected Colors`で、Color Listを基準に旧Edit Modeペイントの暗い色だけを自動判定し、選択中Meshを一括補正できます。

## Edit Mode で面だけ塗る

1. Mesh オブジェクトを選択します。
2. Edit Mode に入ります。
3. 塗りたい面を選択します。
4. `VC Painter` パネルで Paint Attribute 名と New Type を確認します。
5. `Add New Color` で用途名と色を追加します。
6. リスト行のブラシボタン、または `Apply Color` を押します。

## 塗った色の面を選択する

1. Mesh オブジェクトを Edit Mode、または Object Mode で選択します。
2. `VC Painter` パネルで Paint Attribute 名を確認します。
3. カラーリスト行の選択ボタン、または `Select Painted Faces` を押します。
4. そのカラーと一致する面だけが選択されます。
5. Object Modeから実行した場合は、選択中Meshを複数ティックに分けてスキャンし、Object Modeのまま選択状態を保持します。

## Color List外の色を持つObjectを選択する

1. Mesh オブジェクトを Object Mode で選択、または Edit Mode にします。
2. `VC Painter` パネルで Paint Attribute 名を確認します。
3. `Color List` に正しい用途カラーを登録します。
4. `Select Unknown Color Objects` を押します。
5. 指定Attribute内にColor Listと一致しないLoop Colorを1つでも持つObjectだけが選択されます。

判定はColor Listの色値で行います。名前やHex文字列は使いません。Color Listが空の場合は、指定Attributeを持つObjectをすべて未知色ありとして選択します。Edit Modeから実行した場合は、未知色を持つObjectだけをEdit Modeで開き直します。

## Object Mode で複数オブジェクト全体を塗る

1. Object Mode で Mesh オブジェクトを複数選択します。
2. `VC Painter` パネルで Paint Attribute 名と New Type を確認します。
3. カラーリストから用途カラーを選びます。
4. リスト行のブラシボタン、または `Apply Color` を押します。

## カラーリストをJSONから読み込む

1. `Color List` の `Import JSON` を押します。
2. 読み込むJSONファイルを選びます。
3. JSONの内容で現在のColor Listが置き換わります。

`Name` は空でない一意の名前、`Color` はアルファ値を含まない線形RGB `0.0` から `1.0` の3要素配列です。読み込んだColor Listのアルファ値はすべて `1.0` になります。空の配列 `[]` は有効で、現在のColor Listを空にします。

単純な配列形式:

```json
[
  {
    "Name": "Wood",
    "Color": [0.45, 0.24, 0.09]
  }
]
```

テンプレート形式:

```json
{
  "schema_version": 1,
  "name": "Material ID Template",
  "colors": [
    {
      "Name": "Wood",
      "Color": [0.45, 0.24, 0.09]
    }
  ]
}
```

同梱テンプレートは `templates/color_list_template.json` にあります。形式エラー、重複名、RGB以外の配列、範囲外の値がある場合は読み込みを中止し、現在のColor Listは変更しません。

## カラーリストをJSONへ書き出す

1. `Color List` の `Export JSON` を押します。
2. 保存先を選びます。初期ファイル名は `vertex_color_material_colors.json` です。
3. カラーリストの順序を維持したまま、各項目の `Name` と `Color` が保存されます。

書き出しJSONは `Import JSON` でそのまま読み戻せるテンプレート形式です。`Color` はアルファ値を含まない線形RGB `0.0` から `1.0` の3要素配列です。日本語名はUTF-8のまま保存されます。空のカラーリストは `colors: []` として出力されます。

```json
{
  "schema_version": 1,
  "name": "Material ID Template",
  "colors": [
    {
      "Name": "White",
      "Color": [1.0, 1.0, 1.0]
    }
  ]
}
```

## 他のColor Attributeへコピーする

1. コピー元にしたい Paint Attribute 名を確認します。
2. `Attribute Helper > Copy` の Destination にコピー先Attribute名を入力します。
3. コピー先を新規作成する場合の New Type を選びます。
4. `Copy Attribute` を押します。

Edit ModeではアクティブMeshのAttribute全体をコピーします。Object Modeでは選択中Meshオブジェクトすべてに対して、Attribute全体をコピーします。

## 選択中の複数MeshからAttributeを削除する

1. Object Modeで対象Meshを複数選択します。複数Object Edit Modeの場合は、Edit Modeに参加しているMeshが対象です。
2. `Attribute Helper > Remove` の `Match Mode` を選びます。
3. `Filter Source` を `Direct` または `Reference Attribute` にします。
4. 削除条件を設定して `Remove Matching Attributes` を押します。
5. 必要な場合は `Use Remove Helper` をONにして、選択Object数、固有Mesh数、削除Attribute数、共有Meshへの影響をパネル上で確認します。
6. `Remove Matching Attributes` の確認画面で内容を確認して削除を確定します。

### Match Mode

- `Same Name`: 入力した名前と完全一致するAttributeを削除します。
- `Data Type`: `FLOAT`、`BYTE_COLOR` など同じデータ型のAttributeを削除します。
- `Domain`: `POINT`、`EDGE`、`FACE`、`CORNER` の同じドメインを削除します。
- `Type + Domain`: データ型とドメインが両方一致するAttributeを削除します。
- `All Removable`: 内部・必須属性を除く、削除可能なAttributeをすべて削除します。

`Direct` は名前、データ型、ドメインをUIで直接指定します。`Reference Attribute` はアクティブMeshで選んだAttributeの名前、データ型、ドメインを条件として使います。

同じMeshデータを共有する選択Objectは固有Mesh単位で1回だけ処理します。未選択Objectも同じMeshを共有している場合は、そのObjectにも削除結果が反映されるため、パネルと確認画面に警告が表示されます。

## 色の状態を自動判定して修復する

1. Object Modeで修復対象のMeshオブジェクトを選択します。
2. `Paint Attribute > Name` に修復するAttribute名を指定します。
3. 修復の基準にする色を `Color List` に登録します。
4. `Attribute Helper > Automatic Color Fix > Auto Fix Selected Colors` を押します。
5. 自動判定結果を確認して実行します。

各ColorをColor Listと比較し、そのままの値が登録色に近い場合は変更しません。旧Edit Mode変換を戻した値だけが登録色に近い場合のみ補正します。両方が近い曖昧な色と、どちらも登録色に近くない未知の色は安全のため変更しません。

この修復ボタンはBlenderのBMesh安定性を考慮してObject Mode専用です。Edit Modeペイントは1.0.3以降でObject Modeと同じ色になるよう修正されています。

## 注意

- Object Mode では面選択状態は使わず、選択中 Mesh オブジェクトの全フェイスに塗ります。
- Vertex / Edge Select でも、Blender 側で `face.select` が立っている面だけを塗ります。
- 色で面を選択するときは、指定色と面の全ループカラーが一致する面だけを選択します。Object Modeでは選択中Meshをタイマーで分割スキャンし、Object Modeのまま結果を保持します。
- Color List外の色でObjectを選択するときは、指定Attribute内のLoop Colorをタイマーで分割スキャンし、未知色を1つでも持つObjectだけを現在のModeのまま選択します。
- Attribute HelperのCopyは面選択範囲ではなく、Attribute全体をコピーします。
- Attribute HelperのRemoveはColor Attribute以外を含むMesh Attributeを条件指定で削除します。
- `is_internal` または `is_required` のAttributeは、`All Removable`を含むすべての削除条件で保護されます。
- 同名の Color Attribute が `BYTE_COLOR` / `CORNER` または `FLOAT_COLOR` / `CORNER` 以外で存在する場合は、上書きせずエラーにします。
