# P7 Local Interactive Group Roll advisor

状态：**实施前冻结；尚无 P7 结果**
冻结日期：2026-08-06
显式 `as_of`：`2026-08-06T08:15:00Z`

## 产品定位

P7 是次要的本地状态跟踪器，不是新人工手册、手册发布 gate 或自动 Dota 工具。它必须同时
显示冻结手册、Rate-agnostic safety、一步模型估值和按需 P5 solver 的分歧，不得用 UI
把两份 `draft` 手册、P5 失败门禁或 P6 partial 审计包装成可靠推荐。

冻结配置为 `config/models/fantasy-group-interactive-advisor-v1.json`。它锁定 P3/P4/P5/P6
evidence hash、两份手册 hash、P6 的 128 个留出情景、三个出率模型、四个 epsilon 和所有
功能/性能边界。

## 手工输入与状态

用户按界面顺序确认：

- Core、Mid、Support 各三个 Emblem 的 Stat、T1–T5 品质和 Trait；
- 当前共享三个正权重 operation ID，并同时显示由 mutation/目标生成的可读描述；
- 剩余 1–40 次 Group Roll；
- 手册 edition、模型、epsilon 和风险修正。

首次确认创建 Locked Roll baseline 和 Observed state。后续只能选择一个当前合法动作，再人工
确认其实现的 mutation outcome 与新的三个共享 offer。纯转移引擎扣减一次 Roll、替换
Observed state 并重新规划；Locked baseline 的数据、规则、模型与 seed 永远不变。刷新动作只
替换 offer，不改战旗。

会话 JSON 只保存初始状态、基准身份和用户已确认事件；加载时从初始状态重放每个事件并校验
中间 hash，不信任直接写入的终态。相同基准、事件和规则必须得到相同的当前状态与会话 digest。

## 默认快速层

默认层不运行 40-Roll rollout。对当前每个合法动作，它计算：

1. 所有合法 mutation 结果上的 Rate-agnostic 终局战旗值变化区间 `[L, U]`；
2. Primary/Flattened/Sharpened 各自权重下，mutation 与 128 个 Group 表现情景混合后的一步
   Expected score 与 CVaR10；
3. 相对当前状态的均值/CVaR10 delta、四个 epsilon 的可选集与模型首选是否分歧；
4. 当前 Core/Mid/Support 完整战旗的同队最佳 Team matching。

刷新的一步终局 delta 为 0；它不是“刷新无价值”，而是快速层明确不估计下一组 offer
的期权价值。整张表必须标注“one-step，不含未来 offer 与剩余 Roll 可达性”，不得称为完整策略
期望。

## 按需 P5 solver

只在用户明确点击时，以当前 Observed state 重建 15,625 配置表并运行一次 P5 root decision。
UI 必须同时显示 preferred action、实际 executed action、resolved/unresolved、原因、screening/
confirmation 样本数和 `failed-escalation-review-required`。若 unresolved，executed action 必须是
Rate-agnostic fallback；不得用稳定排序隐藏未决。该计算可缓存在同一个状态 hash 下，但结果实现后
必须使用新 Observed state 重新计算。

## 硬边界与验收

- Web 服务只监听 `127.0.0.1`；
- 不读 Steam 凭据，不控制 Dota 客户端，不自动填写；
- OCR 若存在也只能产生待确认草稿，不能自动执行动作；
- 本局观测不改模型权重；
- `period=main` 和五格状态必须 fail closed，不得因为类型可扩展就显示为已支持。

功能 gate 要求：本地 bind、九格与三 offer 完整校验、apply/refresh 事件、Observed-state
replanning、会话确定性重放、Main 阻断以及 Streamlit 页面无运行异常。性能目标为上下文 30s、
快速层 10s、缓存重复 1s、按需 solver 60s。任何超时、来源缺失或功能失败都以实验性
warning/blocked 显示，不会改变手册标签。

实装后只向本报告追加功能、性能、AppTest、真实浏览器验收和剩余限制；上述范围不根据 UI
方便性回填放宽。

## 实装结果（追加于冻结契约之后）

P7 已在实现提交 `f7640d75f6b4ad712469cace7cacae36f803ae2a` 上完成。冻结范围没有
回填放宽：两份人工手册仍为 `draft`，P5 仍是
`failed-escalation-review-required`，P6 仍是 `partial-draft`。P7 不修改两份手册、P4/P5/P6
产物或 `docs/playbooks/group-roll/evidence-package-v1.json`。

新增的生产路径为：

- `fantasy/advisor.py`：强类型 policy、状态/基准序列化、apply/refresh 事件、逐事件重放与 hash
  拒绝、可读 operation/action 描述；
