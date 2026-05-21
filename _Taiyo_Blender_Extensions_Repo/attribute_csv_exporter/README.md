# Attribute CSV Exporter

## 概要
選択したメッシュの属性をCSVに書き出すアドオンです。Geometry Nodesやモディファイア適用後の評価済みメッシュにも対応します。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Attr CSV`
- バージョン: `1.8.1`
- 対応Blender目安: `5.1.0` 以降
- カテゴリ: `Import-Export`

## 使う場面
- Geometry Nodesで作った属性値を表計算ソフトで確認したい
- 頂点、辺、面、コーナー単位の属性を外部ツールへ渡したい
- 複数オブジェクトの属性を同じCSVで比較したい

## 最短手順
1. 対象メッシュを選択します。
2. 3D Viewportで `N` キーを押し、`Attr CSV` タブを開きます。
3. `Export Folder`、`Domain`、必要な属性を設定します。
4. `Export CSV` を押します。

## 主な設定
- `Domain`: Vertex / Edge / Face / Corner のどの単位で出すか
- `Vector Mode`: ベクトルを1列にまとめるか、`_x/_y/_z` に分けるか
- `Attribute Source`: 選択オブジェクト全体から属性候補を集めるか、アクティブだけを見るか
- `Use Evaluated Mesh`: Geometry Nodes / modifier 結果を反映するか
- `Export Individually`: オブジェクトごとに別CSVへ出すか

## 結果
CSV。行は属性の要素インデックス、列は `object`、`index`、選択した属性です。

## 注意点
- 属性候補が出ない場合は `Refresh` を押します。
- Geometry Nodesの結果を出したい場合は `Use Evaluated Mesh` をONにします。
- Excelで文字化けする場合はUTF-8として読み込みます。

## 詳細な使用書
- 元フォルダの詳細使用書: `Attribute_CSV_Exporter_Helper_User_Manual_JP_v1_8_2.md`
