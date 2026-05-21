# インスタンスヘルパー / UVチャンネル配置ツール 完全使用書 v2.6

対象ファイル：`インスタンスヘルパー_UVチャンネル配置ツール_v2_6_修正版.py`  
元ファイル：`UVMatSlots_Ver2.6.py`  
アドオン名：`UV Channel Placement Tool`  
対応想定：Blender 4.4 以降

---

## 1. このアドオンの目的

このアドオンは、Blender上で **指定したUVマップのUVを、8個の決まったスロット位置へ移動するためのツール** です。

主な用途は、次のような「UVの位置をID情報として使う」ワークフローです。

- マテリアルID用のUVチャンネルを作る
- 特定の面・パーツを、Slot 0〜Slot 7 のどれかに割り当てる
- 選択した面だけを手動で特定スロットへ送る
- メッシュ島ごとにランダムでスロットを割り当てる
- 8種類のID、色、質感、マスク、分類情報をUV位置で管理する

通常のUV展開をきれいに作るためのツールではありません。  
このアドオンは、UVを非常に小さく縮小し、決まった座標へ集めることで、**「この面はどのIDに属するか」** をUVチャンネル上で管理するための補助ツールです。

---

## 2. どこに表示されるか

インストール後、Blenderの3Dビューポート右側サイドバーに表示されます。

```text
3D Viewport
└─ Sidebar / Nキー
   └─ UV Tools
      └─ UV Channel Placement Tool
```

3Dビューポートで `N` キーを押し、右側サイドバーを開きます。  
その中の `UV Tools` タブに `UV Channel Placement Tool` パネルが表示されます。

---

## 3. インストール方法

1. Blenderを起動します。
2. 上部メニューから `Edit > Preferences` を開きます。
3. 左メニューの `Add-ons` を開きます。
4. 右上付近の `Install...` または `Install from Disk...` を押します。
5. `インスタンスヘルパー_UVチャンネル配置ツール_v2_6_修正版.py` を選択します。
6. アドオン一覧に表示された `UV Channel Placement Tool` にチェックを入れて有効化します。
7. 3Dビューポートで `N` キーを押し、`UV Tools` タブを確認します。

---

## 4. 使用前に必ず理解すること

### 4.1 UV Map Index は 0始まり

`UV Map Index` は、BlenderのUVマップ番号を指定する項目です。  
番号は **0始まり** です。

| UV Map Index | 意味 |
|---:|---|
| 0 | 1番目のUVマップ |
| 1 | 2番目のUVマップ |
| 2 | 3番目のUVマップ |
| 3 | 4番目のUVマップ |

デフォルト設定では、Manual側が `2`、Random側が `3` になっています。  
つまり、初期状態のまま使う場合は、対象メッシュに最低でも次の数のUVマップが必要です。

| 機能 | デフォルトIndex | 必要なUVマップ数 |
|---|---:|---:|
| Manual Slot Placement | 2 | 3個以上 |
| Random Placement | 3 | 4個以上 |

UVマップ数が足りない場合、`UV index not found` というエラーが出ます。

### 4.2 Edit Modeで使う

このアドオンは、メッシュの編集データにアクセスしてUVを移動します。  
基本的には、対象メッシュを選択して **Edit Mode** に入ってから使用してください。

Manual Slot Placementでは、選択されている面だけが処理対象です。  
Random Placementでは、メッシュ内の接続された面グループが処理対象です。

### 4.3 UVを小さく縮小してスロットへ移動する

このアドオンは、UVを元の形のまま大きく移動するのではなく、UVを非常に小さく縮小して、スロットの中心付近へ集めます。

そのため、通常のテクスチャ用UVとしてではなく、ID管理・マスク管理用のUVチャンネルとして使うのが適しています。

---

## 5. パネル全体の構成

パネルは大きく3つの部分に分かれています。

```text
UV Channel Placement Tool

[Preset]
[Name]
[Add Current] [Remove]

Manual Slot Placement
  UV Map Index
  UV Map Name
  Slot 0  [Label]
  Slot 1  [Label]
  ...
  Slot 7  [Label]

Random Placement
  UV Map Index
  UV Map Name
  Place All Islands Randomly
```

---

## 6. Preset エリアの使い方

Presetエリアは、Slot 0〜Slot 7 に入力したラベル名を保存・切り替えするための機能です。

重要：プリセットに保存されるのは **各スロットのラベル名だけ** です。  
UV Map Index、UV Map Name、実際のUV配置結果は保存されません。

### 6.1 Preset

保存済みプリセットを選択するドロップダウンです。

プリセットを選ぶと、Manual Slot Placement内のSlot 0〜Slot 7 のラベルが、そのプリセット内容に切り替わります。

### 6.2 ▶ ボタン

次のプリセットへ順番に切り替えるボタンです。

複数のプリセットを登録している場合、押すたびに次のプリセットへ移動します。  
最後のプリセットの次は、最初のプリセットに戻ります。

### 6.3 Name

新しくプリセットを保存するときの名前を入力する欄です。

例：

```text
Building_ID
Character_Parts
Material_Group
Damage_Mask
```

### 6.4 Add Current

