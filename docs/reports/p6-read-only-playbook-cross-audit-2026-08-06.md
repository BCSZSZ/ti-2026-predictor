# P6 Read-only Human Roll playbook cross-audit

状态：**实施前冻结；尚无 P6 结果**
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
