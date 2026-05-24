# Overlap Object Selector v1.2.1 使用書

## 1. このアドオンの目的

**Overlap Object Selector** は、Blenderシーン内で同じ位置に重なっているオブジェクトを検出し、結果を確認しながら安全に選択するためのアドオンです。

大量のオブジェクトがあるシーンで、重複配置・同位置コピー・不要なブロッカーなどを探す用途を想定しています。

v1.2.1では、長い結果リストをそのまま全部表示する方式から、**グループ一覧をクリックして、選んだグループの中身だけを見るUI** に変更しています。さらに、**グループ行・オブジェクト行をクリックした瞬間にBlender上でも選択されるUX** と、**個別オブジェクト削除ボタン** を追加しています。

---

## 2. インストール方法

### Blender Extensions / Remote Repositoryからインストールする場合

1. Blenderを開く
2. `Edit > Preferences > Get Extensions` を開く
3. Taiyo Blender Scripts のRemote Repositoryを追加、または更新する
4. **Overlap Object Selector** を検索してインストールする
5. 3D Viewの右側サイドバーを開く
6. `Overlap` タブを開く

### ZIPからインストールする場合

1. Blenderを開く
2. `Edit > Preferences > Add-ons` を開く
3. `Install...` を押す
4. `overlap_selector-1.2.2.zip` を選択
5. Add-on一覧で **Overlap Object Selector** を有効化
6. 3D Viewの右側サイドバーを開く
7. `Overlap` タブを開く

### Pythonファイルから実行する場合

1. Blenderの `Text Editor` を開く
2. `__init__.py` を開く、または中身を貼り付ける
3. `Run Script` を実行
4. 3D Viewの右側サイドバーに `Overlap` タブが表示されます

古いバージョンをText Editorで直接実行している場合は、古い `overlap_selector.py` / `overlap_selector.py.002` が残っていないか確認してください。

---

## 3. 基本的な使い方

1. 3D View右側の `N` パネルを開く
2. `Overlap` タブを開く
3. 必要に応じて `Detect Settings` を設定する
4. `Detect Overlaps` を押す
5. 検出が終わると、重なっているオブジェクトが **Overlap Groups** に表示される
6. 上のグループリストから確認したいグループをクリックする
7. クリックしたグループ内のオブジェクトがBlender上でも自動選択される
8. 下の `Objects in Selected Group` に、そのグループ内のオブジェクトだけが表示される
9. オブジェクト行をクリックすると、その1つだけがBlender上で自動選択される

---

## 4. Detect Settings

### Include Hidden Objects

ONにすると、Viewportで非表示になっているオブジェクトも検出対象になります。

通常はOFFで問題ありません。非表示オブジェクトも含めて完全に調べたい場合だけONにしてください。

### Match Scale

ONにすると、位置だけでなくスケールも一致しているオブジェクトだけを同じグループにします。

### Match Rotation

ONにすると、位置だけでなく回転も一致しているオブジェクトだけを同じグループにします。

### Show Collection Names

ONにすると、選択中のオブジェクト詳細欄に、そのオブジェクトが所属しているCollection名を表示します。

---

## 5. Collection Filter / Bulk Select

v1.2.0で追加された機能です。

指定したCollectionに入っているオブジェクトを、検出結果の中からまとめて選択できます。

### 使い方

1. `Collection Filter / Bulk Select` の `Collection` 欄にCollection名を入力する
2. 必要に応じて `Exact` / `Case` を設定する
3. `Select Matches` を押す
4. 検出結果内で、そのCollectionに所属しているオブジェクトだけがBlender上で選択される
5. 実際に削除したい場合は、Blender標準の `X` / `Delete` で削除する

### Exact

ONの場合、入力したCollection名と完全一致したものだけを対象にします。

例：

```text
BLOCKER
```

と入力した場合、`BLOCKER` というCollectionだけが対象です。

OFFの場合、部分一致になります。

例：

```text
BLOCK
```

と入力した場合、`BLOCKER_A` や `BLOCKER_TEST` も対象になります。

### Case

ONにすると、大文字と小文字を区別します。

通常はOFFで問題ありません。

### Select Matches

検出結果の中から、指定したCollectionに所属しているオブジェクトをまとめて選択します。

