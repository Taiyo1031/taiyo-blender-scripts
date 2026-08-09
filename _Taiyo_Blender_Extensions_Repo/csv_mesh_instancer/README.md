# CSV Mesh Instancer

Version 3.0.2

CSVのTransformを読み込み、FBXのMesh datablockを共有するObjectを高速配置するBlender Extensionです。

## 対応環境

- Blender 4.5.9以上
- `3D Viewport > Sidebar (N) > CSV Instancer`
- UIは英語

## 機能

UIと内部処理は次の3機能だけです。

1. CSV Import
2. FBX Import
3. Placement

Placementには、FBX用のUnit Scale `0.01`、Local X Rotation `90°`、`.001`サフィックス照合、Blender標準形式のObject名、複数tick処理、進捗、ETA、キャンセルを含みます。

生成ObjectはCSVの`objname`を使い、同名の場合だけ末尾に`.001`、`.002`を付けます。先頭にCSV行番号は付けません。

FBX SourceとCSV Outputには、Collection全体を高速に切り替える`Show` / `Hide`ボタンがあります。Objectを1件ずつ走査しません。

Stable ID、Change Review、属性フィルター、Custom Property転送、削除IDのEmpty化、Restore、属性別Collection、管理Collection一覧、実体化はありません。

## 互換性

Version 3は旧出力を読み込み・移行・更新しません。同名の旧出力Collectionがある場合は、削除するか別の出力名を指定してください。

詳細は[CSV Mesh Instancer 使用書](CSV_Mesh_Instancer_使用書.md)を参照してください。
