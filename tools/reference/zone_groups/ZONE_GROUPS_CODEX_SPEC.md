# Zone Groups — Codex実装仕様書

**文書バージョン:** 1.0 / 2026-10-26  
**対象:** Blender 4.5.10 以降の4.5系（Windows中心。可能ならLinux/macOSでも動作）  
**言語:** Python / Blender `bpy` API  
**参照実装:** `zone_groups_ui_mock_v0_2.py` （UIの承認済みプロトタイプ。製品版コードではない）  
**開発ステータス:** 実装指示書。以下の「設計補完」は曖昧さを取り除くための実装デフォルトであり、ユーザーから個別に承認を得た仕様ではない。

---

## 0. Codexへの最優先指示

あなた（Codex）は、同梱の `zone_groups_ui_mock_v0_2.py` を読み、現在のレイアウトとボタンの意図を保ったまま、**見た目だけのUIモックを、実際に動作するBlenderアドオンに置き換えてください**。

1. Nパネルのタブ名は `Groups`。基本UIはv0.2準拠。既存ボタンの削除・別UIへの再設計はしない。
2. グループ所属方式は **`MANUAL` と `VOLUME` の2種類だけ**。`BOTH` を追加しない。
3. **Mergeは同じ方式のグループ同士に限定する**。UIの候補表示だけでなく `execute()` でも検証する。
4. グループを表現するためのBlender Collectionを作らず、Collectionに所属することをグループ判定に使わない。シーン内にEmptyを実在させる際は**既存のCollectionへリンクしてよい**（Blenderの通常操作として必要）。
5. **CSV・JSON・FBX・Houdini連携等を含む、アドオン独自の書き出し機能を一切実装しない**。Exportパネル、メニュー、オペレーター、予約フィールドも不要。
6. 1つのObjectが複数グループに所属できる。グループ数上限31のビットマスク方式は採用しない。
7. グループの追加、削除、並べ替え、Duplicate、Merge、選択、一括表示、一括ロック、Volume評価、Undo/Redo、保存/再読込を実機で実装する。
8. UIのボタンが `[MOCK]` や未実装通知を表示する状態を納品しない。実装が物理的に不可能な操作は安全に無効化し、理由を表示する。
9. 既存のv0.2ソースは**参照用に残し**、実装版は別フォルダ・別アドオンとして納品する。
10. 各フェーズの後にBlender実機の検証を行う。Blender実行環境がない場合、実機検証済みと偽らず、その旨と具体的な手動テスト手順を提出する。

**納品物:** インストール可能なアドオン（推奨ディレクトリ構成は§17）、`README.md`、テストコード、テスト実行結果。Blenderから何かをエクスポートする機能は納品物の作成とは別概念であり、禁止事項と混同しないこと。

---

## 1. 背景・目的

作業シーンには大規模なマップがあり、将来的にその一部をHoudiniでRBDシミュレーションしてからUnreal Engineへ持ち込む制作ワークフローを想定している。**ただし、このアドオン自体はファイル転送・書き出しを担当しない。**

Blender標準Collectionを増やしたり、外部ツール向けの構造を作り変えたりせずに、3D Viewport内でオブジェクトを**論理グループ**に分けて管理することが目的である。たとえば「階段エリア」「廊下」「教室A」などの空間的ゾーンと、任意に選んだ複数オブジェクトをまとめる手動グループを使用する。

### 1.1 用語

| 用語 | 意味 |
|---|---|
| Group | Collectionと独立した論理グループ。Sceneが所有する |
| Manual Group | 選択オブジェクトの明示的なメンバー登録によって構成されるグループ |
| Volume Group | Emptyの幾何学的範囲からメンバーを導出するグループ |
| Controller Empty / Volume | Box / Sphereの判定範囲を定義するBlender Empty |
| Region（内部） | 複数のADD/EXCLUDEボリュームを1つの論理領域として評価する単位。Mergeの正確性のために必要 |
| Dirty | 最終評価時点より関連データが変化しており、表示中の人数やメンバーキャッシュが古い状態 |
| Active Group | グループUIListで選択されているグループ |

### 1.2 適用範囲

- オブジェクト単位の管理（`Object`）。Mesh/Light/Camera/Curve/Empty/Otherを扱う。
- Grease Pencilのレイヤー、Mesh内部の頂点・面、Collection自体のグループ化は対象外。
- グループはScene単位。1シーンで多数のグループを作成可能。
- Objectの**参照**を管理し、グループの編集で元Objectを複製・削除・再親子付けしない。例外はDuplicate Group時に明示的に複製するController Emptyのみ。

---

## 2. 確定要件と設計補完の区別

### 2.1 ユーザーと合意済み

- Collectionをグループ保存先として使用しない。
- UIの基本形は `zone_groups_ui_mock_v0_2.py`。
- MembershipはManual / Volumeのみ。Both不要。
- 複数グループへの同時所属が可能。
- グループ単位のまとめて選択、表示・選択ロックが必要。
- Duplicate GroupとMerge Groupsが必要。
- Mergeは同方式同士のみ。
- VolumeはBox/Sphere、ADD/EXCLUDEに対応。
- Export CSV / すべての書き出し機能が不要。
- Blender 4.5.10以降をターゲットとする。

### 2.2 以下はCodexが採用すべき設計補完（ユーザー未確定部分）

- Group識別子はUUID。名前変更とリスト並べ替えでメンバーを失わない。
- `Duplicate Group` は設定とメンバーをコピーする。ManualのObject自体は複製せず、VolumeのController Emptyは独立したObjectとして複製する。
- `Merge Groups` はアクティブグループを宛先とし、ユーザーが選択した別グループをソースとして統合する。ソース**グループ定義だけ**削除。宛先の名前・色・各種設定を維持。
- Volume MergeはRegionの和集合として保持し、単純なADD/EXCLUDEリスト結合を禁止。
- Hide / Lockが複数グループで競合したときは**制限優先（いずれかが非表示・ロックなら該当Objectに制限を適用）**。
- Manualグループは登録済みメンバーが残る間、VolumeグループはVolume定義が残る間、所属方式を変更できない。誤操作による暗黙のデータ消失を防ぐ。
- Volume評価は初期状態では `ORIGIN` / `DIRTY` を使用する。画面上にはv0.2の全オプションを維持。
- Isolateはトグル式。Show Allはグループによる表示制限をすべて解除する。既存の手動非表示状態を尊重する。

