import io
import tempfile
import tomllib
import unittest
from collections import namedtuple
from pathlib import Path

from helpers import FIX, FakeFetch, make_ctx

from statusstrip import __main__ as m
from statusstrip import config
from statusstrip.config import DEFAULTS

Usage = namedtuple("Usage", "total used free")


def run(test, *argv, ctx=None, conf_text=None):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    conf = Path(tmp.name) / "config.toml"  # 無いファイル = 設定なし
    if conf_text is not None:
        conf.write_text(conf_text, encoding="utf-8")
    out = io.StringIO()
    ctx = ctx or make_ctx(test, disk_usage=lambda p: Usage(100, 50, 50))
    rc = m.main(["--config", str(conf), *argv], ctx=ctx, out=out)
    test.assertEqual(rc, 0)
    text = out.getvalue()
    test.assertEqual(text.count("\n"), 1, text)
    return text.rstrip("\n")


class Line(unittest.TestCase):
    def test_default_plain(self):
        self.assertEqual(run(self, "--plain"), "CPU -- | MEM 75% | LOAD 3.20 | DISK 50%")

    def test_default_tmux_colors(self):
        out = run(self)
        self.assertIn("MEM #[fg=yellow]75%#[default]", out)
        self.assertIn("CPU #[fg=colour244]--#[default]", out)
        self.assertIn("#[fg=colour244] | #[default]", out)

    def test_order_and_hide(self):
        out = run(self, "--plain", conf_text='order = ["battery", "load"]\nseparator = " / "\n[battery]\nlabel = "電池"\n')
        self.assertEqual(out, "電池 42%- / LOAD 3.20")

    def test_absent_battery_is_omitted(self):
        out = run(self, "--plain", ctx=make_ctx(self, "t1"), conf_text='order = ["battery", "cpu"]\n')
        self.assertEqual(out, "CPU --")

    def test_broken_segments_are_question_marks(self):
        conf = 'order = ["mem", "net", "nope", "json.x", "json.missing"]\n[net]\ninterface = "nope0"\n' \
               '[json.x]\npath = "/does/not/exist.json"\n'
        out = run(self, "--plain", ctx=make_ctx(self, "t1"), conf_text=conf)  # t1 には meminfo が無い
        self.assertEqual(out, "MEM ? | NET ? | nope ? | x ? | missing ?")

    def test_bad_config_still_prints(self):
        out = run(self, "--plain", conf_text="order = [\n")
        self.assertEqual(out, "CFG ? | CPU -- | MEM 75% | LOAD 3.20 | DISK 50%")
        out = run(self, "--plain", conf_text="order = 3\n")
        self.assertTrue(out.startswith("CFG ? | CPU"))

    def test_unexpected_crash_still_prints(self):
        ctx = make_ctx(self)
        orig = m.line
        m.line = lambda *a: 1 / 0
        self.addCleanup(setattr, m, "line", orig)
        self.assertEqual(run(self, "--plain", ctx=ctx), "statusstrip ?")

    def test_hash_from_network_is_escaped(self):
        # 天気の文字に #(...) が混ざっても tmux にコマンドとして渡らない
        ctx = make_ctx(self, fetch=FakeFetch(b"#(touch /tmp/pwned) #[fg=red]x"))
        out = run(self, ctx=ctx, conf_text='order = ["weather"]\n')
        self.assertEqual(out, "##(touch /tmp/pwned) ##[fg=red]x")
        self.assertEqual(run(self, "--plain", ctx=ctx, conf_text='order = ["weather"]\n'),
                         "#(touch /tmp/pwned) #[fg=red]x")

    def test_bad_color_is_ignored(self):
        out = run(self, conf_text='order = ["mem"]\n[colors]\nwarn = "red]#(x)"\n')
        self.assertEqual(out, "MEM 75%")


class Commands(unittest.TestCase):
    def test_print_config_is_the_defaults(self):
        out = io.StringIO()
        m.main(["--print-config"], out=out)
        self.assertEqual(tomllib.loads(out.getvalue()), DEFAULTS)
        self.assertEqual(DEFAULTS["order"], ["cpu", "mem", "load", "disk"])

    def test_snippet(self):
        out = io.StringIO()
        m.main(["--snippet"], out=out)
        self.assertIn('set -g status-right "#(', out.getvalue())
        self.assertIn("set -g status-interval", out.getvalue())

    def test_config_path_xdg(self):
        self.assertEqual(config.config_path({"XDG_CONFIG_HOME": "/x"}), Path("/x/statusstrip/config.toml"))

    def test_state_dir_xdg(self):
        from statusstrip.segments import default_state_dir
        self.assertEqual(default_state_dir({"XDG_RUNTIME_DIR": "/run/user/1000"}),
                         Path("/run/user/1000/statusstrip"))


if __name__ == "__main__":
    unittest.main()
