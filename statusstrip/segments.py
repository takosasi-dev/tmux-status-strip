"""手元の値(/proc・/sys・ディスク・JSON ファイル)を読むセグメント。

セグメントは f(ctx, 設定の節) -> 表示片のリスト(出さないときは None)。
表示片は (文字, 段階)。段階は ok / good / warn / crit / unknown で、色は描くときに決める。
"""

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

Piece = tuple[str, str]
NA = [("--", "unknown")]  # 差分の相手がまだ無い(初回など)


def default_state_dir(env=os.environ) -> Path:
    run = env.get("XDG_RUNTIME_DIR")
    base = Path(run) if run else Path(os.path.expanduser("~")) / ".cache"
    return base / "statusstrip"


@dataclass
class Ctx:
    """外から読む物の置き場所と時計。テストでは根・状態置き場・時計・通信を差し替える。"""
    root: Path = Path("/")
    state_dir: Path = field(default_factory=default_state_dir)
    now: Callable[[], float] = time.time
    fetch: Callable | None = None  # (url, headers, timeout) -> bytes。None なら remote.http_get
    env: dict = field(default_factory=lambda: dict(os.environ))
    disk_usage: Callable = shutil.disk_usage

    def path(self, p: str) -> Path:
        return self.root / p.lstrip("/")

    def read(self, p: str) -> str:
        return self.path(p).read_text(encoding="utf-8")

    def _state_file(self, name: str) -> Path:
        return self.state_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")

    def load_state(self, name: str) -> dict | None:
        try:
            data = json.loads(self._state_file(name).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def save_state(self, name: str, data: dict) -> None:
        """書けなくても黙る(次回も差分が取れないだけ)。途中で切れないよう別名に書いて置き換える。"""
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            f = self._state_file(name)
            tmp = f.with_name(f".{f.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, f)
        except OSError:
            pass


def level(value: float, warn=None, crit=None) -> str:
    """crit >= warn なら上がるほど悪い、crit < warn なら下がるほど悪い。"""
    if warn is not None and crit is not None and crit < warn:
        return "crit" if value <= crit else "warn" if value <= warn else "ok"
    if crit is not None and value >= crit:
        return "crit"
    if warn is not None and value >= warn:
        return "warn"
    return "ok"


def pct(value: float, c: dict) -> list[Piece]:
    return [(f"{value:.0f}%", level(value, c.get("warn"), c.get("crit")))]


def cpu(ctx: Ctx, c: dict):
    nums = [int(x) for x in ctx.read("/proc/stat").splitlines()[0].split()[1:9]]  # user..steal
    total, idle = sum(nums), nums[3] + nums[4]  # idle + iowait
    prev = ctx.load_state("cpu")
    ctx.save_state("cpu", {"total": total, "idle": idle})
    if not prev:
        return NA
    dt, di = total - prev["total"], idle - prev["idle"]
    if dt <= 0 or di < 0 or di > dt:  # 再起動などで数が戻った
        return NA
    return pct(100 * (dt - di) / dt, c)


def mem(ctx: Ctx, c: dict):
    info = {}
    for line in ctx.read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        if v.split():
            info[k] = int(v.split()[0])
    total, avail = info["MemTotal"], info["MemAvailable"]
    return pct(100 * (total - avail) / total, c)


def load(ctx: Ctx, c: dict):
    one = float(ctx.read("/proc/loadavg").split()[0])
    ncpu = sum(1 for line in ctx.read("/proc/stat").splitlines() if re.match(r"cpu\d+ ", line)) or 1
    return [(f"{one:.2f}", level(one / ncpu, c.get("warn"), c.get("crit")))]


def disk(ctx: Ctx, c: dict):
    u = ctx.disk_usage(os.path.expanduser(c.get("path", "/")))
    return pct(100 * u.used / (u.used + u.free), c)  # df と同じく予約領域を除いた割合


def human(n: float) -> str:
    for unit in "BKMG":
        if n < 1024 or unit == "G":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


def net(ctx: Ctx, c: dict):
    iface = c.get("interface", "")
    rx = tx = 0
    found = False
    for line in ctx.read("/proc/net/dev").splitlines()[2:]:
        name, _, data = line.partition(":")
        name = name.strip()
        if (iface and name != iface) or (not iface and name == "lo"):
            continue
        f = data.split()
        rx, tx, found = rx + int(f[0]), tx + int(f[8]), True
    if not found:
        raise LookupError(f"interface {iface!r} が無い")
    now = ctx.now()
    prev = ctx.load_state("net")
    ctx.save_state("net", {"rx": rx, "tx": tx, "t": now})
    if not prev:
        return NA
    dt, drx, dtx = now - prev["t"], rx - prev["rx"], tx - prev["tx"]
    if dt <= 0 or drx < 0 or dtx < 0:
        return NA
    return [(f"rx{human(drx / dt)}", "ok"), (f"tx{human(dtx / dt)}", "ok")]


def battery(ctx: Ctx, c: dict):
    base = ctx.path("/sys/class/power_supply")
    caps, statuses = [], []
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        rd = lambda n: (d / n).read_text(encoding="utf-8").strip() if (d / n).exists() else ""
        # scope=Device はマウスなど周辺機器の電池
        if rd("type") != "Battery" or rd("scope") == "Device" or not rd("capacity"):
            continue
        caps.append(int(rd("capacity")))
        statuses.append(rd("status"))
    if not caps:
        return None
    # ponytail: 複数の電池は容量の単純平均。容量差が大きい機種で正確さが要るなら energy_now で重み付け
    value = sum(caps) / len(caps)
    mark = "+" if "Charging" in statuses else "-" if "Discharging" in statuses else ""
    lvl = "ok" if mark == "+" else level(value, c.get("warn"), c.get("crit"))
    return [(f"{value:.0f}%{mark}", lvl)]


def json_value(ctx: Ctx, c: dict):
    path = os.path.expandvars(os.path.expanduser(c["path"]))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in str(c.get("key", "")).split(".") if c.get("key") else []:
        data = data[int(k)] if isinstance(data, list) else data[k]
    unit = c.get("unit", "")
    if isinstance(data, bool) or not isinstance(data, (int, float)):
        if isinstance(data, (dict, list)) or data is None:
            raise ValueError("値が数や文字ではない")
        return [(f"{data}{unit}", "ok")]
    text = f"{data}" if isinstance(data, int) else f"{data:.1f}"
    return [(text + unit, level(data, c.get("warn"), c.get("crit")))]


LOCAL = {"cpu": cpu, "mem": mem, "load": load, "disk": disk, "net": net, "battery": battery}
