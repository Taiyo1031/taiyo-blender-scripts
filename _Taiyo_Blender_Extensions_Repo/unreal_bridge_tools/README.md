# Unreal Bridge Tools

## 概要
Blender上のオブジェクトTransform情報とCollection情報をCSVへ書き出し、Unreal EngineのPCGパイプラインで使いやすくするためのアドオンです。

オブジェクト名への `-coll` タグ付け、Collection / Scene単位の対象選択、名前フィルタ、名前正規化をまとめて扱えます。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > Sidebar (N) > Unreal Bridge Tools`
- バージョン: `2.3.2`
- 対応Blender目安: `4.5.0` 以降
- カテゴリ: `Import-Export`

## 使う場面
- Unreal Engine PCG用にBlender配置情報をCSV化したい
- `-coll` 付きのCollision用オブジェクトを整理したい
- Collection単位、再帰Collection、全Sceneから書き出し対象を選びたい
- `.001` などのBlender自動連番を用途に応じて除去したい

## 最短手順
1. 3D View右側の `N` パネルを開きます。
2. `Unreal Bridge Tools` タブを開きます。
3. `Scope` と `Target Collection` を設定します。
4. `Export CSV` に書き出し先を指定します。
5. 必要に応じて `Filters`、`Visible Only`、`Name Normalization`、`Export Mode` を調整します。
6. `Export CSV` を押します。

## 主な機能
- `Scope`: Direct Only / Recursive / All Collections の切り替え
- `Presets`: Scope、Collection、Export CSV、Export Mode、Filters、Name Normalizationをユーザー設定に保存・復元
- `Filters`: Include / Exclude テキスト条件で対象名を絞り込み
- `Collision Tag`: 選択オブジェクトへ `-coll` を追加・削除・選択
- `Name Normalize`: 生名維持、数値サフィックス除去、ドット以降削除
- `Test Write`: CSV保存先への書き込み可否を確認
- `Export Mode`: 60,000個以上向けの `Fast Locked` と、従来寄りに操作を通す `Responsive` を切り替え
- `Export CSV`: 大量オブジェクト時は `Fast Locked` を標準として、所属Collectionを一度だけキャッシュし、大きなchunkで書き出し。Nパネルのゲージ、進捗率、残り時間、処理速度を表示

## 出力CSV
出力列は以下です。

```text
id, tx, ty, tz, rx, ry, rz, sx, sy, sz, objname, colname
```

回転はXYZ Eulerをdegreeへ変換して出力します。

## 注意点
- `Visible Only` がONの場合、Viewportで見えているオブジェクトだけを書き出します。全オブジェクトを書き出す大量処理ではOFF推奨です。
- `Scope` が `All Collections` 以外の場合は `Target Collection` の指定が必要です。
- 保存先フォルダを作れない場合は、一時フォルダへフォールバックします。
- プリセットはBlenderのユーザー設定領域に保存され、Extension更新後も維持されます。
- 書き出し中の進捗率と残り時間は、`Remaining: 2m 03s` の形式でNパネルのゲージとBlender下部のステータスバーに表示され、`Esc` で中断できます。
- オブジェクトの所属Collectionは書き出し開始時に一度だけ取得するため、オブジェクト数に応じて処理時間が二乗で増える問題を解消しています。
- 高速化のために全オブジェクトを自動で非表示にはしません。非表示化はCSV対象を変える危険があり、60,000個規模では非表示変更そのものも重くなります。
- Blender Pythonのデータアクセスは基本的にメインスレッド中心です。マルチスレッド化ではなく、UI割り込みとファイル書き込み回数を減らして高速化しています。
- 大量の書き出し前に `.blend` を保存しておくと安心です。

## GitHub仕様書
- [Unreal_Bridge_Tools_使用書.md](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/Unreal_Bridge_Tools_%E4%BD%BF%E7%94%A8%E6%9B%B8.md)

## Map Roundtrip対応（2.3.1 / Blender 4.5以上）

- `Scope = Selected` は開始時の選択だけを書き出します。Target Collectionは不要です。選択ゼロならCSVを作りません。既存Filters／Visible Onlyは適用されます。
- `Tag Exported Objects (ub_zone)` は既定ONです。CSVが正常に保存されたときだけ、実際に書き出したObjectへCSVファイル名（拡張子なし）を付与します。中断・エラーではタグを変更しません。この設定はプリセットに含めません。
- `Zones > Select In Zone` は`ZONE_`から始まるCube Emptyの範囲に原点が入るMeshを選択します。Emptyの回転・スケールとdisplay sizeを反映し、同名サフィックス領域は合成します。重複はゾーン名順で決まります。Selectedスコープでは使えません。
- Zones処理はtimerで分割し、ESCで中断できます。中断時の途中選択は残ります。タグ名はCSVへ追加せず、12列の形式は従来どおりです。
- 推奨手順：Recursiveでゾーンを選択 → Selectedで`ZONE_A.csv`を出力 → Map Roundtrip ToolsでPreview → Dry RunをOFFにしてReplace Zone。

## 複数Emptyと範囲の引き算（2.3.1）

`Zones`で選んだゾーンのEmpty一覧と、各Emptyの`Add / Subtract`が表示されます。ゾーンの範囲は **（すべてのAddの和集合）から（すべてのSubtractの和集合）を除いた部分**です。Subtractは同じゾーンだけに効き、Addがないゾーンは空の範囲になります。Meshを加工するBooleanではなく、Object原点の選択判定です。回転・スケール・Cubeのdisplay sizeを反映します。

1. `Zone = All Zones`で`Add Empty`を押し、ダイアログで`ZONE_A`などのゾーン名を入力します。新しいゾーンもこの操作で作成できます。
2. 既存ゾーンを選んだ状態で`Add Empty`を押すと、そのゾーンのCube Emptyを3Dカーソル位置に追加し、選択・アクティブにします。初期サイズは1、OperationはAddです。
3. 追加したEmptyを移動・回転・拡大して範囲を組み立てます。くり抜く箱は一覧でSubtractに切り替えます。
4. Recursiveなどの候補スコープで`Select In Zone`を押し、結果を確認してからSelectedでCSVへ出力します。

新規Emptyはシーン直下に追加され、カスタムプロパティ`zone`で所属を保存します。Operationは`ubt_zone_operation`として.blendに保存されます。従来のCube EmptyはAddとして扱い、`.001`などの同名末尾連番による合成も維持します。Empty追加・Operation変更は通常のUndo対象です。

Operationを変更しても、過去にCSV出力で付いた`ub_zone`タグは自動解除しません。すでに書き出したゾーンの範囲を変える場合、ReplaceのPreview件数も確認してください。

### 2.3.1 検証結果

Blender 4.5.9 / 5.2.2で、複数Addの和集合、同一ゾーンだけのSubtract、回転・スケール、Subtractのみの空ゾーン、従来Emptyの互換性、追加ボタンと.blend保存復元を確認しました。10万点・Add 2箱＋Subtract 1箱のnumpy判定は4.5.9で0.0114秒、5.2.2で0.0086秒でした（Object座標取得・選択適用を除く）。既存CSV／プリセットとMap Roundtripの回帰も合格しました。

回帰: `blender --background --factory-startup --python-exit-code 1 --python tools/test_unreal_bridge_zones.py`。実UIのAdd Empty／Undo／Redo: `blender --factory-startup --python-exit-code 1 --python tools/ui_test_unreal_bridge_zones.py`。

## UIからのZone登録（2.3.2）

New Zoneで空のZoneを登録し、Add Emptyで新しい箱を作るか、既存Emptyを選んでRegister Selected Emptiesで登録できます。一覧の名前ボタンで選択し、×で登録だけ解除します。登録解除でObjectは削除しません。各欄・ボタンにはホバーヒントがあります。

Zoneは範囲選択用、CSV zone tagはCSVファイル名由来です。名前を揃えてください。詳しい手順とExchange Folderの説明は[Map Roundtrip 詳細使用書](https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/map_roundtrip_tools/WORKFLOW_JA.md)をご覧ください。
