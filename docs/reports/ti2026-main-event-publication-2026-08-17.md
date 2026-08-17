# TI 2026 Main Event 发布版：实际八队、1.5× 阶段权重与五格 Fantasy

状态：**Main 五格求解包为 `ready / actual`；淘汰赛 Forecast 与通用 Fantasy 推荐为
`warning`，没有 blocking issue。** 本文中的概率和推荐均为本项目输出，不是 Valve 官方赛果。

- 数据与模型截止：`2026-08-16T15:31:30Z`
- Main 锁定时间：`2026-08-20T02:00:00Z`
- 淘汰赛 Forecast：`bracket-eb209f6fad530148`
- 通用 Main Fantasy：`fantasy-cf5ab8f302bfd876`
- 五格求解发布：`main-roll-20260816T153130Z-b2a9f1af5835.json.zst`
- 求解发布内容 SHA-256：
  `b2a9f1af583546dd64d7564c8ceaf866cf8546e35b7e720d8b47229b42735fe0`
- 求解发布源码身份：`047305d7cea97698572ddea94d3d2d53fdd7321d-dirty-54bf22abf4f9`
- 玩家出版运行源码身份：`047305d7cea97698572ddea94d3d2d53fdd7321d-dirty-54bf22abf4f9`

## 先看结论

1. 实际八队和官方直播揭晓的首轮对阵已进入独立 Main 配置；Group 的模型、数据快照和运行时
   指针没有被覆盖。
2. TI 2026 小组赛与突围赛共 `109` 场，全部进入 Elo/Glicko 和 Fantasy 历史证据，并在原有
   版本、赛事级别和 60 天半衰期之外再乘 `1.50`。
3. 当前八队综合强度前三为 **TEAM VISION、Team Liquid、Nigma Galaxy**。模型枚举完整
   `2^14 = 16,384` 个合法双败网格后，三个目标都选择 **TEAM VISION 冠军**；期望积分与
   top-100 使用同一完整网格，top-10 只在败者组第二轮 A 改选 BoomBoys。
4. 通用期望型 Fantasy 阵容为：**VISION Core、Nigma Mid、Nigma Support**。这只是无个人
   战旗画面时的基准；实际 Roll 决策仍应在 Web 中录入 15 格后使用 G 或 G-Lite。
5. Web 当前只提供实际八队，每个 Core / Mid / Support 下拉框均为 `8` 个候选。默认策略仍是
   **G**，G-Lite 保留为用户主动选择项。

## 实际八队与首轮

以下对阵来自官方直播画面，项目按稳定 Team ID 写入种子顺序；不是根据强度排名重新配对。

| 首轮 | 左队 | 右队 | 左队模型节点胜率 | 右队模型节点胜率 |
| ---: | --- | --- | ---: | ---: |
| 1 | Iron Wing | Team Spirit | **54.86%** | 45.14% |
| 2 | TEAM VISION | BoomBoys | **74.07%** | 25.93% |
| 3 | Team Liquid | Team Yandex | **63.83%** | 36.17% |
| 4 | Nigma Galaxy | Team Falcons | **56.68%** | 43.32% |

这些百分比是当前 Elo/Glicko 集成模型交给 BracketEngine 的节点概率，不是盘口，也不是 Valve
公布的胜率。小幅差距不应理解为确定结果。

败者组第二轮的接线另由当前游戏内 Main bracket 画面确认：A 节点接收胜者组半决赛 B 的败者，
B 节点接收胜者组半决赛 A 的败者，即两个半区交叉落位。核对截图 SHA-256 为
`eff7133618ee625277f095607b99dbb35e50e24e61dd7ed7c8b56911d2acb10e`；此前同侧落位的模型与
发布图已废弃并重新计算。

## 1.5× 阶段权重怎样计算

Team-strength 与 Fantasy 共用以下权重轴，但两者使用不同证据范围：

`大版本 × 当前精确版本 × 赛事级别 × 2^(-距 as_of 天数 / 60) × 当前赛事阶段`

