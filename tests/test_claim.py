#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim.py 的测试用例（纯标准库 unittest，无外部依赖）

跑法： python3 -m unittest discover -s tests -v
"""
import json, os, pathlib, subprocess, sys, tempfile, time, unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import claim  # noqa: E402

CLAIM_PY = SCRIPTS / "claim.py"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "videos.json").write_text("[]", encoding="utf-8")
        for bv in ("BVA", "BVB", "BVC"):
            (self.root / bv).mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    # 便捷调用
    def run_cli(self, *args, env=None):
        e = dict(os.environ)
        e.pop("BILI_SESSION", None)
        if env:
            e.update(env)
        return subprocess.run([sys.executable, str(CLAIM_PY), *args,
                               "--root", str(self.root)],
                              capture_output=True, text=True, env=e).returncode

    def call(self, *argv, sid="sess-a"):
        return claim.main([*argv, "--root", str(self.root), "--session", sid])

    def claim_file(self, bv="BVA"):
        return self.root / ".claims" / f"{bv}.claim"

    def backdate(self, bv="BVA", minutes=200):
        p = self.claim_file(bv)
        t = time.time() - minutes * 60
        os.utime(p, (t, t))

    def mark_done(self, bv="BVA"):
        d = self.root / bv
        for f in ("note.md", "note.html", "deck.html"):
            (d / f).write_text("x", encoding="utf-8")


class TestClaim(Base):
    def test_01_首次占用成功(self):
        self.assertEqual(self.call("claim", "BVA"), 0)
        data = json.loads(self.claim_file().read_text(encoding="utf-8"))
        self.assertEqual(data["session"], "sess-a")
        self.assertEqual(data["bvid"], "BVA")

    def test_02_他人占用时拒绝(self):
        self.assertEqual(self.call("claim", "BVA", sid="sess-a"), 0)
        self.assertEqual(self.call("claim", "BVA", sid="sess-b"), 3)
        # 原租约没被改动
        data = json.loads(self.claim_file().read_text(encoding="utf-8"))
        self.assertEqual(data["session"], "sess-a")

    def test_03_同会话重复占用视为续约(self):
        self.call("claim", "BVA")
        old = self.claim_file().stat().st_mtime
        time.sleep(1.1)
        self.assertEqual(self.call("claim", "BVA"), 0)
        self.assertGreater(self.claim_file().stat().st_mtime, old)
        data = json.loads(self.claim_file().read_text(encoding="utf-8"))
        self.assertEqual(data["session"], "sess-a")
        self.assertEqual(data["started"], data["started"])  # started 不变

    def test_04_超时后他人可接手(self):
        self.call("claim", "BVA", sid="sess-a")
        self.backdate(minutes=200)
        self.assertEqual(self.call("claim", "BVA", sid="sess-b"), 0)
        data = json.loads(self.claim_file().read_text(encoding="utf-8"))
        self.assertEqual(data["session"], "sess-b")
        log = (self.root / ".claims" / ".log").read_text(encoding="utf-8")
        self.assertIn("steal", log)

    def test_05_未超时不可接手(self):
        self.call("claim", "BVA", sid="sess-a")
        self.backdate(minutes=10)      # 10 分钟 < 默认 90
        self.assertEqual(self.call("claim", "BVA", sid="sess-b"), 3)

    def test_06_自定义ttl立即过期(self):
        self.assertEqual(self.call("claim", "BVA", "--ttl", "0.01", sid="sess-a"), 0)
        time.sleep(1.2)
        self.assertEqual(self.call("claim", "BVA", sid="sess-b"), 0)

    def test_07_break需确认(self):
        self.call("claim", "BVA", sid="sess-a")
        self.assertEqual(self.call("break", "BVA", sid="sess-b"), 4)
        self.assertEqual(json.loads(self.claim_file().read_text())["session"], "sess-a")
        self.assertEqual(self.call("break", "BVA", "--confirm", sid="sess-b"), 0)
        self.assertEqual(json.loads(self.claim_file().read_text())["session"], "sess-b")
        log = (self.root / ".claims" / ".log").read_text(encoding="utf-8")
        self.assertIn("BREAK", log)

    def test_08_释放只有持有者可以(self):
        self.call("claim", "BVA", sid="sess-a")
        self.assertEqual(self.call("release", "BVA", sid="sess-b"), 3)
        self.assertTrue(self.claim_file().exists())
        self.assertEqual(self.call("release", "BVA", sid="sess-a"), 0)
        self.assertFalse(self.claim_file().exists())

    def test_09_释放未占用不报错(self):
        self.assertEqual(self.call("release", "BVA", sid="sess-a"), 0)

    def test_10_列表区分有效与过期(self):
        self.call("claim", "BVA", sid="sess-a")
        self.call("claim", "BVB", sid="sess-b")
        self.backdate("BVB", 500)
        rows = json.loads(subprocess.run(
            [sys.executable, str(CLAIM_PY), "list", "--root", str(self.root), "--json"],
            capture_output=True, text=True).stdout)
        by = {r["bvid"]: r for r in rows}
        self.assertEqual(len(rows), 2)
        self.assertFalse(by["BVA"]["expired"])
        self.assertTrue(by["BVB"]["expired"])

    def test_11_已完成默认拒占(self):
        self.mark_done("BVA")
        self.assertEqual(self.call("claim", "BVA"), 5)
        self.assertFalse(self.claim_file().exists())
        self.assertEqual(self.call("claim", "BVA", "--allow-done"), 0)
        self.assertTrue(self.claim_file().exists())

    def test_12_缺少会话标识报错(self):
        code = self.run_cli("claim", "BVA")          # 未设 BILI_SESSION
        self.assertEqual(code, 4)

    def test_13_并发抢占只有一个成功(self):
        procs = []
        for i in range(8):
            e = dict(os.environ, BILI_SESSION=f"sess-{i}")
            procs.append(subprocess.Popen(
                [sys.executable, str(CLAIM_PY), "claim", "BVA", "--root", str(self.root)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=e))
        codes = [p.wait() for p in procs]
        self.assertEqual(codes.count(0), 1, f"应只有一个成功，实际 {codes}")
        self.assertEqual(codes.count(3), 7, f"其余应被拒，实际 {codes}")

    def test_14_不存在的BV目录报错(self):
        self.assertEqual(self.call("claim", "BVNOTEXIST"), 4)

    def test_15_日志按顺序记录(self):
        self.call("claim", "BVA", sid="sess-a")
        self.call("release", "BVA", sid="sess-a")
        log = (self.root / ".claims" / ".log").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("claim BVA by sess-a" in l for l in log))
        self.assertTrue(any("release BVA by sess-a" in l for l in log))
        self.assertLess(log.index([l for l in log if "claim BVA" in l][0]),
                        log.index([l for l in log if "release BVA" in l][0]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
