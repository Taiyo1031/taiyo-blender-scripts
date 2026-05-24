# CHANGELOG v0.2

## v0.2

- `Export FBX` ボタンを折りたたみセクションの外に移動しました。
- `Main Actions` セクションを常時表示にしました。
- `Refresh Preview` と `Export FBX / Cancel Export` を常にアクセスしやすい位置に配置しました。
- Previewセクションは折りたたみ可能なまま残しました。
- 仕様として以下を維持しています。
  - 1コレクション = 1FBX
  - 非破壊処理
  - OriginはWorld 0,0,0
  - Transformを頂点に焼き込み
  - Apply Modifiers ON/OFF
  - Keep Material Slots ON/OFF
  - Include Hidden Objects ON/OFF、初期値ON
  - Include Collection Instances ON/OFF、初期値OFF
  - Modal Operatorによる分割処理
  - Progress Bar / Remaining Objects表示
  - Blenderファイルの自動保存なし