- 目标大版本 7.41：`1.00`；相邻 7.40：`0.15`；更早版本：`0`。
- 当前精确版本 7.41e：再乘 `1.50`。
- OpenDota `premium / professional`：`1.00 / 0.75`；其他赛事级别：`0`。
- TI 2026 小组赛与突围赛的冻结 `109` 场：当前赛事阶段再乘 `1.50`。
- 因此一场同时属于 7.41e 和本届 TI 已结束阶段的比赛，会同时获得两个独立的 `1.50`，即在
  其他轴不变时相对基础 7.41 权重乘 `2.25`。这是“当前版本”与“当前赛事表现”两个不同判断，
  不是重复录入同一轴。

阶段集合只按显式 match ID 生效：

- 冻结场数：`109 / 109`
- 缺失或联赛冲突：`0`
- match ID 集合 SHA-256：
  `3bfecfc99e0ce51e7ce621093e8d3748b1b412c4207e2c92d5e5f0f169277fc4`
- 阶段有效权重：`239.546948`
- 全模型有效权重：`948.099939`
- 最终入模比赛：`4,069`

### 与 1.0× 对照

下面只把“TI 已结束阶段”从 `1.50` 改回 `1.00`，其他数据、版本权重、时间衰减、身份桥和
随机种子完全相同。生产结果使用右栏。

| 队伍 | 1.0× 综合强度（名次） | 1.5× 综合强度（名次） | 变化 |
| --- | ---: | ---: | ---: |
| TEAM VISION | 1820.58（1） | **1853.28（1）** | +32.70 |
| Team Liquid | 1745.28（2） | **1772.56（2）** | +27.29 |
| Nigma Galaxy | 1693.68（4） | **1735.60（3）** | +41.92 |
| Iron Wing | 1702.12（3） | **1719.54（4）** | +17.42 |
| Team Falcons | 1685.58（5） | **1688.60（5）** | +3.02 |
| Team Spirit | 1673.83（7） | **1685.48（6）** | +11.65 |
| Team Yandex | 1674.18（6） | **1673.14（7）** | -1.04 |
| BoomBoys | 1664.37（8） | **1669.62（8）** | +5.25 |

1.5× 并没有机械地给每队加同样分数。例如 Nigma–Falcons 的左队节点概率由 `51.17%` 变为
`56.68%`，Liquid–Yandex 由 `60.01%` 变为 `63.83%`；Yandex 的综合强度则小幅下降。

## 当前八队强度

综合强度为 Elo 与 Glicko rating 各占 50%。绝对 rating 的原点没有现实单位，主要用于八队间
横向比较。

| 排名 | 队伍 | 综合强度 | Elo | Glicko | RD | 入模局数 | 7.41 局数 | 有效权重 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | TEAM VISION | **1853.28** | 1792.49 | 1914.07 | 57.98 | 194 | 125 | 54.83 |
| 2 | Team Liquid | **1772.56** | 1722.73 | 1822.40 | 47.31 | 231 | 122 | 72.76 |
| 3 | Nigma Galaxy | **1735.60** | 1692.76 | 1778.44 | 58.67 | 62 | 62 | 44.19 |
| 4 | Iron Wing | **1719.54** | 1661.07 | 1778.01 | 49.19 | 46 | 46 | 57.33 |
| 5 | Team Falcons | **1688.60** | 1627.51 | 1749.69 | 46.53 | 197 | 114 | 74.94 |
| 6 | Team Spirit | **1685.48** | 1613.45 | 1757.50 | 52.65 | 191 | 111 | 59.27 |
| 7 | Team Yandex | **1673.14** | 1606.36 | 1739.91 | 51.68 | 171 | 83 | 58.77 |
| 8 | BoomBoys | **1669.62** | 1601.02 | 1738.23 | 46.83 | 224 | 134 | 77.12 |

冻结滚动验证中，50/50 Elo/Glicko 集成的 log loss / Brier / accuracy 为
`0.680296 / 0.243723 / 57.77%`，优于固定 50% 基线的 `0.693147 / 0.250000 / 51.23%`。
Isotonic 候选的 log loss 没有优于集成，因此按门禁拒绝，没有进入正式概率。

### 八队两两节点胜率

沿用 Group 阶段发布表口径，下面每格是左侧队伍战胜列队伍的概率。这里俗称“Elo 表”，但为与
实际 Forecast 一致，数值是 **Elo/Glicko 概率各占 50%** 的正式集成，不是纯 Elo 单模型。

