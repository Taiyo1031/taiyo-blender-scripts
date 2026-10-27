# Taiyo Object Groups 1.0.1 — 検証結果

1.0.1追加確認: Blender 4.5.9 / 5.2.2で繰り返しの.blend読込後に監視タイマーを保持する回帰テストPASS。4.5.9のBackground統合テスト再実行PASS。5.2.2の実UIデモで読込後のLive移動・所属復元PASS。以下の包括的なUI/Undo/性能結果は1.0.0時点の実測で、1.0.1での全再実行はNOT RUN。

検証日: 2026-10-27（日本時間）。Blender **4.5.9 LTS** / macOS 27.0.1 / arm64 / NumPy 1.26.4。
対象: Blender 4.5.9以降の4.5 LTS。Windows／Linuxおよび他パッチ版は **NOT RUN**。

## 受け入れテスト

以下は同梱テストで実行した代表シナリオの結果です。すべてのObject型・ライブラリ・制作Sceneの組合せを網羅するものではありません。T17/T32は実UIタイマー、T29は実UIのnative Undo/Redo、その他はBackground統合テストを基本とします。

| ID | 内容 | 結果 |
|---|---|---|
| T01 | 新規グループ・Collection非作成 | PASS |
| T02 | Manual追加・重複防止 | PASS |
| T03 | 複数所属・個別解除 | PASS |
| T04 | Select/Extend/Deselect | PASS |
| T05 | 所属グループへの選択拡張 | PASS |
| T06 | リネーム・並べ替え | PASS |
| T07 | 空選択の安全処理 | PASS |
| T08 | Box原点判定 | PASS |
| T09 | Sphere・境界・非等方Scale | PASS |
| T10 | 回転・親Transform | PASS |
| T11 | ADD/EXCLUDE順序独立 | PASS |
| T12 | 4判定方式・包含Overlap | PASS |
| T13 | Object Types・Controller除外 | PASS |
| T14 | Fit to Selection | PASS |
| T15 | Missing・ゼロScale・非対応Shape | PASS |
| T16 | Manual/On Demand更新 | PASS |
| T17 | Live・ドラッグデバウンス・Object移動 | PASS |
| T18 | Manual Duplicate | PASS |
| T19 | Controller独立Duplicate | PASS |
| T20 | Manual Merge | PASS |
| T21 | Region ORによるMerge | PASS |
| T22 | 異なる判定条件のRegion維持 | PASS |
| T23 | 異方式Merge拒否 | PASS |
| T24 | UUID維持・Object非削除 | PASS |
| T25 | 複数所属の表示競合 | PASS |
| T26 | 元から非表示の状態保全 | PASS |
| T27 | Select/Render制限と復元 | PASS |
| T28 | Isolate/Show All復元 | PASS |
| T29 | UIでのUndo/Redo | PASS |
| T30 | 保存・再読込 | PASS |
| T31 | 再有効化・handler重複防止 | PASS |
| T32 | UI描画から評価しない | PASS |
| T33 | 禁止UI・未実装表示なし | PASS |
| T34 | Collectionから独立 | PASS |
| T35 | 削除後の他所属維持 | PASS |

追加検証: Top Group／Overlap Color、順序変更、元色復元、Scene共有時の上書き拒否、部分適用後のCancel、接触・shear・平坦BBox、管理Object削除直後の無効化を確認。再有効化時の制限復元と、別Blenderプロセスでの複数Region再読込もPASS。

UI UndoテストはAdd/Remove Selected、Duplicate、Merge、色、Isolate、Show All、新規グループ、方式変更、Volume追加、Fit、削除の前後を往復比較しています。

## 性能実測

共有Mesh（2頂点）のObjectを格子状に配置。Origin評価。測定時間は計算処理の累計で、UIのタイマー待ち・描画時間は含みません。1回測定の参考値です。全モデルで無変更時の追加フラグ書込みは0件でした。

| Objects / Volumes | 初回評価 ms | 1 Object差分 ms | 評価の最大処理区間 ms | 非表示 ms | 復元 ms | 対象メンバー |
|---|---:|---:|---:|---:|---:|---:|
| 1,000 / 2 | 9.02 | 6.67 | 5.15 | 5.94 | 2.25 | 136 |
| 10,000 / 4 | 77.53 | 1.52 | 5.43 | 710.44 | 202.48 | 1,877 |
| 50,000 / 10 | 394.68 | 3.40 | 7.01 | 10336.86 | 2465.55 | 4,037 |

1万Object全件をManualにも所属させた重複グループの表示切替: 非表示 **3.76秒**、復元 **1.06秒**。最大処理区間はそれぞれ 6.12ms / 6.97ms。

5万Object評価時のプロセス最大RSS増分は約 27.0MiB（累積ピーク差分。常駐メモリ全体ではありません）。

1万Object／4 Boxの実UI検証では、Controller連続移動中は評価0回、停止後1回、対象Objectの移動も更新されました。監視handler最大 **2.80ms**。Undo/制限変更等を含む全UI操作の最大分割区間は **70.07ms**。5msは目標であり上限保証ではありません。

## 制約と改善内容

- Scene所属をObjectごとにRNA検索する処理を集合キャッシュへ変更し、5万Object初回評価の初期実装約92秒を約0.4秒まで改善しました。
- 復元情報はObject側のPropertyGroupに保存し、所有Scene UUIDで競合を防ぎます。SceneのObject参照リストへの大量追加を避けています。
- 初期UIテストの100秒タイムアウトを修正後、1万Objectの制限・Undo/Redo・Cancelを含むUIテストが完走しました。Cancel検証は速い環境でも部分適用状態を作る専用テスト窓を使用します。
- hide_viewport等のBlender内部更新は評価より重く、大量の表示変更は分割しても完了まで数秒以上かかります。大規模Sceneでの無スタッターは保証しません。
- Any OverlapはBBox基準。Modifier評価結果のメッシュCSGではありません。
- オブジェクト表示色はSolid/Object Colorで確認します。Material/Rendered表示のマテリアル色を変更しません。
- 旧モックの自動移行は対象外。旧データは削除せず、新アドオンで再作成してください。

実行スクリプトと機械可読結果はリポジトリの `tools/` と `tools/reference/zone_groups/results/` にあります。
