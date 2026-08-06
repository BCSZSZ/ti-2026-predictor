# P5 Branch-capped Reference Roll solver

状态：**实施前冻结；尚无求解器结果**  
冻结日期：2026-08-06  
显式 `as_of`：`2026-08-06T08:15:00Z`

## 目标

在不读取求解器结果来改写 P4 人工手册的前提下，实现 ADR-0003 的限枝参考求解器。它是
近似反例查找器和后续本地 advisor 的计算内核，不是人工手册、精确动态规划或“全局最优”
证明。

P5 只回答三个问题：当前合法动作如何在固定出率模型和风险容忍度下排序；简化求解器相对
短视与出率无关基线是否有可靠增益；这种近似能否在一小时预算内通过预先声明的有效性门槛。

## 冻结的最小实现范围

- 配置来源为 `config/models/fantasy-group-branch-capped-solver-v1.json`；输入必须显式携带
  `as_of`、规则快照、P3 情景、P4 证据 hash、模型、epsilon 和随机种子。
- 每个已观测决策根、每个 Banner 的当前 Stat 三元组完整枚举 `25^3 = 15,625` 个有位置的
  Quality×Trait 配置，并用 P3 同队匹配终局算术计算 Expected score 与 CVaR10。
- 在六个属性（三个 Quality、三个 Trait）的 Hamming 距离不超过三时，查找风险目标下的
  最佳配置；潜力乘数严格为 `(remaining Rolls - 1) / 39`，最后一 Roll 为零。
- 该表的 Stat 作用域只覆盖当前已观测决策根。模拟路径若改变 Stat，新 Stat 得到精确即时
  终局价值，但未来协同潜力为零；只有玩家确认真实结果并重新规划时才建立新表。这个限制是
  “Stats 无额外未来潜力项”的可执行解释，也是限枝边界，不得在看到结果后放宽。
- 根节点只展开当前最多九个 option×Banner 应用与一次 refresh。每个根动作通过一个固定、
  非递归 continuation 走完剩余 token；未来决策不再产生求解树。
- 每个模型与 `epsilon = 0%, 1%, 2%, 5%` 是独立运行。四条/action screening path 后只保留
  两名 finalist；finalist 使用十二条全新的 confirmation path。screening 样本不能进入最终
  置信结论。
- 无法在独立 confirmation 下区分领先动作时输出 `unresolved`，并执行 Rate-agnostic safety
  fallback；不得用稳定排序伪装成已解决。
- 生产代码只进入 `src/`，默认测试全部离线、确定性；Main 接口保留但执行必须 fail closed。

## 冻结的验证与验收

验证使用 P4 九个 Starting-state coverage case、固定 128 个 P3 common scenarios、三个出率
模型和四个 epsilon。每个格进行两条完整 40-Roll 独立路径；这个低样本配置优先保证一小时
硬预算，并可能诚实地产生大量 unresolved，而不是事后增加样本追逐通过。

P5 只有同时满足以下条件才算 effectiveness gate 通过：

1. 一至三 Roll 的分层可穷举状态中，决策 regret 的单侧 95% 上界不超过 2%；
2. 独立完整 40-Roll 结果在 Expected Group score 与 CVaR10 上，均未统计显著劣于
   one-step greedy 和 Rate-agnostic safety；
3. P4 定义的 Common playbook situations 中，unresolved session 比例不超过 10%；
4. 墙钟时间不超过 3,600 秒，估算路径总量不超过 2,400,000 条 40-Roll 等效路径；
5. artifact 明示模型依赖、近似边界和失败项，从不输出“globally optimal”。

Gate 任一项失败，都必须在本报告追加失败数据与 escalation review。失败不会自动启用 Full
configuration planner，也不会修改两份已冻结、当前仍为 draft 的 P4 手册。原三小时全规划器
继续只保存在 ADR-0003，除非未来另作明确决策。

## 实施前来源身份

- 冻结 P5 配置文件 SHA-256：
  `cb79f45fabe802930dc937dba9effc137be114453bd9b55d2d2a936b163ff5da`
- P4 clean-commit semantic evidence：
  `a0361a228629c46663fe844387af7f71eea37113838b3036dc6181dd227ad857`
- P4 validation policy：
  `19b505159bb7c42b93d952359932e26dd0434ff4ae9283738432784afe685865`
- P3 common scenario source：
  `872533c3a40cb8a23bb90158234fca40294b940631805ae192d0813ec699e6a2`
- Rule snapshot：`20260806T081345Z-702ddf2a6953`

后续章节只追加实现、基准和 gate 结果；上述参数与失败语义不根据结果回填修改。

## 实装结果

P5 已实现以下正式路径：

- `solver.py`：冻结配置校验、15,625 配置的向量化精确终局表、每个状态 1,545 个
  Hamming≤3 邻居、协同潜力、非递归 continuation、root rollout、独立 confirmation、
  unresolved safety fallback，以及条件化的一至三 Roll 穷举 oracle；
- `solver_validation.py`：复用 P4 九格起点、配对完整会话、one-step greedy 与
  Rate-agnostic safety 基线、Common-situation unresolved 统计和预注册 gate；
- `solver_reporting.py` 与 `ti fantasy group-solver-evidence`：强制显式 `as_of`，核对 P4
  evidence、P3 pool/scenario 和 Rule snapshot 身份，按一小时边界停止新增完整单元并写出可审计
  partial artifact；
- 默认离线测试覆盖 15,625 索引往返、1,545 邻域的完整性、epsilon→CVaR 选择、向量化表与
  原 P3 终局算术等价、独立 confirmation、条件 oracle、P4 coverage 复用和失败门禁。

Human playbook 模块没有 import solver；P5 没有修改 P4 两份手册、规则配置或其冻结 hash。
Main 仍由 P2 状态校验 fail closed。

