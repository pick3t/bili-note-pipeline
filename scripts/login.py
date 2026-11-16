#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""login.py — 登录一次，所有会话共用（B 站 cookie 存取）

agent-browser 的 session 是「一个浏览器实例」，cookie 只活在这个实例里；
实例重启（换代理、空闲回收、机器重启）就掉登录。所以正确做法是：
扫一次码 → 导出 cookie 到本地文件 → 以后每个新会话先 import，不用再扫。

子命令:
  python3 login.py login  [--session X] [--wait 300]   # 开登录页、截图二维码、等扫码、自动保存
  python3 login.py save   [--session X]                # 从当前会话导出 cookie 到本地文件
  python3 login.py load   [--session Y]                # 把本地文件导入到（新）会话
  python3 login.py status [--session X]                # 查是否已登录

cookie 文件默认 ~/.config/bili-note/cookies.json（0600 权限，本机私密）
"""
import argparse, json, os, pathlib, subprocess, sys, time

COOKIE_FILE = pathlib.Path(os.environ.get("BILI_COOKIE_FILE")
                           or (pathlib.Path.home() / ".config/bili-note/cookies.json"))
DEFAULT_SESSION = os.environ.get("BILI_BROWSER_SESSION", "bili-dff29cd85209")


# ── agent-browser 调用 ───────────────────────────────────────────────────
def ab(session, *args, json_out=False, timeout=120):
    cmd = ["agent-browser", "--session", session, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = r.stdout.strip()
    if json_out:
        try:
            return json.loads(out)
        except Exception:
            return None
    return out


def get_cookies(session):
    d = ab(session, "cookies", "get", "--json", json_out=True)
    if not d:
        return []
    return (d.get("data") or {}).get("cookies") or []


def is_login(session):
    """返回 {'ok': bool, 'name': str}；任何异常都当未登录"""
    try:
        ab(session, "open", "https://www.bilibili.com/")
        js = ("fetch('https://api.bilibili.com/x/web-interface/nav',{credentials:'include'})"
              ".then(r=>r.json()).then(d=>JSON.stringify({ok:!!(d.data&&d.data.isLogin),"
              "name:(d.data&&d.data.uname)||''}))")
        out = ab(session, "eval", js)
        d = json.loads(out)
        if not isinstance(d, dict):
            return {"ok": False, "name": ""}
        return {"ok": bool(d.get("ok")), "name": d.get("name") or ""}
    except Exception:
        return {"ok": False, "name": ""}


# ── 命令 ─────────────────────────────────────────────────────────────────
def cmd_save(session):
    cs = get_cookies(session)
    if not cs:
        print("当前会话没有 cookie（可能未登录或浏览器刚重启）；先跑 login")
        return 1
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cs, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(COOKIE_FILE, 0o600)
    have = [c["name"] for c in cs]
    key = "SESSDATA" in have
    print(f"✓ 已保存 {len(cs)} 条 cookie -> {COOKIE_FILE}"
          f"（含登录态 SESSDATA: {'是' if key else '否'}）")
    return 0 if key else 2


def cmd_load(session):
    if not COOKIE_FILE.exists():
        print(f"没有 cookie 文件 {COOKIE_FILE}，先在一个会话里 login")
        return 1
    cs = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    ok = 0
    for c in cs:
        args = ["cookies", "set", c["name"], c["value"]]
        if c.get("domain"):
            args += ["--domain", c["domain"]]
        if c.get("path"):
            args += ["--path", c["path"]]
        if c.get("secure"):
            args += ["--secure"]
        if c.get("httpOnly"):
            args += ["--http-only"]
        if c.get("expires", -1) and c["expires"] > 0:
            args += ["--expires", str(int(c["expires"]))]
        r = subprocess.run(["agent-browser", "--session", session, *args],
                           capture_output=True, text=True)
        ok += 0 if r.returncode else 1
    st = is_login(session)
    print(f"导入 {ok}/{len(cs)} 条 -> isLogin={st['ok']}"
          + (f"（{st['name']}）" if st["ok"] else "（失败：cookie 可能已过期，需重新 login）"))
    return 0 if st["ok"] else 3


def cmd_status(session):
    st = is_login(session)
    print(f"session={session} isLogin={st['ok']}" + (f" 用户={st['name']}" if st["ok"] else ""))
    print(f"cookie 文件：{'有' if COOKIE_FILE.exists() else '无'}  {COOKIE_FILE}")
    return 0 if st["ok"] else 3


def cmd_login(session, wait_s):
    ab(session, "open", "https://passport.bilibili.com/login")
    time.sleep(3)
    shot = "/tmp/bili-login-qr.png"
    ab(session, "screenshot", shot)
    print(f"二维码截图：{shot}\n请用 B 站 App 扫码（最多等 {wait_s}s）…")
    t0 = time.time()
    while time.time() - t0 < wait_s:
        st = is_login(session)
        if st["ok"]:
            print(f"✓ 登录成功：{st['name']}（用时 {int(time.time()-t0)}s）")
            return cmd_save(session)
        time.sleep(5)
    print("✗ 等待超时，未检测到登录")
    return 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["login", "save", "load", "status"])
    ap.add_argument("--session", default=DEFAULT_SESSION)
    ap.add_argument("--wait", type=int, default=300)
    a = ap.parse_args()
    if a.cmd == "login":
        return cmd_login(a.session, a.wait)
    if a.cmd == "save":
        return cmd_save(a.session)
    if a.cmd == "load":
        return cmd_load(a.session)
    return cmd_status(a.session)


if __name__ == "__main__":
    sys.exit(main())
