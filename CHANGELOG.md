# Changelog

このプロジェクトの変更点を書きます。形式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、
版の付け方は [Semantic Versioning](https://semver.org/lang/ja/) に従います。

## [0.1.0] - 2026-10-08

### Added

- `statusstrip`: tmux の帯に出す1行を出して終わるコマンド。`#[fg=...]` の色付き、`--plain` で色なし。
- セグメント: cpu・mem・load・disk・net・battery(電池があるときだけ)・ci(GitHub Actions)・weather(wttr.in)・json(任意の JSON ファイルの値)。
- 設定ファイル `~/.config/statusstrip/config.toml`(`$XDG_CONFIG_HOME` 優先)。並び順・表示/非表示・閾値・色を変えられる。
- ci と weather は結果をキャッシュし(既定 5分 / 30分)、取りに行けなければ古い値を出す。タイムアウト 2秒。
  トークンなしの GitHub API は 1時間に 50回を超えないよう間隔を自動で延ばす。
- `--print-config`(既定の設定例)と `--snippet`(tmux.conf に書く行)。
