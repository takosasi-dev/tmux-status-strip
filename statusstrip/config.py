"""設定ファイルの読み込み。既定値は EXAMPLE_TOML そのもの(--print-config と食い違わないように)。"""

import os
import tomllib
from pathlib import Path

EXAMPLE_TOML = """\
# statusstrip の設定 (~/.config/statusstrip/config.toml)
# どの項目も省略できます。省略したところは既定値になります。

# 出す順番。ここに書いたものだけが出ます。
# 使えるもの: cpu mem load disk net battery ci weather json.<名前>
order = ["cpu", "mem", "load", "disk"]
separator = " | "

# 閾値: 値が warn 以上で warn の色、crit 以上で crit の色。
# crit を warn より小さくすると「下がるほど悪い」向きになります(battery の既定)。

[colors]
# tmux の色名 (red, colour244, #ff8800 など)。空にすると色を付けません。
label = ""
ok = ""
good = "green"
warn = "yellow"
crit = "red"
unknown = "colour244"
separator = "colour244"

[cpu]
label = "CPU"
warn = 60
crit = 80

[mem]
label = "MEM"
warn = 75
crit = 90

[load]
label = "LOAD"
# 1分平均をコア数で割った値で判定します(表示は割る前の値)
warn = 0.7
crit = 1.0

[disk]
label = "DISK"
path = "/"
warn = 80
crit = 90

[net]
label = "NET"
# 空なら lo 以外の全部の合計
interface = ""

[battery]
label = "BAT"
warn = 30
crit = 15

[ci]
label = "CI"
# 例: repos = ["takosasi-dev/dbc-agent"]
# 非公開リポジトリやたくさん並べるときは環境変数 GITHUB_TOKEN を設定します
# (トークンはこのファイルには書けません)。
repos = []
# 空ならすべてのブランチの最新の実行
branch = ""
# 秒。トークンなしのときは 1時間に 50回を超えないよう自動で延ばします
ttl = 300

[weather]
label = ""
# 例: "Tokyo"。空なら wttr.in が接続元から推測します
location = ""
# wttr.in の format (%C 天気, %t 気温, %w 風, %h 湿度 など)
format = "%C %t"
# m = メートル法, u = ヤード・ポンド法
units = "m"
ttl = 1800

# json: 任意の JSON ファイルから値を1つ出します。order に "json.usage" のように書きます。
# [json.usage]
# label = "5h"
# path = "~/.local/state/something/latest.json"
# key = "five_hour.utilization"   # 点区切り。配列は 0 などの番号
# unit = "%"
# warn = 70
# crit = 90
[json]
"""

DEFAULTS = tomllib.loads(EXAMPLE_TOML)


def config_path(env=os.environ) -> Path:
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "statusstrip" / "config.toml"


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load(path: Path | None = None) -> tuple[dict, str | None]:
    """(設定, エラー文) を返す。読めなければ既定値とエラー文。ファイルが無いのはエラーではない。"""
    path = path or config_path()
    try:
        with open(path, "rb") as f:
            conf = merge(DEFAULTS, tomllib.load(f))
    except FileNotFoundError:
        return DEFAULTS, None
    except (OSError, tomllib.TOMLDecodeError) as e:
        return DEFAULTS, f"{path}: {e}"
    if not (isinstance(conf.get("order"), list) and all(isinstance(x, str) for x in conf["order"])):
        return DEFAULTS, f"{path}: order は文字列の配列にしてください"
    for k in ("colors", "json"):
        if not isinstance(conf.get(k), dict):
            return DEFAULTS, f"{path}: [{k}] は表にしてください"
    return conf, None
