# P6 Read-only Human Roll playbook cross-audit

状态：**`partial-draft`；完成 9/108 行，两版手册仍为 `draft`**
冻结日期：2026-08-06
显式 `as_of`：`2026-08-06T08:15:00Z`

## 目标与不对称边界

P6 只读比较两份冻结的 Human Roll playbook、P5 Branch-capped solver 与条件精确
oracle。它可以发现并披露反例，却不能从 solver 分歧中生成规则、修补手册或把 P4
的 `draft` 升级为可靠。如果未来要改规则，必须另建新版，从独立推导开始并重做 P4。

条件精确部分只能在剩余 1–3 次 Roll 时穷举 mutation、后续动作与 Group 表现；
未条件化的未来 offer 随机性仍没有积分。因此它是末期反例审计，不是对前中期或完整
40-Roll 手册可靠性的新证明；前中期的正式依据仍是 P4 的完整会话独立验证。

## 冻结输入

- 配置：`config/models/fantasy-group-read-only-cross-audit-v1.json`；
- P4 evidence：`a0361a228629c46663fe844387af7f71eea37113838b3036dc6181dd227ad857`；
- P5 clean evidence：`eb6a399d19653377ec20757e17c195cd3bac32e66b2dad2bddd411abb82e80d7`；
- P5 solver policy：`9466049f426e10c03926152c9cf60ecd9a4b96c155c19389456f2a5b73e5d3d9`；
- P3 source scenarios：`872533c3a40cb8a23bb90158234fca40294b940631805ae192d0813ec699e6a2`；
- 冻结手册：Rate-agnostic `cf6d2e5c…`，Primary-model `f710f7d2…`。

P6 将从 8,192 个 P3 公共情景索引中固定抽取 128 个，且明确排除 P4 的 512 个验证
索引和 P5 的 128 个验证索引。“随机种子不同”不充当留出证明；产物必须报告两个旧
子集的实际交集数以及 P6 与它们的交集为零。

## 冻结审计矩阵

九个 P4 Starting-state coverage case 全部保留其原始当前 offer。对每个 case 设置
`remaining Rolls = 1, 2, 3`，后续 offer 按下一个 coverage case 循环取值。这样覆盖九组
原始操作，不重复 P5 只用 `23/24/26` 的狭窄条件。

| 手册 | 模型范围 | 默认 ε | 行数 |
| --- | --- | ---: | ---: |
| Rate-agnostic | Primary / Flattened / Sharpened | 1% | 81 |
| Primary-model | Primary | 2% | 27 |
| 合计 |  |  | 108 |

每行记录人工手册动作与规则 ID、solver preferred/executed 动作及 unresolved、oracle
动作、均值/CVaR10 条件损失和分歧。只对在 P4 相同 edition×model×case 中会话频率
至少 10% 的实际规则触发计算 2,000 次独立加权 outcome bootstrap 单侧 95% 上界。
该方法比不加权或把路径当独立 Game 更符合当前分布，但不冒充 Series-cluster P4
确认，也不用于升级可靠性。

## 冻结显著例外与发布规则

一行只有在下列条件之一成立时才是 Playbook-significant exception：

1. 它是 P4 Common 规则触发，且 Expected score 或 CVaR10 条件损失的单侧 95% 上界
   超过 10%；
2. 它是 P4 Common 触发，且人工动作的条件精确均值和 CVaR10 都严格低于花一次
   Roll 刷新。

5% 只是更严格标记。solver 分歧、稀有状态或不容易解释的差异一律披露，但不产生新
手册分支。P6 最终只能依据 P4 已记录 gate 和本次审计完整性输出
`baseline-reliable`、`strict-reliable`、`draft` 或 `inapplicable`。由于两版 P4 已是
`draft`，P6 不可能把它们升级。

## 运行时与失败语义

目标为 1,800 秒，硬上限为 3,600 秒。每一行开始前用最近耗时预测是否会越过目标；
如果会，停止新行并写出 partial artifact。未完成 108 行、留出索引不交或来源 hash 不一致
都不得输出完整审计。任何失败只继续保留 `draft`，不修改手册、不自动启用 Full planner。

实装后只向本文档追加实测结果、证据包身份和最终标签；上述规则不根据结果回填。

## 实装与正式运行

P6 实装了强类型冻结配置、P4/P5 索引重建和显式差集抽样、人工/solver/oracle 三方
动作对齐、只对 Common 触发的加权 bootstrap、发布标签和不可反向修改手册的检查。
正式逻辑仅位于 `src/`，默认测试离线且确定。实装提交为
`58036bdb6fa3c6a89ac4ef57bb12a755d625e2ca`，全量验证为 `121 passed, 1 skipped`。

