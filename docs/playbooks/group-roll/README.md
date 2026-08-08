# Group Roll 人工手册索引

## 当前发布版（7.41e 双倍证据权重）

- [Group 40 Roll 玩家手册 v3](group-roll-publication-manual-v3.md)：Stat、队伍 Top 3 与 Title 已按
  7.41e 双倍权重刷新；B/C/D 操作规则仍沿用原 v2 验证，不冒充重新认证。
- [Stat 队伍 Top 3 v3](stat-team-top3-publication-v3.md)：当前 42 行排名、基础建议、前三队伍与
  400 次 Series 重采样稳定率。
- [Title 推荐](../../reports/ti2026-fantasy-title-recommendation-2026-08-09.md)：默认仍为
  `Cerulean + the Clutch`，并说明一血内部配置为什么不能按变量名直接解释。
- [本轮实施与影响报告](../../reports/ti2026-current-exact-patch-weight-v3-implementation-2026-08-09.md)：
  记录中央权重实现、四个正式 run、验收、变化与剩余边界。

以下内容是原 v2 冻结验证与历史报告。

截至 `2026-08-06T17:27:00Z`，v2 已完成独立推导、standalone validation 和 108/108 held-out
只读交叉审计；两版均未通过全部门槛，状态为 `draft`。两份 v1 操作手册继续作为 `draft`
历史证据保留：

- [v2 standalone validation 报告](../../reports/group-roll-playbook-v2-p3-standalone-validation-2026-08-07.md)：
  Primary 保持 10% Common 门槛但仍有五条核心规则和两个风险修正失败；Rate 有 23 个
  10% Common 失败。两版候选均未按结果回写。
- [v2 held-out 只读交叉审计](../../reports/group-roll-playbook-v2-p4-read-only-cross-audit-2026-08-07.md)：
  108/108 在 44 分 48.6 秒内完成，与 standalone/P5 索引交集均为 0。Rate 没有重大例外；
  Primary 有一个同时劣于刷新的方向性例外。P5 的 path-pinned 确定性 run 保持全部数值结论，
  并连续复现相同 artifact hash。两版仍为 `draft`，且没有按结果回写。
- [v2 最终证据包](evidence-package-v2.json)：固定 P2/P3/P4、两份手册、规则/数据/Scenario、
  path-pinned 复跑、运行时间、发布标签和全部已知限制。
- [v2 P5 项目审计](../../reports/group-roll-playbook-v2-p5-project-audit-2026-08-07.md)：记录
  确定性缺陷与最小修复、两次完整 P4 复跑、全项目回归、JAR 包装身份 warning 和清理判断。
- [v2 易懂总结](../../reports/group-roll-playbook-v2-summary-2026-08-07.md)：面向实际查阅，说明
  应优先看什么、两版怎么选、真实提升与仍不能承诺的部分。
- [Group 40 Roll 玩家手册（证据分层发布版）](group-roll-publication-manual-v2.md)：先解释
  Roll 机制，再按 S/A/B/C/D 确定度分层整理当前可公开使用、条件参考和暂不采用的规则。
- [玩家手册易懂总结](../../reports/group-roll-publication-manual-summary-2026-08-08.md)：用最短篇幅说明
  Roll 怎么运作、四条最强规则、条件规则和当前不要机械执行的做法。
- [玩家手册实现与验收记录](../../reports/group-roll-publication-manual-2026-08-08.md)：保存内部规则
  映射、最小范围、测试、项目级审查和清理判断；发布正文不显示这些内部编号。
- [v2 后续问题 memo](../../reports/group-roll-playbook-v2-follow-up-memo-2026-08-07.md)：登记
  已确认的进步、退步、发布阻断、工程 warning 和当前处理决定，不修改冻结证据。
- [v3 调研笔记](../../plans/group-roll-playbook-v3-investigation-notes.md)：把问题拆为失败分类、
  构建身份、独立候选、全新 standalone/cross-audit 和发布集成工作包；目前只是 proposal，
  不代表已授权实装。

- [生成率无关版 v2 候选](playbook-rate-agnostic-v2.md)：保留三个跨模型支持原则，收窄
  v1 RA06，并把 RA10/RA12 移出发布序列；standalone 状态为 `draft`。
- [主模型 best-guess 版 v2 候选](playbook-primary-model-v2.md)：PM05/PM12 优先，其余
  均值规则统一过风险档门槛；standalone 状态为 `draft`。
- [v2 Stat、Quality、Trait 证据表](stat-quality-trait-evidence-v2.md)：新 `as_of` 下重新计算，
  42 行分档与边界不变，并逐项显示 `exact/derived` provenance。
