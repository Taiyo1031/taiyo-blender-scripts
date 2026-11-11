# Map Roundtrip 検証報告

対象version: Map Roundtrip Tools **0.1.0** / Unreal Bridge Tools **2.3.0** / Taiyo Extension Manager **1.0.17**

検証日: 2026-11-11（日本時間）。macOS arm64、Blender **4.5.9 LTS** / **5.2.2 LTS**。外部のHoudini／Unrealは実行対象外です。

## 結果

配置・FBXの統合回帰と実UIのESC復元は合格しました。**6万件での生成時間の線形性、および最大0.5秒のUI応答目標は未達です。** Mesh共有のリンク複製方式は維持しています。

## 性能（秒）

| 件数 | CSV Selected | CSV Collection | plan | 生成＋最終同期 | Archive | Replace全体 | 最長単一step |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.268 | 0.243 | 0.037 | 4.314 | 0.034 | 4.416 | 0.728 |
| 30,000 | 0.829 | 0.719 | 0.142 | 59.327 | 0.105 | 59.645 | 2.139 |
| 60,000 | 1.649 | 1.501 | 0.278 | 281.792 | 0.262 | 282.516 | 3.878 |

10万点・全4ゾーン（5個のCube）のnumpy判定: **0.01374秒**（点の取得・選択適用を除く）。planは6万行でも3秒未満です。CSV Selectedは同一シーンのCollectionより約10%遅く、厳密な「同等以上」の目標は未達です。既存UBT回帰の別シーンでは6万行2.731秒でした。

![実測グラフ](benchmark_4_5_9.png)

生成は1万→3万→6万で約4.31→59.33→281.79秒となり、線形ではありません。Archiveは約0.034→0.105→0.262秒で、二次関数的な増加は見られませんでした。生成値には最後の依存グラフ同期が含まれます。単一stepはgeneratorのyield間隔で、timer全体の上限を保証する値ではありません。最長stepが0.5秒を超えるため、大規模処理の応答目標は満たせません。

### 原因切り分けと対策

- 既定の新規Collectionはシーン未リンク状態で充填します。既存Collectionは変更せず再利用します。
- 同名Objectの自動連番探索を避ける名前集合・連番キャッシュを追加しました。
- 切り分け用の1万Object試験では、評価済みシーンでObject.newが約5.29秒、linkが約0.022秒でした。未リンクCollectionでもObject.new約13.06秒・link約0.025秒で、Collection未リンク化だけでは解消しませんでした。Object.newとlinkを別フェーズに分ける試験もObject.new約5.26秒で解消しませんでした。
- 既存Collectionへの処理件数調整は、時間予算内で最大8192ステップまで自動調整します。最終同期や単一FBXオペレーターは分割できません。
- 計測には複数Blenderの一部実行時間帯が重なっています。再現用スクリプトと生JSONを同梱し、絶対時間は参考値とします。非線形傾向は対策前後の両方で再現しました。

## 仕様書§9.2 受け入れ16項目

| # | 結果 | 確認内容・制約 |
|---:|---|---|
| 1 | 合格 | 回転・スケール付きCube、複数領域、重複時のZONE_A優先を確認。 |
| 2 | 合格 | Selectedの行数・12列・名前・ワールドTransformを確認。6万行出力も実行。 |
| 3 | 合格 | 正常終了時だけタグ付与。ESC・エラー・一時出力再試行では中途タグなし。 |
| 4 | 合格 | 選択ゼロのエラーとファイル未作成を確認。 |
| 5 | 合格 | Previewの旧／新件数と非変更を確認。6万行planも一致。 |
| 6 | 合格 | Archive除外・所属移動・タグ変更・位置回転スケール・Mesh共有を確認。 |
| 7 | 未検証 | TransformとMesh共有の自動比較は合格。人による画面の目視比較は未実施。 |
| 8 | 合格 | 同じゾーンの再実行で現在タグ総数が一定、過去配置が追加Archive。 |
| 9 | 合格 | 作成中・Archive中・タグ変更中のESC／例外を検証。所属・タグ・一時hide・選択を復元。実UIは2000件。 |
| 10 | 合格 | Delete後の現在タグ数・共有Meshを確認。batch_removeを使用。 |
| 11 | 合格 | 未解決名のスキップ・集計と先頭5件表示を実装。 |
| 12 | 合格 | 未知colnameのMap直下Collection作成を確認。 |
| 13 | 合格 | Blender製FBX代用でSKIP／UPDATE／Material再利用を確認。UPDATE途中の中断でも旧Mesh参照へ復元。 |
| 14 | 合格 | Per Objectの12ファイル、サニタイズ、既存パスの連番、Combined、選択・active維持を確認。 |
| 15 | 合格 | LINEAR既定とカラー属性を含むFBX往復を確認。Unreal内の見た目は未検証。 |
| 16 | 不合格 | 6万件のCSV・plan・生成・Archiveを計測。生成線形性と0.5秒目標は未達。全16操作の6万件実UI再実行は未実施。 |

## 要検証3件

1. **FBX importer**: 4.5.9・5.2.2とも`wm.fbx_import`。旧Python版へのfallbackは模擬的なAPI欠落で回帰検証しました。
2. **temp_override**: 採用。複数選択中に1個だけ出力したFBXを再取り込みし、Mesh Objectが1個だけになることを両バージョンで確認しました。
3. **link線形性**: link単体より評価済みシーンでのObject作成が支配的でした。新規Collectionの未リンク充填と時間予算調整を採用しましたが、生成の非線形性は残っています。

## 変更・追加ファイル

- UBT: `__init__.py`、`preset_utils.py`、`blender_manifest.toml`、`README.md`、`Unreal_Bridge_Tools_使用書.md`を更新。`constants.py`、`zones.py`を追加。
- MRT: `__init__.py`、`constants.py`、`props.py`、`presets.py`、`chunked.py`、`fbx_export.py`、`mesh_import.py`、`placement.py`、`ui.py`、`blender_manifest.toml`、`README.md`、本報告、ベンチJSON／PNG、`tools/bench_make_scene.py`を追加。
- リポジトリ: `tools/test_map_roundtrip_tools.py`、`tools/benchmark_map_roundtrip_tools.py`、`tools/ui_test_map_roundtrip_tools.py`を追加。Extension Managerの本体／manifest／README、ビルド対象、README一覧、AGENTS、配布ZIP／indexを更新。

## 既定値と公開範囲

仕様書§11を採用しました。追加の実装上の既定は、非有限数値を不正行としてスキップすること、特異なゾーン変換をエラーにすること、復元中の再中断を抑止することです。FBX既定値やCSV列は変更していません。

配布indexは既存27件にMRTを加えた**28件**です。Object Groupsの公開済み内容は保持し、今回のcommitでは変更しません。Manager 1.0.17は公開済みの別名を維持し、MRT検索語と説明を追加します。
