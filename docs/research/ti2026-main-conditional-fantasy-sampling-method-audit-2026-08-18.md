# TI 2026 Main 条件化 Fantasy 抽样方法审计

- 审计日期：2026-08-18
- 数据截止：`2026-08-16T15:31:30Z`
- 代码来源：`src/ti_predictor/fantasy/main_conditional_truth.py`
- 冻结证据：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b`
- manifest SHA-256：`e43bfaaad33cc4e3be7428d45548e66a83baabe8a7d0d23148ba74a9c5a936dd`
- 本次边界：只读核查与解释；未修改研究模型、Web、发布包或 runtime pointer

## 精确结论

当前方法既不是“复制一场完全相同的历史比赛”，也不是“根据历史均值生成一套新的连续 Fantasy Stat”。
它属于**条件化联合经验重采样**，可以理解为一种分层 bootstrap：

1. 未来 bracket 和 Series 胜负来自模型；
2. 未来 BO3/BO5 的合法比分序列由模型概率抽取；
3. 每个未来 Team-Series 侧先按宽条件选择一个历史 Series 作为来源上下文；
4. 每个未来 Game 再从历史 Game 中抽一个该队五名当前阵容选手的完整联合 Stat 向量；
5. 多个历史 Game 片段可以拼成一条此前从未真实发生过的未来 Series；
6. Banner 倍率、Series Top 2 和阶段最佳 Series 在最后统一计算。

因此，未来 Series 是合成的，但它的最小表现单元仍是一个真实历史 Game 的五人联合向量，而不是从统计分布
生成的新数值。

## 实际执行过程

假设一条 bracket 路径规定未来某场 BO3 为 Falcons 2–1 Liquid。

### 1. 先生成共同比分序列

冻结的单局 Team-strength 概率决定 Falcons 以 2–1 获胜的合法顺序概率。实现会抽一条例如：

```text
Falcons: Win / Loss / Win
Liquid:  Loss / Win / Loss
```

双方共享三局长度，每一局结果严格相反。它不会分别给双方抽出互相矛盾的 2–0 和 2–1。

### 2. 两个 Team 侧分别选择历史 Series 上下文

Falcons 一侧优先从以下历史 Series 中按 evidence weight 有放回抽样：

```text
Falcons + BO3 + Series Win + 未来对手强度带
```

Liquid 一侧则独立选择：

```text
Liquid + BO3 + Series Loss + 未来对手强度带
```

“对手强度带”只有 `<40% / 40%–60% / >60%` 三档，不要求历史对手就是未来对手，也不要求英雄、
时长、经济曲线等局面完全一致。样本不足时使用冻结的层级回退。

当前一个种子的 7,340,032 次 Team-Series 侧选择中：

| 回退层 | 保留条件 | 占比 |
| ---: | --- | ---: |
| 0 | Team + 格式 + Series 结果 + 对手带 | 68.6105% |
| 1 | Team + 格式 + Series 结果 | 19.3359% |
| 2 | Team + Series 结果 + 对手带 | 5.1060% |
| 3 | Team + Series 结果 | 0.6975% |
| 4 | Team + 格式 + 对手带 | 5.8036% |
| 6 | Team + 对手带 | 0.4464% |

Series 权重是组成该历史 Series 的比赛 `evidence_weight` 均值。它继承当前 Fantasy 的时间、版本、赛事
等级和阶段加权；TI 小组赛与突围赛 109 场使用 1.5 倍阶段权重。

### 3. 每一局再抽五人联合 Game 模板

对于 Falcons 的 `Win / Loss / Win`：

- Win 局优先从选中历史 Series 内 Falcons 获胜的 Game 中抽；
- Loss 局优先从同一 Series 内 Falcons 失利的 Game 中抽；
- 如果来源 Series 没有需要的单局结果，例如一个 2–0 胜利 Series 没有 Loss Game，则回退到
  `同 Team + 同单局结果 + 同对手带`，再不足则回退到 `同 Team + 同单局结果`。

一个种子的 19,133,422 次 Game 模板抽样中：

| 层级 | Game 来源 | 占比 |
| ---: | --- | ---: |
| 0 | 选中历史 Series 内 + 相同单局结果 | 88.9310% |
| 1 | 同 Team + 相同单局结果 + 对手带 | 10.8496% |
| 2 | 同 Team + 相同单局结果 | 0.2194% |

每次抽到的 Game 模板包含当前阵容五名选手在同一场历史比赛中的 18 项 Stat。五人必须同时具有要求的
provenance；缺失 Stat 不会补零。当前池因此从 4,555 场正权重 evidence 中进一步得到：

- 358 个当前阵容完整联合 Series；
- 863 个当前阵容完整联合 Game 模板。

同一来源 Game 可以有放回重复抽到。未来 Series 中的三局也不一定对应同一场历史 Series 的原始顺序；
它是按共同未来赛果约束拼接出来的经验 Series。

### 4. 对阵双方不是复制同一场历史比赛

Falcons 与 Liquid 只共享未来 Series 长度和相反的每局胜负。两边的五人模板在给定结果后独立抽取。
因此它不会要求历史上恰好存在 Falcons 对 Liquid 的同比分比赛，也不会复制一个完整历史对局的十人数据。

这保留了每一队内部五名选手的联合波动，但没有保留对阵双方 Stat 的完整十人守恒关系。例如双方模板的
击杀/死亡、比赛节奏未必能像同一真实 Match 那样逐项互相对应。这是当前 manifest 已公开的限制。

### 5. Banner 在最后才进入

冻结证据保留所有模板的 18 项 Stat。玩家提供 Banner 后：

1. 按五个 Stat、Quality 和 Trait 算出五项倍率；
2. 给每个历史 Game 模板计算该 Banner 下的综合分；
3. 每个未来 Series 取综合分最高两局之和；
4. 每个 Team 在整个 Main 阶段取最佳 Series；
5. 比较八队并选择每个位置的最高 Mean。

所以不能把一个历史 Game 预先压成“通用 Fantasy 总分”：不同玩家 Banner 选择的 Stat 不同。

## 为什么当前没有直接使用历史均值合成

如果分别对 18 个 Stat 或五名选手取平均再拼接，会破坏重要结构：

- 胜负、比赛时长、战斗频率和经济节奏共同影响多项 Stat；
- 同一队五名选手之间存在资源和事件分配关系；
- Kills、Deaths、Teamfight、GPM、守卫等并不独立；
- Series 内 Top 2 和阶段最大值依赖尾部与方差，不只依赖均值；
- `E[max(X)]` 不等于 `max(E[X])`，先平均会低估“多打 Series 带来的刷新机会”。

当前联合模板的主要优点就是保留真实的队内联合形状和尾部，避免产生“每个 Stat 都同时处于历史高位”的
不可能合成局。

## 用户担心的部分确实存在

当前方法也有明确不足：

1. 最小表现单元只能取历史上出现过的五人联合 Game 向量，支持集是离散的；
2. 当前阵容完整五人条件使部分 Team 的模板池较小；
3. 有放回抽样可能重复同一个表现模板；
4. 对手只按三档强度条件化，信息较粗；
5. 双方模板独立，不能生成完全守恒的十人比赛；
6. BO5 样本稀疏，Nigma Galaxy 和 Team Spirit 没有满足完整五人条件的历史 BO5；
7. 该方法不会生成介于两个历史表现之间的新连续 Stat 向量。

所以把它称为“研究真值”时，精确含义是相对当前 256 路径代理更完整的**模型条件化参考**，不是最理想的
未来表现生成模型。

## 个别历史 Series / Game 的集中度实测

针对三个冻结 seed 的全部 draw，按每条 outer path 的精确概率计算每支 Team 内部的模板引用份额：

```text
模板加权份额
= 所有引用该模板的 future draw 对应 path probability
 / 该 Team 全部 future draw 的 path probability 总和
