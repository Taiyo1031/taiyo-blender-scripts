# CSV Mesh Instancer 使用書

Version 3.0.1

## 1. 概要

CSV Mesh Instancerは、CSVに記録されたTransformを使い、FBXから読み込んだMeshを共有するObjectを配置します。Version 3では操作を`CSV Import`、`FBX Import`、`Placement`の3つだけに整理しています。

対応Blenderは4.5.9以上です。UIは`3D Viewport > Sidebar (N) > CSV Instancer`に表示され、既定言語は英語です。

## 2. CSV Import

必須列は次の10列です。その他の列は無視します。

```text
objname,tx,ty,tz,rx,ry,rz,sx,sy,sz
```

- UTF-8とUTF-8 BOMに対応
- `objname`の空欄をエラーとして停止
- Transform列の空欄、非数値、NaN、Infinityをエラーとして停止
- `rx/ry/rz`は度数法として読み込み、BlenderのXYZ Eulerへ変換
- `id`、`ptnum`、Zoneなどの追加列は不要で、配置には使用しない
- 外部でCSVが変更された場合は、Placement前に再Importを要求

## 3. FBX Import

FBX内のMesh Objectを専用のSource Collectionへ読み込みます。Source CollectionはViewportとRenderから非表示になり、可能なView LayerではExcludeされます。

`Show FBX Source` / `Hide FBX Source`でSource Collection全体のViewport・Render表示を切り替えます。

再Import時は旧ソースの名前を一時退避してから読み込むため、FBX本来のObject名・Mesh名を照合に使用できます。出力が使用中の旧Meshは次のPlacementまで`[Previous FBX]`名で保持し、未使用になったものだけ削除します。不正FBXでは旧ソースと名前を復旧します。

## 4. Placement

`objname`とFBX Object名を照合し、Mesh datablockを共有するObjectを出力Collectionへ作成します。

- Location、XYZ Euler Rotation、ScaleをCSVから設定
- `Apply FBX Correction`既定ON
- Unit Scale既定`0.01`
- Local X Rotation既定`90°`。BlenderのローカルX回転に相当
- `Ignore .001 Suffixes`では末尾の`.数字3桁以上`だけを無視
- Object名に`CSV_`は付けず、`CSV物理行_objname`形式を使用。行番号を先頭に置いてBlender内部の名前比較を高速化し、Mesh datablock名はFBXの元名をそのまま維持
- 同名のVersion 3出力は全置換
- 通常Collectionや旧Version出力は上書きしない
- 大量ObjectのViewport再評価を避けるため、完成した出力CollectionはViewportとRenderで非表示
- `Show CSV Output` / `Hide CSV Output`で出力Collection全体のViewport・Render表示を切り替え

表示切替はObject単位のoperatorや走査を使わず、CollectionとView Layerの設定だけを変更します。そのためアドオン側の処理量はCollection内のObject数に依存しません。Hide時はView Layerから再Excludeし、次のPlacementで非表示Objectが評価されるのを防ぎます。Show時はView Layerへ対象を戻すため、Blenderのdepsgraph更新時間がかかる場合があります。

`Split Across Multiple Ticks`は既定ONです。大量配置を約12ms単位に分け、進捗とETAを低頻度で更新します。初回生成中のCancelでは新しい仮出力だけを削除します。再配置ではメモリを二重使用しないよう旧Objectを再利用するため、処理開始後はCancelを無効化します。OFFでは同じ処理を一括実行します。

60,474行・1,225種類の実CSVを使ったBlender 4.5.9負荷試験では、CSV Import 0.29秒、初回Placement 2.05秒、再Placement 0.47秒を確認しています。環境やデータ構成で時間は変わります。

## 5. Version 3で削除した機能

- Stable IDとID台帳
- Preview ChangesとChange Review
- Transform、Mesh、Propertyごとの採用判断
- 検索、フィルター、Zone Collection分割
- CSV追加属性のCustom Property転送
- Deleted EmptyとRestore
- Managed Outputs一覧、Clear、Delete
- 実体化
- v1/v2出力の移行と更新

## 6. エラー時の動作

- CSV不正: キャッシュを差し替えず停止
- FBX不正・Meshなし: 新規Importを削除して旧ソースを復旧
- 不足Mesh: 該当行だけSkipし、件数と名前を結果へ表示
- 出力名衝突: 通常Collectionまたは旧Version出力を変更せず停止
- Placement Cancel: 仮出力を削除して旧出力を維持

## 過去バージョン

- [Version 2.0.1 ZIP](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/csv_mesh_instancer-2.0.1.zip)
- [Version 1.1.0 ZIP](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/csv_mesh_instancer-1.1.0.zip)
