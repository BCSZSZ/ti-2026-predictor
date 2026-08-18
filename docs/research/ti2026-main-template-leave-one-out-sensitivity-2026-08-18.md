# TI 2026 Main 历史模板 Leave-One-Out 敏感性测试

- 测试日期：2026-08-18
- 数据截止：`2026-08-16T15:31:30Z`
- 条件化证据：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b`
- 证据 manifest SHA-256：`e43bfaaad33cc4e3be7428d45548e66a83baabe8a7d0d23148ba74a9c5a936dd`
- 个人终局状态：`config/research/states/ti2026-main-zero-roll-screen-20260818.json`
- 终局状态 SHA-256：`efbe026895b5eb7970187db1fdbd7534f6d7d497fc70c930b04150f155b578cb`
- 测试边界：定向移除一个高集中 Game 或其所属 Series；没有遍历全部 863 Game / 358 Series
- 发布边界：没有修改 Web、求解器 release、正式配置或 runtime pointer

## 结论

问题已被定向反事实测试确认：**当前用户终局 Core 推荐会被 Falcons 的一个历史 Game 模板翻转。**

在原始完整条件化面板中，Core 推荐为 Team Falcons；从候选池彻底排除一个 Falcons 历史 Game 后，
Falcons Core Mean 下降 8.084%，从第一跌到第四，推荐改为 TEAM VISION。排除该 Game 所属的整个历史
Series 后，Falcons Mean 下降 6.082%，也从第一跌到第四。

这证明当前结果不是只在概率引用层面“看起来集中”，而是对单个历史观测不稳健。该观测本身不一定错误，
但单个 Game 能改变正式 Team 选择，已经超过适合直接发布为高精度终局结论的稳健性范围。

增加 inner samples 或直接把 83.4 MiB 全包接入 Web 都不会修复这个问题；它们只会更精确地复现当前
高集中的经验分布。

## 测试设计

### 为什么只选这两个目标

先前集中度审计显示：

- Falcons 使用率最高的 Series 占其全部加权 future Series-side 引用 29.72%；
- 该 Series 中使用率最高的单个 Game 占 Falcons 全部加权 future Game 引用 11.94%；
- Nigma Galaxy 的最大 Series/Game 份额更高，分别为 32.50% / 14.10%，因此作为“高集中但当前领先
  很大”的对照。

测试没有遍历所有模板，而是选择一个可能影响当前 Core 第一名的 Falcons 样本，以及一个 Mid 领先较大的
Nigma 对照，足以区分“集中但结论稳健”和“集中且改变结论”。

### 反事实定义

每个变体都保留：

- 相同 16,384 条完整双败路径及精确路径概率；
- 每条路径 16 个 inner samples；
- 相同三个 seed：`2026081701/02/03`；
- 相同 Team-strength 模型、Fantasy 规则、历史数据和用户最终 15 格；
- 相同层级回退规则。

只改变一个输入：

- `drop-game`：从所属 Series 的 Game 列表和所有 fallback Game 候选中排除目标 Game；
- `drop-series`：从所有 Series 候选中排除目标 Series，并从 fallback Game 候选中排除其所有 Game。

随后重新生成完整 future draw，而不是简单删除已经包含目标模板的情景。基线重生成的三个
`game_template_ids_sha256` 与原冻结 draw 完全一致，证明测试入口复现了原算法。

### 目标 Falcons 历史样本

- Series template index：`296`
- Series ID：`1130309`
- Series：Iron Wing vs Team Falcons，BO3，Falcons 1–2 失利
- Match IDs（时间顺序）：
  - `8944611964`：Falcons 失利
  - `8944695348`：Falcons 获胜
  - `8944764687`：Falcons 失利
- 被移除的 Game template index：`711`
- 对应 Match ID：`8944611964`

这个 Series 的 evidence weight 为 `2.190142`：在 Falcons 59 个 Series 中排第 4，约为 Falcons
Series weight 中位数 `0.200552` 的 **10.92 倍**。

在用户最终 Core Banner 下，Game 711 的 Core 模板分数为 `16,295.166`，在 Falcons 136 个 Game
模板中排第 6，位于约 96.32 百分位。它同时具有“抽样概率高”和“对该 Banner 得分高”两个条件。

## 三种子正式结果

### Core 推荐

| 面板 | Core 第一 | Falcons Mean | Falcons 排名 | 相对基线 |
| --- | --- | ---: | ---: | ---: |
| 原始基线 | **Team Falcons** | 31,562.966 | 1 | — |
| 排除 Game 711 | **TEAM VISION** | 29,011.344 | 4 | **-8.084%** |
| 排除 Series 296 | **TEAM VISION** | 29,643.279 | 4 | **-6.082%** |

原始基线中 Falcons 比 Vision 高 5.289%；排除单 Game 后 Falcons 比 Vision 低 3.222%；排除整个
Series 后低 1.114%。三个 seed 合并后两个反事实都翻转，因此不是单个 seed 的 Monte Carlo 偶然。

排除单 Game 后的 Core 前四：

1. TEAM VISION：29,977.328
2. BoomBoys：29,918.204
3. Team Spirit：29,756.229
4. Team Falcons：29,011.344

排除整个 Series 后的 Core 前四：

1. TEAM VISION：29,977.328
2. BoomBoys：29,918.204
3. Team Spirit：29,752.999
4. Team Falcons：29,643.279

### 为什么排除一局比排除整个 Series 降得更多

这不是“一个 Game 的价值大于整个 Series”的一般结论，而是现有分层回退与非线性 Top 2 的结果：

- 只排除 Game 711 时，Series 296 仍保留 29.72% 附近的高选择质量，但 Falcons 失利局只能更多使用该
  Series 中 Core 分较低的另一场失利 Game；
- 排除整个 Series 时，这部分概率转移到其他 Falcons 失利 Series，其中部分替代 Game 比上述低分局更好；
- 因而 leave-one-out 响应不要求单调，反而说明“选 Series -> 选 Game -> Top 2/max”的组合较脆弱。

### Nigma 高集中对照

用 seed `2026081701` 做探索性对照：

| 面板 | Nigma Mid Mean | 相对基线 | Mid 第一是否变化 |
| --- | ---: | ---: | --- |
| 基线 | 25,411.359 | — | 否，Nigma 第一 |
| 排除最大份额 Game 308 | 25,029.820 | -1.50% | 否 |
| 排除最大份额 Series 126 | 25,164.343 | -0.97% | 否 |

这说明“引用集中”不必然导致每个 Banner 都翻转；是否有问题取决于模板分数、当前 Banner 和原本名次间隔。
Falcons 案例则明确证明至少一个当前实际需要发布的推荐会翻转。

## 判定

当前 83.4 MiB 包不应原样升级为 Web 的正式高精度终局 terminal。原因不是计算时间，而是估计分布对单个
观测不稳健。现有结果仍可作为研究 baseline，但在解决模板集中前，不能把
`Falcons / Nigma / Vision` 标为高精度最终推荐。

建议为下一版预注册至少以下稳健性门槛：

- leave-one-Game 后目标 Team Mean 变化不超过 1%，除非该 Game 被明确建模为特殊状态；
- leave-one-Series 后 Mean 变化不超过 2%；
- 若基线第一与第二差距大于 1%，单 Game/Series 不得翻转第一名；
- 每个 Team×result 条件池必须报告 Series/Game ESS 和最大单模板概率；
- 超过门槛时结果降级为 warning，不得进入正式 Web pointer。

这些是建议讨论稿，不是已经冻结的发布规则。

## 三套解决方案

### 方案 A：受限混合 Bootstrap（最小改动）

保留真实五人联合 Game 模板，但不再把窄条件池直接当作完整未来分布：

1. 每次先选择数据层：长期 current-player/role、近期版本/赛事、相似胜负/对手/BO；
2. 三层使用冻结混合权重，而不是依次筛到最窄池；
3. 对单 Series 和单 Game 设置最大概率，超出部分重新分配；
4. 同一条 future Series 内尽量无放回抽 Game；
5. 若 ESS 不足，主动扩大长期池，而不是让三条 Series 承载绝大多数概率；
6. 发布前强制运行定向 leave-one-out。

优点：改动最小，继续保留五名选手的真实联合相关性和现有 Top 2/max 代码；最适合在 Main 开始前快速修复。

缺点：未来表现仍由离散历史模板组成，只是重复受控；不能生成历史上未出现的新五人 Stat 向量。

### 方案 B：长期 Player×Role 基线 + 有界近期/场景修正 + 联合残差（推荐）

这最接近用户提出的方向。针对每个当前选手、位置和 Stat：

```text
未来条件期望
= 长期 Player×Role 基线
 + 有界的近期版本/状态修正
 + 有界的胜负、对手强度、BO/比分修正
