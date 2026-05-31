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
- Edit Mode ではアクティブな Mesh の選択面だけを塗ります。
- Edit Mode では、カラー行ごとの選択ボタンで同じ色の面を再選択できます。
- Object Mode では選択中の Mesh オブジェクトそれぞれの全フェイスを塗ります。
- Copy Helperで、Paint Attribute全体を別のColor Attributeへコピーできます。
- Copy Helperは `BYTE_COLOR` と `FLOAT_COLOR` の相互コピーに対応します。

## Edit Mode で面だけ塗る

1. Mesh オブジェクトを選択します。
2. Edit Mode に入ります。
3. 塗りたい面を選択します。
4. `VC Painter` パネルで Paint Attribute 名と New Type を確認します。
5. `Add New Color` で用途名と色を追加します。
6. リスト行のブラシボタン、または `Apply Color` を押します。

## Edit Mode で塗った色の面を選択する

1. Mesh オブジェクトを Edit Mode にします。
2. `VC Painter` パネルで Paint Attribute 名を確認します。
3. カラーリスト行の選択ボタン、または `Select Painted Faces` を押します。
4. そのカラーと一致する面だけが選択されます。

## Object Mode で複数オブジェクト全体を塗る

1. Object Mode で Mesh オブジェクトを複数選択します。
2. `VC Painter` パネルで Paint Attribute 名と New Type を確認します。
3. カラーリストから用途カラーを選びます。
4. リスト行のブラシボタン、または `Apply Color` を押します。

## 他のColor Attributeへコピーする

1. コピー元にしたい Paint Attribute 名を確認します。
2. `Copy Helper` の Destination にコピー先Attribute名を入力します。
3. コピー先を新規作成する場合の New Type を選びます。
4. `Copy Attribute` を押します。

Edit ModeではアクティブMeshのAttribute全体をコピーします。Object Modeでは選択中Meshオブジェクトすべてに対して、Attribute全体をコピーします。

## 注意

- Object Mode では面選択状態は使わず、選択中 Mesh オブジェクトの全フェイスに塗ります。
- Vertex / Edge Select でも、Blender 側で `face.select` が立っている面だけを塗ります。
- 色で選択するときは、指定色と面の全ループカラーが一致する面だけを選択します。
- Copy Helperは面選択範囲ではなく、Attribute全体をコピーします。
- 同名の Color Attribute が `BYTE_COLOR` / `CORNER` または `FLOAT_COLOR` / `CORNER` 以外で存在する場合は、上書きせずエラーにします。