これらの設計補完は、無断で隠れた仕様変更を加えるよりも安全で、テスト可能な初期規則を与えることが目的。コードとREADMEにも明記すること。

---

## 3. UI仕様（基本はv0.2から変更しない）

**配置:** 3D Viewport → `N` → `Groups`

### 3.1 Main Panel `Groups`

```text
┌──────────────────────────────────────────────┐
│ Groups                                       │
│ Zone Groups                                 │
│ ┌───────────────────────────────────┐  [+]   │
│ │ ■ V  階段エリア       128  [視][選] │  [-] │
│ │ ■ V  廊下             342  [視][選] │  [⧉] │
│ │ ■ M  教室A             87  [視][選] │  [↑] │
│ │ ■ M  教室B             64  [視][選] │  [↓] │
│ └───────────────────────────────────┘        │
│ [Duplicate Group]  [Merge Groups]            │
│ Active: 階段エリア [Volume]                  │
│ Selected: 3 object(s)                        │
│ In: 階段エリア / 廊下                         │
│ [Select] [Extend] [Deselect]                 │
│ [Expand to Groups]                           │
├──────────────────────────────────────────────┤
│ ▾ Members                                    │
├──────────────────────────────────────────────┤
│ ▸ Visibility                                 │
└──────────────────────────────────────────────┘
```

※上図は説明用。列幅とIconはBlender 4.5に存在するものを用いる。名称・基本操作は維持する。

- UIList各行: 色、`M`/`V`、編集可能な名前、現在のメンバー数、Dirty印、表示スイッチ、選択可否スイッチ。
- +: 新しいグループ作成。デフォルトManual。
- −: アクティブグループ削除。**Objectは削除しない**。必要なら確認ダイアログ。
- Duplicate: 新規グループ作成。コピーされたグループをアクティブ化。
- ↑↓: UI順序の入れ替えのみ。グループ所属は変わらない。
- Merge: 同方式の相手が存在するときだけ押せる。Confirm付き。異方式は候補にも出さない。
- Active: アクティブグループ名と方式。
- Selected: 現在選択中のObject数。
- In: 選択が1個なら、そのObjectの所属グループ名を列挙。複数選択なら共通所属と混在状態を区別し、誤って全員同じ所属と見せない。
- Manualのときだけ `Add Selected` / `Remove Selected` を表示。
- Volumeのときは上記2ボタンの代わりにVolume案内文を表示。
- `Select` / `Extend` / `Deselect` / `Expand to Groups` は両方式で利用可能。
- 新規シーンでは `No groups yet`、`New Group`、任意の `Create Demo Groups` を表示してよい。ただしデモの人数は実数ではないため、**製品版では偽の人数を保持しない**。デモ作成は開発用として隠すか、カウント0で実際の登録を作る。

### 3.2 Members Panel

- `Membership Mode`: `Manual` / `Volume` ラジオ式。
- Manual: メンバー数と `Add Selected / Remove Selected` の案内。
- Volume: Controller Empty一覧と `+ (Box/Sphere)`、`− (参照解除)`、`Fit to Selection`。
- 各Volume行に `ADD / EXCLUDE`。`PointerProperty(Object)`を使いリネームに追随させる。
- 選択Volumeの `Shape` / `Size` / `Scale` を編集可能。
- 判定方式: `Origin` / `Bounds Center` / `Fully Inside` / `Any Overlap`。
- Object Types: Mesh / Light / Camera / Curve / Empty / Other のオンオフ。v0.2と同じくVolumeのみ表示。
- Update Behavior: `Manual` / `On Demand (DIRTY)` / `Live`。**この3択はグループ方式ではなく、Volumeの評価タイミング設定**であり、Membershipの2方式制限には抵触しない。
- `Evaluate` ボタンと、評価済み人数・Dirtyメッセージ。
- `Panel.draw()`・`UIList.draw_item()`内で高コストのシーン評価を実行しない。

**Regionの表示（Volume Merge後だけ追加される最小限のUI）:** 通常のVolumeグループは1 Regionなので今のフラットリストを維持する。Mergeで2つ以上のRegionを持つ場合のみ `Region 1`、`Region 2` の区切りをリストに表示し、各VolumeがどのRegionのADD/EXCLUDEか識別できるようにする。既存UIを全面的に入れ替えないこと。`Add Volume` は現在選択中のRegionに追加する。Regionを空にした際はそのRegionを削除してよい（少なくとも1件の空Regionを初期値として維持）。Regionの移動・並べ替えは本仕様の必須ではない。`Test` / `Object Types` は**アクティブRegion**の設定を編集する。通常（1 Region）はv0.2と同じ見た目だが、Merge後はRegionの評価設定が互いに独立する。

### 3.3 Visibility Panel

- `Viewport`（`hide_viewport`相当）
- `Select`（`hide_select`相当）
- `Render`（`hide_render`相当）
- `Isolate` / `Show All`
- 表示チェックがOFFであれば所属Objectを非表示、SelectがOFFなら所属Objectの選択を禁止、RenderがOFFなら所属Objectをレンダー対象から除く。
- **これらはグループの状態を表現するスイッチであり、対象Objectの既存のユーザー設定を無条件にTrue/Falseへ上書きしてはならない。** §10参照。

### 3.4 実装不要のUI

- `Both` モード、Export / Export CSV / `zone_id`設定、Houdiniボタン、グループ用Collection作成、複雑な検索フィルタ、専用GPUアウトライン、プレービュー用頂点ハイライト、Bot H。
- 承認済みv0.2にない大規模な新UIは追加しない。

---

## 4. 永続化データモデル

### 4.1 基本方針

`Scene`にPropertyGroup群を保存する。Objectごとに「どこか1つのGroup ID」を持たせる方式では**複数所属に対応できない**。ビットマスクにもグループ数制限があるため採用しない。

推奨構造（名前は提案、同等の設計でも可）:

