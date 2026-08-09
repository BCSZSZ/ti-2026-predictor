# TI 2026 玩家发布包（2026-08-09）

本文件夹只保留当前有效、能够独立提供完整信息的正式文档。同一主题只保留一个入口，避免重复
文件让人难以判断应该打开哪一份。移出的转述版仍保留在仓库原报告目录中，发布包没有删除正式
完整版或底层证据。

## Fantasy

1. [Stat 与队伍 Top 3 完整表](playbooks/group-roll/stat-team-top3-publication-v3.md)：42 个
   位置×颜色×Stat 组合的明确排名、保留/改善建议、对应位置选手池的前三队伍和稳定性。
2. [Title 分析与推荐](reports/ti2026-fantasy-title-recommendation-2026-08-09.md)：Prefix、Suffix、
   触发率、默认选择和客户端条件冲突。
3. [Group 40 Roll 玩家手册](playbooks/group-roll/group-roll-publication-manual-v3.md)：Stat、Tier、
   Trait 的接受/拒绝标准，Trait 配方计算、追逐概率和停止线。

## 小组赛预测与赛果证据

1. [综合实力、队伍对局关系与填写建议](reports/ti2026-group-forecast-publication-2026-08-09.md)：
   正式排名、实力带、按队名展开的胜负关系和 16 个预测槽位。
2. [7.41 完整系列赛证据](reports/ti2026-group-current-patch-series-evidence-2026-08-08.md)：
   按版本、赛事和对手展开的 Series 与单局记录。
3. [2026 年战队已获奖金累计](reports/ti2026-team-prize-ytd-2026-08-08.md)：每队今年已经确认获得
   的奖金及逐赛事明细。
4. [赛事档位与赛事总奖池](reports/ti2026-group-event-tier-prize-2026-08-08.md)：社区赛事
   Tier、赛事性质和总奖池；它与战队实际获得的奖金不是同一个指标。

## 方法、权重与可信度

1. [方法速查](reports/ti2026-methodology-quick-reference-2026-08-09.md)：数据来源、计分公式、均值、
   Series 和权重的简要定义。
2. [统一加权方式](WEIGHTING.md)：7.41e 双倍权重及大版本、赛事级别、时间衰减的完整政策。
3. [方法与证据权威性报告](reports/ti2026-methodology-and-evidence-authority-report-2026-08-09.md)：
   数据基础、分析方法、复算入口、可信范围和已知限制。

本包统一使用：

`单局证据权重 = 大版本权重 × 当前精确版本倍率 × 赛事目录等级权重 × 2^(-距 as_of 天数/60)`

其中 7.41e 在其他条件相同时额外乘 2；社区 Tier、奖金和名次不进入模型权重。

## 版本边界

- 7.41e 乘 2 是明确的建模政策，不是已证明最优的自然常数；
- v3 Trait 追逐线是精确的一步算术门槛，不冒充整段 40 Roll 已验证核心规则；
- Group Forecast 的历史留出集单局命中率为 56.25%，概率未校准；
- 所有百分比、排名和槽位都是决策辅助，不是 Valve 保证答案。
