# Attribute CSV Exporter Helper 使用書（Blenderアドオン）

対象ファイル：`Attribute_CSV_Exporter_Helper_v1_8_2_USE_THIS.py`  
元ファイル：`attribute_csv_exporter.py`  
対象ユーザー：Blenderでメッシュ属性をCSVとして書き出したい人  
アドオンの場所：`3D Viewport > Sidebar（Nキー）> Attr CSV`

---

## 1. このアドオンの目的

このアドオンは、Blender上で選択したメッシュオブジェクトの**属性（Attribute）**をCSVファイルとして書き出すためのツールです。

主な目的は次の通りです。

- Geometry Nodesで作った属性をCSVに出力する
- 頂点、エッジ、面、フェイスコーナー単位のデータを確認する
- 複数オブジェクトの属性を個別CSV、または1つのCSVにまとめて出力する
- `position` や `normal` などの基本属性を表形式で確認する
- モディファイアやGeometry Nodes適用後の評価済みメッシュから属性を取得する

CSVは基本的に次の形で出力されます。

```csv
object,index,position_x,position_y,position_z,normal_x,normal_y,normal_z,my_attribute
Cube,0,0,0,0,0,0,1,1
Cube,1,1,0,0,0,0,1,0
```

つまり、**1行 = 選択したDomainの1要素**、**1列 = 選択した属性**です。

---

## 2. どんな時に使うか

### 2.1 Geometry Nodesの結果を外部で確認したい時

Geometry Nodesで作ったポイント属性、ID、マスク、ウェイト、ランダム値などをCSVで確認できます。

例：

- ポイントごとのID
- 頂点ごとのマスク値
- 面ごとの分類番号
- 法線、位置、カラー情報
- Geometry Nodes後に生成された属性

### 2.2 Blender外のツールにデータを渡したい時

CSVなので、次のようなツールに渡せます。

- Excel
- Google Sheets
- Python
- Houdini
- Unreal Engine用のデータ変換スクリプト
- 独自ツール

### 2.3 複数オブジェクトの属性を比較したい時

複数のメッシュを選択して、オブジェクトごとにCSVを分けたり、まとめて1つのCSVにできます。

---

## 3. インストール方法

1. Blenderを開きます。
2. 上部メニューから `Edit > Preferences` を開きます。
3. 左側の `Add-ons` を選びます。
4. 右上付近の `Install...` を押します。
5. `Attribute_CSV_Exporter_Helper_v1_8_2_USE_THIS.py` を選択します。
6. インストール後、アドオン一覧で有効化チェックを入れます。
7. 3D Viewportで `Nキー` を押します。
8. 右側サイドバーに `Attr CSV` タブが表示されていれば成功です。

---

## 4. 基本的な使い方

### 最短手順

1. CSVにしたいメッシュオブジェクトを選択します。
2. `Nキー > Attr CSV` を開きます。
3. `Export Folder` で保存先を指定します。
4. `Domain` を選びます。
5. `Attribute Selection` で出力したい属性にチェックを入れます。
6. 必要なら `File Naming` を設定します。
7. `Export CSV` を押します。

---

## 5. 画面構成

アドオンのUIは大きく分けて次の構成です。

1. Target / Export設定
2. Attribute Selection
3. File Naming
4. Export CSV

---

## 6. Target / Export設定

### 6.1 Target: Selected Mesh Objects

このアドオンは、**現在選択しているメッシュオブジェクト**を対象にします。

注意点：

- カーブ、ライト、カメラ、Emptyは対象外です。
- メッシュオブジェクトを1つ以上選択する必要があります。
- アクティブオブジェクトだけでなく、選択中の複数メッシュを処理できます。

---

### 6.2 Export Folder

CSVを書き出す保存先フォルダです。

例：

- `//`  
  現在の `.blend` ファイルと同じ場所を基準にします。