```python
Scene.zg_schema_version: IntProperty
Scene.zg_groups: CollectionProperty(type=ZG_Group)
Scene.zg_active_group_index: IntProperty
Scene.zg_visibility_baselines: CollectionProperty(type=ZG_ObjectBaseline)

ZG_Group:
    uid: StringProperty  # UUID4; name/indexから独立
    name: StringProperty
    source: EnumProperty(MANUAL, VOLUME)
    color: FloatVectorProperty
    show: BoolProperty
    selectable: BoolProperty
    render: BoolProperty
    update_mode: EnumProperty
    manual_members: CollectionProperty(type=ZG_ObjectRef)
    regions: CollectionProperty(type=ZG_Region)
    active_region_index: IntProperty
    last_evaluated_count: IntProperty
    dirty: BoolProperty

ZG_Region:
    uid: StringProperty
    eval_mode: EnumProperty  # ORIGIN / BOUNDS_CENTER / FULLY_INSIDE / ANY_OVERLAP
    t_mesh, t_light, t_camera, t_curve, t_empty, t_other: BoolProperty
    volumes: CollectionProperty(type=ZG_Volume)
    volume_index: IntProperty

ZG_Volume:
    controller: PointerProperty(type=bpy.types.Object)
    operation: EnumProperty(ADD, EXCLUDE)

ZG_ObjectRef:
    obj: PointerProperty(type=bpy.types.Object)

ZG_ObjectBaseline:
    obj: PointerProperty(type=bpy.types.Object)
    original_hide_viewport: BoolProperty
    original_hide_select: BoolProperty
    original_hide_render: BoolProperty
    active_override_mask: IntProperty  # 各項目を管理中かどうか
```

- UUIDは新規作成時に生成。名前変更・並べ替えでも維持。
- メンバー参照・Volume参照は`PointerProperty(Object)`で保存し、Object名変更でも破損させない。
- Group名は重複しても内部処理が壊れない構造にする。UIの新規生成名は重複回避。
- Sceneに属さないObjectや削除済みの参照は不正メンバーとして無視し、安全にクリーンアップできる。
- ライブラリリンク等で書き込み不可のObjectの**グループ登録・選択**は、Scene内参照として可能な範囲で対応。Object本体のフラグ変更が不可ならスキップして明確な警告を出す。

### 4.2 Volumeの結果キャッシュ

- Volume由来の実メンバーは**評価結果**。保存すべき定義の本体は `regions / volumes`。
- 評価結果セットと、`obj -> groups` 逆引きインデックスは実行時キャッシュに置く。内部キーに`as_pointer()`を使う場合、Undo/Load後は必ず全破棄する。
- `last_evaluated_count` はUI上の参考値。キャッシュ未構築・期限切れ時にはDirty表示を付け、実際のメンバーとして利用しない。
- `eval_mode` / Object Typesは**Regionごとの保存が正**。既存v0.2のGroup単位UIを、1 Regionのとき同じ見た目でRegionプロパティにバインドする。`update_mode` / show / selectable / render はGroup単位。
- Manualメンバーはポインター参照として `.blend` に保存する。
- Volumeの可視性を保存中に変更するために、§10のベースラインは永続化する。開き直し時に表示状態を復元/再計算できること。

### 4.3 v0.2モックとの互換

- v0.2の `Scene.lg_groups`, `LG_GroupItem.volumes` はUIモック形式。**実メンバーは存在しない**。過去のダミー人数を本当のメンバーとして取り込まない。
- 可能なら旧 `lg_groups` を検出して名前/色/source/設定/Volumeポインターを新構造へマイグレーション。旧 `volumes` は `regions[0]` に置く。人数は0またはDirtyに再初期化。
- 移行が難しければ、破損なく「移行不可・新アドオンで再作成」と明示する。勝手に旧データを削除しない。
- ユーザーがv0.2のテキストエディタ版と新アドオンを同時実行するケースに注意。新アドオンはプロパティ/クラス接頭辞を `ZG_` 等に分離し、旧コードと登録名が衝突しないようにする。

---

## 5. Manual Group機能

### 5.1 Add Selected

1. Active GroupがMANUALであることを確認。
2. 現在のView Layerの選択Objectを列挙。
3. 既登録Objectを重複追加しない。
4. Objectそのもの、Collection構造、親子構造を変更せず参照を登録。
5. キャッシュ・人数・可視性制限を更新。
6. 0件選択時はCANCELLED/INFO。クラッシュしない。

### 5.2 Remove Selected

- 選択ObjectとActive Manual Groupとの関係だけを削除。
- 他グループへの所属は維持する。
- Object自体は削除しない。
- 可視性・ロックがこのグループによってのみ適用されていた場合、元の状態へ復元する。

### 5.3 複数所属

- オブジェクト `A` が `教室A`, `階段エリア`, `ライト一式` に同時に所属してもよい。
- Manualへ登録したからといって他のManual/Volumeのメンバーから外してはいけない。
- グループ表示順は**所属の優先順位ではない**。Mergeや再評価も他グループを直接変更しない。

### 5.4 方式変更ガード

- Manual → Volume: `manual_members` が空の場合のみ許可。
- Volume → Manual: 全RegionのVolume参照が0件なら許可し、そのGroupの旧Volume結果キャッシュを無効化する（定義が残る場合の暗黙の消去は禁止）。
- メンバー/Volumeが残っている場合は切替をブロックし、その理由をUIに示す。強制的に無断で全メンバーを消す実装は禁止。
- 直接RNA `update` コールバックで無限再帰が発生しないようにする。実装困難なら切替を専用Operatorで管理し、見た目の二択を維持する。

---

## 6. Volume Group機能

### 6.1 Controller Empty

- `Add Volume → Box` は3Dカーソル位置に `empty_display_type='CUBE'` のEmptyを作成。
- `Add Volume → Sphere` は `empty_display_type='SPHERE'`。
- `empty_display_size=1.0` で初期化。作成後にSize/Scale/Transform変更可。
- Emptyは、現在のコンテキストの**既存**Collectionにリンク。新規管理用Collectionは作らない。
- `Volume Remove` は参照だけ外す。Empty Objectは削除しない。
- Group削除・MergeでもController Emptyを無断削除しない。
- Controller Empty自体はデフォルトで**Volume自動所属の候補から除外**（`t_empty=True`であっても、どこかのグループでControllerとして参照されているEmptyは除外）。普通のEmptyはフィルタに従い対象化できる。
- Controllerとして参照されるEmptyが削除されたらクラッシュせず、該当RegionをDirtyにし、UIにMissing表示する。
- Volume Emptyが `CUBE` / `SPHERE` 以外の形状に変更されたら、計算対象から除外して警告する。勝手に別の形で評価しない。

### 6.2 Regionモデルとブール演算（**最重要**）

1つのRegionは `ADD` と `EXCLUDE` を持つ。基準的な原点評価では、

