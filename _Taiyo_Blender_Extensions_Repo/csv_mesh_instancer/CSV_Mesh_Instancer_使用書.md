# CSV Mesh Instancer 使用書

## 1. 概要

CSV Mesh Instancerは、CSVに記録したObject名、位置、回転、スケールを読み込み、対応するMesh datablockを共有したObjectを配置します。6万Object規模を想定し、既定では処理を複数tickへ分割します。

表示場所:

```text
3D Viewport > Sidebar (N) > CSV Instancer
```

## 2. CSV形式

必須列:

```text
objname,tx,ty,tz,rx,ry,rz,sx,sy,sz
```

`ptnum`は任意です。存在しない、または値が空の場合はCSVの物理行番号を使用します。

- `tx/ty/tz`: Blender Locationへそのまま設定
- `rx/ry/rz`: 度数法として読み、XYZ Eulerへ変換
- `sx/sy/sz`: Blender Scaleへそのまま設定。0と負数も許可
- `objname`が空、または数値が空・文字列・NaN・Infinityの行はスキップ

CSVの読み込みに失敗した場合、前回正常に読み込んだデータは維持されます。外部でファイルが変更されると警告が表示されますが、自動再読込は行いません。

## 3. Collectionモード

1. `CSV File`を指定し、`Import CSV`を押します。
2. `Mesh Source`を`Collection`にします。
3. `Mesh Collection`を選択します。子Collectionも検索されます。
4. 必要なら`Ignore .001 Numeric Suffixes`を有効にします。
5. `Output`名を確認して`Update`を押します。

ソースCollectionとアウトプットCollectionが同じ、または親子関係にある場合は処理を中止します。同一Objectが両方にリンクされている場合も安全のため中止します。

## 4. FBXモード

1. `Mesh Source`を`FBX`にします。
2. `FBX File`と`Managed Collection`名を指定します。
3. `Import FBX`を押します。
4. CSV読込後に`Update`を押します。

FBXは一時Collectionへ読み込み、Meshが存在することを確認してから旧管理Collectionと差し替えます。失敗時は旧ソースを維持します。管理Collectionと同名の通常Collectionは上書きしません。読込後の管理Collectionは全View Layerで`Exclude`され、View Layerから取得できない場合はCollectionのViewport/Render表示を無効にします。

処理中のパネルは状態表示と`Cancel`だけになります。Blender標準FBXインポーターの実行部分は分割できないため、その間に受けたキャンセル要求は標準インポート終了直後に適用され、新規読込分を破棄して旧ソースを維持します。

配置Objectが引き継ぐのはMesh datablock側の情報です。ソースObjectのLocation、Rotation、Scale、Parent、Constraint、Animation、Modifierは配置へ引き継ぎません。ソースMeshのTransformが未適用の場合は警告します。

FBXの頂点座標がセンチメートル単位・軸変換前の状態で格納されていても、CSVの通常Transform値を変更しないよう、FBXモードの配置には既定で次のDelta Transform補正を適用します。

```text
Delta Scale: 0.01, 0.01, 0.01
Local X Rotation: 90°
```

Local X RotationはCSVの回転後にローカルX軸で適用され、Blenderで`R`→`X`→`X`→`90`と操作した場合と同じ結果になります。通常のCSV Euler値を維持するため、内部ではローカル補正を姿勢に応じたDelta Rotationへ変換します。そのため、ObjectのDelta Rotation欄に表示される各軸値はCSV姿勢によって変わります。

`Apply FBX Unit / Axis Correction`をOFFにすると補正なしになります。異なる単位・軸のFBXでは`Unit Scale`と`Local X Rotation`を調整してください。Collectionモードにはこの補正を適用しません。

## 5. 名前照合

通常は完全一致です。`Ignore .001 Numeric Suffixes`がONでも完全一致を最優先します。

生成Object名にはCSVの`objname`をそのまま使います。同名Objectがすでにある場合や同じ名前を複数行で配置する場合だけ、Blender形式の`.001`、`.002`を末尾へ追加します。`CSV_`や`ptnum`はObject名へ付けませんが、`ptnum`とCSV物理行番号はCustom Propertyへ保持します。

大量生成時のBlender内部の名前衝突処理を高速化するため、作成順は`objname`ごとに安定グループ化します。CSVの物理行番号とTransformの対応は変わらず、再更新でも各行のObject名を維持します。

