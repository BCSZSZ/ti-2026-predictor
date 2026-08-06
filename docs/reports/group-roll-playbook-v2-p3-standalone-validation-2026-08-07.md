# Group Roll playbook v2 P3 standalone-validation report

状态：**P3 完成；Rate-agnostic v2 与 Primary-model v2 均为 `draft`**

日期：2026-08-07

显式 `as_of`：`2026-08-06T17:27:00Z`

## 阶段目标、最小范围与验收

P3 从 `main@1379b32d7adfdb944248f00cd8d69ee8e44e2412` 开始，只确认 P2 已冻结的两份
Human Roll 候选。候选配置、人工手册、Stat 表、handler 及 semantic hash 均禁止改动；
验证结果不得回写成例外规则，也不得读取 P5/P6 动作轨迹。

最小实装范围是：

- 新增 v2 validation policy 与新 seed；
- 让既有 CLI 显式选择 `v1/v2`，默认 v1 行为和语义 hash 保持不变；
- v2 启动前逐项核对 P2 candidate freeze、P3 来源与 Rule snapshot；
- 在原有九格、完整会话、8/12/16、Common 损失和核心规则消融之外，补齐风险修正的
  配对确认；
- 生成本报告与版本化证据身份。

验收要求是：screening/confirmation 不交；每个角色完整覆盖九个 readiness cell；所有
会话包含 40 次真实 Roll 成本；Primary 只用主模型做 release gate，Rate-agnostic 用三模型；
核心规则和风险修正分别按预注册单侧 95% 门槛判定；运行不超过 30 分钟，或如实报告失败。

## 实装与冻结边界

v2 policy 使用 seed `2026080704`，与 v1 的 `2026080604` 不同。screening 固定为 replicate
`0-15`，confirmation 与 ablation 固定为 `16-63`，两者显式不交。每版、每个 8/12/16
候选、每个模型、每个 coverage case 运行 64 个完整会话。

风险修正确认以 `mean-first` 为配对基线，仅在 confirmation 区间运行：

| 手册 | default-knee 允许的均值损失上界 | downside-first 允许的均值损失上界 |
| --- | ---: | ---: |
| Rate-agnostic | 1% | 2% |
| Primary-model | 2% | 5% |

修正必须同时满足：均值损失单侧 95% 上界不超过声明容忍度，且 CVaR10 改善单侧 95%
下界严格大于零。如果两个偏好在发布 12 条下产生完全相同的动作路径，则记为 `inactive`，
不能用零差异伪称“已证明改善”。

兼容性测试固定 v1 validation semantic SHA-256 仍为
`19b505159bb7c42b93d952359932e26dd0434ff4ae9283738432784afe685865`。v2 启动前也验证
`candidate-freeze-v2.json` 的所有 tracked file hash、两份 playbook semantic hash、空的
solver source 数组和独立人工路线标记。

## 正式运行身份

- 干净 source commit：`642f7ba77e3f9624dc7d892c9dcdcc918ae1b5c8`
- 正式命令：
  `ti fantasy group-playbook-evidence --as-of 2026-08-06T17:27:00Z --playbook-version v2`
- run：`fantasy-1c8871c419f59f08`
- evidence semantic SHA-256：
  `77032ccf42dccd2d6a7bda1e9f51786245b955f0ed548d934c5c9f956bc7e299`
- artifact file SHA-256：
  `38751743bb44c8f0aa79e7ca75cb02d3d152f15e6bc5a52e38a98ab073a84783`
- validation policy file SHA-256：
  `7868c841454e2762a1fa7ddc203cf70e8924a2eb4c46f4aad4631098af8020f2`
- validation policy semantic SHA-256：
  `a3ee5a9976e0668d7d6d01c76a52f28d954b72e714b3c13afd2870b76dcff3d5`
- source P3 / validation Scenario SHA-256：
  `22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3` /
  `35028c1f0c29802e47ade6dcb0dbf9ba69583488c52287aa449510f4de49b93b`
- P3 evidence / data / pool SHA-256：`de84baa3…` / `49e373b2…` / `9a86b14e…`
- Rule snapshot：`20260806T172612Z-702ddf2a6953`，语义 SHA-256 `702ddf2a…`

主候选和规则消融沿用 v1 的 31,104 个完整会话；风险修正确认新增 3,456 个 confirmation
会话。合计 34,560 个会话、1,382,400 次人工规则决策。共享 future offer、mutation 与
比赛表现继续使用互相独立的确定性随机流，因此不同候选和消融保持配对。

## 12 条发布候选的点估计

以下是九格等量的 coverage 诊断，不是实际起始状态的总体概率预测：

| 手册 | 验证模型 | ε=0 期望 Group 分 | ε=0 CVaR10 | fallback/决策 |
| --- | --- | ---: | ---: | ---: |
| Rate-agnostic | client-weight-primary-v1 | 52,117.02 | 40,711.16 | 65.61% |
| Rate-agnostic | flattened-weights-v1 | 53,336.35 | 42,237.93 | 62.83% |
| Rate-agnostic | sharpened-weights-v1 | 50,049.48 | 38,656.95 | 68.71% |
| Primary-model | client-weight-primary-v1 | 57,585.35 | 45,983.76 | 52.23% |
| Primary-model | flattened-weights-v1（敏感性） | 59,403.49 | 47,658.48 | 50.70% |
| Primary-model | sharpened-weights-v1（敏感性） | 55,470.68 | 44,240.79 | 51.39% |

Primary 与 Rate 在主模型 576 个会话中有 99.83% 的完整动作序列不同，首决策分歧率
33.33%。这保持了两个产品的差异，不证明 Primary 所声明的后台率是真值。

