#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_note_html.py — 把固定体例的 markdown 转成排版好的静态 HTML

用法: python3 md2html.py <input.md> <output.html>

版式沿用 偏印与正印-年月印旺.html：左侧固定目录 + 宋体标题 + 表格 / 提示块。
"""
import sys, re, html, pathlib

TPL = pathlib.Path(__file__).resolve().parent.parent / "templates"


def load_style():
    return (TPL / "note.css").read_text(encoding="utf-8")


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    return t


def parse(md):
    lines, blocks, i = md.split("\n"), [], 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1; continue
        if re.fullmatch(r"-{3,}", s):
            blocks.append(("hr", None)); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            blocks.append((f"h{len(m.group(1))}", m.group(2).strip())); i += 1; continue
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            blocks.append(("quote", buf)); continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(set(c) <= set("-: ") and c for c in r)]
            blocks.append(("table", rows)); continue
        if re.match(r"^[-*]\s+", s):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                t = re.sub(r"^[-*]\s+", "", lines[i].strip()); i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    t += lines[i].strip(); i += 1
                items.append(t)
            blocks.append(("ul", items)); continue
        if re.match(r"^\d+\.\s+", s):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                t = re.sub(r"^\d+\.\s+", "", lines[i].strip()); i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    t += lines[i].strip(); i += 1
                items.append(t)
            blocks.append(("ol", items)); continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(-{3,}$|#{1,4}\s|>|\||[-*]\s|\d+\.\s)", lines[i].strip()):
            buf.append(lines[i].strip()); i += 1
        blocks.append(("p", "".join(buf)))
    return blocks


def split_sections(blocks):
    """返回 (h1, meta_lines, [ (num, title, [blocks]) ])"""
    h1, meta, secs = "", [], []
    i = 0
    while i < len(blocks) and blocks[i][0] != "h1":
        i += 1
    if i < len(blocks):
        h1 = blocks[i][1]; i += 1
    if i < len(blocks) and blocks[i][0] == "quote":
        meta = blocks[i][1]; i += 1
    cur = None
    for kind, payload in blocks[i:]:
        if kind == "h2":
            num, txt = "", payload
            m = re.match(r"^([一二三四五六七八九十百]+、)\s*(.*)$", payload)
            if m:
                num, txt = m.group(1), m.group(2)
            cur = (num, txt, [])
            secs.append(cur)
        elif cur is not None:
            cur[2].append((kind, payload))
    return h1, meta, secs


def render_body_blocks(items):
    out = []
    for kind, payload in items:
        if kind == "p":
            out.append(f"<p>{inline(payload)}</p>")
        elif kind == "ul":
            cls = ' class="tight"' if len(payload) > 4 else ""
            out.append(f"<ul{cls}>" + "".join(f"<li>{inline(x)}</li>" for x in payload) + "</ul>")
        elif kind == "ol":
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in payload) + "</ol>")
        elif kind == "h3":
            out.append(f"<h3>{inline(payload)}</h3>")
        elif kind == "table":
            head, rows = payload[0], payload[1:]
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += [f"<th>{inline(c)}</th>" for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
        elif kind == "hr":
            out.append('<hr class="sep">')
        elif kind == "quote":
            out.append("<blockquote>" + "".join(f"<p>{inline(x)}</p>" for x in payload) + "</blockquote>")
    return "".join(out)


def render(md, title):
    h1, meta, secs = split_sections(parse(md))

    chips, eyebrow = [], ""
    for m in meta:
        mm = re.match(r"\*\*(.+?)\*\*[：:]\s*(.*)", m)
        if mm:
            k, v = mm.group(1), mm.group(2)
            if not eyebrow and "来源" in k:
                eyebrow = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", v)
            chips.append((k, v))
        elif not eyebrow:
            eyebrow = m

    # 「一句话」做成导语卡
    lede, secs2 = "", []
    for num, txt, items in secs:
        if txt in ("一句话", "一句话结论") and not lede:
            lede = "".join(inline(x[1]) for x in items if x[0] == "p")
        else:
            secs2.append((num, txt, items))

    toc, body = [], []
    for idx, (num, txt, items) in enumerate(secs2, 1):
        sid = f"s{idx}"
        toc.append((sid, num + txt))
        body.append(f'<section id="{sid}"><h2>'
                    + (f'<span class="num">{html.escape(num)}</span>' if num else "")
                    + f"{inline(txt)}</h2>{render_body_blocks(items)}</section>")

    toc_html = ('<nav class="toc"><div class="toc-title">目录</div>'
                + "".join(f'<a href="#{sid}">{html.escape(t)}</a>' for sid, t in toc)
                + "</nav>")
    lede_html = f'<div class="lede">{lede}</div>' if lede else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{load_style()}
  .eyebrow{{font-size:12px;letter-spacing:.14em;color:var(--accent);margin-bottom:14px}}
  .meta span{{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:3px 11px}}
  .lede{{margin:4px 0 40px;padding:22px 26px;background:var(--card);border:1px solid var(--line);
    border-left:4px solid var(--accent);border-radius:var(--radius);font-size:16.5px;line-height:1.95;color:var(--ink-2)}}
  h3{{font-size:17px;margin:28px 0 10px;color:var(--ink)}}
  hr.sep{{border:none;border-top:1px solid var(--line);margin:34px 0}}
  code{{background:#f4f1ea;border-radius:4px;padding:1px 5px;font-size:.9em}}
  blockquote{{margin:16px 0;padding:12px 18px;border-left:3px solid var(--line);
    background:#fdfcfa;border-radius:0 8px 8px 0;color:var(--muted)}}
  blockquote p{{margin:4px 0}}
</style>
</head>
<body>
<div class="wrap">
  {toc_html}
  <main>
    <header class="doc-head">
      {f'<div class="eyebrow">{inline(eyebrow)}</div>' if eyebrow else ''}
      <h1>{inline(h1 or title)}</h1>
      {('<div class="meta">' + "".join(f"<span>{html.escape(k)}：{inline(v)}</span>" for k, v in chips) + '</div>') if chips else ''}
    </header>
    {lede_html}
    {''.join(body)}
    <footer>视频笔记 · 由字幕整理，口误与形近字已按上下文校正</footer>
  </main>
</div>
</body>
</html>
"""


def main():
    src, dst = sys.argv[1], sys.argv[2]
    md = pathlib.Path(src).read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+)$", md, re.M)
    title = m.group(1).strip() if m else pathlib.Path(src).stem
    pathlib.Path(dst).write_text(render(md, title), encoding="utf-8")
    print("ok ->", dst)


if __name__ == "__main__":
    main()