現在のSlot 0〜Slot 7 のラベル名を、Name欄の名前でプリセットとして保存します。

使用例：

1. Slot 0〜Slot 7 のラベルに意味のある名前を入力します。
2. Name欄にプリセット名を入力します。
3. `Add Current` を押します。
4. Presetドロップダウンに登録されます。

### 6.5 Remove

現在選択しているプリセットを削除します。

削除されるのはプリセット情報だけです。  
すでに移動済みのUV配置には影響しません。

---

## 7. Manual Slot Placement の使い方

Manual Slot Placementは、**選択した面のUVを、指定したSlotへ手動で移動する機能** です。

### 7.1 UV Map Index

処理対象にするUVマップ番号を指定します。

例：

| 入力値 | 対象 |
|---:|---|
| 0 | 1番目のUVマップ |
| 1 | 2番目のUVマップ |
| 2 | 3番目のUVマップ |

デフォルトは `2` です。  
これは3番目のUVマップを使う設定です。

### 7.2 UV Map Name

指定したUVマップの名前を変更する欄です。

デフォルトは `ID` です。

Manual Slot Placementを実行すると、指定したIndexのUVマップ名が、この欄の名前に変更されます。

例：

```text
ID
MaterialID
MaskID
PartID
```

### 7.3 Slot 0〜Slot 7 ボタン

選択中の面を、対応するスロットへ移動します。

| ボタン | 処理内容 |
|---|---|
| Slot 0 | 選択面のUVをSlot 0へ移動 |
| Slot 1 | 選択面のUVをSlot 1へ移動 |
| Slot 2 | 選択面のUVをSlot 2へ移動 |
| Slot 3 | 選択面のUVをSlot 3へ移動 |
| Slot 4 | 選択面のUVをSlot 4へ移動 |
| Slot 5 | 選択面のUVをSlot 5へ移動 |
| Slot 6 | 選択面のUVをSlot 6へ移動 |
| Slot 7 | 選択面のUVをSlot 7へ移動 |

### 7.4 Slot横のラベル欄

各Slotに名前を付けるための欄です。

このラベルは作業者が意味を忘れないためのメモです。  
実際のUV位置や処理内容には影響しません。

例：

| Slot | ラベル例 |
|---|---|
| Slot 0 | Wall |
| Slot 1 | Floor |
| Slot 2 | Metal |
| Slot 3 | Wood |
| Slot 4 | Glass |
| Slot 5 | Dirt |
| Slot 6 | Damage |
| Slot 7 | Emission |

---

## 8. Random Placement の使い方

Random Placementは、**メッシュ内の接続された面グループをランダムにSlot 0〜Slot 7へ配置する機能** です。

### 8.1 UV Map Index

Random Placementで処理するUVマップ番号を指定します。

デフォルトは `3` です。  
これは4番目のUVマップを使う設定です。

### 8.2 UV Map Name

指定したUVマップの名前を変更する欄です。

デフォルトは `ID` です。

### 8.3 Place All Islands Randomly

メッシュ内の接続された面グループを検出し、それぞれをSlot 0〜Slot 7 のどれかへランダムに移動します。

注意：この機能でいうIslandは、UVエディタ上のUVアイランドではなく、コード上では **エッジで接続されたメッシュの面グループ** として扱われます。

完全に分離したメッシュパーツが複数ある場合、それぞれが別のグループとしてランダム配置されます。

---

## 9. 実際の使用手順：手動でSlotに割り当てる

ここでは、選択した面をSlotへ手動配置する基本手順を説明します。

### 手順

1. Blenderで対象メッシュを選択します。
2. Object Data Propertiesで、必要なUVマップを用意します。
   - Manualのデフォルト `UV Map Index = 2` を使う場合、UVマップは3個以上必要です。
3. 対象メッシュを `Edit Mode` にします。
4. Face Selectモードにします。
5. Slotへ割り当てたい面を選択します。
6. 3Dビューポート右側の `UV Tools` タブを開きます。
7. `Manual Slot Placement` の `UV Map Index` を確認します。
8. `UV Map Name` を必要に応じて `ID` や `MaterialID` などにします。
9. 使いたいSlotの横にラベルを入力します。
10. 選択した面に対応する `Slot 0〜Slot 7` ボタンを押します。
11. 選択面のUVが、そのSlotの位置へ移動します。

### 作業例

```text
Slot 0 = Wall
Slot 1 = Floor
Slot 2 = Metal
Slot 3 = Wood
```

壁の面を選択して `Slot 0` を押す。  
床の面を選択して `Slot 1` を押す。  
金属パーツを選択して `Slot 2` を押す。

このように、面ごとにID用UV位置を割り当てます。

---

## 10. 実際の使用手順：ランダムにSlotへ割り当てる

ここでは、メッシュ島ごとにランダムでSlotを割り当てる手順を説明します。

### 手順

1. Blenderで対象メッシュを選択します。
2. Object Data Propertiesで、必要なUVマップを用意します。
   - Randomのデフォルト `UV Map Index = 3` を使う場合、UVマップは4個以上必要です。
