# Group Roll playbook v2 P4 read-only cross-audit report

状态：**P4 完成；108/108 全部完成，Rate-agnostic v2 与 Primary-model v2 均保持 `draft`**

日期：2026-08-07

显式 `as_of`：`2026-08-06T17:27:00Z`

## 阶段目标、最小范围与验收

P4 从 `main@91d090d53f7ba4e0f2dc23f022e19676f9fef2ab` 开始，只读比较 P2 冻结的两份
Human Roll 手册、单独版本化的 bounded solver 与条件 exact oracle。P3 standalone 结果、手册
动作、规则顺序和 semantic hash 全部禁止修改；solver/oracle 的动作分歧只能披露，不能回写手册。

最小实装范围是：

- 新增 v2 audit-context solver policy；算法参数与冻结 v1 policy 完全相同，只更新 v2 来源身份；
- 新增 v2 cross-audit policy、独立 seed、运行预算和来源清单；
- 让既有 CLI 显式选择 `v1/v2`，默认 v1 行为与 semantic hash 保持不变；
- v2 使用当前 audit policy 执行条件求解；历史 v1 P5 产物只披露失败的 effectiveness 状态，
  不冒充一次新的 v2 full-session P5；
- 生成 108 行只读证据和本报告，不新增 full planner，也不改任何人工规则。

验收要求是：P4 audit 索引与 v2 standalone、记录的 P5 索引都不交；完成 108/108；来源、
Rule、Scenario、手册和模型身份一致；总运行不超过 60 分钟；逐项披露分歧、unresolved、5%
警告和 10%/方向性重大例外。30 分钟另作性能软目标，不以提前停止换取通过。

## 冻结身份与独立性

- 干净 source commit：`58f1158c0bf54094e5a778c8f7c5cea892acbedf`
- 正式命令：
  `ti fantasy group-cross-audit --as-of 2026-08-06T17:27:00Z --cross-audit-version v2`
- run：`fantasy-1fc085f551c890a4`
- evidence semantic SHA-256：
  `6dca84fe1192de7e04a9ca0c8dcfd095d7b3bc3f09a8e445735865661159aebf`
- artifact file SHA-256：
  `2871ded7f030f78ac1872f55c9c297882727d9273e4f31774e04a81e2e68dbce`
- cross-audit policy file / semantic SHA-256：
  `21bf40f8271cc49a22b09bad2ba18f965cc3785af867b35d12eb52b354fe6519` /
  `51d07f181942b6755e33faee46c27cedc8b6bb6b04b4c654607e2b948ecf482a`
- audit solver policy file / semantic SHA-256：
  `dd917516a9aecf84d932ef531f60a4563783cc4a914549bf78eacc8be8bc16ef` /
  `6b067754c1caf6e5f866e3c86bc0358eb30e4fd789a497239577ea3d094e8f9c`
- P3 standalone evidence semantic SHA-256：
  `77032ccf42dccd2d6a7bda1e9f51786245b955f0ed548d934c5c9f956bc7e299`
- Rate / Primary playbook semantic SHA-256：`2e4936c7…` / `8a548206…`
- source / validation Scenario SHA-256：`22fd9f2f…` / `716b7ee3…`
- data / pool SHA-256：`49e373b2…` / `9a86b14e…`
- Rule snapshot：`20260806T172612Z-702ddf2a6953`，semantic SHA-256 `702ddf2a…`
- 14 项 source manifest semantic SHA-256：`e37cb92f…`

新 seed 为 `2026080706`。从 8,192 个来源 Scenario 中固定抽取 128 个 audit 索引；其索引
SHA-256 为 `386d96f7…`。它与 v2 standalone 索引、记录的 P5 索引交集分别为 0 和 0。
standalone 与历史 P5 之间原有 5 个交集不参与本次独立性门禁，也没有进入 audit 集。

历史 P5 evidence `eb6a399d…` 及其 policy `9466049f…` 只以
`historical-v1-effectiveness-only` 身份记录，其状态仍为
`failed-escalation-review-required`。本次执行的是 semantic `6b067754…` 的 v2 audit policy；
没有把历史 P5 的失败或运行量说成一次新的 v2 full-session 验证。

## 108 行结果

每个 edition/model 检查九个 coverage case 和剩余 1/2/3 Roll，共 27 行。`Common` 表示其
P3 session frequency 至少为 10%。损失上界使用独立 weighted-outcome bootstrap 的单侧
95% 诊断；它不是 P3 的 Series-cluster confirmation。

| 手册 | 模型 | 行数 / Common | oracle 分歧 | solver 分歧 / unresolved | 5% 严格例外 | 10%或方向性重大例外 | Common 最大均值 / CVaR10 损失上界 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rate-agnostic | Primary | 27 / 27 | 9 | 14 / 11 | 14 | 0 | 6.31% / 8.28% |
| Rate-agnostic | Flattened | 27 / 24 | 9 | 13 / 16 | 15 | 0 | 7.06% / 8.86% |
| Rate-agnostic | Sharpened | 27 / 27 | 10 | 19 / 11 | 15 | 0 | 6.36% / 8.34% |
| Primary-model | Primary | 27 / 27 | 12 | 19 / 10 | 10 | 1 | 4.89% / 6.92% |

Rate-agnostic 的 81 行中没有单侧 95% 损失上界超过 10%，也没有手册动作在均值和 CVaR10
上同时劣于刷新；但 44 行超过 5% 严格线。因此这次局部条件审计比 P3 standalone 的 23 个
10% Common 失败温和，却不能覆盖或推翻完整 40-Roll standalone 失败。

