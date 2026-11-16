#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bili.py — B 站取数工具箱（列表 / 视频元信息 / 官方字幕），全部经浏览器身份发出

所有请求都通过 agent-browser 在 bilibili 页面上下文里 fetch，
这样带登录态与浏览器指纹，能拿到官方 AI 字幕、绕开大部分风控。

CLI:
  python3 bili.py list <mid> [-o videos.json] [--pages 1-4]
  python3 bili.py meta <bvid>
  python3 bili.py subtitle <bvid> [-o source.md]
"""
import os, sys, json, time, hashlib, urllib.parse, argparse, pathlib, subprocess, re

SESSION = os.environ.get("BILI_BROWSER_SESSION", "bili-dff29cd85209")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MIXIN = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
         33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
         26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
         20, 34, 44, 52]
MIXIN_CACHE = pathlib.Path("/tmp/bili_mixin.txt")


# ── 浏览器执行 ────────────────────────────────────────────────────────────
def ab_eval(js, session=SESSION):
    out = subprocess.run(["agent-browser", "--session", session, "eval", js],
                         capture_output=True, text=True, timeout=120).stdout.strip()
    try:
        return json.loads(out)          # 去掉外层引号
    except Exception:
        return out


def be_fetch(url, session=SESSION):
    """在页面上下文 fetch，返回 (status, text)"""
    js = ("fetch(%s,{credentials:'include'})"
          ".then(r=>r.text().then(t=>JSON.stringify({s:r.status,b:t})))" % json.dumps(url))
    raw = ab_eval(js, session)
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
        return d.get("s"), d.get("b", "")
    except Exception:
        return 0, raw


def ensure_bili_page(session=SESSION):
    url = ab_eval("location.href", session)
    if not isinstance(url, str) or "bilibili.com" not in url:
        subprocess.run(["agent-browser", "--session", session, "open",
                        "https://www.bilibili.com/"], capture_output=True)


# ── WBI 签名 ──────────────────────────────────────────────────────────────
def mixin_key():
    if MIXIN_CACHE.exists():
        return MIXIN_CACHE.read_text().strip()
    import urllib.request
    req = urllib.request.Request("https://api.bilibili.com/x/web-interface/nav",
                                 headers={"User-Agent": UA})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    img = d["data"]["wbi_img"]["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub = d["data"]["wbi_img"]["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    key = "".join((img + sub)[i] for i in MIXIN)[:32]
    MIXIN_CACHE.write_text(key)
    return key


def signed(path, params):
    p = dict(params); p["wts"] = int(time.time())
    q = urllib.parse.urlencode(sorted(p.items()))
    p["w_rid"] = hashlib.md5((q + mixin_key()).encode()).hexdigest()
    return path + "?" + urllib.parse.urlencode(sorted(p.items()))


# ── 列表 ──────────────────────────────────────────────────────────────────
def cmd_list(mid, out, pages):
    ensure_bili_page()
    a, b = pages
    allv = []
    for pn in range(a, b + 1):
        url = signed("https://api.bilibili.com/x/space/wbi/arc/search",
                     {"mid": mid, "ps": 30, "pn": pn, "order": "pubdate",
                      "platform": "web", "web_location": "1550101",
                      "index": 0, "order_avoided": "true"})
        got = None
        for attempt in range(4):
            st, txt = be_fetch(url)
            try:
                d = json.loads(txt)
            except Exception:
                d = {}
            if d.get("code") == 0:
                got = d
                break
            code = d.get("code") or st
            print(f"  pn{pn} attempt{attempt+1}: blocked ({code})")
            if code == -352:
                print("  ↳ 风控，等 20s 再试（可先做别的）")
                time.sleep(20)
            else:
                time.sleep(5)
        if not got:
            print(f"  pn{pn}: 放弃，稍后重跑 --pages {pn}-{pn}")
            continue
        for v in got["data"]["list"]["vlist"]:
            allv.append({"bvid": v["bvid"], "aid": v["aid"], "title": v["title"],
                         "duration": v["length"], "created": v["created"],
                         "date": time.strftime("%Y-%m-%d", time.localtime(v["created"])),
                         "desc": v.get("description", "")})
        total = got["data"]["page"]["count"]
        print(f"  pn{pn}: +{len(got['data']['list']['vlist'])} / {total}")
        time.sleep(4)

    # 合并已有
    p = pathlib.Path(out)
    old = {}
    if p.exists():
        for v in json.loads(p.read_text(encoding="utf-8")):
            old[v["bvid"]] = v
    for v in allv:
        old[v["bvid"]] = v
    merged = sorted(old.values(), key=lambda x: x["created"])
    p.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {len(merged)} videos -> {out}")


# ── 元信息 ────────────────────────────────────────────────────────────────
def cmd_meta(bvid):
    ensure_bili_page()
    st, txt = be_fetch(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    d = json.loads(txt)
    if d.get("code") != 0:
        print(json.dumps({"error": d.get("code"), "msg": d.get("message")}, ensure_ascii=False))
        return None
    v = d["data"]
    return {"bvid": bvid, "title": v["title"], "cid": v["cid"], "aid": v["aid"],
            "duration": v["duration"], "pubdate": v["pubdate"],
            "date": time.strftime("%Y-%m-%d", time.localtime(v["pubdate"])),
            "owner": v["owner"]["name"], "desc": v.get("desc", "")[:300]}


# ── 字幕 ──────────────────────────────────────────────────────────────────
def cmd_subtitle(bvid, out):
    m = cmd_meta(bvid)
    if not m:
        return
    ensure_bili_page()
    url = f"https://api.bilibili.com/x/player/wbi/v2?bvid={bvid}&cid={m['cid']}"
    for attempt in range(3):
        st, txt = be_fetch(url)
        try:
            d = json.loads(txt)
        except Exception:
            d = {}
        if d.get("code") == 0:
            break
        print(f"  player attempt{attempt+1}: {d.get('code') or st}")
        time.sleep(4)
    subs = (((d.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
    if not subs:
        print("  ⚠ 无官方字幕（可能未登录或该视频无 AI 字幕）")
        json.dump({"meta": m, "subtitle": None}, open("/tmp/last_sub_meta.json", "w"), ensure_ascii=False)
        return
    su = subs[0]["subtitle_url"]
    if su.startswith("//"):
        su = "https:" + su
    # CDN 直连（带 Referer）
    import urllib.request
    req = urllib.request.Request(su, headers={
        "User-Agent": UA, "Referer": f"https://www.bilibili.com/video/{bvid}"})
    body = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())["body"]

    lines = [f"# {m['title']}", "",
             f"> **视频**：https://www.bilibili.com/video/{bvid}",
             f"> **BV**：{bvid} · **UP**：{m['owner']} · **发布**：{m['date']} · "
             f"**时长**：{m['duration']//60}:{m['duration']%60:02d}",
             f"> **字幕**：官方 AI 中文轨，共 {len(body)} 段", "",
             "## 字幕底本", ""]
    for seg in body:
        t = seg["from"]
        lines.append(f"[{int(t//60):02d}:{t%60:05.2f}] {seg['content']}")
    pathlib.Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"  ok {len(body)} 段 -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("list"); p1.add_argument("mid"); p1.add_argument("-o", default="videos.json")
    p1.add_argument("--pages", default="1-4")
    p2 = sub.add_parser("meta"); p2.add_argument("bvid")
    p3 = sub.add_parser("subtitle"); p3.add_argument("bvid"); p3.add_argument("-o", default="source.md")
    a = ap.parse_args()
    if a.cmd == "list":
        lo, hi = a.pages.split("-"); cmd_list(a.mid, a.o, (int(lo), int(hi)))
    elif a.cmd == "meta":
        print(json.dumps(cmd_meta(a.bvid), ensure_ascii=False, indent=1))
    else:
        cmd_subtitle(a.bvid, a.o)
