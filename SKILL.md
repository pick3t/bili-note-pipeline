---
name: bili-note-pipeline
description: 把 B 站（或其他视频）逐集扒成「字幕底本 + markdown 总结 + 静态笔记页 + HTML 幻灯片」的流水线。当用户要批量总结某个 UP 主 / 某个合集的视频、要字幕底本、要一集三件套（md / 非 slide html / slide），或要接着上次的进度继续扒时使用。触发词：扒视频、批量总结、字幕底本、up主每一集、三件套、继续下一批。
---

# bili-note-pipeline · 视频 → 四件套

一条命令级别的流水线：**字幕底本 → markdown 总结（人工写）→ 静态笔记页（自动）→ 幻灯片（自动）→ 资料库归档 → 进度表**。

## 0. 目录约定

项目根目录（下称 `$ROOT`）结构固定：

```
$ROOT/
  videos.json            全部视频清单（最早→最新）
  进度.md                进度表（脚本生成，别手改）
  BV1xxxxxxxxx/
    source.md            字幕底本（标题 + 元信息 + 带时间轴字幕）
    note.md              markdown 总结（人写，质量的唯一来源）
    note.html            静态笔记页（脚本生成）
    deck.html            HTML 幻灯片（脚本生成）
```

## 1. 登录：扫一次，全局复用

**结论先给**：整个流程只需要你扫**一次**码。之后脚本自己处理 cookie 落盘、跨会话导入、12 小时保活。

**先理解一个机制**：agent-browser 的 `--session` 是「一个浏览器实例」，cookie 只活在这个实例里。
实例一重启（换代理、空闲回收、机器重启），登录态就没了——这就是「每个会话都要重新扫码」的原因。
而反复扫码本身才是风控的高风险动作。

所以正确做法不是每个会话都登录，而是**登录一次、把 cookie 落盘、其余会话导入**：

```bash
# ① 只在第一个会话里做：开登录页 → 截图二维码 → 等你扫 → 自动保存
python3 scripts/login.py login            # 默认等 300 秒
#    二维码截图会打印在 /tmp/bili-login-qr.png，记得发给用户（他看不到浏览器窗口）

# ② 之后任何新会话（哪怕换了 session 名）：
python3 scripts/login.py load             # 从本地 cookie 文件导入并验证
python3 scripts/login.py status           # 只看状态，不写
```

- **cookie 存在哪**：`~/.config/bili-note/cookies.json`（绝对路径 `/Users/<你>/.config/bili-note/cookies.json`），
  权限 `0600`，内容是一组 `{name,value,domain,path,expires,httpOnly,secure}`。
  刻意放在仓库和工作区之外，不会被 git/上传带走。可用 `BILI_COOKIE_FILE` 改路径。
- **它等于账号临时凭证**（含 `SESSDATA`）：不要提交、不要发人、不要同步到云端盘；换账号就删掉这个文件。
- `save` 有防倒退：如果这次抓到的是匿名 cookie（没有 `SESSDATA`），而文件里已有登录态，**会拒绝覆盖**（加 `--force` 才强行写）。
- `load` 会顺手查一次 `nav` 接口，输出 `isLogin=true 用户=xxx` 才算成功；返回 3 表示 cookie 已失效，需重新 `login`
- **不建议多个会话共用同一个 session 名**：虽然 cookie 通用，但一个浏览器只有一个当前页面，
  两个会话同时 `open` 会互相跳页，抓字幕会拿错页。**共享登录、各自 session，才是稳的**。

若确实需要共用一个 session，务必保证同一时刻只有一个会话在操作，且别并行执行 `open→eval` 序列。

### 为什么 cookie 老是丢（真凶）

agent-browser 会记住**启动时用的代理**。后续连接若带着不同的代理（每个进程的本地代理端口都不一样），
它就会**重启浏览器**，内存里的 cookie 全部清空——这才是"每个会话都要重新扫码"的根源，不是 B 站踢人。

所以 `login.py` / `bili.py` 调 agent-browser 时**统一剥掉 `HTTP(S)_PROXY`**（B 站直连即可）。
只要走这两个脚本，实例就不再被反复重启。**别手动 export 代理去跑 bili 命令。**

### 从正在跑的会话里复用 cookie

任何一个已登录的会话都能当"源"：