- `C:\Users\Name\Desktop\csv_export\`
- `/Users/Name/Desktop/csv_export/`

注意：

- `//` はBlenderの相対パスです。
- `.blend` を保存していない状態では、意図しない場所になることがあります。
- 確実に管理したい場合は、明示的なフォルダを指定してください。

---

### 6.3 Domain

どの単位の属性を書き出すかを決めます。

#### Vertex（POINT）

頂点単位の属性を出力します。

主な用途：

- 頂点位置
- 頂点法線
- 頂点ウェイト
- 頂点ごとのマスク
- Geometry NodesのPoint属性

CSVの1行は「1頂点」に対応します。

---

#### Edge（EDGE）

エッジ単位の属性を出力します。

主な用途：

- エッジごとのフラグ
- 境界エッジ判定
- エッジ長に関連するカスタム属性
- エッジ選択情報の確認

CSVの1行は「1エッジ」に対応します。

---

#### Face（FACE）

面単位の属性を出力します。

主な用途：

- 面ごとのID
- マテリアル分類用の属性
- 面ごとのランダム値
- ポリゴン単位のマスク
- シミュレーションや破壊用のグループ情報

CSVの1行は「1面」に対応します。

---

#### Corner（CORNER）

フェイスコーナー、つまりLoop単位の属性を出力します。

主な用途：

- UV
- 頂点カラー
- フェイスコーナーごとの法線
- 面に属する頂点ごとのデータ
- UV展開後のデータ確認

CSVの1行は「1フェイスコーナー」に対応します。

重要：

- `CORNER` は頂点数より多くなることがあります。
- 1つの頂点が複数の面で共有されている場合、面ごとに別のCornerとして扱われます。
- UVやColor Attributeを確認したい時は、まず `CORNER` を試すのがおすすめです。

---

### 6.4 Vector Mode

ベクトル型の属性をCSVでどう出すかを決めます。

#### A: Keep as (x,y,z)

ベクトルを1つのセルにまとめて出力します。

例：

```csv
position
"(1.0,2.0,3.0)"
```

向いている用途：

- 人間がざっくり確認したい
- 1セルにまとまっていた方が見やすい
- 後で文字列として処理する予定がある

---

#### B: Split to _x/_y/_z

ベクトルを成分ごとの列に分けて出力します。

例：

```csv
position_x,position_y,position_z
1.0,2.0,3.0
```

向いている用途：

- ExcelやGoogle Sheetsで分析したい
- Pythonで数値として読み込みたい
- HoudiniやUnrealなどにデータとして渡したい

基本的には、**Splitがおすすめ**です。

---

### 6.5 Attribute Source

`Attribute Selection` に表示する属性リストを、どのオブジェクトから作るかを決めます。

#### Selected Union

選択中のすべてのメッシュオブジェクトから属性名を集めます。

向いている用途：

- 複数オブジェクトをまとめて出力したい
- オブジェクトごとに少し違う属性を持っている
- まず全体の属性を確認したい

注意：

- あるオブジェクトに存在しない属性は、CSV上では空欄になります。
- 複数選択時はこちらが基本です。

---

#### Active Object

アクティブオブジェクトだけを基準に属性リストを作ります。

向いている用途：

- 代表オブジェクトの属性だけを基準にしたい
- 選択中オブジェクトが多く、属性リストを絞りたい
- 余計な属性を表示したくない

注意：

- アクティブオブジェクトにない属性はリストに出ません。
- 複数オブジェクトを書き出す場合でも、リスト生成だけがアクティブ基準になります。

---

### 6.6 Use Evaluated Mesh（GN/Modifiers）

モディファイアやGeometry Nodesを反映した後のメッシュから属性を取得するかを決めます。

#### ON

評価済みメッシュから属性を取得します。

向いている用途：

- Geometry Nodesで作った属性を書き出したい
- モディファイア後の頂点数、面数、属性を使いたい
- 実際に見えている結果に近いデータを書き出したい

基本的にはONがおすすめです。

#### OFF

元のメッシュデータから属性を取得します。

向いている用途：

