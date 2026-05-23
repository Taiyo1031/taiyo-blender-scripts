# UV Channel Placement Tool

## 概要
選択UVまたはUVアイランドを、8つの定義済みスロットへ移動するUV編集用アドオンです。

## 基本情報
- 本体ファイル: `UVMatSlots_Ver2.6.py`
- 表示場所: `View3D > Sidebar > UV Tools`
- バージョン: `2.6.0`
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
- 基本はEdit Modeで使用します。
- `UV Map Index` は0始まりです。
- プリセットはスロット名の保存であり、UV配置そのものの保存ではありません。

## 詳細な使用書
- 詳細版: `インスタンスヘルパー_UVチャンネル配置ツール_完全使用書_v2_6.md`
