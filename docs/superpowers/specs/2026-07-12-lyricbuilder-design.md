# lyricBuilder 设计文档

- 日期：2026-07-12
- 状态：已批准（设计阶段）

## 一、目标

为本地曲库自动匹配歌词，使音乐导入播放器时歌词随之可用。扫描曲库文件夹（mp3 / wav / m4a 等多种格式），逐首歌匹配歌词并产出 `.lrc` 同名文件 + 内嵌进音频标签，让播放器自动加载。

非目标：不做播放、不做曲库管理、不做歌词编辑器。

## 二、需求摘要

| 维度 | 决策 |
|------|------|
| 核心功能 | 扫描曲库 → 匹配歌词 → 写出 .lrc + 内嵌 |
| 歌词来源 | 在线 API 优先，查不到时网页爬取兜底 |
| 匹配依据 | 音频标签（title+artist）优先，wav 等无标签时用文件名兜底 |
| 输出形式 | .lrc 同名文件 + 内嵌进音频，两者都做（wav 等无内嵌标准的只出 .lrc） |
| 运行方式 | CLI 全自动 + `--dry-run` 预览 |
| 歌词类型 | 同步 LRC 优先，找不到时纯文本兜底 |
| 技术栈 | Python |
| Skill | 项目内薄包装 CLI，让 agent 能自动调用 |

## 三、方案选型

采用 **方案 A：API 主导 + 爬取兜底 + 本地结果缓存**。

- 取词首选 LRCLIB（`lrclib.net`，公开免 key、专做同步 LRC），网易云歌词 API 作为补充源。
- 两者都查不到时回退网页爬取（容错解析 HTML）。
- 匹配结果在本地缓存按歌索引，重跑直接命中、不重复请求、便于离线复查。
- 理由：API 结构化数据最稳最快，爬取只走兜底路径、把脆弱性隔离到尾部；本地缓存成本低（一个 JSON 索引 + 缓存目录），换来重跑省时、离线复查、命中统计。

## 四、架构与目录布局

```
lyricBuilder/
├── lyricbuilder/
│   ├── __init__.py
│   ├── cli.py            # 入口：参数解析、--dry-run、调度、统计
│   ├── scanner.py        # 扫描曲库，提取每首歌的"线索"(title/artist/path/format)
│   ├── tagger.py         # 唯一写文件/改音频者：写 .lrc + 内嵌 USLT/lyrics
│   ├── lyricfetch.py     # 取词流水线：API源→爬取兜底，返回统一结构
│   └── cache.py          # 本地结果缓存：按歌索引、命中复用、命中统计
├── sources/             # 取词源适配（每源一文件，可增删）
│   ├── lrclib.py
│   ├── netease.py
│   └── web_scrape.py
├── .claude/skills/lyricbuilder/SKILL.md   # 薄包装 CLI 的 agent 操作手册
├── docs/superpowers/specs/
├── tests/
├── pyproject.toml
└── README.md
```

模块边界（单一职责，副作用集中）：
- `scanner` 只产出线索对象（title/artist/path/format/source），不碰网络、不写文件。
- `lyricfetch` 按优先级串多个源，返回统一结构，不写文件。
- `tagger` 是唯一有文件/音频副作用的模块，便于 dry-run 整体跳过。
- `cache` 纯本地 JSON 索引 + 缓存目录，可独立测试。
- `sources/*` 每源一文件，加/换源不动流水线逻辑（代价是少量样板，对会频繁换源的工具值得）。

### 核心数据流

```
scanner → [每首歌的线索] → lyricfetch(lrclib→netease→web_scrape)
       → [歌词结果] → cache(存/查) → tagger(写 .lrc + 内嵌)
```

## 五、数据流：一首歌的完整处理路径

以 `周杰伦 - 晴天.mp3` 为例：

1. **线索提取**（scanner）
   - 读 ID3 → `{title:"晴天", artist:"周杰伦", path, format:"mp3"}`。
   - ID3 缺失/为空 → 解析文件名 `周杰伦 - 晴天`，标记 `source="filename"` 表示信心较低。

2. **缓存命中检查**（cache）
   - 键 = 规范化 `title + artist`（小写、去标点、去空格）做哈希。
   - 命中且缓存里有结果 → 直接返回，跳过网络（重跑省时、离线复查关键）。

3. **取词流水线**（lyricfetch，按序尝试，命中即停）
   ```
   lrclib.get(title, artist)   → 同步 LRC？
        ↓ None
   netease.get(title, artist)  → 同步 LRC 或纯文本？
        ↓ None
   web_scrape.get(title, artist) → 纯文本（爬取兜底，多无时间轴）
        ↓ None
   {matched: false}
   ```
   - 优先级即"同步 LRC 优先、纯文本兜底"：lrclib 几乎只给同步 LRC；netease 给同步或纯文本；爬取多给纯文本。每个源内部判断拿到的是否带时间轴。
   - 统一返回结构：`{matched: bool, type: "lrc"|"plain"|null, text, source, query}`。

