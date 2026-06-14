# Map Link Tools

## 概要

`Map Link Tools` は、マップ・環境制作で使う名前整理、共有Meshチェック、置換作業だけに絞ったBlender Extensionです。

今後ツールを一つずつ追加しやすいように、機能は `Rename` / `Check` / `Replace` の3ジャンルに分けています。

## 基本情報

- 本体フォルダ: `map_link_tools`
- 表示場所: `View3D > Sidebar (N) > Map Link Tools`
- バージョン: `0.2.4`
- 対応Blender目安: `4.5.0` 以降
- カテゴリ: `Object`

## Rename

- `Remove .001 From Selected Objects`
  - 選択Object名の末尾 `.001`, `.002` などを削除します。
  - 削除後の名前が既に存在する場合はリネームせず、スキップとして通知します。
  - `Rename Unselected Conflicts` がONの場合、削除後の名前を選択外Objectが使っているときだけ、その選択外Objectを選択Objectの元の `.001` 名へリネームしてから実行します。
  - 複数選択や `Cube.001.001` のような連鎖名でも、`.001` 側から安定した順番で処理します。
  - `_01` のような別suffixは作りません。
- `Object Name -> Mesh Name`
  - 選択Mesh ObjectのMesh Data名をObject名に合わせます。
  - Mesh Data名が衝突する場合はスキップして通知します。
- `Mesh Name -> Object Name`
  - 選択Mesh ObjectのObject名をMesh Data名に合わせます。
  - Object名が衝突する場合はスキップして通知します。

## Check

- `Collection A` と `Collection B` を指定します。
- Collection pickerはCollectionの `color_tag` に合わせた色付きアイコンを表示します。
- `Check Mesh Links` で、2つのCollection間に同じMesh Dataを共有しているObjectがあるか確認します。
- 各Collection横の `Select Unlinked` で、相手CollectionとMesh Dataを共有していないObjectを選択します。
- Collection内のObjectは子Collectionも含めて走査します。
- `Check Mesh Links` と `Select Unlinked` はmodal/timer処理で数ティックに分けて実行します。

## Replace

- `Replace Selected With Active Object`
  - 選択ObjectをActive Mesh Objectに置換します。
  - 元ObjectのTransform、名前、所属Collectionを保持します。
  - `Use Mesh Instance` ON: Active ObjectのMesh Dataを共有します。
  - `Use Mesh Instance` OFF: Active ObjectのMesh Dataをコピーします。
- `Replace Selected With Collection Instance`
  - 選択Objectを指定CollectionのCollection Instance Emptyに置換します。
  - 元ObjectのTransform、名前、所属Collectionを保持します。
  - `Set` ボタンでActive Layer Collectionを指定欄へ入れられます。
- `Replace Collection Instances With Matching Mesh`
  - 選択中のCollection Instance Objectを、指定Collection内の同名Mesh Objectへ置換します。
  - 名前比較では選択Object名と候補Mesh Object名の末尾 `.001` などを無視します。
  - 候補が見つからない場合、または同名候補が複数ある場合はスキップして通知します。

## Helper

- `Unhide Collection + Objects`
  - 指定Collectionと子Collectionを表示状態に戻します。
  - 指定Collection配下のObjectも表示状態に戻します。
  - 現在のView Layerに存在するLayer Collectionも `exclude` / `hide_viewport` を解除します。
  - 大きなCollectionでも固まりにくいよう、modal/timer処理で数ティックに分けて実行します。
- `Make Selectable Too`
  - ONの場合、`Unhide Collection + Objects` 実行時にCollectionとObjectを選択可能にも戻します。
- `Make Collection + Objects Selectable`
  - 表示状態は変えず、指定Collectionツリーと配下Objectを選択可能に戻します。

## 導入手順

1. Blenderで `Edit > Preferences > Add-ons` を開きます。
2. `Install from Disk` から、このExtensionのzipまたはフォルダをインストールします。
3. `Map Link Tools` を有効化します。
4. 3D Viewportを開きます。
5. `N` キーでSidebarを開きます。
6. `Map Link Tools` タブを開きます。

## 注意点

- 直接実行型のツールです。必要に応じてBlenderのUndoで戻してください。
- リンク判定は、同じMesh Dataを共有しているかどうかで行います。
- 外部リンクされたデータを編集する場合はBlender側の制約で失敗することがあります。その場合はスキップとして通知されます。
