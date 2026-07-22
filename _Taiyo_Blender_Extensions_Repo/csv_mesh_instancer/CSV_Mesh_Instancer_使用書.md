# CSV Mesh Instancer 仕様書・使用書

Version 2.0.0

## 1. 概要

CSV Mesh Instancerは、CSVの永続ID、Object名、Transformを読み込み、CollectionまたはFBX内のMesh datablockを共有したObjectを配置します。前回CSV、新CSV、現在のBlender ObjectをIDごとに比較し、Houdiniの再シミュレーション結果をBlender側の手修正を壊さず反映できます。

表示場所:

```text
3D Viewport > Sidebar (N) > CSV Instancer
```

UIは英語が既定で、次の順に整理されています。

```text
CSV & Identity
Source
Update Rules
Attribute Filters
Preview & Apply
Managed Outputs
Advanced
```

## 2. Version 2の互換性

Version 2.0.0はv1.xと後方互換ではありません。v1.xの出力、CSV物理行番号、`ptnum`による照合・移行・フォールバックは行いません。v1.xマーカーまたは非対応schemaの同名Collectionは上書きせず停止します。v1.x出力を削除するか、新しい出力名を指定してください。

## 3. CSV形式と永続ID

必須列:

```text
objname,tx,ty,tz,rx,ry,rz,sx,sy,sz
```

さらにIdentity Columnで指定したID列が必要です。既定は`id`です。

- IDはHoudiniを再計算しても同じ破片に残る永続値を使用
- 正負の整数・文字列を使用可能。負数も有効
- 空IDまたは重複IDが1件でもあればCSV全体を拒否し、物理行番号を表示
- ZoneはIDの一部ではなく、フィルター・Collection分割用の属性
- `ptnum`はエラー行の確認以外に使わず、Object名・Custom Property・永続台帳へ保存しない
- `tx/ty/tz`はLocation、`rx/ry/rz`は度数法のXYZ Euler、`sx/sy/sz`はScale
- NaN、Infinity、空の数値、空`objname`は不正
- UTF-8とUTF-8 BOMに対応

CSVの追加列は型推定され、CSV & Identity内に列ごとの`Write to Objects`チェックが表示されます。チェックした列だけが同名のObject Custom Propertyになります。既定はOFFです。IDは指定列名と内部管理用`csvmi_id`へ保存します。

## 4. Source

### Collection

Mesh Collectionとその子Collectionを再帰検索します。完全一致を優先し、`Ignore .001 Numeric Suffixes`がONなら末尾の`.001`形式だけを無視します。候補はサフィックスなし、最小番号、辞書順で決定します。

### FBX

FBXは一時Collectionへ読み込み、Meshがあることを確認してから旧管理Collectionと差し替えます。失敗時は旧FBXソースと出力を維持します。読込後は全View LayerでExcludeし、利用できない場合はCollectionをViewport/Renderで非表示にします。

FBX補正の既定値:

```text
Delta Scale: 0.01
Local X Rotation: 90°
```

Local X RotationはCSV回転後のローカルX軸へ適用され、Blenderの`R`→`X`→`X`→`90`に相当します。Collectionモードには補正しません。

生成Object名はCSVの`objname`を使い、重複時だけ`.001`、`.002`を末尾へ付けます。`CSV_`やID、`ptnum`は名前に付けません。

## 5. Preview Changesの三方向比較

`Preview Changes`はSceneを変更しません。IDごとに次を比較します。

1. 前回Apply時のCSVと採用状態
2. 今回ImportしたCSV
3. 現在のBlender Object

Transform、Mesh、Custom Propertiesは独立して判定します。

| 変更元 | 既定動作 |
| --- | --- |
| CSVだけ変更 | CSVを適用 |
| Blenderだけ変更 | Blenderを維持 |
| CSVとBlenderの両方を変更 | Conflictとして警告し、Blenderを維持 |
| 未編集Meshの`objname`/FBXソース変更 | 新しい共有Meshへ再リンク |
| Single-Userまたは別Meshへ手編集 | 現在Meshを維持して警告 |

TransformはLocation・Rotation・Scaleを1ドメインとして扱います。固定許容値はLocation/Scale `1e-5`、Quaternion角度 `1e-4 rad`です。決定したOverrideはCSV側が再度変わるまでChange Reviewへ繰り返し表示しません。

