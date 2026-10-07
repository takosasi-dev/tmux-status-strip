# tmux(StatusStrip)

tmux の下の帯(`status-right` など)に、CPU・メモリ・ディスク・GitHub Actions の結果・天気などを
1行で出すコマンドです。tmux の `#(statusstrip)` から呼ばれるたびに1行を出して終わります(常駐しません)。

## 画面

帯の右側はこう見えます(色は tmux の `#[fg=...]` で付きます。閾値を超えた値は黄・赤、取れない値は薄い色の `?`)。

```
[main] 0:vim*  1:zsh-              CPU 12% | MEM 43% | LOAD 0.52 | DISK 61% | CI dbc-agent:o | Partly cloudy +18°C
```

| セグメント | 出すもの | 例 |
|---|---|---|
| `cpu` | CPU 使用率(前回呼ばれたときからの差分。初回は `--`) | `CPU 12%` |
| `mem` | メモリ使用率(`MemAvailable` 基準) | `MEM 43%` |
| `load` | ロードアベレージ(1分) | `LOAD 0.52` |
| `disk` | `/`(設定で変更可)の使用率。`df` と同じ数え方 | `DISK 61%` |
| `net` | 送受信の速さ(毎秒。lo を除く合計か、指定したインターフェース) | `NET rx1.2M tx30.0K` |
| `battery` | 電池の残量(`+` 充電中、`-` 放電中)。電池が無ければ何も出さない | `BAT 85%+` |
| `ci` | GitHub Actions の最新の実行。`o` 成功(緑)・`x` 失敗(赤)・`~` 実行中(黄)・`-` 中止など・`?` 取れない | `CI dbc-agent:o` |
| `weather` | [wttr.in](https://wttr.in) の短い形式 | `Partly cloudy +18°C` |
| `json.<名前>` | 任意の JSON ファイルの値を1つ(ほかのツールが書き出す数値など) | `5h 42.5%` |

既定で出るのは `cpu` `mem` `load` `disk` です。Nerd Font などの特別な字体は要りません。

## 動作環境

- Linux(Arch Linux で確認)
- tmux(3.7 で確認)
- Python 3.11 以上。標準ライブラリだけで動き、依存はありません。

## 入れ方

pipx で入れる:

```sh
pipx install git+https://github.com/takosasi-dev/tmux-status-strip
```

clone して `python -m` で動かす:

```sh
git clone https://github.com/takosasi-dev/tmux-status-strip
cd tmux-status-strip
python3 -m statusstrip --plain
```

## 使い方

### tmux に出す

`statusstrip --snippet` で tmux.conf に書く行が出ます。**statusstrip は tmux.conf を書き換えません。**
自分で tmux.conf に足して、`tmux source-file ~/.tmux.conf` で読み直してください。

```sh
$ statusstrip --snippet
set -g status-interval 5
set -g status-right-length 120
set -g status-right "#(/home/you/.local/bin/statusstrip)"
```

`status-interval` の秒数ごとに呼ばれます。cpu と net はこの間の差分になります。

### コマンド

```sh
statusstrip                 # tmux の色指定付きで1行
statusstrip --plain         # 色なし(ほかのスクリプトから使うとき)
statusstrip --print-config  # 既定の設定例
statusstrip --snippet       # tmux.conf に書く行
statusstrip --config PATH   # 別の設定ファイルを使う
```

### 設定

`~/.config/statusstrip/config.toml`(`$XDG_CONFIG_HOME` があればそちら)。無くても既定値で動きます。
`statusstrip --print-config > ~/.config/statusstrip/config.toml` で書き出してから直すのが楽です。

```toml
# 出す順番。ここに書いたものだけ出ます
order = ["cpu", "mem", "disk", "ci", "weather", "json.usage"]

[cpu]
warn = 60   # これ以上で黄
crit = 80   # これ以上で赤

[ci]
repos = ["takosasi-dev/dbc-agent"]
branch = "main"

[weather]
location = "Tokyo"

[json.usage]
label = "5h"
path = "~/.local/state/something/latest.json"
key = "five_hour.utilization"
unit = "%"
warn = 70
crit = 90
```

- 閾値は `crit` を `warn` より小さくすると「下がるほど悪い」向きになります(battery の既定は `warn = 30`, `crit = 15`)。
- `load` の閾値は 1分平均をコア数で割った値と比べます。
- 色は `[colors]` で tmux の色名を指定します(空にすると色を付けません)。
- 設定ファイルが壊れていると、既定値で出したうえで帯の先頭に赤い `CFG ?` を出します(理由は標準エラーに出ます)。

### 壊れないための決まり

- どのセグメントで何が起きても、コマンドは落ちずに1行を出します。取れない値は薄い色の `?` です。
- `ci` と `weather` は結果をキャッシュします(既定 5分 / 30分)。期限が切れたら1回だけ取りに行き(タイムアウト 2秒)、
  失敗したら前回の値を出します。失敗しても次に試すのは期限が切れてから。
- トークンなしの GitHub API は 1時間に 60回までなので、リポジトリの数に合わせて間隔を自動で延ばし、1時間 50回以内に収めます。
- 前回の値とキャッシュは `$XDG_RUNTIME_DIR/statusstrip/`(無ければ `~/.cache/statusstrip/`)に置きます。

## 安全面の注意

- GitHub のトークンは環境変数 `GITHUB_TOKEN` からだけ読みます。引数や設定ファイルでは受け取らず、キャッシュにも書きません。
  公開リポジトリならトークンは要りません。tmux から呼ばれるときは tmux サーバーの環境変数が使われます。
- tmux は `#()` の出力に含まれる `#{...}` や `#(...)` をもう一度展開します(`#(...)` ならコマンドが走ります)。
  statusstrip は天気や JSON の値など外から来た文字の `#` をすべて `##` にしてから出すので、これらが展開されることはありません。
- `weather` は wttr.in に、設定した場所の名前を送ります。

## ライセンス

MIT(`LICENSE` を見てください)。

## 開発状況

v0.1.0。テストは `python tests/run_all.py`(/proc・/sys・GitHub API・wttr.in の応答は手で作った fixture。ネットワークには出ません)。