```bash
python3 scripts/login.py save --session <已登录的会话名>   # 导出到 cookie 文件
python3 scripts/login.py load  --session <新会话名>        # 新会话导入
```

查某个会话是否已登录（用新标签探，不打扰它正在做的页面）：

```bash
agent-browser --session <名字> tab new "https://www.bilibili.com/"
agent-browser --session <名字> eval "fetch('https://api.bilibili.com/x/web-interface/nav').then(r=>r.json()).then(d=>d.data.isLogin)"
```

### 保活

`bili_ticket` 这类 cookie 只有几天寿命，定期带 cookie 访问一次 B 站会自动续：

```bash
python3 scripts/login.py keepalive     # load → 访问 B 站 → 再保存
```

建议每 12 小时跑一次，登录态就不会过期，也不用再扫码。


## 2. 拉清单

```bash
python3 scripts/bili.py list <mid> -o $ROOT/videos.json --pages 1-4
```

- 空间视频列表接口有风控（`-352` / `412`）。脚本已带 4 次重试 + 冷却；仍失败就换时间段再跑 `--pages 2-2`，每次结果会**合并**进 videos.json，可以断点续抓。
- `videos.json` 按 `created` 升序（最早→最新），这是默认推进顺序。

## 3. 单集：抓字幕底本

```bash
python3 scripts/bili.py subtitle <bvid> -o $ROOT/<bvid>/source.md
```

产出 `source.md`：标题、链接、UP、发布日期、时长、字幕段数 + `[mm:ss.xx] 文本` 逐段底本。

取字幕前脚本会自己检查登录态，**未登录会自动调 `login.py load` 恢复一次**（输出里能看到 `⚠ 未登录，尝试从 cookie 文件恢复…`）；
只有 cookie 文件也不存在时才需要人工扫码。
**这份底本是后续总结的唯一事实来源**，不要凭记忆写。

## 4. 单集：写 note.md（唯一需要人工判断的一步）

结构固定（脚本按这个结构选版式，别改标题层级）：

```markdown
# 标题（可用「主题：副题」，冒号前当封面主标）

> **来源**：B站 @UP名 · BV号 · 时长
> **字幕**：官方 AI 中文轨，N 段
> **性质**：按「判断顺序」重排的笔记，非逐句转写

## 一句话
一句定性（脚本会把它做成导语卡，不进目录）

## 一、小节名
正文段落 / 要点列表

## 二、小节名
| 列 A | 列 B | 列 C |   ← 三列表格会自动排成表格页
...

## 九、存疑与空白
原片没讲清 / 讲矛盾的地方（这一节是这套笔记的价值差，别省）
```

写作要求：
- **不要按视频顺序流水账**，按「判断顺序 / 因果」重排。
- 每节标题 ≤ 14 字，正文段落 ≤ 120 字，一条要点 ≤ 45 字（超了幻灯片会挤）。
- 至少留一节「存疑与空白」，标出自己不同意或原片没交代的地方。

## 5. 单集：出两个 HTML

```bash
python3 scripts/build_note_html.py $ROOT/<bvid>/note.md $ROOT/<bvid>/note.html
python3 scripts/build_deck.py      $ROOT/<bvid>/note.md $ROOT/<bvid>/deck.html
```

版式选择规则（`build_deck.py` 自动判断）：

| 内容形状 | 版式 |
|---|---|
| 封面 | H1 + 来源/字幕/性质 |
| 「一句话」节 | 导语卡（note.html）/ statement（deck） |
| 只有要点、且平均 ≤30 字 | list（左标题 + 右要点） |
| 只有要点、但平均 >30 字 | dense 双栏（避免挤成竖排） |
| 只有要点、且 >6 条 | list 按 6 条切页，第 2 页起标题带「（续）」 |
| ≥2 段正文 | dense 双栏 |
| 三列表格 | table（细线表格页） |
| 结尾 | end |

写作侧两条硬约束（都踩过）：

- 单节要点**超过 6 条**会被切成 6+N，N 只有 1–2 条时那页几乎空白。控制在 6 条内，或主动拆成两节。
- 要点里可以写 `**加粗**`（2026-11 已修，li 改块流后排版正常）；但 note.md 里别塞 HTML 标签，deck 只认 `**` / 链接。

自检（**必做**，至少抽 3 页）：

