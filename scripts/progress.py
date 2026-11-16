#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress.py — 扫描项目目录，生成/更新进度表（markdown）

用法:
  python3 progress.py <项目目录> [--videos videos.json] [--out 进度.md]

目录约定（每个视频一个文件夹，以 BV 号命名）：
  <项目目录>/BV1xxxxxxxxx/{source.md, note.md, note.html, deck.html}
进度表按 videos.json 的时间顺序（最早→最新）列出全部视频。
"""
import json, pathlib, argparse

MARK = {"y": "✅", "n": "❌"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--videos", default=None)
    ap.add_argument("--out", default="进度.md")
    a = ap.parse_args()

    root = pathlib.Path(a.root)
    videos = []
    vj = pathlib.Path(a.videos) if a.videos else root / "videos.json"
    if vj.exists():
        videos = json.loads(vj.read_text(encoding="utf-8"))
    bvs = {v["bvid"]: v for v in videos}

    # 目录里出现过但 json 里没有的，也补上
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name.startswith("BV") and d.name not in bvs:
            t = ""
            f = d / "source.md"
            if f.exists():
                first = f.read_text(encoding="utf-8").splitlines()
                t = first[0].lstrip("# ").strip() if first else ""
            videos.append({"bvid": d.name, "title": t, "date": "", "duration": ""})
            bvs[d.name] = videos[-1]

    videos.sort(key=lambda v: (v.get("created") or 0, v.get("date") or ""))

    rows, done = [], {"md": 0, "html": 0, "deck": 0, "src": 0}
    for idx, v in enumerate(videos, 1):
        bv, d = v["bvid"], root / v["bvid"]
        has = {k: (d / f).exists() for k, f in
               (("src", "source.md"), ("md", "note.md"),
                ("html", "note.html"), ("deck", "deck.html"))}
        for k in done:
            done[k] += 1 if has[k] else 0
        rows.append(
            f"| {idx} | [{bv}](https://www.bilibili.com/video/{bv}) | {v['title']} | "
            f"{MARK['y' if has['md'] else 'n']} | {MARK['y' if has['html'] else 'n']} | "
            f"{MARK['y' if has['deck'] else 'n']} |")

    total = len(videos)
    head = [
        f"# {root.name} · 扒片进度",
        "",
        f"共 {total} 集｜字幕底本 {done['src']}/{total}｜"
        f"md 总结 {done['md']}/{total}｜html {done['html']}/{total}｜slide {done['deck']}/{total}",
        "",
        "| 序号 | BV 号 | 视频名称 | markdown 总结 | html 总结 | html slide |",
        "|---|---|---|---|---|---|",
    ]
    out = root / a.out
    out.write_text("\n".join(head + rows) + "\n", encoding="utf-8")
    print(f"ok -> {out}  ({total} 行)")


if __name__ == "__main__":
    main()
