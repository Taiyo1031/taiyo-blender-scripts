# Move Objects to Own Collections

## 概要
選択中のオブジェクトを、それぞれのオブジェクト名と同じ名前のコレクションへ移動するアドオンです。

移動先コレクションは、オブジェクトが元々入っていたコレクションの中に作成または再利用されます。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Collection Tools`
- バージョン: `1.4.0`
- 対応Blender目安: `4.2.0` 以降
- カテゴリ: `Object`

## 使う場面
- 選択オブジェクトごとに個別コレクションへ整理したい
- オブジェクト名とコレクション名を揃えて管理したい
- アセット、パーツ、インスタンス用の階層を素早く作りたい

## 最短手順
1. 整理したいオブジェクトを選択します。
2. `Collection Tools` パネルを開きます。
3. 必要に応じて `Set Collection Color` を有効にし、移動先コレクションへ付ける色を選びます。
4. Object名でコレクションを作る場合は `Move by Object Name`、Meshデータ名で作る場合は `Move by Mesh Name` を押します。

## 結果
各オブジェクトは、元の所属コレクション内にある同名コレクションへ移動します。

例:

```text
Original Collection
├─ Chair
│  └─ Chair
└─ Table
   └─ Table
```

## 注意点
- 選択オブジェクトがない場合は実行されません。
- オブジェクトが複数コレクションに所属している場合、最初の所属コレクションを基準にします。
- 同名コレクションが元コレクション直下にある場合は再利用します。
- 同名コレクションデータが既に存在する場合は、それを元コレクションへリンクして再利用します。
- `Set Collection Color` が有効な場合、作成または再利用した移動先コレクションのOutliner色が指定色に更新されます。
- `Move by Mesh Name` では、MeshオブジェクトはMeshデータ名を使います。Mesh以外のオブジェクトはObject名を使います。

## 詳細な使用書
- `Move_Objects_to_Own_Collections_使用書.md`

## GitHub仕様書
- [Move_Objects_to_Own_Collections_使用書.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/move_selected_to_own_collections/Move_Objects_to_Own_Collections_%E4%BD%BF%E7%94%A8%E6%9B%B8.md)
