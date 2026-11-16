#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_deck.py 的版式回归测试（纯标准库 unittest，无外部依赖）

跑法： python3 -m unittest discover -s tests -v

背景：`.bullet-list li` 曾用 `display:grid; grid-template-columns:1.2em 1fr`，
要点里的 `<b>`（markdown `**加粗**`）会变成匿名 grid item 被挤进 1.2em 宽的那列，
逐字竖排并把后续要点顶出页脚。2026-11 改成块流 + 绝对定位破折号。
这两条断言防止改回去。
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
BUILD = SCRIPTS / "build_deck.py"

SAMPLE = """# 测试：要点里的加粗

> **来源**：B站 @测试频道 · BVtest · 1:00
> **字幕**：官方 AI 中文轨，10 段
> **性质**：测试

## 一句话

验证一条规则。

## 一、带加粗的要点

- 这一条正常
- 这一条中间有**加粗片段**，不能竖排
- 这一条也正常

## 二、存疑与空白

- 无
"""


def build_deck(md_text):
    with tempfile.TemporaryDirectory() as td:
        md = pathlib.Path(td) / "note.md"
        out = pathlib.Path(td) / "deck.html"
        md.write_text(md_text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(BUILD), str(md), str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(f"build_deck failed: {r.stderr}")
        return out.read_text(encoding="utf-8")


class TestBulletLayout(unittest.TestCase):
    def setUp(self):
        self.html = build_deck(SAMPLE)

    def test_bullet_li_is_block_flow(self):
        """li 必须是块流：grid 会让行内标签变成独立列，导致竖排。"""
        rules = re.findall(r"\.bullet-list li\s*\{([^}]*)\}", self.html)
        self.assertTrue(rules, "没找到 .bullet-list li 规则")
        merged = "\n".join(rules)
        self.assertIn("display: block", merged,
                      "li 应为 display:block，grid 会让要点内的 <b> 竖排")
        self.assertNotIn("grid-template-columns", merged,
                         "li 上不应再出现 grid-template-columns")
        self.assertRegex(merged, r"padding-left:\s*[\d.]+em",
                         "块流方案要靠 padding-left 留出破折号的位置")

    def test_bullet_dash_is_absolute(self):
        """破折号走绝对定位，才能做出悬挂缩进。"""
        rules = re.findall(r"\.bullet-list li::before\s*\{([^}]*)\}", self.html)
        self.assertTrue(rules, "没找到 .bullet-list li::before 规则")
        merged = "\n".join(rules)
        self.assertIn("position: absolute", merged)
        self.assertIn("left: 0", merged)

    def test_bold_in_bullet_becomes_b_tag(self):
        """`**x**` 在要点里要转成 <b>，且与前后文字同一行流（不是独立块）。"""
        self.assertIn('<li>这一条中间有<b>加粗片段</b>，不能竖排</li>', self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