Primary-model 的唯一重大例外为 `coverage-05`、剩余 3 Roll、规则 `P2M02`：手册选择
`mid:29`，而直接刷新在均值和 CVaR10 上都更高（43,313.12 对 43,040.24；35,989.94 对
35,682.07），所以按预注册定义记为 directionally wrong。条件 exact oracle 选择
`support:29`；手册相对 oracle 的均值/CVaR10 点损失为 2.90%/2.56%，单侧 95% 上界为
4.89%/6.92%。该项并不是“损失上界超过 10%”，而是方向性安全门禁单独触发。

solver 分歧和 unresolved 仅作为诊断。它们不等同于 exact oracle，也不单独改变手册；这次
唯一方向性例外由手册、刷新与 exact oracle 的同一条件分布直接计算得出。

## 发布标签与限制

| 手册 | P3 standalone 标签 | P4 重大例外 | P4 最终标签 | 可升级 |
| --- | --- | ---: | --- | --- |
| Rate-agnostic v2 | `draft` | 0 | `draft` | 否 |
| Primary-model v2 | `draft` | 1 | `draft` | 否 |

只读 audit 可以保持或降级已有标签，不能把 P3 的 `draft` 升级。Rate 在本矩阵没有重大例外，
仍因 P3 standalone 失败保持 `draft`；Primary 既有 P3 失败，又新增一个方向性反例，同样保持
`draft`。没有按结果修改任何一条规则。

本矩阵只覆盖剩余 1-3 Roll；未来 replacement offer 使用声明的循环序列而非积分随机 offer；
独立 bootstrap 只是诊断；v2 没有新 full-session solver effectiveness validation。以上限制均写入
正式证据，不能把“artifact 可审计”解释为“手册已经可靠”。

## 性能、验收与工程回归

| 项目 | 结果 |
| --- | --- |
| 身份与上下文重建 | 11.95s |
| 108 行只读审计 | 2,676.63s |
| 总墙钟 | 2,688.58s（44 分 48.6 秒） |
| 完成行中位数 | 3.49s |
| 30 分钟软目标 | 未通过，超出 888.58s |
| 60 分钟硬上限 | 通过，余量 911.42s |
| P3 + P4 正式计算总墙钟 | 4,221.06s（1 小时 10 分 21 秒），通过两小时工程目标 |
| 运行中观察内存峰值 | 工作集约 11.6 GB、私有提交约 12.9 GB；没有新增大型磁盘缓存 |
| 完整性与独立性 | 108/108；P3/P5 audit overlap 均为 0 |
| 来源与人工手册 hash | 全部一致、人工手册未变化 |
| 全量离线 Python tests | 通过：147 passed，1 skipped |
| Ruff / format / diff | 通过；136 files already formatted，`git diff --check` 无错误 |
| lock / 依赖兼容 | 通过：87 packages resolved，77 packages compatible |
| `ti rules validate` | 仅 3 条既有客户端语义 warning，无新增 blocker |
| route / debug 边界 | 人工路线无 solver/cross-audit import；无 TODO/FIXME/HACK/debugger 残留 |
| artifact audit（报告编辑前的干净 source commit） | `publishable: true`、`status: warning`，文件 hash 完整，无 blocker |

正式产物基于干净实现提交生成，随后 `ti audit fantasy-1fc085f551c890a4` 通过。audit warning
只包括既有客户端规则歧义、数据/校准警告、历史 P5 effectiveness 失败、条件 offer 局限和两版
`draft`；没有新增 blocking issue。开始编辑本报告后再次运行 audit 会按设计只因
`source_version-changed` 阻止“当前工作树等于正式 source”的声明；这不是产物 hash 失败，正式
证据仍固定到上面的干净 commit。

完整实现 diff 审查确认只增加显式 v2 policy/CLI 路由和来源区分；默认 v1 policy semantic hash
仍为 `803ffeb4…`，默认 v1 solver semantic hash 仍为 `9466049f…`。预测、数据、replay parser、
Web、客户端控制、Main 支持和人工 handler 均未改动。v1 路径继续作为不可变历史兼容入口，v2
是显式版本化路径；两者不是可清理的重复 production 实现。因此本阶段没有可安全删除的旧代码。
P4 至此完成，P5 只做项目最终审计、证据包闭合和单独的易懂总结，不再修改手册结论。

## P5 确定性收口附记

P5 在重跑 standalone 后发现：旧 v2 来源发现逻辑遇到多个“语义与文件均相同”的 P3 artifact
时，会按目录名选择最后一个，并把这个偶然物理路径写入 cross-audit evidence。108 行数值不受
影响，但同快照、配置和 seed 的最终文件 hash 会漂移。P5 以最小修复在 v2 policy 中冻结确切
P3/P5 artifact 路径，并同时验证路径范围、文件名和语义哈希；v1 默认行为没有改变。

- 修复提交：`1f48f8a`；修复后 policy file / semantic SHA-256：`c591d90d…` / `5aee998b…`
- 最终 path-pinned run：`fantasy-26e4f9240b19a518`
- 最终 evidence semantic / file SHA-256：`d0f90db6…` / `0f01ffb2…`
- 最终 source manifest SHA-256：`abb3e90f…`
- 第一次 / 第二次总墙钟：2,679.16s / 2,726.74s

第二次运行返回同一 run ID、semantic hash 和 file hash，ArtifactWriter 未发现任何字节差异。
最终 108 行、summary 和 gate 与本报告上方原 P4 run 逐字段完全一致；因此原 run 继续是有效的
阶段历史，但 v2 最终证据包以 path-pinned run 为准。没有把这次工程确定性修复用于修改手册。
