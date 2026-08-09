# TI 2026 玩家发布包（2026-08-09）

本文件夹只收录当前仍有效的玩家版 Markdown。核心变化是：7.41e 的单局证据在所有中央权重使用处
额外乘 2；其他大版本、赛事目录等级和时间衰减不变。Stat、Title 和小组赛 Forecast 已重新生成。

## 本包统一采用的加权方式

队伍实力、胜负关系、Fantasy Stat/Top 3 和 Title 统一使用：

`单局证据权重 = 大版本权重 × 当前精确版本倍率 × 赛事目录等级权重 × 2^(-距 as_of 天数/60)`

- 7.41 为 1.00，其中当前精确版本 7.41e 再乘 2.00；其他 7.41 字母版本不额外放大；
- 7.40 为 0.15，更早大版本为 0；
- OpenDota `premium` / `professional` 分别为 1.00 / 0.75，其他目录等级为 0；
- 时间每 60 天减半；社区 Tier、奖金和名次不参与加权。

完整解释、示例、适用范围和可信度边界见 [统一加权方式](WEIGHTING.md)。2 倍是明确的模型政策，
不是声称它已经被证明为理论最优值。

## 最短阅读顺序

1. [方法极简速查](reports/ti2026-methodology-quick-reference-2026-08-09.md)：数据、计分、平均分、
   Series 和 7.41e 权重怎样算。
2. [Fantasy Stat Top 3](playbooks/group-roll/stat-team-top3-publication-v3.md)：查 42 项排名、建议和
   前三队伍；先看[易懂说明](reports/group-stat-team-top3-publication-summary-2026-08-09.md)也可以。
3. [Title 分析与推荐](reports/ti2026-fantasy-title-recommendation-2026-08-09.md)：默认仍是
   `Cerulean + the Clutch`，并解释两个一血内部字段为什么暂时排除。
4. [Roll 手册易懂总结](reports/group-roll-publication-manual-summary-2026-08-09.md)：先看明确的
   Stat/Tier/Trait 接受与拒绝标准；完整条件见
   [Roll 玩家手册](playbooks/group-roll/group-roll-publication-manual-v3.md)。
5. [小组赛预测易懂总结](reports/ti2026-group-forecast-publication-summary-2026-08-09.md)：当前第一集团
   是 Liquid 与 Yandex；完整排名和矩阵见[完整预测](reports/ti2026-group-forecast-publication-2026-08-09.md)。
6. [2026 年战队已获奖金累计](reports/ti2026-team-prize-ytd-2026-08-08.md)：查看每队今年实际获得
   的奖金累计与逐赛事明细。

## Fantasy

- [Stat Top 3 易懂说明](reports/group-stat-team-top3-publication-summary-2026-08-09.md)
- [Stat Top 3 完整发布表](playbooks/group-roll/stat-team-top3-publication-v3.md)
- [Title 分析、排名与内部字段说明](reports/ti2026-fantasy-title-recommendation-2026-08-09.md)
- [Roll 玩家手册易懂总结](reports/group-roll-publication-manual-summary-2026-08-09.md)
- [Roll 玩家手册完整发布版](playbooks/group-roll/group-roll-publication-manual-v3.md)

## 小组赛预测

- [7.41e 权重版易懂总结](reports/ti2026-group-forecast-publication-summary-2026-08-09.md)
- [综合实力排名、按队名拆分的完整对局表与填写建议](reports/ti2026-group-forecast-publication-2026-08-09.md)
- [7.41 完整系列赛证据展开](reports/ti2026-group-current-patch-series-evidence-2026-08-08.md)
- [2026 年战队已获奖金累计](reports/ti2026-team-prize-ytd-2026-08-08.md)
- [赛事 Tier 与赛事总奖池说明](reports/ti2026-group-event-tier-prize-summary-2026-08-08.md)

## 方法与可信度

- [统一加权方式](WEIGHTING.md)
- [方法极简速查](reports/ti2026-methodology-quick-reference-2026-08-09.md)
- [方法与证据易懂总结](reports/ti2026-methodology-and-evidence-summary-2026-08-09.md)
- [方法与证据权威性报告](reports/ti2026-methodology-and-evidence-authority-report-2026-08-09.md)

## 版本边界

- 7.41e 乘 2 是明确的建模政策，不是已证明最优的自然常数；
- 旧 Roll v2 的完整 standalone/cross-audit 没有在新权重下重跑，所以 v3 手册只刷新当前数值，
  B/C/D 操作规则继续沿用原验证身份；
- Group Forecast 在历史留出集上只有 56.25% 单局命中率，概率未校准；
- “赛事总奖池”和“战队今年实际获得的奖金”是两份不同表；
- 所有百分比、排名和槽位仍是决策辅助，不是 Valve 保证答案。