```text
Region_i(point) =
    (ADD_i[0] ∪ ADD_i[1] ∪ ...)
    \ (EXCLUDE_i[0] ∪ EXCLUDE_i[1] ∪ ...)

Group(point) = Region_0(point) ∪ Region_1(point) ∪ ...
```

- EmptyしかないRegion、あるいはADDが0のRegionは空集合。EXCLUDEだけで全シーンのマイナスにはならない。
- Volumeリストの**順序で結果が変わってはいけない**。ADDの集合からEXCLUDEの集合を引く。
- 複数RegionはOR演算。Region A内のEXCLUDEはRegion Bを削らない。
- 通常は1Region。Mergeで複数Regionになった場合にも**各Regionの評価条件を保存**する。

### 6.3 幾何学的判定

Volume Emptyの変換は `matrix_world` を使用する。オブジェクトの判定点/Boundを世界座標に変換し、Emptyのワールド行列の逆行列でEmptyローカル座標へ移す。

`p_local = inverse(empty.matrix_world) @ p_world`

- Box: Emptyローカル空間の `abs(p.x/y/z) <= size` を満たす領域。境界点は内側。
- Sphere: `dot(p_local, p_local) <= size²` を満たす領域。境界点は内側。
- `size` は `empty_display_size`。スケール/回転/親子付けは `matrix_world` から自然に反映。
- Sphereに非等方Scaleがある場合、世界座標では楕円体として扱う。
- Boxに回転/非等方Scaleがある場合、回転した直方体（親によるshearがあれば平行六面体）として扱う。
- 逆行列が特異（スケール0等）なら評価を安全にスキップして警告。
- **注意:** Blender標準Emptyの描画されるサイズと上記判定領域が一致するかは、Blender 4.5.10実機で箱/球の境界点を使い検証する。ズレがあればBlenderの表示定義に合わせて係数を統一し、テストとREADMEを更新する。推測で固定しない。

### 6.4 Evaluation Mode

| UI | 判定対象 | 明示的な仕様 |
|---|---|---|
| Origin | `Object.matrix_world.translation` | Object原点がEmptyの内側ならTrue。最速、デフォルト |
| Bounds Center | ObjectローカルBBox 8頂点の平均をワールド変換 | 中心点が内側ならTrue |
| Fully Inside | ObjectのワールドBBox全体 | **1つのVolume形状に全BBox頂点が含まれる**とき、そのVolumeの判定がTrue |
| Any Overlap | ObjectのワールドBBoxとVolume形状 | 両者が少しでも交差（接触を含む）すれば、そのVolumeの判定がTrue |

- Mesh内部の正確なポリゴン交差ではなく、`Object.bound_box`で扱う。
- Boundsが存在しないObjectタイプはOriginへのフォールバックとし、その件数を必要に応じ報告。無意味な `(-1,-1,-1)` のBBoxを真の幾何として扱わない。
- MeshのModifierやGeometry Nodes生成結果については**元ObjectのBBox基準**をv1の基本とする。Evaluated Geometryに基づく完全な形状評価は将来拡張。
- Fully Inside: 凸形状VolumeについてBBoxの全8頂点の包含で判定可能。ただし**複数のADD VolumeをまたいでBBox全体が覆われるケース**は「1つのVolumeに完全内包」という実装上の定義に従う。
- Any Overlap: BBox頂点だけを検査する実装は禁止（大きなBoxが小さなVolumeを包むケース等を見落とす）。Box同士はSATまたは同等の凸体交差判定、球/楕円体とBBoxはGJK等の正確な凸体交差判定を推奨する。接触/微小誤差のepsilonを定数化しテストする。

**重要 — BoundsモードのADD/EXCLUDE:** 本v1ではVolumeごとに上表のPredicateを評価し、各Regionを

`hit_region(object) = any(hit(add_v, object)) and not any(hit(exclude_v, object))`

として結合する。この結果は「各Volumeに対するBBox判定の論理積和」であり、複数の部分重なりを含む**厳密な3D形状の差集合そのもの**とは必ずしも一致しない。UI tooltip/READMEに明記し、完全なCSGやメッシュ演算を暗黙に保証しないこと。Merge後も**このPredicateの結果をRegion単位でOR結合**するため、統合前の所属結果の和集合が保持される。

### 6.5 Object Typesフィルタ

- `MESH`, `LIGHT`, `CAMERA`, `CURVE`, `EMPTY`, その他を切替。
- Blender 4.5のCurve系/Grease Pencil/Font等は、一致するUI種別へ分類し、未分類はOther。
- このフィルタはVolume評価にのみ作用。Manualで明示登録したメンバーは強制削除しない。
- マスク変更時はDirtyにして再評価対象にする。

### 6.6 Fit to Selection

- 選択されたObjectのワールド空間BBox全体を計算する。
- 原点だけしか扱えないObjectはその位置を点として扱う。
- 選択全体を包含するAABBを計算し、Box Volumeを作る。AABB中心に配置し、寸法に半径/余白を反映。
- EmptyのScale/Sizeが意図したAABBを描画するよう設定。余白の初期値はごく小さい正値（例 0.01 Blender unit）。一部の軸がゼロ幅でも極小厚を確保。
- 新規Volumeは対象RegionのADDとして登録する。
- 選択0件は警告し、何も作らない。

---

## 7. Update Behavior・Dirty管理

**Volume評価方式**はManual Group/Volume Groupの区別とは独立した設定。

### 7.1 MANUAL

- `Evaluate`クリック時だけメンバーキャッシュを再計算。
- Empty/Object移動時はDirtyにするが、勝手に計算しない。
- Dirtyのまま `Select Members` 等を押すと、**再評価が必要**と通知し、古いキャッシュを新しい結果であるかのように使わない。必要なら最後の確定結果を使うことを明記したオプションは将来実装とする。

### 7.2 DIRTY / On Demand（デフォルト）

- Dirty原因（空間変化、対象ObjectのTransform/Bounds変化、Objectの作成/削除、フィルタ、ボリューム構成や設定変更）を検出する。
- Dirty中にそのグループの実メンバーを必要とするオペレーター（Select / Expand / Isolate / 制限状態再適用）を実行するとき、**先に再評価**する。
- `Evaluate`による手動再評価も可能。
- パネル描画自体では評価しない。Dirtyの人数は前回値であることが分かるアイコンを出す。

### 7.3 LIVE