- [v2 Stat 队伍 Top 3 发布版](stat-team-top3-publication-v2.md)：面向直接查阅；每张表明确显示
  1–6 的 Stat 排名、基础建议和相对强度，再以中文字段展示三支候选队伍；不显示内部队伍 ID。
- [发布版 r4 易懂总结](../../reports/group-stat-team-top3-publication-r4-summary-2026-08-08.md)：
  用核心位红色示例解释 Stat 排名、四档建议、分档边界与队伍前三应如何一起阅读。
- [发布版基础字段说明](../../reports/group-stat-team-top3-publication-summary-2026-08-08.md)：逐项解释
  平均分、低迷分、样本和稳定率可以及不可以代表什么。
- [发布版 r2 修订说明](../../reports/group-stat-team-top3-publication-r2-2026-08-08.md)：记录移除
  队伍 ID 显示后的不可变重生成、数值一致性、审计与测试。
- [发布版 r3 修订说明](../../reports/group-stat-team-top3-publication-r3-2026-08-08.md)：记录移除
  来源显示、保留内部 provenance 与分档状态后的重生成和验收。
- [发布版 r4 实施与验收](../../reports/group-stat-team-top3-publication-r4-2026-08-08.md)：记录新增
  Stat 排名与基础建议的权威规则复用、正式哈希、冻结清单回归和全项目验收。
- [发布版实施与验收](../../reports/group-stat-team-top3-publication-revision-2026-08-08.md)：记录
  新旧数值逐字节一致、不可变 run、正式哈希、审计和项目回归。
- [v2 Stat 队伍 Top 3 技术版](stat-team-top3-evidence-v2.md)：为每个位置/颜色/Stat 列出点估计
  前三、稳定队伍 ID、均值/CVaR10、Series 样本数及 `P1/P3` 重采样频率；它是描述性扩展，
  作为上一版技术证据保留，不改变冻结的 v2 表、手册规则或 `draft` 标签。
- [Top 3 扩展技术报告](../../reports/group-stat-team-top3-evidence-extension-2026-08-07.md)：记录
  最小实现范围、兼容性哈希、正式重生成、确定性验收和可信度边界。
- [Top 3 易懂总结](../../reports/group-stat-team-top3-easy-summary-2026-08-07.md)：说明新增字段、
  为什么只列第一会误导，以及实际查表顺序。

- [生成率无关版 v1](playbook-rate-agnostic-v1.md)：三模型下有 5 个 Common 情形超过 10%
  重大损失上界，并有跨模型规则消融失败。
- [主模型 best-guess 版 v1](playbook-primary-model-v1.md)：93 个主模型 Common 情形均通过
  10% 线，但 12 条规则中只有 PM05、PM12 通过严格消融，故整版仍不能发布为可靠。
- [Stat、Quality、Trait 证据表](stat-quality-trait-evidence-v1.md)：独立于 Roll 求解器，包含
  七张完整 Stat 表和精确三格 Trait 条件；这是当前最扎实、可以直接查阅的部分。
- [P4 完整报告](../../reports/p4-independent-human-playbooks-2026-08-06.md)：记录冻结 hash、九格
  起始覆盖、40-Roll 验证、复杂度前沿、风险前沿、失败情形和运行时间。
- [P5 求解器报告](../../reports/p5-branch-capped-solver-2026-08-06.md)：只读记录限枝 solver 的
  条件 oracle、7/216 完整配对、约 29.58 小时全量投影和失败 escalation review；它没有改写
  本目录的任何规则。
- [P6 只读交叉审计](../../reports/p6-read-only-playbook-cross-audit-2026-08-06.md)：显式留出情景与
  P4/P5 交集均为 0，但只完成 9/108 行；已完成行中有 2 个 5% strict 警告、0 个
  10% 重大例外。审计状态是 `partial-draft`，不升级任何手册。
- [v1 证据包清单](evidence-package-v1.json)：固定 P3/P4/P5/P6 产物、两份手册、数据/规则
  身份与当前发布标签。
- [P7 本地交互顾问报告](../../reports/p7-local-interactive-group-roll-advisor-2026-08-06.md)：
  手工确认九格与实际 Roll 结果、确定性会话重放、一步诊断和最终队伍匹配。它是次要实验工具，
  不属于本手册发布证据包，也不改变任何规则或 `draft` 标签。
- [P0–P7 完成审计](../../reports/p0-p7-group-roll-completion-audit-2026-08-07.md)：汇总阶段
  gate、证据哈希、干净提交复现、最终回归与仍然生效的使用边界。

`draft` 的含义不是“所有建议都错”，而是整版尚未达到预先约定的证明门槛。不要把通过的
个别规则拼成一份未经验证的新手册；任何 v2 都必须在不看 P5 求解器输出的独立路线中重新
冻结并用新 seed 做完整确认。