## 6. Change Review

変更がないIDは表へ表示しません。表にはID、Zone、Object、Status、Transform、Mesh、Props、Decision、Focusをコンパクトに表示します。

- Search: ID、Object名、Zone、Status、旧新Mesh名、変更Property名を検索
- Filters: Status、Zone、Transform/Mesh/Props変更で絞り込み
- Paging: 100件単位
- Apply CSV / Keep Blender: Transform、Mesh、Propsを個別判断
- Create / Skip / Move to Deleted / Keep Deleted / Restore: Object状態を判断
- Bulk: 現在の検索結果へ一括判断
- Focus: 出力を表示し、Objectを選択してViewport中央へ移動。Objectがない行は最終位置へ移動

CSV、Source、Update Rules、フィルター、SceneがPreview後に変わった場合、古いPreviewは無効になります。

## 7. Attribute FiltersとZone分割

初回生成はフィルターを無視して全IDを作成します。2回目以降は完全一致フィルターを複数追加できます。

- 同じ属性内の複数値はOR
- 異なる属性同士はAND
- 対象外IDは新規作成・更新・削除判定を行わない

例えば`Zone == 1`だけを選ぶと、その場所だけを更新できます。

`Split by Attribute`は既定OFF、属性名の既定は`Zone`です。ONでは`Zone_0`、`Zone_1`などの管理子Collectionへ分け、属性値が変わればObjectを移動します。

## 8. 削除とRestore

Blender標準Deleteで消したID、または新CSVから消えたIDは、出力配下の非表示`Deleted` CollectionへHidden Emptyとして保存します。Mesh ObjectとEmptyの型変更は安全な置換として処理されます。

- EmptyはIDと最終Transformを保持
- IDが後のCSVへ再登場しても自動復元しない
- Change Reviewで`Restore`を選ぶまで削除状態を維持
- CSVから消えたIDを残したい場合は`Keep Blender`相当の判断が可能

## 9. Apply、進捗、安定性

ApplyはPreview済み判断だけを反映し、最後に圧縮したschema v2 ID台帳を内部Text datablockへ原子的に差し替えます。失敗・キャンセル時は旧台帳を維持します。台帳には前回CSV値、Transform、objname、属性、Override、削除状態を保存するため、`.blend`を閉じて開き直しても差分判定できます。

`Split Across Multiple Ticks`は既定ONです。大量のObject変更を適応チャンクへ分割し、進捗率、段階、ETAを約0.2秒間隔で更新します。処理中は設定・管理操作をロックし、Cancelだけを表示します。OFFでは同じ処理を一括実行して速度を優先します。

出力は空のうちにSceneへ接続・View LayerからExcludeし、大量Object生成中のdepsgraph/Outliner再評価を抑えます。成功後はViewportとRenderの両方で非表示のままです。60,474行の実CSV一時修正版によるBlender 4.5.9負荷試験では、CSV Import 0.43秒、初回Preview 0.53秒、初回Apply 14.81秒、無変更Preview 1.30秒を確認しています。環境や選択Custom Property数で時間は変わります。

## 10. Managed Outputs

管理マーカーを持つ出力Collectionだけを一覧表示します。

- Show/Hide: ViewportとRenderを同時切替。Show時はView LayerのExcludeも解除
- Clear Contents: ルートCollection、名前、色、親リンク、管理マーカーを残して配下を削除
- Delete Collection: 配下とルートCollection、内部状態Textを削除

Clear/Deleteは対象数を示す確認後、`batch_remove`で高速削除します。大量Undoは作らず、削除開始後はキャンセルできません。ソースMesh、他の管理Collection、グローバルな孤立データは削除しません。

## 11. エラー時の安全動作

- CSVの空/重複ID: 全Update停止、問題IDと行番号を表示
- 不足Mesh: 件数・名前を表示し、該当作成をSkip
- v1.xまたは状態schema不一致: 出力を変更せず停止
- 内部Text破損: 出力を変更せず停止
- Preview後のScene変更: Applyを拒否して再Previewを要求
- FBX失敗: 旧ソースと旧出力を維持
- Cancel: 変更済みObjectを復旧し、旧ID台帳を維持

## 過去バージョン

- [Version 1.1.0 ZIP](https://taiyo1031.github.io/taiyo-blender-scripts/extensions/csv_mesh_instancer-1.1.0.zip)
