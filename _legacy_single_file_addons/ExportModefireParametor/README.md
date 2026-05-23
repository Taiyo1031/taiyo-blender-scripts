# GN Parameter CSV Exporter

## 概要
選択オブジェクトのGeometry Nodesモディファイア入力パラメータをCSVに書き出すアドオンです。

## 基本情報
- 本体ファイル: `GNパラメータCSVエクスポーター_v1_1_修正版.py`
- 表示場所: `View3D > Sidebar (N) > GN CSV Export`
- バージョン: `1.1.0`
- 対応Blender目安: `4.0.0` 以降
- カテゴリ: `3D View`

## 使う場面
- オブジェクトごとのGeometry Nodes設定値を一覧化したい
- インスタンス配置やプロシージャル設定を外部で確認したい
- 同じモディファイアを持つ複数オブジェクトの値を比較したい

## 最短手順
1. Geometry Nodesモディファイアを持つオブジェクトを選択します。
2. `GN CSV Export` パネルを開きます。
3. `Use Active GN Modifier` または `Modifier Name` で対象を指定します。
4. `Populate from GN Inputs` で入力項目を追加し、必要に応じて整理します。
5. `Export CSV` を押します。

## 主な設定
- `Modifier Name`: 読み取るGeometry Nodesモディファイア名
- `Parameters`: CSV列として出したい入力名
- `Export All Selected Objects`: 選択中の全オブジェクトを出すか
- `Include Header`: 1行目に列名を付けるか

## 結果
CSV。各行がオブジェクト、各列が指定したGeometry Nodes入力パラメータです。

## 注意点
- `Populate from GN Inputs` で何も出ない場合、アクティブオブジェクトとモディファイア名を確認します。
- 旧版 `ExportModefireParametor.py` ではなく、修正版 v1.1 を配布対象にしています。
- 一部の値が空欄の場合、そのオブジェクトに対象入力が存在しない可能性があります。

## 詳細な使用書
- 詳細版: `GNパラメータCSVエクスポーター_完全使用書.md`