サフィックス無視時の優先順位:

1. 完全一致
2. サフィックスなしObject
3. 数値サフィックスが最小のObject
4. Object名の辞書順

除去対象はObject名末尾のピリオドと3桁以上の数字だけです。`Wall.01`や`SM_001_Wall`は変更しません。

## 6. アウトプットと大量処理

初期アウトプット名は`CSV_Output`です。同名CollectionがあればCollection本体、名前、カラー、Viewport/Render設定を維持し、内容と子Collectionを置き換えます。検証が成功するまでは既存内容を変更しません。

`Split Across Multiple Ticks`は既定ONです。削除・生成・リンク・実体化を通常約12ms、大規模処理では速度と応答性を両立する約50msの時間枠に分割し、進捗とキャンセルボタンを表示します。OFFにすると同じ処理を一括実行するため速くなる場合がありますが、完了までBlender UIが応答しないことがあります。

初回生成や通常Objectを含む出力は一時Collectionで安全に作成します。このアドオンだけで作られた出力の再更新では、CSV行番号が同じObjectを再利用して高速化し、変更前の状態を保持します。確定前にキャンセルした場合は一時Objectを削除、または変更を巻き戻して以前のアウトプットを維持します。確定処理が始まった後は、Collectionを不整合にしないため確定完了まで処理します。

新しいアウトプットはSceneへ接続する前にObjectの生成とリンクを完了し、完成後に一度だけSceneへ接続します。これにより、大量Object生成中のView LayerとOutlinerの再評価を抑えます。Updateが正常終了したアウトプットは、ViewportとRenderの両方で自動的に非表示になります。必要なアウトプットは`Managed Outputs`の目のボタンで表示してください。

進捗率はCSV行、旧データ削除、Objectリンク、名前確定などの実作業数から計算されます。処理速度から推定した残り時間も表示されます。表示更新は約0.2秒間隔に制限され、進捗表示自体が大量処理を遅くしないようにしています。

### 6.1 Managed Outputs

`Managed Outputs`には、このアドオンが作成したすべての管理アウトプットCollectionが表示されます。各行には直下のObject数と子Collection数、および次のボタンがあります。

- 目のボタン: ViewportとRenderを同時に表示・非表示。表示時は現在のSceneにあるView LayerのExcludeも解除
- `X`: ルートCollection、名前、カラー、親リンク、管理情報を残し、中のObjectと子Collectionを高速削除
- ゴミ箱: 中身とルートCollectionをまとめて高速削除

削除対象は管理情報を持つCollectionだけです。実行前に対象数を表示する確認ダイアログが開きます。削除前にCollectionをSceneから一時的に切り離し、OutlinerとView Layerの再評価を抑えます。準備、子Collection、完了処理は`Split Across Multiple Ticks`がONなら短い適応バッチへ分割します。大量ObjectのID削除は、分割するとBlenderが残りのIDを何度も再走査して極端に遅くなるため、常に1回の`batch_remove`でまとめて実行します。この単一処理中だけはUIが数秒応答しない場合がありますが、Outlinerや分割削除より大幅に早く完了します。

Clear/Deleteは大量のUndoスナップショットを作らないため、確認後は取り消せず、削除開始後のキャンセルもできません。ソースMesh datablock、他のCollection、グローバルな孤立データには触れません。現在の出力CollectionをClear/Deleteした場合は生成統計をリセットしますが、出力名設定は維持されるため、次回Updateで同じ名前を再作成できます。

## 7. インスタンス実体化

`Make Meshes Single-User`は各ObjectのMesh datablockを個別コピーします。Object数とメモリ使用量が大幅に増えるため、確認ダイアログが表示されます。実体化中にキャンセルした場合は、変更済みObjectを元の共有Meshへ戻します。

再度`Update`すると、実体化済みObjectも共有Meshの配置へ戻ります。

## 8. エラーとログ

パネルには生成数、スキップ数、不足Mesh種類・行数、処理時間、最大tick時間を表示します。不足Mesh名とサフィックス衝突の全一覧はSystem Consoleへ出力します。

大量更新と実体化はメモリ負荷の大きなUndoスナップショットを作りません。アップデート前にアウトプットCollectionが専用Collectionであることを確認してください。
