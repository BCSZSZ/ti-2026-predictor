# Domain glossary

| Term | Canonical meaning |
|---|---|
| InGamePrediction / 游戏内预测 | Valve TI 活动中由玩家填写的结果槽位或淘汰赛节点。不是模型概率。 |
| Forecast / 模型预测 | 本项目在给定 `as_of` 下产生的概率分布与推荐。 |
| Game / 单局 | 一张地图，从选人到一方获胜。 |
| Series / 系列赛 | 两支队伍之间的 BO1/BO2/BO3/BO5，由若干 Game 组成。 |
| Period / 结算期 | Fantasy 锁定一次阵容并结算的一段赛事；2026 年为 Group 与 Main。 |
| Team identity / 战队身份 | Valve/OpenDota 的稳定 team ID，不等同于展示名称。 |
| Roster interval / 阵容区间 | 某选手为某战队生效的 `[valid_from, valid_to)` 时间区间。 |
| Fantasy role / 梦幻定位 | `core`（1/3 号位双人组）、`mid`（2 号位）、`support`（4/5 号位双人组）。 |
| War Banner / 战旗 | 某 Fantasy role 的徽标容器；小组期 3 槽，主赛事 5 槽。 |
| Emblem / 徽标 | 带颜色、统计项、品质和特质的 Fantasy 加分项。 |
| Coach title / 指导员称号 | 全阵容共享的前缀与后缀条件加成。 |
| Rule snapshot / 规则快照 | 从指定客户端 build 提取并哈希的活动规则集合。 |
| Data snapshot / 数据快照 | 在指定抓取时刻冻结的原始与规范化数据集合。 |
| Forecast run / 预测运行 | 规则、数据、配置、代码和随机种子全部固定的一次计算。 |
| Publishable / 可发布 | 审计通过，可作为游戏内填写依据；不代表必然正确。 |