4. **写出**（tagger，dry-run 整段跳过）
   - 写 `.lrc` 同名文件：`晴天.mp3` → `晴天.lrc`（纯文本也写成 .lrc 内容，无时间标签行）。
   - 内嵌：mp3 写 `USLT` 帧、m4a 写 `lyrics` atom。wav/flac 等无内嵌标准 → 只写 .lrc，跳过内嵌并记日志。
   - 已存在 `.lrc` → 默认跳过，`--force` 才覆盖。

5. **统计汇总**（cli 收尾）：`已匹配 LRC / 已匹配纯文本 / 未匹配 / 缓存命中 / 内嵌失败` 一张表。

### 关键决策
- 缓存键用 `title+artist` 而非文件路径——同一首歌多份（专辑版/单曲版/不同格式）只查一次。代价是同名异曲误命中，但同 artist+title 异曲极罕见，可接受。
- 缓存命中后仍执行写出（缓存的是"查词结果"而非"已写文件状态"）——换播放器/删了 .lrc 重跑也能复用匹配结果，只省网络不漏写出。

## 六、错误处理与边界

原则：任何外部失败降级到"这首歌未匹配/跳过"，绝不因一首歌或一个源中断整批；所有降级进日志 + 最终统计表。

**网络层**
- 每源超时默认 8s + 重试上限 2 次（指数退避）。
- 单源彻底失败 → 视作返回 None，流水线自动降到下一源；单源失败永不中断整首处理。
- 429/限速 → 退避后重试，仍失败则降级，记 `rate_limited`。
- 全部源 None → 该歌记 `未匹配`，继续下一首，不报错退出。

**文件/标签层**
- 读标签失败/乱码 → 回退文件名解析，记 `tag_corrupt`，不跳过。
- 不支持的格式（.ape/.ogg 等，视实现而定）→ 能读标签就匹配并写 .lrc、内嵌跳过记日志；完全读不了 → 记 `unsupported_format` 跳过。
- 写 .lrc / 内嵌失败（权限/磁盘满/文件被占）→ 记日志、标 `write_failed`，继续；已写的 .lrc 不回滚，下次重跑可补。
- 文件名完全无法解析出 title/artist（如 `track01.mp3` 且无标签）→ 记 `no_clue` 跳过，不强行瞎查。

**爬取兜底层**
- HTML 结构变/选择器失效 → 解析返回 None，记 `scrape_parse_failed`，不崩。
- 爬取到纯文本（无时间轴）→ 仍接受作为纯文本兜底结果。

**音频编码**（tagger）
- 写 USLT 前：mutagen 写标签是覆盖式，写入异常 catch 后记 `embed_failed`，.lrc 已写则保留；保留原文件不动。

**并发**
- 初版单线程串行，简单可观测。预留 `--jobs N` 接口但初版不实现（避免并发带来的缓存写竞态、限速放大）。

## 七、测试策略

围绕"把外部依赖隔离"设计，全部用 mock，不打真实网络。

**单元测试（pytest）**
- `scanner`：fixtures 现造空 mp3/m4a，验证标签读取 + 文件名解析回退 + `source="filename"` 低信心标记。
- `cache`：键规范化（大小写/标点/空格）、命中/未命中、损坏缓存文件不崩、并发写同一键容忍。
- `lyricfetch` 流水线：mock 源对象验证优先级——lrclib 命中不问 netease、都 None 才到爬取、全 None 返回 `{matched:false}`、返回结构统一。
- `sources/*`：每源一测试，用 `respx` 固定 API/网页响应，验证解析正确 + 异常 HTTP（429/超时/乱码 HTML）返回 None 不抛。
- `tagger`：临时目录造音频，验证 .lrc 写出内容、mp3 USLT 写入可读回、m4a lyrics atom、wav 跳过内嵌但写 .lrc、`--force` 覆盖、已存在默认跳过、写入失败不损坏原文件。

**集成测试**
- 端到端：小目录（2-3 首）+ 全 mock 源 → 跑完整 CLI → 断言 .lrc 出现、内嵌可读回、缓存索引正确、统计输出匹配。
- `--dry-run` 专用：断言运行后无任何文件改动、但统计/日志反映"会匹配到什么"。

