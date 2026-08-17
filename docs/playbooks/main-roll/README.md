# Main Fantasy 玩家资料

当前资料绑定 `2026-08-16T15:31:30Z` 的 actual 八队 Main 求解发布包：

- [Main 30 Roll 玩家手册](main-roll-publication-manual-v1.md)
- [Main Stat 与队伍 Top 3 完整表](stat-team-top3-publication-v1.md)
- [Main Title 分析与推荐](../../reports/ti2026-main-fantasy-title-recommendation-2026-08-17.md)
- [Main 概率参考：八队对位、预测期望与 Roll 随机机制](../../reports/ti2026-main-probability-reference-2026-08-17.md)

这四份资料与 Group 冻结历史版分开维护。Main 是三面五格、30 Roll、实际八队和完整双败
Series 情景；不得把 Group 三格手册的 B/C/D 操作规则直接搬到 Main。

数值证据由 `ti fantasy main-publication-evidence` 从当前内容寻址 Main release 生成。玩家启动
Streamlit 或本地版时不需要执行生成命令，两个入口会自动读取 `deploy/runtime/main-current.json`。