- 変更検知後にデバウンス（推奨300ms程度）して必要なグループを再評価。ユーザー操作中の毎フレーム全シーン走査はしない。
- `bpy.app.handlers.depsgraph_update_post` では差分を観測・Dirty付与する。重い実評価や大量の可視性書換えは原則ここでは行わず、`bpy.app.timers` 側で安全に処理。
- Objectの移動を見逃すと範囲への出入りが正しく更新されないため、Controller Emptyだけでなく、**判定対象のObjectのTransform/データ変更も監視**する。
- アニメーション評価/フレーム変更や表示状態の変更などにも配慮する。BlenderのUndo/Redo/ファイル読込/書込/終了中にタイマー処理が古いObject参照へアクセスしないようにする。
- UIを描画していない状態でもLiveを選んだグループの更新が成立する。ただし重いシーンで描画/変形操作を妨げないこと。

### 7.4 Handler・Cacheの安全性

- `load_post`（persistent）、`undo_post`、`redo_post` でObject/Groupキャッシュと逆引きを破棄、Region参照とベースラインを再照合しDirtyを設定。
- `depsgraph_update_post` は対象更新の絞り込みを行う。Scene全走査を毎イベントに行わない。
- 更新コールバックの無限ループ防止用ガードを実装（自分で書換えた `hide_*` が再評価トリガーにならない）。
- `unregister()` で登録済みタイマー/handler/UIクラスを確実に解除。複数回Enable/Disableしても二重登録しない。
- ハンドラとビュー描画の同時データ書換えについてBlender APIの注意事項に従う。

---

## 8. 選択操作の厳密な定義

### 8.1 Select Members

- `SET` (Select): View Layer内の現行選択を解除し、アクティブグループの所属Objectを選択。
- `EXTEND`: 現行選択を保ち、所属Objectを追加選択。
- `DESELECT`: 所属Objectを選択解除。その他の選択は保持。
- 現在のView Layerに属さないObject、選択ロックされているObject、選択不可な隠れたObjectは**安全にスキップ**し、スキップ数を表示。
- グループ未作成・メンバー0件でもクラッシュしない。
- 選択数などの更新に合わせ、UIのSelected/Inを刷新。

### 8.2 Expand to Groups

1. 現在選択中のObjectの**すべての所属グループ**を逆引き（複数所属を含む）。
2. そのすべてのグループの所属メンバーの和集合を計算。
3. 元の選択は維持し、同View Layerで選択可能なObjectを追加選択。
4. 重複は除去。選択Objectが未所属なら何もしない。
5. Volume Groupを参照する際はUpdate Behaviorに従って必要なら評価。

### 8.3 `In:` 表示

- 選択が1個: `In: Group A / Group B`（0件なら `In: None`）。
- 複数選択: `Common: ...` など全選択Objに共通する所属を明示し、相違がある場合 `Mixed membership` を表示。
- 毎回のPanel.drawで全Sceneをスキャンしない。所属逆引きのキャッシュを活用し、変更時に再構築する。

---

## 9. Duplicate / Merge / Delete のルール

### 9.1 Duplicate Group

共通:

1. Active Groupの設定一式（方式、色、フィルタ、Visibility、評価モード、更新モード等）をコピー。
2. 新UUID、新名前（例 `階段エリア Copy`。重複時に連番）を持たせる。
3. コピー先を新Active Groupにする。
4. コピー元Groupとそのメンバーを破壊しない。

Manual:

- 登録オブジェクトの**参照**をコピー。Objectデータ本体は複製しない。
- 同じObjectが元と複製グループの両方に所属する。

Volume:

- 全Region構造、ADD/EXCLUDE、EmptyのTransform/Shape/Size/Parentをコピー。
- Controller Emptyは**独立した新Objectとして複製**し、既存Collectionにリンク。片方を移動してももう片方は変化しない。
- 同じ旧Emptyが複数Volume行で参照されていた場合は、コピー先では対応する1つの新Emptyを共有する（旧→新マップ）。
- 対象グループのメンバーキャッシュは再評価対象。ダミー人数を単純コピーしない。

### 9.2 Merge Groups（同方式のみ）

- UIでアクティブなGroupが**宛先**。別Groupをダイアログで**ソース**に選ぶ。
- `MANUAL + MANUAL`、`VOLUME + VOLUME` のみ選べる。
- ダイアログにはソースGroupが削除されることと、Object/Emptyは削除されないことを示す。
- `execute()`で**UUIDによって**両Groupの存在と方式を再検証する（グループリストのインデックスを長期間保持しない）。
- 宛先GroupのUUID、名前、色、設定は維持。ソースGroup定義を削除。Undo可能。

Manual:

```text
members(result) = members(destination) ∪ members(source)
```

- ポインター重複なし。どのObjectも一度だけカウント。

Volume:

```text
regions(result) = regions(destination) + regions(source)
members(result) = members(destination) ∪ members(source)
```

- `regions(source)` を独立したRegionのまま移管。Volume定義を1つのRegionへ**平坦結合してはならない**。
- **例:** A = `ADD(廊下全体) - EXCLUDE(階段)`、B = `ADD(階段)` とき、A∪Bは廊下と階段全体をカバーする。単純にADDの後ろにEXCLUDEを連結すると階段が消えてしまうためNG。
- 元Emptyを新グループのRegionが参照し、Emptyは削除しない。名前/色は宛先が優先。
- Objectタイプフィルタや `eval_mode` / `update_mode` が両Groupで異なる場合、Region単位で**評価設定を保存**しないと統合前のメンバー集合を維持できない。**必須設計:** Regionに必要な判定設定（`eval_mode`、Object Typesフィルタ）を保持する。今回は「同じ方式同士ならMerge可能」を満たす必要があるため、**Regionごとに評価設定をスナップショット保持する方法を採用する**。通常の1 Region時はGroup設定と同期し、Merge後は複数Regionの設定を内部に保持・必要なら最小UIで編集可能にする。これを欠くと異なるObject Types/判定設定のグループをMergeしたとき結果が変わる。
- Merge直後の所属結果は事前に確定した各Groupの評価結果の和集合に等しくなり、その後ObjectやEmptyが移動した場合も各Regionの条件で動的に更新される。
- 宛先Groupの`update_mode`は維持し、ソースの`update_mode`は引き継がない（所属判定の内容ではなく更新タイミングのため）。
- ソースがDirtyならMerge前に正しく評価・更新し、結果確認ができるようにする。ただしMANUAL更新方式でユーザーがEvaluateしない方針の場合は、実装が評価内容を一貫して扱えるまでMergeを安全にブロックし、理由を明記する。

