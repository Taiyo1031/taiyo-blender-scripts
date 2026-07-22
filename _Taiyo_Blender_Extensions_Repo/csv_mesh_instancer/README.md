# CSV Mesh Instancer

CSVの`objname`とTransformを読み取り、CollectionまたはFBX内のMeshを共有するリンクObjectとして大量配置するBlender Extensionです。

## 対応環境

- Blender 4.5.9以上
- `3D Viewport > Sidebar (N) > CSV Instancer`
- UIの既定言語は英語

## 主な機能

- CSVのインポート・安全な再インポート
- CollectionまたはFBXをMeshソースとして使用
- FBX配置へ既定でDelta Scale `0.01`・Local X Rotation `90°`の単位／軸補正を適用（`R`→`X`→`X`と同じローカル軸、UIで調整・無効化可能）
- FBX管理Collectionを全View Layerから除外（不可時はCollectionを非表示）
- 子Collectionを含むMesh検索
- 完全一致優先と`.001`等の数値サフィックス無視
- 位置・XYZ回転（度）・スケールによるリンクMesh配置
- 生成Object名はCSVの`objname`を使い、重複時だけ`.001`形式の末尾番号を追加
- 出力Collectionの検証後上書き
- Scene未接続のCollectionへ先に配置する高速な初回Update
- 実作業量に基づく進捗率と低負荷な残り時間表示
- Update完了時に出力をViewport・Renderの両方で自動非表示
- 生成Collectionの一覧、表示切替、中身の高速削除、Collection全体の高速削除
- 通常約12ms・大規模時約50msの`Split Across Multiple Ticks`処理とキャンセル
- 共有Meshの個別Mesh化
- 不正行、不足Mesh、名前衝突の集計
- 処理中は状態表示とキャンセルだけにUIをロック

詳細は[CSV Mesh Instancer 使用書](CSV_Mesh_Instancer_使用書.md)を参照してください。
