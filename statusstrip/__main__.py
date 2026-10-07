"""statusstrip: tmux の帯に出す1行を出して終わる。何が起きても1行は出し、終了コードは 0。"""

import argparse
import re
import shutil
import sys
from pathlib import Path

from . import __version__, config
from .remote import REMOTE
from .segments import LOCAL, Ctx, json_value

SEGMENTS = {**LOCAL, **REMOTE}
UNKNOWN = [("?", "unknown")]


def build(name: str, conf: dict, ctx: Ctx):
    """1セグメント → (ラベル, 表示片) または None(出さない)。中で何が起きても '?' にする。"""
    if name.startswith("json."):
        section, func, default_label = conf["json"].get(name[5:]), json_value, name[5:]
    else:
        section, func, default_label = conf.get(name), SEGMENTS.get(name), name
    section = section if isinstance(section, dict) else {}
    label = str(section.get("label", default_label))
    if func is None or (name.startswith("json.") and "path" not in section):
        return label, UNKNOWN
    try:
        pieces = func(ctx, section)
    except Exception:
        return label, UNKNOWN
    return None if pieces is None else (label, pieces)


def esc(text: str) -> str:
    # tmux は #() の出力をもう一度展開する。'#(' がそのまま届くとコマンドが走るので必ず '##' にする
    return re.sub(r"[\x00-\x1f\x7f]", "", str(text)).replace("#", "##")


def style(color, text: str) -> str:
    if not isinstance(color, str) or not re.fullmatch(r"#?\w+", color):
        return text
    return f"#[fg={color}]{text}#[default]"


def render(segs, conf: dict, plain: bool) -> str:
    colors = conf["colors"]
    sep = str(conf.get("separator", " | "))
    out = []
    for label, pieces in segs:
        if plain:
            out.append(" ".join(([label] if label else []) + [t for t, _ in pieces]))
        else:
            parts = [style(colors.get("label"), esc(label))] if label else []
            parts += [style(colors.get(lvl), esc(t)) for t, lvl in pieces]
            out.append(" ".join(parts))
    return sep.join(out) if plain else style(colors.get("separator"), esc(sep)).join(out)


def line(conf: dict, err: str | None, ctx: Ctx, plain: bool) -> str:
    segs = [("CFG", [("?", "crit")])] if err else []  # 設定が読めないことを帯で知らせる
    for name in conf["order"]:
        seg = build(name, conf, ctx)
        if seg:
            segs.append(seg)
    return render(segs, conf, plain)


def snippet() -> str:
    exe = shutil.which("statusstrip") or "statusstrip"
    return (
        "# tmux.conf (~/.tmux.conf か ~/.config/tmux/tmux.conf) に足す行です。\n"
        "# statusstrip は tmux.conf を書き換えません。足したら `tmux source-file <そのファイル>` で読み直します。\n"
        "set -g status-interval 5\n"
        "set -g status-right-length 120\n"
        f'set -g status-right "#({exe})"\n'
    )


def main(argv=None, ctx: Ctx | None = None, out=None) -> int:
    out = out or sys.stdout
    for stream in (out, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # 端末の文字コードで出せない字(° など)があっても落ちない
    p = argparse.ArgumentParser(prog="statusstrip", description="tmux の帯に出す1行を出して終わります。")
    p.add_argument("--plain", action="store_true", help="tmux の色指定を付けずに出す")
    p.add_argument("--config", type=Path, help="設定ファイル (既定: ~/.config/statusstrip/config.toml)")
    p.add_argument("--print-config", action="store_true", help="既定の設定例を出す")
    p.add_argument("--snippet", action="store_true", help="tmux.conf に書く行を出す")
    p.add_argument("--root", type=Path, help="/proc と /sys を読む根 (試験用)")
    p.add_argument("--version", action="version", version=f"statusstrip {__version__}")
    args = p.parse_args(argv)

    if args.print_config:
        out.write(config.EXAMPLE_TOML)
        return 0
    if args.snippet:
        out.write(snippet())
        return 0
    try:
        ctx = ctx or Ctx()
        if args.root:
            ctx.root = args.root
        conf, err = config.load(args.config)
        if err:
            print(f"statusstrip: 設定を読めないので既定値で出します: {err}", file=sys.stderr)
        text = line(conf, err, ctx, args.plain)
    except Exception as e:  # ここまで来るのは想定外の壊れ方。帯には何か出す
        text = "statusstrip ?" if args.plain else f"#[fg=red]statusstrip ?#[default]"
        print(f"statusstrip: {e!r}", file=sys.stderr)
    out.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
