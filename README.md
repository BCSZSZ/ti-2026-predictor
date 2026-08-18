# TI 2026 游戏内预测决策台

[![GitHub Release](https://img.shields.io/github/v/release/BCSZSZ/ti-2026-predictor?display_name=tag)](https://github.com/BCSZSZ/ti-2026-predictor/releases/latest)

这是一个可复现的 TI 2026 游戏内活动辅助工具，提供公开 Streamlit 手填版和 Windows 本地
OCR 版。它覆盖：

- 小组赛 16 项预测；
- 主赛事 14 节点双败预测；
- 2026 新版 Fantasy（核心双人组、中单、辅助双人组、战旗与教练）；
- 规则、数据覆盖、时间泄漏和运行产物审计。

LLM 不参与最终数值结论。推荐由版本化规则、数据快照、统计模型和固定随机种子产生。

## v0.4.0：Main 终局 V1 / B1 / 10% 混合并列预测

- Main 仍有 Roll 时继续使用默认 G 或用户可选 G-Lite；Roll 用完后只需最终 15 格，不再要求
  客户端已经隐藏的三个选项。
- 终局同时运行 **V1 历史模板、B1 选手—定位条件生成、10% Series 限额混合**，分别显示队伍、
  期望、低迷 10% 与 Title。页面保留分歧，不平均、不多数投票。
- 公开 Streamlit 继续只允许手填；Windows 本地版额外支持终局截图。用户提供的原始截图已通过
  `46/46` 字段验收，正确得到 `remaining_rolls=0 / offer=null`。
- 三模型证据包约 `266.1 MiB`，只在第一次终局计算时从 GitHub Release 下载并校验；随后按内容
  哈希缓存。普通 G/G-Lite 不下载它。

完整算法、回溯与当前画面三套结果见
[Main 终局三模型发布报告](docs/reports/ti2026-main-parallel-fantasy-forecast-release-2026-08-19.md)。

## v0.3.1：Main Web 动态 Title 推荐

- 公开 Streamlit 手填版与 Windows 本地 OCR 版现在都会按当前 Core / Mid /
  Support 三队组合计算 Title，显示 Prefix / Suffix 前三、预计触发率与纸面加成。
- Title 证据已内嵌进同一个 actual 八队 Main 冻结求解包；云端不增加 OCR、
  原始数据或联网依赖。

## v0.3.0：actual 八队、最新 Fantasy 与 Main 玩家资料

- Main 当前发布已从 projected 16 队切换为 `ready / actual`：Core / Mid / Support 均只提供正式
  八队，并使用小组赛与突围赛后重建的 Main Fantasy Series pool。
- TI 已结束阶段在 Team-strength 与 Fantasy 两条证据通道中各自使用 1.5×；精确版本 7.41e 的
  1.5×、赛事级别和 60 天半衰期继续生效。
- 新增 [Main 30 Roll 玩家手册](docs/playbooks/main-roll/main-roll-publication-manual-v1.md)、
  [Main Stat 与队伍 Top 3 完整表](docs/playbooks/main-roll/stat-team-top3-publication-v1.md)和
  [Main Title 分析与推荐](docs/reports/ti2026-main-fantasy-title-recommendation-2026-08-17.md)。
- Streamlit 云端仍只手填；Windows 本地版仍额外提供 Main 15 格 OCR。两个入口现在共同读取
  actual 八队、`2026-08-16T15:31:30Z` 数据截止的内容寻址求解包。

## v0.2.0：Main 五格与 G/G-Lite（历史）

- 页面用独立 Tab 切换 `Main（当前 · 五格）` 与 `小组赛（历史 · 三格）`，两阶段不共享状态、
  OCR 或求解逻辑。
- Main 支持三面战旗各五格、三个共享 Roll 选项和 30 次 Roll。实际八队冻结前使用 16 支候选队，
  每个预测情景仍只让八队进入 Main，并显式标记为 `projected/provisional`。
- 默认策略是 `G`（只比较当前一步）；用户也可主动选择 `G-Lite`，仅在近似平手时执行固定预算的
  有限二步抽样。G-Lite 当前只有开发阶段正向证据，不替代默认 G，也不宣称全局最优。
- 公开 Streamlit 只允许手动录入；Windows 本地版在相同手填与求解功能之上，额外提供 Main
  15 格和小组赛九格的一次性画面识别。两个版本都不会控制 Dota 或自动提交选择。

完整变更见 [v0.2.0 Release](https://github.com/BCSZSZ/ti-2026-predictor/releases/tag/v0.2.0)。

## 两种发布方式

| 能力 | 公开 Streamlit | Windows 本地版 |
| --- | --- | --- |
| Main 五格 / 小组赛三格手填 | 支持 | 支持 |
| G / G-Lite 分析 | 支持 | 支持 |
| 0 Roll 时 V1 / B1 / 10% 混合并列预测 | 支持 | 支持 |
| 按当前三队动态推荐 Title | 支持 | 支持 |
| Dota 画面识别 | 不提供 | 支持 Main 15 格与小组赛九格 |
| 控制客户端或自动填写 | 不提供 | 不提供 |

### 1. 公开 Streamlit：仅手动输入

公开版入口是 [`streamlit_app.py`](streamlit_app.py)。玩家在 Main/小组赛 Tab 手动录入当前
15/9 格、有 Roll 时的同屏三个选项和剩余次数；页面返回当前动作建议、队伍组合与 Title 排名。
Main 终局只填 15 格，并显示三套独立 Forecast。它明确
不包含：

- 截图或画面识别；
- Dota/Steam 控制和自动填写；
- 原始数据同步、规则抓取或完整未来路线搜索（可选 G-Lite 仅做冻结的受限下一轮抽样）；
- 本机 `data/raw`、`data/processed` 或 `artifacts` 目录依赖。

云端分别使用 [`deploy/runtime/current.json`](deploy/runtime/current.json) 和
[`deploy/runtime/main-current.json`](deploy/runtime/main-current.json) 指向的内容寻址
**冻结求解发布包**。Group 历史包截止 `2026-08-10T13:45:12Z`；Main 当前包截止
`2026-08-16T15:31:30Z`，为 `ready / actual` 八队。发布包只含求解所需的紧凑派生证据，
不含也不会下载约 188 GB 的原始数据。终局三模型另由
[`deploy/runtime/main-forecast-current.json`](deploy/runtime/main-forecast-current.json) 指向约
`266.1 MiB` 的 GitHub Release 派生证据包；它不是原始数据，只在首次终局求解时下载。本地手动预览：

```powershell
uv sync --locked
uv run ti web --manual
```

Streamlit Community Cloud 选择本仓库、Python 3.12，并把 Main file path 设为
`streamlit_app.py`；项目根目录的 `uv.lock` 是唯一依赖锁文件，不需要 secrets 或
`packages.txt`。完整部署与快照更新流程见
[`deploy/streamlit/README.md`](deploy/streamlit/README.md)。

### 2. GitHub 仓库：Windows 本地 OCR

画面识别是可选的 Windows 本地能力，不进入公开 Streamlit。推荐安装步骤：

```powershell
winget install --id=astral-sh.uv -e
git clone https://github.com/BCSZSZ/ti-2026-predictor.git
Set-Location ti-2026-predictor
uv python install 3.12
uv sync --locked --extra ocr
uv run ti web
```

打开终端显示的 `http://127.0.0.1:8501`。这个用户入口与公开手动版读取同一个冻结求解发布包，
不需要规则快照、ValveResourceFormat、OpenDota、`data/` 或 `artifacts/`。点击识别后切回完整
Dota Roll 页面；程序只读窗口画面，确认一个稳定页面后自动停止。它不会保存 Steam 凭据、控制
鼠标键盘或提交游戏内选择。OCR 截图与识别 JSON 只写入被 Git 忽略的本机
`data/cache/ocr/live-roll/`。

开发者需要测试工具时使用：

```powershell
uv sync --locked --extra dev --extra ocr
uv run pytest
```

uv 的官方安装入口见 [Astral uv Installation](https://docs.astral.sh/uv/getting-started/installation/)；
`uv sync --locked` 会拒绝过期锁文件，避免安装时静默改变依赖集合。

梦幻挑战与赛事预测共同使用的数据基础、分析方法、证据等级、复现身份和可信边界，统一见
[TI 2026 当前方法与证据权威性报告](docs/reports/ti2026-methodology-and-evidence-authority-report-2026-08-10.md)。
当前 7.41e 1.5 倍权重的完整公式与适用范围另见
[统一加权方式](docs/reports/ti2026-weighting-policy-2026-08-10.md)。
它逐项区分 Valve/客户端事实、`exact`/`derived` 观测、模型推断和仍未闭合的草案，不把
`publishable` 误写成“预测一定正确”；[首轮与 LGD 实装、重算及验收记录](docs/reports/ti2026-swiss-round1-roster-update-2026-08-10.md)
保存本阶段的正式运行和数学闭合检查；只想看数据来源、计分、平均分与 Series 时，
使用[方法极简速查](docs/reports/ti2026-methodology-quick-reference-2026-08-10.md)。当前 Main Event
玩家版已集中到
[TI 2026 Main Event 玩家发布包](docs/publication/ti2026-release-bundle-2026-08-17/README.md)；
[2026-08-11 Group 发布包](docs/publication/ti2026-release-bundle-2026-08-11/README.md)保持为小组赛阶段
的冻结历史版本。

## Main Event 当前版本

当前实际八队、官方直播首轮、1.5× 已结束 TI 阶段权重、完整双败网格、Fantasy 通用基准和
Main 五格求解发布见
[Main Event 完整报告](docs/reports/ti2026-main-event-publication-2026-08-17.md)。模型枚举
`16,384` 个合法双败网格后，期望积分、Top-10 和 Top-100 代理目标均推荐 **TEAM VISION
冠军**；完整路径已改为可缩放的[双败淘汰赛树状图](docs/assets/ti2026-main-event-double-elimination-bracket-2026-08-17.svg)。
[Main 概率参考](docs/reports/ti2026-main-probability-reference-2026-08-17.md)另列八队完整
Elo/Glicko 对位表、随机乱填与模型网格的数学期望，以及 G/G-Lite 所用的全部 Roll 分布与
来源可信度。

Main 五格运行时为 `ready / actual`，Core / Mid / Support 各有 8 个实际参赛队候选。Web 默认
使用 G，也允许用户主动选择 G-Lite；Streamlit 云端只接受手动 15 格录入，本地版另外保留截图
识别。Roll 用完后两端都显示 V1 / B1 / 10% 混合三套终局结果。Main 锁定时间为
`2026-08-20T02:00:00Z`。当前 Stat、Title 和逐 Roll 使用说明集中在
[Main Fantasy 玩家资料](docs/playbooks/main-roll/README.md)。

## Group 冻结历史版本

当前面向玩家的小组赛结论见
[TI 2026 瑞士轮 Forecast：16 队身份归一与 LGD 0.60 主情景](docs/reports/ti2026-group-forecast-publication-2026-08-10.md)。
它使用 Valve 官方首轮和规则驱动的五轮 Swiss 模拟，给出 BO3 胜率、16 槽类别概率以及
**期望正确 5.1561 / 16（最终期望正确比例 32.23%）**；正式模型在 TI 2025 的 144 局留出集上命中率为
56.25%，所以不把微弱优势包装成确定答案。
[赛事档位与奖金易懂总结](docs/reports/ti2026-group-event-tier-prize-summary-2026-08-08.md)单独说明
当前 7.41 赛事的社区 Tier、总奖金和资格赛缺失值该怎样理解，
[7.41 系列赛证据展开](docs/reports/ti2026-group-current-patch-series-evidence-2026-08-08.md)列出
每队汇总、精确小版本、社区赛事档位、赛事总奖金、最终名次、关键直接交手和当前版本全部完整系列赛，
[生成与验收记录](docs/reports/ti2026-group-forecast-publication-implementation-2026-08-08.md)保存运行、
失败门禁、数值追溯与项目级审查；[系列赛证据 v3 实施记录](docs/reports/ti2026-group-series-evidence-v3-implementation-2026-08-08.md)
单独保存赛事档位、奖金、资格赛缺失值语义及这次发布增强的验收。

## 16 队身份处理

- 当前 16 队逐项审计确认四个博彩品牌相关展示别名：BoomBoys/BetBoom、TEAM VISION/PARIVISION、
  HULIGANI/L1GA、Iron Wing/1win；另有 Team Resilience、Xtreme Gaming 与 LGD Gaming 的赛事
  临时注册 ID。
- 正式模型不按队名字符串猜测。当前配置使用 **9 条带有效期的 identity bridge**，在冻结比赛中
  映射 **203 场不同比赛**；原始比赛与 raw team ID 全部保留。
- `10150413 Iron Wing` 只从 `2026-06-01T00:00:00Z` 起承认当前身份，排除此前 24 场 Tundra
  阶段比赛；`5017210 Team Resilience` 也有防止历史 ID 复用的身份窗口。
- `8291895 Tundra`、`9303484 HEROIC` 和无关同名 BoomBoys 明确不合并。阵容连续性不能跨越真实
  组织转会边界。

完整证据、每条映射的有效期和反例见
[16 队身份审计](docs/research/ti2026-team-display-alias-audit-2026-08-11.md)、
[VISION 专项审计](docs/research/ti2026-yandex-liquid-vision-rating-audit-2026-08-11.md)与
[当前赛事报告](docs/reports/ti2026-group-forecast-publication-2026-08-10.md)。

## LGD 阵容变更处理

- 本机 Dota 客户端 TI 事件名单确认 TaiLung 已无效、Topson `94054712` 为 LGD 当前有效中单；
  阵容使用半开生效区间，不把新阵容回填到更早比赛。
- 赛事 Forecast 不把绝对 Elo/Glicko rating 直接乘 0.60，而是在未来 BO3 对局中将 LGD 的模型
  胜算 odds 乘 **0.60**。这是正式下行情景；同时保留 `1.00`、`0.90`、`0.75` 及不同选对手策略
  作为敏感性。Falcons–LGD 的未调整概率为 65.02%–34.98%，应用 0.60 胜算乘数后为
  **75.65%–24.35%**。
- Fantasy 不为 Topson 编造分数。虽然公开数据存在 14 局 7.41c/d，但当前正式
  `premium/professional` 口径下合格完整 Series 为 0，因此 **LGD 中单不可选**；LGD 核心位和
  辅助位仍可选。缺失保持 `unavailable/null`，不填 0，也不继承 TaiLung 数据。
- LGD 公告只公开称“赛事诚信信息”和禁赛安排，没有公开确认具体假赛事实；本项目不扩大表述。

完整证据与判断见[调查记录](docs/research/ti2026-swiss-round1-lgd-roster-2026-08-10.md)和
[当前方法报告](docs/reports/ti2026-methodology-and-evidence-authority-report-2026-08-10.md)。

## 快速开始

```powershell
uv sync --extra dev
uv run ti rules validate
uv run ti forecast group --as-of 2026-08-10T13:45:12Z --profile all --samples 100000 --sensitivity-samples 20000 --seed 20260813
uv run ti fantasy recommend --as-of 2026-08-10T13:45:12Z --period group --profile all
uv run ti fantasy group-evidence --as-of 2026-08-10T13:45:12Z --seed 20260813 --bootstrap --team-rank-bootstrap
uv run ti fantasy group-playbook-evidence --as-of 2026-08-06T17:27:00Z --playbook-version v2
uv run ti fantasy group-cross-audit --as-of 2026-08-06T17:27:00Z --cross-audit-version v2
uv run ti fantasy group-advisor-evidence --as-of 2026-08-06T08:15:00Z
uv run ti fantasy main-publication-evidence --as-of 2026-08-16T15:31:30Z --hero-source data/raw/rules-title/20260810T134512Z-7d89d1a71895/scripts/npc/npc_heroes.txt
uv run ti dev web
```

默认网页只监听 `127.0.0.1`。首次同步会访问 OpenDota；测试永远不访问实时 API。
数据同步默认分页获取 `as_of` 所在 UTC 年份的 OpenDota 职业比赛目录，并关联游戏版本与
OpenDota 赛事级别。Web 可按时间、版本和赛事级别过滤。同步还会补齐当前 16 队每队最近
20 场逐场详情，并按 `match_id` 断点续传；可用 `--team-detail-limit 0` 只保留比赛摘要。

付费 OpenDota key 只放在已被 Git 忽略的 `.env`，由 `uv run --env-file .env` 注入。客户端按
`$5/月 = 50,000 次`设置带 key 请求尝试的本地硬上限，并对单次运行上限、重复成功请求和有限
递增重试作统一保护；详见 [OpenDota API 使用计划与安全规范](docs/opendota-api-usage.md)。

Fantasy 的正式历史范围按当前 TI 名单中的稳定玩家 ID 选择，并包含他们在旧战队参加的
`premium/professional` 比赛。首次全量或后续增量同步使用：

```powershell
uv run ti data fantasy-history --as-of 2026-08-01T15:00:00Z --year 2026
```

该命令逐个请求、遵守 OpenDota 响应中的限额、每批落盘并可断点续传；它不会请求 `.dem`
或自动提交 replay 解析任务。五项 replay 原生统计需要 Java 21+，并使用独立的可恢复步骤：

```powershell
Push-Location src/ti_replay_parser
.\mvnw.cmd -q '-DskipTests' package
Pop-Location
uv run ti data replay-fantasy --as-of 2026-08-01T15:00:00Z --year 2026 --workers 4
```

它下载并保存不可变的 Valve replay，解析 Madstone、Smoke、Watcher、Lotus 与 Tormentor
逐人原生计数，并把旧 OpenDota event-map 值隔离到诊断表。命令默认复用已验证检查点；
缺失 replay、缺失字段，以及未获准 build 的 Watcher 保持 `null/unavailable`，绝不以 proxy 或
getter 默认零回填。数据表、状态和历史回填结果见
[Fantasy 覆盖契约](docs/fantasy-coverage.md)与
[P1 实装报告](docs/reports/p1-native-replay-stats-implementation-2026-08-06.md)。

`fantasy_performance_samples.parquet` 中一行表示“一名玩家在一局比赛中的表现”，只是
Fantasy 模型的历史输入。三张定位卡片、徽标、教练及重选策略才是 Fantasy 推荐结果。

`fantasy group-evidence` 是 P3 的 Group 专用证据入口：它用完整 Series 块、8,192 个公共情景
和 400 次 Series 分组重采样生成可复现的 Stat 表及终局估值哈希；它不是人工手册或重随求解器。
可选的 `--team-rank-bootstrap` 会再为 42 个位置/颜色/Stat 组生成当前可用队伍的排名记录和
可读 Top 3 附表。默认关闭以保持冻结 v2 schema 与哈希兼容；发布版以“平均分、低迷分、
样本、落后第一、第一稳定率、前三稳定率”呈现，稳定率不是未来真实排名概率。正式附表见
[v4 Stat 队伍 Top 3 发布版](docs/playbooks/group-roll/stat-team-top3-publication-v4.md)。当前核心位和
辅助位各 16 队，中单因 LGD 不可用而为 15 队，共 47 个队伍×位置池。
两版 v2 人工手册、完整 Stat/Quality/Trait 表、最终证据包和当前发布状态见
[Group Roll 手册索引](docs/playbooks/group-roll/README.md)。v2 standalone 在约 25 分钟内完成，
完整 held-out 只读交叉审计在约 45 分钟内完成 108/108；二者合计约 70 分钟，不需要再追加
15 小时分析。两版仍为 `draft`：Primary 没有 standalone 10% Common 失败，但有五条核心规则、
两个风险修正失败，并在只读审计新增一个方向性反例；Rate 有 23 个 standalone 10% Common
失败。最终结论见
[易懂总结](docs/reports/group-roll-playbook-v2-summary-2026-08-07.md)。

面向玩家直接查阅的保守版本见
[Group 40 Roll 玩家手册（2026-08-10 阵容更新版）](docs/playbooks/group-roll/group-roll-publication-manual-v4.md)：
它用易懂语言说明 Roll 机制，并按证据确定度排列规则，不把仍为 `draft` 的两本候选包装成
可靠或全局最优策略。

v2 没有新跑 full-session P5 solver。历史 v1 P5 仍是
`failed-escalation-review-required`，只作为失败的诊断证据保留，不会自动启用更复杂的 full
planner。v1 手册、P5/P6 产物和默认 CLI 路径继续作为不可变兼容证据保留。
本地页面直接运行 `uv run ti web` 即可模拟 Fantasy；启动时会自动验证并选择 Group 与 Main 的
当前发布指针，不需要玩家运行 `main-solver-release`。页面提供 `Fantasy Roll 实时顾问`，画面上用
两个 Tab 切换 `Main（当前 · 五格）` 与
`小组赛（历史 · 三格）`。两边分别使用状态、OCR、求解和发布栈，不共享阶段业务逻辑。默认
Main 可手填三面共 15 枚 Emblem，也可在 Windows 本机执行一次性读屏；Group 历史 Tab 保留
原有九格手填和读屏。点击后，程序会核对 `dota2.exe` 并等待它所在显示器出现稳定的完整页面；
Chrome 可以放在另一块屏幕，也可以与 Dota 同屏并用 Alt+Tab 切换。完整识别当前阶段的全部
15/9 格、三个共享选项和剩余 Roll 后，
会自动填入本页并重新计算。Main 默认使用 `G`（只看当前一步），也允许玩家主动切换到
`G-Lite`：后者只在前两项足够接近时，用固定 4 个样本做一次有限二步比较，每局最多触发
4 次。`G-Lite` 仅有 100 个合成开发状态的正向点估计，尚未完成独立 confirmation，因此不替代
默认 `G`。Main 页面给出当前动作建议、风险说明和三个位置的 actual 八队匹配，并按当前三队
动态重算 Title 前三。Title 是 Roll 之外的免费建议，尚未与五格终局联合优化；Group 历史
页面继续显示其冻结 Title 排名。Main 逐 Roll 使用 `2026-08-16T15:31:30Z` 的赛后 pool；只有用户
选择 `G-Lite` 且触发
近似平手条件时才生成受限的下一轮样本。程序不会向 Dota 发送鼠标、键盘或内存操作。每次识别
完成后会自动停止；玩家在游戏内操作后，需要再次点击识别按钮读取实际新画面。
两个玩家入口都直接加载仓库内按阶段冻结的求解发布包，不再执行约 40 秒的真实数据冷启动。
Main 现在已经完成赛后数据、actual 八队和正式种子更新：候选列表为 8 队，每个情景均从同一
八队生成完整双败路径，指针明确显示 `ready / actual`。此前 16 队 projected 包只保留为历史
证据，不再是玩家页面运行路径。一步计算仍约 0.6 秒，缓存重算约 0.05 秒。旧 P7 v1 会话与证据
命令作为历史兼容证据保留。实装范围和验收标准见
[v2 实装计划](docs/plans/current-screen-roll-advisor-v2.md)，完成结果见
[易懂总结](docs/reports/current-screen-roll-advisor-v2-implementation-2026-08-09.md)。
完整操作顺序、主赛事种子导入和状态含义见 [docs/runbook.md](docs/runbook.md)。模型的时间
切分、覆盖门槛和三种目标见 [docs/modeling.md](docs/modeling.md)。

## 本地实时 OCR（可选）

```powershell
uv sync --locked --extra ocr
uv run ti web
```

打开 `Fantasy Roll 实时顾问`，先选择 Main 或小组赛 Tab，再点击该阶段的单次识别按钮并切回
完整 Roll 页面。
完整且可信的屏幕观测会自动写入本页并计算；缺失、冲突或低置信度字段只会填入已确认部分，
不会触发计算。识别到一个目标页面后会自动停止，也可在等待时手动取消。程序按 `dota2.exe`
的 Windows 显示器句柄选择画面，不要求浏览器与游戏分处两屏；单屏可以点击后用 Alt+Tab 切回
Dota。Dota 最小化、尚未切回或不在完整 Roll 页面时只会继续等待，不会读取 Chrome 来填表。
当前语言顺序固定为英文优先，同时支持简体中文客户端；角色、Stat、品质、Trait、Roll 操作和
剩余次数均使用对应的客户端词表识别。
截图与识别 JSON 只覆盖写入本机忽略目录 `data/cache/ocr/live-roll/`。手填始终可用。
一次性识别按钮只在本机 Windows 显示；Linux/托管环境保持原始手填页面。
旧的 `ti ocr inspect <截图>` 仍只生成待确认草稿。两条路径都不控制 Steam，也不会自动提交
游戏内选择。

本轮实装结果与已知校准缺口见
[技术报告](docs/reports/local-live-group-roll-ocr-implementation-2026-08-09.md)；直接使用时可看
[易懂总结](docs/reports/local-live-group-roll-ocr-summary-2026-08-09.md)。

## 数据与发布状态

- 原始响应、抓取元数据和哈希保存在 `data/raw/`。
- 规范化 Parquet 和 DuckDB 保存在 `data/processed/` 与 `data/ti.duckdb`。
- 每次推荐写入 `artifacts/<run_id>/`，包括输入哈希、Git 版本、模型参数、随机种子和审计结论。
- 当规则、阵容或关键数据覆盖不满足要求时，结果状态为 `blocked`，不能作为可发布推荐。

## 当前边界

- 2026 首轮已经按 Valve 官方节点冻结，五轮 Swiss 规则已经进入可哈希模拟器；A/B 归属仍由
  `.A/.B` 节点名与组内规则派生，后续非唯一合法配对、选对手、平均时长和掷币继续保留 warning。
- 9 条身份桥和 2 个 registration identity window 只在稳定选手 ID、时间区间与冻结证据共同支持时
  生效；名称相似本身不足以合并，未来超出生效区间的比赛不会自动继承。
- LGD `0.60` 是显式 roster-shock 情景而非已验证效应量；Fantasy 的 LGD 中单保持不可用，不以
  0 分或旧中单历史填补。
- 主赛事实际八队与官方直播首轮已写入；若后续客户端结构化槽位与直播转录冲突，必须重新生成，
  不得静默沿用当前网格。
- Fantasy 默认只用覆盖充分的 `exact/derived` 字段；五项原生 replay 统计只有通过逐场状态、
  字段存在性和 Watcher build 门槛后才参与，OpenDota proxy 永不参与默认最优解。
- 实时 OCR 只在完整观测时自动填入本地顾问；任何不完整观测都会阻止自动计算。
