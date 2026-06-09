# Collection Linked Mesh Replacer

配置済みMesh Objectを、指定Collection内の同形状アセットへ差し替えるBlender Extensionです。新しいObjectはSource ObjectとMesh Dataを共有するlinked duplicateとして作成されます。

## 基本情報

- Extension ID: `collection_linked_mesh_replacer`
- バージョン: `1.0.4`
- 対応Blender: `4.5.0` 以降
- 表示場所: `3D Viewport > Sidebar (N) > Mesh Replace`
- キャッシュ: メモリのみ。Blender終了時に消去

## 主な機能

- Source Collectionを手動スキャンして形状キャッシュを作成
- 子Collectionを含む再帰検索
- Object名、Mesh Data名、原点、頂点順に依存しない形状照合
- 頂点、辺、面、bounding box寸法、正規化済み頂点・トポロジーによるSHA-256 hash
- 完全一致が見つからない場合のプロポーション一致フォールバック
- Source ObjectとMesh Dataを共有するlinked duplicateへの差し替え
- 元Objectのworld transformと親子関係を引き継ぎ
- world bounding box centerによる原点ずれ補正
- 単体置換と選択Meshの一括置換
- 選択中Objectごとの対応先を一覧表示する複数プレビュー
- 複数候補があるObjectを警告表示し、first matchを使うことを明示
- 元Objectのバックアップ移動、削除、非表示、保持
- 複数候補時は名前順の最初の候補を使用

## 基本手順

1. 正規アセットをまとめたCollectionを`Source Collection`に指定します。
2. `Build / Update Cache`を押します。
3. 差し替えたいMesh Objectを選択してアクティブにします。
4. 必要なら`Find Match`で候補を確認します。
5. `Replace Selected`を押します。
6. 複数を処理する場合は対象を選択し、`Replace All Selected`を押して確認します。

複数Objectを処理する前に`Preview Selected`を押すと、選択中の各Objectについて対応するSource Object、候補数、Not Found、Skippedを一覧で確認できます。
選択を変えて再度プレビューした場合は、前回の単体Match Resultを消してから現在の選択結果を表示します。
候補が複数あるObjectは`Multiple Candidate Targets`として警告し、v1.0.4では名前順のfirst matchを使用します。

## 形状照合

照合にはMeshのlocal geometryを使います。頂点群をlocal bounding box center基準へ移動し、各軸のbounding box寸法で正規化してからソートします。さらに辺と面の接続情報、実寸のbounding box、頂点・辺・面数をhashへ含めます。

このため、次の違いは照合に影響しません。

- Object名
- Mesh Data名
- Object原点に対するMesh全体の平行移動
- 頂点の格納順
- Objectのworld transform

完全一致が見つからない場合は、uniform scale差や微小な寸法差を吸収する`Shape Match`として再検索します。この場合は置換後の見た目の大きさが変わりにくいよう、Source Meshのlocal bounding boxに合わせて新Objectのscaleを補正します。

## キャッシュ状態

- `Not Built`: キャッシュ未作成
- `Valid`: Source Collection、Object数、Collection Color、再帰設定が作成時と一致
- `Outdated`: 上記のいずれかが変更済み

Mesh内部の編集はv1.0ではOutdated判定に含めません。`Verify Match Before Replace`がONの場合は、差し替え直前に対象とSource Meshを再計算します。

## Transform

- `Keep Transform`: 元Objectの`matrix_world`と親子関係を引き継ぎます。
- `Adjust by Bounding Box Center`: 元Objectと新Objectのworld bounding box centerが一致するように位置を補正します。

## 元Objectの処理

- `Move to Backup Collection`: 既定。元Objectを`_MeshReplace_Backup`へ移動して非表示にします。
- `Delete Original`: 元Objectを削除します。
- `Hide Original`: 元Collection内に残してViewportとRenderで非表示にします。
- `Keep Original`: 元Objectを残し、新Objectを同じ場所へ追加します。

バックアップへ移動したObjectは名前末尾に`_backup`が付きます。新Objectは通常、元Objectの名前を引き継ぎます。`Rename New Object to Source Name`をONにするとSource Object名を使います。

## 注意点

- Source CollectionのObjectは既定で置換対象から除外されます。
- キャッシュは自動更新されません。Source Collectionを変更したら再ビルドしてください。
- Outdated状態でも実行できますが、警告が表示されます。
- 大量置換の前に`.blend`を保存してください。置換OperatorはUndoに対応しています。