### 9.3 Delete Group

- Group定義だけ削除。Objectは一切削除しない。
- 関連する可視性/選択ロック/レンダー制限を再計算。
- Volume Emptyは原則残す。明示的なEmpty削除機能を勝手に追加しない。
- Sceneのアクティブインデックスを適切に補正する。

---

## 10. Visibility/Lock（複数所属に対応）

### 10.1 使用プロパティ

- Viewport: `Object.hide_viewport`
- Selection: `Object.hide_select`
- Render: `Object.hide_render`

`Object.hide_set()`はView Layer単位の目玉相当であり、本件は合意した**モニターアイコン側**の挙動を採用する。これらのObjectプロパティはシーンやView Layerを超えて影響することがあるため、v1のUIは**現在のSceneのGroupを基準に制御する**ものとし、他SceneとObjectを共有する場合の制約をREADMEに明示。別Sceneの設定を破壊しないよう可能な範囲でガードを実装する。

### 10.2 計算規則

1 Objectが複数Groupに属する場合:

```text
restrict_viewport(obj) = any(group.show == False for group in groups_of(obj))
restrict_select(obj)   = any(group.selectable == False for group in groups_of(obj))
restrict_render(obj)   = any(group.render == False for group in groups_of(obj))
```

- **「制限が1つでもあるなら制限する」**。別GroupがONでも、OFFのGroupに所属しているObjectは非表示/ロック。
- Groupに所属しないObjectはアドオンによる変更対象にしない。
- Groupを削除・Merge・Duplicateしたときも、この式から再計算する。

### 10.3 元状態の保存と復元

- 初めてGroupによる制限を適用するとき、対象Objectの `hide_viewport`, `hide_select`, `hide_render` の元値を**項目ごとに**保存。
- Group制限を解除したら、対応する元値へ戻す。元からhide=TrueだったObjectを勝手に表示しない。
- 一部のGroupだけOFFの場合に別GroupがONだからといってObjectを無条件で表示させない。
- ベースラインの追跡情報は `.blend` に保存し、再起動後も破壊的な復元をしない。
- アドオンによる上書き中にユーザーがOutlinerから直接同じ `hide_*` を編集した場合は、どちらの操作が優先するかの競合を検出し、少なくとも一方を無言で潰さない。最小仕様ではGroup制限が有効な間はGroupが優先する旨をREADMEで明記し、元状態復元を保持する。
- 変更したObjectだけ反映する。画面描画ごとに全Objectのフラグをセットしない。

### 10.4 Isolate / Show All

- `Isolate`: アクティブグループのメンバーだけ見える状態へ一時切替。再実行でIsolate前の**グループ表示状態とアドオン管理状態**を復元。
- Isolate中に複数所属しているObjectがActive Groupに属すれば表示可能にする（ただし元々のユーザー非表示状態は尊重）。通常時の「制限優先」ルールに対する**Isolateモードの明示的な例外**。
- Isolate対象外のObjectも非表示の対象にするが、復帰可能なスナップショットを持ち、意図しない永続変更を残さない。
- `Show All`: Isolateを終了し、全Groupの`show=True`にする。その後元々のObject非表示設定を適切に復元。選択可否/Renderスイッチは勝手に全解除しない（名称が表示に限定されるため）。
- 制限を適用できないリンクObject等は警告を返す。

---

## 11. Undo/Redo/保存・読み込み

- 変更を伴うOperatorは原則 `bl_options={'REGISTER', 'UNDO'}`。
- Add/Remove Selected、Duplicate、Merge、Add/Remove Volume、Fit to Selection、Isolate、Show All、グループ削除、並べ替え等が1回のUndoで直前の状態へ戻る。
- Undo/Redoで逆引き、評価メンバー、Dirty、表示ベースラインが整合すること。必要に応じメンバーキャッシュを破棄し再評価。
- `.blend`をSave→Close→OpenしてManual所属、VolumeのEmpty参照、複数Region、色・方式・フィルタ、Visibilityの状態が復元されること。
- 読込時は古いキャッシュ・Python側のObjポインターを使用せず、関連GroupsをDirtyに設定して再構築。
- Controller Emptyが削除された `.blend` を開いてもパネルが落ちず、Missing表示になること。
- Script再実行やAddon Reloadでクラスの重複登録/handlersの重複が発生しないようにする。`register()`/`unregister()`を冪等に近い動作にし、標準アドオン形式（フォルダ+`__init__.py`）を優先。

---

## 12. 大規模シーンの性能要件

### 12.1 守るべき原則

- `Panel.draw()` / `UIList.draw_item()`からScene全走査・BBox判定・ソートを行わない。
- BlenderのDepsgraph handlerで毎回50,000 Objectsを走査しない。
- Origin/BBox座標の大量判定はNumPy配列化を優先し、候補Objectを必要に応じキャッシュ。
- 元の属さないObjectも含めて全Objectに `hide_viewport` 等を毎回書き込まない。**変更差分のみ**反映。
- `foreach_get/foreach_set` は実際にそのRNA Collection/Propertyで利用可能か実機で検証してから使用。`matrix_world` の一括取得が可能だと**仮定しない**。非対応時はObjループで配列を構築してNumPyで判定。
- Volume数×Object数が多い場合はBroad-phase（AABB候補除外）で不要な精密判定を省略。
- グループメンバーの逆引きは都度全Groupを走査せず、変更時にキャッシュ再構築。
- 低コストOrigin評価を最適化優先。Bounds/Any Overlapは重くても正確性を優先し、必要に応じ警告。

### 12.2 性能検証

以下のデータセットで計測値をREADMEに記録する（**推奨測定条件であり、未検証の数値保証はしない**）。

| テストシーン | 操作 | 計測値 |
|---|---|---|
| 1,000 Object / 2 Box | Evaluate Origin | 実測ms |
| 10,000 Object / 4 Box | Evaluate Origin | 実測ms |
| 50,000 Object / 10 Box/Sphere | Evaluate Origin | 実測ms、RAM変化 |
| 10,000 Object / 4 Volume | 連続Emptyドラッグ、On Demand | UI応答性・handler実行時間 |
| 10,000 Object / 4 Volume | LIVEで複数Obj移動 | デバウンス回数、スタッター有無 |
| 10,000 Object / 重複Group | Visibility Toggle | 実測ms |

性能が未達ならアルゴリズム上のボトルネック、対応済み最適化と未解決事項を報告。テストを省略して高速だと断定しない。

