# Taiyo Extension Manager

Version 1.0.13

Taiyo Blender Scripts repositoryに含まれる各Extensionを、Blenderの3D Viewサイドバーから検索、インストール、更新、アンインストールするための管理アドオンです。

This add-on searches, installs, updates, and uninstalls Taiyo Blender Scripts extensions from the Blender 3D View sidebar.

## 場所 / Location

```text
View3D > Sidebar(N) > Taiyo > Taiyo Add-on Manager
```

## 主な機能 / Features

- Taiyo Blender Scripts Remote Repositoryの登録状態を表示
- リポジトリ未登録時に、Taiyo repositoryを追加
- Remote RepositoryのmanifestからExtension一覧を動的に取得
- 名前、ID、説明、推定タグで検索
- 検索ポップアップから複数タグを選び、AND条件で絞り込み
- `csv`、`export`、`import`、`instance`、`uv`、`unreal`、`custom-property`、`mesh`、`配置`、`名前整理`、`差し替え`、`衝突` などのタグに対応
- `All`、`Installed`、`Enabled`、`Disabled`、`Available`、`Updates` で状態フィルター
- 名前順、名前逆順、更新順、状態順で並び替え
- 配布indexに記録された最終更新日をExtensionごとに表示
- 管理対象Extensionの日本語/英語説明をコンパクトに表示
- 各Extensionのインストール状態を表示
- 新しいversionがある場合はUpdateボタンを表示
- ExtensionごとにInstall / Update / Uninstallを実行
- インストール済みExtensionのEnable / Disableを切り替え
- GitHub sourceリンクとUser Manualリンクを表示
- Blender起動後に一度だけTaiyo repositoryを自動同期
- RefreshはRepository directory指定で安全に再読み込み
- Auto、日本語、Englishの表示切り替え

## 使い方 / Usage

1. BlenderでこのExtensionを有効にします。
2. 3D Viewで `N` キーを押してサイドバーを開きます。
3. `Taiyo` タブを開きます。
4. Repositoryが未登録の場合は `Add Repository` を押します。
5. 必要に応じてSearch欄、Status欄で絞り込み、Sort欄で並び替えます。
6. `Add Tag` からタグを選択します。複数選択時は、選んだタグをすべて持つExtensionだけが表示されます。
7. 選択中のタグボタンを押すと、そのタグだけを解除できます。右端の `X` ですべて解除できます。
8. 必要なExtensionの `Install`、`Update`、`Uninstall` を押します。

## Search Tags

`Add Tag` の検索ポップアップでは、次のようなタグを選択できます。

```text
csv
export
uv
unreal
collection
instance
scale
viewport
custom-property
mesh
timeline
animation
配置
読み込み
メタデータ
名前整理
差し替え
書き出し
衝突
寸法
```

## Remote Repository URL

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

## Notes

- このマネージャーはBlender標準のExtensions管理機能を使います。
- 管理対象はTaiyo Blender Scripts repositoryのRemote Repository manifestから読み込みます。新しいExtensionが配布indexに追加されると、Refreshまたは自動同期後に一覧へ追加されます。
- `Recently Updated` は、配布ビルド時に各Extensionのsource folderから取得した最終Git更新時刻を使います。古いindexに更新時刻がない場合は、名前順を補助順として使います。
- このマネージャー自身のDisable / Uninstallはサイドパネルから実行できないようにしています。
