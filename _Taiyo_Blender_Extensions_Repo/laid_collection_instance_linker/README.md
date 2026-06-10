# CW_Laid Collection Instance Linker

`Laid_MAP`の配置Transformと、`Laid_Individual`配下の分割済みパーツCollectionを名前で結び、Collection Instance版のマップを生成するBlender Extensionです。

このExtensionはカスタムワークフロー専用の独立ツールです。既存のMap Link ToolsやCollection Linked Mesh Replacerには機能を混在させません。

## 基本情報

- Extension ID: `laid_collection_instance_linker`
- バージョン: `1.0.2`
- 配布対象Blender: `4.2.0`以降
- アドオンコードのAPI基準: Blender `4.0.0`以降
- 表示場所: `3D Viewport > Sidebar (N) > Laid Linker`
- 出力Collection既定名: `Generated_SIM_Map`

## 対象構造

```text
Laid_MAP
└─ 配置済みの元Object

Laid_Individual
└─ 任意の階層
   └─ 直下にMesh Objectを持つリンク対象Collection
```

`Laid_MAP`と`Laid_Individual`は子Collectionを含めて再帰的に検索します。リンク候補になるのは、`Laid_Individual`配下で直下にMesh Objectを1つ以上持つCollectionです。

## 基本手順

1. `Laid_MAP Collection`へ配置元のCollectionを指定します。
2. `Laid_Individual Root`へ分割済みパーツ群のRoot Collectionを指定します。
3. 必要に応じて名前照合設定と出力Collection名を変更します。
4. `Preview / Link`を実行します。
5. `MISSING`と`DUPLICATE`を確認し、名前やCollection構造を修正します。
6. 問題が解消したら`Generate Collection Instances`を実行します。
7. 実体Objectが必要な場合は`Realize Generated Instances`を実行します。

## 名前照合

`Name Source`は次の3種類です。

- `Object Name, then Mesh Data`: Object名で見つからない場合にMesh Data名を試す
- `Object Name Only`: Object名だけを使う
- `Mesh Data Name Only`: Mesh Data名だけを使う

`Ignore .001 / .1234`がONの場合、末尾の`.`と数字だけを除去します。

```text
Wall_A.001   -> Wall_A
Wall_A.1234  -> Wall_A
Wall_A_v001  -> Wall_A_v001
```

一致候補が1つなら`LINKED`、0件なら`MISSING`、複数なら`DUPLICATE`です。Duplicateは自動解決しません。`Only Mesh Objects`がONのとき、Mesh以外の元Objectは`SKIPPED`になります。

## Previewで保存するCustom Properties

リンク結果は`Laid_MAP`側の元Objectへ保存します。

```text
LCIL_link_collection_name
LCIL_link_collection_path
LCIL_link_collection_color_tag
LCIL_link_match_key
LCIL_link_status
LCIL_link_source_name_field
```

リンク失敗時は古いリンク先情報を消し、現在のstatus、match key、name fieldだけを残します。これにより古い成功結果を誤って生成に使いません。

## Collection Instance生成

生成物は次の形式です。

```text
Generated_SIM_Map
└─ GRP_<Target Collection>
   └─ INST_<Source Object>
```

- Emptyの`instance_type`は`COLLECTION`
- `instance_collection`はリンク先Collection
- `matrix_world`は`Laid_MAP`側元Objectと同じ
- Group Collectionにはリンク先のCollection Color Tagをコピー
- EmptyのObject ColorにもColor Tagに対応した近似色を設定

`Group by Target Collection`をOFFにすると、Emptyを出力Collection直下へ作ります。`Instance Prefix`の既定値は`INST_`です。

## 再生成の安全性

生成物には必ず次のCustom Propertyを付けます。

```text
LCIL_generated = True
```

再生成時に削除するのは、このPropertyを持つObjectと、ツールが新規作成した空のGroup Collectionだけです。出力Collectionへ手動で追加したObjectや既存Collectionは削除しません。

## Realize

`Realize Generated Instances`は生成済みCollection Instance Emptyだけを対象にします。参照Collection配下のObjectを再帰的に複製し、Mesh Dataは共有したまま実体Objectを作ります。

RealizeはTimerを使ったModal処理です。パーツObject単位で複数ティックに分割し、NパネルとBlenderのステータスバーへ進捗を表示します。`Cancel Realize`または`Esc`で中断できます。中断時は処理途中だった1インスタンスだけを巻き戻し、完了済みインスタンスは保持します。もう一度実行すると残りのEmptyから続行できます。

```text
Realized Matrix World
= Instance Empty Matrix World
@ Source Part Matrix World
```

Realize後のObject名は次の形式です。

```text
REAL_<Instance Empty Name>__<Source Part Object Name>
```

処理が完了した元Emptyは削除されます。Realize済みObjectには`LCIL_generated_kind = "REALIZED_OBJECT"`を保存します。

## Emptyだけを削除

`Delete Generated Empty Instances`は次の条件を満たす生成Emptyだけを削除します。

```text
LCIL_generated = True
LCIL_generated_kind = "COLLECTION_INSTANCE_EMPTY"
type = EMPTY
instance_type = COLLECTION
```

Realize済みObjectや手動作成Objectは削除しません。

## 注意点

- `Laid_MAP`のTransform、表示、Render設定は変更しません。
- `Laid_Individual`の内容は変更しません。
- 同じ正規化名の候補が複数ある場合は生成しません。
- Manual Link Override、Candidate Picker、Export Pipeline連携は未実装です。
- 大量処理は同期実行です。数万Object規模では処理中にBlenderが応答待ちになる場合があります。