- モディファイア前の元データを確認したい
- Geometry Nodesの結果を含めたくない
- オリジナルメッシュの属性だけ欲しい

---

## 7. Attribute Selection

ここでは、CSVに出力する列を選びます。

### 7.1 Available

現在の設定で検出された属性の数です。

この数は次の設定で変わります。

- 選択オブジェクト
- Domain
- Attribute Source
- Use Evaluated Mesh

---

### 7.2 Selected

現在チェックされている属性の数です。

チェックしたものだけCSVに出力されます。

---

### 7.3 Output Columns

実際にCSVに出力される列数です。

例：

`position` をSplitで出す場合：

- 選択属性数：1
- 出力列数：3  
  `position_x`, `position_y`, `position_z`

つまり、**選択属性数と出力列数は一致しないことがあります。**

---

### 7.4 Rows(N)

現在のDomainで出力される行数の目安です。

例：

- Vertex（POINT）なら頂点数
- Edge（EDGE）ならエッジ数
- Face（FACE）なら面数
- Corner（CORNER）ならループ数

複数オブジェクトを選択している場合は、合計数になります。

---

### 7.5 object

アドオン側で追加される列です。

どのオブジェクトから来た行かを記録します。

複数オブジェクトを1つのCSVにまとめる場合は、基本的にチェックすることをおすすめします。

---

### 7.6 index

アドオン側で追加される列です。

各Domain内での要素番号を記録します。

例：

- Vertexなら頂点インデックス
- Edgeならエッジインデックス
- Faceなら面インデックス
- Cornerならループインデックス

後で元データと照合したい場合は、基本的にチェックすることをおすすめします。

---

### 7.7 position

メッシュの位置属性です。

通常はVertex（POINT）で使用します。

Splitの場合：

```csv
position_x,position_y,position_z
```

---

### 7.8 normal

法線属性です。

通常はVertex（POINT）やCorner（CORNER）で確認します。

Splitの場合：

```csv
normal_x,normal_y,normal_z
```

---

### 7.9 その他のカスタム属性

Geometry NodesやBlender内で作られた属性が表示されます。

例：

- `id`
- `mask`
- `weight`
- `random_value`
- `group`
- `uv`
- `color`
- `my_attribute`

注意：

- `.` で始まる内部属性は表示・出力しない仕様です。
- 選択したDomainと一致しない属性は表示されません。
- 属性データ数とDomainの要素数が合わない属性はスキップされます。

---

## 8. v1.8.2で追加した補助ボタン

修正版では、属性選択をしやすくするために補助ボタンを追加しています。

### 8.1 Refresh

現在の選択状態と設定をもとに、属性リストを手動更新します。

使う場面：

- オブジェクト選択を変えた
- Geometry Nodesの属性を変更した
- Domainを切り替えた
- リスト表示が古い気がする

---

### 8.2 All

表示中の属性をすべてチェックします。

使う場面：

- とりあえず全部書き出したい
- 属性数が少ない
- デバッグ目的で全データを見たい

---

### 8.3 None

表示中の属性チェックをすべて外します。

使う場面：

- 一度選択をリセットしたい
- 必要なものだけ選び直したい

---

### 8.4 Basic: object / index / position / normal

基本セットを自動選択します。

選ばれるもの：

- `object`
- `index`
- `position`
- `normal`

使う場面：

- まず最低限のCSVを出したい
- 座標と法線を確認したい
- 複数オブジェクトを安全に識別したい

---

## 9. File Naming

### 9.1 Export Individually（Selected）

ONの場合、選択したメッシュオブジェクトごとにCSVを作ります。

例：

選択オブジェクト：

- `Cube`
- `Sphere`
- `Plane`

出力：

```text
Cube.csv
Sphere.csv
Plane.csv
```

向いている用途：

- オブジェクトごとにデータを分けたい
- 後で個別に処理したい
- オブジェクト単位の管理を優先したい

---

### 9.2 Export IndividuallyをOFFにした場合

