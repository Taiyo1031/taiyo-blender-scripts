# Blend Reference Graph

## 概要・対応バージョン

対象バージョン: **0.2.0**。Blender **4.2.0以降**に対応します。0.2.0は後方互換のある更新です。

Blender内の参照関係を読み取り、HTMLビューアで確認するExtensionです。選択したObject / Boneを起点にするスキャンと、開いている.blend全体を対象にするWhole Fileスキャンを使えます。データの削除は行いません。

表示場所は `View3D > Sidebar (N) > Blend Ref Graph`、本体フォルダは `blend_reference_graph` です。

## Object / Boneから調べる

1. 対象Objectを選択し、パネルの `Use Selected` を押します。
2. `Scan` 内の `Uses`（参照先）/ `Used By`（参照元）/ `Both`（両方向）と `Depth`（1〜5）を設定します。
3. `Update + Open Viewer` を押します。

Pose ModeでBoneを選択して `Use Selected` を押すと、そのBoneのConstraintを中心に調べます。`Update Graph Data` はデータ更新、`Open Viewer` はビューアを開く操作です。Blender側でデータを更新した後、既に開いているブラウザには `Reload Data` で反映します。

対象にはObject、Mesh、Collection、親子関係、Object / Pose Bone Constraint、Armature / Bone、Geometry Nodes ModifierとNode Group、Geometry Nodes内のObject / Collection / Material / Image / Sub Node Group参照、Action / NLA Action、Driverとその参照先、Library Linked Dataが含まれます。

Collectionの代表パスはノード内、複数の所属パスは `Details` で確認できます。Safe Delete Previewは従来どおり**ターゲットのスキャン範囲内だけ**の確認用情報です。削除可能性を保証せず、実際の削除も行いません。

## Whole Fileで全体を調べる

ターゲット選択は不要です。パネルの `Whole File` で次を設定し、`Scan Whole File` を押します。

| 表示名 | プロパティ | 内容 |
|---|---|---|
| Include Internals | `include_internals` | 既定ON。ObjectのConstraint、Geometry Nodes、アニメーション・Driverなどの内部参照を追加 |
| Include Bones | `include_bones` | 既定OFF。Boneノードを追加 |
| Maximum Bones | `max_bones` | Boneの合計上限。既定2,000、設定範囲100〜50,000 |
| Open Viewer After Scan | `open_viewer_after_scan` | 既定ON。完了時にビューアを開く |

進捗は `Progress`、件数は `Nodes` / `Edges`、所要時間は `Scan:` に表示します。Blenderでスキャン中に `Esc` または右クリックするとキャンセルし、その途中結果は書き出しません。完了後は種類別の概要モードで開きます。

全Sceneを含む現在ロード済みのデータが対象で、選択状態や現在のView Layerの表示範囲に限定されません。Object、Mesh、Armature、Curve（MetaBall / Lattice / Grease Pencilを含む）、Collection、Material、Image、Node Group、Action、Scene、World、Camera、Light、Text、Font、Sound、Particle、Texture、Libraryなどを列挙し、Blenderの `bpy.data.user_map()` が返すデータ間参照を使用側→参照先の線にします。未使用データも対象です。

Materialなどに埋め込まれたNode TreeやSceneのルートCollectionは独立ノードにせず、所有者への参照にまとめます。リンクデータはLibraryを区別しますが、外部.blendを新たに開いて全内容を調べる機能ではありません。

Whole Fileにはターゲット用の `Scan Mode` / `Depth` による範囲制限はありません。巨大な.blendでは時間とメモリが必要です。分割処理でも `user_map()` や書き出しなどの処理中は応答が遅れることがあり、即時キャンセルや一定の応答時間を保証しません。Bone上限などによる打ち切りは出力データの `meta.truncated` に記録します。Whole FileはSafe Delete Previewを全データに拡張する機能ではありません。

## Live Viewer

