# Taiyo Object Groups

対象Version **1.1.0** / Blender **4.5.9以降**（4.5.9 LTS／5.2.2 LTSで検証）。Taiyo Blender ExtensionsのRemote Repository、または `zone_groups-1.1.0.zip` を「Install from Disk」でインストールしてください。

Collectionを増やさず、Objectを任意の論理グループに分類します。ManualとVolumeの複数所属、グループの複製・統合、表示・選択・Render制限、グループ別の色分けに対応します。書き出し機能はありません。

## 操作

3D ViewportのNパネル → **Groups**。操作はObject Modeで行います。

- `New`：空のManualグループを作成。`From Selection`：選択Objectを登録したManualグループを作成。名前・色を編集できます。
- `Add Selected / Remove Selected`：選択Objectとの所属関係だけを変更します。元Objectは変更しません。
- `Select / Extend / Deselect`：所属Objectの選択を置換／追加／解除。非表示・選択ロック・View Layer外のObjectはスキップします。
- `Expand to Groups`：選択Objectが属する全グループのメンバーへ選択を広げます。
- `Duplicate Group`：Manualでは参照をコピー。VolumeではController Emptyを独立複製します。
- `Merge Groups`：同方式のソースをアクティブグループへ統合します。ソースのグループ定義だけを削除し、Object／Emptyは残します。
- `−`：グループ定義だけを削除。↑↓は一覧順を変更します。
- 長い操作は分割して進み、Esc／右クリックでCancelできます。Cancelは設定と適用済み表示・色を元に戻します。各操作は1回のUndoで戻せます。

Manualメンバー、またはVolume参照が残るグループは所属方式を変更できません。空にしてから切り替えてください。旧v0.2モックの自動移行は行いません。旧モックを無効化して新アドオンで作り直してください。既存のモックデータは削除しません。

## Volume

Membership ModeをVolumeへ切り替え、`+` からBox／Sphereを追加します。Emptyは3Dカーソル位置の既存Collectionに置きます。各Volume行の選択アイコンで参照Objectを選択できます。非表示／選択ロックは自動解除しません。`−` は参照解除のみで、Emptyを削除しません。Controllerとして参照中のEmptyは自動所属から除外されます。

- 各Regionは「ADDの和集合 − EXCLUDEの和集合」。Volumeの順番には依存しません。
- Merge後はRegionごとに独立した条件を保持し、各Regionの結果をORで合成します。Regionボタンで編集対象を選びます。
- 例：A=`大きいBox − 小さいBox`、B=`小さいBox`。Merge後は小さいBoxの内部も所属し、A側のEXCLUDEがB側へ漏れません。
- Shape、Size、Scale、位置・回転・親Transformが判定へ反映されます。非等方ScaleのSphereは楕円体です。Scale 0、Missing、非対応Shapeは警告して判定から除外します。
- `Fit to Selection`：選択ObjectのBBoxを包含するBoxを作成。初期余白は0.01 Blender unitです。

| Test | 判定 |
|---|---|
| Origin（初期値） | Objectの原点。最速 |
| Bounds Center | 元ObjectのBBox中心 |
| Fully Inside | 1つのVolumeにBBoxの全8頂点が入る |
| Any Overlap | BBoxとVolumeが接触または交差。内包も検出 |

BBoxがないObjectは原点へフォールバックします。元ObjectのBBoxを使うため、Modifier／Geometry Nodesの評価結果や実メッシュの交差を保証しません。BoundsモードもVolumeごとの判定結果にADD／EXCLUDEを適用する方式で、厳密なCSGの差集合とは異なります。Box交差はSAT、SphereはVolumeローカル空間で凸二次問題の境界候補を解き、shear・楕円体・包含を扱います。境界許容差はVolumeローカル座標で1e-7です。

### Update Behavior

- **On Demand（初期値）**：変更時はDirtyにし、実メンバーが必要な操作で評価します。パネル描画では評価しません。
- **Manual**：`Evaluate`で明示更新。Dirtyのままメンバー操作をすると評価を要求します。
- **Live**：変更が約300ms落ち着いたあと自動更新します。連続ドラッグ中は評価を繰り返しません。

Dirtyの人数は前回の値です。評価は段階的に計算し、全結果の完成後に所属を確定します。評価中にSceneが変わった場合は古い結果を捨てます。ManualのDirtyグループが残る場合は、全体の表示・色の再適用を保留することがあります。`Evaluate`は全グループを更新します。

## Visibilityと色分け

ViewportはOutlinerの**モニター**相当、Selectは選択ロック、Renderはレンダー制限です。複数所属時は1つでも制限があれば制限します。各項目の元値をObject側へ永続保存し、Sceneの所有UUIDで管理するため、元から非表示だったObjectをShow Allで勝手に表示しません。

一覧の各行の`Isolate`はそのグループだけを一時表示し、同じ行の再実行で戻り、別行では対象を切り替えます。複数所属の競合よりIsolate対象を優先しますが、元の非表示状態は尊重します。`Show All`はIsolateとグループの表示制限だけを解除し、Select／Renderは変更しません。

一覧上部の **Global Settings / All Groups** → `Group Colors`で色分けをON（初期値OFF）。`Show Object Colors in This View`で現在の3D ViewをSolid／Object Colorへ切り替えます。

