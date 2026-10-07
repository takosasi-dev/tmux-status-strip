import json
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

from helpers import FIX, make_ctx

from statusstrip import segments as s
from statusstrip.config import DEFAULTS

Usage = namedtuple("Usage", "total used free")


class Level(unittest.TestCase):
    def test_high_is_bad(self):
        self.assertEqual([s.level(v, 60, 80) for v in (10, 60, 79.9, 80)], ["ok", "warn", "warn", "crit"])

    def test_low_is_bad(self):
        self.assertEqual([s.level(v, 30, 15) for v in (90, 30, 16, 15, 0)], ["ok", "warn", "warn", "crit", "crit"])

    def test_no_threshold(self):
        self.assertEqual(s.level(1e9), "ok")


class Cpu(unittest.TestCase):
    def test_first_call_is_na_then_diff(self):
        ctx = make_ctx(self, "t0")
        self.assertEqual(s.cpu(ctx, DEFAULTS["cpu"]), [("--", "unknown")])
        ctx.root = FIX / "t1"
        # 総 10000→11000, idle+iowait 8500→9100 → 使用 400/1000
        self.assertEqual(s.cpu(ctx, DEFAULTS["cpu"]), [("40%", "ok")])

    def test_threshold_from_config(self):
        ctx = make_ctx(self, "t0")
        s.cpu(ctx, {})
        ctx.root = FIX / "t1"
        self.assertEqual(s.cpu(ctx, {"warn": 30, "crit": 40}), [("40%", "crit")])

    def test_counter_went_back(self):
        ctx = make_ctx(self, "t1")
        s.cpu(ctx, {})
        ctx.root = FIX / "t0"  # 再起動で数が戻った
        self.assertEqual(s.cpu(ctx, {}), [("--", "unknown")])

    def test_state_dir_unwritable_still_works(self):
        ctx = make_ctx(self, "t0")
        ctx.state_dir = FIX / "github" / "success.json" / "x"  # ファイルの下には作れない
        self.assertEqual(s.cpu(ctx, {}), [("--", "unknown")])


class Others(unittest.TestCase):
    def test_mem_uses_memavailable(self):
        self.assertEqual(s.mem(make_ctx(self), DEFAULTS["mem"]), [("75%", "warn")])

    def test_load_per_core(self):
        # 3.20 / 4コア = 0.8 → warn(0.7) 以上 crit(1.0) 未満
        self.assertEqual(s.load(make_ctx(self), DEFAULTS["load"]), [("3.20", "warn")])

    def test_disk_like_df(self):
        ctx = make_ctx(self, disk_usage=lambda p: Usage(total=100, used=85, free=10))
        self.assertEqual(s.disk(ctx, DEFAULTS["disk"]), [("89%", "warn")])

    def test_disk_real_path(self):
        ctx = make_ctx(self)
        text, _ = s.disk(ctx, {"path": str(FIX)})[0]
        self.assertTrue(text.endswith("%"))

    def test_net_rate_skips_lo(self):
        ctx = make_ctx(self, "t0")
        self.assertEqual(s.net(ctx, DEFAULTS["net"]), [("--", "unknown")])
        ctx.root = FIX / "t1"
        ctx.now.t += 2
        self.assertEqual(s.net(ctx, DEFAULTS["net"]), [("rx1.5M", "ok"), ("tx10.0K", "ok")])

    def test_net_interface_missing(self):
        with self.assertRaises(LookupError):
            s.net(make_ctx(self), {"interface": "nope0"})

    def test_net_clock_went_back(self):
        ctx = make_ctx(self, "t0")
        s.net(ctx, {})
        ctx.root = FIX / "t1"
        ctx.now.t -= 5
        self.assertEqual(s.net(ctx, {}), [("--", "unknown")])

    def test_battery_ignores_peripherals(self):
        self.assertEqual(s.battery(make_ctx(self), DEFAULTS["battery"]), [("42%-", "ok")])

    def test_battery_absent(self):
        self.assertIsNone(s.battery(make_ctx(self, "t1"), DEFAULTS["battery"]))

    def test_human(self):
        self.assertEqual([s.human(n) for n in (0, 1023, 1536, 5 * 1024**3)], ["0B", "1023B", "1.5K", "5.0G"])


class JsonValue(unittest.TestCase):
    def write(self, data) -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "v.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    def test_nested_key_and_threshold(self):
        path = self.write({"five_hour": {"utilization": 72.25}, "items": [{"n": 3}]})
        ctx = make_ctx(self)
        c = {"path": path, "key": "five_hour.utilization", "unit": "%", "warn": 70, "crit": 90}
        self.assertEqual(s.json_value(ctx, c), [("72.2%", "warn")])
        self.assertEqual(s.json_value(ctx, {"path": path, "key": "items.0.n"}), [("3", "ok")])

    def test_string_value(self):
        path = self.write({"state": "idle"})
        self.assertEqual(s.json_value(make_ctx(self), {"path": path, "key": "state"}), [("idle", "ok")])

    def test_missing_key_raises(self):
        path = self.write({"a": 1})
        with self.assertRaises(KeyError):
            s.json_value(make_ctx(self), {"path": path, "key": "b"})

    def test_object_is_not_a_value(self):
        path = self.write({"a": {"b": 1}})
        with self.assertRaises(ValueError):
            s.json_value(make_ctx(self), {"path": path, "key": "a"})


if __name__ == "__main__":
    unittest.main()
