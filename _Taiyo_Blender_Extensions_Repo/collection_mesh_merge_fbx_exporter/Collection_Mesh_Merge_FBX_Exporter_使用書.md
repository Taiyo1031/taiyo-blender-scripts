# Collection Mesh Merge FBX Exporter v0.2 使用書

## 1. このアドオンの目的

このアドオンは、Blender内のコレクションを対象にして、**コレクションごとに1つのFBXを書き出す**ためのツールです。

想定しているワークフローは以下です。

```text
アセット制作用Blenderファイル
  └─ アセットをコレクション単位で管理
  └─ Asset Browserにコレクションを登録
  └─ このアドオンでコレクションごとにFBX化

レベルデザイン用Blenderファイル / Unreal Engine
  └─ 書き出したFBXを利用
```

各対象コレクションの中にある複数メッシュを、一時的に1つのメッシュへ統合し、コレクション名と同じ名前でFBXを書き出します。

例：

```text
Collection: SM_School_Desk_A
  ├─ Desk_Top
  ├─ Desk_Leg_01
  ├─ Desk_Leg_02
  └─ Desk_Drawer

Export Result:
  SM_School_Desk_A.fbx
```

---

## 2. 重要な特徴

このアドオンは、元のBlenderデータを壊さないことを重視しています。

- 元のオブジェクトは結合しません。
- 元のコレクション構造は変更しません。
- 元のモディファイヤーは変更しません。
- 元のマテリアルは削除しません。
- 書き出し後、Blendファイルは自動保存しません。
- 一時オブジェクトはFBX書き出し後に削除されます。

つまり、実行後は、**FBXだけが出力され、Blenderファイル自体は何も起きていないような状態**を目指します。

---

## 3. インストール方法

1. Blenderを開きます。
2. 上部メニューから `Edit > Preferences` を開きます。
3. `Add-ons` を選びます。
4. `Install...` を押します。
5. `collection_mesh_merge_fbx_exporter_v02.py` を選択します。
6. インストールされたアドオンにチェックを入れて有効化します。
7. 3D Viewportの右側サイドバーを開きます。
8. `CMFE` タブを開きます。

---

## 4. 基本的な使い方

一番基本的な手順は以下です。

```text
1. Export Folderを指定する
2. Search Root Collectionを指定する
3. 必要に応じて設定を確認する
4. Refresh Previewを押す
5. Previewで書き出し予定数を確認する
6. Export FBXを押す
```

`Export FBX` ボタンは折りたたみセクションの外にあり、常に見えるようになっています。

---

## 5. UIの説明

## 5.1 Export Target

### Export Folder

FBXを書き出すフォルダです。

ここに、対象コレクションごとのFBXがまとめて出力されます。

例：

```text
D:/Project/Exports/FBX/
```

### Search Root Collection

どのコレクションの中を検索するかを指定します。

このコレクションの中にある子コレクション・孫コレクションを再帰的に調べます。

例：

```text
Asset_Collections
  ├─ SM_Desk_A
  ├─ SM_Chair_A
  └─ Props
      ├─ SM_Book_A
      └─ SM_Pencil_A
```

`Search Root Collection` に `Asset_Collections` を指定すると、その中にあるコレクションが書き出し候補になります。

### Include Root Collection as Target

指定した親コレクション自体も書き出し候補に含めるかどうかです。

基本的にはONで問題ありません。

---

## 5.2 Filter

どのコレクションをFBX書き出し対象にするかを決めます。

### Filter Mode

#### Asset Browser Registered

デフォルト設定です。

Asset Browserに登録されているコレクションだけを書き出します。

おすすめの使い方です。

```text
Asset登録あり → 書き出す
Asset登録なし → スキップ
```

#### Name Contains Filter

コレクション名に指定した文字列が含まれるものだけを書き出します。

例：

```text
Name Filter: SM_
```

この場合：

```text
SM_Desk_A      → 書き出す
SM_Chair_A     → 書き出す
Test_Blockout  → スキップ
```

#### Asset AND Name

Asset Browserに登録されていて、さらに名前条件にも一致するコレクションだけを書き出します。

#### Asset OR Name

Asset Browserに登録されている、または名前条件に一致するコレクションを書き出します。

### Nested Target Rule

親子コレクションの両方が書き出し条件に一致した場合のルールです。

#### Export All Matching Collections

一致したコレクションをすべて書き出します。

#### Export Only Leaf Matching Collections

親と子の両方が一致する場合、より下の階層の子コレクションだけを書き出します。

重複書き出しを避けたい場合におすすめです。

#### Parent Ignores Children

親コレクションが一致した場合、その子コレクションは別FBXとしては書き出しません。

大きなセット単位で書き出したい場合に便利です。

---

## 5.3 Mesh Processing

### Include Nested Meshes in Each Target

対象コレクションを書き出す時、その中の子コレクションに入っているメッシュも含めるかどうかです。

通常はON推奨です。

### Include Hidden Objects

非表示オブジェクトを含めるかどうかです。

デフォルトはONです。

ONの場合：

```text
Viewportで非表示のオブジェクトも含める
Renderで非表示のオブジェクトも含める
```

OFFの場合：

```text
非表示オブジェクトはスキップ
```

### Include Collection Instances

Collection Instanceを含めるかどうかです。

デフォルトはOFFです。

ONにすると、Collection Instance内のメッシュも実体化に近い形で書き出し対象にします。ただし、この機能は実験的です。

最初はOFF推奨です。

### Apply Modifiers Before Export

モディファイヤーを評価した状態で書き出すかどうかです。

ONの場合、以下のようなモディファイヤーを反映したメッシュを書き出します。

```text
Bevel
Mirror
Array
Solidify
Subdivision Surface
Geometry Nodes
Weighted Normal
```