```bash
agent-browser --session $S open "file://$ROOT/<bvid>/deck.html"
agent-browser --session $S eval "document.querySelectorAll('.nav-dot')[2].click()"
agent-browser --session $S screenshot /tmp/p3.png   # 然后 ViewImage 看有没有溢出/竖排/压页脚
```

## 6. 归档到资料库（一集一个文件夹）

**结构固定**，不要散放：

```
<专题文件夹>/                      ← 专题文件夹（parent id 见 config.local.md）
  扒片进度                         ← 进度表文档（唯一共享状态，所有会话都读它）
  第 01 集标题/                    ← 一集一个文件夹，用视频标题命名
      笔记标题                     ← note.md（文档）
      字幕底本                     ← source.md（文档，带时间轴的全文字幕）
      笔记标题-笔记页               ← note.html（页面）
      笔记标题-幻灯片               ← deck.html（页面）
```

- 文件夹名 = 视频标题（`/` 换 `／`、`:` 换 `：`，避免路径问题）
- **底本一定要一起传**：只留在本地别人检索不到、换机器就没了。`publish.py` 已内置这一步，且**幂等**（同名文档存在就跳过，可反复运行）。
- 一条命令完成「建/找文件夹 + 传 note.md + 传 source.md」，并打印两个 html 的上传目标：

```bash
python3 scripts/publish.py --bv <bvid> --dir <BV目录> \
  --space-id <spaceId> --parent-id <专题文件夹id>
```

- 再用 `LibraryUpload` 工具传两个 html（`parent_id` = 该集文件夹 id），命名 `<短标题>-笔记页.html` / `<短标题>-幻灯片.html`。
- 传完回读该集文件夹，确认**四个节点齐全**：总结 doc、字幕底本 doc、笔记页、幻灯片。
- 已有节点要调整位置用 `space.workspace.move-node --node-id X --target-parent-id <folderId>`；返回 `data.status=success` 才算成功。

### 固定 id（<专题文件夹>）

| 用途 | id |
|---|---|
| spaceId | `<spaceId>` |
| 专题文件夹 | `<专题文件夹id>` |
| 进度表文档 | `<进度表文档id>` |

## 7. 进度表（多会话共享）

**一条命令完成生成 + 安全同步**（推荐，别手动覆盖）：

```bash
python3 scripts/sync_progress.py $ROOT \
  --space-id <spaceId> --doc-id <进度表文档id> \
  --title "<项目名> · 扒视频进度"
```

它会：

1. 跑 `progress.py` 生成表格（含生成时间戳）
2. 读线上那份，解析各列完成数
3. **只有本地不落后于线上才覆盖**；落后就中止并打印两边数字（`--force` 可强制）

表格列：`序号｜BV 号（超链接）｜视频名称｜markdown 总结｜html 总结｜html slide`，
值只有 `✅ / ❌`。序号按发布时间升序，新投稿追加在末尾，已有编号不前移。

### 并发模型（重要）

这里**没有真正的锁**，靠三层保障避免互相踩：

| 层 | 做了什么 | 解决什么 |
|---|---|---|
| 存储 | 全库只有**一篇**进度表文档（固定 node id） | 不会出现两份表各说各话 |
| 数据 | 表格由**扫描本地目录**生成，内容天然收敛 | 两个会话读同一份文件系统，结果一致 |
| 写入 | `sync_progress.py` 的**防倒退检查** + 时间戳 | 旧快照盖掉新数据（最常见的坑） |
| 分工 | 用户按序号分配区间，开工前先读表 | 重复做同一集 |

仍然存在的限制：

- **最后写入为准**，两个会话同一分钟写，仍是后者覆盖前者——但因为都基于同一目录扫描，内容差异通常只是几分钟的进度差。
- **没有占用标记**：没人能"锁定第 30 集"。真要做，得在同一集文件夹里放一个 `DOING` 文件当租约；目前只靠区间分配。
- 别在项目目录里用 `.` 跑脚本（已在 `progress.py` 里加了根目录校验，会直接报错）。

## 8. 并发与租约（多会话抢同一集怎么办）

进度表只解决「做完没有」，不解决「正在做」。多人/多会话并行时用文件租约：

```bash
export BILI_SESSION=sess-a          # 每个会话一个标识，必须设
python3 scripts/claim.py claim BV1xxx [--ttl 90]
python3 scripts/claim.py list       # 看谁在做什么
python3 scripts/claim.py release BV1xxx
python3 scripts/claim.py break BV1xxx --confirm   # 手动抢占（对方卡死时）
```

