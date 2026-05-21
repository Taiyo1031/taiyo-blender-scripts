# RB Instance Helper 使用書 v1.3.1 FINAL

**使用するアドオンファイル:** `RB_Instance_Helper_Blender_Addon_v1.3.1_FINAL.py`  
**対象:** Blender 5.1.x  
**表示場所:** `View3D > N-panel > RB Helper`  
**用途:** リンク Collection Instance を Rigid Body シミュレーションで扱いやすくするための補助アドオン

---

## 1. このアドオンの目的

`RB Instance Helper` は、Blender の **リンク Collection Instance** を、Rigid Body シミュレーションで安全に動かすためのアドオンです。

通常、Asset Browser などから配置したリンク Collection Instance は、そのままでは Rigid Body 用の実体メッシュとして扱いにくいです。そこでこのアドオンでは、元のリンクインスタンスは見た目用として残し、そのインスタンスに対応する **隠しプロキシメッシュ** を作成します。

作成されたプロキシメッシュに Rigid Body を付けて物理シミュレーションを行い、最後にその動きを元のリンクインスタンスへキーフレームとして転送します。

---

## 2. 基本コンセプト

このアドオンの考え方はシンプルです。

```text
元のリンク Collection Instance = 見た目担当
生成された Proxy Mesh       = Rigid Body 担当
```

セットアップ後は、基本的に次のような構造になります。

```text
RB_Proxies コレクション
└── RBProxy_[InstanceName]        ← Rigid Body 用プロキシメッシュ
    └── [InstanceName]            ← 元のリンク Collection Instance / 見た目担当
```

重要な点は以下です。

- 元のリンクインスタンスは、元の所属コレクションから移動しません。
- 新しく作られるプロキシだけが `RB_Proxies` コレクションに入ります。
- `RB_Proxies` コレクションには茶色系のカラータグが付きます。
- プロキシはレンダリングから非表示にできます。
- 元インスタンスはプロキシの子になるため、物理シミュレーションに追従します。
- 最終的に `Transfer & Remove Parent` で、プロキシの動きを元インスタンスへキーフレームとして移せます。



---

## 5. 事前準備

このアドオンは、**Collection Instance** を対象にします。

対象になるもの:

- Asset Browser などから配置したリンク Collection Instance
- `Object > Collection Instance` で配置した Collection Instance
- 同じ `.blend` ファイル内の Collection を参照している Collection Instance
- `instance_collection` を持っているオブジェクト

対象にならないもの:

- 普通の Mesh Object
- ただの Empty
- Collection Instance ではないオブジェクト

---

## 6. メニュー構成

N-panel の `RB Helper` タブには、以下の4つのメニューがあります。

```text
RB Instance Helper
├── 1 · SETUP
├── 2 · UPDATE
├── 3 · BAKE & TRANSFER
└── 4 · SELECT & COPY
```

---

# 1 · SETUP

## 1-1. Target

対象の選び方を指定します。

### Selected Objects

現在選択している Collection Instance だけを対象にします。

通常はこちらを使います。

### Collection

指定した Collection の中にある Collection Instance をまとめて対象にします。

複数のリンクインスタンスを一括でセットアップしたい場合に使います。

---

## 1-2. Collection

`Target` が `Collection` の時だけ表示されます。

ここで指定したコレクション内にある Collection Instance が処理対象になります。

---

## 1-3. Hide Proxy from Render

デフォルト: ON

生成されたプロキシメッシュをレンダリングに映らないようにします。

基本的には ON のまま使ってください。

理由:

- 見た目は元のリンクインスタンスが担当するため
- プロキシは物理計算用であり、レンダリングには不要なため

---

## 1-4. Show Proxy Object Name

デフォルト: ON

生成されたプロキシのオブジェクト名を Viewport 上に表示するかどうかを指定します。

ON の場合、プロキシ名が表示されます。OFF の場合、プロキシは表示されたままですが、オブジェクト名ラベルは表示されません。

---

## 1-5. Put Proxies in "RB_Proxies"

デフォルト: ON

生成されたプロキシを `RB_Proxies` コレクションに入れます。

基本的には ON のまま使ってください。

`RB_Proxies` コレクションには茶色系のカラータグが付き、Outliner 上でプロキシ管理用コレクションだと分かりやすくなります。

---

## 1-6. Auto Add Rigid Body

デフォルト: ON

生成したプロキシに、自動で Rigid Body を追加します。

基本的には ON 推奨です。

ON の場合、`Realize & Parent` を押した時点でプロキシに Active Rigid Body が付きます。

---

## 1-7. Center Proxy Origin

デフォルト: ON

生成されたプロキシの原点を、統合メッシュの中心に移動します。

これは重要な機能です。