---

## 13. 主要オペレーター（想定ID）

同じIDを再利用できるなら、v0.2 UI操作を壊さないこと。

| Operator | 必須挙動 |
|---|---|
| `lg.group_new` | 新規Group（Manual初期値） |
| `lg.group_remove` | Groupだけ削除 |
| `lg.group_move` | Group表示順の変更 |
| `lg.group_duplicate` | Group/設定/Manual参照 or Volume Emptyを複製 |
| `lg.group_merge` | UUIDベースの同方式Merge（候補フィルタ/再検証） |
| `lg.add_selected` | Manualへ選択Objを追加 |
| `lg.remove_selected` | Manualから選択Objを解除 |
| `lg.select_members` | SET/EXTEND/DESELECT |
| `lg.select_groups_of_selection` | 選択Objの所属Groupの全メンバーへ拡張 |
| `lg.volume_add` | Box/Sphere Controller作成 |
| `lg.volume_remove` | 参照解除、Empty維持 |
| `lg.fit_to_selection` | 選択BBoxを包含するBox Volumeを作成 |
| `lg.evaluate` | Volume再評価 |
| `lg.isolate` | Active Groupの一時単独表示/復帰 |
| `lg.show_all` | 全GroupのshowをON、Isolate解除 |

- `lg.export_csv`、Export関連Operatorは**登録しない**。
- Operatorの`poll()`と`execute()`で安全性をチェック。UIに候補が表示されないだけでは不十分。
- APIの名称は可能な限り維持しつつ、製品実装ではモジュール・登録Class接頭辞をユニークに保つこと。

---

## 14. 受け入れテスト（Codexが必ず実施）

テストは自動化できるところをBlender Background/`bpy`スクリプトで作り、UI固有操作を手動手順で補完。**期待値を明示**すること。

### 基本・Manual

- **T01** 新規SceneにGroupがない。AddでManual Group作成。Collectionが増えない。
- **T02** Mesh A,B選択→Add Selected→2件。再度Addで重複せず2件。
- **T03** Manual Group X/Y両方にA登録。Aの所属はXとY。XからRemoveしてもYに残る。
- **T04** XのSelect/Extend/DeselectはSET/加算/減算の期待結果になる。
- **T05** A選択→Expand to Groupsで、Aが属するすべてのGroupのメンバーの和集合を選択。
- **T06** 名前変更/グループ並べ替え後もManual所属が変わらない。
- **T07** 空選択でAdd/Remove/Expandしてもエラーにならない。

### Volume

- **T08** Boxを3Dカーソル位置に作成。Inner/Outer ObjectがOriginで正しく分類。
- **T09** Sphereの内外・境界点が正しく分類。非等方Scaleで楕円体になる。
- **T10** Empty/Objectの回転、Scale、親子Transformが判定に反映。
- **T11** ADD2個+EXCLUDE1個で結果が順序に依存しない。
- **T12** Origin/Bounds Center/Fully Inside/Any Overlapが意図した違いを示す。BBoxがVolumeを包むが頂点がVolume内にないOverlapケースもTrue。
- **T13** Mesh/Light/Camera/Curve/Empty/Otherのフィルタを切替可能。Controller Emptyが候補から除外される。
- **T14** Fit to Selectionで選択ObjのBBoxをBox Emptyが包含。
- **T15** Missing Empty / Scale 0 / 非対応Empty形状 / BBoxなしObjectでクラッシュせず警告。
- **T16** On DemandのDirtyはEvaluate前に実メンバー操作したとき自動更新、Manual更新はEvaluateを要求。
- **T17** LiveはControllerまたは対象Object移動後に自動更新し、連続変形時に過度なEvaluateを実行しない。

### Duplicate / Merge

- **T18** Manual Duplicateでは参照がコピーされるがObject自体の数は増えない。
- **T19** Volume Duplicate後、元Emptyを動かしても複製側のEmptyは動かない。
- **T20** Manual+Manual Mergeは和集合、重複なし、ソースGroup削除、Object削除なし。
- **T21** Volume+Volume Mergeは独立RegionのOR。`A=Box1-ExcludeBox`, `B=ExcludeBox` で除外範囲が戻り、単純連結による誤結果が起きない。
- **T22** 異なる`eval_mode` / Object Types設定を持つVolume Groupsでも、Merge前後のメンバー集合が一致する。Merge後もEmpty移動による結果を確認。
- **T23** Manual+Volume Mergeは候補に表示されず、強制オペレーター実行でも拒否。
- **T24** Merge後の宛先Group UUID/名前/色は維持、ソース削除。Delete Groupでも元Object/Emptyは残る。

### Visibility / 永続化 / 安全性

- **T25** AがX/Yに所属。X非表示・Y表示ならA非表示。Xを再表示すると元の表示状態に戻る。
- **T26** もともと`hide_viewport=True`のObjは、Group ON / Show Allで勝手に表示されない。
- **T27** Lock / Renderの設定も複数所属時に制限優先で、解除後に元状態を復元。
- **T28** Isolate→再実行で元の表示状態復帰。Show All後も元から隠れていたObjectは隠れたまま。
- **T29** Add/Remove/Merge/Duplicate/Volume追加操作のUndo/RedoでGroup、メンバー、Emptyが一致。
- **T30** `.blend`保存→再起動/再読込後にManual/Volume/Region/設定と元のhide状態が整合。
- **T31** アドオンEnable→Disable→Enable、スクリプト再実行等でクラス/handlerの多重登録がない。
- **T32** UIリストを描画/展開してもシーンの所属評価を毎フレーム実行しない。
- **T33** UIに`Both`, `Export`, `CSV`, 書き出し用ボタン、`[MOCK]`の表示がない。
- **T34** 手動でCollectionを変更してもアドオンのグループ定義は維持。Add Group等によって新規Collectionが作られない。
- **T35** Group削除→残るGroupから対象Objectを選択可能で、他の所属が保持される。

**合格条件:** T01〜T35に対しPass/Fail/Blockedを記録し、Failが残る状態を「完成」と報告しない。実機未実行項目は`NOT RUN`と明記。

---

## 15. 品質・エラー処理

