# Custom Properties Batch Editor

Object、Mesh Data、MaterialのCustom Propertiesをまとめて追加、編集、検索、削除するBlender Extensionです。

## 基本情報

- Extension ID: `custom_properties_batch_editor`
- バージョン: `1.0.0`
- 対応Blender: `4.4.0` 以降
- 表示場所: `3D Viewport > Sidebar (N) > Custom Props`

## 主な機能

- Object、Mesh Data、Materialへの型付きCustom Property一括追加・編集
- String、Int、Float、Boolに対応
- Selected Objects、Active Object、All Scene ObjectsのScope切り替え
- Exists、Equals、Contains、Not Existsによる検索
- Mesh DataやMaterialの検索結果から、それを参照するObjectを選択
- 値条件付きの一括削除とUndo
- Active Objectまたは複数対象のProperty一覧、Count、Mixed Value表示
- 複数Custom PropertiesをまとめたJSONプリセット
- 処理件数と詳細ログの表示、クリップボードへのコピー

## Custom Propertyを一括設定する

1. 対象Objectを選択します。
2. `N` キーでサイドバーを開き、`Custom Props` タブを選びます。
3. `Target` で保存先とScopeを選びます。
4. `Add / Edit Property` で名前、型、値、Operation Modeを指定します。
5. `Apply Property` を押します。

Operation Mode:

- `Add or Overwrite`: 存在しなければ追加し、存在すれば上書き
- `Add Only`: 存在しない対象だけに追加
- `Edit Existing Only`: すでに持っている対象だけを変更

## Target Type

- `Object`: Object本体へ保存します。
- `Mesh Data`: Meshデータへ保存します。同じMeshを共有するObjectは、`Unique Data Only` がONなら1回だけ処理します。
- `Material`: Material Slotに割り当てられたMaterialへ保存します。同じMaterialは1回だけ処理します。

非表示ObjectやViewport無効Objectは初期状態では除外されます。必要な場合は`Include Hidden`または`Include Disabled Viewport`をONにしてください。

## 検索

`Search / Select`でProperty名と条件を指定します。

- `Exists`: Propertyが存在する
- `Equals`: 型と値が一致する
- `Contains`: String値に文字列を含む
- `Not Exists`: Propertyが存在しない

`Print Result`はログだけを更新し、`Select Results`は一致したObjectを選択します。Mesh DataやMaterialを検索した場合も、それを参照するScope内のObjectが選択されます。

## 削除

`Delete Property`でProperty名を指定し、必要なら値一致条件を設定します。表示される`Matching Targets`を確認し、`Confirm Delete`をONにして実行してください。削除はUndoできます。

## Property List

- `Active Only`: Active Objectに対応する現在のTargetだけ
- `Selected Summary`: 選択Object全体
- `Target Data`: 現在のScope全体

`Refresh Property List`を押すと、Property名、型、値、所有数を表示します。値や型が異なる場合は`Mixed`と表示します。

## プリセット

`Add / Edit Property`で入力したPropertyを`Add Current Property`でPreset Editorへ追加します。同名Propertyを追加すると置き換わります。複数項目を用意してPreset Nameを入力し、`Save Preset`で保存します。

ユーザープリセットはBlenderのユーザー設定領域に`custom_properties_batch_editor/presets.json`として保存され、Extension更新後も維持されます。初回は以下のプリセットを作成します。

- Unreal Static Mesh Export
- Breakable Object
- School Environment

Importは同名プリセットを置き換えてマージします。Exportは現在の全プリセットをJSONへ書き出します。

## 注意事項

- `_RNA_UI`はBlender予約名のため編集できません。
- ライブラリリンクなど読み取り専用データはスキップされます。
- v1.0ではCollection指定、Bone、Pose Bone、Vector、Color、CSV、検索結果のIsolateには対応していません。
- 1000件を超える処理では、件数ログを残して詳細ログを省略します。
