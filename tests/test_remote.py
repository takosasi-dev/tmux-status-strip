import unittest

from helpers import FIX, FakeFetch, make_ctx

from statusstrip import remote as r
from statusstrip.config import DEFAULTS


def gh(name: str) -> bytes:
    return (FIX / "github" / f"{name}.json").read_bytes()


def ci_conf(**kw):
    return {**DEFAULTS["ci"], "repos": ["example-user/example-repo"], **kw}


class ParseRuns(unittest.TestCase):
    def test_states(self):
        self.assertEqual(r.parse_runs(gh("success")), "success")
        self.assertEqual(r.parse_runs(gh("failure")), "failure")
        self.assertEqual(r.parse_runs(gh("running")), "running")
        self.assertEqual(r.parse_runs(gh("empty")), "none")

    def test_garbage(self):
        with self.assertRaises(Exception):
            r.parse_runs(b"<html>rate limited</html>")


class Ci(unittest.TestCase):
    def test_marks(self):
        for name, want in [("success", ("example-repo:o", "good")), ("failure", ("example-repo:x", "crit")),
                           ("running", ("example-repo:~", "warn")), ("empty", ("example-repo:-", "unknown"))]:
            ctx = make_ctx(self, fetch=FakeFetch(gh(name)))
            self.assertEqual(r.ci(ctx, ci_conf()), [want], name)

    def test_cache_ttl_and_stale_on_failure(self):
        fetch = FakeFetch(gh("success"))
        ctx = make_ctx(self, fetch=fetch)
        r.ci(ctx, ci_conf())
        ctx.now.t += 299
        fetch.body = gh("failure")
        self.assertEqual(r.ci(ctx, ci_conf()), [("example-repo:o", "good")])  # 5分以内は取りに行かない
        self.assertEqual(len(fetch.calls), 1)
        ctx.now.t += 2
        fetch.body = TimeoutError("timed out")
        self.assertEqual(r.ci(ctx, ci_conf()), [("example-repo:o", "good")])  # 失敗 → 古い値
        self.assertEqual(len(fetch.calls), 2)
        ctx.now.t += 10
        r.ci(ctx, ci_conf())
        self.assertEqual(len(fetch.calls), 2)  # 失敗しても次は ttl 後
        ctx.now.t += 300
        fetch.body = gh("failure")
        self.assertEqual(r.ci(ctx, ci_conf()), [("example-repo:x", "crit")])

    def test_first_failure_is_question(self):
        ctx = make_ctx(self, fetch=FakeFetch(OSError("network down")))
        self.assertEqual(r.ci(ctx, ci_conf()), [("example-repo:?", "unknown")])

    def test_timeout_and_url(self):
        fetch = FakeFetch(gh("success"))
        r.ci(make_ctx(self, fetch=fetch), ci_conf(branch="main"))
        url, headers, timeout = fetch.calls[0]
        self.assertEqual(url, "https://api.github.com/repos/example-user/example-repo/actions/runs?per_page=1&branch=main")
        self.assertEqual(timeout, 2.0)
        self.assertNotIn("Authorization", headers)

    def test_token_only_from_env_and_not_cached(self):
        fetch = FakeFetch(gh("success"))
        ctx = make_ctx(self, fetch=fetch)
        r.ci(ctx, ci_conf(token="from-config-must-be-ignored"))
        self.assertNotIn("Authorization", fetch.calls[0][1])
        ctx = make_ctx(self, fetch=fetch, env={"GITHUB_TOKEN": "tok-123"})
        r.ci(ctx, ci_conf())
        self.assertEqual(fetch.calls[1][1]["Authorization"], "Bearer tok-123")
        for f in ctx.state_dir.iterdir():
            self.assertNotIn("tok-123", f.read_text(encoding="utf-8"))

    def test_rate_budget_without_token(self):
        # 20 リポジトリ・ttl 60 秒でも、トークンなしなら 1時間に 50回を超えない
        repos = [f"example-user/repo{i}" for i in range(20)]
        fetch = FakeFetch(gh("success"))
        ctx = make_ctx(self, fetch=fetch)
        for _ in range(3600 // 5):  # 5秒ごとに帯を描く1時間
            r.ci(ctx, ci_conf(repos=repos, ttl=60))
            ctx.now.t += 5
        self.assertLessEqual(len(fetch.calls), r.GITHUB_BUDGET + len(repos))

    def test_bad_repo_name_not_fetched(self):
        ctx = make_ctx(self)  # no_network: 取りに行けば落ちる
        self.assertEqual(r.ci(ctx, ci_conf(repos=["../../evil?x=1"])), [("evil?x=1:?", "unknown")])

    def test_no_repos(self):
        self.assertIsNone(r.ci(make_ctx(self), DEFAULTS["ci"]))


class Weather(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(r.parse_weather((FIX / "wttr" / "ok.txt").read_bytes()), "Partly cloudy +18°C")
        for bad in [(FIX / "wttr" / "unknown.txt").read_bytes(), b"", b"<html></html>", b"x" * 200]:
            with self.assertRaises(ValueError):
                r.parse_weather(bad)

    def test_cache_30min_and_stale(self):
        fetch = FakeFetch((FIX / "wttr" / "ok.txt").read_bytes())
        ctx = make_ctx(self, fetch=fetch)
        conf = {**DEFAULTS["weather"], "location": "Tokyo"}
        self.assertEqual(r.weather(ctx, conf), [("Partly cloudy +18°C", "ok")])
        self.assertTrue(fetch.calls[0][0].startswith("https://wttr.in/Tokyo?format=%25C+%25t&m"))
        ctx.now.t += 1799
        r.weather(ctx, conf)
        self.assertEqual(len(fetch.calls), 1)
        ctx.now.t += 2
        fetch.body = (FIX / "wttr" / "unknown.txt").read_bytes()
        self.assertEqual(r.weather(ctx, conf), [("Partly cloudy +18°C", "ok")])
        self.assertEqual(len(fetch.calls), 2)

    def test_never_fetched(self):
        ctx = make_ctx(self, fetch=FakeFetch(OSError("down")))
        self.assertEqual(r.weather(ctx, DEFAULTS["weather"]), [("?", "unknown")])


if __name__ == "__main__":
    unittest.main()
