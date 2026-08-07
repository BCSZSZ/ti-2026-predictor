# Group Roll 人工手册 v2 后续问题 memo

状态：**v2 已收口；两版手册保持 `draft`；本 memo 只登记问题和后续决策，不修改冻结证据**

- 日期：2026-08-07
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- v2 最终合并提交：`3bc904c44f762283f9aac18e8f3be08723aa749e`
- 正式 standalone：`fantasy-1c8871c419f59f08`
- 正式 path-pinned cross-audit：`fantasy-26e4f9240b19a518`

## 目的和边界

这份 memo 把 v2 的实际进步、退步、未解决风险和后续工作记录为可追踪的工程事实，避免后续
只记住“运行变快”或把个别通过规则误认为整本手册已经可靠。它不回写 v2 手册，不改变
release gate，不授权 v3 实装，也不把 solver/cross-audit 动作轨迹变成人工规则来源。

## 当前决策

1. v2 工程工作已经成功收口，但经验发布门禁失败；Rate-agnostic 和 Primary-model 均保持
   `draft`。
2. 当前最可靠、可以直接查阅的成果是 Stat/Quality/Trait 表：16 个 `exact`、2 个批准的
   `derived`、0 个 `proxy`。Coach 继续 `unavailable/excluded`。
3. Primary-model 是后续更有希望的研究方向，但现版不能整体发布；Rate-agnostic 更适合作为
   解释性基线，而不是在现有 12 条上继续做小补丁。
4. v2 候选、seed、Scenario 索引和正式产物保持不可变。任何 v3 必须独立冻结，并用全新的
   confirmation 与 held-out audit 验收。
5. 在新手册通过全部门禁前，不把本地实验顾问从 v1 切换到 v2/v3，也不启用完整 full-session
   planner。

## 已确认的进步

| 领域 | v2 结果 | 判断 |
| --- | --- | --- |
| 正式统计来源 | 16 `exact`、2 `derived`、0 `proxy` | 数据边界更清楚，缺失值没有伪装成零 |
| standalone | 34,560 个完整 40-Roll 会话，约 25 分钟 | 满足 30 分钟工程目标 |
| held-out cross-audit | 108/108，约 44–45 分钟 | 从旧吞吐约 7.9 小时投影缩短约 10.6 倍 |
| 日常完整成本 | standalone + cross-audit 约 70 分钟 | 不需要在 v1 后再追加 15 小时 |
| 确定性 | 两次完整 audit 的 run ID、semantic hash、file hash 相同 | 长运行可复现 |
| Primary 核心规则 | 7/12 通过消融；v1 为 2/12 | 规则支持面扩大，但尚未全过 |
| Rate 跨模型核心规则 | 4/12；v1 为 3/12 | 小幅增加，但不足以抵消整版失败 |

这些结果证明的是工程速度、来源治理和证据完整性提高。不同 seed、候选和 Scenario 下的分数
不能直接解释为 v2 对 v1 的因果得分提升。

## 问题台账

| ID | 优先级 | 已确认问题 | 影响 | 当前处理决定 |
| --- | --- | --- | --- | --- |
| GRV2-01 | 发布阻断 | 两份手册都未通过全部预注册门槛 | 不能标记为可靠或用于自动化 | 保持 `draft` |
| GRV2-02 | 发布阻断 | Primary 的 P2M01、P2M05、P2M09、P2M10、P2M11 消融失败 | 只有 7/12 核心规则获得支持 | v3 只能独立重新推导，不在 v2 上回写 |
| GRV2-03 | 发布阻断 | Primary 的 `default-knee` 与 `downside-first` 都降低均值和下尾 | 风险修正声明不成立 | 探索时只参考 `mean-first`，v3 不默认继承两项修正 |
| GRV2-04 | 高 | `P2M02` 在 `coverage-05`、剩余 3 Roll 时同时劣于直接刷新 | 存在方向性反例 | 作为新假设的调查入口，禁止针对该 audit 行调参 |
| GRV2-05 | 发布阻断 | Rate 的 10% Common 失败由 v1 的 5 个增至 v2 的 23 个；另有 96 个超过 5% | 整版退步，跨模型名称不代表安全 | 降级为解释性基线；若保留，必须从独立路线重做 |
| GRV2-06 | 高 | 预估小于约 1% 均值、0–2.5% 下尾空间尚未被证明兑现 | 不能声称得分提升 | 新版本必须报告配对效果和置信界，不用规则通过数代替收益 |
| GRV2-07 | 中 | 条件 exact 只覆盖剩余 1–3 Roll；没有新的 v2 full-session P5 | 不能声称 40-Roll 全局最优 | 优先扩展可承受的 exact 边界，不因历史 P5 失败直接上 full planner |
| GRV2-08 | 中 | 本地实验顾问仍冻结为 v1 | UI 与 v2 文档不是同一身份 | 发布门禁通过前不切换 |
| GRV2-09 | 高 | 当前 replay JAR 与历史回填 JAR 文件哈希不同 | 构建身份尚未完全闭合 | 固定并记录 JDK/Maven/打包环境；不改写历史 raw 元数据 |
| GRV2-10 | 低 | 正常完整证据仍需约 70 分钟 | 频繁迭代成本仍高 | 正确性优先；只做语义保持且有基准证明的优化 |

GRV2-04 的正式反例不推翻 P2M02 在 standalone 消融中的支持；它说明支持不是所有局部状态下
都方向正确。GRV2-05 中 Rate 的局部 81 行审计没有 10% 重大例外，也不能覆盖其完整 40-Roll
standalone 的 23 个失败。两组证据必须同时保留。

## 后续路线

详细工作包和数据防火墙见
[v3 调研笔记](../plans/group-roll-playbook-v3-investigation-notes.md)。推荐顺序是：

1. 只读建立 Primary 五条失败规则、两个风险修正、P2M02 方向反例和 Rate 失败的分类图谱；
2. 先闭合 replay JAR 工具链身份，避免新数据处理引入来源歧义；
3. 用独立人工路线冻结更短的 Primary 核心候选，并决定 Rate 是重做还是归档；
4. 使用新 seed、全新且互不相交的 screening、confirmation、cross-audit 集验收；
5. 只有保留的每条 Core 规则、风险修正、Common 10% 门槛和方向性审计全部通过，才讨论发布和
   顾问集成。

重复运行当前 v2 seed、从现有 audit 行直接调阈值、把现有 7 条规则拼成未经新验证的手册，均
不构成后续验收。

## 证据入口

- [v2 易懂总结](group-roll-playbook-v2-summary-2026-08-07.md)
- [v2 standalone validation](group-roll-playbook-v2-p3-standalone-validation-2026-08-07.md)
- [v2 held-out cross-audit](group-roll-playbook-v2-p4-read-only-cross-audit-2026-08-07.md)
- [v2 P5 项目审计](group-roll-playbook-v2-p5-project-audit-2026-08-07.md)
- [v2 最终证据包](../playbooks/group-roll/evidence-package-v2.json)
