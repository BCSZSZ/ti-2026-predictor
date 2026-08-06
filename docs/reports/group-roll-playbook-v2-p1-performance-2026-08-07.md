# Group Roll playbook v2 P1 performance report

状态：**P1 已按“优化通过、v1 全矩阵仍受冻结目标阻断”收口**

日期：2026-08-07

显式 `as_of`：`2026-08-06T08:15:00Z`

## 阶段目标与最小范围

P1 只诊断并优化冻结 v1 P6 的计算路径，不改两份 Human Roll playbook、不改 P3
数值、Roll 规则、P5 策略语义或任何 v1 历史证据。起点为
`main@9192a61bea208e81e5f441f471018985e1798abe`，实装范围最终只有：

- `match_group_roles` 的候选组合枚举；
- 该边界上的性能回归和全枚举差分测试；
- 本报告与 v2 总计划状态。

验收要求是：小型测试可稳定复现原始工作量；输出与旧实现数值一致；108 行在 60 分钟
内完成，或明确记录仍然阻断它的条件；全量离线测试和工程级回归通过；不保留临时探针
或第二套生产实现。

## 诊断结论

冻结 v1 的正式 P6 曾在约 39 分 54 秒内只完成 `9/108` 行。最慢形态是包含整色
Quality、Trait 或 Stat mutation 的 `horizon=3` 状态；一个缩小后的固定 offer 探针产生
`200,312` 次终值 Group 估值。

逐项探测得到：

1. oracle 分布确实存在相同 support，但先合并 support 没有减少终值调用，反而增加排序
   成本，因此未采用；
2. 根 mutation outcome 没有重复 child state，不能靠根节点去重；
3. 缓存 mutation distribution 有大量命中，但没有降低墙钟，因此未采用；
4. 真正的热点是每次终值估值都在 `match_group_roles` 中遍历 `16^3 = 4,096` 个队伍
   组合，即使绝大多数组合仅凭角色均值就不可能达到全局 mean-retention floor。

在九个冻结 coverage case 上，安全必要条件把实际进入笛卡尔积的组合数缩小为：

| 风险膝点 | 原组合数 | 剪枝后候选范围 |
| --- | ---: | ---: |
| Rate-agnostic，epsilon=1% | 4,096 | 3–60 |
| Primary-model，epsilon=2% | 4,096 | 5–160 |

## 最小修复

设每个角色的最大均值之和为 `M`，全局允许最低均值为 `F`，则总均值损失预算为
`M-F`。若某队在自己的角色上相对该角色最大值的损失已经超过这个总预算，即便其他
两个角色都取最大值，也不可能达到 `F`。因此它可以在笛卡尔积之前排除。

实装仅先按这个必要条件生成三个有序索引集合，再沿用原来的：

- 组合总均值复核；
- 共同 Scenario 上的联合 CVaR10；
- `(-CVaR, -mean, team_ids)` 确定性排序；
- 原有输出对象和语义哈希。

该剪枝不会把一个可能达到 `F` 的组合排除。索引仍按原 team 顺序枚举，最终门槛判断
也未删除。

## 先红后绿与语义验收

性能回归用 16 队矩阵构造“只有一个组合可能达标”的情形。修复前稳定访问 `4,096`
个组合并失败；修复后只访问 `1` 个组合并通过。

语义验收包含两层：

- 4 个 epsilon（0%、1%、2%、5%）乘 3 个固定随机种子，共 12 组 16 队矩阵；剪枝
  路径与旧的完整 `4,096` 枚举在 selected team IDs、Scenario outcome 向量、最大均值、
  distribution summary 和 semantic hash 上全部相同；
- 新正式产物与冻结旧产物重叠的前 9 行逐字段比较，`0` 个差异；P3 source、P4/P5
  source evidence 和 P6 held-out Scenario hashes 全部相同。

被否定的 support 合并临时测试已删除。生产中不存在可切回的旧全枚举分支；v1 报告和
产物属于历史证据，按规则保留而不提交新的大型运行产物。

## 正式 v1 P6 复跑

新 run：`fantasy-03c9fa323e653b7d`

evidence semantic SHA-256：
`ec74d57d1c772b0d348cc4ad504d358171b8b2641efe223f36eaa295075a99fe`

artifact file SHA-256：
`dc18bcfc5601b7d85c6a78becbd93c3e5590feba46e20c584a5091d9f7df84d6`

| 指标 | 冻结旧 run | P1 run |
| --- | ---: | ---: |
| 完成行数 | 9/108 | 84/108 |
| 来源与上下文 | 14.06s | 12.95s |
| 只读审计 | 2,379.67s | 1,811.19s |
| 总墙钟 | 2,393.73s | 1,824.14s |
| 已完成行中位数 | 15.39s | 2.22s |

按只读审计阶段的完成行吞吐计算，提升约 **12.3 倍**；已完成行中位数约快 **6.9 倍**。
本次没有减少 128 个 held-out Scenarios、模型、coverage case、horizon、bootstrap 或风险
门槛。

正式 runner 在第 84 行完成后停止，原因精确为：
`projected next P6 row would exceed the frozen 30-minute target`。完成范围包括全部 81 行
Rate-agnostic 矩阵，以及 Primary-model 的 coverage-01 三个 horizon。它不是 108 行完整
审计，因此仍为 `partial-draft`，两版 v1 手册仍为 `draft`。

这构成 P1 的明确剩余阻断：v1 配置把 1,800 秒目标作为行间停止条件；虽另有 3,600 秒
硬上限，本阶段不改冻结 v1 策略来制造“完整”结果。v2 P6 应在新版本策略中明确采用
不超过 60 分钟的完整矩阵预算，并分别报告 30 分钟目标是否达到。

运行时抽样观察到工作集约 8.0 GB、私有提交约 9.3 GB；这是内存中的终值缓存，不是
磁盘缓存，也没有生成 186 GB 级文件。它不是正式峰值测量，后续 v2 仍需作为资源风险
披露。

## 工程级审查与 Gate

| Gate | 结果 |
| --- | --- |
| 小型确定性性能回归 | 通过：4,096 -> 1 |
| 固定随机矩阵全枚举差分 | 通过：12/12 语义完全相同 |
| 冻结正式行差分 | 通过：9/9，逐字段 0 差异 |
| 108 行 v1 矩阵 | 未完成：84/108，冻结 30 分钟目标停止 |
| P1 替代验收 | 通过：准确报告剩余 blocker，不伪称完整 |
| 全量 Python 测试 | 通过：136 collected，135 passed，1 skipped |
| Ruff / format / diff | 通过 |
| `uv lock --check` / 依赖兼容 | 通过：77 packages compatible |
| Parser/JAR | 未触碰，因此不重建；冻结身份保持 |
| 本地 Web 服务、客户端与凭据 | 未触碰 |

`ti audit fantasy-03c9fa323e653b7d` 返回 `status: warning` 且产物哈希完整；warning 包含
P6 partial、v1 draft 和既有规则歧义，不能解释为可发布手册。

P1 至此按预注册的“完成或准确 blocker 报告”分支收口。P2 只能从受治理的 manual-route
证据独立推导 v2 规则，不得读取本报告中的 solver/oracle 动作来生成或修补规则。
