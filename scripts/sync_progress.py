#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_progress.py — 生成进度表并安全同步到资料库（带防倒退检查）

用法:
  python3 sync_progress.py <项目根> --space-id <spaceId> --doc-id <进度表文档id> \
      [--videos videos.json] [--out 进度.md] [--dry-run] [--force]

它做三件事：
  1) 调 progress.py 生成表格（带生成时间戳）
  2) 读资料库现有那份，解析出各列完成数
  3) 只有「本地不落后于线上」才覆盖；否则中止并打印差异（--force 可强制）

这样即使两个会话同时写，也不会出现「旧快照盖掉新数据」。
"""
import argparse, json, pathlib, re, subprocess, sys, time, datetime

HERE = pathlib.Path(__file__).resolve().parent
LIB = ("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/"
       "resources/plugins/workbuddy-builtin/skills/library")


def gen(root, videos, out):
    subprocess.run([sys.executable, str(HERE / "progress.py"), str(root),
                    "--videos", str(videos), "--out", str(out)], check=True)
    return pathlib.Path(out) if pathlib.Path(out).is_absolute() else pathlib.Path(root) / out


def parse_counts(text):
    """从进度表文本里取出 (底本, md, html, slide) 的完成数"""
    m = re.search(r"字幕底本\s*(\d+)/(\d+).*?md 总结\s*(\d+)/(\d+).*?html\s*(\d+)/(\d+).*?slide\s*(\d+)/(\d+)", text, re.S)
    if not m:
        return None
    g = list(map(int, m.groups()))
    return {"src": g[0], "md": g[2], "html": g[4], "slide": g[6], "total": g[1]}


def remote_text(doc_id):
    r = subprocess.run([sys.executable, f"{LIB}/doc/get_doc_reviews.py",
                        "--page-id", doc_id], capture_output=True, text=True).stdout
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--space-id", required=True)
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--videos", default="videos.json")
    ap.add_argument("--out", default="进度.md")
    ap.add_argument("--title", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    root = pathlib.Path(a.root).expanduser().resolve()
    vids = root / a.videos if not pathlib.Path(a.videos).is_absolute() else pathlib.Path(a.videos)
    local = gen(root, vids, a.out)
    text = local.read_text(encoding="utf-8")
    lc = parse_counts(text)
    if not lc:
        sys.exit("生成的表格里找不到汇总行，检查 progress.py 输出")

    rt = remote_text(a.doc_id)
    rc = parse_counts(rt)

    print(f"本地: 底本 {lc['src']} / md {lc['md']} / html {lc['html']} / slide {lc['slide']}")
    if rc:
        print(f"线上: 底本 {rc['src']} / md {rc['md']} / html {rc['html']} / slide {rc['slide']}")
    else:
        print("线上: 读不到汇总行（首次创建或格式异常），按覆盖处理")

    if rc and not a.force:
        regress = [k for k in ("src", "md", "html", "slide") if lc[k] < rc[k]]
        if regress:
            print(f"✗ 中止：本地在 {', '.join(regress)} 上落后于线上，覆盖会造成数据倒退。")
            print("  可能原因：你在错误的目录跑、或另一个会话刚写过更新的数据。")
            print("  确认无误后可加 --force 强制覆盖。")
            sys.exit(2)

    if a.dry_run:
        print("dry-run，不写库")
        return

    # 在表格前加生成时间，方便判断新旧
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    text = text.replace("\n\n共 ", f"\n\n_生成于 {stamp}_\n\n共 ", 1)
    local.write_text(text, encoding="utf-8")

    title = a.title or f"{root.name} · 扒视频进度"
    r = subprocess.run([sys.executable, f"{LIB}/doc/create_doc.py", "--title", title,
                        "--node-block-id", a.doc_id, "--space-id", a.space_id,
                        "--content-file", str(local), "--confirm-overwrite"],
                       capture_output=True, text=True).stdout
    if "KS_DOC_CREATE" not in r:
        sys.exit(f"覆盖失败: {r[:200]}")
    print(f"✓ 已同步（{stamp}） -> https://www.workbuddy.cn/space/d/{a.doc_id}")


if __name__ == "__main__":
    main()
