# Unreal Bridge Tools 使用書

## 1. このアドオンの目的

**Unreal Bridge Tools** は、Blenderで配置したオブジェクトのTransform情報をCSVに書き出し、Unreal Engine側のPCGや配置処理へ渡しやすくするための補助アドオンです。

オブジェクト名にCollision用の `-coll` タグを付けたり、Collection単位で対象を絞ったり、Blenderの自動連番サフィックスを扱いやすくできます。

## 2. インストール方法

### Blender Extensions / Remote Repositoryからインストールする場合

1. Blenderを開く
2. `Edit > Preferences > Get Extensions` を開く
3. Taiyo Blender Scripts のRemote Repositoryを追加、または更新する
4. **Unreal Bridge Tools** を検索してインストールする
5. 3D Viewの右側サイドバーを開く
6. `Unreal Bridge Tools` タブを開く

### ZIPからインストールする場合

1. Blenderを開く
2. `Edit > Preferences > Add-ons` を開く
3. `Install...` を押す
4. `unreal_bridge_tools-2.2.15.zip` を選択
5. Add-on一覧で **Unreal Bridge Tools** を有効化
6. 3D Viewの右側サイドバーを開く
7. `Unreal Bridge Tools` タブを開く

## 3. 基本的な使い方

1. 3D View右側の `N` パネルを開く
2. `Unreal Bridge Tools` タブを開く
3. `Scope` を選ぶ
4. `All Collections` 以外の場合は `Target Collection` を指定する
5. `Export CSV` に保存先を指定する
6. 必要に応じて `Filters`、`Visible Only`、`Name Normalization` を設定する
7. `Test Write` で保存先に書けるか確認する
8. `Export CSV` を押す

## 4. Scope & Export

### Scope

- `Direct Only`: 指定Collection直下のオブジェクトだけを書き出します。
- `Recursive`: 指定Collectionと子Collection内のオブジェクトを書き出します。
- `All Collections`: 現在のView Layer内の全オブジェクトを対象にします。

### Target Collection

`Scope` が `Direct Only` または `Recursive` の場合に使います。

### Export CSV

CSVの保存先です。拡張子が `.csv` でない場合は自動的に `.csv` に補正されます。

### Test Write

指定した保存先に書き込みできるかを確認します。

## 5. Filters

`Filters` では、オブジェクト名に対するInclude / Exclude条件を複数設定できます。

- `Include`: テキストを含む名前だけを対象にします。
- `Exclude`: テキストを含む名前を対象外にします。
- `Case Sensitive`: 大文字と小文字を区別します。
- `Visible Only`: Viewportで表示されているオブジェクトだけを対象にします。

Exclude条件はInclude条件より優先されます。

## 6. Collision Tag

### Add -coll

選択中オブジェクト名に `-coll` を追加します。すでに `-coll` が含まれる場合は重複しないように整理します。

### Remove -coll

選択中オブジェクト名から `-coll` を削除します。

### Select With -coll

対象範囲内で、名前に `-coll` を含むオブジェクトを選択します。

### Select Without -coll

対象範囲内で、名前に `-coll` を含まないオブジェクトを選択します。

## 7. Name Normalization

### Keep Raw (No Change)

Blender上のオブジェクト名をそのまま出力します。

### Remove Numeric Suffix (.001+)

末尾の `.001` など、Blenderの自動連番だけを削除して出力します。

### Trim After Dot

最初の `.` 以降を削除して出力します。

## 8. 出力CSV形式

CSVには以下の列が出力されます。

```text
id,tx,ty,tz,rx,ry,rz,sx,sy,sz,objname,colname
```

- `id`: 連番
- `tx / ty / tz`: World Location
- `rx / ry / rz`: World Rotation、degree
- `sx / sy / sz`: World Scale
- `objname`: Name Normalization後のオブジェクト名
- `colname`: オブジェクトが直接所属する最初のCollection名

## 9. 注意点

- `Scope` が `All Collections` 以外のときは、必ず `Target Collection` を指定してください。
- 書き出し先フォルダを作成できない場合、一時フォルダへフォールバックします。
- `Visible Only` がONの場合、Viewportで非表示のオブジェクトはCSVに出ません。
- 大量処理前に `.blend` を保存しておくと、名前変更やタグ付けを戻しやすくなります。
