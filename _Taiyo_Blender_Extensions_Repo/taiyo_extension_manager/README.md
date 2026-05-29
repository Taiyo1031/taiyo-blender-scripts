# Taiyo Extension Manager

Taiyo Blender Scripts repositoryに含まれる各Extensionを、Blenderの3D Viewサイドバーからインストール/アンインストールするための管理アドオンです。

This add-on manages the Taiyo Blender Scripts extensions from the Blender 3D View sidebar.

## 場所 / Location

```text
View3D > Sidebar(N) > Taiyo > Taiyo Add-on Manager
```

## 主な機能 / Features

- Taiyo Blender Scripts Remote Repositoryの登録状態を表示
- リポジトリ未登録時に、Taiyo repositoryを追加
- 管理対象Extensionの日本語/英語説明を表示
- 各Extensionのインストール状態を表示
- ExtensionごとにInstall / Uninstallを実行
- インストール済みExtensionのEnable / Disableを切り替え
- 日本語、English、日本語 + Englishの表示切り替え

## 使い方 / Usage

1. BlenderでこのExtensionを有効にします。
2. 3D Viewで `N` キーを押してサイドバーを開きます。
3. `Taiyo` タブを開きます。
4. Repositoryが未登録の場合は `Add Repository` を押します。
5. Refreshボタンを押してRemote Repositoryを同期します。
6. 必要なExtensionの `Install` または `Uninstall` を押します。

## Remote Repository URL

```text
https://taiyo1031.github.io/taiyo-blender-scripts/extensions/index.json
```

## Notes

- このマネージャーはBlender標準のExtensions管理機能を使います。
- 管理対象はTaiyo Blender Scripts repository内の通常Extensionです。このマネージャー自身の自己アンインストールは一覧に含めていません。
- 一部ExtensionはBlender 4.4または4.5.9以降を必要とします。未対応バージョンではInstallボタンが無効表示になります。