**状态机**：无主 →（claim）→ 持有中 →（release）→ 无主
　　　　　　　　　　　　　└（超 ttl 未续约）→ 视为废弃，别人可接手
　　　　　　　　　　　　　└（break --confirm）→ 强制易主

**要点**

- 租约是 `<项目根>/.claims/<bvid>.claim`，靠 `O_CREAT|O_EXCL` 原子创建，天然互斥；8 个进程同时抢，只有一个能成功。
- **文件 mtime 就是心跳**，同会话重复 `claim` 即续约；`ttl` 默认 90 分钟（可用 `--ttl` 按集长调整）。
- 已完成（`note.md`+`note.html`+`deck.html` 都在）默认拒占，要重做加 `--allow-done`。
- 所有动作写进 `.claims/.log`，事后可追责。
- `publish.py` 会检查租约：这一集若在别人手上，直接拒绝归档。

**推荐节奏**：`claim → 抓底本 → 写 note → build → publish → release → sync_progress`
`claim` 放在最前，`release` 放在归档之后——这样整个流程内别人抢不走。

## 9. 批量推进节奏

- 一批 **5 集**，每集走：`claim` → 抓底本 → 写 md → 生成两个 html → 抽查 3 页 → 上传 → `release`；整批结束再 `sync_progress`。
- 每批结束给用户：本批清单 + 链接 + 剩余数量，别一次性铺开 20 集（质量会掉）。
- 遇到长视频（>30 分钟）或内容跨越多主题，拆成两篇 note.md，第二篇命名 `<bvid>-2`。

## 常见故障

| 现象 | 处理 |
|---|---|
| `无官方字幕` | 先查登录；再查该视频是否真的没 AI 字幕（部分早期视频没有），有则退回 OCR |
| 列表 `-352` / `412` | 风控。等 20–60s，或换 `--pages` 分批跑，结果会自动合并 |
| 幻灯片文字竖排 | 老版本 `.bullet-list li` 用 grid，要点里的 `<b>` 被挤进窄列逐字竖排（已修为块流）。若在老 deck 上复现，重跑 `build_deck.py` 即可 |
| 幻灯片出现只剩 1 条的「（续）」页 | 该节要点 >6 条被机械切块。把该节压到 6 条以内，或拆成两个小节 |
| 中文一行只放得下几个字 | 模板按 1920 设计，`clamp()` 已设最小字号；预览面板窄会缩小，按 F11 全屏看真实效果 |
| 上传后文档样式丢失 | 文档只吃 Markdown，表格用 GFM，别塞 HTML 标签 |
| `正被 sess-x 占用` | 别人在做这一集。换一集，或等 `ttl` 到期；对方确认卡死再 `break --confirm` |
| 进度表写进去反而是旧数据 | 用 `sync_progress.py`（有防倒退检查），别直接 `create_doc --confirm-overwrite` |
| 租约文件残留 | `.claims/*.claim` 超过 `ttl` 会自动失效，不影响接手；也可 `release` 清掉 |
| `cookies get` 返回 0 条、每个会话都要重登 | 浏览器被重启了。八成是手动带了 `HTTP(S)_PROXY` 去调 agent-browser；用 skill 脚本（已自动剥代理），再 `login.py load` |
| 日志出现 `relaunched browser` | 同上：代理配置变了。别混用不同代理的进程操作同一个 session |
| 二维码扫了但 `login.py` 一直不结束 | 老版本 bug（已修）：等待循环里用 `is_login()` 轮询，而它会 `open bilibili.com`，等于每 5 秒把登录页刷走一次，扫码确认永远回不来。现在等待期只读 cookie 里的 `SESSDATA`，不导航。若仍在旧版本上遇到：别中断，先 `login.py status`，成功就 `login.py save` |
| 登录页显示 `ERR_PROXY_CONNECTION_FAILED` | 系统代理（Clash 之类 127.0.0.1:7897）挂了，但 Chrome 仍走系统代理。脚本只剥环境变量，管不到系统代理——关掉系统代理或让它放行 `bilibili.com` 直连，再重跑 `login.py login` |
| `Auto-launch failed: CDP response channel closed` | 给 agent-browser 传了 `--proxy-server=direct://` 这类启动参数，反而起不来。别传启动参数，靠脚本剥环境变量即可 |
