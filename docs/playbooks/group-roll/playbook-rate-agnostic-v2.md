# Group 40 Roll 人工手册：生成率无关版 v2

状态：**P2 候选已冻结，尚未经过 v2 P4 独立确认；当前不是可靠发布版**

- 适用：Group 的三格战旗与 40 次 Roll；Main 继续不适用。
- `as_of`：`2026-08-06T17:27:00Z`。
- 规则快照：`20260806T172612Z-702ddf2a6953`；客户端规则语义与 v1 相同。
- 证据：P3 `de84baa3…` 与
  [v2 Stat/Quality/Trait 表](stat-quality-trait-evidence-v2.md)。

这版不假装知道后台出现率或结果率。规则来自客户端合法结果集合、当前 Stat 分档以及精确
Quality/Trait 算术；没有使用 P5/P6 solver 或 oracle 动作来生成、排序或修补规则。

## 快查页 1：先看三格

位置固定为 Core `Red/Green/Red`、Mid `Red/Blue/Green`、Support
`Blue/Green/Blue`。

| 位置 | keep | conditional-reroll | priority-repair |
| --- | --- | --- | --- |
| Core Red | Creep Score | Deaths, GPM, Tower, Kills, Madstones | 无 |
| Core Green | Teamfight, Tormentor | Roshan, First Blood | Stuns, Courier（均为边界） |
| Mid Red | Creep Score, Deaths | GPM, Kills, Tower, Madstones | 无 |
| Mid Blue | Runes | Camps, Lotuses | Watchers, Wards, Smokes（均稳定） |
| Mid Green | Teamfight | Tormentor, Stuns, Roshan, Courier, First Blood | 无 |
| Support Blue | Camps, Wards, Watchers, Lotuses, Smokes | Runes | 无 |
| Support Green | Teamfight | Tormentor, Courier, Stuns, First Blood | Roshan（稳定） |

Trait 只按完整三格判断：品质全异时优先核对三 Fractal；均衡旗核对三 Friendly；边贡献和
超过中间 3.5 倍时才考虑 `Vampiric/Benevolent/Vampiric`。单 Unique 是不能成套时的填充，
两个 Unique 都不生效。

## 快查页 2：按顺序检查 12 条发布候选

阶段为前期 `40–26`、中期 `25–11`、末期 `10–1`。每次从第 1 条向下检查，命中第一条
就执行；同条多个动作时，先比较最差合法结果，再比较最好合法结果。

1. **随机 +1 品质（23）**：有任一战旗不是全 T5 就拿，优先低品质且基础贡献高的旗。
2. **Mid 单格 C 档 Stat（11/14/17）**：对应颜色只影响 Mid 一格，优先修蓝色
   Watchers/Wards/Smokes。
3. **末期支持保护**：最后十次只应用“所有合法结果都不低于当前代理值”的动作；否则刷新。
4. **稳定绿色 C 档**：只精确修 Support Green 的 Roshan；Core Stuns/Courier 是 bootstrap
   边界项，不再放入默认 C 档规则。
5. **精确 T1 品质**：只在前中期、且选项不会碰到更高品质格时使用。
6. **整色全 T1 品质**：只在前期使用。v1 的全阶段 RA06 已收窄，避免中末期机会成本。
7. **精确失效蓝色 Trait**：只在前中期、不拆完整套装，且目标格贡献至少为相邻格 20%。
8. **稳定绿色 B 档**：前中期可精确洗非边界 conditional-reroll；边界项默认不洗。
9. **只差一格的 Trait 套装**：前中期且蓝色精确选项命中唯一缺口时才追。
10. **Stat 支持检查**：前中期只有当所有合法 Stat 结果都不降时才应用其它 Stat 选项。
11. **Quality 支持检查**：前中期只有当所有合法 Quality 结果都不降时才应用其它品质选项。
12. **Trait 支持检查**：前中期只有当所有合法 Trait 结果都不降时才应用其它 Trait 选项。

统一兜底：**没有规则支持应用当前选项时，花 1 次 Roll 刷新三个共享选项。**

8/12/16 嵌套候选已经冻结。第 13–16 条只用于 P3 的复杂度前沿：前期绿色边界 B 档、
精确 T2、整色失效 Trait、以及仅 mean-first 的中期低品质二升一降；它们不出现在这 12 条
发布候选中。v1 的精确 T2 默认规则与前期 T3 二升一降已从发布序列删除。

风险修正不复制整本手册：`default-knee` 与 `downside-first` 都不启用二升一降和边界项；
`mean-first` 只在 12 条之外的复杂度挑战中允许它们。该选择仍需 P3 新 seed 验证，不能因为
规则看起来更保守就预先标成可靠。

## 相对 v1 的可验证变化

- 保留 v1 中跨三模型通过消融的“不降级 +1”“Mid 单格 C 档”“末期全支持不降”三项原则；
- v1 RA06 从全阶段收窄为前期；RA10 降为未发布挑战；RA12 的前期 T3 路径删除；
- 用 mutation 类型分开的全支持不降规则补足可读操作，不新增 coverage-case 特判；
- Stat 表没有改档，变化来自规则简化而不是改写数据。

P3/P4 完成前，本文件只能作为候选操作稿；不要把“独立推导完成”误解为“可靠性验收通过”。