Rigid Body シミュレーションでは、オブジェクトの原点や重心位置が挙動に大きく影響します。リンクインスタンスの元の原点が中心からズレている場合、そのままシミュレーションすると、不自然な回転やズレが出やすくなります。

このオプションを ON にすると、プロキシの原点を中心に置きつつ、元のリンクインスタンスの見た目位置はオフセットとして保持されます。

基本的には ON 推奨です。

---

## 1-8. Collision Shape

`Auto Add Rigid Body` が ON の時に表示されます。

生成プロキシに設定する Rigid Body の Collision Shape を選びます。

### Convex Hull

デフォルトです。

動く Rigid Body では比較的安定しやすいため、基本的にはこれを使います。

### Mesh

メッシュ形状をそのまま使います。

形状の正確さは高いですが、複雑な形状や Active Rigid Body では重くなったり、不安定になったりすることがあります。

### Box / Sphere / Capsule / Cylinder / Cone

軽量な簡易コリジョンです。

形が単純なアセットではこちらの方が安定することがあります。

---

## 1-9. Realize & Parent

セットアップを実行するボタンです。

このボタンを押すと、選択または指定コレクション内の Collection Instance に対して、次の処理を行います。

1. 元のリンク Collection Instance を確認する
2. 元 Collection 内の Mesh を読み取る
3. Rigid Body 用の統合プロキシメッシュを生成する
4. プロキシを `RB_Proxies` コレクションへ入れる
5. 必要ならプロキシをレンダー非表示にする
6. 必要ならプロキシに Rigid Body を追加する
7. プロキシの原点を中心に移動する
8. 元リンクインスタンスをプロキシの子にする
9. 見た目がズレないようにオフセット情報を保存する

注意:

このボタンは、元リンクインスタンスそのものを実体化して置き換えるものではありません。Rigid Body 用のプロキシメッシュを新しく生成するものです。

---

# 2 · UPDATE

## 2-1. Update Selected Proxy

選択中のインスタンスまたはプロキシに対応するペアだけを更新します。

使う場面:

- 元の Collection の中身を変更した
- プロキシの形状を作り直したい
- セットアップ後に元アセットを修正した

このボタンは、古いプロキシを削除してから新しいプロキシを再生成します。

そのため、Update を押すたびに Mesh や Empty が増え続けるような挙動にならないように作られています。

---

## 2-2. Update All Proxies

シーン内にある、このアドオンで作成された全プロキシを更新します。

使う場面:

- 複数のリンクインスタンスをまとめて更新したい
- アセット全体を修正した後、一括でプロキシを作り直したい

注意:

Update ではプロキシ形状が再生成されます。重要な作業前にはファイルを保存してから実行することをおすすめします。

---

# 3 · BAKE & TRANSFER

## 3-1. Range

Bake と Transfer に使うフレーム範囲を指定します。

### Scene

シーンの `Start` / `End` フレームを使います。

通常はこちらで問題ありません。

### Custom

任意の `Start` / `End` フレームを指定します。

一部分だけベイクしたい場合に使います。

---

## 3-2. Bake RB to Keyframes

Rigid Body シミュレーション結果を、プロキシのキーフレームに変換します。

このアドオンでは、対象プロキシを内部で選択してから Blender 標準の Rigid Body Bake を実行します。

基本的な流れ:

1. プロキシに Rigid Body を設定する
2. タイムラインでシミュレーションを確認する
3. 問題なければ `Bake RB to Keyframes` を押す
4. プロキシにキーフレームが作成される

注意:

この時点では、まだ元リンクインスタンスに直接キーが入るわけではありません。プロキシに焼かれた動きを、次の `Transfer & Remove Parent` で元インスタンスへ移します。

---

## 3-3. Delete Proxy after Transfer/Restore

デフォルト: ON

`Transfer & Remove Parent` または `Restore Selected` の後に、プロキシを削除するかどうかを指定します。

### ON

元リンクインスタンスへキーフレームを転送した後、プロキシを削除します。

最終的なアニメーションデータだけを残したい場合に使います。

### OFF

転送後もプロキシを残します。

検証したい場合や、再調整したい場合はこちらが便利です。

---

## 3-4. Transfer & Remove Parent

プロキシの動きを、元リンクインスタンスへキーフレームとして転送します。

このアドオンでは、単純なトランスフォームコピーではなく、Setup 時に保存したオフセットを使って次のように計算します。

```text
元インスタンスのワールド行列 = プロキシのワールド行列 × 保存済みオフセット
```

そのため、プロキシの原点を中心に移動していても、元リンクインスタンスの見た目位置が正しく保たれます。

処理内容:

