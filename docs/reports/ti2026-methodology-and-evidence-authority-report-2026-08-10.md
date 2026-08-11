# TI 2026 当前方法与证据权威性报告（2026-08-10）

本文是 `2026-08-10T13:45:12Z` 冻结后的当前入口。旧版报告继续承担历史复现，不应再作为本次
首轮、LGD 阵容或 Fantasy 候选范围的当前说明。

## 一页结论

| 产品 | 当前状态 | 最可靠内容 | 必须保留的边界 |
| --- | --- | --- | --- |
| 赛事 Forecast | `warning` | 官方首轮、五轮 Swiss 约束、BO3 留出选择、固定种子联合模拟 | 后续合法配对和选对手不唯一；LGD `0.60` 是情景参数 |
| 16 槽 InGamePrediction | `warning` | 固定容量下联合选择、百分率、期望正确数与分布闭合 | 不是官方答案；`top_10/top_100` 总体阈值仍是代理 |
| Fantasy Stat / Team Top 3 | `warning` | 47 个合格队伍×位置 Series 池、精确/派生 Stat、400 次分组重采样 | LGD 中单不可用；排名稳定率不是未来命中概率 |
| Fantasy Title | 可公开的中等确定度纸面建议 | 当前客户端英雄分类、47 个池的触发率、冲突条件排除 | 不是完整 P3 终局联合优化 |
| Group Roll 手册 | 保守公开说明，完整候选仍为 `draft` | 客户端机制、Stat/Quality/Trait 算术、已冻结规则证据 | 本轮只更新查表与候选池，没有重跑完整 70 分钟交叉审计 |

当前赛事主结果为 **期望正确 5.1561 / 16（32.23%）**。Fantasy 当前有 **47 / 48** 个
队伍×位置池可用，唯一不可用的是 LGD 中单。

## 术语和来源优先级

- **InGamePrediction / 游戏内预测**：玩家在 Valve 活动中实际填写的槽位。
- **Forecast / 模型预测**：本项目在固定 `as_of` 下产生的概率分布。
- **Game / 单局**：一张 Dota 地图。
- **Series / 系列赛**：BO1/BO2/BO3/BO5 的一次完整交手。

规则证据依次采用：本机当前 Dota 客户端与 Valve 公告；Valve/官方或开源 API 和源代码；最后才是
社区资料。社区 Tier、奖金和名次只提供背景，不进入模型权重。

## 冻结身份

| 项目 | 当前值 |
| --- | --- |
| 统一 UTC `as_of` | `2026-08-10T13:45:12Z` |
| Group run | `group-4cfa61a8f4a47746` |
| Fantasy Stat P3 run | `fantasy-8b0113b26a7da1c7` |
| 当前顾问 P3 run | `fantasy-5ea8bdfd5fb528cb` |
| Title run | `fantasy-b2240b141540675d` |
| Rule snapshot | `20260810T134439Z-f26cfd47ab1d` |
| Tournament manifest SHA-256 | `cf527bc9953edb1908be6a9531ec7579322e581a8db9cd3799cd8ba62c42722c` |
| Team identity bridge config SHA-256 | `dae7f5b08604a9082661db5034e7f359546950145c21021d3effb0af8201f0bb` |
| Registration identity config SHA-256 | `624ec8492a84eacd2849e823e98bfd23eb5c0a82b07e8afa4a59a57a8c058cd4` |
| Swiss 格式 SHA-256 | `b505473a35522df6d8f56de14d1b1eea945bb4d5089855a448b1c4be3f7db7c6` |
| Swiss 策略 SHA-256 | `245f046b3b0c1d02e2ee9bf6034cdf5e8c9682e3366487a0e306eef8bd9d40c5` |
| Fantasy Stat evidence SHA-256 | `1319be5a19029c04ec16496ad49b90807dda31b596492e580c84f986fac328b4` |
| Fantasy data snapshot SHA-256 | `9208c15c173b7ee0fc05b0e04cc9e89f5aac8d78c1a2b4905d550e2abaf4bc7b` |
| Fantasy scenario SHA-256 | `f1c869662b3bf1f170ac68b843beb90a866c5bf4e46facf1047ecd95de7b7f8c` |
| Fantasy pool set SHA-256 | `6a01d321a8956211ebeb27a0537e8a311b7d6d6c6d90fb15843715901d2ed72d` |
| Title evidence SHA-256 | `03cde760c24316030d83af0d6b92b999f1a9deb8292c34001dea41f96ca90da6` |