アドオン設定 `Edit > Preferences > Add-ons > Blend Reference Graph` の `Live Viewer`（`live_viewer`）は既定ONです。`Open Viewer`、`Update + Open Viewer`、またはWhole File完了時の自動表示でローカルサーバーを起動します。

待受先は **127.0.0.1のみ**で、URLは `http://127.0.0.1:<port>/<token>/viewer.html` です。起動ごとのランダムtokenを必要とし、HostとPOSTのOriginも検証します。配信対象はビューアとグラフの5ファイルだけです。グラフや.blendを外部サービスへ送信しません。Extensionの `network` 権限（理由: `Local viewer server on 127.0.0.1`）は、この同じPC内のブラウザとの通信に必要です。`GitHub` ボタンを押した場合は外部のリポジトリページを開きます。

パネルの `Live Viewer` に `Running` / `Stopped` と稼働中のURLが表示されます。`Stop Live Viewer` で停止できます。別の.blendを開く前、アドオン無効化時にも停止します。再起動時は新しいtokenとポートのURLを使います。

設定をOFFにすると `file://` で開き、保存済みグラフの閲覧はできますが**ブラウザから再スキャンはできません**。サーバーに接続できない場合も再スキャン操作は無効になり、`Blender の Live Viewer で開くと使えます` と表示します。

### ブラウザから再スキャン

| 操作 | 内容 |
|---|---|
| Re-scan from selection / `R` | ちょうど1ノードを選択したとき、そのノードを起点に再スキャン |
| Mode | `Uses` / `Used By` / `Both` で参照方向を指定 |
| Depth | ノード中心スキャンの深さ1〜5 |
| Whole file | 全体を再スキャン。Mode / Depthで範囲は絞られません |
| Back | 直前のスキャン要求を再実行。過去の結果ファイルを表示する操作ではありません |
| キャンセル | 待機中・実行中のLiveスキャンを取り消す |

再スキャンはBlenderが起動している間に使えます。Whole Fileの内部参照・Bone設定はBlender側の設定を使います。進捗とメッセージを表示し、完了するとページを自動更新します。エラー時はメッセージを表示します。`Back` の履歴はブラウザタブのセッション内で最大20件です。検索欄や他の入力欄にフォーカスがある間、`R` は再スキャンを実行しません。

## HTMLビューアの操作

Whole Fileの結果だけが**概要モード**になります。種類ごとの箱に件数とorphan件数を表示し、箱の見出しをクリックして展開・折りたたみします。

- `Node Types` のチェックボックスで型を絞り込みます。
- `Orphanのみ` は `users == 0` かつFake Userなしのデータに絞ります。安全に削除できるという判定ではありません。
- `すべて展開` / `すべて折りたたみ` で全種類を操作します。
- 展開時は1種類あたり通常500件まで表示します。検索ヒットと選択ノードは、型・Orphanフィルターを通る限り上限外でも表示します。省略分は `+N more — use filter/search` と表示します。
- 検索はフィルターを通ったノードが対象で、ヒットのある種類を自動展開してフォーカスします。
- 箱間の参照は件数で集約し、展開中は表示ノードと集約箱の間にも線を描きます。概要モードの実エッジ（ノードと集約箱の線を含む）は通常**2,500本まで**。選択ノードにつながる表示対象エッジは上限を超えても残し、次に検索ヒットを優先します。省略本数は画面下に表示します。これは描画上の制限であり、グラフデータや `Export JSON` から参照を削除しません。
- 縮小表示ではエッジラベルとノードの補助テキストを隠します。

共通操作:

