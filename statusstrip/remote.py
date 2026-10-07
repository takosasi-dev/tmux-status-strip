"""ネットワークを使うセグメント(GitHub Actions・wttr.in)。

呼ばれるたびに取りに行かない: 結果を状態置き場に残し、ttl を過ぎたときだけ1回取りに行く。
取りに行った時刻は成否に関係なく残すので、失敗しても ttl ごとに1回しか試さない
(GitHub の回数制限を食いつぶさない)。失敗したら前回の値を出す。
"""

import json
import re
import urllib.parse
import urllib.request

from . import __version__
from .segments import Ctx, Piece

TIMEOUT = 2.0
MIN_TTL = 60
GITHUB_BUDGET = 50  # トークンなしの上限は 60回/時。ほかの用途のぶんを残す


def http_get(url: str, headers: dict, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"statusstrip/{__version__}", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1_000_000)


def cached(ctx: Ctx, key: str, ttl: float, get):
    """ttl 以内なら前回の値。過ぎていれば get() を試し、失敗したら前回の値(無ければ None)。"""
    st = ctx.load_state(key) or {}
    now = ctx.now()
    tried = st.get("tried")
    if isinstance(tried, (int, float)) and 0 <= now - tried < ttl:
        return st.get("value")
    st["tried"] = now
    ctx.save_state(key, st)  # 先に残す: 同時に呼ばれた別の帯が二重に取りに行かないように
    try:
        st["value"] = get()
        ctx.save_state(key, st)
    except Exception:
        pass
    return st.get("value")


def _fetch(ctx: Ctx):
    return ctx.fetch or http_get


# ---- GitHub Actions ----

CI_MARKS = {
    "success": ("o", "good"),
    "failure": ("x", "crit"),
    "timed_out": ("x", "crit"),
    "startup_failure": ("x", "crit"),
    "running": ("~", "warn"),
}


def parse_runs(body: bytes) -> str:
    """runs API の応答 → success / failure / running / cancelled / none など。"""
    runs = json.loads(body)["workflow_runs"]
    if not runs:
        return "none"
    r = runs[0]
    if r.get("status") != "completed":
        return "running"
    return r.get("conclusion") or "unknown"


def ci(ctx: Ctx, c: dict):
    repos = c.get("repos") or []
    if not repos:
        return None
    token = ctx.env.get("GITHUB_TOKEN", "")  # トークンは環境変数からだけ読む
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    ttl = max(float(c.get("ttl", 300)), MIN_TTL)
    if not token:
        ttl = max(ttl, 3600 * len(repos) / GITHUB_BUDGET)
    branch = c.get("branch", "")
    query = {"per_page": "1", **({"branch": branch} if branch else {})}
    out: list[Piece] = []
    for repo in repos:
        name = str(repo).rsplit("/", 1)[-1]
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(repo)):
            out.append((f"{name}:?", "unknown"))
            continue
        url = f"https://api.github.com/repos/{repo}/actions/runs?{urllib.parse.urlencode(query)}"
        state = cached(ctx, f"ci-{repo}-{branch}", ttl,
                       lambda: parse_runs(_fetch(ctx)(url, headers, TIMEOUT)))
        mark, lvl = CI_MARKS.get(state, ("-", "unknown")) if state else ("?", "unknown")
        out.append((f"{name}:{mark}", lvl))
    return out


# ---- wttr.in ----

def parse_weather(body: bytes) -> str:
    text = body.decode("utf-8", "replace").strip().splitlines()[0] if body.strip() else ""
    text = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", text).split())  # wttr.in は %C を空白で埋めてくる
    low = text.lower()
    if not text or "<" in text or len(text) > 80 or low.startswith(("unknown location", "sorry", "error")):
        raise ValueError(f"wttr.in の応答が天気ではない: {text[:40]!r}")
    return text


def weather(ctx: Ctx, c: dict):
    loc = c.get("location", "")
    query = urllib.parse.urlencode({"format": c.get("format", "%C %t")})
    units = c.get("units", "m")
    if units in ("m", "u", "M"):
        query += f"&{units}"
    url = f"https://wttr.in/{urllib.parse.quote(loc)}?{query}"
    ttl = max(float(c.get("ttl", 1800)), MIN_TTL)
    text = cached(ctx, f"weather-{loc}-{query}", ttl, lambda: parse_weather(_fetch(ctx)(url, {}, TIMEOUT)))
    return [(text, "ok")] if text else [("?", "unknown")]


REMOTE = {"ci": ci, "weather": weather}
