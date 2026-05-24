# Collection Mesh Merge FBX Exporter

## 概要
Blenderのコレクションを対象に、各コレクション内のメッシュを一時的に統合し、コレクションごとに1つのFBXを書き出すアドオンです。

元のオブジェクト、コレクション構造、モディファイヤー、マテリアルは変更せず、書き出し後に一時オブジェクトを削除します。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > CMFE`
- バージョン: `0.2.0`
- 対応Blender目安: `4.2.0` 以降
- カテゴリ: `Import-Export`

## 使う場面
- Collection単位で管理しているアセットを、CollectionごとにFBX化したい
- Asset Browser登録済みCollectionだけを書き出したい
- 名前条件で対象Collectionを絞り込みたい
- 複数メッシュを1つのStatic Mesh向けFBXとして書き出したい

## 最短手順
1. 3D View右側の `N` パネルを開きます。
2. `CMFE` タブを開きます。
3. `Export Folder` を指定します。
4. `Search Root Collection` を指定します。
5. 必要に応じて `Filter` と `Mesh Processing` を調整します。
6. `Refresh Preview` を押して対象を確認します。
7. `Export FBX` を押します。

## 主な機能
- `Filter Mode`: Asset Browser登録、名前条件、AND/OR条件で対象Collectionを選択
- `Nested Target Rule`: 親子Collectionが両方一致した場合の書き出しルールを選択
- `Apply Modifiers Before Export`: モディファイヤー評価後のメッシュを書き出し
- `Keep Material Slots`: 元メッシュのマテリアルスロットを保持
- `Objects per Tick`: 大量オブジェクト時にUIを固めにくい分割処理

## 注意点
- FBX Export処理の瞬間はBlenderが一時的に止まったように見える場合があります。
- `Include Collection Instances` は実験的機能です。最初はOFF推奨です。
- 初回はテスト用 `.blend` で出力結果を確認してください。

## GitHub仕様書
- [Collection_Mesh_Merge_FBX_Exporter_使用書.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/collection_mesh_merge_fbx_exporter/Collection_Mesh_Merge_FBX_Exporter_%E4%BD%BF%E7%94%A8%E6%9B%B8.md)
