# Group Roll v1：Stat、Quality 与 Trait 证据表

冻结时间：`2026-08-06T08:15:00Z`  
P3 证据包：`f42517fa5c0c596f2b15397ad2206136d48b0ff7fef578e131b4a919aa7fd9b8`

本文是两版人工手册共同使用的只读算术证据，不是 Roll 求解器输出。所有 Stat 数值均来自
P3 的 8,192 个公共 Group 场景；每个 Stat 先在 16 支队伍中选择其单项最佳队伍，再以同一
角色/颜色的最高值归一为 100。三格终局仍必须重新做同队匹配，因此“单项最佳”不能相加，
Top 3 只是描述性优先级，不是三格锁定配方。

## 分档规则

- `hard-protect`：仅当本色最佳 Stat 的第二名队伍表现低于最佳队伍的 44% 时成立。本次七表
  均不满足，所以没有 hard-protect。
- `keep`：相对最佳值至少 84.6%。
- `conditional-reroll`：相对值从 44%（含）到 84.6%（不含）。
- `priority-repair`：低于 44%。
- `边界`只表示完整 Series 分组 bootstrap 的 95% 区间跨过 44% 或 84.6%；它不改变点估计
  分档。42 行的合格数据覆盖率均为 100%，每支队伍至少 10 个完整 Series block。

表中分数是该 Stat 在 Group 场景中的期望贡献；`第二`和`16队均值`用于显示队伍依赖性。
每张表都存在组合冲突：单项最佳队伍可能不同，最终三格必须匹配同一队。

## Core · Red（描述性 Top 3：Creep Score、Deaths、GPM）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| creep_score | 100.0 | 4292.7 | 4043.3 | 3686.8 | keep | 稳定 |
| deaths | 83.0 | 3564.2 | 3393.8 | 3241.3 | conditional-reroll | 边界 |
| gpm | 75.1 | 3225.4 | 3194.1 | 3055.1 | conditional-reroll | 稳定 |
| tower_kills | 64.6 | 2771.2 | 2695.3 | 2410.7 | conditional-reroll | 稳定 |
| kills | 61.7 | 2649.1 | 2527.8 | 2251.9 | conditional-reroll | 稳定 |
| madstone_collected | 61.1 | 2624.8 | 2512.9 | 2021.6 | conditional-reroll | 稳定 |

## Core · Green（描述性 Top 3：Teamfight、Tormentor、Roshan）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| teamfight_participation | 100.0 | 3286.2 | 3271.7 | 3064.2 | keep | 边界 |
| tormentor_kills | 95.6 | 3140.2 | 3043.7 | 2605.5 | keep | 稳定 |
| roshan_kills | 78.4 | 2576.5 | 2560.4 | 2067.4 | conditional-reroll | 边界 |
| first_blood | 47.8 | 1570.1 | 1520.5 | 1172.0 | conditional-reroll | 边界 |
| stuns | 42.2 | 1385.2 | 1378.4 | 1132.4 | priority-repair | 边界 |
| courier_kills | 40.1 | 1318.4 | 1272.9 | 922.6 | priority-repair | 边界 |

## Mid · Red（描述性 Top 3：Creep Score、Deaths、GPM）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| creep_score | 100.0 | 3946.0 | 3888.7 | 3395.9 | keep | 稳定 |
| deaths | 91.8 | 3622.9 | 3576.4 | 3360.0 | keep | 边界 |
| gpm | 81.1 | 3201.6 | 3036.8 | 2879.9 | conditional-reroll | 边界 |
| kills | 75.5 | 2979.3 | 2881.0 | 2647.9 | conditional-reroll | 边界 |
| tower_kills | 73.2 | 2889.1 | 2780.5 | 1799.8 | conditional-reroll | 稳定 |
| madstone_collected | 61.0 | 2406.4 | 1951.8 | 1531.0 | conditional-reroll | 边界 |

## Mid · Blue（描述性 Top 3：Runes、Camps、Lotuses）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| runes_grabbed | 100.0 | 4718.3 | 4703.9 | 4214.6 | keep | 稳定 |
| camps_stacked | 60.2 | 2842.4 | 2396.2 | 1738.9 | conditional-reroll | 稳定 |
| lotuses_gained | 46.1 | 2174.5 | 1599.1 | 1160.3 | conditional-reroll | 边界 |
| watchers_taken | 21.5 | 1012.2 | 1007.9 | 716.0 | priority-repair | 稳定 |
| wards_placed | 13.7 | 644.3 | 641.7 | 520.1 | priority-repair | 稳定 |
| smokes_used | 11.6 | 549.4 | 458.6 | 153.5 | priority-repair | 稳定 |