原始响应不可覆盖；Valve league/rules、客户端资源和抓取元数据保存在 `data/raw/`，运行产物保存在
被 Git 忽略的 `artifacts/`。同一快照、配置和种子必须生成相同的推荐 JSON 或 evidence hash。

## 16 队身份规范化

16 队逐项审计确认四个博彩品牌相关展示别名：BoomBoys/BetBoom、TEAM VISION/PARIVISION、
HULIGANI/L1GA、Iron Wing/1win。BoomBoys 的 Valve 稳定 ID 已一致；其他显示身份与赛事临时
注册身份使用带证据时点和生效区间的 bridge。当前共 9 条：

- `9824702 → 9572001`；
- `10182357 → 10150413`；
- `9303383 / 10182299 / 10208009 → 10149530`；
- `9316703 / 10207984 → 5017210`；
- `10208071 → 8261500`；
- `10208068 → 10150538`。

冻结比赛中共映射 **203 场不同比赛**。此外，bridge 只能处理“另一 raw ID 属于谁”，不能防止
canonical ID 本身被旧身份复用，因此配置还包含两个 registration identity window：

- `10150413 Iron Wing` 从 `2026-06-01T00:00:00Z` 起生效，排除 24 场转会前 Tundra 比赛；
- `5017210 Team Resilience` 从 `2026-04-08T09:08:01Z` 起生效，阻止早年无关 ID 复用进入当前路径。

共同实现约束是：

- 原始 parquet 与原始 team ID 不改写；模型入口另存 raw ID、bridge ID 和映射审计；
- `evidence_as_of` 与有效区间共同防止证据泄漏到更早运行，也防止未来比赛自动无限继承；
- `8291895 Tundra`、`9303484 HEROIC` 和无关同名 BoomBoys 明确不合并。

全比赛网络重放后，TEAM VISION、Iron Wing、HULIGANI 的综合强度分别为 `1754.5 / 1643.0 /
1487.0`。这属于补齐已存在的比赛证据并应用真实转会边界，不是把奖金、名次或人工加分写入
Elo/Glicko。完整 16 队表和一手证据见
[身份审计](../research/ti2026-team-display-alias-audit-2026-08-11.md)。

## 赛事强度模型

历史 Game 证据权重为：

`大版本权重 × 当前精确版本倍率 × 赛事目录等级权重 × 2^(-距 as_of 天数/60)`

当前 7.41 权重 1.00，7.41e 在其上再乘 1.50，7.40 权重 0.15；OpenDota
`premium/professional` 分别为 1.00/0.75，其他等级为 0。模型只保留与 16 支目标队连通的正权重
比赛网络，用 Elo/Glicko 各 50% 形成概率。滚动验证没有接受 isotonic 校准，因此部署概率保持
未校准并公开 warning。

TI 2025 的 144 局赛事留出结果：

| 模型 | 命中率 | Brier | log loss |
| --- | ---: | ---: | ---: |
| 50% 基线 | 45.14% | 0.250000 | 0.693147 |
| 当前部署模型 | 56.25% | 0.244712 | 0.682552 |

命中率高于随机方向判断，但优势有限，不支持把 51% 与 55% 的差别说成确定性结论。

## BO3 概率选择

同一个底层概率可以直接解释为 Series 概率，也可以假设每局独立后合成 BO3。项目在 TI 2025
57 个结构完整 BO3 上预先比较：

| 方案 | 命中率 | Brier | log loss |
| --- | ---: | ---: | ---: |
| 直接 Series | 57.89% | **0.235022** | **0.661459** |
| 独立 Game 合成 | 57.89% | 0.240991 | 0.674950 |

