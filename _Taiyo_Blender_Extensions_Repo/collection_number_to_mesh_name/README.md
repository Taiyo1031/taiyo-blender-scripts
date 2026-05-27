# Collection Number To Mesh Name

## 概要
シーンのコレクションを階層順に採番し、各コレクション内のMeshデータ名を `001_CollectionName` 形式に変更するアドオンです。

Object名は変更せず、Meshデータ名だけを整理できます。Collection Instanceなどの実体化と、共有Meshのシングルユーザー化にも対応します。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Taiyo Tools`
- バージョン: `1.0.1`
- 対応Blender目安: `4.2.0` 以降
- カテゴリ: `Object`

## 最短手順
1. 3D View右側の `N` パネルを開きます。
2. `Taiyo Tools` タブの `Collection Mesh Renamer` を開きます。
3. `Start Number` と `Digits` を必要に応じて設定します。
4. インスタンスや共有Meshを処理する設定を確認します。
5. `Rename Mesh By Collection Number` を押します。

## 名前の形式
- 初期設定では `001_Roof_A` のように `番号_コレクション名` になります。
- `Prefix` と `Suffix` を指定すると、番号の前またはコレクション名の後ろへ任意の文字を追加できます。
- コレクションはシーンのルート配下を階層順に処理します。

## 主な設定
- `Realize Instances First`: Collection Instanceなどを先に実体化してから処理します。
- `Make Mesh Single User`: 複数Objectに共有されているMeshをコピーし、Objectごとに個別のMesh名を付けます。
- `Number Empty Collections`: Meshが直接入っていないコレクションにも番号を割り当てます。

## 注意点
- 同じObjectが複数コレクションに所属している場合は、最初に見つかったコレクション名が使われます。
- Geometry Nodes内部のInstanceは、`Realize Instances First` では完全に実体化されない場合があります。
- `Realize Instances First` を有効にすると、シーン内の対象インスタンスを実体化します。必要に応じて実行前にファイルを保存してください。
