# Mesh Attribute Batch Remover

多数のMesh Objectから、指定名と完全一致するMesh Attributeをまとめて削除する軽量なBlender Extensionです。

## 基本情報

- Extension ID: `mesh_attribute_batch_remover`
- バージョン: `1.0.0`
- 対応Blender: `4.5.9 LTS` 以降
- 表示場所: `3D Viewport > Sidebar (N) > Attr Remove`

## 主な特徴

- 選択中のMesh、または現在のSceneにある全Meshから一括削除
- アクティブMeshのAttribute候補から選択、または名前を直接入力
- 同じMesh Dataを共有するObjectは固有Mesh単位で1回だけ処理
- 削除前に対象数、削除数、共有Meshの影響を確認
- 内部属性と必須属性を保護
- Undo対応
- 属性値、頂点、辺、面などのGeometryデータは走査しない軽量処理

## 使い方

1. BlenderをObject Modeにします。
2. `Selected Objects`を使う場合は、対象のMesh Objectを選択します。
3. 3D Viewportで`N`キーを押し、`Attr Remove`タブを開きます。
4. `Scope`を選びます。
5. `Attribute Name`で削除するAttributeを選択または入力します。
6. `Remove Attribute`を押します。
7. 確認画面の対象数と共有Mesh警告を確認して実行します。

## Scope

- `Selected Objects`: 選択中のMesh Objectだけを対象にします。
- `All Scene Objects`: 現在のSceneにあるすべてのMesh Objectを対象にします。非表示ObjectとViewport無効Objectも含みます。

## 削除ルール

- Attribute名は大文字小文字を区別した完全一致です。
- 同じMesh Dataを複数Objectが共有している場合、そのMesh Dataから1回だけ削除します。
- 対象外Objectも同じMesh Dataを共有している場合、そのObjectにも結果が反映されます。確認画面に影響Object数を表示します。
- `is_internal`または`is_required`のAttributeは削除しません。
- ライブラリリンクなど編集できないMeshはスキップします。
- 削除はBlenderのUndoで戻せます。

## 対応しないもの

- Custom Properties
- 複数Attribute名の同時指定
- ワイルドカード、部分一致、大文字小文字を無視した検索
- データ型やDomainによる一括削除
- Geometry Nodesやモディファイアの評価後にだけ存在するAttribute

このExtensionはMesh Dataに保存された実体のAttributeだけを対象にします。