## 正式证据运行

运行 `fantasy-7611686c6c0f92e7`，语义 evidence SHA-256 为
`c9e9daeb4fcc6c7389dfd4ebb84473727798a93c4b2e41fbe363cd634a49252c`，artifact 文件
SHA-256 为 `1b7ae1fd184e33e49100dc0530e8a1186726b2f3f8005fabe40e493436e1bf4c`。

墙钟分段如下：

| 阶段 | 秒 | 说明 |
| --- | ---: | --- |
| 上下文重建 | 13.02 | 核对数据、P3 scenario、P4 artifact 与规则快照 |
| 18 个条件 oracle | 69.14 | 1/2/3 Roll × 6 个 coverage case |
| 完整会话验证 | 3,476.33 | 完成 7 个 solver + 两基线配对单元 |
| 总计 | 3,558.49 | 59 分 18 秒，未越过 60 分钟 |

完整计划为 216 个 solver session；在完成 7 个单元后，运行器判断下一单元会越过冻结的一小时
目标并停止。已完成单元的中位配对时长为 `492.95s`。按该中位数线性投影，216 个单元约需
`106,477s = 29.58h`，远高于一小时。七条 solver session 合计 `8,128.1` 条 40-Roll
等效路径，线性投影完整计划约 `250,810` 条，仍低于 240 万 path ceiling；因此失败根因是
生产路径的每 path 状态估值与重复规划成本，而不是 path 数量上限本身。

## 有效性结果

### 短 horizon oracle

18/18 个固定未来 offer 日程的条件 oracle 全部完成。solver 与 oracle 的首选动作在 8/18 个
case 不同；最大单 case Expected-score regret 为 2.16%，最大 CVaR10 regret 为 4.81%。对每个
case 取两者较大值后，平均 regret 的单侧 95% 上界为 1.13%，数值上低于 2% 门槛。

但该穷举只在未来 offer 序列固定后，完整积分 mutation、后续动作和 128 个表现 scenario；
它没有积分下一次从 20 个正权重 operation 中抽取三项的全部随机性。它因此只能叫
`exact_for_declared_condition`，不能满足预注册的无条件一至三 Roll oracle gate。数值通过不被
升级为正式通过。

### 完整 40-Roll 诊断

时间边界只允许完成 Primary model、`epsilon=0%`、coverage-01 至 coverage-04 的前 7/216
session，不能代表其余两个模型、其他 epsilon 或全部九格。点估计和配对单侧 95% 下界如下：

| 比较 | solver 均值差 | 均值单侧 95% 下界 | solver CVaR10 差 | CVaR10 单侧 95% 下界 | 诊断 |
| --- | ---: | ---: | ---: | ---: | --- |
| vs one-step greedy | -4,394.87 | -11,095.26 | -65.53 | -20,525.51 | 失败 |
| vs Rate-agnostic safety | +8,395.21 | +3,717.75 | +6,502.14 | +351.23 | 通过（仅 7 条） |

对应点分为：solver `mean=55,679.51, CVaR10=42,854.14`；one-step greedy
`60,074.38 / 42,919.66`；Rate-agnostic safety `47,284.30 / 36,352.00`。solver 对
one-step 的均值和置信下界均较差，不能满足“不劣于两个基线”。

每条 solver session 的 40 个决策中有 19–33 个 unresolved；所有已观察到的 P4 Common
situation 都至少在一条 session 出现 unresolved，最大 unresolved session 比例为 100%，远高于
10% 门槛。这主要反映每 finalist 仅 12 条 fresh confirmation path 无法稳定区分，而不是一个
可用的强制排序结果。这里采用保守的 P4 `coverage case → Common situations` 连接，没有在
solver 路径上重放人工手册逐决策 activation；因此 100% 是 case-level 上界，不应解释为每条
具体手册规则的独立失败率，但它已经足以否决 ≤10% gate。

## Gate 与 escalation review

正式 gate 逐项为：

| Gate | 结果 | 原因 |
| --- | --- | --- |
| 无条件 1–3 Roll regret ≤2% | 失败 | 数值诊断通过，但只条件化固定未来 offer |
| 不劣于 two baselines | 失败 | 仅 7/216，且对 one-step 的均值/下界为负 |
| Common unresolved ≤10% | 失败 | 已观察 Common situation 为 100% |
| 完整验证 ≤60min | 失败 | 59:18 只完成 7/216；投影约 29.58h |
| 完整路径 ≤2.4m | 失败（不可判定） | partial 投影低于上限，但未完成冻结计划 |

P5 状态为 **`failed-escalation-review-required`**。此次 review 的决定是：

1. 不自动启用 Full configuration planner；它更复杂、更慢，不能修复当前验证吞吐与
   confirmation 样本不足；
2. 不让 solver 输出修补 P4 手册；两份手册仍保持各自的 `draft` 失败结论；
3. 保留 15,625 表、条件 oracle、确定性 rollout 和 saved-state 合约，供稀疏反例审计与 P7
   本地 UI 的明确“实验性/可能 unresolved”模式使用；
4. 若未来要重新争取 effectiveness gate，必须另开明确版本，首先改变 continuation/验证表示
   或预计算层，再冻结新预算；不能在 v1 结果后增加 path 数、放宽 10% unresolved 或把条件
   oracle 改名为无条件；
5. 原三小时 Full planner 继续作为 ADR-0003 的 dormant 设计记录，不进入当前实装路线。

`ti audit fantasy-7611686c6c0f92e7` 校验 artifact 文件 hash，返回 run `status: warning`。
通用 audit 的 `publishable: true` 只表示完整性检查未阻塞，不覆盖 P5 artifact 内明确失败的
effectiveness gate；该 solver 不应作为可靠或全局最优推荐发布。
