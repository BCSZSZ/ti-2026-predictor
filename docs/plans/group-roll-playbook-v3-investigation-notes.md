# Group Roll 人工手册 v3 调研笔记

状态：**proposal only；尚未授权实现、尚未冻结候选、不得视为 v3 发布计划**

- 记录日期：2026-08-07
- 上游结论：[v2 后续问题 memo](../reports/group-roll-playbook-v2-follow-up-memo-2026-08-07.md)
- 继承边界：显式 UTC `as_of`、稳定 ID、时间有效阵容、原始响应不可覆盖、人工路线不得使用
  solver/cross-audit 动作轨迹推导规则

## 目标

下一轮的目标不是把 v2 的 12 条规则修到看起来更好，而是回答三个问题：

1. Primary 的失败来自规则本身、阈值、阶段划分，还是风险目标定义？
2. Rate-agnostic 是否还能形成一份短而可靠的手册，还是应只保留为敏感性基线？
3. 能否用全新、严格隔离的证据证明一份更短手册达到发布门槛？

最现实的成功形态是“规则更少、失败面更小、证据完整”，不是宣称全局最优或追求大幅均值
提升。

## 数据与推导防火墙

- v2 standalone/cross-audit 与历史 P5 solver 产物只能用于记录问题、设计诊断指标和决定
  研究优先级；不得读取其中的 solver/oracle 动作轨迹来生成或选择人工动作。
- 新规则内容必须来自获准的人工路线、当前客户端规则、Stat/Quality/Trait 证据和明确可解释
  的算术关系。
- v3 启动时必须冻结新的显式 `as_of`、规则快照、数据快照、Git commit、配置和 seed。
- derivation、screening、confirmation 与最终 cross-audit 的 Scenario 索引必须分别记录并
  互不相交；不能复用 v2 confirmation 或 audit 行作为 v3 发布证据。
- 不得根据 confirmation/cross-audit 结果回写同版本候选。失败后只能保留失败证据，并启动
  新版本或新候选身份。

## 建议工作包

### N0 — 失败分类图谱

阶段作业目标：解释问题分布，不提出新规则。

最小修改范围：新增只读分析和报告；不改 playbook、solver、Scenario policy、release gate、
advisor 或 v2 artifact。

应覆盖：

- Primary 失败规则 P2M01、P2M05、P2M09、P2M10、P2M11 的触发率、阶段、coverage 和
  mean/CVaR10 分解；
- `default-knee`、`downside-first` 相对 `mean-first` 的动作分歧和损失来源；
- P2M02 方向反例是否属于更广的状态类型，而不是只描述一个 audit 行；
- Rate 的 23 个 10% 和 96 个 5% Common 失败按 rule/model/coverage/阶段聚类；
- 规则遮蔽、fallback 频率和 8/12/16 复杂度差异。

验收标准：每个 GRV2 问题能映射到证据行和一种可证伪的根因假设；报告明确区分观察、推断和
未知项；不输出新手册动作。

### N1 — Replay 构建身份闭合

阶段作业目标：解释或消除 GRV2-09，不重写历史数据。

最小修改范围：记录并固定 JDK、Maven、依赖解析和打包参数；必要时增加构建身份测试。禁止用
新 JAR 覆盖已有 raw response、processed table 或历史 manifest。

验收标准：相同源码和工具链连续构建得到相同文件哈希；历史 JAR 仍可追溯；若不能复现历史
字节，明确记录已排除项、剩余原因和 300 个冻结统计值的语义差分结果。

### N2 — 独立候选冻结

阶段作业目标：冻结更短、可解释的 v3 候选，而不是修补 v2 文件。

最小修改范围：新增版本化候选、候选冻结清单、推导说明和新 validation policy；v1/v2 保持
不可变。

建议方向：

- Primary 为主要候选；v2 已支持的 7 条规则只能作为研究线索，保留与否仍需独立推导；
- 两个失败风险修正不默认继承；若重新提出，必须有新的数学定义和预注册容忍度；
- Rate 必须在“从第一原则重做短版”与“归档为解释性基线”之间做显式决定；
- 不预设一定发布 12 条，复杂度以前沿和全部保留规则可验证为准。

验收标准：候选来源不含 solver/cross-audit 动作轨迹；规则不超过 12 条、每条不超过 3 个条件、
全手册不超过 3 个阶段；冻结 semantic/file hash；冻结后不得按结果回写。

### N3 — 新 standalone 验收

阶段作业目标：在完整 40-Roll 会话上判断新候选是否达到发布条件。

最小修改范围：只新增 v3 policy、artifact、测试和报告；不在运行中修改候选。

验收标准沿用已预注册语义：

- screening 与 confirmation 索引完全不交，并与 v2 正式索引分离；
- 每个角色覆盖九个 starting-state strata，运行完整 40-Roll 会话；
- 每条发布 Core 规则在均值和 CVaR10 上具有单侧 95% 无损支持，并至少一项严格点改善；
- 每个发布风险修正同时满足均值保留容忍度和单侧 95% CVaR10 改善；
- Primary 在主模型下没有 Common 10% 失败；Rate 若仍是发布候选，则三个 release 模型均没有
  Common 10% 失败；5% strict 结果单独披露；
- 相同快照、配置和 seed 产生相同推荐 JSON 与 artifact identity。

任何一项失败都保留 `draft`，但失败报告仍是可验收、可合并的阶段产物。

### N4 — 全新 held-out cross-audit

阶段作业目标：只读查找方向反例和短视野 exact 差异，不用审计结果升级失败的 standalone。

最小修改范围：新增 v3 cross-audit policy、版本化 evidence 和报告；不修改人工规则。

验收标准：审计索引与 derivation/screening/confirmation/历史 solver 索引交集为零；计划矩阵
完整结束；所有 disagreement、unresolved、5% warning、10% exception 和方向性反例均披露；
连续两次运行的 semantic/file hash 一致。cross-audit 只能维持或降低 release label，不能单独
促成发布。

### N5 — 发布与顾问集成

进入条件：N3 全部发布门槛通过，N4 没有阻断反例，项目级回归通过。

最小修改范围：先更新文档默认入口和证据包，再单独评审是否将本地顾问切换到新版本。仍然
不控制 Dota 客户端、不自动填写，也不把 Group 手册用于 Main。

验收标准：版本身份在 CLI、文档、advisor 和 artifact 中一致；默认路径 fail closed；旧版本
作为历史证据可复现。只有完成替代验证且无历史用途的 production 路径才允许清理。

## 待确认问题

- 新 `as_of` 时是否已有新增比赛、阵容或客户端规则；如果没有，是否仍值得启动 v3 正式验证？
- Primary 模型权重是否仍只能视为 best guess，还是获得了更高优先级的官方来源？
- 多快照验证需要多少独立时间点，才足以区分 seed 波动和候选变化？
- exact horizon 从 3 扩展到多少仍能保持可接受成本？必须先有基准，不能默认启用 full planner。
- Rate-agnostic 是否有明确用户价值足以支持从第一原则重做？若没有，应正式归档而非继续消耗
  validation 预算。

## 明确不做

- 不重复跑同一 v2 seed 并把结果当成新证据；
- 不从 P5/P6 或 v2 cross-audit 的推荐动作反向生成手册；
- 不把现有 7 条 Primary 规则直接拼成“已验证短版”；
- 不把局部 exact oracle 称为完整 40-Roll 全局最优；
- 不在手册仍为 `draft` 时切换 advisor 或自动化任何客户端操作。
