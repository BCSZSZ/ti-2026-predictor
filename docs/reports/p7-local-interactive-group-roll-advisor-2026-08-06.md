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