| 左队 / 对手 | TEAM VISION | Team Liquid | Nigma Galaxy | Iron Wing | Team Falcons | Team Spirit | Team Yandex | BoomBoys |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **TEAM VISION** | — | **61.32%** | **66.14%** | **68.23%** | **71.94%** | **72.27%** | **73.67%** | **74.07%** |
| **Team Liquid** | 38.68% | — | **55.25%** | **57.53%** | **61.79%** | **62.17%** | **63.83%** | **64.29%** |
| **Nigma Galaxy** | 33.86% | 44.75% | — | **52.30%** | **56.68%** | **57.09%** | **58.81%** | **59.29%** |
| **Iron Wing** | 31.77% | 42.47% | 47.70% | — | **54.42%** | **54.86%** | **56.60%** | **57.10%** |
| **Team Falcons** | 28.06% | 38.21% | 43.32% | 45.58% | — | **50.46%** | **52.21%** | **52.72%** |
| **Team Spirit** | 27.73% | 37.83% | 42.91% | 45.14% | 49.54% | — | **51.76%** | **52.26%** |
| **Team Yandex** | 26.33% | 36.17% | 41.19% | 43.40% | 47.79% | 48.24% | — | **50.50%** |
| **BoomBoys** | 25.93% | 35.71% | 40.71% | 42.90% | 47.28% | 47.74% | 49.50% | — |

BracketEngine 直接把这些概率用于一个淘汰赛节点，没有另做 BO3 / BO5 series transform。因此
相对强弱方向比小数点后的精确 series 胜率更可信。完整来源、可信度和复算身份见
[Main 概率参考](ti2026-main-probability-reference-2026-08-17.md)。

## 淘汰赛 Forecast

### 冠军边际概率

| 队伍 | 冠军概率 |
| --- | ---: |
| TEAM VISION | **40.15%** |
| Team Liquid | **18.44%** |
| Nigma Galaxy | **11.75%** |
| Iron Wing | **9.26%** |
| Team Falcons | 6.03% |
| Team Spirit | 5.64% |
| Team Yandex | 4.69% |
| BoomBoys | 4.04% |

### 建议填写的完整网格

默认的期望积分网格同时也是 top-100 代理网格；期望活动积分为 `2464.237`，分布 P50 / P90
为 `1800 / 5400`。top-10 代理只在败者组第二轮 A 改选 BoomBoys，其自身期望积分为
`2463.615`。由于服务器总体分位阈值没有公开，玩家默认仍应采用期望积分网格。

[![TI 2026 Main Event 双败淘汰赛预测树](../assets/ti2026-main-event-double-elimination-bracket-2026-08-17.png)](../assets/ti2026-main-event-double-elimination-bracket-2026-08-17.svg)

图中金色行是建议胜者；金色实线表示胜者组晋级，蓝色实线表示败者组晋级，棕色虚线表示
从胜者组落入败者组。败者组第一轮卡片上方的 `UB R1 A / B`、`UB R1 C / D` 说明其来源。

<details>
<summary>展开纯文字节点表</summary>

| 节点 | 对阵 | 建议胜者 |
| --- | --- | --- |
| 胜者组第一轮 A | Iron Wing vs Team Spirit | **Iron Wing** |
| 胜者组第一轮 B | TEAM VISION vs BoomBoys | **TEAM VISION** |
| 胜者组第一轮 C | Team Liquid vs Team Yandex | **Team Liquid** |
| 胜者组第一轮 D | Nigma Galaxy vs Team Falcons | **Nigma Galaxy** |
| 败者组第一轮 A | Team Spirit vs BoomBoys | **BoomBoys** |
| 败者组第一轮 B | Team Yandex vs Team Falcons | **Team Yandex** |
| 胜者组半决赛 A | Iron Wing vs TEAM VISION | **TEAM VISION** |
| 胜者组半决赛 B | Team Liquid vs Nigma Galaxy | **Team Liquid** |
| 败者组第二轮 A | Nigma Galaxy vs BoomBoys | **Nigma Galaxy** |
| 败者组第二轮 B | Iron Wing vs Team Yandex | **Iron Wing** |
| 败者组第三轮 | Nigma Galaxy vs Iron Wing | **Iron Wing** |
| 胜者组决赛 | TEAM VISION vs Team Liquid | **TEAM VISION** |
| 败者组决赛 | Iron Wing vs Team Liquid | **Team Liquid** |
| 总决赛 | TEAM VISION vs Team Liquid | **TEAM VISION** |

</details>

