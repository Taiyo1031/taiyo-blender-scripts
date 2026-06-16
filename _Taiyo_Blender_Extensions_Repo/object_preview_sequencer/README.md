# Object Preview Sequencer

選択したオブジェクトを登録し、タイムライン上で1フレームずつ順番に表示する一時プレビューシーケンスを作るBlender Extensionです。

## 基本情報

- 表示場所: `View3D > Sidebar(N) > Object Preview`
- バージョン: `1.0.1`
- 対応Blender目安: `4.2.0` 以降
- 対象: Object全般

## 使い方

1. 順番に確認したいオブジェクトを選択します。
2. `Object Preview` パネルで `Register Selected` を押します。
3. `Build Sequence` を押します。
4. タイムラインをスクラブして、1フレームごとに対象オブジェクトを確認します。
5. 確認が終わったら `Restore / End Mode` を押して元の状態に戻します。

## 動作

- 登録順はOutliner/Collectionツリーに近い順番です。
- `Build Sequence` は現在フレームから、登録数ぶんのフレーム範囲を作ります。現在フレームが0以下の場合は1フレーム目から作ります。
- 各フレームでは登録オブジェクトのうち1つだけ表示され、他のView Layer内オブジェクトは一時的に非表示になります。
- 元のAction、表示状態、選択状態、Active Object、現在フレーム、シーンのframe rangeは退避されます。
- 復元データは `.blend` 内にも保存されるため、保存後に別PCで開いた場合も、同じExtensionが入っていれば `Restore / End Mode` で戻せます。
- `Restore / End Mode` は一時Actionを削除し、退避した状態へ戻します。

## 注意点

- 既存Actionは直接編集しません。プレビュー中だけ一時Actionへ差し替えます。
- プレビュー中に保存した場合でも復元データは残りますが、確認後は `Restore / End Mode` で戻してください。
- Collection側で非表示・除外されているオブジェクトは、Objectの表示キーだけでは表示できない場合があります。