直接 Series 同时取得更低 Brier 和 log loss，因此正式胜负采用它。2–0/2–1 局分只用于排名
tiebreak，并从直接 Series 概率反解一个单局代理；输出明确标为 `scoreline proxy`。

## 官方 Swiss 规则怎样进入模型

首轮 8 个 BO3 节点来自 Valve `GetLeagueData`。官方规则明确：

1. 同战绩队相配，尽量避免重赛并尽量缩小排名距离；
2. 第 1 轮在两个初始组内使用赛事方对阵；
3. 第 2、3 轮只能匹配初始同组队伍；
4. 第 4 轮只能匹配另一个初始组的队伍；
5. 第 5 轮的负者淘汰局最大化排名距离；
6. 最好的 3–2 队依次从尚未被选择的 2–3 队中选择淘汰轮对手。

排名依次比较 Series 胜负、对手总胜场、Game 胜率、对手平均 Game 胜率、平均时长和掷币。
模拟器生成实际逐轮对阵、BO3 局分与排名，并保证六类容量严格为 `1 / 2 / 5 / 5 / 2 / 1`。

规则仍包含“尽量”和主动选择，因此不能仅凭胜负记录确定唯一后续赛程。正式策略使用最小排名
距离、固定种子 tie-break 和 `model_optimal` 选对手；另有随机与对抗性选择敏感性。平均时长使用
截断正态代理，最终掷币使用固定种子代理。

## LGD 阵容变化

客户端 build `6893:10895878` 的 TI 事件名单把 TaiLung 标为无效、Topson
`account_id=94054712` 标为 LGD 当前有效中单。阵容记录使用半开区间：TaiLung 在变更时刻结束，
Topson 从该时刻开始，不回填到历史比赛。

LGD 官方公告只公开称“赛事诚信信息”、赛事方禁赛及 PGL 处罚转述，没有披露具体比赛、证据、
下注或故意输局。因此发布版不把“假赛”作为已证实事实。

### 赛事 Forecast

绝对 Elo/Glicko rating 有任意原点，直接把 rating 乘 `0.60` 会依赖量表。项目改为在每场未来
对局进入 BO3 处理前，把 LGD 的正胜算 odds 乘 `0.60`：

- `1.00`：无阵容冲击基线；
- `0.90`：较轻冲击敏感性；
- `0.75`：中度冲击敏感性；
- `0.60`：正式主情景。

它不修改历史 rating 或比赛权重。LGD 在 `1.00 / 0.90 / 0.75 / 0.60` 下的晋级率依次为
**35.28% / 31.31% / 24.05% / 17.35%**，方向与冲击强度一致。`0.60` 是负责人确认的显式
风险假设，不是一手事实或回测得出的自然常数。

例如 Falcons–LGD 的阵容冲击前 LGD 概率为 `34.9120%`，原胜算为 `0.536381`；乘 `0.60` 后
胜算为 `0.321829`，换回概率得到 **24.3472%**。因此 `0.60` 是胜算乘数，不是把胜率机械减去
40 个百分点。

### Fantasy

Topson 在公开数据中有 14 局 7.41c/d，但属于未分类或 OpenDota `excluded` 的公开预选赛；当前
Fantasy 历史政策只接受 `premium/professional`，所以正式合格完整 Series 为 0。

- LGD 中单保持 `unavailable/null`，从中单候选排除；
- LGD 核心位有 54 个、辅助位有 61 个合格完整 Series，继续可选；
- 不把 TaiLung 的历史转移给 Topson；
- 不把缺失写成 0；
- 不把赛事 odds `×0.60` 机械应用到每项 Fantasy Stat；只让重算后的预计 Series 机会数进入
  Group Fantasy 估值。

## Fantasy P3 与 Stat 表

正式 P3 使用 8,192 个公共情景和 400 次完整 Series 分组重采样。每个可用队伍×位置池必须至少
有 10 个结构完整 BO2/BO3，且所需 Stat 的 provenance 为 `exact/derived`。Core/Support 以稳定
二人组为单位，Mid 以单一稳定 ID 为单位；历史样本跟随选手 ID，可包含其共同效力旧队的比赛。

