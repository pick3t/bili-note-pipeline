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

## 1. 一次性准备：登录

官方 AI 字幕**必须登录**才取得到（不登录返回空 subtitles）。流程：

```bash
S=bili-$$; agent-browser session id --scope worktree --prefix bili   # 固定会话名，记下来复用
agent-browser --session $S open "https://passport.bilibili.com/login"
agent-browser --session $S screenshot /tmp/qr.png                    # 把二维码截图发给用户扫
agent-browser --session $S eval "fetch('https://api.bilibili.com/x/web-interface/nav',{credentials:'include'}).then(r=>r.json()).then(d=>d.data.isLogin)"
```

要点：
- 用户看不到浏览器窗口，**必须截图**（`screenshot`）再 `present_files` 给他扫。
- 登录成功后 cookie 会跟着会话走；浏览器闲置重启后可能失效，脚本报「无官方字幕」时先重新确认登录。
- 拿不到登录时只能退回「下载视频 + 每 0.5s 截字幕区 + OCR」，慢 10 倍且错字多，非必要不用。

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
| ≥2 段正文 | dense 双栏 |
| 三列表格 | table（细线表格页） |
| 结尾 | end |

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

```bash
python3 scripts/progress.py $ROOT --videos $ROOT/videos.json --out 进度.md
```

表格列：`序号｜BV 号（超链接）｜视频名称｜markdown 总结｜html 总结｜html slide`，值只有「✅（完成）/ ❌（未完成）」——不要用文字，便于一眼扫。

**序号规则**：按 `created` 升序（最早＝1），用于用户指定区间（"做 30–39"）。新投稿发布更晚，只会追加在末尾，**已有编号不前移**；因此抓清单后要一次抓全（`--pages 1-4`），缺页会让编号错位——发现编号可疑先补全 `videos.json` 再重跑。

同步到资料库（覆盖同一篇文档，别新建第二份）：

```bash
python3 "$LIB/doc/create_doc.py" --title "扒片进度" \
  --node-block-id <进度表文档id> --space-id <spaceId> \
  --content-file $ROOT/进度.md --confirm-overwrite
```

写入前先自检（防踩坑）：
- **用项目根路径，不要用 `.`**：`progress.py` 现在会校验目录（找不到 `videos.json` 就报错退出），标题也从目录名取，`.` 会得到空标题。
- **只在每批结束时写一次**，别边做边写；两个会话同时覆盖，内容会互相打架，以最后一次为准。
- 覆盖后**回读文档前两段**，确认标题是「<项目名> · 扒片进度」、汇总行的集数跟你本地一致。

多会话协作约定：
- 每个会话开工前先读这份进度表（`library_search` 或 `get_doc_reviews.py --page-id <进度表文档id>`），只领「未完成」的集
- 领到的区间由用户分配，会话之间不重叠；做完一批立刻更新进度表再继续
- 进度表以「资料库那份」为准，本地 `进度.md` 只是生成物

## 8. 批量推进节奏

- 一批 **5 集**：抓底本 → 写 md → 生成两个 html → 抽查 3 页 → 上传 → 更新进度表。
- 每批结束给用户：本批清单 + 链接 + 剩余数量，别一次性铺开 20 集（质量会掉）。
- 遇到长视频（>30 分钟）或内容跨越多主题，拆成两篇 note.md，第二篇命名 `<bvid>-2`。

## 常见故障

| 现象 | 处理 |
|---|---|
| `无官方字幕` | 先查登录；再查该视频是否真的没 AI 字幕（部分早期视频没有），有则退回 OCR |
| 列表 `-352` / `412` | 风控。等 20–60s，或换 `--pages` 分批跑，结果会自动合并 |
| 幻灯片文字竖排 | 要点过长被塞进 list 版式。检查该条是否 >45 字，或确认 `build_deck.py` 的长要点分支生效 |
| 中文一行只放得下几个字 | 模板按 1920 设计，`clamp()` 已设最小字号；预览面板窄会缩小，按 F11 全屏看真实效果 |
| 上传后文档样式丢失 | 文档只吃 Markdown，表格用 GFM，别塞 HTML 标签 |
