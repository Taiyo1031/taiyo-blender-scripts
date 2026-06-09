# Move Objects to Own Collections 使用書

## このアドオンでできること
選択したオブジェクトを、オブジェクト名と同じ名前のコレクションへまとめます。

移動先のコレクションは、オブジェクトが現在入っているコレクションの中に作られます。既に同じ名前の子コレクションがある場合は、そのコレクションを再利用します。

## インストール方法
Blender 4.2以降では、Taiyo Blender ScriptsのRemote Repositoryからインストールできます。

Remote Repository URL:

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

1. Blenderを開きます。
2. `Edit > Preferences > Get Extensions` を開きます。
3. `Repositories` からRemote Repositoryを追加します。
4. `Move Objects to Own Collections` を検索してインストールします。
5. アドオンを有効にします。

## 使い方
1. 3D Viewで整理したいオブジェクトを選択します。
2. 右側のSidebarを開きます。表示されていない場合は `N` キーを押します。
3. `Collection Tools` タブを開きます。
4. 移動先コレクションに色を付けたい場合は、`Set Collection Color` を有効にして `Collection Color` を選びます。
5. Object名でコレクションを作る場合は `Move by Object Name`、Meshデータ名で作る場合は `Move by Mesh Name` を押します。

## 実行例
`Assets` コレクションの中に `Chair`、`Table`、`Lamp` がある状態で実行すると、次のように整理されます。

```text
Assets
├─ Chair
│  └─ Chair
├─ Table
│  └─ Table
└─ Lamp
   └─ Lamp
```

## 仕様
- 移動先コレクション名はオブジェクト名です。
- 基準になる元コレクションは、オブジェクトの最初の所属コレクションです。
- 元コレクション直下に同名の子コレクションがある場合は、それを使います。
- 元コレクション直下にない場合は、同名の既存コレクションデータをリンクするか、新しく作成します。
- `Move by Object Name` はObject名を移動先コレクション名に使います。
- `Move by Mesh Name` はMeshオブジェクトのMeshデータ名を移動先コレクション名に使います。Mesh以外のオブジェクトはObject名を使います。
- `Set Collection Color` が有効な場合は、移動先コレクションのOutliner色を指定した色に設定します。既存コレクションを再利用した場合も、その色に更新されます。
- 移動後、オブジェクトは移動先以外のコレクションから外されます。

## 注意点
- オブジェクト名と同名のコレクションデータが別の場所に既にある場合、そのコレクションが元コレクションにもリンクされます。
- Blenderではコレクションデータ名が重複すると自動で `.001` などが付くことがあります。このアドオンは、できるだけオブジェクト名と一致する既存コレクションを再利用します。
- コレクションに所属していないオブジェクトはスキップされます。

## トラブルシューティング
- ボタンが見つからない場合は、Add-onsまたはExtensionsでアドオンが有効になっているか確認してください。
- Sidebarが表示されない場合は、3D Viewで `N` キーを押してください。
- 何も起きない場合は、オブジェクトを選択してから実行してください。
