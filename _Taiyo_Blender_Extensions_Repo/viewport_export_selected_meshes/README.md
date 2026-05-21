# Viewport Export Selected Meshes

## 概要
選択メッシュを1つずつ現在のビューポート見た目で画像書き出しするアドオンです。一時カメラで自動フィットします。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar > Viewport Export`
- バージョン: `1.5.2`
- 対応Blender目安: `4.0.0` 以降
- カテゴリ: `Render`

## 使う場面
- アセットサムネイルをまとめて作りたい
- 現在のビューポート表示をそのまま画像化したい
- 選択メッシュをオブジェクト名の画像ファイルとして出したい

## 最短手順
1. 書き出したいメッシュを選択します。
2. ビューポート角度、表示モード、解像度を整えます。
3. `Viewport Export` パネルで `Output Folder` を指定します。
4. 必要なら `Solo`、`Fit Margin`、一時カメラ設定を調整します。
5. `Export Selected Meshes` を押します。

## 主な設定
- `Output Folder`: 画像の保存先
- `Solo`: 対象以外を隠して書き出すか
- `Project Format`: シーンの画像形式設定を使う
- `Match Viewport Lens`: ビューポートのレンズ感を反映
- `Fit Margin`: オブジェクト周囲の余白
- `Delete Temp Camera After`: 書き出し後に一時カメラを消すか

## 結果
選択メッシュごとの画像ファイル。ファイル名はオブジェクト名ベースです。

## 注意点
- 旧版 `VirportExport.py` ではなく、修正版 v1.5.2 を配布対象にしています。
- 出力品質と見た目はビューポート表示、レンダー解像度、画像形式に依存します。
- グリッドやアウトラインを写したくない場合はOverlaysをOFFにします。

## 詳細な使用書
- 元フォルダの詳細使用書: `ViewportExport_SelectedMesh_AutoFit_完全使用書.md`