这里的交叉落位来自当前游戏内 Main bracket：败者组第二轮 A 接收
`Liquid–Nigma Galaxy` 的败者，败者组第二轮 B 接收 `Iron Wing–TEAM VISION` 的败者。
top-10 代理网格唯一不同之处是把败者组第二轮 A 的胜者由 Nigma Galaxy 改为 BoomBoys；
其余十三个节点与上表相同。

### 随机乱填与模型网格的数学期望

这里把“随机乱填”定义为：在 `2^14 = 16,384` 个拓扑自洽的完整双败网格中均匀抽一个，而
不是在下游写入已经被自己上游答案淘汰的队伍。实际赛果路径仍按同一冻结模型分布。

| 填写方法 | 期望正确节点 | 期望正确率 | 期望活动积分 | 相对随机提升 |
| --- | ---: | ---: | ---: | ---: |
| 随机合法网格 | **3.7500 / 14** | **26.7857%** | **1367.525** | — |
| 当前推荐网格 | **5.4122 / 14** | **38.6583%** | **2464.237** | **+1096.712 分（+80.20%）** |

随机命中不是 `7 / 14`：下游节点必须先让真实胜者出现在自己的预测分支里，四个胜者组首轮各
有 50%，败者组第一轮和胜者组半决赛各 25%，交叉落位后的败者组第二轮及后续节点各
12.5%。随机积分也不是“期望 3.75 个正确，所以直接查表”；累计积分表非线性，正确算法是
`E[points(K)]`，少量高命中路径会把结果抬到 `1367.525`。
完整分层推导、全中概率与计算边界见 [Main 概率参考](ti2026-main-probability-reference-2026-08-17.md)。

## Fantasy 数据与通用基准

Main Fantasy 使用全局正权重的目标选手历史，而不是 Elo 的 Team 连通图；同一场 TI 比赛仍使用
与 Elo 相同的 1.5× 阶段倍率。缺失值保持 `null`，没有把 replay 缺失当成 0。

- 赛前已有 exact replay：`2,055`
- 本次实际八队新增 exact replay：`80`
- 当前 exact replay 总数：`2,135`
- 本届 TI Fantasy Game：`109`
- 正权重 Fantasy Game：`4,555`
- 合格 BO2/BO3 Game：`3,636`
- 结构完整 BO2/BO3 Series：`1,481`
- 目标选手行：`11,279`
- 全 16 队历史池：`47 / 48`；唯一不可用池是已淘汰 LGD 的 Mid
- 实际 Main 候选：Core / Mid / Support 均为 `8 / 8`，不存在缺失位置

无个人画面时，通用期望型基准如下：

| 位置 | 队伍与选手 | 五个 Stat | 期望原始分 |
| --- | --- | --- | ---: |
| Core | TEAM VISION：Satanic、Noticed | creep score；teamfight；GPM；Roshan；deaths | **15689.5660** |
| Mid | Nigma Galaxy：lorenof | creep score；runes；teamfight；GPM；Roshan | **15028.4624** |
| Support | Nigma Galaxy：GH、OmaR | wards；teamfight；watchers；stuns；smokes | **11284.6262** |
| **合计** |  |  | **42002.6546** |

top-10 / top-100 代理目标仍选择 VISION Core 与 Nigma Mid，但把 Support 改为 Team Falcons 的
Cr1t-、Sneyking。服务器总体分位阈值没有公开，因此两个尾部目标只保留 `warning`。

## 五格求解器发布状态

当前 `deploy/runtime/main-current.json` 已指向 actual 发布包：

- 状态：`ready`
- 候选模式：`actual`
- 候选队 / 实际参赛队：`8 / 8`
- Main 情景：`256`
- Main Fantasy pool SHA-256：
  `e623437a7e1da94519a0bfd3b9c8680e3e0c5f7a9a2c09e873f40938e4eaab41`
- 模型 SHA-256：
  `bf7bd372f1ebc57dee0e238bca21d776411bc0e25f4a28c1f72aafc9dfed76c2`
- 数据情景 SHA-256：
  `3f1aad154b20bdce7795ec293efa7462b7932a74bc8dcec967f7c048ae5a56b3`

策略边界保持研究结论：

