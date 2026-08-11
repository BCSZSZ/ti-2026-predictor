# TI 2026 游戏内预测决策台

这是一个只在本机运行、可复现的 TI 2026 游戏内活动辅助工具。它覆盖：

- 小组赛 16 项预测；
- 主赛事 14 节点双败预测；
- 2026 新版 Fantasy（核心双人组、中单、辅助双人组、战旗与教练）；
- 规则、数据覆盖、时间泄漏和运行产物审计。

LLM 不参与最终数值结论。推荐由版本化规则、数据快照、统计模型和固定随机种子产生。

## 两种发布方式

### 1. 公开 Streamlit：仅手动输入

公开版入口是 [`streamlit_app.py`](streamlit_app.py)。玩家手动录入当前九格、同屏三个 Roll 选项和
剩余次数；页面返回唯一的一步建议、队伍组合与 Title 排名。它明确不包含：

- 截图或画面识别；
- Dota/Steam 控制和自动填写；
- 原始数据同步、规则抓取或下一轮选项猜测；
- 本机 `data/raw`、`data/processed` 或 `artifacts` 目录依赖。

云端使用内容寻址的冻结求解上下文
[`deploy/streamlit/frozen/manual-advisor-v1.json.zst`](deploy/streamlit/frozen/manual-advisor-v1.json.zst)，
数据截止为 `2026-08-10T13:45:12Z`。本地预览：

```powershell
uv sync --locked
uv run streamlit run streamlit_app.py
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
$ruleAsOf = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss'Z'")
uv run ti rules snapshot --as-of $ruleAsOf
uv run ti rules validate
uv run ti web
```

规则快照命令会读取本机 Dota 客户端；若 Dota 或 ValveResourceFormat CLI 不在默认位置，传入
`--dota-path` / `--vrf-cli`，或设置 `DOTA_PATH` / `VRF_CLI`。规则校验未通过时不要继续计算。
然后打开终端显示的 `http://127.0.0.1:8501`，进入 `Group Roll 实时顾问`。点击识别后切回完整
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
使用[方法极简速查](docs/reports/ti2026-methodology-quick-reference-2026-08-10.md)。本轮所有仍然有效的
玩家版 Markdown 已集中到
[TI 2026 玩家发布包](docs/publication/ti2026-release-bundle-2026-08-11/README.md)。

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
uv run ti web
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
本地页面现提供 `Group Roll 实时顾问`：默认保留原有下拉菜单手填，也可在 Windows 本机执行
一次性读屏。点击后，程序会核对 `dota2.exe` 并等待它所在显示器出现稳定的完整页面；Chrome
可以放在另一块屏幕，也可以与 Dota 同屏并用 Alt+Tab 切换。完整识别
九格、当前三个共享选项和剩余 Roll 后，
会自动填入本页并重新计算。页面给出唯一的一步建议、风险说明、当前三个位置的队伍组合及
自动 Title 排名。它直接使用
2026-08-10 的当前 P3/Title/Swiss 冻结证据，不依赖旧 P4/P5/P6 手册门禁；不会生成下一轮选项，
也不会向 Dota 发送鼠标、键盘或内存操作。每次识别完成后会自动停止；玩家在游戏内操作后，
需要再次点击识别按钮读取实际新画面。
真实数据冷启动约 40 秒，首次一步
计算约 0.6 秒，缓存重算约 0.05 秒。旧 P7 v1 会话与证据命令作为历史兼容证据保留，不再是
页面运行路径。实装范围和验收标准见
[v2 实装计划](docs/plans/current-screen-roll-advisor-v2.md)，完成结果见
[易懂总结](docs/reports/current-screen-roll-advisor-v2-implementation-2026-08-09.md)。
完整操作顺序、主赛事种子导入和状态含义见 [docs/runbook.md](docs/runbook.md)。模型的时间
切分、覆盖门槛和三种目标见 [docs/modeling.md](docs/modeling.md)。

## 本地实时 OCR（可选）

```powershell
uv sync --extra dev --extra ocr
uv run ti web
```

打开 `Group Roll 实时顾问`，点击“识别下一次稳定的 Dota 画面”，再切回完整 Roll 页面。
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
- 主赛事实际八队与种子未写入前，14 节点网格会生成但保持 `blocked`。
- Fantasy 默认只用覆盖充分的 `exact/derived` 字段；五项原生 replay 统计只有通过逐场状态、
  字段存在性和 Watcher build 门槛后才参与，OpenDota proxy 永不参与默认最优解。
- 实时 OCR 只在完整观测时自动填入本地顾问；任何不完整观测都会阻止自动计算。