- `fantasy/advisor_analysis.py`：验证 P3–P6 身份、重建 P6 的 128 个留出情景、人工手册与一步
  精确混合分布、四个 epsilon、三模型敏感性及每个 role 的最终 Team matching；
- `fantasy/advisor_ui.py`：九格与三 offer 手工录入、Locked baseline、Observed-state replanning、
  会话下载/加载、Main 阻断和显式 P5 按钮；
- `fantasy/advisor_reporting.py` 与 `ti fantasy group-advisor-evidence`：在干净 commit 上复现
  功能门禁、快速层、缓存、观察后重规划、最后一次 P5 和会话重放。

## 正式证据与门禁

正式运行是 `fantasy-125d96172389a0aa`：

| 身份 | 值 |
| --- | --- |
| 显式 `as_of` | `2026-08-06T08:15:00Z` |
| Git commit | `f7640d75f6b4ad712469cace7cacae36f803ae2a` |
| P7 semantic evidence hash | `07c14dffe8f2b9c216aa30f3d6ff7ec4cd81106087f95d59fddcd8779dd7051c` |
| evidence file SHA-256 | `0ee561977858f119d2519c71b55b0de1eea0528f8a4c389edc6386b4ddfe84c3` |
| quick-analysis hash | `9c1814fa8c6853bc598f1d776dc9f3ec019a4bff8e60cc72659c415a3af38249` |
| saved-session hash | `c5aa9353bcaae43b7a9214d88532f5480b22c9197d5c5fa58a298b268485e36d` |

本地 bind、完整输入校验、apply、refresh、观察后重规划、Locked baseline 不变、确定性会话
重放和 Main fail-closed 的布尔门禁全部通过。最后一次 Roll 的正式 P5 行为是 resolved，preferred
与 executed 均为 `support:24`；这只证明该次内部确认分离候选，不改变 P5 总体失败标签。
`ti audit fantasy-125d96172389a0aa` 返回 `status=warning`、`publishable=true`，文件 hash 与上表
一致；warning 完整保留规则歧义、数据警告、两版 draft、P5 失败、P6 partial 和 P7 一步限制。

## 性能

| 项目 | 冻结目标 | 正式 CLI | 真实浏览器 | 结论 |
| --- | ---: | ---: | ---: | --- |
| 上下文与来源验证 | 30s | 18.919s | 22.60s | 通过 |
| 四 epsilon × 三模型快速层 | 10s | 1.252s | 2.16s | 通过 |
| 相同/可复用上下文重复 | 1s | 0.028s | 0.06s（refresh 后同旗） | 通过 |
| 最后一次 Roll 的 P5 | 60s | 8.603s | 未在浏览器重复消耗 | 通过 |
| 正式 P7 证据总计 | — | 29.757s | — | 远低于三小时参考目标 |

P5 长视野不能满足交互目标：P5 clean 证据的完整会话中位数约 749 秒。因此 UI 在剩余 Roll
大于 1 时明确阻断 P5 按钮，只提供人工手册与约 1–2 秒的一步诊断；最后 1 次才开放按需 P5。
这不是把长视野近似成一轮，而是拒绝在响应式界面里运行已知超时的次要路径。

## UI 验收

离线全仓测试为 `128 passed, 1 skipped`，其中新增测试覆盖 policy、apply/refresh、baseline、
确定性重放、篡改拒绝、Main 阻断、operation 描述，以及默认/顾问/Main 三个 Streamlit AppTest
路径。真实 `127.0.0.1:8502` 浏览器验收进一步确认：

1. 页面显示手册/P5/P6 的失败或草案警告，Main 选项只显示阻断信息；
2. 默认九格和三个选项能创建会话，真实上下文与一步分析完成；
3. 手册结论在一步表之前，队伍匹配允许 Carry/Mid/Support 分别选队；
4. refresh 只有勾选人工确认后才能记录，记录后 Roll `40→39`、事件 `0→1`，重新规划为
   `0.06s`；
5. 40 Roll 状态展开 P5 区域时只显示长视野阻断，不显示可误点的运行按钮；
6. 浏览器控制台没有 warning/error，临时服务验收后已停止。

## 剩余限制

- 快速层不是 40-Roll 策略价值：刷新显示零 delta 不等于刷新没有价值；
- P6 留出情景用于响应式诊断，不是为手册新增的发布证据；
- 长视野 P5 仍可由证据命令审计，但不会自动进入 UI，也不会启动 Full planner；
- OCR、Steam/Dota 控制、自动填写和 Main 五格策略均未实现；
- P7 完成意味着跟踪器功能 gate 达成，不意味着两份人工手册已达到可靠发布门槛。