3. 対象メッシュを `Edit Mode` にします。
4. `UV Tools` タブを開きます。
5. `Random Placement` の `UV Map Index` を確認します。
6. `UV Map Name` を必要に応じて設定します。
7. `Place All Islands Randomly` を押します。
8. メッシュの接続グループごとに、Slot 0〜Slot 7 のどこかへランダムにUVが配置されます。

### 向いている用途

- 大量の分離パーツにランダムIDを付けたい
- 建物の破片、岩、瓦礫、装飾パーツなどをランダム分類したい
- 手作業で1つずつSlotを押すのが大変な場合

---

## 11. プリセットを使ったおすすめ運用

ラベル名を毎回入力すると作業効率が落ちるため、よく使う分類はプリセット化するのがおすすめです。

### 例：建物用プリセット

```text
Preset Name: Building_Material_ID
Slot 0: Wall
Slot 1: Floor
Slot 2: Roof
Slot 3: Wood
Slot 4: Metal
Slot 5: Glass
Slot 6: Dirt
Slot 7: Damage
```

### 例：キャラクターパーツ用プリセット

```text
Preset Name: Character_Parts_ID
Slot 0: Skin
Slot 1: Hair
Slot 2: Cloth
Slot 3: Leather
Slot 4: Metal
Slot 5: Eye
Slot 6: Accessory
Slot 7: Effect
```

### 例：マスク管理用プリセット

```text
Preset Name: Mask_Control_ID
Slot 0: Base
Slot 1: EdgeWear
Slot 2: Dirt
Slot 3: Rust
Slot 4: Wet
Slot 5: Emission
Slot 6: Damage
Slot 7: Custom
```

---

## 12. よくあるエラーと対処法

### 12.1 `No mesh object selected`

原因：メッシュオブジェクトが選択されていません。

対処：対象のMeshオブジェクトを選択してください。

### 12.2 `UV index 2 not found` / `UV index 3 not found`

原因：指定したUV Map Indexに対応するUVマップが存在しません。

対処：

- UV Map Indexを存在する番号に変更する
- または、Object Data PropertiesでUVマップを追加する

例：`UV Map Index = 2` を使うなら、UVマップが3個以上必要です。

### 12.3 ボタンを押しても想定した面が動かない

原因候補：

- Edit Modeではない
- Face Selectで面を選択していない
- 違うUV Map Indexを指定している
- 見ているUVマップと、処理しているUVマップが違う

対処：

1. 対象オブジェクトがEdit Modeになっているか確認します。
2. 面が選択されているか確認します。
3. UV Map Indexが正しいか確認します。
4. UVエディタで表示しているUVマップを確認します。

### 12.4 Presetに保存したのにUV配置が戻らない

仕様です。  
PresetはSlotラベルだけを保存します。

UV配置結果そのもの、UV Map Index、UV Map Nameは保存されません。

### 12.5 Random Placementで思った単位に分かれない

このアドオンのRandom Placementは、UVアイランドではなく、エッジで接続されたメッシュ面グループをIslandとして扱います。

UVエディタ上では別アイランドでも、メッシュとしてつながっている場合は同じグループとして処理される可能性があります。

---

## 13. おすすめの命名ルール

後から見返したときに混乱しないように、ファイル名とUV名は役割が分かる名前にしておくのがおすすめです。

### アドオンファイル名

```text
インスタンスヘルパー_UVチャンネル配置ツール_v2_6_修正版.py
```

### 使用書ファイル名

```text
インスタンスヘルパー_UVチャンネル配置ツール_完全使用書_v2_6.md
```

### UVマップ名

```text
ID
MaterialID
PartID
MaskID
RandomID
```

### プリセット名

```text
Building_Material_ID
Character_Parts_ID
Mask_Control_ID
```

---

## 14. 最短使用フローまとめ

### 手動配置したい場合

```text
1. メッシュを選択
2. UVマップを必要数作成
3. Edit Modeに入る
4. Face Selectで面を選択
5. UV Tools > UV Channel Placement Tool を開く
6. Manual Slot PlacementのUV Map Indexを確認
7. Slot名を入力
8. 対応するSlotボタンを押す
```

### ランダム配置したい場合

```text
1. メッシュを選択
2. UVマップを必要数作成
3. Edit Modeに入る
4. UV Tools > UV Channel Placement Tool を開く
5. Random PlacementのUV Map Indexを確認
6. Place All Islands Randomlyを押す
```

### プリセットを作りたい場合

```text
1. Slot 0〜Slot 7のラベルを入力
2. Nameにプリセット名を入力
3. Add Currentを押す
4. 次回からPreset欄で選択する
```

---

## 15. 最後に：このアドオンを使うときの考え方

このアドオンは、通常のUV展開を作るためのものではなく、**追加UVチャンネルを使ってID・分類・マスク情報を持たせるための作業補助ツール** です。

基本の考え方は次の通りです。

```text
面やパーツを選ぶ
↓
どのSlotに属するか決める
↓
そのSlotボタンを押す
↓
指定UVチャンネル上で、ID用の位置にUVが移動する
```

この流れを使うことで、マテリアル、シェーダー、外部ツール、ゲームエンジン側で、UV位置を使った分類処理を行いやすくなります。
