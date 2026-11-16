# bili-note-pipeline

把 B 站（或其他视频）逐集扒成**四件套**的 agent 流水线：

```
字幕底本(source.md) → markdown 总结(note.md) → 静态笔记页(note.html) → HTML 幻灯片(deck.html)
```

面向「批量整理某个 UP 主 / 某个合集」：一个会话从头做到尾，或多个会话并行，产物结构一致、可归档、可检索。

## 它解决什么

- **字幕怎么拿**：官方 AI 字幕必须登录，走播放器接口 `player/wbi/v2` 取 `subtitle_url`，再从 CDN 拉 JSON。脚本把「登录 → 取字幕 → 落成带时间轴的底本」串好，并把扫码、二维码要截图发人、cookie 失效这些坑写进文档。
- **列表怎么抓**：空间投稿接口要 WBI 签名且有风控（`-352` / `412`）。`bili.py list` 负责签名、重试、退避、断点合并。
- **总结怎么保持一致**：`note.md` 的标题层级有约定，两个生成器按「内容形状」自动选版式（要点→列表页、多段落→双栏、表格→表格页、短内容→放大居中）。
- **多会话怎么不打架**：文件租约（`claim.py`）+ 一份带防倒退检查的进度表（`sync_progress.py`）。

## 依赖

- Python 3.9+（标准库，无第三方包）
- [agent-browser](https://www.npmjs.com/package/agent-browser)：B 站请求都在它托管的浏览器上下文里发出，带登录态与指纹
- 可选：WorkBuddy 的 library 技能脚本（归档到资料库）

## 安装

```bash
git clone <this-repo> ~/.workbuddy/skills/bili-note-pipeline
```

会话里说「扒某个 UP 主的视频」「要字幕底本」「接着上次进度继续」即可触发。

## 用法

```bash
export BILI_SESSION=sess-a                    # 会话标识，租约靠它区分

python3 scripts/bili.py list <mid> -o $ROOT/videos.json --pages 1-4
python3 scripts/claim.py claim <bvid>          # 先占住这一集
python3 scripts/bili.py subtitle <bvid> -o $ROOT/<bvid>/source.md
#   ……写 note.md……
python3 scripts/build_note_html.py $ROOT/<bvid>/note.md $ROOT/<bvid>/note.html
python3 scripts/build_deck.py      $ROOT/<bvid>/note.md $ROOT/<bvid>/deck.html
python3 scripts/publish.py --bv <bvid> --dir $ROOT/<bvid> \
  --space-id <spaceId> --parent-id <专题文件夹id>
python3 scripts/claim.py release <bvid>
python3 scripts/sync_progress.py $ROOT --space-id <spaceId> --doc-id <进度表id>
```

完整流程、md 体例、版式规则、故障表见 [`SKILL.md`](./SKILL.md)。

## 目录

```
SKILL.md                      agent 用的操作手册（9 步 + 故障表 + 并发模型）
config.local.md               本地 id 与路径（已 gitignore，不进仓库）
scripts/
  bili.py                     列表 / 元信息 / 官方字幕
  build_note_html.py          md → 静态笔记页
  build_deck.py               md → 幻灯片（按内容形状选版式）
  publish.py                  建标题文件夹 + 传 md + 传字幕底本
  progress.py                 扫描目录 → 进度表
  sync_progress.py            生成 + 安全覆盖到资料库（防倒退）
  claim.py                    文件租约：claim / release / list / break
templates/
  note.css                    笔记页样式
  deck_theme.html             幻灯片主题（只含 head 与翻页脚本）
tests/
  test_claim.py               15 个场景，含 8 进程并发抢占
```

## 设计取舍

- **字幕优先官方轨，不优先 OCR**：OCR 每集多花 4 分钟且错字多；只有拿不到字幕才退回逐帧截图 + Vision OCR。
- **总结必须人工写**：这是质量的全部来源，脚本只负责排版；流水线里唯一不能自动化的一步，留给人。
- **版式按内容形状选，不按页数**：同一套样式要能容纳「一段话的定论页」和「六行三列的对照表」。
- **进度表用符号**：✅ / ❌，一眼扫完。
- **登录只做一次**：agent-browser 的实例一旦因代理变化被重启，内存 cookie 就没了（这是「每个会话都要重扫」的真因）。所以脚本统一剥掉代理变量，并把 cookie 落盘到 `~/.config/bili-note/cookies.json`，新会话 `load` 即可；另有 12 小时保活任务续短周期 cookie。
- **并发用文件租约，不用服务端锁**：两个会话共享同一目录，`O_CREAT|O_EXCL` 就是最便宜的互斥；mtime 当心跳，超时自动回收。跨机器会失效——那种情况要换成服务端租约。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## License

未附 License，如需开源请自行补充。
