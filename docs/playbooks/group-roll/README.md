# Group Roll 人工手册索引

截至 `2026-08-06T08:15:00Z`，证据表已经可用，但两份 v1 操作手册都仍是 `draft`：

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
