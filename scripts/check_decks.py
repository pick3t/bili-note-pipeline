#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_decks.py —— 全量体检幻灯片，替代「抽三页肉眼看」。

为什么要有这个：2026-11 之前 build_deck.py 的 `.bullet-list li` 用
`display:grid; grid-template-columns:1.4em minmax(0,1fr)`，要点若以 `**加粗**`
开头，`<b>` 占第 1 行、正文被丢进只有 1.4em 宽的第 2 行，于是中文一个字一行竖下来，
页面被撑到远超 100vh（第 5 集第 6 页就是这样）。肉眼抽查很容易漏，必须机械查。

查五类问题（每一条都能定位到页）：
  1. 竖排        `.bullet-list li` 的 display 还是 grid（老模板特征，最狠的一种）
  2. 溢出        正文区 scrollHeight/scrollWidth 超出可视区
  3. 窄栏        正文区里某元素宽度 < 3 个字宽，却装着一行以上的字
  4. 空续页      标题带「（续）」的页，正文条目 ≤1

（刻意不查「压页脚」：正文盒子本来就顶到页脚上沿，几何上必然相交，
 是个假阳性制造机；真压到页脚一定是先溢出，第 2 条会报。）

用法：
  python3 scripts/check_decks.py <项目根> [--session deckchk] [--only BV1xxx]
  python3 scripts/check_decks.py <项目根> --static   # 只做静态查（不启浏览器）

退出码：0 全通过；1 有违规；2 环境问题（agent-browser 不可用）。
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

JS = r"""(()=>{
const bad=[];
const wOf=s=>s;
document.querySelectorAll('.slide').forEach((s,i)=>{
  const body=s.querySelector('.slide-body')||s;
  const t=(s.querySelector('h2')||{}).textContent||'';
  const rec={p:i+1,title:t.trim().slice(0,18),issues:[]};
  // 1) 竖排：老模板的 grid li
  let gridLi=0;
  body.querySelectorAll('.bullet-list li').forEach(li=>{
    if(getComputedStyle(li).display==='grid') gridLi++;
  });
  if(gridLi) rec.issues.push('grid-li:'+gridLi);
  // 2) 溢出
  if(body.scrollHeight>body.clientHeight+2||body.scrollWidth>body.clientWidth+2)
    rec.issues.push('overflow:'+(body.scrollHeight-body.clientHeight)+'px');
  // 3) 窄栏（排除装饰性 label）
  let narrow=null;
  body.querySelectorAll('li,p,td,h2,div').forEach(el=>{
    if(el.children.length>1) return;
    const t2=(el.textContent||'').trim();
    if(t2.length<8) return;
    const fs=parseFloat(getComputedStyle(el).fontSize)||16;
    const w=el.getBoundingClientRect().width;
    if(w>0&&w<fs*3) narrow={w:Math.round(w),txt:t2.slice(0,10)};
  });
  if(narrow) rec.issues.push('narrow:'+narrow.w+'px');
  // 4) 空续页
  if(t.indexOf('（续）')>=0){
    const els=[...body.querySelectorAll('li,tr,p')];
    const chars=els.reduce((a,e)=>a+(e.textContent||'').trim().length,0);
    if(els.length<=1 && chars<100) rec.issues.push('thin-cont:'+chars+'字');
  }
  if(rec.issues.length) bad.push(rec);
});
return JSON.stringify({slides:document.querySelectorAll('.slide').length,bad});
})()"""

LEGACY = "grid-template-columns:1.4em"


def decks(root: pathlib.Path, only=None):
    pats = ["*/deck.html", "*/deck-2.html", "*/幻灯片.html", "*/幻灯片-2.html"]
    out = []
    for p in pats:
        for f in sorted(root.glob(p)):
            if only and only not in str(f):
                continue
            out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--session", default="deckchk")
    ap.add_argument("--only", default=None)
    ap.add_argument("--static", action="store_true")
    a = ap.parse_args()
    root = pathlib.Path(a.root).expanduser().resolve()
    files = decks(root, a.only)
    if not files:
        sys.exit(f"{root} 下没找到 deck.html")

    problems = 0
    legacy = [f for f in files if LEGACY in f.read_text(encoding="utf-8", errors="ignore")]
    if legacy:
        print(f"✗ {len(legacy)} 个 deck 仍是老模板（li 用 grid，会竖排）：")
        for f in legacy[:10]:
            print("   -", f.relative_to(root))
        problems += len(legacy)
    print(f"静态：{len(files)} 个 deck，老模板 {len(legacy)} 个")

    if a.static:
        return 1 if problems else 0

    try:
        subprocess.run(["agent-browser", "--session", a.session, "eval", "1"],
                       capture_output=True, timeout=60, check=False)
    except Exception:
        print("agent-browser 不可用，跳过渲染检查")
        return 2

    for f in files:
        subprocess.run(["agent-browser", "--session", a.session, "open",
                        f"file://{f}"], capture_output=True, timeout=120)
        time.sleep(0.9)   # 等自动缩排跑完再量，否则量到的是缩放前的尺寸
        r = subprocess.run(["agent-browser", "--session", a.session, "eval", JS],
                           capture_output=True, text=True, timeout=120)
        raw = r.stdout.strip()
        try:
            payload = json.loads(json.loads(raw))      # 双层 JSON 字符串
        except Exception:
            print(f"? {f.relative_to(root)} 解析失败: {raw[:80]}")
            problems += 1
            continue
        bad = payload.get("bad", [])
        if bad:
            problems += len(bad)
            print(f"✗ {f.relative_to(root)}（{payload['slides']} 页）")
            for b in bad:
                print(f"    p{b['p']} 「{b['title']}」 {' '.join(b['issues'])}")
    print(f"\n{'全部通过' if not problems else f'共 {problems} 处问题'}｜检查 {len(files)} 个 deck")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