1. プロキシのキーフレームをフレームごとに評価する
2. 保存済みオフセットを使って元インスタンスの正しいワールド位置を計算する
3. 元インスタンスの親を解除する
4. 元インスタンスに `location` / `rotation` / `scale` のキーフレームを打つ
5. 必要ならプロキシを削除する
6. カスタムプロパティを整理する

使用後は、元リンクインスタンスが単体でアニメーションを持つ状態になります。

---

## 3-5. Restore Selected

選択中のインスタンスまたはプロキシに対応するペアを、現在の状態で元リンクインスタンス側へ戻します。

フレーム範囲のキーフレーム転送は行わず、現在フレームの状態だけを扱います。

### Remove Parent Only

元リンクインスタンスの見た目位置を保ったまま、プロキシとの親子関係を解除します。

使う場面:

- セットアップを取り消したい
- プロキシ親子だけを解除したい
- 現在の見た目位置をそのまま残したい

### Apply Proxy Transform

保存済みオフセットを使って、現在のプロキシのトランスフォームを元リンクインスタンスへ反映してから、親子関係を解除します。

使う場面:

- キーフレーム転送ではなく、現在位置だけを元リンクインスタンスへ適用したい
- シミュレーションや手動移動後の1フレーム分の結果だけを残したい

`Delete Proxy after Transfer/Restore` が ON の場合、Restore 後にプロキシは削除されます。OFF の場合はプロキシを残しますが、RB Instance Helper のペア情報は整理されます。

---

# 4 · SELECT & COPY

## 4-1. Select Related

このセクションでは、このアドオンで管理しているオブジェクトをまとめて選択できます。

選択中のオブジェクトに関係するものだけを選ぶのではなく、**シーン内にある全ての RB Instance Helper 管理オブジェクト**を対象にします。

### Instances

シーン内にある、このアドオンで管理されている全リンクインスタンスを選択します。

使う場面:

- 最終的に残る見た目用インスタンスをまとめて確認したい
- Transfer 後の対象をまとめて選びたい

---

### Proxies

シーン内にある、このアドオンで生成された全プロキシを選択します。

使う場面:

- 生成プロキシをまとめて確認したい
- Rigid Body 設定をまとめて調整したい
- Bake 対象を確認したい

---

### Both

このアドオンで管理されている全リンクインスタンスと全プロキシをまとめて選択します。

使う場面:

- シーン内でこのシステムが使われている範囲を確認したい
- プロキシとインスタンスの対応を一括で見たい

---

### Proxy Children

選択中のプロキシの直下にある子オブジェクトを選択します。

使う場面:

- プロキシを選んだ状態から、元リンクインスタンス側へ素早く選択を切り替えたい
- 複数プロキシを選択して、それぞれの子オブジェクトをまとめて確認したい

注意:

このボタンは、選択中の RB Instance Helper プロキシだけを対象にします。プロキシ以外を選択している場合や、プロキシに子オブジェクトがない場合は実行されません。

---

## 4-2. Copy RB Settings to Selected

アクティブオブジェクトの Rigid Body 設定を、選択中の他オブジェクトへコピーします。

使い方:

1. コピー元にしたい Rigid Body オブジェクトを選択する
2. それ以外のコピー先オブジェクトも選択する
3. コピー元をアクティブオブジェクトにする
4. `Copy RB Settings to Selected` を押す

コピーされる主な項目:

- Type
- Mass
- Friction
- Restitution
- Collision Shape
- Mesh Source
- Use Margin
- Collision Margin
- Linear Damping
- Angular Damping

注意:

アクティブオブジェクトに Rigid Body が付いていない場合は実行できません。

---

## 7. 基本的な使用手順

最も基本的な使い方です。

```text
1. リンク Collection Instance をシーンに配置する
2. 対象インスタンスを選択する
3. N-panel > RB Helper > 1 · SETUP を開く
4. Target を Selected Objects にする
5. Hide Proxy from Render を ON にする
6. Put Proxies in "RB_Proxies" を ON にする
7. Auto Add Rigid Body を ON にする
8. Center Proxy Origin を ON にする
9. Collision Shape はまず Convex Hull にする
10. Realize & Parent を押す
11. 生成されたプロキシの Rigid Body 設定を調整する
12. タイムラインを再生してシミュレーションを確認する
13. 3 · BAKE & TRANSFER を開く
14. 必要なフレーム範囲を指定する
15. Bake RB to Keyframes を押す
16. Transfer & Remove Parent を押す
17. 元リンクインスタンスにアニメーションが転送される
```

---

## 8. 複数インスタンスをまとめて処理する手順

```text
1. 複数のリンク Collection Instance を用意する
2. まとめて選択する
3. Target を Selected Objects にする
4. Realize & Parent を押す
5. 必要に応じて Select Related > Proxies で全プロキシを選択する
6. Rigid Body 設定を調整する
7. Bake RB to Keyframes を実行する
8. Transfer & Remove Parent を実行する
```

