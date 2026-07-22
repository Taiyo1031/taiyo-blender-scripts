# CSV Mesh Instancer

Version 2.0.0

CSVの永続IDを使い、CollectionまたはFBX内のMeshを共有するObjectを大量配置・差分更新するBlender Extensionです。Houdini RBDシミュレーション後のBlenderクリーンアップを想定し、前回CSV・新CSV・現在のBlender編集を比較して安全に更新します。

## 対応環境

- Blender 4.5.9以上
- `3D Viewport > Sidebar (N) > CSV Instancer`
- UIの既定言語は英語

## Version 2.0.0の主な機能

- 指定可能な永続ID列（既定`id`、負数可、空欄・重複はUpdate停止）
- 前回CSV、新CSV、現在のBlenderを比較する三方向Update
- Transform、Mesh、Custom Propertiesごとの独立した採用判断
- Blenderだけの編集は維持、競合は警告してBlenderを既定採用
- 変更行だけを表示する検索・絞り込み・ページング付きChange Review
- ID、Object、Zone、Status、Mesh名、変更Propertyの検索
- 1クリックのFocus、行別判断、検索結果への一括判断
- 複数属性の完全一致フィルター（同一属性はOR、異なる属性はAND）
- 属性別Collection分割（既定属性`Zone`、既定OFF）
- Blender/CSVから削除されたIDを非表示`Deleted` CollectionのEmptyとして保持し、明示的にRestore
- CSV追加列を型推定し、チェックした列だけObject Custom Propertyへ保存
- Collection/FBXソース、`.001`サフィックス照合、FBX Unit/Local X補正
- 進捗、ETA、キャンセル、`Split Across Multiple Ticks`（既定ON）
- 管理出力のShow/Hide、Clear Contents、Delete Collection
- 圧縮した永続ID台帳を`.blend`内のText datablockへ原子的に保存

## 重要な互換性

v2はv1.x出力と後方互換ではありません。v1.xの行番号・`ptnum`照合や自動移行は行いません。同名のv1.x管理Collectionを検出した場合は変更せず停止するため、削除するか別の出力名を指定してください。

詳細は[CSV Mesh Instancer 使用書](CSV_Mesh_Instancer_使用書.md)を参照してください。
