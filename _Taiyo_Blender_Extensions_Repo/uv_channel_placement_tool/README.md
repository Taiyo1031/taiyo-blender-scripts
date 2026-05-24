# UV Channel Placement Tool

## 概要
選択UVまたはUVアイランドを、8つの定義済みスロットへ移動するUV編集用アドオンです。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar > UV Tools`
- バージョン: `2.6.2`
- 対応Blender目安: `4.4.0` 以降
- カテゴリ: `UV`

## 使う場面
- IDマスクや素材切り替え用にUVを決まった領域へ置きたい
- 面やアイランドをスロット単位で整理したい
- プリセットを使って同じスロット名を繰り返し使いたい

## 最短手順
1. 対象メッシュを選び、Edit Modeに入ります。
2. `UV Tools` パネルを開きます。
3. `UV Map Index` または `UV Map Name` を確認します。
4. 選択UVを `Slot 0` から `Slot 7` のボタンで移動します。
5. ランダム配置したい場合は `Place All Islands Randomly` を使います。

## 主な設定
- `Preset`: スロット名セットを切り替える
- `UV Map Index`: 0始まりのUVマップ番号
- `UV Map Name`: 対象UVマップ名
- `Slot 0-7`: 選択UVを指定スロットへ移動
- `Place All Islands Randomly`: アイランド単位でランダム配置

## 結果
対象UVマップ上のUV座標を変更します。

## 注意点
- Edit Modeで使用します。Object Modeなどでは実行せず、警告を表示してキャンセルします。
- `UV Map Index` は0始まりです。
- プリセットはスロット名の保存であり、UV配置そのものの保存ではありません。

## 詳細な使用書
- 詳細使用書: `インスタンスヘルパー_UVチャンネル配置ツール_完全使用書_v2_6.md`

## GitHub仕様書
- [インスタンスヘルパー_UVチャンネル配置ツール_完全使用書_v2_6.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/uv_channel_placement_tool/%E3%82%A4%E3%83%B3%E3%82%B9%E3%82%BF%E3%83%B3%E3%82%B9%E3%83%98%E3%83%AB%E3%83%8F%E3%82%9A%E3%83%BC_UV%E3%83%81%E3%83%A3%E3%83%B3%E3%83%8D%E3%83%AB%E9%85%8D%E7%BD%AE%E3%83%84%E3%83%BC%E3%83%AB_%E5%AE%8C%E5%85%A8%E4%BD%BF%E7%94%A8%E6%9B%B8_v2_6.md)
