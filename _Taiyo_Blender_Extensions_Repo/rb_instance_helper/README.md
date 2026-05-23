# RB Instance Helper

## 概要
リンクされたコレクションインスタンス用にRigid Body向けプロキシメッシュを作り、更新、ベイク、転送まで扱う補助アドオンです。

## 基本情報
- 本体ファイル: `__init__.py`
- 表示場所: `View3D > N-panel > RB Helper`
- バージョン: `1.3.2`
- 対応Blender目安: `4.5.9 LTS` 以降
- カテゴリ: `Object`

## 使う場面
- コレクションインスタンスをRigid Bodyシミュレーションに使いたい
- 元アセットを壊さずに物理用プロキシを管理したい
- ベイク後の動きを元インスタンスへ転送したい
- 同じ `.blend` 内のCollection Instanceもプロキシ化したい

## 最短手順
1. 対象インスタンスを選択します。
2. `RB Helper` パネルの `1 SETUP` でTargetやCollision Shapeを設定します。
3. `Realize & Parent` でプロキシを作成します。
4. 必要に応じてRigid Bodyを調整し、`Bake RB to Keyframes` を実行します。
5. `Transfer & Remove Parent` で結果を元インスタンス側へ転送します。

## 主な設定
- `Target`: 選択オブジェクトまたはコレクションを対象にする
- `Hide Proxy from Render`: プロキシをレンダー非表示にする
- `Show Proxy Object Name`: Viewport上のプロキシ名表示を切り替える
- `Auto Add Rigid Body`: 作成時にRigid Bodyを付ける
- `Collision Shape`: Convex Hull / Mesh / Box など
- `Update Selected Proxy` / `Update All Proxies`: 元アセット変更後にプロキシを更新
- `Restore Selected`: 選択中ペアの親子解除、または現在のプロキシトランスフォームだけを元インスタンスへ適用
- `Proxy Children`: 選択中のプロキシ直下の子オブジェクトを選択

## 結果
Rigid Body用プロキシ、親子付け、ベイク済みキーフレーム、転送結果を作成・更新します。

## 注意点
- Rigid Body調整は基本的にプロキシ側で行います。
- 元アセットを変更したら `Update` を実行します。
- `Delete Proxy after Transfer` は必要な場合だけONにします。
- スキップ理由はBlenderコンソールに `[RB Instance Helper] SKIP:` として出力されます。

## 詳細な使用書
- 詳細使用書: `RB_Instance_Helper_使用書_v1.3.1_FINAL.md`
