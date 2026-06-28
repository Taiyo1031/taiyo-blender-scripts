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
4. `unreal_bridge_tools-2.2.19.zip` を選択
5. Add-on一覧で **Unreal Bridge Tools** を有効化
6. 3D Viewの右側サイドバーを開く
7. `Unreal Bridge Tools` タブを開く

## 3. 基本的な使い方

1. 3D View右側の `N` パネルを開く
2. `Unreal Bridge Tools` タブを開く
3. `Scope` を選ぶ
4. `All Collections` 以外の場合は `Target Collection` を指定する
5. `Export CSV` に保存先を指定する
6. 必要に応じて `Filters`、`Visible Only`、`Name Normalization`、`Export Mode` を設定する
7. 必要なら最上部の `Presets` で設定を保存または読み込む
8. `Test Write` で保存先に書けるか確認する
9. `Export CSV` を押す
10. 書き出し中はNパネルのゲージとBlender下部のステータスバーに進捗率と残り時間が出ます。中断したい場合は `Esc` を押します。

## 4. Scope & Export

### Presets

Nパネル最上部の `Presets` では、現在のScope、Target Collection名、Export CSV、Export Mode、Filters、Name Normalization、Visible Only、Case Sensitiveをユーザー設定として保存できます。

- `Load`: 選択中プリセットを現在の設定へ読み込みます。
- `Save`: 選択中プリセットを現在の設定で上書きします。
- `Save As New`: 新しい名前で保存します。
- `Delete`: 選択中プリセットを削除します。
- `Import` / `Export`: プリセットJSONを読み込み・書き出しします。

プリセットはBlenderのユーザー設定領域に保存されるため、Extensionを更新しても維持されます。Target Collectionは名前で保存され、読み込み時に同名Collectionが無い場合は警告し、その他の設定だけ復元します。

### Scope

- `Direct Only`: 指定Collection直下のオブジェクトだけを書き出します。
- `Recursive`: 指定Collectionと子Collection内のオブジェクトを書き出します。
- `All Collections`: 現在のView Layer内の全オブジェクトを対象にします。

### Target Collection

`Scope` が `Direct Only` または `Recursive` の場合に使います。

### Export CSV

CSVの保存先です。拡張子が `.csv` でない場合は自動的に `.csv` に補正されます。

書き出し処理は大量オブジェクトでも進捗が見えるようにtimer tickごとに分割して実行されます。標準の `Fast Locked` は60,000個以上の書き出し向けで、Blender操作をほぼ止め、1tickあたりの処理量を大きくして高速化します。`Responsive` は従来寄りに操作を通しながら小さめのchunkで処理します。

進捗率、残り時間、書き出し件数、処理速度はNパネルのゲージとBlender下部のステータスバーに表示されます。

### Test Write

指定した保存先に書き込みできるかを確認します。

## 5. Filters

`Filters` では、オブジェクト名に対するInclude / Exclude条件を複数設定できます。

- `Include`: テキストを含む名前だけを対象にします。
- `Exclude`: テキストを含む名前を対象外にします。
- `Case Sensitive`: 大文字と小文字を区別します。
- `Visible Only`: Viewportで表示されているオブジェクトだけを対象にします。全オブジェクトを書き出す大量処理ではOFF推奨です。

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
- 高速化のために全オブジェクトを自動で非表示にはしません。非表示化はCSV対象を変える危険があり、60,000個規模では非表示変更そのものも重くなります。
- Blender Pythonのデータアクセスは基本的にメインスレッド中心です。CPU全コアを使うマルチスレッド化ではなく、UI割り込みとCSV書き込み回数を減らして高速化しています。
- 書き出し中に中断したい場合は `Esc` を押してください。中断時は途中までのCSVが残る場合があります。
- 大量処理前に `.blend` を保存しておくと、名前変更やタグ付けを戻しやすくなります。
