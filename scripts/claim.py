#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim.py — 用文件租约协调多会话：谁在做哪一集

原理：`.claims/<bvid>.claim` 的原子创建（O_CREAT|O_EXCL）就是锁；
文件的 mtime 就是心跳；超过 ttl 视为废弃，可被接手。

用法:
  export BILI_SESSION=sess-a          # 每个会话一个标识（也可以用 --session）
  python3 claim.py claim BV1xxxx [--ttl 90] [--allow-done]
  python3 claim.py release BV1xxxx
  python3 claim.py list [--json]
  python3 claim.py break BV1xxxx --confirm     # 手动抢占（过期或卡死时用）

退出码:
  0 成功   3 被他人占用   4 参数/身份问题   5 已完成拒占
"""
import argparse, json, os, pathlib, sys, time, socket

DEFAULT_TTL = 90          # 分钟
CLAIMS_DIRNAME = ".claims"


# ── 基础设施 ─────────────────────────────────────────────────────────────
def claims_dir(root):
    d = pathlib.Path(root) / CLAIMS_DIRNAME
    if not d.exists():
        try:
            d.mkdir(parents=True)
        except FileExistsError:      # 并发创建：正常，忽略
            pass
    return d


def claim_path(root, bvid):
    return claims_dir(root) / f"{bvid}.claim"


def session_id(arg=None):
    sid = arg or os.environ.get("BILI_SESSION")
    if sid:
        return sid.strip()
    print("缺少会话标识：请 export BILI_SESSION=sess-a 或加 --session", file=sys.stderr)
    sys.exit(4)


def read_claim(p):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"session": "?", "step": "?", "started": 0}
    return d


def age_minutes(p):
    return (time.time() - p.stat().st_mtime) / 60.0


def ttl_of(p, default=DEFAULT_TTL):
    try:
        return float(read_claim(p).get("ttl") or default)
    except Exception:
        return default


def is_expired(p, default=DEFAULT_TTL):
    return age_minutes(p) > ttl_of(p, default)


def log(root, msg):
    p = claims_dir(root) / ".log"
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def is_done(root, bvid):
    d = pathlib.Path(root) / bvid
    return all((d / f).exists() for f in ("note.md", "note.html", "deck.html"))


# ── 命令 ─────────────────────────────────────────────────────────────────
def cmd_claim(root, bvid, sid, ttl, allow_done):
    if is_done(root, bvid) and not allow_done:
        print(f"{bvid} 已完成（note.md / note.html / deck.html 都在），无需占用；"
              f"确实要重做请加 --allow-done")
        return 5

    p = claim_path(root, bvid)
    payload = json.dumps({"bvid": bvid, "session": sid, "step": "start",
                          "started": int(time.time()), "ttl": ttl,
                          "host": socket.gethostname()}, ensure_ascii=False)

    # 1) 原子创建
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        log(root, f"claim {bvid} by {sid}")
        print(f"✓ 已占用 {bvid}（{sid}，ttl {ttl} 分钟）")
        return 0
    except FileExistsError:
        pass

    # 2) 已存在：自己的就续约
    cur = read_claim(p)
    if cur.get("session") == sid:
        os.utime(p, None)
        print(f"↻ 续约 {bvid}（{sid}，已做 {age_minutes(p):.0f} 分钟）")
        return 0

    # 3) 别人的：过期才能接手
    if is_expired(p, DEFAULT_TTL):
        _take_over(p, payload)
        log(root, f"steal {bvid} from {cur.get('session')} (expired {age_minutes(p):.0f}min) by {sid}")
        print(f"✓ 接手 {bvid}：原持有者 {cur.get('session')} 已超时 {age_minutes(p):.0f} 分钟")
        return 0

    left = ttl_of(p, DEFAULT_TTL) - age_minutes(p)
    print(f"✗ {bvid} 正被 {cur.get('session')} 占用，已做 {age_minutes(p):.0f} 分钟，"
          f"还剩约 {max(left, 0):.0f} 分钟租约")
    return 3


def _take_over(p, payload):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, p)          # 原子替换


def cmd_release(root, bvid, sid):
    p = claim_path(root, bvid)
    if not p.exists():
        print(f"{bvid} 没有被占用，无需释放")
        return 0
    cur = read_claim(p)
    if cur.get("session") != sid:
        print(f"✗ {bvid} 的租约属于 {cur.get('session')}，不能由 {sid} 释放")
        return 3
    p.unlink()
    log(root, f"release {bvid} by {sid}")
    print(f"✓ 已释放 {bvid}")
    return 0


def cmd_break(root, bvid, sid, confirm):
    p = claim_path(root, bvid)
    if not p.exists():
        print(f"{bvid} 本来就没人占，直接 claim 即可")
        return 0
    if not confirm:
        cur = read_claim(p)
        print(f"{bvid} 当前持有者：{cur.get('session')}（已做 {age_minutes(p):.0f} 分钟）。"
              f"确认抢占请加 --confirm")
        return 4
    cur = read_claim(p)
    payload = json.dumps({"bvid": bvid, "session": sid, "step": "break",
                          "started": int(time.time()), "ttl": DEFAULT_TTL,
                          "host": socket.gethostname()}, ensure_ascii=False)
    _take_over(p, payload)
    log(root, f"BREAK {bvid} from {cur.get('session')} by {sid}")
    print(f"✓ 已强制接手 {bvid}（原持有者 {cur.get('session')}）")
    return 0


def cmd_list(root, as_json):
    d = claims_dir(root)
    rows = []
    for p in sorted(d.glob("*.claim")):
        cur = read_claim(p)
        rows.append({"bvid": p.stem, "session": cur.get("session"),
                     "age_min": round(age_minutes(p)),
                     "expired": is_expired(p, DEFAULT_TTL)})
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    if not rows:
        print("当前没有占用")
        return 0
    for r in rows:
        flag = "（已超时，可接手）" if r["expired"] else ""
        print(f"{r['bvid']}  {r['session']}  已做 {r['age_min']} 分钟{flag}")
    return 0


# ── 入口 ─────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["claim", "release", "break", "list", "whoami"])
    ap.add_argument("bvid", nargs="?")
    ap.add_argument("--root", default=".", help="项目根目录（含 BV*/ 与 videos.json）")
    ap.add_argument("--session", default=None)
    ap.add_argument("--ttl", type=float, default=DEFAULT_TTL)
    ap.add_argument("--allow-done", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    root = pathlib.Path(a.root)

    if a.cmd == "whoami":
        print(session_id(a.session))
        return 0
    if a.cmd == "list":
        return cmd_list(root, a.json)

    sid = session_id(a.session)
    if not a.bvid:
        print("缺少 BV 号", file=sys.stderr)
        return 4
    if not (root / a.bvid).is_dir():
        print(f"项目根下没有 {a.bvid} 目录", file=sys.stderr)
        return 4

    if a.cmd == "claim":
        return cmd_claim(root, a.bvid, sid, a.ttl, a.allow_done)
    if a.cmd == "release":
        return cmd_release(root, a.bvid, sid)
    return cmd_break(root, a.bvid, sid, a.confirm)


if __name__ == "__main__":
    sys.exit(main())
