# 検証レポート — v1.0.0

環境: Blender 4.5.9 LTS / macOS ARM64。最低対応宣言は4.5.5。

## Object負荷テスト

1000 ObjectsごとにCollectionを分けた、形状を持たない空Objectでの測定です。HRMエンジンを約8msずつ進め、Timer待機・実際の描画・最終依存グラフ評価・BlenderのUndoスナップショット作成を含まない時間です。実シーンで同じ待ち時間を保証する値ではありません。

| Objects | Render Off | 同値再適用 | Fast件数確認 | Regex反転 |
|---:|---:|---:|---:|---:|
| 10,000 | 0.062s | 0.016s | 0.007s | 0.075s |
| 50,000 | 0.583s | 0.079s | 0.035s | 0.613s |
| 100,000 | 1.985s | 0.165s | 0.072s | 1.916s |
| 250,000 | 9.240s | 0.434s | 0.195s | 9.381s |
| 500,000 | 33.659s | 0.857s | 0.400s | 34.015s |

全KeepではObject走査0・書き込み0。同値再適用は全サイズで書き込み0。50万Objectのプロセス最大RSSは1,563 MiB（約1.53 GiB、テストScene、Blender本体、復元記録を含む）。

## Cancel負荷テスト

各サイズの約半数へRender Offを適用した時点でSessionにCancelを要求し、全Objectの元の値と操作ロックの解除を確認しました。Timer待機・描画を含まない測定で、実UIの待ち時間とは異なります。

| Objects | 復元したプロパティ数 | 要求後の最初の復元チャンク | 完全復元まで |
|---:|---:|---:|---:|
| 10,000 | 5,936 | 3.511ms | 0.021s |
| 50,000 | 25,372 | 8.515ms | 0.250s |
| 100,000 | 50,333 | 9.077ms | 0.874s |
| 250,000 | 125,089 | 10.555ms | 4.793s |
| 500,000 | 250,084 | 13.285ms | 18.294s |

50万ObjectでのCancelテストの最大RSSは1,423 MiB。復元中も分割処理を続けるため、Cancel直後には処理が終了せず、復元完了まで進捗を表示します。`--cancel-only`でこの計測だけ再実行できます。

## Collection階層テスト

| 条件 | エンジン処理時間 | 変更プロパティ数 | Object走査数 |
|---|---:|---:|---:|
| holdout_100_collections | 0.0010s | 101 | 0 |
| holdout_1000_collections | 0.0142s | 1,001 | 0 |
| holdout_10000_collections | 0.6259s | 10,001 | 0 |
| depth_1100 | 0.0608s | 1,101 | 0 |

深さ1100でもPython再帰に依存せず処理できました。多数CollectionのLayerCollection取得では、Blender内部の同期による約238msの長いステップを観測しました。50万Objectの操作でもGC/RNA等により約118msのステップがあり、8msは協調処理の目安であって厳密な上限ではありません。

## 機能検証

- 7種類 × Keep/On/Off/Invert、Quick Actionsが詳細設定を混ぜないこと。
- 深さ、対象フラグ、名前・種類・枝刈り、Object重複リンク、Collection複数経路。
- 複数View Layer、一時表示とグローバル表示の分離、読み取り専用ライブラリ、編集可能なLibrary Override。
- 除外された階層のShow、Cancel時の完全復元、Blenderが破棄する一時非表示の補償。
- 4種類のSolo、再Solo、再Solo途中のCancel、Restore、別View Layerの一時非表示の復元。親直属のObjectと対象内にもリンクされたObject、Target解除後のRestore。
- PreviewがSceneを変更しないこと、無効なRegex、削除されたCollection／View Layer、空Collection。
- プリセット保存・読込・削除、対象参照の解決、履歴、お気に入り、登録解除と再登録。
- 専用UIでModal完了、1回のUndo、Redo、途中Cancel、大量処理の確認前に書き込まないこと。一時表示変更もネイティブUndoで復元。
- 実際の保存・再読込で、改名したTarget、範囲、条件、お気に入りを保持し、実行時キャッシュを破棄すること。

再現用スクリプトはリポジトリの `tools/test_hierarchy_restriction_manager.py`、`tools/ui_test_hierarchy_restriction_manager.py`、`tools/benchmark_hierarchy_restriction_manager.py`。Load/Undo後の参照は再取得し、統計キャッシュは破棄します。

Edit ModeのネイティブUndoでは制限フラグが復元されないことを確認しました。v1.0.0の変更操作はObject Modeに限定し、他モードでは無変更で中止するテストを追加しています。
