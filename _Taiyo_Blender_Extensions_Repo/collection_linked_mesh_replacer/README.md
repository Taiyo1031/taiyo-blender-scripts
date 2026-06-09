# Collection Linked Mesh Replacer

配置済みMesh Objectを、指定Collection内の同形状アセットへ差し替えるBlender Extensionです。新しいObjectはSource ObjectとMesh Dataを共有するlinked duplicateとして作成されます。

## 基本情報

- Extension ID: `collection_linked_mesh_replacer`
- バージョン: `1.0.7`
- 対応Blender: `4.5.0` 以降
- 表示場所: `3D Viewport > Sidebar (N) > Mesh Replace`
- キャッシュ: メモリのみ。Blender終了時に消去

## 主な機能

- Source Collectionを手動スキャンして形状キャッシュを作成
- 子Collectionを含む再帰検索
- Object名、Mesh Data名、原点、頂点順に依存しない形状照合
- 頂点、辺、面、bounding box寸法、正規化済み頂点・トポロジーによるSHA-256 hash
- 完全一致が見つからない場合のプロポーション一致フォールバック
- キャッシュを使わず全Source Meshを再検査するThorough Search
- 指定したMesh ObjectでActive Objectを置換するManual Replacement
- Source ObjectとMesh Dataを共有するlinked duplicateへの差し替え
- 元Objectのworld transformと親子関係を引き継ぎ
- world bounding box centerによる原点ずれ補正
- 選択Meshの一括置換（1個選択も同じ操作）
- 置換前に必ず表示される選択中Objectごとのプレビュー
- 候補なし時に一度だけキャッシュを自動再構築するオプション
- 複数候補があるObjectを警告表示し、first matchを使うことを明示
- 元Objectのバックアップ移動、削除、非表示、保持
- 複数候補時は名前順の最初の候補を使用

## 基本手順

1. 正規アセットをまとめたCollectionを`Source Collection`に指定します。
2. `Build / Update Cache`を押します。
3. 差し替えたいMesh Objectをすべて選択します。
4. リロードアイコンの`Replace All Selected`を押します。
5. 必ず表示されるプレビューで、各ObjectのSource Object、候補数、Not Found、Skippedを確認してから実行します。

単体専用の置換ボタンはありません。Objectを1個だけ選択した場合も、同じ`Replace All Selected`を使用します。プレビュー専用ボタンもなく、置換前の確認ダイアログへ常に表示されます。
候補が複数あるObjectは`Multiple Candidate Targets`として警告し、名前順のfirst matchを使用します。

## 形状照合

照合にはMeshのlocal geometryを使います。頂点群をlocal bounding box center基準へ移動し、各軸のbounding box寸法で正規化してからソートします。さらに辺と面の接続情報、実寸のbounding box、頂点・辺・面数をhashへ含めます。

このため、次の違いは照合に影響しません。

- Object名
- Mesh Data名
- Object原点に対するMesh全体の平行移動
- 頂点の格納順
- Objectのworld transform

完全一致が見つからない場合は、uniform scale差や微小な寸法差を吸収する`Shape Match`として再検索します。この場合は置換後の見た目の大きさが変わりにくいよう、Source Meshのlocal bounding boxに合わせて新Objectのscaleを補正します。

## 最終手段のThorough Search

通常検索で`Not Found`になる場合は、`Fallback / Manual`パネルを開きます。

- `Thorough Check Active`: キャッシュを使わず、Source Collection内の全Meshを最新状態で再読み込みしてActive Objectと比較します。
- `Thorough Replace Active`: 同じ完全走査を実行し、見つかった名前順の最初の候補でActive Objectを置換します。実行前に確認ダイアログを表示します。

Thorough Searchは通常のhash照合に加え、bounding box比率、全頂点の対応付け、辺・面の接続を許容誤差付きで比較します。キャッシュ作成後にSource Mesh内部を編集し、Cache Statusが`Valid`のまま通常検索できない場合にも使用できます。Source数や頂点数が多いほど時間がかかるため、通常検索で見つからない場合の最終手段として使用してください。

## Manual Replacement

自分で置換元を指定する場合は、`Fallback / Manual > Manual Source Object`へ使用したいMesh Objectを設定します。差し替えたいObjectをActiveにして`Replace Active Manually`を押すと、形状照合を行わず、指定ObjectのMesh Dataを共有するlinked duplicateへ置換します。

Manual Source ObjectはSource Collection外からも指定できます。元Objectの処理、Transform、bounding box center補正、置換後の選択設定は通常置換と共通です。

## キャッシュ状態

- `Not Built`: キャッシュ未作成
- `Valid`: Source Collection、Object数、Collection Color、再帰設定が作成時と一致
- `Outdated`: 上記のいずれかが変更済み

Mesh内部の編集はv1.0ではOutdated判定に含めません。`Verify Match Before Replace`がONの場合は、差し替え直前に対象とSource Meshを再計算します。

`Auto Rebuild Cache When No Match`がONの場合、選択中の有効なMeshに候補0件が1つでもあると、キャッシュを一度だけ自動再構築して全選択を再照合します。キャッシュ未作成の場合も自動構築します。OFFの場合は現在のキャッシュだけで判定し、候補なしのObjectを置換しません。

## Transform

- `Keep Transform`: 元Objectの`matrix_world`と親子関係を引き継ぎます。
- `Adjust by Bounding Box Center`: 元Objectと新Objectのworld bounding box centerが一致するように位置を補正します。

## 元Objectの処理

- `Move to Backup Collection`: 既定。元Objectを`_MeshReplace_Backup`へ移動して非表示にします。
- `Delete Original`: 元Objectを削除します。
- `Hide Original`: 元Collection内に残してViewportとRenderで非表示にします。
- `Keep Original`: 元Objectを残し、新Objectを同じ場所へ追加します。

バックアップへ移動したObjectは名前末尾に`_backup`が付きます。新Objectは通常、元Objectの名前を引き継ぎます。`Rename New Object to Source Name`をONにするとSource Object名を使います。
Backup Collectionが現在のView Layerで除外されている場合も、元Objectの退避処理は継続されます。

## 注意点

- Source CollectionのObjectは既定で置換対象から除外されます。
- キャッシュは自動更新されません。Source Collectionを変更したら再ビルドしてください。
- Outdated状態でも実行できますが、警告が表示されます。
- 大量置換の前に`.blend`を保存してください。置換OperatorはUndoに対応しています。
