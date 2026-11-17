#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress.py — 扫描项目目录，生成/更新进度表（markdown）

用法:
  python3 progress.py <项目目录> [--videos videos.json] [--out 进度.md]

目录约定（每个视频一个文件夹，以 BV 号命名）：
  <项目目录>/BV1xxxxxxxxx/{source.md, note.md, note.html, deck.html}
进度表按 videos.json 的时间顺序（最早→最新）列出全部视频。

拆篇（长视频写两篇笔记）请把第二篇放在**同一个目录**里，命名 note-2.md /
note-2.html / deck-2.html。**不要**另建 `BV1xxx-2` 目录：那会被当成一集
新视频、且因为没有发布时间而被排到表格第 1 位，导致全表序号整体 +1。
即便如此建了，本脚本也会把 `BV1xxx-N` 视为同一集（不单独成行），
并把它的文件计入主目录那一行。
"""
import json, pathlib, re, argparse

MARK = {"y": "✅", "n": "❌"}
SPACE_DOC = "https://www.workbuddy.cn/space/d/"
SPLIT_RE = re.compile(r"^(BV[0-9A-Za-z]+)-(\d+)$")   # 拆篇目录 BV1xxx-2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--videos", default=None)
    ap.add_argument("--out", default="进度.md")
    a = ap.parse_args()

    root = pathlib.Path(a.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"目录不存在: {root}")
    if not (root / "videos.json").exists() and not any(root.glob("BV*/note.md")):
        raise SystemExit(f"{root} 看起来不是项目根目录（找不到 videos.json 或 BV*/note.md）")
    title = root.name or "扒片进度"
    videos = []
    vj = pathlib.Path(a.videos) if a.videos else root / "videos.json"
    if vj.exists():
        videos = json.loads(vj.read_text(encoding="utf-8"))
    bvs = {v["bvid"]: v for v in videos}

    # 可选的 folders.json（{bvid: {id, seq, title}}）：有它就把「视频名称」列做成
    # 指向资料库该集文件夹的超链接，表格从「对账用」变成「浏览用」。
    folders = {}
    fj = root / "folders.json"
    if fj.exists():
        try:
            folders = json.loads(fj.read_text(encoding="utf-8"))
        except Exception:
            print(f"提示：{fj.name} 解析失败，标题列按纯文本生成")

    # 目录里出现过但 json 里没有的，也补上
    # 两种特例：
    #   BV1xxx-2（拆篇目录）→ 并入主目录那一行，不单独成行
    #   其余未知目录         → 排到表格末尾，绝不打乱已有序号
    split_dirs, unknown = {}, []
    for d in sorted(root.iterdir()):
        if not (d.is_dir() and d.name.startswith("BV")):
            continue
        name = d.name
        if name in bvs:
            continue
        m = SPLIT_RE.match(name)
        if m:
            split_dirs.setdefault(m.group(1), []).append(name)
            continue
        unknown.append(d)

    for d in unknown:
        t = ""
        f = d / "source.md"
        if f.exists():
            first = f.read_text(encoding="utf-8").splitlines()
            t = first[0].lstrip("# ").strip() if first else ""
        videos.append({"bvid": d.name, "title": t, "date": "", "duration": "",
                       "_local": True})
        bvs[d.name] = videos[-1]
    if unknown:
        print(f"提示：{len(unknown)} 个目录不在 videos.json 里，已排在表格末尾："
              + "、".join(d.name for d in unknown))
    if split_dirs:
        print("提示：拆篇目录已并入主集统计："
              + "、".join(f"{k}({'+'.join(v)})" for k, v in split_dirs.items()))

    # 未收录目录没有发布时间，排在最后；json 里的照旧按发布时间
    videos.sort(key=lambda v: (v.get("created") or (float("inf") if v.get("_local") else 0),
                               v.get("date") or ""))

    rows, done = [], {"md": 0, "html": 0, "deck": 0, "src": 0}
    for idx, v in enumerate(videos, 1):
        bv, d = v["bvid"], root / v["bvid"]
        cands = [d] + [root / x for x in split_dirs.get(bv, [])]
        has = {k: any((c / f).exists() for c in cands) for k, f in
               (("src", "source.md"), ("md", "note.md"),
                ("html", "note.html"), ("deck", "deck.html"))}
        for k in done:
            done[k] += 1 if has[k] else 0
        f = folders.get(bv) or {}
        name = v["title"]
        name_cell = f"[{name}]({SPACE_DOC}{f['id']})" if f.get("id") else name
        rows.append(
            f"| {idx} | [{bv}](https://www.bilibili.com/video/{bv}) | {name_cell} | "
            f"{MARK['y' if has['md'] else 'n']} | {MARK['y' if has['html'] else 'n']} | "
            f"{MARK['y' if has['deck'] else 'n']} |")

    total = len(videos)
    head = [
        f"# {title} · 扒片进度",
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