## ε 风险与人工复杂度前沿

主模型下的 12 条候选：

| 手册 | ε | 期望 Group 分 | CVaR10 | 相对 ε=0 均值 | 相对 ε=0 CVaR10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rate-agnostic | 0% | 52,117.02 | 40,711.16 | — | — |
| Rate-agnostic | 1% | 51,851.86 | 41,066.99 | -0.51% | +0.87% |
| Rate-agnostic | 2% | 51,641.34 | 41,007.85 | -0.91% | +0.73% |
| Rate-agnostic | 5% | 51,485.89 | 41,040.16 | -1.21% | +0.81% |
| Primary-model | 0% | 57,585.35 | 45,983.76 | — | — |
| Primary-model | 1% | 57,148.19 | 45,946.75 | -0.76% | -0.08% |
| Primary-model | 2% | 56,977.09 | 46,155.75 | -1.06% | +0.37% |
| Primary-model | 5% | 56,919.47 | 46,029.97 | -1.16% | +0.10% |

在主模型、ε=0 下，Rate 的 12 条相对 16 条损失为均值 1.18%、CVaR10 2.44%，只进入
5% complexity tier；Primary 的 12 条损失为 0.70%/0.51%，进入 1% tier。可读性上限仍是
12 条，但 Rate 的 16 条挑战集明显优于发布候选，这会继续作为局限披露，不能用结果把第
13-16 条塞回手册。

## Common 情形与核心规则消融

### Rate-agnostic v2

- 三模型共 253 个 Common 情形；23 个的均值或 CVaR10 损失单侧 95% 上界超过 10%，
  96 个超过 5%。按模型分布为 7 / 11 / 5 个 10% 失败。
- 最大均值损失上界为 6.07%（flattened、coverage-01、R2A09）；最大 CVaR10 损失上界
  为 19.19%（primary、coverage-04、R2A10）。
- 36 个 model×rule 消融中 23 个失败，涉及 8 个唯一规则。只有 R2A01、R2A02、R2A03、
  R2A08 在三个 release 模型下都通过单侧无损与严格点改善。
- 发布序列中的 default/downside 偏好在三模型均与 mean-first 完全同路径，六项记录均为
  `inactive`；它们没有风险修正规则失败，但也没有获得 CVaR 改善声明。

因此 Rate-agnostic 是明确 `draft`，且本轮结果没有达到“消除五个 v1 重大失败”的预期。

### Primary-model v2

- 主模型共 83 个 Common 情形；0 个超过 10%，19 个超过 5%。最大均值/CVaR10 损失
  上界分别为 3.92% 与 9.99%。
- 12 条中 7 条通过核心规则消融：P2M02、P2M03、P2M04、P2M06、P2M07、P2M08、
  P2M12；失败项为 P2M01、P2M05、P2M09、P2M10、P2M11。
- default-knee 相对 mean-first 的动作路径分歧率 99.54%；均值点损失 2.94%，其 95% 上界
  3.47% 超过 2% 容忍度，CVaR10 点差为 -1,542.11、单侧下界 -2,323.46。
- downside-first 的路径分歧率 100%；均值点损失 12.29%，95% 上界 13.11% 超过 5%
  容忍度，CVaR10 点差为 -6,198.29、单侧下界 -7,092.00。

Primary 保持了 10% Common 门槛，并把本轮通过消融的规则数提高到 7/12，但仍没有达到
全部核心规则通过；两个实际生效的风险修正还同时降低均值与下尾，因此也必须是 `draft`。

上述 v1/v2 计数使用不同预注册 seed 和不同候选，能说明本次独立验收结果，不能当作同一
会话上的因果提升估计。

## 性能、审计与工程回归

| 项目 | 结果 |
| --- | --- |
| P3 source reproduction | 15.86s |
| 分析上下文重建 | 15.95s |
| standalone validation | 1,500.67s |
| 总墙钟 | 1,532.48s（25 分 32 秒） |
| 30 分钟目标 | 通过，余量约 267.5s |
| 运行中观察内存 | 工作集约 1.3 GB、私有提交约 2.5 GB；非磁盘缓存 |
| 聚焦 playbook/evidence tests | 通过：21/21 |
| 正式运行前全量 Python tests | 通过：145 collected，144 passed，1 skipped |
| Ruff / format / diff | 通过 |
| lock / 依赖兼容 | 通过：77 packages compatible |
| artifact audit | `publishable: true`、`status: warning`，文件 hash 完整，无 blocker |
| route separation | 通过：standalone 模块没有 solver/cross-audit import |
| candidate freeze | 通过：两份候选 semantic hash 与 P2 完全相同 |
| v1 compatibility | 通过：默认 CLI 仍为 v1，v1 policy semantic hash 未变化 |

audit warning 只包括两版 standalone `draft`、既有 First Blood/percentile 规则歧义、非目标
联赛过滤、部分目标队缺少正权重历史和 isotonic 校准被滚动验证拒绝。没有把 artifact
`publishable` 误写成手册可靠；它只表示证据文件本身可审计。

项目级审查确认没有改 P2 候选、v1 历史证据、P3 终值数学、预测、数据、solver、Web、客户端
控制或 Main 支持。没有新旧 production 双路径可清理；v1 和候选 v2 必须继续作为历史证据
保留。

P3 至此按失败分支完整收口。P4 仍要完成预注册的 108 行 held-out read-only audit，以披露
solver/oracle 反例和运行完整性；但 read-only audit 不得把已经 standalone `draft` 的手册
升级为 reliable，也不得生成 v2.1 规则。