正式 run 为 `fantasy-9dd6d0012634bda5`，语义 evidence SHA-256 为
`b500065b609bba0cdc99aead49ad16fdd8d90bc27803ce5977bee2b1acba580d`，artifact 文件
SHA-256 为 `09a0f57e074eb9acd3a30a63f9889d470521401694e721230063b43d0dd57ccb`。

| 阶段 | 耗时 |
| --- | ---: |
| 来源身份与上下文重建 | 14.06s |
| 只读交叉审计 | 2,379.67s |
| 总计 | 2,393.73s（39 分 54 秒） |
| 已完成行中位数 | 15.39s |

运行完成 Rate-agnostic×Primary model 的 coverage-01 至 coverage-03、每个 1/2/3 Roll，
合计 `9/108` 行。coverage-03 的原始 offer 同时含整色品质、精确 Trait 和整色 Stat；
horizon=3 的状态分支远大于 P5 固定 `23/24/26` 的品质 offer，使这一个已启动的
exact 行耗时超出最近行中位数。完成它后，运行器在下一行前预测已越过 1,800 秒
目标并停止。因此没有启动其他两个 Rate-agnostic 模型或 Primary-model 版，也不能用这
9 行代表完整矩阵。

## 留出、分歧与损失结果

P4 的 512 个验证索引与 P5 的 128 个验证索引实际重叠 `5` 个；这证明只换 seed
不能保证不交。P6 的 128 个新索引是从两者并集的差集中抽取，与 P4/P5 交集均为
`0`。留出情景 SHA-256 为
`6b25f08e0a48cb2da3a936eec5a00de6695f5272db43481b28ea758a7ad4e6dc`。

9/9 行的实际手册规则触发都是 P4 Common。聚合结果为：

| 指标 | 结果 |
| --- | ---: |
| 人工动作 ≠ solver preferred | 8/9 |
| 人工动作 ≠ 条件 oracle | 7/9 |
| solver unresolved | 5/9 |
| 最大均值点损失 | 3.23% |
| 最大 CVaR10 点损失 | 1.44% |
| Common 均值损失单侧 95% 上界最大值 | 5.11% |
| Common CVaR10 损失单侧 95% 上界最大值 | 5.76% |
| 10% baseline 重大例外 | 0/9 |
| 5% strict 标记 | 2/9 |

两个 strict 标记是：

- coverage-01、剩余 3 Roll：RA01 选 `support:23`，oracle 选 `core:31`；均值/CVaR10
  点损失为 1.69%/1.12%，CVaR10 单侧上界为 5.76%；
- coverage-03、剩余 3 Roll：手册 fallback 刷新，oracle 选 `core:17`；均值/CVaR10
  点损失为 2.82%/1.19%，均值单侧上界为 5.11%。

它们没有越过冻结的 10% 基线线，也没有人工动作在均值与 CVaR10 上同时被刷新严格支配，
所以不是 v1 Playbook-significant exception。但它们是明确的 5% 严格层警告。由于审计只有
9/108，“未发现 10% 例外”绝不表示其余 99 行通过。

## P6 gate 与证据包标签

| Gate | 结果 | 原因 |
| --- | --- | --- |
| 来源身份 | 通过 | P3/P4/P5、手册、规则与配置 hash 一致 |
| P6 留出不交 | 通过 | 与 P4/P5 索引交集均为 0 |
| 手册 hash 未改 | 通过 | 两个 semantic hash 与 P4 一致 |
| 108 行审计完整 | 失败 | 只完成 9 行，单个广分支 horizon=3 行使目标超时 |
| Rate-agnostic 发布标签 | `draft` | P4 本已为 draft，P6 不完整且不得升级 |
| Primary-model 发布标签 | `draft` | P4 本已为 draft，Primary-model P6 行尚未运行 |

P6 状态为 **`partial-draft`**。`ti audit fantasy-9dd6d0012634bda5` 返回
`status: warning`，并校验产物文件 SHA-256 为
`09a0f57e074eb9acd3a30a63f9889d470521401694e721230063b43d0dd57ccb`。通用
`publishable: true` 只表示 artifact 完整性没有 blocking issue；不会把 partial 审计或两份 draft
手册变成可发布推荐。

此次结果不修改任何手册规则，不启用 Full planner。P7 只能在实验性 UI 中显示手册、
安全基线、一步估值和按需 P5 solver 之间的分歧；不能用 P6 partial 补全未知分支。
