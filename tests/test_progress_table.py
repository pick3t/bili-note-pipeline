#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress.py / sync_progress.py 的回归测试（纯标准库 unittest）

跑法： python3 -m unittest discover -s tests -v

背景：进度表会把「不在 videos.json 里的 BV* 目录」当作新视频，而这类目录
没有发布时间，排序时 `created or 0` 把它们顶到第 1 位，导致全表序号整体 +1。
用户按序号分配区间，一移位就等于全部对错集。
真实事故：拆篇时另建了 `BV1PHS5BuEvR-2` 目录，线上表从 117 集变 118 集，
61 号那一集变成 62 号。

本文件锁两件事：
  1) `BV1xxx-N` 视为同一集（不单独成行，文件计入主行）
  2) 其余未收录目录排到末尾，已有序号绝不移位
  3) sync 的防倒退按「逐集」判定，不被重复行污染
"""
import json, pathlib, re, subprocess, sys, tempfile, unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import sync_progress as sp  # noqa: E402

PROGRESS_PY = SCRIPTS / "progress.py"

BV_A, BV_B, BV_C, BV_NEW = "BV1aaa111", "BV1bbb222", "BV1ccc333", "BV1zzz999"


class ProgressTable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        vids = [
            {"bvid": BV_A, "title": "老一", "created": 1700000000},
            {"bvid": BV_B, "title": "老二", "created": 1700100000},
            {"bvid": BV_C, "title": "老三", "created": 1700200000},
        ]
        (self.root / "videos.json").write_text(
            json.dumps(vids, ensure_ascii=False), encoding="utf-8")
        self.mkdir(BV_A, ["source.md", "note.md", "note.html", "deck.html"])
        self.mkdir(BV_B, ["source.md", "note.md", "note.html", "deck.html"])
        self.mkdir(BV_C, ["source.md"])

    def tearDown(self):
        self.tmp.cleanup()

    def mkdir(self, name, files):
        d = self.root / name
        d.mkdir()
        for f in files:
            (d / f).write_text("# 标题\n" if f == "source.md" else "x\n",
                               encoding="utf-8")

    def run_progress(self):
        out = self.root / "进度.md"
        r = subprocess.run([sys.executable, str(PROGRESS_PY), str(self.root),
                            "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return out.read_text(encoding="utf-8"), r.stdout

    def rows(self, text):
        """{序号: bvid}"""
        out = {}
        for line in text.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and re.fullmatch(r"\d+", cells[0] or ""):
                m = re.search(r"(BV[0-9A-Za-z]+)", cells[1])
                if m:
                    out[int(cells[0])] = m.group(1)
        return out

    # ---- 1. 拆篇目录不单独成行 -------------------------------------
    def test_split_dir_does_not_add_row(self):
        self.mkdir(BV_C + "-2", ["note.md", "note-2.md"])
        text, log = self.run_progress()
        rows = self.rows(text)
        self.assertEqual(len(rows), 3, "拆篇目录不该多出一集")
        self.assertEqual(rows[3], BV_C, "拆篇不该把自己顶到前面去")
        self.assertIn("拆篇目录已并入主集统计", log)
        # 主行应因拆篇目录里的 note.md 而变成 ✅
        self.assertIn(f"| 3 | [{BV_C}]", text)
        self.assertRegex(text, rf"\| 3 \| \[{BV_C}\][^\n]*\| ✅ \|")

    # ---- 2. 未知目录排末尾，序号不移位 ------------------------------
    def test_unknown_dir_goes_last(self):
        self.mkdir(BV_NEW, ["source.md"])
        text, log = self.run_progress()
        rows = self.rows(text)
        self.assertEqual(len(rows), 4)
        self.assertEqual([rows[i] for i in (1, 2, 3)], [BV_A, BV_B, BV_C])
        self.assertEqual(rows[4], BV_NEW, "未收录目录必须排在末尾")
        self.assertIn("不在 videos.json 里", log)

    # ---- 3. 只有拆篇目录、主目录不存在 -----------------------------
    def test_split_dir_without_base_dir(self):
        (self.root / BV_C).rename(self.root / (BV_C + "-2"))
        text, log = self.run_progress()
        rows = self.rows(text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[3], BV_C)


class SyncGuard(unittest.TestCase):
    def test_markdown_and_xml_rows(self):
        md = ("| 序号 | BV 号 | 名称 | markdown 总结 | html 总结 | html slide |\n"
              "|---|---|---|---|---|---|\n"
              f"| 1 | [{BV_A}](https://www.bilibili.com/video/{BV_A}) | 一 | ✅ | ❌ | ❌ |\n")
        xml = (f'<TableRow><TableCell><Paragraph>1</Paragraph></TableCell>'
               f'<TableCell><Paragraph>{BV_A}</Paragraph></TableCell>'
               '<TableCell><Paragraph>一</Paragraph></TableCell>'
               '<TableCell><Paragraph>✅</Paragraph></TableCell>'
               '<TableCell><Paragraph>✅</Paragraph></TableCell>'
               '<TableCell><Paragraph>✅</Paragraph></TableCell></TableRow>')
        want = {BV_A: {"md": True, "html": False, "slide": False}}
        self.assertEqual(sp.parse_rows(md), want)
        self.assertEqual(sp.parse_rows(xml),
                         {BV_A: {"md": True, "html": True, "slide": True}})

    def test_duplicate_rows_do_not_fake_regress(self):
        """线上有重复行（幻影集）时，逐集比对不该报倒退"""
        local = {BV_A: {"md": True, "html": True, "slide": True}}
        remote = {BV_A: {"md": True, "html": True, "slide": True},
                  BV_B: {"md": True, "html": True, "slide": True}}
        self.assertEqual(sp.find_regress(local, remote), {})

    def test_real_regress_detected(self):
        local = {BV_A: {"md": True, "html": False, "slide": False}}
        remote = {BV_A: {"md": True, "html": True, "slide": True}}
        self.assertEqual(sp.find_regress(local, remote),
                         {BV_A: ["html", "slide"]})

    def test_local_ahead_is_not_regress(self):
        local = {BV_A: {"md": True, "html": True, "slide": True}}
        remote = {BV_A: {"md": True, "html": False, "slide": False}}
        self.assertEqual(sp.find_regress(local, remote), {})


if __name__ == "__main__":
    unittest.main()
