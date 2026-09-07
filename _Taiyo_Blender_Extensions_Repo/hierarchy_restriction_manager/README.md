# Hierarchy Restriction Manager

**Version 1.0.0 / Blender 4.5.5以降 / 動作検証: Blender 4.5.9 LTS (macOS)**

Collectionを指定し、その階層の表示・選択・レンダー制限をまとめて変更するExtensionです。Nパネルの **Hierarchy** タブで使用します。既存のMap Link Toolsとは別にインストールできます。

## 最短の使い方

1. Object Modeで、`Collection`で対象を検索するか、`Use Active Collection`を押します。
2. `Affect`と階層範囲を確認します。初期状態はルート・子Collection・配下Objectsの全階層です。
3. `Show Hierarchy`など、目的のQuick Actionを押します。
4. 元に戻すときはBlenderのUndoを1回実行します。処理途中なら`Cancel & Restore`またはEscで変更前へ戻します。

大きな処理は小分けに実行し、処理中の進捗と変更数を表示します。5万候補超では、パネル上の`Confirm Apply`を押してから変更を開始します。候補数は実際に値が変わる件数とは異なります。

## Quick Actions — 即実行

| ボタン | 変更する項目 |
|---|---|
| Show Hierarchy | Included・Visible・Viewport EnabledをOn |
| Hide in Viewport | VisibleだけOff |
| Unlock Selection | SelectableだけOn |
| Lock Selection | SelectableだけOff |
| Enable Render | Render EnabledだけOn |
| Disable Render | Render EnabledだけOff |

**現在のScopeとFiltersがすべてのQuick Actionに適用されます。** 詳細設定で準備中の7項目はQuick Actionsへ混ぜません。フィルターが有効なときは、閉じていても`Filters Active`と表示します。

Show HierarchyはRender、Holdout、Indirect Only、選択可否を変更しません。また、対象外の親Collectionは変更しません。親が非表示・除外の場合は対象をOnにしても見えない場合があります。対象を親Collectionへ変更してから操作してください。

## 詳細な制限設定

`Detailed Restrictions`を開き、各項目を`Keep / On / Off / Invert`から選び、`Apply to Hierarchy`で実行します。

- **Keep**: 変更しません。全項目の初期値です。
- **On / Off**: 項目名に対する有効／無効です。Blenderの`hide_*`の反転を意識する必要はありません。
- **Invert**: 各対象の現在値を個別に反転します。
- **Reset Settings to Keep**: 操作設定だけを初期化します。Sceneの状態は変えません。

| 項目 | 対象 | 適用範囲 |
|---|---|---|
| Included | LayerCollection | 選択View Layerへの組み込み／除外 |
| Selectable | Collection・Object | 全View Layer共通 |
| Visible | LayerCollection・Object | 選択View Layerの一時表示 |
| Viewport Enabled | Collection・Object | 全View Layer共通のViewport有効化 |
| Holdout | LayerCollection | 選択View LayerのHoldout |
| Indirect Only | LayerCollection | 選択View Layerの間接寄与のみ。レンダー上の効果はエンジンに依存 |
| Render Enabled | Collection・Object | 全View Layer共通のレンダー有効化 |

Collectionを他Sceneでも共有している場合、グローバルな設定はそちらにも反映されます。同じCollectionが複数経路に現れる場合、選択View Layer内の該当する全LayerCollectionを対象にします。同じObjectは1回だけ処理します。

## Target・Scope・Filters

- `Use Active Collection`: 現在のView LayerのActive Collectionを使用します。
- `Use Object Collection`: Active Objectの所属Collectionを使用します。複数所属の場合は選択メニューを表示します。
- OutlinerでCollectionを1つ選び、右クリックの`Set as HRM Target`でも指定できます。
- Target横の星ボタンはお気に入りへの追加／解除です。`Recent & Favorites`には最近使った10件とお気に入りを表示します。参照なので通常の改名にも追従します。
- `Layer`が空欄なら現在のView Layerです。検索欄で現在のScene内の別View Layerも選べます。戻るアイコンで現在のView Layerへ戻します。

`Scope`はCollectionのフラグ変更とObjectのフラグ変更を分けて指定します。

- `Include Root`: 指定Collection自身のフラグを変更します。
- `Child Collections`: 選択した深さ内にある子Collectionのフラグを変更します。
- `Objects`: 遍歴するCollectionに直接所属するObjectsを変更します。Include RootがOffでも、ObjectsがOnならルート直属Objectsは対象です。
- `All Descendants`: 深さ制限なし。
- `Direct Children`: ルート（深さ0）と直下（深さ1）。
- `Depth Limit`: 指定深さまで。0ならルートとその直属Objectsだけです。

`Filters`ではCollection名／Object名それぞれにIncludeとExcludeを指定できます。Contains、Starts With、Ends With、Exact、Wildcard、Regexに対応し、Excludeを優先します。空のIncludeは全件です。

Object Typesは何も選ばなければ全種類です。`Skip Item Only`は不一致Collectionとその直属Objectsを除外し、子の探索を続けます。`Skip Entire Branch`は不一致Collectionの子階層も探索しません。複数経路で到達可能なデータは、有効な経路から到達できれば対象になります。

## Presets・Copy / Paste

この区画の操作は**設定の準備**です。最後にApplyを押します。

