# Vertex Color Material Painter

Blender 4.5.9 LTS 用の面単位 Color Attribute ペイント補助アドオンです。

Edit Mode で選択している面、または Object Mode で選択している複数 Mesh オブジェクト全体に、`.blend` ごとに保存した用途別カラーをワンクリックで塗れます。Houdini など外部DCCへ渡すための、木・ガラス・金属などの識別色付けを想定しています。

## 場所

`3D Viewport > Sidebar(N) > VC Painter > Material Vertex Color Painter`

## 基本仕様

- Color Attribute 名は UI で変更できます。
- 初期名は `mat_color` です。
- Color Attribute が存在しない場合は自動作成します。
- 作成する Color Attribute は `FLOAT_COLOR` / `CORNER` です。
- カラーリストは `.blend` ファイル内の Scene プロパティとして保存されます。
- Edit Mode ではアクティブな Mesh の選択面だけを塗ります。
- Edit Mode では、カラー行ごとの選択ボタンで同じ色の面を再選択できます。
- Object Mode では選択中の Mesh オブジェクトそれぞれの全フェイスを塗ります。

## Edit Mode で面だけ塗る

1. Mesh オブジェクトを選択します。
2. Edit Mode に入ります。
3. 塗りたい面を選択します。
4. `VC Painter` パネルで Color Attribute 名を確認します。
5. `Add New Color` で用途名と色を追加します。
6. リスト行のブラシボタン、または `Apply Color` を押します。

## Edit Mode で塗った色の面を選択する

1. Mesh オブジェクトを Edit Mode にします。
2. `VC Painter` パネルで Color Attribute 名を確認します。
3. カラーリスト行の選択ボタン、または `Select Painted Faces` を押します。
4. そのカラーと一致する面だけが選択されます。

## Object Mode で複数オブジェクト全体を塗る

1. Object Mode で Mesh オブジェクトを複数選択します。
2. `VC Painter` パネルで Color Attribute 名を確認します。
3. カラーリストから用途カラーを選びます。
4. リスト行のブラシボタン、または `Apply Color` を押します。

## 注意

- Object Mode では面選択状態は使わず、選択中 Mesh オブジェクトの全フェイスに塗ります。
- Vertex / Edge Select でも、Blender 側で `face.select` が立っている面だけを塗ります。
- 色で選択するときは、指定色と面の全ループカラーが一致する面だけを選択します。
- 同名の Color Attribute が `FLOAT_COLOR` / `CORNER` 以外で存在する場合は、上書きせずエラーにします。
