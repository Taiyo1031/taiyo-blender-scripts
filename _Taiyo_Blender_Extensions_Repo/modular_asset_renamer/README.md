# Modular Asset Renamer

複数の命名モジュールを左から順に組み合わせ、選択中のObjectとMesh Dataを一括リネームするBlender Extensionです。

## 基本情報

- Extension ID: `modular_asset_renamer`
- バージョン: `1.0.5`
- 対応Blender: `4.5.0`以降
- 動作確認: `Blender 4.5.10 LTS`
- 表示場所: `3D Viewport > Sidebar (N) > Rename Tools`

初期状態には命名モジュールもプリセットもありません。用途に合わせて必要なモジュールを追加してください。

## 命名モジュール

各モジュールは出力文字列と、その直後に付ける`Separator After`を持ちます。

```text
Final Name =
Module 1 Output + Separator 1 +
Module 2 Output + Separator 2 + ...
```

使用できるモジュール:

- `Text`: 固定文字列
- `Choice`: 編集可能な候補リストから選択した文字列
- `Dimensions`: Object寸法
- `Index`: 連番
- `Original Name`: 元のObject名または分割した一部分
- `Collection Name`: 所属Collection、Active Collection、親Collection

## 基本的な使い方

1. リネームするObjectを選択します。
2. `N`キーでSidebarを開き、`Rename Tools`タブを選びます。
3. `Naming Modules`から必要なモジュールを追加します。
4. Module Detail Editorで値と`Separator After`を設定します。
5. `Preview Selected`で変更後の名前を確認します。
6. `Apply Rename`で確定します。

直前の操作は`Revert Last Rename`で戻せます。監査用Custom PropertyはRevert後も残ります。

## ChoiceとQuick Controls

Choiceモジュールを追加すると、パネル上部の`Quick Controls`にも同じドロップダウンが表示されます。ここで変更した選択値はModule Detail Editorと共通です。

候補はModule Detail Editorで追加、削除、並べ替えできます。候補には内部IDが付くため、表示文字列を変更しても現在値とプリセットの対応が保たれます。

プリセットの保存・読込後もQuick Controlsの候補リストは維持され、そのまま別の候補へ切り替えられます。

無効化したChoiceモジュールでもQuick Controlsから候補値を変更できます。候補が空、現在値が未選択、または選択した候補文字列が空の場合はPreview/Applyとプリセット保存でエラーになります。

古いプリセットや旧バージョンのSceneから読み込まれたChoice内部IDは、起動時または操作実行時に安全な形式へ自動修復されます。修復が必要な状態でUIを開いても、パネル全体が消えないようにRepairボタンが表示されます。

Quick Controlsの選択状態は候補ID文字列で保持されるため、候補を切り替えた直後に空欄へ戻らないようになっています。

## Dimensions

Blenderの寸法値をメートルとして扱い、`m`、`cm`、`mm`へ変換します。

設定項目:

- 軸順: `XYZ`、`XZY`、`YXZ`、`YZX`、`ZXY`、`ZYX`
- 軸区切り文字
- 小数桁数: 0から4
- 丸め: Round、Floor、Ceil
- 単位サフィックス
- 軸ラベル
- 末尾の0削除

例:

```text
180x240x30cm
X180_Y240_Z30cm
```

## Indexと処理順

最初の有効なIndexモジュールの`Sort Mode`が処理順を決めます。

- Selection Order: Active Objectを先頭にし、残りはBlenderの選択リスト順
- Object Name A-Z / Z-A
- Location X / Y / Z

複数のIndexモジュールを配置した場合も、それぞれ同じ処理番号を出力します。

## Preview Status

- `OK`: 適用可能
- `Duplicate`: 既存名エラーがON、または重複自動解決がOFF
- `Empty Name`: 有効なモジュールから名前が生成されない
- `Invalid Character`: 禁止文字の置換がOFFで、禁止文字が残っている
- `Skipped`: Optionsまたは安全条件により対象外

PreviewはObjectやMesh Dataの名前を変更しません。

## Optionsと安全動作

- Object名とMesh Data名は個別に有効化できます。
- 空白と `/ \ : * ? " < > |` は、設定がONなら`_`へ置換します。
- `Error If Name Exists`がONの場合、生成名が既存Object名またはMesh名と衝突すると`Duplicate`として停止します。この設定は重複自動解決より優先されます。
- 重複自動解決は末尾に`_001`、`_002`を追加します。
- 重複判定は既存Object名と、Mesh Dataを変更する場合は既存Mesh名も確認します。
- 共有Meshはリンク解除せず、処理順で最初のObjectの生成名へ1回だけ変更します。
- linked/read-onlyのObjectは変更しません。読み取り専用MeshはObject名だけ変更可能な場合があります。
- 1000 Objectを超えるApplyでは確認ダイアログを表示します。

`Store Original Name as Custom Property`がONの場合、変更前の名前を次へ保存します。

```text
object["original_name_before_modular_renamer"]
object.data["original_name_before_modular_renamer"]
```

## Presets

プリセットは次へJSONとして保存されます。

```text
Blender user config/modular_asset_renamer/presets.json
```

保存内容:

- モジュールの種類、順序、全設定
- Choice候補と現在値
- 各モジュールのSeparator
- Options

`Save`は選択中プリセットを更新し、`Save As New`は別名で保存します。Exportは全プリセットを書き出し、Importは同名プリセットを上書きしてマージします。

## 注意事項

- RevertはこのExtensionによる直前のApplyだけを対象にします。
- Apply後に対象を削除した場合、存在するデータだけを復元します。
- Apply後に同名データを新しく作成した場合、Blenderが復元名へ数値サフィックスを付けることがあります。
- Active Collectionは操作時の3D View contextにあるCollectionを使用します。