- `Enable All`: Included・Selectable・Visible・Viewport・RenderをOn、Holdout・Indirect OnlyをOff。
- `Disable All`: Included・Selectable・Visible・Viewport・RenderをOff、Holdout・Indirect OnlyはKeep。
- `Viewport Only`: Included・Visible・ViewportをOn、RenderをOff。
- `Render Only`: Included・RenderをOn、ViewportをOff。
- `Lock / Hide`: それぞれSelectable／VisibleだけをOff。
- `Match Root to Settings`: ルートの状態を設定へ取り込み、Include RootをOffにします。
- `Copy Root Restrictions → Paste to Settings`: 別の階層へルートの状態をコピーします。複数LayerCollectionで混在・取得不可の項目はKeepとし、メッセージに示します。

独自プリセットには7項目、Scope、Traversal、Filters、Object Typesを保存します。同名Saveは上書きです。`Browse Presets`で保存済み一覧から選べます。保存先はBlenderのExtensionユーザー領域（単体モジュールでの開発時はCONFIG/hierarchy_restriction_manager）です。更新でプリセットを消しません。

`Include Target in Preset`は既定Offです。Onではblendファイル名・Collection名・ライブラリを保存し、一致しなければTargetを未設定にします。別ファイルで誤ったCollectionを勝手に選びません。

## Solo / Restore

`Solo Hierarchy`はScope／Filtersとは独立した隔離操作です。対象Collectionへ至る親の制限を必要な範囲で解除し、他の階層はCollection単位で隠します。対象内の子Collection・Objectの個別の非表示は保持します。保持する親Collectionの直属Objectだけは、対象内にも所属するものを除き、Object単位で隔離します。

- `Viewport Visibility`（既定）: 選択View Layerの一時表示で隔離します。
- `Viewport Enabled`: CollectionのグローバルViewport設定で隔離します。
- `Render`: グローバルRender設定で隔離します。
- `Viewport + Render`: 両方を隔離します。

前のSolo中に別TargetでSoloすると、先に元の状態を戻してから新しい隔離を行います。`Restore Solo`は保存した値へ戻します。外部共有Collectionのグローバル設定では、保持すべき出現を優先するため完全に分離できない場合があります。

Soloの復元情報はこのBlenderセッション内だけに保存します。**元の表示状態を保存したいときは、Restoreしてからblendを保存してください。** ファイル読込、Undo／Redo、Extension無効化で実行時キャッシュは破棄されます。Undo／Redo自体はBlenderに保存されたScene状態へ戻します。

## Statistics・Performance

`Refresh`はSceneを変更しません。

- `Fast Counts`: Collection数、Object Links、Unique Objectsを計算します。
- `Detailed Preview`: さらに各項目のOn／Off／Mixed、変更見込みを表示します。

統計は継承された最終表示ではなく、保存されたフラグの集計です。除外されてView Layerに存在しないObjectの一時表示は取得・変更できず、Unavailableとして扱います。IncludedとVisibleを同時に変更する場合、事前Previewと実処理では到達可能なObjectが変わり、見込み件数と結果が異なる場合があります。

| Performance | 動作 |
|---|---|
| Auto | 対象を数えてから分割実行 |
| Detailed | 詳細解析をしてから分割実行 |
| Fast | 件数の事前走査を省いて分割実行。確認有効時は件数不明として確認 |

約8msごとに処理を返す設計ですが、Blender内部の単発RNA更新や依存グラフ更新が長い場合、1回の処理が8msを超えることがあります。処理中は競合する編集を抑止します。

Cancelは変更した値を戻します。Blenderが除外・Viewport無効化時に破棄するObjectの一時非表示も復元用に記録します。そのため、ObjectsをOffにしていても、Collectionの除外やViewport変更では復元用に配下Objectを走査する場合があります。Undo用・復元用メモリは変更数に応じて増えます。

Auto Refreshは既定Offです。有効時はHRM設定を変更した後に更新します。Sceneを別操作で編集した後は、古い統計の表示を確認してRefreshしてください。Last Operationでは変更数、スキップ、エラー、時間を確認し、Copy Reportで詳細をコピーできます。

## 検証と制約

- 制限を変更する操作はObject Mode専用です。Edit ModeではBlenderのUndoがCollection/Objectの制限を戻さないケースを実機で確認したため、変更を開始せず案内します。モードは勝手に切り替えません。対象選択・設定・Previewは他モードでも使用できます。

- Blender 4.5.9 LTSで7項目の4操作、階層・フィルター・重複リンク・複数View Layer・ライブラリ・Preview・Solo・Cancelの統合テストが通過しました。
- 通常のObject ModeのUIで、一括変更を1回のUndo／Redoで戻せること、Modal処理中のCancel、保存後の設定復元を確認済みです。
- 読み取り専用の変更はスキップします。Library Overrideは書き込み可能なプロパティを扱い、新規Overrideは作りません。
- TargetやView Layerの削除、無効なRegexはエラーとして通知します。処理中に外部スクリプトがデータを削除した場合など、復元できない項目はLast OperationのErrorsに残ります。
- 既定のグローバルショートカットは登録しません。メッシュ、名前、所属、マテリアル、Transformは変更しません。

テスト: `blender --background --factory-startup --python-exit-code 1 --python tools/test_hierarchy_restriction_manager.py`

負荷計測結果と計測条件は[検証レポート](VALIDATION.md)を参照してください。