- 無効Group index/UUID・削除されたPointer・View Layer非所属Object・Edit Mode中の選択操作などを検知して安全に中断/スキップする。
- 可能ならObject Modeで動作させ、Edit Modeからの操作は明確なエラーメッセージとする。勝手に作業モードを変えない。
- Undoできない外部状態を勝手に編集しない。
- `Operator.report({'INFO'|'WARNING'|'ERROR'}, ...)` を適切に用いる。
- Python例外を黙って捕捉・握り潰して成功を返さない。失敗内容をコンソールとUIに伝える。
- 新規生成Emptyの名前は `Vol_<Group>` のように分かりやすく、必ず一意にする。
- Blender 4.5用に存在しないIconやAPIを使わない。`IndentationError`のようなコード破損を避け、ファイルを丸ごと構文検証する。
- NumPy/GPU/タイマーなどの機能はBlender内での利用可否を実機確認する。

---

## 16. 開発順序（Codex実装フェーズ）

1. **基盤・永続化:** Add-on登録、Group UID/Sceneデータ、Manual参照、基本UI、キャッシュ。
2. **Manual・選択:** Add/Remove Selected、複数所属、Select/Extend/Deselect/Expand。
3. **Volume:** Empty作成/参照解除、Region、判定幾何、Object Types、Fit、Evaluate、Dirty。
4. **操作:** Duplicate、同方式Merge、Region維持、Volumeの異なる設定の統合。
5. **表示制御:** Viewport/Select/Render、ベースライン、Isolate、Show All、複数所属競合。
6. **監視・性能:** depsgraph/timer、DIRTY/LIVE、差分適用、ベンチマーク。
7. **品質保証:** Undo/Redo、Save/Load、テストT01〜T35、ドキュメント・インストールパッケージ。

各フェーズ終了時点で既存機能を壊さず、アドオンの起動/登録/終了が正常であることを確認。危険な仕様の省略を後続フェーズへ黙って先送りしない。

---

## 17. 推奨ファイル構成と納品形式

```text
zone_groups/
    __init__.py        # bl_info / register / unregister
    properties.py      # PropertyGroup / 永続化スキーマ
    membership.py      # Manual / 結果セット / 逆引き
    volume.py          # Region・幾何判定・ADD/EXCLUDE
    operations.py      # Group / Manual / Merge / Duplicate / Select
    visibility.py      # hide_* / baseline / Isolate
    handlers.py        # Dirty / Live / cache invalidation
    ui.py              # Panel / UIList / ダイアログ
    migrations.py      # 可能なら旧モック形式を認識
README.md              # 導入、操作、既知の制約
TEST_RESULTS.md        # 実機・自動テスト結果
scripts/
    test_zone_groups.py
    benchmark_zone_groups.py
```

- アドオンZIPでインストール可能にする。
- Blender Preferences→Add-ons→Install from Diskから導入できること。
- v0.2モックは同梱してよいが、**アドオンとして同時ロードしない**。参照は `reference/zone_groups_ui_mock_v0_2.py` 等へ隔離。
- READMEにBlenderバージョン、利用手順、Volumeモードの意味、各更新モード、Mergeの規則、独立Empty複製、パフォーマンス検証条件、仕様の限界、既知の制約を記載。
- `TEST_RESULTS.md`にテストごとのPass/Fail/NOT RUN、実行したBlenderバージョン、OS、発生例外と修正状況を記載。

---

## 18. 実装時に注意する落とし穴

1. **単純Mergeの破綻:** VolumeのADD/EXCLUDEを平坦に結合しない。Regionを別々に評価してORする。
2. **Merge時の設定差:** Box/Excludeだけでなく`eval_mode`やObject Typesが異なると集合が変わる。Regionに判定設定を保持する。
3. **Group IDとIndex:** UIListのIndexを永続IDとして使用しない。Mergeダイアログ等はUUIDが必要。
4. **複数所属とVisibility:** 1つのGroup操作で別Group所属を消さない。hide状態を原状復帰できるようにする。
5. **`Object.hide_set()`の誤用:** モニター相当のグローバルフラグを使うこと。
6. **Volume Empty参照解除:** Emptyを削除しない。Duplicateだけは独立Emptyを新規作成。
7. **`Panel.draw()`の重い処理:** 結果キャッシュとDirtyのみ表示。
8. **bpy RNA `foreach_set`仮定:** そのコレクション/プロパティで検証せず使用しない。
9. **Bound Box判定の誤実装:** Any Overlapを角8点の包含だけで済ませない。
10. **直接ボタンでの未実装:** UI見た目だけでFINISHEDを返さない。
11. **BlenderのLoad/Undo:** Python側キャッシュは無効になるので保持し続けない。
12. **Methodの違い:** Membership=ManualとUpdate Behavior=Manualは別の設定。
13. **Scene/Object共有:** hide_*はObjectに作用するため、複数Sceneで同じObjectを使うケースは影響の範囲を明記・テスト。
14. **旧モックの偽カウンター:** Migration後に128件などのダミー数値を本物の結果として出さない。
15. **Collectionの解釈:** 既存CollectionにEmptyをlinkするのは許可。論理グループ用にCollectionを新設して管理するのは禁止。

---

## 19. 参考API・確認先

- [Blender 4.5 Python API — bpy.props](https://docs.blender.org/api/4.5/bpy.props.html)
- [Blender 4.5 Python API — Application Handlers](https://docs.blender.org/api/4.5/bpy.app.handlers.html)
- [Blender Python API — Object (`hide_viewport`, `hide_select`, `hide_render`, `hide_set`, `bound_box`)](https://docs.blender.org/api/4.5/bpy.types.Object.html)
- [Blender 4.5 Release Notes — Python API](https://developer.blender.org/docs/release_notes/4.5/python_api/)
- 同梱 `zone_groups_ui_mock_v0_2.py` がUIレイアウトと現時点のボタン名の第一参照資料。

---

## 20. 完了時にCodexが報告する内容

1. 完成したアドオンのファイル構成とインストール方法。
2. 実装できた項目・意図的に省いた項目。
3. T01〜T35の結果、Blender実機のバージョン。
4. VolumeのMergeがRegionで正しく保持されることを示す具体例。
5. 多数Objectにおける評価時間・Dirty/Liveの監視負荷。
6. `hide_*`・複数Scene・Bound Boxの既知の制約と回避策。
7. 旧モック形式の移行可否。
8. `[MOCK]`機能・Export UIが残っていないことの確認。

**最終完了条件:** インストールできることだけでなく、Manual/Volumeの所属判定、選択、複数所属、同方式Merge、Duplicate、Visibility、Undo/保存が正しく動き、受け入れテスト結果が提出されていること。