| 操作 | 内容 |
|---|---|
| ノードクリック / Shift+クリック | 選択 / 選択の追加・切り替え。右側の `Details` で詳細を確認 |
| ノードの左ドラッグ | 移動。複数選択ならまとめて移動 |
| 空白の左ドラッグ / `B` 後のドラッグ | ボックス選択。Shift併用で追加・切り替え |
| 中央ドラッグ / 空白でSpace+左ドラッグ | パン |
| ホイール / トラックパッドの2本指スクロール | パン |
| ピンチ / Ctrl・Cmd・Altのいずれか+スクロール | ズーム |
| Fit View / `F` / `0` | 全体を表示 |
| Zoom In / Zoom Out / `+` / `-` | 拡大・縮小 |
| `/` / Cmd+F | 検索欄へ移動 |
| Next / Prev / `N` / `P` | 次 / 前の検索結果へ移動 |
| 検索欄でEnter / Shift+Enter | 次 / 前の検索結果へ移動 |
| 矢印キー / H・J・K・L | パン。Shift併用で移動量を増加 |
| Esc | ドラッグ等の操作を取り消す。検索欄では検索解除、その後フォーカス解除 |
| Swap Bars | 左右サイドバーを入れ替え |
| Reload Data | ページと出力データを再読み込み（Blenderの再スキャンではありません） |
| Export JSON | 読み込んだグラフをJSONで保存 |
| GitHub | ソースのページを開く |

ブラウザの `Esc` はLiveスキャンのキャンセルではありません。Liveスキャンには `キャンセル` ボタンを使ってください。

## 検出しない参照・限界

- View Layer / Layer Collection固有の所属・除外・表示状態を独立した参照グラフとしては扱いません。
- WindowManager / WorkSpace / Screen、Brush / PaletteはWhole Fileの列挙対象外です。
- Modifierすべての内部設定や参照経路を個別には展開しません。Geometry Nodes以外のModifierや、Geometry Nodes Modifierの入力設定などの一部は、`user_map()` が拾うID間の線として出ても、どのModifier・入力を経由したかまでは表示しません。
- Pythonコード、Textや文字列カスタムプロパティ内に書かれた名前・ファイルパスを解析して参照先を推測しません。未ロードの外部ファイルや実行時に計算される参照を網羅しません。
- `Include Internals` がOFFなら詳細な内部ノードを省略します。BoneはOFFなら省略し、ONでも上限があります。線がないことだけで未使用・削除可能とは判断できません。

## 出力ファイル

標準の `Output Location` は `System Temp` で、OSの一時フォルダ内にプロセスごとのフォルダを作ります。

```text
<System Temp>/blend_reference_graph/<Process ID>/
```

アドオン設定で `Output Location` を `Custom Folder` にすると保存先を指定できます。未設定、作成不可、書き込み不可の場合はエラーで中止します。更新ごとに次のファイルを上書きします。

- `graph_data.js`
- `graph_data.json`
- `viewer.html`
- `viewer.css`
- `viewer.js`

## Whole Fileベンチマーク

リポジトリ直下から次を実行します。新しいテスト用Sceneを作るため、作業中のBlenderでは実行しないでください。

```sh
/Applications/Blender4.5.9.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tools/benchmark_blend_reference_graph_whole_file.py
```

既定はObject 20,000 / Material 1,000です。`--python` で渡すスクリプトの引数を `--` の後に指定して変更できます。

```sh
/Applications/Blender4.5.9.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 --python tools/benchmark_blend_reference_graph_whole_file.py -- --objects 2000 --materials 100
```

Materialごとの三角形MeshをObject間で共有し、全Objectに共通のGeometry Nodesグループを割り当てます。内部参照ON・Bone OFFで、データ作成と依存グラフ更新を計測対象から分離します。

出力は `iter_scan` の所要時間、yield回数・最大間隔・30ms超過回数、返されたメッセージ別の間隔内訳、スキャン内で実際に呼ばれる `user_map()` の時間とRNA型別のID数・参照組数、ノード・エッジ件数、compact JSONのバイト数、書き出し時間です。yield間隔には計測側の処理も含み、メッセージ別集計は厳密な工程別時間ではありません。`user_map()` の内訳は除外・重複排除前の値で、集計のためスキャン完了までその結果を保持します。生成ファイルは `tempfile` の一時フォルダへ書き、終了時に削除します。ブラウザ描画やModalの応答時間を直接測るベンチマークではありません。