選択した複数メッシュを1つのCSVにまとめます。

例：

```text
Selected.csv
```

向いている用途：

- まとめてExcelで確認したい
- Pythonで一括処理したい
- オブジェクトをまたいで比較したい

この場合は、`object` 列をチェックしておくと、どの行がどのオブジェクトのデータか分かりやすくなります。

---

### 9.3 Prefix

ファイル名の先頭に文字を追加します。

例：

Prefix：

```text
export_
```

出力：

```text
export_Cube.csv
```

---

### 9.4 Suffix

ファイル名の末尾に文字を追加します。

例：

Suffix：

```text
_v001
```

出力：

```text
Cube_v001.csv
```

---

### 9.5 Merged File Name

`Export Individually` がOFFの時だけ使用されます。

空欄の場合は `Selected.csv` になります。

例：

```text
school_wall_vertex_attributes.csv
```

のように、何のデータか分かる名前にするのがおすすめです。

---

## 10. Export CSV

クリックするとCSVを書き出します。

実行前に最低限確認すること：

- メッシュオブジェクトを選択しているか
- 保存先フォルダが正しいか
- Domainが正しいか
- 出力したい属性にチェックが入っているか
- 個別出力か、結合出力か

---

## 11. おすすめ設定

### 11.1 まず動作確認したい時

- Domain：`Vertex（POINT）`
- Vector Mode：`Split to _x/_y/_z`
- Attribute Source：`Selected Union`
- Use Evaluated Mesh：ON
- Attribute Selection：`Basic: object / index / position / normal`
- Export Individually：ON

---

### 11.2 Geometry Nodesの属性を確認したい時

- Domain：属性を作ったDomainに合わせる
- Vector Mode：`Split to _x/_y/_z`
- Attribute Source：`Selected Union`
- Use Evaluated Mesh：ON
- Attribute Selection：確認したいGN属性をチェック

重要：

Geometry Nodesで作った属性が表示されない場合は、まず `Use Evaluated Mesh` がONか確認してください。

---

### 11.3 複数オブジェクトを1つのCSVにまとめたい時

- Attribute Source：`Selected Union`
- Export Individually：OFF
- Merged File Name：分かりやすい名前を入力
- `object` と `index` をチェック

例：

```text
merged_wall_parts_point_attributes.csv
```

---

### 11.4 UVやカラーを確認したい時

- Domain：`Corner（CORNER）`
- Vector Mode：`Split to _x/_y/_z`
- Use Evaluated Mesh：ON

UVや頂点カラーはCorner側にあることが多いため、Vertexで見つからない場合はCornerを試してください。

---

## 12. 出力CSVの読み方

### 12.1 object列

どのオブジェクトのデータかを示します。

### 12.2 index列

そのDomain内の番号です。

### 12.3 position_x / position_y / position_z

位置のXYZ成分です。

### 12.4 normal_x / normal_y / normal_z

法線のXYZ成分です。

### 12.5 カスタム属性列

Geometry NodesやBlender上で作った任意の属性です。

---

## 13. よくあるエラーと対処

### 13.1 No mesh objects selected.

原因：

メッシュオブジェクトが選択されていません。

対処：

CSVにしたいメッシュオブジェクトを選択してください。

---

### 13.2 No attributes selected.

原因：

Attribute Selectionで何もチェックされていません。

対処：

`object`、`index`、`position`、`normal`、または必要なカスタム属性にチェックを入れてください。

---

### 13.3 属性が表示されない

考えられる原因：

- Domainが違う
- Use Evaluated MeshがOFFになっている
- アクティブオブジェクト基準になっている
- 属性名が `.` で始まる内部属性
- 属性データ数とDomainの要素数が一致していない

対処：

1. `Refresh` を押します。
2. `Use Evaluated Mesh` をONにします。
3. Domainを切り替えます。
4. `Attribute Source` を `Selected Union` にします。
5. オブジェクトを選び直します。

---

