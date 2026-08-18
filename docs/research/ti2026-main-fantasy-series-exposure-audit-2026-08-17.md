# TI 2026 Main Fantasy Series 暴露量审计

- 审计日期：2026-08-17
- 审计对象：当前 `ready / actual` Main 求解发布包，以及 G / G-Lite 共用的 Main terminal
- 当前数据截止：`2026-08-16T15:31:30Z`
- 当前 Main release：`b2a9f1af583546dd64d7564c8ceaf866cf8546e35b7e720d8b47229b42735fe0`
- 当前 Main Scenario：`3f1aad154b20bdce7795ec293efa7462b7932a74bc8dcec967f7c048ae5a56b3`
- 本次边界：只读调查；未修改求解器、Web、配置、运行时指针或发布包

## 结论

当前 Main Fantasy 推荐**已经考虑每队未来 Series 数量不平衡**，但只做到“有结构的代理”，
不是完整赛制精算。

当前链路是：

1. 按八队双败树抽取 256 条完整 bracket 路径；
2. 在每条路径中，统计每队实际参加的 Series 数量，范围为 2–6；
3. 对某队某位置抽取同样数量的历史完整 Series blocks；
4. 每个 Series 先取该位置分数最高的两局之和；
5. 整个 Main Period 再从该队参加的全部 Series 中取最高的一个；
6. 用 256 条情景的均值和下尾风险选择一个事前固定的 Team，不允许在看到某条情景的实际
   晋级结果后再换 Team。

因此“多打一轮”并不会把所有 Series 分数相加，而是多获得一次刷新“最佳 Series”的机会。
这是一种有明显边际递减的机会优势。

当前尚未完整处理的部分是：

- 256 条路径抽样本身有可见 Monte Carlo 误差；
- bracket 节点概率仍是未校准的单图 Team-strength proxy，没有分别校准 BO3 / BO5 Series 胜率；
- 历史 Fantasy Series 是独立、有放回抽样，没有按未来对手、胜负、轮次或舞台条件化；
- Grand Final 的 BO5 没有生成 3–5 局，只把它当作“又一个历史 BO2/BO3 Series 机会”；
- Title 推荐与五格 Banner terminal 尚未联合优化。

## Valve 规则与 Main 赛制

### Fantasy 结算规则

本机 Dota 客户端快照
`data/raw/rules/20260813T132319Z-9728c506baf6/resource/localization/dota_english.txt`
在第 52445 行明确写明 TI 2026 的顺序：

1. 先计算每名选手每局的分数；
2. 对同一 role 的选手取平均，得到 role 的单局分数；
3. 一个 Series 只取最高两局之和；
4. 一个 Period 打多个 Series 时，只取最高 Series。

对应数学式为：

```text
series_score_s = highest(game_scores_s) + second_highest(game_scores_s)
period_score(K) = max(series_score_1, ..., series_score_K)
```

规则快照来自 Dota 客户端，`as_of=2026-08-13T13:23:17Z`，Steam build
`6898:10904633`，快照 SHA-256
`9728c506baf6b5b2a706d0c70e4869fc6354c543d0cb4b911a4bf8427276bf06`。

### Main bracket

Valve 官方 [`GetLeagueData`，league_id=19719](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719)
的本地不可变响应为
`data/raw/valve_ti2026_league/20260816T093516Z/response.json`：

