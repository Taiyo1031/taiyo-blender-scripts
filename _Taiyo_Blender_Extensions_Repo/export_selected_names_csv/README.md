# Export Selected Object Names to CSV

## 概要
選択中のオブジェクト名をCSVへ書き出すシンプルなアドオンです。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar > Selected CSV Export`
- バージョン: `1.0.1`
- 対応Blender目安: `3.0.0` 以降
- カテゴリ: `Object`

## 使う場面
- 選択したアセット名を一覧化したい
- チーム共有用にオブジェクト名リストを作りたい
- インスタンス候補や作業対象を記録したい

## 最短手順
1. 書き出したいオブジェクトを選択します。
2. `Selected CSV Export` パネルを開きます。
3. `Save Path` を指定します。
4. 必要なら `Include Header` と `Sort by Name` を設定します。
5. `Export Selected Names to CSV` を押します。

## 主な設定
- `Save Path`: CSVの保存先
- `Include Header`: `name` ヘッダーを付けるか
- `Sort by Name`: 名前順に並べるか

## 結果
CSV。選択オブジェクト名の一覧です。

## 注意点
- 書き出されるのはオブジェクト名のみです。
- 同じ保存先を指定すると上書きされます。
- `//` から始まる相対パスは `.blend` の保存場所基準です。

## 詳細な使用書
- 元フォルダの詳細使用書: `インスタンスヘルパー_選択オブジェクト名CSV書き出し_完全使用書.md`

## GitHub仕様書
- [インスタンスヘルパー_選択オブジェクト名CSV書き出し_完全使用書.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/export_selected_names_csv/%E3%82%A4%E3%83%B3%E3%82%B9%E3%82%BF%E3%83%B3%E3%82%B9%E3%83%98%E3%83%AB%E3%83%8F%E3%82%9A%E3%83%BC_%E9%81%B8%E6%8A%9E%E3%82%AA%E3%83%95%E3%82%99%E3%82%B7%E3%82%99%E3%82%A7%E3%82%AF%E3%83%88%E5%90%8DCSV%E6%9B%B8%E3%81%8D%E5%87%BA%E3%81%97_%E5%AE%8C%E5%85%A8%E4%BD%BF%E7%94%A8%E6%9B%B8.md)