**不测什么（YAGNI）**
- 不打真实网络请求，不依赖 LRCLIB/网易云真实可用性。
- 不测爬虫对真实站点的解析（mock 固定 HTML 样本即可）。
- 不测 mutagen 自身正确性（信任库），只测"我们调用它的方式对不对"。

**测试数据策略**
- 音频样本：测试里用 mutagen 现造极小空音频，不提交二进制，可重建、无版权。
- HTML/JSON 样本：fixtures 放脱敏离线响应快照。

**铁律**：`tagger` 测试保证"dry-run 期间零副作用"和"写入失败不损坏原文件"——这是用户敢放心跑的前提。

## 八、配置与依赖

**外部依赖**（pyproject.toml）
- `mutagen` — 音频标签读写（ID3/atom/FLAC/Vorbis），纯 Python 无编译。
- `httpx` — 同步 HTTP 客户端（API + 爬取统一）。
- `beautifulsoup4` + `lxml` — 爬取兜底 HTML 解析。
- `typer` — CLI 框架（类型注解、自动 --help、参数声明）。
- `rich` — 统计表/进度/日志彩色输出。
- 开发依赖：`pytest`、`respx`（httpx mock）、`pytest-tmpfiles`。

**配置来源**（优先级高到低）
1. CLI 参数：`--source-dir`、`--dry-run`、`--force`、`--no-embed`、`--no-lrc`、`--verbose` 等。
2. 配置文件 `~/.lyricbuilder/config.toml`（可选，存默认曲库路径、源开关、超时、缓存路径）。
3. 内置默认值。

**配置示例**
```toml
source_dir = "~/Music/library"
cache_dir  = "~/.lyricbuilder/cache"
timeout_sec = 8
retry = 2
proxy = "http://127.0.0.1:6152"   # 可选，默认不设
[sources]
lrclib  = true
netease = true
scrape  = true   # 兜底爬取开关，可关掉只走 API
```

**CLI 接口**
```
lyricbuilder scan [--source-dir DIR] [--dry-run] [--force]
                  [--no-embed] [--no-lrc] [--verbose]
lyricbuilder stats              # 缓存命中率/未匹配列表
lyricbuilder config show|init   # 初始化/查看配置
```
默认子命令 `scan`，最常用即 `lyricbuilder --dry-run`。

**关键决策**
- 配置文件可选——不写配置也能用，全靠 CLI 参数；写了当默认值。不强迫用户先配环境。
- 爬取兜底给单独开关 `[sources] scrape`——可一键关掉只走 API，规避爬虫脆弱性/合规顾虑。
- `--no-embed` / `--no-lrc` 临时只要其中一种输出，默认两者都做。
- 代理 `proxy` 默认不设；本机 Surge（`127.0.0.1:6152`）访问受限站点时手动开。httpx 不自动走系统代理。

## 九、Skill：薄包装 CLI

把 lyricBuilder 做成项目内 skill，让任何 agent 自动调用，不必记 CLI 参数。

**位置**：`.claude/skills/lyricbuilder/SKILL.md`（跟 repo 走，clone 即用）。

**触发**（description 决定 agent 何时自动加载）：
> Use when the user wants to fetch/match lyrics for a music library or folder, or attach lyrics (.lrc + embed) to audio files. Triggers: 匹配歌词、歌词匹配、曲库歌词、match lyrics、fetch LRC.

**skill 的职责**（给 agent 的操作手册，不重新实现逻辑）：
1. 前置检查：确认 `lyricbuilder` CLI 可用；不可用则在 repo 根目录 `uv sync` 或 `pip install -e .` 装好再继续。
2. 默认走 dry-run：第一次对新曲库必先 `lyricbuilder scan --source-dir <dir> --dry-run --verbose`，给用户看"会匹配到什么/未匹配哪些"，确认后再实跑。
3. 实跑：`lyricbuilder scan --source-dir <dir> --verbose`，跑完用 `lyricbuilder stats` 看命中率。
4. 失败兜底：未匹配的歌引导用户补标签或 `--force` 重试；内嵌失败的歌不重试音频写入、只保留 .lrc（沿用 §6 策略）。
5. 代理/网络：请求超时多时，提示用户在 `~/.lyricbuilder/config.toml` 设 `proxy = "http://127.0.0.1:6152"`。

**关键决策**
- skill 不内嵌取词逻辑——重活全在 CLI，skill 只管"怎么用、怎么解读、怎么兜底"。工具升级不用改 skill，agent 不必懂匹配细节。
- skill 强制"先 dry-run 再实跑"——避免 agent 一上来就改用户音频文件，把 §5 的 `--dry-run` 铁律提到 agent 行为层面。
- 触发词中英双语——覆盖中文提需求与英文 "match lyrics" 等。