```

这是“被抽到的概率质量”，不是最终 Banner 分数的因果贡献；Top 2 和阶段最大值还可能进一步放大或削弱
某个高分模板。但它可以直接回答经验分布是否集中。

| Team | Series 池 / 实际引用 | 最大单 Series 份额 | Series ESS | Game 池 / 实际引用 | 最大单 Game 份额 | Game ESS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Iron Wing | 52 / 43 | 21.40% | 6.57 | 125 / 109 | 8.72% | 18.14 |
| Team Liquid | 63 / 51 | 19.90% | 9.95 | 158 / 158 | 8.11% | 28.78 |
| Nigma Galaxy | 16 / 15 | **32.50%** | 5.96 | 34 / 34 | **14.10%** | 14.90 |
| TEAM VISION | 26 / 26 | 16.04% | 9.24 | 69 / 69 | 5.57% | 29.18 |
| BoomBoys | 84 / 35 | 32.13% | 6.40 | 200 / 95 | 13.15% | 18.18 |
| Team Falcons | 59 / 26 | 29.72% | 6.16 | 136 / 67 | 11.94% | 16.85 |
| Team Yandex | 30 / 24 | 23.37% | 6.56 | 77 / 63 | 9.57% | 17.70 |
| Team Spirit | 28 / 15 | 31.83% | **5.84** | 64 / 37 | 13.30% | 15.51 |

ESS 为 `1 / sum(share²)`。例如 BoomBoys 虽有 84 个 Series 模板，当前未来条件真正形成的加权有效数量
只有约 6.40；Nigma Galaxy 的单个历史 Series 占其全部 future Series-side 概率质量约 32.50%，该
Series 中两个失利 Game 模板各占 Nigma 全部 future Game 引用约 14.1%。

代码的 `minimum_conditioned_series=3` 只保证狭窄条件池不足三个 Series 时向外回退，不保证三个候选等权，
也不限制同一个 Series 被多个条件上下文重复使用。Series 仍按 evidence weight 有放回抽样；选中 Series 后，
相同单局结果的 Game 也有放回抽样。如果某一结果只有一两个 Game，它们会被大量重复引用。

因此应区分两句话：

- “存在完全对应的历史对局就自动采用它”——**不正确**。模型不匹配确切未来对手，也不会优先 exact
  head-to-head；它在至少三个候选的最窄可用池中加权抽样。
- “个别历史对局可能显著影响某队的未来 Fantasy 分布”——**正确，而且当前面板已经有可见集中度**。

把 inner samples 从 16 增加到 100 或更多，只会降低对这套集中经验分布的 Monte Carlo 误差；不会降低
某个历史模板本身被赋予的概率。要解决该问题，必须修改分布估计，例如权重上限、Team×result 分层平滑、
leave-one-Series-out 敏感性门槛，或改用分层条件生成模型。

## 如果要真正“根据历史表现合成一个 Fantasy”

不建议只用每名选手的历史平均分。更合理的候选是**分层条件均值 + 联合残差重采样**：

```text
未来五人 Stat 向量
= Team/Player/Role 的条件期望
 + 一次共享的 Game pace / duration / result 潜变量
 + 从历史联合残差中抽取的队内相关波动