## Mid · Green（描述性 Top 3：Teamfight、Tormentor、Stuns）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| teamfight_participation | 100.0 | 3792.7 | 3687.0 | 3483.9 | keep | 稳定 |
| tormentor_kills | 75.0 | 2845.1 | 2697.5 | 2208.3 | conditional-reroll | 边界 |
| stuns | 61.6 | 2336.8 | 2318.7 | 1517.1 | conditional-reroll | 稳定 |
| roshan_kills | 61.0 | 2312.2 | 2225.7 | 1728.5 | conditional-reroll | 稳定 |
| courier_kills | 51.4 | 1950.7 | 1919.7 | 1258.5 | conditional-reroll | 稳定 |
| first_blood | 50.7 | 1923.4 | 1685.4 | 1065.9 | conditional-reroll | 边界 |

## Support · Blue（描述性 Top 3：Camps、Wards、Watchers）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| camps_stacked | 100.0 | 3326.7 | 3236.3 | 2714.7 | keep | 稳定 |
| wards_placed | 99.0 | 3292.4 | 3028.3 | 2776.4 | keep | 边界 |
| watchers_taken | 95.8 | 3186.4 | 3046.7 | 2402.1 | keep | 边界 |
| lotuses_gained | 92.1 | 3065.2 | 2702.7 | 2015.4 | keep | 边界 |
| smokes_used | 92.0 | 3059.4 | 2770.0 | 2523.5 | keep | 边界 |
| runes_grabbed | 63.4 | 2109.4 | 1566.2 | 1309.3 | conditional-reroll | 稳定 |

## Support · Green（描述性 Top 3：Teamfight、Tormentor、Courier）

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| teamfight_participation | 100.0 | 3425.2 | 3354.7 | 3210.8 | keep | 稳定 |
| tormentor_kills | 78.4 | 2684.2 | 2262.9 | 1970.9 | conditional-reroll | 边界 |
| courier_kills | 65.7 | 2249.3 | 1996.4 | 1364.5 | conditional-reroll | 稳定 |
| stuns | 54.4 | 1861.9 | 1797.0 | 1486.4 | conditional-reroll | 稳定 |
| first_blood | 45.8 | 1569.1 | 1448.8 | 1144.7 | conditional-reroll | 边界 |
| roshan_kills | 17.7 | 607.3 | 593.6 | 397.2 | priority-repair | 稳定 |

## Quality 精确表

| Tier | 基础加成 | 不降级 +1 的增量 | 主模型随机重随后的期望加成 |
| --- | ---: | ---: | ---: |
| T1 | +10% | +20pp | +44.68%（全表共同值） |
| T2 | +30% | +30pp | +44.68%（全表共同值） |
| T3 | +60% | +40pp | +44.68%（全表共同值） |
| T4 | +100% | +50pp | +44.68%（全表共同值） |
| T5 | +150% | 0pp（封顶） | +44.68%（全表共同值） |

因此主模型下，单格品质随机重随只对 T1/T2 是正期望；Rate-agnostic 版只把 T1 视为
“所有可能结果不更差”。操作 23 的随机 `+1` 永不降级，但可能打到已是 T5 的格而无变化。
操作 24 的“二升一降”不是普遍正收益，必须同时看三格品质和三格基础贡献。

## Trait 三格精确配方

令未计 Trait 的三格贡献为 `B1, B2, B3`，`E = B1 + B3`，`M = B2`。以下增量均是
相对未计 Trait 的精确增量：

| 配方（左/中/右） | 生效条件 | Trait 增量 | 何时优先 |
| --- | --- | ---: | --- |
| Friendly / Friendly / Friendly | 三格均 Friendly | `0.5(E+M)` | 品质不全异且贡献较均衡的默认套装 |
| Fractal / Fractal / Fractal | 三个品质两两不同 | `0.6(E+M)` | 品质全异且贡献不极端偏置的默认套装 |
| Vampiric / Benevolent / Vampiric | 始终 | `0.7E-0.2M` | 仅当两边合计明显压过中间；要胜 Friendly 需 `E>3.5M` |
| Benevolent / Vampiric / Benevolent | 始终 | `0.9M-0.1E` | 仅当中间极重；要胜 Friendly 需 `M>1.5E` |
| 单个 Unique | 全旗恰好一个 Unique | 该格 `+0.3B` | 不能成套时的稳定填充；两个以上 Unique 均不触发 |

所以“Vampiric 放两边、Benevolent 放中间”是**有条件的边重配方**，不是通用答案。
当品质全异时，三 Fractal 对每格都是 +60%；V/B/V 要超过它需 `E>8M`。枚举全部
`5^3=125` 个有序 Trait 组合得到相同结论；任何局部 Trait 建议都必须服从完整三格计算。

## 使用限制

- Coach 缺少完整、场景对齐的前后缀候选，正式估值为 `unavailable/excluded`，不是零分。
- Red Madstones、Blue Smokes/Watchers/Lotuses、Green Tormentor 均使用 P1 原生 replay
  counter；没有用通用 proxy 替代。
- 表中“全队最佳”是历史场景估计，不证明未来生成率，也不证明某个单项与另两格能在同一
  战队上同时达到单项最佳。