- `node_group_id=5` 为八队 Playoff；
- `node_group_type=6`；
- 共有 14 个节点；
- 13 个节点为 `node_type=2`，Grand Final 为 `node_type=3`；
- Valve [TI 2026 Schedule](https://www.dota2.com/esports/ti15/schedule) 将相应类型显示为
  BO3 与 BO5；
- 节点 24/25 明确采用败者组第二轮交叉落位。

所以每条完整 bracket 路径固定有 14 个 Series、28 次 Team-Series 参与。单队最少参加
2 个 Series，最多参加 6 个 Series。

“冠军一定打得最多”并不成立：

- 胜者组全胜夺冠只打 4 个 Series；
- 胜者组决赛落败、再从败者组夺冠会打 5 个；
- 更早落入败者组后夺冠可能打 6 个；
- 因而败者组长跑的亚军也可能比胜者组全胜冠军参加更多 Series。

用户所说的 PV 在当前稳定身份桥接中对应界面里的 `TEAM VISION`。中心判断仍然成立：
不同队伍的预期比赛机会明显不均衡。

## 当前实现追踪

### 1. Bracket 路径产生 Series 数量

`src/ti_predictor/fantasy/main_scenarios.py` 的
`build_main_scenario_set_from_model()` 对每条 `BracketEngine.sample()` 路径遍历
`path.participants`，两支参赛队的 `series_counts` 各加一。

`MainScenarioSet` 同时强制：

- 每条情景恰好八队 active；
- 每个 Main 参赛队至少 2 个 Series；
- 最大不超过 6；
- 每个 Team/role 的抽样矩阵必须与最大 Series 槽数对齐。

### 2. Series 数量真正进入 Fantasy 值

`build_main_scenario_set()` 为每个 Team/role 先生成最多六个历史 Series block 索引，然后把
超过该队本情景 `series_counts` 的槽位写成 `-1`。

`src/ti_predictor/fantasy/valuation.py` 的 `_period_outcomes_for_pool()` 会：

- 计算每个抽中的完整 Series block 的 Banner 分数；
- 对未使用槽位保持空值；
- 执行 `sampled.max(axis=1)`，即从该队本 Period 的 K 个 Series 中取最高值。

所以 Series 数量不是只存在于审计字段，而是实际进入了 G / G-Lite 的 terminal value。

### 3. Team 选择没有偷看单条未来路径

`match_group_roles()` 先对每支候选队的全部 Scenario 向量求均值，再在均值保留门槛内按联合
CVaR 选择一个固定的 Core/Mid/Support Team 组合。它没有在每条路径里分别挑当条路径的赢家。

这点很重要：选择必须发生在 Main 开赛前，不能在模拟中看到“这条未来路径是谁走得最远”后
再切换 Team。

### 4. 当前冻结发布包的实数审计

当前发布包含 256 条情景、8 支实际 Main 队伍。每条情景的 `series_counts` 总和都是 28，
且所有 2,048 个 Team×Scenario 单元都在 2–6 之间。

| Team | 发布包平均 Series | 2 | 3 | 4 | 5 | 6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Iron Wing | 3.6562 | 58 | 53 | 84 | 41 | 20 |
| Team Liquid | 3.8477 | 32 | 62 | 97 | 43 | 22 |
| Nigma Galaxy | 3.5117 | 60 | 67 | 80 | 36 | 13 |
| TEAM VISION | 4.1875 | 19 | 33 | 122 | 45 | 37 |
| BoomBoys | 3.1094 | 101 | 67 | 56 | 23 | 9 |
| Team Falcons | 3.3125 | 68 | 79 | 79 | 21 | 9 |
| Team Yandex | 3.0312 | 96 | 81 | 59 | 15 | 5 |
| Team Spirit | 3.3438 | 78 | 70 | 63 | 32 | 13 |

对同一个冻结 Team-strength model 枚举全部 `2^14=16,384` 条 bracket 路径后，精确外层期望为：

| Team | 256 抽样均值 | 16,384 加权精确均值 | 抽样减精确 |
| --- | ---: | ---: | ---: |
| Iron Wing | 3.6562 | 3.5250 | +0.1312 |
| Team Liquid | 3.8477 | 3.8448 | +0.0029 |
| Nigma Galaxy | 3.5117 | 3.6310 | -0.1193 |
| TEAM VISION | 4.1875 | 4.1636 | +0.0239 |
| BoomBoys | 3.1094 | 3.0572 | +0.0522 |
| Team Falcons | 3.3125 | 3.3091 | +0.0034 |
| Team Yandex | 3.0312 | 3.1762 | -0.1449 |
| Team Spirit | 3.3438 | 3.2930 | +0.0507 |

这说明 256 条确实捕捉到了方向，但对个别队的平均机会数仍有约 0.12–0.15 Series 的抽样误差。

另做了冻结一致性核对：使用当前修正后的败者组交叉树、同一 Team-strength 模型和 seed
`20260820` 重放 256 条路径，`series_counts` 与发布包 2,048 个单元逐格相同，差异为 0。
因此当前 Fantasy 发布包的 Series 数量不是旧的未交叉 bracket。

## 已考虑与未考虑的边界

| 问题 | 当前状态 |
| --- | --- |
| 不同队伍会打 2–6 个 Series | 已考虑 |
| 多一个 Series 增加刷新最佳 Series 的机会 | 已考虑 |
| 一个 Series 取最高两局 | 已考虑 |
| 事前固定 Team，不偷看单条未来路径 | 已考虑 |
| 八队官方种子与败者组交叉拓扑 | 已考虑，冻结重放一致 |
| BO3 / BO5 使用各自 Series 胜率 | 未考虑，节点直接使用单图 Team-strength proxy |
| Grand Final 生成 3–5 局并取其中最高两局 | 未考虑 |
| Fantasy 表现随对手、胜负、轮次变化 | 未考虑 |
| 晋级结果与本队当场 Fantasy 表现相关 | 未考虑；目前两者条件独立 |
| 五格 Banner 与 Title 联合优化 | 未考虑；Title 是独立推荐 |
| 外层 bracket 概率无 Monte Carlo 误差 | 未达到；当前只抽 256 条 |

## 三套解决方案

### 方案一：强化现有 Monte Carlo

保留当前数据结构与 Web terminal，只加强离线发布过程：

1. 将 256 条提高到 4,096 或 8,192 条，并按关键路径/最终名次分层抽样；
2. 节点先使用经过留出验证的 BO3 Series 概率，Grand Final 使用 BO5 概率；
3. Scenario 不只保存 Series 数量，还保存节点格式；Grand Final 单独生成 3–5 局；
4. bracket 路径、Fantasy blocks 和不同 Banner action 使用公共随机数，减少比较噪声；
5. 加入“Series 数量改变必然改变 period max 分布”的直接回归测试。

优点：改动最小、能继续预生成发布包，Web 延迟基本不变。
缺点：仍然依赖抽样；对手与 Fantasy 表现的相关性仍很弱。
定位：最快可发布方案。

### 方案二：精确外层 bracket + 条件化内层 Fantasy 模拟

把全部 16,384 条合法 bracket 路径作为带精确权重的外层状态，不再抽 256 条路径。每个实际
节点再生成条件化 Fantasy 表现：

1. 外层路径记录双方、轮次、BO3/BO5、胜负与路径概率；
2. 内层 Series block 至少按 Team/role、对手强度带、胜负和 BO 格式条件化；稀疏单元使用
   层级收缩回全队历史池；
3. 同一场的胜负和 Fantasy 表现使用联合抽样，避免“表现很差却独立晋级”的不一致；
4. 严格执行每 Series 最高两局、Period 最高 Series；
5. Team 仍在所有未来路径揭晓前固定选择；
6. 把 Title 触发一起算入单局分数。

优点：最贴近实际赛制，可作为研究真值与最终验收基准。
缺点：数据稀疏、联合模型与运算成本最高；需要离线预计算和压缩，不能把完整模拟搬到每次
Web 点击中。
定位：推荐作为正式研究基准。

### 方案三：解析式“最佳 K 个机会”模型

利用 Valve 只取最佳 Series 的结构，避免逐条抽未来 Series。若某 Team/role/Banner 的单个
Series 分数经验分布为 `F(x)`，在独立同分布近似下：

```text
P(period_best <= x | K=k) = F(x)^k
P(period_best <= x) = sum_k P(K=k) * F(x)^k
```

其中 `P(K=k)` 直接由 16,384 条 bracket 的精确权重给出；BO3 和 BO5 使用不同的经验分布，
必要时再按对手强度带混合。

优点：非常快，Web 可直接使用；Series 数量不平衡和边际递减都能精确表达；没有 256 条外层
抽样误差。
缺点：独立同分布假设会弱化同队状态持续性、对手相关性以及 Core/Mid/Support 的联合 CVaR；
复杂 Title 条件也不如逐局模拟自然。
定位：适合作为生产快速终端和独立数学核对。

## 建议路线

不建议因为“当前已经考虑 K”就保持不动，也不建议直接推翻现有 terminal。

最稳妥的研究顺序是：

1. 先实现方案二的离线小规模真值版本，冻结官方树、BO3/BO5 与事前 Team 选择边界；
2. 同时实现方案三，逐 Team/role/Banner 与方案二比较均值、P10/CVaR10 和 Team 排名；
3. 若方案三在预注册误差门槛内复现方案二，就让 Web 使用方案三的压缩发布包；
4. 方案一作为低风险过渡与独立 Monte Carlo 交叉检查，而不是最终唯一依据。

在开始任何实装前还应先冻结四个门槛：BO3/BO5 概率语义、条件化维度与稀疏回退、方案三可
接受误差、Title 是否进入同一 terminal。本次没有替用户作出这些不可逆选择。
