# Overlap Object Selector

## 概要
同じ位置に重なっているオブジェクトを検出し、グループ単位で確認・選択・リスト整理できるアドオンです。

大量配置シーンの重複オブジェクト、同位置コピー、不要なブロッカー確認に使います。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Overlap`
- バージョン: `1.2.2`
- 対応Blender目安: `4.2.0` 以降
- カテゴリ: `Object`

## 使う場面
- 同じ位置にある重複オブジェクトを探したい
- 重なりグループを見ながら必要なものだけ選択したい
- Collection名で検出結果を絞り込みたい
- 結果リストから不要な項目を外したり、対象オブジェクトを個別削除したい

## 最短手順
1. 3D View右側の `N` パネルを開きます。
2. `Overlap` タブを開きます。
3. 必要に応じて `Detect Settings` を設定します。
4. `Detect Overlaps` を押します。
5. `Overlap Groups` から確認したいグループを選びます。
6. `Objects in Selected Group` で個別オブジェクトを確認・選択します。

## 主な設定
- `Include Hidden Objects`: Viewport非表示オブジェクトも検出対象に含める
- `Match Scale`: 位置に加えてスケールも一致するものだけをグループ化
- `Match Rotation`: 位置に加えて回転も一致するものだけをグループ化
- `Show Collection Names`: 選択中オブジェクトの所属Collection名を表示
- `Collection Filter / Bulk Select`: Collection名で検出結果を選択・チェック

## 注意点
- 検出はワールド座標の位置を基準にします。
- `Select Matches` は選択だけを行い、削除はしません。
- `Delete This Blender Object` は実オブジェクトを削除しますが、Undoに対応しています。
- 現在のView Layerに存在しないオブジェクトは選択できないため、自動でスキップされます。

## 詳細な使用書
- `Overlap_Selector_User_Guide_v1_2_1.md`

## GitHub仕様書
- [Overlap_Selector_User_Guide_v1_2_1.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/overlap_selector/Overlap_Selector_User_Guide_v1_2_1.md)