### 13.4 Rows(N) が0になる

原因：

選択したDomainに要素がありません。

例：

- エッジがないメッシュでEdgeを選んでいる
- 面がないメッシュでFaceを選んでいる
- 選択対象がメッシュではない

対処：

正しいDomainを選ぶか、対象メッシュを確認してください。

---

### 13.5 Excelで文字化けする

このアドオンはUTF-8でCSVを書き出します。

対処：

Excelで直接ダブルクリックして開くのではなく、Excelの「データの取得」または「テキスト/CSVから」を使い、文字コードをUTF-8として読み込んでください。

---

### 13.6 CSVの列が多すぎる

原因：

Vector ModeがSplitで、多数のベクトル属性を選んでいる可能性があります。

対処：

- 不要な属性のチェックを外す
- Vector ModeをKeepにする
- Domainを必要なものだけにする

---

## 14. 実践例

### 14.1 頂点座標だけを書き出す

1. メッシュを選択
2. Domain：`Vertex（POINT）`
3. Vector Mode：`Split`
4. `position` をチェック
5. 必要なら `object` と `index` もチェック
6. `Export CSV`

出力例：

```csv
object,index,position_x,position_y,position_z
Cube,0,-1,-1,-1
Cube,1,1,-1,-1
```

---

### 14.2 面ごとのIDを書き出す

1. Geometry NodesなどでFace Domainに `id` 属性を作る
2. Domain：`Face（FACE）`
3. Use Evaluated Mesh：ON
4. `id` をチェック
5. `Export CSV`

---

### 14.3 UVを書き出す

1. メッシュを選択
2. Domain：`Corner（CORNER）`
3. Vector Mode：`Split`
4. UV属性をチェック
5. `Export CSV`

---

### 14.4 複数オブジェクトを1つにまとめる

1. 複数メッシュを選択
2. Attribute Source：`Selected Union`
3. `object` と `index` をチェック
4. 必要な属性をチェック
5. Export Individually：OFF
6. Merged File Nameを入力
7. `Export CSV`

---

## 15. 運用ルールのおすすめ

後からファイルを見て迷わないように、次の命名がおすすめです。

### アドオン本体

```text
Attribute_CSV_Exporter_Helper_v1_8_2_USE_THIS.py
```

意味：

- `Attribute_CSV_Exporter`：何のツールか
- `Helper`：作業補助アドオン
- `v1_8_2`：バージョン
- `USE_THIS`：使うべき最新版

### 使用書

```text
Attribute_CSV_Exporter_Helper_User_Manual_JP_v1_8_2.md
```

意味：

- `User_Manual`：使用書
- `JP`：日本語
- `v1_8_2`：対応バージョン

### 配布用ZIP

```text
Attribute_CSV_Exporter_Helper_v1_8_2_USE_THIS_Package.zip
```

中にアドオン本体と使用書をまとめて入れておくと、後から見ても分かりやすいです。

---

## 16. まず使うべきファイル

通常は次のファイルを使ってください。

```text
Attribute_CSV_Exporter_Helper_v1_8_2_USE_THIS.py
```

使用書を見る場合は次のファイルです。

```text
Attribute_CSV_Exporter_Helper_User_Manual_JP_v1_8_2.md
```

---

## 17. まとめ

このアドオンは、Blenderのメッシュ属性をCSVに変換するためのツールです。

重要な考え方は次の4つです。

1. **どのオブジェクトを対象にするか**  
   選択中のメッシュオブジェクトが対象です。

2. **どのDomainで出すか**  
   Vertex、Edge、Face、Cornerのどれかを選びます。

3. **どの属性を出すか**  
   Attribute Selectionでチェックしたものだけが出力されます。

4. **個別出力か結合出力か**  
   Export Individuallyで切り替えます。

最初は、`Vertex（POINT）`、`Split`、`Use Evaluated Mesh ON`、`Basic: object / index / position / normal` の組み合わせから始めるのがおすすめです。