```

具体原则：

- 长期基线使用足够宽的 2026/相关版本历史，并保留现有时间衰减；
- 近期和相似比分不是硬筛选，而是 sample-size-aware 的 shrinkage adjustment；样本越少，修正越向零收缩；
- 任何单 Game 对均值参数的最大影响必须显式受限；
- 五名选手和 18 项 Stat 不能独立抽样：从较宽历史池抽一个共享 game-pace/team residual，再叠加到各选手
  条件均值，保留队内联合波动；
- 胜负、时长、对手强度等共享变量先生成，再生成 player-level Stat；
- 最后仍使用真实 Banner、Series Top 2 和阶段最大 Series 规则评分。

优点：既以长期表现为主体，又允许近期和类似局面提供额外信息；能合成历史上未出现的新表现，同时避免一局
被重复上万次。

缺点：需要估计 shrinkage 强度、联合残差和合法约束，必须滚动回测；实现量高于方案 A。

### 方案 C：完整联合比赛生成模型（最高上限）

构建双方十人共同的分层生成模型：

1. 先生成 Series 路径、Game 胜负、时长和比赛节奏；
2. 以双方 Team strength、阵容、角色、版本和对手为条件；
3. 联合生成十名选手的计数型、比例型和连续型 Stat；
4. 对击杀/死亡、团队事件等施加跨队守恒或一致性约束；
5. 用后验预测抽样生成未来 Game，不再引用单个历史 Game 作为最小单位。

可以使用分层 Bayesian count/continuous 模型、copula 或其他可校准的多变量生成结构，但必须和方案 A/B 以及
当前 bootstrap 做滚动时间回测。

优点：理论上最完整，能同时解决离散重复、双方不守恒和稀疏条件回退。

缺点：数据、实现和验证成本最高；在当前 Main 时间窗口内直接替换风险最大。

## 建议顺序

1. 短期先实现并验证方案 A，作为防止单模板主导的安全层；
2. 同时把方案 B 作为正式候选，因为它最符合“长期位置表现为主、近期与类似局面为修正”的目标；
3. 方案 C 保留为长期研究，不阻塞本次 Main；
4. 在 A/B 的同一冻结路径和用户 Banner 上比较 leave-one-out、时间回测和最终 Team 排名，再决定 Web 使用哪套。

不建议仅把当前 inner samples 从 16 增加到更大，也不建议只把现有 83.4 MiB 包原样接入 Web；两者都不会
改变单个历史模板的基础概率。

## 证据定位

- 抽样实现：`src/ti_predictor/fantasy/main_conditional_truth.py`
- 模板集中度审计：`docs/research/ti2026-main-conditional-fantasy-sampling-method-audit-2026-08-18.md`
- 冻结模板：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/templates.npz`
- 冻结路径：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/outer-paths.npz`
- 三个原始 draw：同目录 `draws-2026081701/02/03.npz`
- 定向研究 runner：`.scratch/main-template-sensitivity/run.py`
