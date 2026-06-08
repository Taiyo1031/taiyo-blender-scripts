# Map Link Tools

## 概要

`Map Link Tools` は、マップ・環境制作で大量に配置したリンク複製、共有Mesh、Collection Instanceを整理するためのBlender Extensionです。

オブジェクト名とMesh Data名の整理、`.001` suffixの変換、共有Meshの確認、同じMesh Dataを使うオブジェクトの選択、Collection Instanceのリネームなどを、3D ViewportのNパネルからまとめて実行できます。

## 基本情報

- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Map Link Tools`
- バージョン: `0.1.0`
- 対応Blender目安: `4.5.0` 以降
- カテゴリ: `Object`

## 主な機能

- 選択中オブジェクトの概要表示
- Object名 / Mesh Data名 / 両方を対象にした名前整理
- `.001`, `.002` などのBlender numeric suffix削除
- `.001` を `_01` 形式へ変換
- Pattern Rename、Find and Replace、Prefix/Suffix追加・削除
- Active Object名を基準にしたリネーム
- Object名からMesh Data名への同期
- Mesh Data名からObject名への同期
- 共有Mesh Dataの警告と既定スキップ
- Collection Instanceを参照元Collection名からリネーム
- 同じMesh Dataを使うオブジェクトを選択
- 同じCollectionを参照するCollection Instanceを選択
- Mesh user数の確認
- 選択MeshのSingle User化
- 変更前のSafety Preview
- 大量処理向けのmodal/timer分割処理
- 進捗、残数、キャンセル表示

## 最短手順

1. Blenderで `Edit > Preferences > Add-ons` を開きます。
2. `Install from Disk` から、このExtensionのzipまたはフォルダをインストールします。
3. `Map Link Tools` を有効化します。
4. 3D Viewportを開きます。
5. `N` キーでSidebarを開きます。
6. `Map Link Tools` タブを開きます。
7. `Selection Overview` の `Refresh Selection Info` で選択状態を確認します。
8. `Preview` ボタンで変更内容を確認してから `Apply` します。

## 代表的な使い方

### `.001` を `_01` に変換する

1. 対象オブジェクトを選択します。
2. `Quick Clean` を開きます。
3. `Target` を `Object Names` または `Object + Mesh Data Names` にします。
4. `Preview .001 to _01` を押します。
5. `Safety Preview` で結果を確認します。
6. `Apply Previewed Operation` または `Apply .001 to _01` を押します。

### Object名をMesh Data名へ同期する

1. 対象Mesh Objectを選択します。
2. `Object / Mesh Name Sync` を開きます。
3. `Direction` を `Object Name -> Mesh Data Name` にします。
4. 共有Meshを保護したい場合は `Shared Mesh` を `Skip Shared Mesh Data` のままにします。
5. `Preview Sync` で確認します。
6. 問題なければ `Apply Sync` を押します。

### 同じMesh Dataを使うオブジェクトを選択する

1. 基準にしたいMesh ObjectをActive Objectにします。
2. `Link / Mesh Sharing Tools` を開きます。
3. `Select Same Mesh` を押します。

### Collection Instanceを参照元名でリネームする

1. Collection InstanceのEmptyを選択します。
2. `Collection Instance Tools` を開きます。
3. 必要に応じて `Pattern` を調整します。
4. `Preview Rename Instances` を押します。
5. `Safety Preview` で確認してから適用します。

## 安全設計

- 通常は選択中オブジェクトだけを処理します。
- 外部リンクされたObjectやMesh Dataは既定でスキップします。
- 共有Mesh Dataのリネームは既定でスキップします。
- 変更はSafety Previewで確認できます。
- 大量処理はmodal/timerで分割し、Nパネルに進捗を表示します。
- 長い処理は `Cancel Current Operation` でキャンセルできます。

## 注意点

- キャンセルしても、すでに処理済みの項目は自動では戻しません。必要に応じてBlenderのUndoを使ってください。
- `Make Selected Mesh Single User` はMesh Dataを複製するため、ファイルサイズが増える場合があります。
- Collection Instanceの選択・Mesh共有選択はScene内を走査します。非常に大きいSceneでは進捗表示を見ながら処理してください。
