# Blend Reference Graph

## 概要

`Blend Reference Graph` は、Blender内のObject、Mesh、Collection、Constraint、Geometry Nodesなどの参照関係をスキャンし、HTMLビューアでノードグラフとして確認するBlender Extensionです。

Unreal EngineのReference Viewerに近い発想で、選択したObjectやBoneが「何を参照しているか」「どこから参照されているか」を見える化します。

## 基本情報

- 本体フォルダ: `blend_reference_graph`
- 表示場所: `View3D > Sidebar (N) > Blend Ref Graph`
- バージョン: `0.1.0`
- 対応Blender目安: `4.2.0` 以降
- カテゴリ: `Object`

## Version 0.1 の対象

- Object
- Mesh
- Collection
- Parent / Children
- Object Constraint
- Pose Bone Constraint
- Armature / Bone
- Geometry Nodes Modifier
- Geometry NodesのNode Group
- Geometry Nodes内のObject / Collection / Material / Image / Sub Node Group参照

## 使い方

1. Blenderで対象Objectを選択します。
2. `View3D > Sidebar (N) > Blend Ref Graph` を開きます。
3. `Use Selected` を押してターゲットを登録します。
4. `Scan Mode` と `Depth` を設定します。
5. `Update + Open Viewer` を押します。
6. 生成されたHTMLビューアで参照関係を確認します。

Pose ModeでBoneを選択して `Use Selected` を押すと、対象BoneのConstraintを中心にグラフ化します。

## 出力ファイル

標準では現在のblendファイル基準で次のフォルダへ出力します。

```text
//blend_reference_graph/
```

生成されるファイル:

- `graph_data.js`
- `viewer.html`
- `viewer.css`
- `viewer.js`

## HTMLビューア

- ノード表示
- エッジ表示
- ノードドラッグ
- パン / ズーム
- Fit View
- Reload Data
- 検索
- タイプ別フィルター
- ノードクリック時の詳細表示

## 注意点

- Version 0.1は初期MVPです。Driver、Action、Library Linked Data、Safe Delete Previewは未対応です。
- 大規模シーンではグラフが大きくなるため、Depthを低めにしてください。
- `Open Viewer` はOSの標準ブラウザでローカルHTMLを開きます。
- HTMLを開いた後にBlender側で `Update Graph Data` を押した場合は、HTML側で `Reload Data` を押してください。
