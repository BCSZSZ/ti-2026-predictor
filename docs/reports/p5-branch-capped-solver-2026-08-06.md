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