または、対象が1つのCollection内にまとまっている場合は、`Target` を `Collection` にして一括処理できます。

---

## 9. おすすめ設定

最初は以下の設定がおすすめです。

```text
Target: Selected Objects
Hide Proxy from Render: ON
Show Proxy Object Name: ON
Put Proxies in "RB_Proxies": ON
Auto Add Rigid Body: ON
Center Proxy Origin: ON
Collision Shape: Convex Hull
Frame Range: Scene
Delete Proxy after Transfer: ON
```

---

## 10. 注意点

### 元アセットを変更したら Update する

元の Collection 内の形状を変更した場合、既存プロキシは自動では変わりません。

その場合は、`Update Selected Proxy` または `Update All Proxies` を押してください。

---

### Rigid Body の調整は基本的にプロキシ側で行う

物理計算に使われるのはプロキシです。

元リンクインスタンスではなく、プロキシ側の Rigid Body 設定を調整してください。

---

### Center Proxy Origin は基本 ON

中心がズレたまま Rigid Body を行うと、回転や落下の挙動が不自然になることがあります。

このアドオンでは、中心原点化したプロキシと、元インスタンスの見た目オフセットをセットで管理します。

---

### Transfer 後に再シミュレーションしたい場合

`Delete Proxy after Transfer` が ON の場合、Transfer 後にプロキシは削除されます。

再シミュレーションしたい可能性がある場合は、`Delete Proxy after Transfer` を OFF にしてから Transfer してください。

---

## 11. トラブルシューティング

### Realize & Parent を押しても何も起きない

確認すること:

- 選択しているものが Collection Instance か
- `instance_collection` を持っているか
- Collection モードの場合、Collection が指定されているか
- Blender のコンソールに `[RB Instance Helper] SKIP:` で始まるログが出ていないか

普通の Mesh Object は対象外です。

---

### プロキシが見えない

`Hide Proxy from Render` はレンダー非表示ですが、Viewportでは基本的に見えるはずです。

確認すること:

- `RB_Proxies` コレクションが非表示になっていないか
- Outliner のフィルターで見えなくなっていないか
- Viewport の表示設定でワイヤーやオブジェクト表示が無効になっていないか

---

### Update したら物理設定が変わった

Update はプロキシ形状を再生成します。

基本的な Rigid Body 設定はできるだけ維持するようにしていますが、複雑な設定や手動で追加した制約などは確認してください。

---

### Transfer 後に位置がズレる

このバージョンでは、プロキシとインスタンスのオフセットを保持して転送します。

それでもズレる場合は、以下を確認してください。

- Setup 後に手動で親子関係を変更していないか
- プロキシやインスタンスのカスタムプロパティを削除していないか
- Transfer 前に `Update` で新しい構造に更新しているか
- 古いバージョンで作ったプロキシをそのまま使っていないか

古いバージョンで作ったものは、`Update Selected Proxy` または `Update All Proxies` を一度実行してから使うのがおすすめです。

---

## 12. 内部管理について

このアドオンは、オブジェクトにカスタムプロパティを付けて管理しています。

主な管理情報:

```text
rbih_pair_id
rbih_role
rbih_version
rbih_source_instance_name
rbih_proxy_root_name
rbih_source_collection_name
rbih_instance_offset_matrix
```

これらのプロパティを使って、プロキシと元インスタンスの対応、Update、Select、Transfer を安定して行っています。

通常、ユーザーがこれらを直接編集する必要はありません。

---

## 13. 最終的なおすすめワークフロー

```text
配置
↓
Realize & Parent
↓
プロキシの Rigid Body 設定を調整
↓
シミュレーション確認
↓
Bake RB to Keyframes
↓
Transfer & Remove Parent
↓
元リンクインスタンスにアニメーションが残る
↓
必要ならプロキシ削除
```

この流れが、このアドオンの基本的で一番安定した使い方です。

---

## 14. まとめ

`RB Instance Helper` は、リンク Collection Instance を直接 Rigid Body 化するのではなく、物理用プロキシを作って安全にシミュレーションし、その結果を元インスタンスへ戻すためのアドオンです。

特に重要なのは以下です。

- 見た目は元リンクインスタンス
- 物理計算はプロキシ
- プロキシは `RB_Proxies` にまとまる
- プロキシ原点は中心に置ける
- 元インスタンスの見た目オフセットは保持される
- 最後に Transfer で元インスタンスへキーフレームを移す

使用するファイルは以下です。

```text
RB_Instance_Helper_Blender_Addon_v1.3.1_FINAL.py
```

この使用書は、上記ファイルに対応しています。
