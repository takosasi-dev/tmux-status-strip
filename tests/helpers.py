import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from statusstrip.segments import Ctx  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def no_network(*a, **k):
    raise AssertionError("テストでネットワークに出ようとした")


class FakeFetch:
    """URL ごとの応答を返し、呼ばれた回数と送ったヘッダを覚える。応答が例外なら投げる。"""

    def __init__(self, body):
        self.body = body
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def make_ctx(test, root="t0", **kw) -> Ctx:
    """状態置き場は test の後片付けで消える一時フォルダ。"""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    kw.setdefault("now", Clock())
    kw.setdefault("fetch", no_network)
    kw.setdefault("env", {})
    return Ctx(root=FIX / root, state_dir=Path(tmp.name) / "state", **kw)