注意：このボタンは削除しません。選択だけです。

### Check Matches

検出結果リスト上で、指定したCollectionに所属している項目にチェックを入れます。

その後、選択中グループの `Remove Checked From List` を使うと、リストから不要な項目だけを外せます。

注意：`Remove Checked From List` はBlender上の実オブジェクトを削除しません。検出結果リストから外すだけです。

---

## 6. Overlap Groups の使い方

`Overlap Groups` には、重なっているオブジェクトのグループが一覧表示されます。

各行には以下が表示されます。

- Group番号
- グループ内のオブジェクト数
- 重なっている位置のXYZ

クリックしたグループだけが、下の詳細欄に表示されます。

また、v1.2.1以降では、グループ行をクリックした時点で、そのグループ内のオブジェクトがBlender上でも自動選択されます。

これにより、巨大なグループがあっても、全グループを縦に展開する必要がなくなります。

---

## 7. Selected Group の操作

### Select Group

現在選んでいるグループ内のオブジェクトをまとめて選択します。

ただし、現在のView Layerに存在しないオブジェクトは選択できません。その場合は自動でスキップされます。

### Check Group

現在選んでいるグループ内の全項目にチェックを入れます。

### None

現在選んでいるグループ内のチェックをすべて外します。

### Remove Checked From List

現在選んでいるグループ内で、チェックが入っている項目を検出結果リストから外します。

これはBlender上のオブジェクト削除ではありません。

---

## 8. Objects in Selected Group の使い方

`Objects in Selected Group` には、現在選択しているグループ内のオブジェクトが表示されます。

左側のチェックボックスで、個別に対象を選べます。

リストでオブジェクトをクリックすると、下の `Selected Object Entry` に詳細が表示されます。

v1.2.1以降では、オブジェクト行をクリックした時点で、その1つのオブジェクトがBlender上でも自動選択されます。

---

## 9. Selected Object Entry の操作

### Select This Object

現在リストで選んでいる1つのオブジェクトだけをBlender上で選択します。

### Remove Entry From List

現在リストで選んでいる1つの項目を、検出結果リストから外します。

これは実オブジェクト削除ではありません。

### Delete This Blender Object

現在リストで選んでいる1つのBlenderオブジェクトを、シーンから実際に削除します。

このボタンは `Undo` 対応です。間違えた場合は、Blender標準の `Ctrl + Z` で戻してください。

削除後、そのグループ内の残りオブジェクト数が1個以下になった場合、そのグループは重なりグループではなくなるため、結果リストから自動で非表示になります。

---

## 10. View Layerに関する注意

Blenderでは、オブジェクトがシーン内に存在していても、現在のView Layerに入っていない場合があります。

その場合、Blenderはそのオブジェクトを選択できません。

以前のバージョンでは、以下のようなエラーが出る場合がありました。

```text
Object 'BLOCKER2' can't be selected because it is not in View Layer 'ViewLayer'
```

v1.1.0以降では、現在のView Layerにないオブジェクトは自動でスキップされます。

---

## 11. 安全設計について

このアドオンでは、`Remove` と `Delete` を明確に分けています。

`Remove Entry From List` / `Remove Checked From List` は、検出結果リストから外すだけです。Blender上の実オブジェクトは削除しません。

`Delete This Blender Object` は、Blender上の実オブジェクトをシーンから削除します。確認ダイアログが出るため、削除してよい場合だけ実行してください。

複数オブジェクトをまとめて削除したい場合は、

1. `Select Group` / グループ行クリック / `Select Matches` で対象を選択
2. Blender標準の `X` / `Delete` で削除

という流れが安全です。

---

## 12. v1.2.1 の主な変更点

- グループ行をクリックすると、そのグループ内のオブジェクトがBlender上でも自動選択されるように変更
- オブジェクト行をクリックすると、そのオブジェクト1つだけがBlender上でも自動選択されるように変更
- `Selected Object Entry` に `Delete This Blender Object` を追加
- 実オブジェクト削除後、グループ内の残りオブジェクト数が1個以下になった場合、そのグループを自動で非表示に変更
- `Remove` はリストから外すだけ、`Delete` は実オブジェクト削除、という役割を明確化
- v1.2.0の `Collection Filter / Bulk Select` とクリック式グループUIは維持
