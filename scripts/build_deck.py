#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_deck.py — 把 markdown 笔记自动排成 monochrome 版 HTML 幻灯片

用法: python3 md2slide.py <input.md> <output.html> [--eyebrow "第几篇"]

规则（按内容形状选版式）：
  封面      ← H1 + 来源/字幕/性质
  一句话    ← statement
  纯要点段  ← list（超过 6 条自动拆两页）
  段落+要点 ← list，段落作左栏导语（>120 字则先出「引子」页）
  段落+表格 ← table，段落作表格导语
  多段落    ← dense（双栏）
  三列表格  ← compare（左/右面板）
  结尾      ← end
"""
import os, sys, re, html, pathlib

CHANNEL = os.environ.get("NOTE_CHANNEL", "视频笔记")
THEME = pathlib.Path(__file__).resolve().parent.parent / "templates/deck_theme.html"
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_note_html import parse, split_sections  # noqa: E402


def esc(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", t)
    return t


def strip_links(t):
    return re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", t)


def chrome(sec, page):
    return (f'\n        <header class="slide-chrome">'
            f'<span class="label muted">{esc(sec)}</span>'
            f'<span class="label muted">{page}</span></header>')


def foot(page):
    return (f'\n        <footer class="slide-foot">'
            f'<span class="label muted">{CHANNEL}</span>'
            f'<span class="label muted">{page}</span></footer>')


def sidebar(a="笔记", b="2026"):
    return (f'\n        <div class="slide-sidebar" data-anim="fade-in" data-delay="0">'
            f'<span class="sidebar-label">{esc(a)}</span>'
            f'<span class="sidebar-label">{esc(b)}</span></div>')


def short(t, n=18):
    return t if len(t) <= n else t[: n - 1] + "…"


def cover(title, chips, page):
    lines = title.split("：")
    main = lines[0]
    sub = lines[1] if len(lines) > 1 else ""
    lead = " · ".join(v for k, v in chips if k in ("字幕", "性质")) or "视频逐帧字幕整理"
    h1 = f"{esc(main)}" + (f"<br />{esc(sub)}" if sub else "")
    src = next((v for k, v in chips if "来源" in k), "")
    return f"""
      <section class="slide slide--cover light">{sidebar("八字笔记", "视频笔记")}
        <div style="position:absolute;top:var(--pad-y);right:var(--pad-x);text-align:right;"
             data-anim="fade-in" data-delay="1">
          <span class="label muted">{esc(strip_links(src))}</span>
        </div>
        <div class="cover-body">
          <h1 class="display" data-anim="fade-up" data-delay="2">{h1}</h1>
          <div class="rule" data-anim="reveal-right" data-delay="3" style="margin:1.5vh 0"></div>
          <p class="lead muted" data-anim="fade-up" data-delay="4" style="max-width:56%">{esc(lead)}</p>
        </div>
        <div class="cover-meta" data-anim="fade-in" data-delay="5">
          <span class="label muted">{esc(CHANNEL)} · 视频笔记</span>
          <span class="label muted">{esc(strip_links(src).split("·")[-1].strip() if src else "")}</span>
        </div>
      </section>"""


def statement(sec, body, page):
    return f"""
      <section class="slide slide--statement light">{sidebar(short(sec, 8))}{chrome(sec, page)}
        <div class="statement-body">
          <p class="kicker" data-anim="fade-in" data-delay="1">{esc(sec)}</p>
          <h2 class="h1" data-anim="fade-up" data-delay="2" style="max-width:80%">{body}</h2>
        </div>{foot(page)}
      </section>"""


def title_cls(sec):
    """标题较长时收一号字，避免在左栏折成两行"""
    return " long" if len(sec) > 8 else ""


def list_slide(sec, items, page, kicker=None, lead=None):
    lis = "".join(f"<li>{esc(x)}</li>" for x in items)
    lead_html = f'<p class="list-lead" data-anim="fade-up" data-delay="2">{esc(lead)}</p>' if lead else ""
    return f"""
      <section class="slide slide--list light">{sidebar(short(sec, 8))}{chrome(sec, page)}
        <div class="slide-body">
          <div class="list-head">
            <p class="kicker" data-anim="fade-in" data-delay="1">{esc(kicker or "要点")}</p>
            <h2 class="h2{title_cls(sec)}" data-anim="fade-up" data-delay="2">{esc(sec)}</h2>
            {lead_html}
          </div>
          <ul class="bullet-list" data-anim="fade-up" data-delay="3">{lis}</ul>
        </div>{foot(page)}
      </section>"""


def dense(sec, paras, page):
    is_short = sum(len(x) for x in paras) < 320
    half = (len(paras) + 1) // 2
    cols = []
    for chunk in (paras[:half], paras[half:]):
        inner = "".join(f"<p>{esc(p)}</p>" for p in chunk)
        cols.append(f'<div class="dense-col">{inner}</div>')
    return f"""
      <section class="slide slide--dense light{' short' if is_short else ''}">{sidebar(short(sec, 8))}{chrome(sec, page)}
        <h2 class="dense-hl" data-anim="fade-up" data-delay="1">{esc(sec)}</h2>
        <div class="slide-body">
          <div class="dense-cols" data-anim="fade-up" data-delay="2">{''.join(cols)}</div>
        </div>{foot(page)}
      </section>"""


def table_slide(sec, rows, page, lead=None):
    """表格 → 细线表格页（设计系统里表格是无圆角 + 1px 细线）"""
    head, body = rows[0], rows[1:7]
    th = "".join(f"<th>{esc(c)}</th>" for c in head)
    trs = []
    for r in body:
        tds = "".join(f"<td>{esc(short(c, 30))}</td>" for c in r)
        trs.append(f"<tr>{tds}</tr>")
    lead_html = f'<p class="tbl-lead" data-anim="fade-up" data-delay="1">{esc(lead)}</p>' if lead else ""
    return f"""
      <section class="slide slide--dense light">{sidebar(short(sec, 8))}{chrome(sec, page)}
        <h2 class="dense-hl{title_cls(sec)}" data-anim="fade-up" data-delay="1">{esc(sec)}</h2>
        {lead_html}
        <div class="slide-body">
          <table class="tbl" data-anim="fade-up" data-delay="2">
            <thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody>
          </table>
        </div>{foot(page)}
      </section>"""


def end_slide(title, page):
    return f"""
      <section class="slide slide--end light">{sidebar("视频笔记", "2026")}
        <p class="kicker" data-anim="fade-in" data-delay="1">{esc(CHANNEL)} · 视频笔记</p>
        <div class="rule" data-anim="reveal-right" data-delay="2" style="margin:var(--gap-sm) 0"></div>
        <h2 class="h1" data-anim="fade-up" data-delay="3" style="max-width:68%">{esc(title)}</h2>
        <p class="lead muted" data-anim="fade-up" data-delay="4" style="max-width:46%;margin-top:var(--gap-md)">
          由视频字幕整理 · 口误与形近字已按上下文校正</p>
      </section>"""


def build(md, out):
    theme = THEME.read_text(encoding="utf-8")
    head = theme.split("<body>")[0]
    head = head.replace("</head>", """<style>
      /* 列表列宽下限 + 正常断词（li 本体用块流，见 deck_theme.html） */
      .slide--list .slide-body{grid-template-columns:minmax(0,2fr) minmax(0,3fr)}
      .bullet-list{min-width:0}
      .bullet-list li{word-break:normal;overflow-wrap:anywhere}
      .compare-row{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--pad-x)*0.55);
        border-top:1px solid var(--c-border);padding-top:var(--gap-md)}
      .compare-row .compare-panel{border:none;padding:0}
      .compare-row .compare-panel::before{display:none}
      .tbl{width:100%;border-collapse:collapse;font-size:calc(var(--sz-body)*.99)}
      .tbl th{text-align:left;font-family:var(--f-body);font-size:calc(var(--sz-label)*1.1);
        color:var(--c-fg-3);border-bottom:1px solid var(--c-border);padding:0 1.4vw 1.1vh 0}
      .tbl td{border-bottom:1px solid rgba(26,26,22,.16);padding:1.35vh 1.4vw 1.35vh 0;
        vertical-align:top;color:var(--c-fg);line-height:1.7}
      .tbl td:first-child{color:var(--c-fg-2);white-space:nowrap;width:20%}
      .tbl tbody tr:last-child td{border-bottom:none}
      .slide--dense.short .slide-body{align-items:center}
      .slide--dense.short .dense-col p{font-size:calc(var(--sz-lead)*.92);color:var(--c-fg)}
      /* 节内导语段落：同一节既有段落又有要点/表格时，段落不再被丢弃 */
      .list-lead,.tbl-lead{font-size:calc(var(--sz-body)*.92);line-height:1.75;color:var(--c-fg-2);
        margin:calc(var(--gap-sm)*.7) 0 0;max-width:100%}
      .tbl-lead{margin:0 0 var(--gap-sm);max-width:72%}
      /* 长标题收一号字，避免左栏折成两行 */
      .h2.long,.dense-hl.long{font-size:calc(var(--sz-h2)*.82)}
    </style></head>""")
    script = theme[theme.rindex("<script>"): theme.rindex("</script>") + 9]

    h1, meta, secs = split_sections(parse(md))
    chips = []
    for m in meta:
        mm = re.match(r"\*\*(.+?)\*\*[：:]\s*(.*)", m)
        if mm:
            chips.append((mm.group(1), mm.group(2)))

    global CHANNEL
    for k, v in chips:
        hit = re.search(r"@([^\s·|]+)", v)
        if hit and ("来源" in k or "频道" in k):
            CHANNEL = hit.group(1)
            break

    slides, page = [], 2
    slides.append(cover(h1, chips, "01"))
    last_line = ""
    for num, txt, items in secs:
        if txt.startswith("附"):
            continue
        uis = [x[1] for x in items if x[0] == "ul"]
        ois = [x[1] for x in items if x[0] == "ol"]
        ps = [x[1] for x in items if x[0] == "p"]
        tb = [x[1] for x in items if x[0] == "table"]
        bullets = [b for grp in (uis + ois) for b in grp]
        title = txt

        if tb:
            lead = " ".join(ps) if ps and sum(len(p) for p in ps) <= 120 else None
            if ps and lead is None:                      # 导语太长 → 单独一页，不丢内容
                slides.append(dense(title + "：引子", ps, f"{page:02d}"))
                page += 1
            slides.append(table_slide(title, tb[0], f"{page:02d}", lead=lead))
        elif bullets and (sum(len(b) for b in bullets) / len(bullets) > 30):
            # 要点太长 → 双栏段落，避免挤成竖排
            paras = [f"· {b}" for b in bullets]
            for k in range(0, len(paras), 4):
                slides.append(dense(title if k == 0 else title + "（续）", paras[k:k + 4], f"{page:02d}"))
                page += 1
            continue
        elif bullets and len(bullets) > 6:
            for k in range(0, len(bullets), 6):
                slides.append(list_slide(title if k == 0 else title + "（续）",
                                         bullets[k:k + 6], f"{page:02d}", kicker="要点"))
                page += 1
            continue
        elif bullets:
            lead = " ".join(ps) if ps and sum(len(p) for p in ps) <= 120 else None
            if ps and lead is None:                      # 导语太长 → 单独一页，不丢内容
                slides.append(dense(title + "：引子", ps, f"{page:02d}"))
                page += 1
            slides.append(list_slide(title, bullets, f"{page:02d}", lead=lead))
        elif len(ps) >= 2:
            slides.append(dense(title, ps, f"{page:02d}"))
        elif ps:
            slides.append(statement(title, esc(ps[0]), f"{page:02d}"))
            last_line = ps[0]
        page += 1

    slides.append(end_slide(h1.split("：")[0], f"{page:02d}"))
    doc = head + '<body>\n    <div id="deck">' + "\n".join(slides) + """
    </div>

    <nav id="nav-dots" aria-label="Slide navigation"></nav>
    <div id="slide-counter"></div>

""" + script + "\n  </body>\n</html>\n"
    pathlib.Path(out).write_text(doc, encoding="utf-8")
    print(f"ok -> {out}  slides={doc.count('<section class=\"slide')}")


if __name__ == "__main__":
    build(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"), sys.argv[2])
