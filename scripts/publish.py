#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish.py — 把一集的三件套归档进资料库：建标题文件夹 + 上传 md 文档

HTML 无法由脚本上传（需要宿主工具），本脚本最后会把两个上传目标打印出来。

用法:
  python3 publish.py --bv BV1xxx --dir $ROOT/BV1xxx \
      --space-id <spaceId> --parent-id <专题文件夹id> [--dry-run]
"""
import argparse, json, pathlib, re, subprocess, sys

LIB = ("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/"
       "resources/plugins/workbuddy-builtin/skills/library")


def api(name, **kw):
    cmd = ["python3", f"{LIB}/space_api.py", name]
    for k, v in kw.items():
        cmd += [f"--{k.replace('_','-')}", str(v)]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    try:
        return json.loads(out)
    except Exception:
        return {"raw": out}


def safe_title(t):
    return t.replace("/", "／").replace(":", "：")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bv", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--space-id", required=True)
    ap.add_argument("--parent-id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = pathlib.Path(a.dir)
    note = d / "note.md"
    if not note.exists():
        sys.exit("缺 note.md，先生成总结")
    title = re.search(r"^#\s+(.+)$", note.read_text(encoding="utf-8"), re.M).group(1).strip()
    folder_title = safe_title(title)

    # 1) 找同名文件夹，没有就建
    kids = api("space.workspace.list-nodes", space_id=a.space_id,
               parent_node_id=a.parent_id, limit=100)
    folder_id = None
    for n in kids.get("data", {}).get("nodes", []):
        if n["kind"] == "folder" and n["title"] == folder_title:
            folder_id = n["id"]
            break
    print(f"folder: {folder_title} -> {folder_id or '（将新建）'}")

    if a.dry_run:
        print("dry-run，不写库")
        return

    if not folder_id:
        r = subprocess.run(["python3", f"{LIB}/manage/create_folder.py",
                            "--title", folder_title, "--space-id", a.space_id,
                            "--parent-id", a.parent_id],
                           capture_output=True, text=True).stdout
        m = re.search(r"KS_FOLDER_CREATE\t(\S+)", r)
        if not m:
            sys.exit(f"建文件夹失败: {r[:200]}")
        folder_id = m.group(1)

    # 2) md → 文档
    r = subprocess.run(["python3", f"{LIB}/doc/create_doc.py", "--title", title,
                        "--space-id", a.space_id, "--parent-id", folder_id,
                        "--content-file", str(note)],
                       capture_output=True, text=True).stdout
    m = re.search(r"KS_DOC_CREATE\t(\S+)", r)
    print("doc:", m.group(1) if m else f"失败 {r[:160]}")

    # 3) 剩下两个文件交给宿主工具
    print("\n下一步（用 LibraryUpload 工具，parent_id 填上面的 folder id）：")
    print(f"  {d/'note.html'}  ->  {safe_title(title)}-笔记页.html")
    print(f"  {d/'deck.html'}  ->  {safe_title(title)}-幻灯片.html")
    print(f"\nfolder_id={folder_id}")


if __name__ == "__main__":
    main()
