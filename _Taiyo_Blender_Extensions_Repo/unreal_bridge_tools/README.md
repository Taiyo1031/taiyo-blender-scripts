# Unreal Bridge Tools

## 概要
Blender上のオブジェクトTransform情報とCollection情報をCSVへ書き出し、Unreal EngineのPCGパイプラインで使いやすくするためのアドオンです。

オブジェクト名への `-coll` タグ付け、Collection / Scene単位の対象選択、名前フィルタ、名前正規化をまとめて扱えます。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Unreal Bridge Tools`
- バージョン: `2.2.19`
- 対応Blender目安: `4.2.0` 以降
- カテゴリ: `Import-Export`

## 使う場面
- Unreal Engine PCG用にBlender配置情報をCSV化したい
- `-coll` 付きのCollision用オブジェクトを整理したい
- Collection単位、再帰Collection、全Sceneから書き出し対象を選びたい
- `.001` などのBlender自動連番を用途に応じて除去したい

## 最短手順
1. 3D View右側の `N` パネルを開きます。
2. `Unreal Bridge Tools` タブを開きます。
3. `Scope` と `Target Collection` を設定します。
4. `Export CSV` に書き出し先を指定します。
5. 必要に応じて `Filters`、`Visible Only`、`Name Normalization`、`Export Mode` を調整します。
6. `Export CSV` を押します。

## 主な機能
- `Scope`: Direct Only / Recursive / All Collections の切り替え
- `Presets`: Scope、Collection、Export CSV、Export Mode、Filters、Name Normalizationをユーザー設定に保存・復元
- `Filters`: Include / Exclude テキスト条件で対象名を絞り込み
- `Collision Tag`: 選択オブジェクトへ `-coll` を追加・削除・選択
- `Name Normalize`: 生名維持、数値サフィックス除去、ドット以降削除
- `Test Write`: CSV保存先への書き込み可否を確認
- `Export Mode`: 60,000個以上向けの `Fast Locked` と、従来寄りに操作を通す `Responsive` を切り替え
- `Export CSV`: 大量オブジェクト時は `Fast Locked` を標準として、Blender操作をほぼ止めながら大きなchunkで書き出し。Nパネルのゲージ、進捗率、残り時間、処理速度を表示

## 出力CSV
出力列は以下です。

```text
id, tx, ty, tz, rx, ry, rz, sx, sy, sz, objname, colname
```

回転はXYZ Eulerをdegreeへ変換して出力します。

## 注意点
- `Visible Only` がONの場合、Viewportで見えているオブジェクトだけを書き出します。全オブジェクトを書き出す大量処理ではOFF推奨です。
- `Scope` が `All Collections` 以外の場合は `Target Collection` の指定が必要です。
- 保存先フォルダを作れない場合は、一時フォルダへフォールバックします。
- プリセットはBlenderのユーザー設定領域に保存され、Extension更新後も維持されます。
- 書き出し中の進捗率と残り時間はNパネルのゲージとBlender下部のステータスバーに表示され、`Esc` で中断できます。
- 高速化のために全オブジェクトを自動で非表示にはしません。非表示化はCSV対象を変える危険があり、60,000個規模では非表示変更そのものも重くなります。
- Blender Pythonのデータアクセスは基本的にメインスレッド中心です。マルチスレッド化ではなく、UI割り込みとファイル書き込み回数を減らして高速化しています。
- 大量の書き出し前に `.blend` を保存しておくと安心です。

## GitHub仕様書
- [Unreal_Bridge_Tools_使用書.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/Unreal_Bridge_Tools_%E4%BD%BF%E7%94%A8%E6%9B%B8.md)