元のオブジェクトのモディファイヤー自体は変更されません。

### Keep Material Slots

マテリアルスロットをFBXに含めるかどうかです。

ONの場合、元メッシュのマテリアルスロットを統合後メッシュに引き継ぎます。

OFFの場合、マテリアルスロットを持たないシンプルなメッシュとして書き出します。

---

## 5.4 Export / Performance

### Overwrite Existing FBX

同名のFBXがすでにある場合に上書きするかどうかです。

デフォルトはONです。

### Skip Empty Collections

メッシュが1つもないコレクションをスキップします。

通常はON推奨です。

### Objects per Tick

一度に処理するメッシュ数です。

大量オブジェクトでBlenderが固まりやすい場合は、小さくしてください。

おすすめ目安：

```text
軽いシーン: 50〜100
普通のシーン: 20
重いシーン: 5〜10
```

この値を小さくすると処理時間は伸びますが、UIが固まりにくくなります。

### Preview Sample Count

Previewに表示するサンプル行数です。

すべてのコレクションを一覧表示するとUIが重くなるため、数件だけ表示します。

---

## 5.5 Main Actions

このセクションは折りたたみではありません。

常に表示されます。

### Refresh Preview

現在の設定で、どのくらいのコレクション・メッシュが書き出される予定かを確認します。

表示される内容：

```text
書き出し予定コレクション数
書き出し予定メッシュ数
残りオブジェクト数
サンプルプレビュー
```

### Export FBX

実際にFBXを書き出します。

対象コレクションごとに、1つずつFBXが作られます。

### Cancel Export

書き出し中だけ表示されます。

押すと、現在のTick処理が終わった後にキャンセルします。

---

## 6. 書き出し仕様

## 6.1 1コレクション = 1FBX

対象コレクションごとに1つのFBXを出力します。

```text
SM_Desk_A    → SM_Desk_A.fbx
SM_Chair_A   → SM_Chair_A.fbx
SM_Window_A  → SM_Window_A.fbx
```

## 6.2 FBX名

FBX名は、基本的にコレクション名と同じです。

ファイル名に使えない文字は、自動的に `_` に置き換えられます。

例：

```text
SM:Desk/A
→ SM_Desk_A.fbx
```

## 6.3 Origin

OriginはWorld原点です。

```text
X: 0
Y: 0
Z: 0
```

## 6.4 Transform

元オブジェクトのLocation / Rotation / Scaleは、メッシュ頂点に焼き込まれます。

そのため、見た目の配置を維持したまま、1つのメッシュとして書き出します。

---

## 7. プログレス表示

大量オブジェクトでも1回で処理せず、`Objects per Tick` の数ごとに分けて処理します。

書き出し中は以下を表示します。

```text
Progress Bar
Current Collection
Remaining Objects
Status
```

注意：

FBXを書き出す瞬間だけは、BlenderのFBX Export処理が走るため、一時的に止まったように見える場合があります。

---

## 8. おすすめ設定

まずは以下の設定がおすすめです。

```text
Filter Mode: Asset Browser Registered
Nested Target Rule: Export Only Leaf Matching Collections
Include Root Collection as Target: ON
Include Nested Meshes in Each Target: ON
Include Hidden Objects: ON
Include Collection Instances: OFF
Apply Modifiers Before Export: ON
Keep Material Slots: ON
Overwrite Existing FBX: ON
Skip Empty Collections: ON
Objects per Tick: 20
Preview Sample Count: 8
```

重い場合：

```text
Objects per Tick: 5〜10
```

---

## 9. よくあるトラブル

## 9.1 Previewに何も出ない

確認すること：

```text
Search Root Collectionが指定されているか
対象コレクションがAsset Browserに登録されているか
Filter Modeが意図したものになっているか
対象コレクション内にMeshがあるか
```

## 9.2 書き出されたFBXがない

確認すること：

```text
Export Folderが正しいか
同名FBXがあり、Overwrite Existing FBXがOFFになっていないか
Skip Empty Collectionsでスキップされていないか
```

## 9.3 Blenderが重い

`Objects per Tick` を小さくしてください。

```text
20 → 10 → 5
```

## 9.4 Collection Instanceが入らない

`Include Collection Instances` をONにしてください。

ただし、Collection Instance対応は実験的なので、まずは通常のMesh Objectで確認することをおすすめします。

## 9.5 元ファイルが変わらないか不安

このアドオンは一時的なメッシュと一時コレクションを作り、書き出し後に削除します。

Blendファイルの自動保存は行いません。

それでも初回は必ずテスト用の複製ファイルで確認してください。

---

## 10. 初回テストのおすすめ手順

いきなり本番データで使わず、まずは小さいテストで確認してください。

```text
1. テスト用Blendファイルを作る
2. Asset_TestRoot という親コレクションを作る
3. その中に SM_Test_A と SM_Test_B を作る
4. 各コレクションに2〜3個のMeshを入れる
5. SM_Test_A と SM_Test_B をAsset Browserに登録する
6. Search Root Collectionに Asset_TestRoot を指定する
7. Refresh Previewを押す
8. Export FBXを押す
9. 指定フォルダに SM_Test_A.fbx / SM_Test_B.fbx が出ているか確認する
10. Blender内に一時オブジェクトが残っていないか確認する
```

---

## 11. このバージョンの変更点

v0.2では、以下を調整しています。

```text
Export FBXボタンを折りたたみセクションの外に移動
Main Actionsセクションを常時表示
Previewは折りたたみ可能なまま維持
大量オブジェクト向けの進捗表示を維持
```

---

## 12. 同梱ファイル

```text
collection_mesh_merge_fbx_exporter_v02.py
README_Collection_Mesh_Merge_FBX_Exporter_v02.md
CHANGELOG_v02.md
```