当前 47 个池可用、1 个不可用。Stat Top 3 的“第一稳定率/前三稳定率”表示分组重采样后排名仍然
保持的频率，不是未来比赛的真实概率。三格战旗最终仍必须共同匹配同一队，不能把三张单 Stat 表
的第一名拼成一面战旗。

## Title 与 Roll

Title 当前中性默认仍为 **Cerulean + the Clutch**。Prefix 汇总 47 个可用池，依赖最终阵容；
Suffix 的 Clutch 在 34/47 个池中为纸面第一。两个一血 Title 存在客户端条件冲突，Own-fountain
死亡缺少受治理事件位置证据，均不进入默认排名。

Title 的纸面加成是地图触发率乘客户端显示 bonus，不等于完整 Period 最终增幅。P3 仍没有把
Title 与全部战旗、未来 Series 和最终取最高分规则做完整联合优化，Coach 状态仍为
`unavailable_excluded`。

Roll 手册的 S/A 层机制与查表已更新到当前证据；B/C/D 层仍引用冻结的 v2 验证。本轮没有用新
阵容暗中改写已失败或仍为 draft 的整局规则门禁。实时顾问读取同一 v2 Fantasy/Swiss 冻结，手动
队伍下拉按位置过滤：LGD 只从中单消失。

## 当前 warning 与禁止的表述

- 可以说“Valve 官方首轮 + 规则驱动 Swiss 情景”；不能说“已预知后续唯一对阵”。
- 可以说“LGD 0.60 odds 下行情景”；不能说“模型证明 LGD 胜率下降恰好 40%”。
- 可以说“Topson 当前正式 Fantasy 样本不可用”；不能说“Topson 没有任何 7.41 比赛”或“0 分”。
- 可以引用 LGD 公告的“赛事诚信信息”；不能把未公开细节写成已证实假赛事实。
- 可以说“经稳定选手 ID 与时间区间核验后，9 条 bridge 映射 203 场不同比赛”；不能说“名称
  相似的 ID 都应自动合并”，也不能把转会前 Tundra/HEROIC 历史归给新组织。
- 可以报告期望正确 `5.1561 / 16 = 32.23%`；不能说“一定答对 5 个”。
- 可以报告 BO3 Series 胜率；局分代理必须继续标为 proxy。

## 复算与测试

```powershell
uv run ti forecast group --as-of 2026-08-10T13:45:12Z --profile all --samples 100000 --sensitivity-samples 20000 --seed 20260813
uv run ti fantasy group-evidence --as-of 2026-08-10T13:45:12Z --seed 20260813 --bootstrap --team-rank-bootstrap
uv run ti fantasy title-evidence --as-of 2026-08-10T13:45:12Z --hero-source <npc_heroes.txt> --client-build 6893:10895878 --seed 20260808
uv run ti audit group-4cfa61a8f4a47746
uv run ti audit fantasy-8b0113b26a7da1c7
```

2026-08-11 的 16 队身份修复 + 0.60 重建覆盖身份桥的半开区间与未来证据门禁、registration
identity window、原始 ID 保留、映射有效权重、Title 动态池数、
发布清单和链接、LGD 分位置可用性、odds 变换与 Swiss 概率缓存；Group Fantasy
evidence/Scenario 已更新到本报告列出的新哈希，Title evidence 因输入不受 Swiss 情景影响而保持
不变。顾问只读加载新 P3 的端到端回归通过，仍为 47 个可用池。

## 官方与本地研究入口

- [Valve TI 2026 schedule](https://www.dota2.com/esports/ti15/schedule)
- [Valve GetLeagueData, league 19719](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719)
- [Valve TI 2026 rules](https://www.dota2.com/esports/ti15/tirules)
- [LGD 官方公告](https://weibo.cn/2157471171/RcAAEl9fF)
- [首轮与 LGD 调查记录](../research/ti2026-swiss-round1-lgd-roster-2026-08-10.md)
- [实装与正式重算记录](ti2026-swiss-round1-roster-update-2026-08-10.md)