```

条件至少应包含：

- 当前 Team 与当前阵容；
- 单局胜负；
- 对手身份或连续强度；
- 版本与时间权重；
- BO3/BO5 及 Series 上下文；
- Game duration / pace 等共享因子。

稀疏 Team/Player 条件用层级 shrinkage 向 Team、role、赛事级总体分布收缩。生成的五人×18 Stat 还需通过
联合约束或残差 bootstrap 保持合理相关性，而不是 90 个维度独立正态抽样。

这种模型能生成此前未见过的新表现向量，并减少小样本离散重复；但它必须和当前联合经验 bootstrap 做滚动
时间回测，至少比较：

- 每项 Stat 的均值、分位数和覆盖率；
- 五人/Stat 相关矩阵；
- 胜负和对手强度条件下的校准；
- Series Top 2 与阶段最佳 Series 分布；
- 最终 Team 排名稳定性；
- held-out 真实比赛的 log score、CRPS 或能量分数。

在这些验证完成前，不能仅凭“合成看起来更平滑”替换当前方法。当前 83.4 MiB 完整包可以先作为 Web 的
终局证据：它计算约十秒、方法已冻结且能复现；新的生成模型应作为独立 challenger，而不是直接覆盖。

## 代码与证据定位

- 完整五人历史模板构建：`main_conditional_truth.py:383`
- Fantasy evidence 加权：`main_conditional_truth.py:414`
- Series evidence weight：`main_conditional_truth.py:559`
- Series 条件与层级回退：`main_conditional_truth.py:633-670`
- Game 条件与层级回退：`main_conditional_truth.py:673-700`
- 16 个内层样本及比分序列：`main_conditional_truth.py:711-786`
- Series 有放回加权抽样：`main_conditional_truth.py:816`
- Game 有放回抽样：`main_conditional_truth.py:860`
- Banner 对模板的动态评分：`main_conditional_truth.py:1181`
- Series Top 2 与阶段最大值：`main_conditional_truth.py:1200-1225`
- 样本池审计：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/pool-audit.json`
- 抽样审计：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/draws-2026081701-audit.json`