- **Top Group（初期値）**：一覧で最も上にある所属グループの色。↑↓で優先順位を変更できます。
- **Overlap Color**：2つ以上のグループに所属するObjectを指定色にします。初期値はマゼンタ。
- 「重複」は複数所属であり、Object同士の空間交差ではありません。
- 元のObject表示色を保存し、色分けOFFや最終所属解除で復元します。マテリアルは変更しません。

表示／色の上書き中はグループ設定が優先です。OutlinerやObject Propertiesで同じ項目を直接変更する代わりに、先にグループ側の制限を解除してください。元値は上書き前の値を保持します。同じObjectを共有する他SceneへもObjectプロパティの変更は影響します。他Sceneが先に管理中の場合は警告して上書きをスキップします。元Sceneで制限・色を解除すると別Sceneから管理できます。読み取り専用のリンクObjectのフラグ変更はスキップします。

Undo／Redo／Load時は実行時キャッシュを破棄します。保存中の分割処理はCancelし、未完了の部分状態を保存しません。アドオンを無効化すると管理中の表示・色を復元します。

## 性能・検証

UI描画からScene走査を行いません。Objectの逆引き、座標、種類をキャッシュし、Origin／Boundsの判定をNumPyで処理します。変更Objectの差分評価を優先し、表示・色は実際に値が変わるObjectだけ書き換えます。初期計算、設定保存、表示適用は約5msを目標とする協調分割処理で、Blenderの単一RNA操作やOSスケジューラにより超過する場合があります。

実測値・環境・制約は [TEST_RESULTS.md](TEST_RESULTS.md) を参照してください。大規模Sceneのモニターフラグ変更はBlenderの依存グラフ更新が重く、評価より時間がかかります。5万Objectの処理速度はポリゴン数・Modifier・親子関係にも依存し、数値保証はしません。Windows／Linuxは未実行です。

テストコードはリポジトリの `tools/test_zone_groups.py`、`tools/ui_test_zone_groups.py`、`tools/ui_test_zone_groups_undo.py`、`tools/benchmark_zone_groups.py`。元モックと仕様書は `tools/reference/zone_groups/` に隔離しています。

## 1.0.1から継承した修正

.blend読込後にもLive更新・選択情報更新が継続するよう、監視タイマーを永続登録に変更しました。Blender 5.2.2 LTSで体験デモの読込後も確認しています。

## 1.1.0：Mesh VolumeとUI整理

Members／Visibilityは初期状態で閉じます（既存ファイルの開閉状態は保持）。進捗・警告領域は固定し、詳細は情報アイコンで確認できます。CancelまたはEscで更新を中止できます。色分け・Show Allは一覧上部の全体設定です。EmptyのShapeはBox／Sphereだけを選択できます。

Membersの`+` → **Register Existing Mesh**で、既存の閉じたMeshを指定します。選択中のアクティブMeshが初期候補です。Meshの新規作成はBlender標準機能で行ってください。登録元Objectの表示方法やRender設定は変更しません。内部Objectを見たいときは、VolumeのViewport DisplayをWireにすると便利です。

- 凹形状やトーラスの貫通穴に対応します。面は閉じた単一の連結面集合で、法線の向きが整合している必要があります。穴あき境界・非多様体・遊離頂点／辺・退化面・自己交差はエラーです。
- 元メッシュを判定に使用し、Modifier／Geometry Nodesは無視します。必要な場合は事前に適用してください。Mesh含有RegionのTestはOrigin／Bounds Centerのみです。既存のFully Inside／Any Overlap Regionでは先に方式を変更してください。
- EmptyとMeshを同じRegion内でADD／EXCLUDEとして混在できます。Merge後もRegionは独立したOR結合です。Controller自身は自動所属対象外です。
- 非等方Scale・負Scale・親によるshearを座標変換へ反映します。表面上は内部です。極端に薄い形状や数値的に曖昧な交差は結果を推測せずエラーにします。境界許容差はVolumeの最大寸法の約1e-7です。
- 不正なMeshでは前回の確定結果を保持しDirtyと警告を表示します。初回未評価ならメンバーは未確定です。Live失敗後は関係データが変わるかEvaluateを押すまで再試行しません。
- Meshデータごとに形状/BVHを共有キャッシュし、Transform変更時は再構築しません。頂点・面の変更やUndo／Loadでは必要なキャッシュを再構築します。依存グラフの大規模な再構築では安全のため全形状キャッシュを無効化します。
- Duplicateは参照MeshのObjectとMeshデータを独立複製します。参照解除・グループ削除は元Meshを削除しません。
- 評価は分割しますが、Blender内部の三角形化・BVH構築・交差候補作成は分割できません。低ポリゴンを推奨し、重いMeshや大規模SceneではOn Demand／Manualを選んでください。5msは目標であり応答時間の保証ではありません。

検証スクリプト: `tools/test_zone_groups_mesh.py`、`tools/benchmark_zone_groups_mesh.py`。旧1.0.xのEmpty参照はそのまま読み込めます。

### Mesh Liveの目安（1.1.0）

このMacの5万候補・256/1024三角形では評価は約0.6〜0.8秒規模でした。実測はTEST_RESULTS.mdを参照してください。BVH構築と交差候補列挙は一括APIのため中断できず、高密度Meshや大量表示変更では5msを超えます。まず単純なMeshでLiveを試し、操作待ちが気になる場合はOn Demandを使用してください。5msや300msは応答保証ではありません。
