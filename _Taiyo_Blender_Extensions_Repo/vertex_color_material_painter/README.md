# Vertex Color Material Painter

Blender 4.5.9 LTS 用の面単位 Color Attribute ペイント補助アドオンです。

Edit Mode で選択している面に、`.blend` ごとに保存した用途別カラーをワンクリックで塗れます。Houdini など外部DCCへ渡すための、木・ガラス・金属などの識別色付けを想定しています。

## 場所

`3D Viewport > Sidebar(N) > VC Painter > Material Vertex Color Painter`

## 基本仕様

- Color Attribute 名は UI で変更できます。
- 初期名は `mat_color` です。
- Color Attribute が存在しない場合は自動作成します。
- 作成する Color Attribute は `FLOAT_COLOR` / `CORNER` です。
- カラーリストは `.blend` ファイル内の Scene プロパティとして保存されます。
- v1 はアクティブな Mesh オブジェクトのみ対象です。

## 使い方

1. Mesh オブジェクトを選択します。
2. Edit Mode に入ります。
3. 塗りたい面を選択します。
4. `VC Painter` パネルで Color Attribute 名を確認します。
5. `Add New Color` で用途名と色を追加します。
6. リスト行のブラシボタン、または `Apply To Selected Faces` を押します。

## 注意

- Object Mode では選択面へ塗れません。
- Vertex / Edge Select でも、Blender 側で `face.select` が立っている面だけを塗ります。
- 同名の Color Attribute が `FLOAT_COLOR` / `CORNER` 以外で存在する場合は、上書きせずエラーにします。