- **G（默认）**：只比较当前可见动作的一步期望终局价值。
- **G-Lite（可选）**：通常跟随 G；只有前两项差距不超过当前价值 `0.05%` 时才各抽 4 个固定
  下一轮样本，覆盖 G 还需至少 `0.01%` 二步优势，每局最多触发 4 次。它仍标记为
  development-positive、未独立 confirmation。
- 失败的 `0.10% / 每局 5 次` 变体没有进入生产策略目录。

## Main Stat、Title 与玩家手册

actual 八队另生成了绑定同一求解发布包的三份玩家资料：

- [Main Stat 与队伍 Top 3 完整表](../playbooks/main-roll/stat-team-top3-publication-v1.md)：
  24 个实际队伍×位置池、42 个位置/颜色/Stat 行、400 次完整 Series 分组重采样；
- [Main Title 分析与推荐](ti2026-main-fantasy-title-recommendation-2026-08-17.md)：默认从
  Group 的 Cerulean 更新为 **Elemental**，Suffix 继续是 **the Clutch**；
- [Main 30 Roll 玩家手册](../playbooks/main-roll/main-roll-publication-manual-v1.md)：五格输入、
  G/G-Lite、页面指标、随机模型和每次操作后完整重算的实战循环。
- [Main 概率参考](ti2026-main-probability-reference-2026-08-17.md)：八队两两胜率、随机与模型
  网格期望、20 个 Roll operation 出现率、Quality/Trait/Stat 结果分布及来源可信度。

Main Title 使用 1,073 场不可变原始详情与 1,395 个队伍×位置完整 Series blocks。公开
Streamlit 和本地 Web 共享包内 24 个队伍×位置池，每次按当前 Core / Mid / Support 三队和
当前战旗基础贡献动态重算 Prefix / Suffix 前三；默认画面为 **Otherworldly + the
Underdog**，而无个人画面的全局中性默认仍是 **Elemental + the Clutch**。Clutch 仍以历史 BO3
打满比例作为 proxy，没有把可能的 BO5 总决赛冒充为已经精算。内嵌 Title 运行时证据为
`fbb3a6ae18ea3bd8e86ce20ac203db154ed09ebadebfe2c21f4767b5e7b85e5e`，Main 玩家出版证据为
`97c4590267860438071924b439ce70ee122c7a8f287d3a04eb092a539dd50f66`。Group 三格手册冻结的
B/C/D 操作规则没有直接搬到 Main。

## 冻结数据与哈希

- Main evidence snapshot：
  `data/processed/snapshots/main-actual-20260816T153130-4b189f4726d7`
- snapshot semantic SHA-256：
  `4b189f4726d7e996a70a174feb6be04c4ccaf6148dd006f46fffe523c7cc8bcb`
- snapshot manifest SHA-256：
  `5d20e16405ed73cbbc91a70a11d9f3837511fbc204483779f1544b306bb0fd4c`
- Team-strength policy SHA-256：
  `4895101201e20afd5baf5fecfb46cf171b58285f044a90a84afa4b96ef23875f`
- 最终 Team-strength match set SHA-256：
  `cf54d074a5f49172f36b3ab2489b08aa24e1c383677c40f9870795024c17d178`
- 客户端规则快照：`20260813T132319Z-9728c506baf6`
- 规则快照 SHA-256：
  `9728c506baf6b5b2a706d0c70e4869fc6354c543d0cb4b911a4bf8427276bf06`

## 验证

- Pytest：`332` 项，`331 passed / 1 skipped`
- Ruff lint：通过
- Ruff format check：通过
- `git diff --check`：通过
- Streamlit AppTest：Main 五格、G/G-Lite、实际八队手动组合和动态 Title 全部通过，页面无
  exception/error
- 旧 projected-16 研究栈：改为显式加载 manifest 冻结发布，不再读取当前生产指针

## 使用边界

- 官方直播首轮对阵已人工转录；如果客户端或 Valve 结构化接口随后给出不同种子顺序，必须刷新
  manifest 并重跑。
- BracketEngine 枚举完整双败拓扑，但其节点概率仍是模型估计；精确名次的可信度低于大致实力层。
- Fantasy 的历史 BO2/BO3 Series 用作 Main 出场表现 proxy，不声称精确重建总决赛可能出现的
  BO5 局数。
- G-Lite 由用户主动选择，不是自动晋升的默认策略。
- 本项目不登录 Steam、不控制 Dota 客户端，也不自动填写任何 InGamePrediction。
