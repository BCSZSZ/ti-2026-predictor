# TI 2026 Main：八队两两胜率、预测积分期望与 Roll 概率证据审计

状态：**更正后研究证据。当前游戏内画面确认败者组第二轮交叉落位；原只读审计所用同侧拓扑
已废弃，生产引擎、Main 情景和发布材料随后按本稿重新计算。**

- 审计日期：`2026-08-17`
- Forecast / Fantasy 数据截止：`2026-08-16T15:31:30Z`
- Main Bracket 运行：`bracket-eb209f6fad530148`
- Main 实际八队：Iron Wing、TEAM VISION、Team Liquid、Team Yandex、Nigma Galaxy、
  Team Falcons、Team Spirit、BoomBoys
- 客户端规则快照：`20260813T132319Z-9728c506baf6`
- 规则快照语义 SHA-256：
  `9728c506baf6b5b2a706d0c70e4869fc6354c543d0cb4b911a4bf8427276bf06`

规则证据只绑定**仓库截至本次审计所含的最新冻结客户端快照**：其 `as_of` 为
`2026-08-13T13:23:17Z`，Steam build 为 `6898:10904633`。仓库中没有 8 月 14–17 日的新快照，
所以本文不能证明 8 月 17 日实时客户端仍完全相同；若正式文档要使用“当前实时客户端已确认”
这样的措辞，必须先重新采集客户端规则并比较语义 hash。

本文沿用正式方法报告的证据等级：A 为客户端/Valve 事实，B 为受治理直接观测，C 为给定输入
可唯一复算的派生，D 为经验证模型推断，E 为仍含关键未验证假设的实验模型。这里的“可信度”
描述证据性质，不是胜率本身的置信区间。

## 结论摘要

