# Reimport Selected Meshes 使用書

対象バージョン: **1.0.0**

選択したMeshを元のFBXから再インポートし、そのMeshを使っている全Object(リンク複製を含む)を、新しいMeshへ一括で入れ替えます。UnrealのContent Browserの「Reimport」に近い操作です。

## 基本情報

| 項目 | 内容 |
|---|---|
| ID | `reimport_selected_meshes` |
| バージョン | 1.0.0 |
| 対応Blender | 4.5.9以上 |
| 場所 | 3D Viewport > サイドバー(N) > `Reimport` タブ |

## できること

- 選択したMesh Objectの**Meshデータ**ごとに、元のFBXを探して読み込みます。同じMeshを共有するObjectは1回だけ処理し、**全Objectが同時に新しいMeshになります**(Mesh名もそのまま)。
- FBXの置き場所はフォルダで指定します。見つからないMeshがあるときは、ファイルダイアログでFBXを選びます。
- 1つのFBXに複数のメッシュが入っていても、名前が合うものを探して入れ替えます。FBXにメッシュが1つだけで、それを使う選択Meshも1つなら、名前が違っても入れ替えます。

## 使い方

1. サイドバーの `Reimport` タブで **FBX Folder** にFBXを置いたフォルダを指定します(サブフォルダも探します)。
2. 3D Viewportで、再インポートしたいMesh Objectを選びます。
3. **Reimport Selected Meshes** を押します。
4. 元のFBXが見つからないMeshがあれば、ファイルダイアログが開きます。FBXを選ぶと、見つからなかったMesh全部に対して使います。ダイアログをキャンセルすると何も変わりません。

### 元のFBXの決まり方

Meshごとに、次の順で探します。

1. Meshに記録された元FBX(`rsm_src_fbx`。Map Roundtrip Toolsの`mrt_src_fbx`も読みます)。ファイルが存在するもの。
2. FBX Folder内で、ファイル名(`.fbx`を除く)がMesh名、使っているObject名、記録されたFBXのファイル名と一致するもの(大小文字と`.001`は無視)。同じ名前のFBXが複数あるときは、どれか決められないので警告してダイアログへ回します。
3. どちらも無ければダイアログ。

**Prefer Folder** をONにすると、1と2の順番が入れ替わります(フォルダ内のFBXを優先)。

一度入れ替えたMeshには使ったFBXのパスが記録されるので、次からは選んで押すだけです。

## 設定

| 設定 | 既定 | 内容 |
|---|---|---|
| FBX Folder | 空 | 元FBXを探すフォルダ |
| Search Subfolders | ON | サブフォルダも探す |
| Prefer Folder | OFF | フォルダ内のFBXを、Meshに記録されたFBXより優先する |
| Bake FBX Transform | ON | FBX Objectの変換(親を含む)をMeshデータへ焼き込む。Houdini FBXのように回転X 90度・スケール0.01が付くFBXを、Blenderの向きと大きさに合わせます |
| Keep Existing Materials | ON | FBXのマテリアルと同名(`.001`を除く)のマテリアルが既にあれば、それを使う(`Material.001`が増えない) |
| Vertex Colors as Linear | ON | 頂点カラーをLinearで読み込む |

**Bake FBX Transform はMap Roundtrip Tools(既定OFF)と違い、既定でONです。** すでにBlenderと同じ向き・大きさのFBXなら、変換が無いので結果は変わりません。設定が合っていないと、全リンクが100倍や0.01倍になります。そのため、新旧のMeshの大きさが0.5〜2倍の範囲を外れたときは警告を出します。

## 注意

- Meshデータ全体が新しいMeshに置き換わります。旧Meshだけにあった頂点カラー・UV・マテリアルスロット・シェイプキー・頂点グループのウェイトは失われます。Object側のモディファイアやマテリアルのObjectリンクは残ります。
- Meshのカスタムプロパティは新Meshへ引き継ぎます。
- 他のBlendファイルからリンクしているMeshは対象外です(警告して飛ばします)。
- Object Modeでのみ使えます。
- Undo(Ctrl+Z)で1回分を元に戻せます。失敗したときは、取り込んだデータを削除して元の状態に戻します。
- 見つからなかったMesh・FBXに名前が合わなかったMesh・サイズ警告は、画面下のレポートに出ます。

## テスト

```sh
blender --background --factory-startup --python-exit-code 1 --python tools/test_reimport_selected_meshes.py
```