1. 小组赛阶段的同类 `16×16` 表位于
   [`ti2026-group-forecast-publication-2026-08-09.md`](../reports/ti2026-group-forecast-publication-2026-08-09.md#队伍之间的单局关系)。
   Main 应使用下面新的实际八队 `8×8` 表，不能继续引用小组赛旧 rating。
2. 用户口语中的“Elo 胜率”在当前正式实现里实际是**未校准的 50% Elo + 50% Glicko**。
   TEAM VISION 对其余七队的中立节点概率为 `61.32%–74.07%`；最接近五五开的对局是
   Yandex–BoomBoys，Yandex 为 `50.50%`。
3. Main 预测有 14 个节点，活动积分只取决于正确节点数。若“随机乱填”严格定义为从
   `2^14=16,384` 个合法、内部一致的双败网格中等概率抽一个，则在当前模型的赛果分布下：
   **期望正确 `3.7500` 个节点、期望 `1367.525` 活动积分**。
4. 期望积分发布网格的同口径结果为：**期望正确 `5.4122` 个节点、期望 `2464.237` 活动
   积分**；相对随机网格增加 `1096.712` 分，即 `+80.197%`。全枚举核对确认它是当前冻结
   模型下 16,384 个合法网格中的全局最高期望积分网格。top-10 代理只在败者组第二轮 A 改选
   BoomBoys，top-100 与期望积分网格相同。
5. Roll 的合法支持、20 个正权重 operation、operation 权重和 Quality 权重来自客户端，证据强；
   但“顺序加权无放回”“Trait/Stat/目标均匀”“可重复当前值”“多格独立”“replacement offer
   独立”是项目的 Primary 模型，不是 Valve 已公开的 GC 真概率。
6. 生产 G 和 G-Lite 都以 `client-weight-primary-v1` 评价属性结果。G 不估计未知的下一组
   offer；G-Lite 只有触发有限二步时，才按该模型抽取 4 组确定性 replacement offer。
7. 当前证据不包含 Main 初始 15 格属性或“进入页面时第一组 offer”的联合生成分布。Web / 本地
   正式求解器读取玩家实际看到的状态，因此不需要猜这个先验；只有随机起始画面研究才会受其影响。

## 一、实际八队两两胜负关系

### 1.1 正式概率不是“纯 Elo”

对任意两队 A、B，冻结模型先分别计算 Elo 和 Glicko 中立概率：

```text
p_E(A,B) = 1 / (1 + 10 ^ ((Elo_B - Elo_A) / 400))

q = ln(10) / 400
g(RD) = 1 / sqrt(1 + 3 q^2 RD^2 / pi^2)
e_A = 1 / (1 + 10 ^ (-g(RD_B) (G_A - G_B) / 400))
e_B = 1 / (1 + 10 ^ (-g(RD_A) (G_B - G_A) / 400))
p_G(A,B) = (e_A + 1 - e_B) / 2

p(A,B) = 0.5 p_E(A,B) + 0.5 p_G(A,B)
```

实现见 [`ratings.py`](../../src/ti_predictor/models/ratings.py#L42-L43)、
[`ratings.py`](../../src/ti_predictor/models/ratings.py#L117-L125) 和
[`ratings.py`](../../src/ti_predictor/models/ratings.py#L180-L205)。Main 政策为
[`team-strength-main-v1.json`](../../config/models/team-strength-main-v1.json)，其中 Elo 初值
`1500`、`K=28`、scale `400`，Elo/Glicko 各占 `0.5`；TI 已结束阶段使用额外 `1.5×` 证据
权重。

滚动验证拒绝了 isotonic 候选，因此 `TeamStrengthModel.predict()` 返回上面的原始集成概率，
没有再校准。当前冻结滚动验证的 log loss / Brier / accuracy 为
`0.680296 / 0.243723 / 57.77%`；固定 50% 基线为
`0.693147 / 0.250000 / 51.23%`。因此这一列属于 **D 级、可信度中等**：适合表达相对强弱与
节点倾向，不应写成精确客观概率。

另一个重要边界是：[`BracketEngine`](../../src/ti_predictor/tournament/bracket.py#L43-L110)
把 `model.predict()` 直接用于每个淘汰赛节点，没有额外做 BO3/BO5 转换。所以表中数字与当前
Bracket 运行一致，但应命名为“中立节点概率（单局 Team-strength proxy）”，不能冒充经过
系列赛比分模型校准的 BO3/BO5 胜率。

### 1.2 实际八队 `8×8` 矩阵

读法：行是左侧队伍，列是对手，单元格表示左侧队伍赢下一个中立淘汰赛节点的当前模型概率。
反向单元格严格互补为 100%；显示保留两位小数。

| 左侧队伍 / 对手 | VISION | Liquid | Nigma | Iron Wing | Falcons | Spirit | Yandex | BoomBoys |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TEAM VISION | — | **61.32%** | **66.14%** | **68.23%** | **71.94%** | **72.27%** | **73.67%** | **74.07%** |
| Team Liquid | 38.68% | — | **55.25%** | **57.53%** | **61.79%** | **62.17%** | **63.83%** | **64.29%** |
| Nigma Galaxy | 33.86% | 44.75% | — | **52.30%** | **56.68%** | **57.09%** | **58.81%** | **59.29%** |
| Iron Wing | 31.77% | 42.47% | 47.70% | — | **54.42%** | **54.86%** | **56.60%** | **57.10%** |
| Team Falcons | 28.06% | 38.21% | 43.32% | 45.58% | — | **50.46%** | **52.21%** | **52.72%** |
| Team Spirit | 27.73% | 37.83% | 42.91% | 45.14% | 49.54% | — | **51.76%** | **52.26%** |
| Team Yandex | 26.33% | 36.17% | 41.19% | 43.40% | 47.79% | 48.24% | — | **50.50%** |
| BoomBoys | 25.93% | 35.71% | 40.71% | 42.90% | 47.28% | 47.74% | 49.50% | — |

当前模型组件输入如下，完整精度保存在
`artifacts/bracket-eb209f6fad530148/model.json`：

| 队伍 | Elo | Glicko | RD | 50/50 综合强度 |
| --- | ---: | ---: | ---: | ---: |
| TEAM VISION | 1792.4903 | 1914.0689 | 57.9843 | 1853.2796 |
| Team Liquid | 1722.7279 | 1822.4003 | 47.3080 | 1772.5641 |
| Nigma Galaxy | 1692.7586 | 1778.4380 | 58.6705 | 1735.5983 |
| Iron Wing | 1661.0658 | 1778.0147 | 49.1872 | 1719.5403 |
| Team Falcons | 1627.5124 | 1749.6882 | 46.5302 | 1688.6003 |
| Team Spirit | 1613.4547 | 1757.4956 | 52.6471 | 1685.4752 |
| Team Yandex | 1606.3646 | 1739.9082 | 51.6800 | 1673.1364 |
| BoomBoys | 1601.0189 | 1738.2298 | 46.8295 | 1669.6243 |

### 1.3 建议写入正式 Main MD 的说明

建议把矩阵放在正式 Main 报告“当前八队强度”之后，并保留以下三句：

> 本表使用当前正式 Team-strength，即未校准的 50% Elo + 50% Glicko；“Elo 表”只是口语简称。
> 数字表示中立节点倾向，BracketEngine 没有额外做 BO3/BO5 转换。45%–55% 应按接近五五开
> 解读，不能理解为确定结果或盘口。

## 二、当前 Main 预测规则下的数学期望

### 2.1 Valve 客户端积分规则

规则快照从 `international_2026.eventdef` 读到 14 次 Main grant，见
[`rule_snapshot.json`](../../data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json#L119-L151)；
规范化表见 [`ti2026.json`](../../config/rules/ti2026.json#L38-L42)。正确节点数 `k` 与本阶段
活动积分 `R(k)` 为：

| 正确节点数 k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 活动积分 R(k) | 0 | 120 | 360 | 720 | 1200 | 1800 | 2520 | 3360 | 4320 | 5400 | 6600 | 7920 | 9360 | 10920 | 12000 |

`k=0..13` 时可写成 `R(k)=60k(k+1)`；`k=14` 时客户端把本应为 12600 的递增结果封顶为
`12000`。积分表和 14 个节点数属于 **A 级客户端事实**。

### 2.2 游戏内确认的败者组交叉落位

当前游戏内 bracket 画面 SHA-256
`eff7133618ee625277f095607b99dbb35e50e24e61dd7ed7c8b56911d2acb10e` 显示：

- 败者组第二轮 A：胜者组半决赛 B（Liquid–Nigma）的败者，对败者组第一轮 A 的胜者；
- 败者组第二轮 B：胜者组半决赛 A（Iron Wing–VISION）的败者，对败者组第一轮 B 的胜者。

此前 `BracketEngine` 错把两个胜者组半决赛败者送回同侧。回归测试现在直接断言两个节点的
参赛来源与游戏内上下顺序；Main Fantasy 情景复用同一引擎，因此修正后也重建了求解发布包。

### 2.3 两个可比较策略的精确定义

设 `B` 为所有 `2^14=16,384` 个合法、内部一致的双败填写网格；`O` 是所有 16,384 个可能
赛果路径。每条赛果路径概率由当前模型沿其实际对阵逐节点相乘：

```text
P(o) = product over node n of p_n(chosen winner | participants generated earlier in o)
K(c,o) = sum over 14 nodes of 1[predicted winner in c == actual winner in o]
```

当前模型网格 `c*` 的期望为：

```text
E_model = sum_o P(o) R(K(c*,o))
```

本文把“随机乱填”严格定义为：玩家在锁定前对每个当前可填分支掷公平硬币，因此在全部
16,384 个合法网格中等概率选一个。它的期望为：

```text
E_random = (1 / 16384) sum_c sum_o P(o) R(K(c,o))
```

不能把随机基准写成“已经知道真实后续参赛队后，再对 14 场实际对阵逐场猜硬币”。后者偷看了
未来参赛者，不是锁定前可提交的完整网格。合法随机网格在第一轮节点的正确概率为 `50%`；
败者组第一轮和胜者组半决赛共四个节点为 `25%`；交叉落位的败者组第二轮以及后续共六个
节点为 `12.5%`，所以：

```text
E_random[正确节点数] = 4×0.5 + 4×0.25 + 6×0.125 = 3.75
```

### 2.4 精确全枚举结果

| 提交策略 | 候选网格分布 | 期望正确节点 | 期望活动积分 | 相对 12000 上限 | 相对随机增量 |
| --- | --- | ---: | ---: | ---: | ---: |
| 合法随机乱填 | 16,384 个合法网格等概率 | **3.7500** | **1367.525** | 11.396% | — |
| 期望积分发布网格 | 当前模型的期望积分最高网格 | **5.4122** | **2464.237** | 20.535% | **+1096.712（+80.197%）** |

计算使用 [`BracketEngine.enumerate()`](../../src/ti_predictor/tournament/bracket.py#L113-L119)
生成全部赛果路径，以 [`_scores()`](../../src/ti_predictor/tournament/bracket.py#L121-L127) 的
“同节点 winner team ID 相等”口径计数，再应用客户端非线性积分表。发布 JSON 中显示的
`2464.237` 是舍入到三位小数；全精度为 `2464.2369199264244`。随机网格全精度为
`1367.524913703552`。

生产代码为了日常运行，只对由节点边际与路径概率形成的确定性 shortlist 做非线性精算，见
[`bracket.py`](../../src/ti_predictor/tournament/bracket.py#L143-L178)。本次额外只读审计对所有
16,384 个候选网格逐个计算同一精确期望，确认发布网格索引 `650`、bits
`(0,0,0,0,1,0,1,0,0,0,1,0,1,0)` 也是全局最大值。

这组积分期望属于 **C（给定模型即可精确派生）+ D（赛果概率来自模型）**，总体可信度中等。
公式和枚举没有 Monte Carlo 误差，但若 Team-strength 概率错了，积分期望也会随之偏移。

### 2.5 不得与 Fantasy 或 top-10/top-100 混用

- `2464.237` 是 **Main 淘汰赛 InGamePrediction 的活动积分期望**，不是 Fantasy 原始分。
- Main 通用 Fantasy 报告中的 `42002.6546` 是三面战旗未加个人实际画面时的**原始 Fantasy
  分数期望**；服务器参与者分布未知，不能把它直接转换成活动积分期望。
- Bracket 的 `top_10` / `top_100` profile 是对参考积分分布建立的低置信内部 proxy，见
  [`bracket.py`](../../src/ti_predictor/tournament/bracket.py#L158-L179)。本次 top-10 只在败者组
  第二轮 A 选择 BoomBoys，期望积分为 `2463.615`；top-100 与期望积分网格相同。这不等于
  已知服务器前 10% 或前 100 名门槛。
- 因此目前可以精确报告“Main bracket：随机 1367.525，对期望积分网格 2464.237”；不能把 Group
  已结算积分、Main bracket 和 Fantasy percentile 拼成一个“全活动总期望”。

### 2.6 建议写入正式 Main MD 的说明

建议把上面的比较表放在正式 Main 报告“淘汰赛 Forecast”之前，并明确随机基准是“合法一致网格
均匀随机”，不是拿到实际后续对阵后逐场猜。正式正文保留三位小数即可；研究附录保留全精度、
公式与 run ID。

## 三、G / G-Lite 使用的 Roll 概率

### 3.1 哪些是 Valve 客户端事实，哪些只是 Primary 模型

本节的“客户端”特指仓库最新冻结的 8 月 13 日快照，不等同于对 8 月 17 日正在运行客户端的
实时复核。该快照的 `fantasy_crafting.vdata` 与 8 月 6 日 Group 快照在本节涉及的 operation、
Quality、Trait 和 Stat 字段上相同；这只能说明两次已冻结观察一致，不能证明后台 GC 抽样器。

客户端快照 [`fantasy_crafting.vdata`](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata)
直接给出：

- 每组显示 3 个操作；
- 20 个正权重 operation（ID `9–17,23–33`）及各自 `m_nRollWeight`，权重和为 `168`；
- Quality T1–T5 权重 `10/20/10/5/2`；
- 五种 Trait 与每色六种合法 Stat 的支持集；
- 操作作用于 All color / One random / First / Last 等目标的结构。

这些“字段和值”属于 **A 级、可信度很高**。但客户端没有公开 GC 的完整抽样函数。生产
`client-weight-primary-v1` 另外声明：

1. offer 按 operation 权重顺序无放回抽 3 项；
2. Quality 按 `10/20/10/5/2` 归一化；
3. Trait、同色 Stat 和随机目标在合法支持中均匀；
4. 重随允许重复当前属性；
5. 多格属性抽取条件独立；
6. Quality 增减目标均匀，越界 clamp；
7. replacement offer 与先前状态独立。

第 1–2 项有客户端权重字段支撑，但具体抽样算法仍未公开；第 3–7 项是明确的项目假设。
规范化声明见 [`ti2026.json`](../../config/rules/ti2026.json#L83-L101)，执行见
[`roll.py`](../../src/ti_predictor/fantasy/roll.py#L705-L803)。因此下面所有百分比都必须加前缀：
**“在 Primary Roll transition model 下”**，不能写成“Valve 官方出率”。

此外，当前快照和规范化配置都没有给出“初始 15 格属性 + 首组 3 个 offer”的联合分布。不得把
下面的重随 transition 权重反向当成初始画面出率；G / G-Lite 对当前 15 格和当前 offer 都以
玩家的直接观测为输入。

### 3.2 三项 offer 的完整 operation 边际概率

Primary 模型对有顺序 offer `(i,j,k)` 使用：

```text
P(i,j,k) = w_i/168 × w_j/(168-w_i) × w_k/(168-w_i-w_j)
```

共有 `20P3=6,840` 个有顺序 offer、`C(20,3)=1,140` 个无序三项集合。下表“首位概率”是该
operation 第一抽出现的概率；“三项中出现”已把它在第一、第二或第三位置的概率相加。

| ID | 当前客户端操作 | 权重 | 首位概率 | 三项中出现 |
| ---: | --- | ---: | ---: | ---: |
| 9 | 全部红色徽标重随 Quality | 10 | 5.9524% | 17.7257% |
| 10 | 全部红色徽标重随 Trait | 10 | 5.9524% | 17.7257% |
| 11 | 全部红色徽标重随 Stat | 10 | 5.9524% | 17.7257% |
| 12 | 全部蓝色徽标重随 Quality | 10 | 5.9524% | 17.7257% |
| 13 | 全部蓝色徽标重随 Trait | 10 | 5.9524% | 17.7257% |
| 14 | 全部蓝色徽标重随 Stat | 10 | 5.9524% | 17.7257% |
| 15 | 全部绿色徽标重随 Quality | 10 | 5.9524% | 17.7257% |
| 16 | 全部绿色徽标重随 Trait | 10 | 5.9524% | 17.7257% |
| 17 | 全部绿色徽标重随 Stat | 10 | 5.9524% | 17.7257% |
| 23 | 随机一格 Quality +1 | 4 | 2.3810% | 7.3762% |
| 24 | 随机两格 Quality +1、另一格 -1 | 8 | 4.7619% | 14.3741% |
| 25 | 随机一个红色徽标重随 Quality | 10 | 5.9524% | 17.7257% |
| 26 | 第一个红色徽标重随 Quality | 6 | 3.5714% | 10.9236% |
| 27 | 最后一个红色徽标重随 Quality | 6 | 3.5714% | 10.9236% |
| 28 | 随机一个蓝色徽标重随 Trait | 10 | 5.9524% | 17.7257% |
| 29 | 第一个蓝色徽标重随 Trait | 6 | 3.5714% | 10.9236% |
| 30 | 最后一个蓝色徽标重随 Trait | 6 | 3.5714% | 10.9236% |
| 31 | 随机一个绿色徽标重随 Stat | 10 | 5.9524% | 17.7257% |
| 32 | 第一个绿色徽标重随 Stat | 6 | 3.5714% | 10.9236% |
| 33 | 最后一个绿色徽标重随 Stat | 6 | 3.5714% | 10.9236% |

按操作族汇总：

| 操作族 | 首抽属于该族 | 新三项 offer 至少含一个 | 每组期望个数 |
| --- | ---: | ---: | ---: |
| Quality 重随（ID 9/12/15/25/26/27） | 30.9524% | 69.5912% | 0.9275 |
| Trait 重随（ID 10/13/16/28/29/30） | 30.9524% | 69.5912% | 0.9275 |
| Stat 重随（ID 11/14/17/31/32/33） | 30.9524% | 69.5912% | 0.9275 |
| Quality 增减（ID 23/24） | 7.1429% | 21.0304% | 0.2175 |
| 任意 Quality 相关（重随或增减） | 38.0952% | 78.8179% | 1.1450 |

若把 ID 23/24 归入 Quality，整组 3 个 offer 的属性族构成如下；`Q/T/S` 分别是 Quality
相关、Trait 重随和 Stat 重随操作。它是三格**联合构成**，不能与上表“至少出现一次”的边际
概率相加：

| Q 个数 | T 个数 | S 个数 | Primary 概率 |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 3 | 1.8913% |
| 0 | 1 | 2 | 8.6997% |
| 0 | 2 | 1 | 8.6997% |
| 0 | 3 | 0 | 1.8913% |
| 1 | 0 | 2 | 10.6764% |
| 1 | 1 | 1 | 25.8908% |
| 1 | 2 | 0 | 10.6764% |
| 2 | 0 | 1 | 13.7332% |
| 2 | 1 | 0 | 13.7332% |
| 3 | 0 | 0 | 4.1079% |

这些是 **C 级条件派生**；作为 Primary 模型内部数值可精确复算，但作为真实后台出率只能列为
**E 级、可信度中低**。

### 3.3 Quality 重随结果

Primary 模型允许重随到当前 Tier；每个目标槽按客户端 Quality weight 独立抽取：

| Quality | 加成 | 客户端权重 | Primary 条件概率 |
| ---: | ---: | ---: | ---: |
| T1 | +10% | 10 | 21.2766% |
| T2 | +30% | 20 | 42.5532% |
| T3 | +60% | 10 | 21.2766% |
| T4 | +100% | 5 | 10.6383% |
| T5 | +150% | 2 | 4.2553% |

客户端对 Quality 提供显式权重，因此支持强于 Trait/Stat；但“允许重复当前 Tier”和“多格独立”
仍未由 GC 源码或受控大样本认证，真实出率可信度为中等偏低。

Web 同时计算 flattened / sharpened 的动作一致性提示，但 G/G-Lite 的正式选择仍以 Primary 为主：

| 模型 | 权重变换 | T1 | T2 | T3 | T4 | T5 | 用途 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| flattened-weights-v1 | `sqrt(w)` | 21.8889% | 30.9555% | 21.8889% | 15.4778% | 9.7890% | 敏感性 |
| client-weight-primary-v1 | `w` | 21.2766% | 42.5532% | 21.2766% | 10.6383% | 4.2553% | 生产主模型 |
| sharpened-weights-v1 | `w^2` | 15.8983% | 63.5930% | 15.8983% | 3.9746% | 0.6359% | 敏感性 |

Primary 的原始权重来自客户端；flattened / sharpened 是项目刻意构造的上下压力情景，不是从
Valve 数据拟合出的另外两套真实概率，也不能把三行平均成“综合出率”。它们的用途只是在动作
排序随合理扰动翻转时降低建议置信度。

### 3.4 Trait 与 Stat 重随结果

客户端只给出 Trait / Stat 的合法列表，没有逐 Trait 或逐 Stat 权重。Primary 因而使用均匀分布：

| 属性 | 合法结果 | Primary 条件概率 | 来源与可信度 |
| --- | --- | ---: | --- |
| Trait | Fractal / Benevolent / Vampiric / Unique / Friendly | 每项 20% | 支持集 A；均匀与允许重复为 E，可信度中低 |
| 红 Stat | kills / deaths / creep_score / gpm / madstone_collected / tower_kills | 每项 16.6667% | 支持集 A；均匀与允许重复为 E，可信度中低 |
| 蓝 Stat | wards_placed / camps_stacked / runes_grabbed / smokes_used / watchers_taken / lotuses_gained | 每项 16.6667% | 同上 |
| 绿 Stat | roshan_kills / teamfight_participation / first_blood / stuns / tormentor_kills / courier_kills | 每项 16.6667% | 同上 |

如果后台排除当前值，则 Trait 当前值概率会从 Primary 的 20% 变成 0、其余四项各 25%；Stat
当前值会从 16.6667% 变成 0、其余五项各 20%。现有生产模型没有采用这一变体，研究只用
`repeat-suppressed-v1` 做敏感性压力测试。

### 3.5 随机目标与 Quality 增减

Primary 对目标的条件概率如下：

| 操作 | Primary 条件分布 | 越界处理 | 可信度 |
| --- | --- | --- | --- |
| One random matching color | 在该 Banner 所有匹配槽中均匀选一格，即每格 `1/m` | 不适用 | 目标支持 A；均匀 E |
| First / Last matching color | 位置确定 | 不适用 | A / C，高 |
| All matching color | 所有匹配槽都变；各槽属性结果独立 | 不适用 | All 支持 A；独立 E |
| ID 23：一格 +1 | 五格各 `1/5=20%` | T5 clamp 为 T5，可出现状态不变 | 均匀/clamp 均为 E |
| ID 24：两升一降 | 降级槽 `1/5`；其余四格选升级 pair 为 `1/6`；30 个 assignment 各 `1/30=3.3333%` | T1/T5 clamp；不同 assignment 可能合并为同一结果 | 均匀/clamp 均为 E |

实际 Main 颜色数使随机一格的概率依赖 Banner：

| 随机 operation | Core | Mid | Support |
| --- | ---: | ---: | ---: |
| ID 25：随机红 Quality | 3 格，各 33.3333% | 2 格，各 50% | 无红色，不可应用 |
| ID 28：随机蓝 Trait | 无蓝色，不可应用 | 1 格，100% | 3 格，各 33.3333% |
| ID 31：随机绿 Stat | 2 格，各 50% | 2 格，各 50% | 2 格，各 50% |

真实后台是否会在 T1/T5 重抽目标、是否会让全色多格共享同一结果，客户端没有说明。不能用上表
反推 Valve 真正实现。

### 3.6 G 与 G-Lite 到底怎样使用这些概率

策略目录由
[`fantasy-main-advice-strategies-v1.json`](../../config/models/fantasy-main-advice-strategies-v1.json#L1-L39)
冻结，文件 SHA-256 为
`4a90ec6d3b33664b6099e4af4ca74b55b333eb3cf2839e5be717fb71c522e218`。

| 策略 | 当前 offer 的来源 | 当前操作结果概率 | 未知 replacement offer | 证据状态 |
| --- | --- | --- | --- | --- |
| G（默认） | 玩家已观察到，不赋先验 | Primary；同时展示 flattened/sharpened 动作敏感性 | **不估值、不生成**；执行后重新读完整画面 | 生产默认；不是 30 步全局最优 |
| G-Lite（可选） | 玩家已观察到，不赋先验 | Primary | 只在一步前两名差距 ≤ 当前值 0.05% 时，对两候选各抽 4 个确定性下一步样本；改选需 ≥0.01%，每局最多触发 4 次 | `development-positive-user-opt-in-not-confirmed` |

G 的当前一步评价见
[`main_current_advisor.py`](../../src/ti_predictor/fantasy/main_current_advisor.py#L268-L354)；刷新动作的
当前终局值等于不改 Banner 的当前值。G-Lite 的 replacement offer 与 mutation 抽样见
[`main_advice_policy.py`](../../src/ti_predictor/fantasy/main_advice_policy.py#L117-L152)，有限二步门槛见
[`main_advice_policy.py`](../../src/ti_predictor/fantasy/main_advice_policy.py#L187-L303)。

因此正式说明里不应写“G 和 G-Lite 都预测未来每一次选项”。准确说法是：**两者共享当前动作
结果模型；只有 G-Lite 的有限二步触发会使用未来 offer 分布，G 在每次真实操作后依赖用户提供
新的已观察画面。**

### 3.7 建议写入 Main 玩家手册的可信度表

| 内容 | 原始来源 | 等级 | 建议公开措辞 |
| --- | --- | --- | --- |
| 三项共享 offer、20 个正权重操作、各 operation target | Dota 客户端规则快照 | A | 当前客户端已确认 |
| operation / Quality 暴露权重 | Dota 客户端 `m_nRollWeight` | A | 客户端暴露的相对权重 |
| 顺序加权无放回生成 offer | Primary 模型 + `roll.py` | E（条件派生为 C） | 当前最佳支持估计，不是 Valve 官方出率 |
| Quality 归一化概率 | 客户端权重 + Primary | C/E | Primary 条件概率 |
| Trait / Stat / 随机目标均匀 | owner policy + `roll.py` | E | 未认证假设 |
| 可重复当前值、多格独立、越界 clamp、replacement 独立 | owner policy + `roll.py` | E | 未认证假设；已做敏感性检查 |
| G 当前一步 | 生产策略目录和代码 | C/D | 默认的模型条件策略，不是全局最优证明 |
| G-Lite 有限二步 | 100 个合成开发状态 | E | 用户自选；尚未独立 confirmation |

## 四、复现身份与核查命令

### 4.1 关键文件哈希

| 文件 | SHA-256 / 语义身份 |
| --- | --- |
| `artifacts/bracket-eb209f6fad530148/model.json` | `18055527f5e99712d26eab3c66dc957c80e17672cbe8838368991b7721ed2f01` |
| `artifacts/bracket-eb209f6fad530148/recommendations.json` | `c2b641ad64fa47bcefa6875878a89dbaca438cdc3f170789ca0ebdd728eaa6d5` |
| `artifacts/bracket-eb209f6fad530148/run.json` | `6121d6c400f24159396e1d76c5cd7b2cde8f50aa16f38808010b7ca44bbbf04e` |
| `config/rules/ti2026.json` | `401e8d89222320d42eac3dba3b97d2f9b72b97134c4e707a558c97f7ebed2f60` |
| `fantasy_crafting.vdata`（客户端快照内） | `ebd26ec79c49c055beecdf1d55ac0175b88df0f0c22e6447a6b38baec5b5efd9` |
| 规则快照语义 hash | `9728c506baf6b5b2a706d0c70e4869fc6354c543d0cb4b911a4bf8427276bf06` |
| Team-strength policy 语义 hash | `4895101201e20afd5baf5fecfb46cf171b58285f044a90a84afa4b96ef23875f` |
| Main strategy catalog 文件 | `4a90ec6d3b33664b6099e4af4ca74b55b333eb3cf2839e5be717fb71c522e218` |

`run.json` 记录的 bracket 运行源码身份为
`047305d7cea97698572ddea94d3d2d53fdd7321d-dirty-db9b26b90312`。它如实包含本次交叉拓扑修正，
但仍带 dirty tree 标记；因此正式发布若要求“运行源码完全 clean”的更高门槛，应在不改变输入的
前提下从提交后的同一源码重生 artifact。本文所有矩阵与积分值仍绑定上表文件 hash，可从冻结
JSON 唯一复算；不能拿其他运行的源码身份替代这个独立 Bracket 运行身份。

### 4.2 复现核查命令

```powershell
Get-FileHash -Algorithm SHA256 `
  artifacts/bracket-eb209f6fad530148/model.json, `
  artifacts/bracket-eb209f6fad530148/recommendations.json, `
  artifacts/bracket-eb209f6fad530148/run.json, `
  config/rules/ti2026.json, `
  config/models/fantasy-main-advice-strategies-v1.json

# 查看客户端快照中规范化后的 points / Quality / operation 证据
$snapshot = Get-Content -Raw `
  data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json | ConvertFrom-Json
$snapshot.observed.main_cumulative_points
$snapshot.observed.fantasy_roll.qualities
$snapshot.observed.fantasy_roll.operations |
  Where-Object roll_weight -gt 0 |
  Select-Object operation_id, roll_weight, operation_target, mutations
```

两两矩阵只读取 `model.json` 中的 `ratings / glicko_ratings / glicko_deviations / scale /
ensemble_weights`，按 1.1 的公式生成。积分审计用
`BracketEngine.enumerate()` 各生成一次 16,384 个赛果路径和候选网格，再对全部
`16,384 × 16,384` 组合应用客户端 `R(k)`；这是确定性枚举，不是随机模拟。

## 五、更正与发布动作

游戏内截图暴露出原拓扑并非单纯的文档问题，必须修正共用求解逻辑。当前更正范围为：

1. `BracketEngine` 的败者组第二轮改为交叉接入：LB R2 A 接 UB Semi B 败者，LB R2 B 接
   UB Semi A 败者；
2. 新增精确拓扑回归测试，并验证淘汰赛 Forecast 与 Main Fantasy 共用同一修正后的路径枚举；
3. 重新生成 bracket、Main 五格 Solver Release、通用 Main Fantasy 与玩家出版证据；
4. 用更正后的 16,384 个合法网格更新发布报告、概率参考、树状图、公共 bundle、manifest 与 ZIP。

两两队伍胜率没有变化；变化来自“哪支胜者组败者会遇到哪支败者组首轮胜者”。因此旧
`bracket-6702d61436d49c8a` 及其 4.0000 / 1491.969 / 2647.872 等拓扑派生值均已作废，不能与本次
更正后的发布结果混用。
