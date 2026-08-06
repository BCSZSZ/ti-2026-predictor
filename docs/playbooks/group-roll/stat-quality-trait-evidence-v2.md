# Group Roll v2：Stat、Quality 与 Trait 证据表

状态：**P2 独立推导冻结；尚未开始 v2 P4 验证**

- 显式 `as_of`：`2026-08-06T17:27:00Z`
- P3 run：`fantasy-bcffa25a645c8438`
- P3 evidence：`de84baa3081ac5d81e55ec9110766d96c26071a907b7a74824bff8e8faf7a42f`
- P3 common Scenario：`22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3`
- Rule snapshot：`20260806T172612Z-702ddf2a6953`，语义 SHA-256 `702ddf2a…`

本文只包含人工路线可用的受治理算术证据，不包含 P5/P6 solver 或 oracle 动作。每个 Stat
先在 16 队中取本项最佳 Team matching，再按同一角色/颜色最佳项归一为 100；完整三格仍要
重新做同队匹配，不能把三个单项最佳直接相加。

## Provenance gate

| 类型 | 唯一 Stat 数 | v2 正式用途 |
| --- | ---: | --- |
| `exact` | 16 | 允许进入 P3、分档和手册 |
| 获准 `derived` | 2 | `creep_score=last_hits+denies`；`teamfight_participation=(kills+assists)/team_total_kills`，允许进入 |
| `proxy` | 0 | 一律排除；不能填补 exact `null` |
| `unavailable` | 0 | 一律失败关闭；不能当作 0 |

42 个 role/color/stat 行的合格 row provenance 与完整 Series-block provenance 覆盖率均为
100%。Madstone、Smoke、Watcher、Lotus、Tormentor 使用 P1 原生 replay counter；诊断事件
proxy 仍单独保留但没有进入这里。Coach 缺少场景对齐候选，继续是
`unavailable/excluded`，不是零加成。

新的 `as_of` 没有新增比赛或 Fantasy 样本，只使预注册时间衰减权重前移 9 小时。与 v1
相比，42 行的排序、分档和 bootstrap 边界标记全部不变；相对指数最大变化约 0.0055 个百分
点。以下仍是新的 P3 重新计算值，而不是复制旧 hash。

## 分档规则

- `hard-protect`：本色最佳 Stat 的第二队低于最佳队 44%；本次七表仍没有此档。
- `keep`：相对最佳至少 84.6%。
- `conditional-reroll`：44%（含）至 84.6%（不含）。
- `priority-repair`：低于 44%。
- `边界`表示完整 Series cluster bootstrap 区间跨过分档线，不会自动改变点分档。

## Core · Red

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| creep_score | 100.0 | 4292.7 | 4043.3 | 3686.8 | keep | 稳定 | derived |
| deaths | 83.0 | 3564.2 | 3393.8 | 3241.3 | conditional-reroll | 边界 | exact |
| gpm | 75.1 | 3225.4 | 3194.1 | 3055.1 | conditional-reroll | 稳定 | exact |
| tower_kills | 64.6 | 2771.2 | 2695.3 | 2410.7 | conditional-reroll | 稳定 | exact |
| kills | 61.7 | 2649.1 | 2527.8 | 2251.9 | conditional-reroll | 稳定 | exact |
| madstone_collected | 61.1 | 2624.8 | 2512.9 | 2021.6 | conditional-reroll | 稳定 | exact |

## Core · Green

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| teamfight_participation | 100.0 | 3286.2 | 3271.7 | 3064.2 | keep | 边界 | derived |
| tormentor_kills | 95.6 | 3140.2 | 3043.7 | 2605.5 | keep | 稳定 | exact |
| roshan_kills | 78.4 | 2576.5 | 2560.4 | 2067.4 | conditional-reroll | 边界 | exact |
| first_blood | 47.8 | 1570.1 | 1520.5 | 1172.0 | conditional-reroll | 边界 | exact |
| stuns | 42.2 | 1385.2 | 1378.5 | 1132.4 | priority-repair | 边界 | exact |
| courier_kills | 40.1 | 1318.4 | 1272.9 | 922.6 | priority-repair | 边界 | exact |

## Mid · Red

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| creep_score | 100.0 | 3946.0 | 3888.7 | 3395.9 | keep | 稳定 | derived |
| deaths | 91.8 | 3622.9 | 3576.4 | 3360.0 | keep | 边界 | exact |
| gpm | 81.1 | 3201.6 | 3036.8 | 2879.9 | conditional-reroll | 边界 | exact |
| kills | 75.5 | 2979.3 | 2881.0 | 2647.9 | conditional-reroll | 边界 | exact |
| tower_kills | 73.2 | 2889.0 | 2780.5 | 1799.8 | conditional-reroll | 稳定 | exact |
| madstone_collected | 61.0 | 2406.4 | 1951.8 | 1531.0 | conditional-reroll | 边界 | exact |

## Mid · Blue

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| runes_grabbed | 100.0 | 4718.3 | 4703.9 | 4214.6 | keep | 稳定 | exact |
| camps_stacked | 60.2 | 2842.2 | 2396.2 | 1738.9 | conditional-reroll | 稳定 | exact |
| lotuses_gained | 46.1 | 2174.2 | 1599.3 | 1160.2 | conditional-reroll | 边界 | exact |
| watchers_taken | 21.5 | 1012.2 | 1007.9 | 716.0 | priority-repair | 稳定 | exact |
| wards_placed | 13.7 | 644.3 | 641.7 | 520.1 | priority-repair | 稳定 | exact |
| smokes_used | 11.6 | 549.4 | 458.6 | 153.5 | priority-repair | 稳定 | exact |

## Mid · Green

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| teamfight_participation | 100.0 | 3792.7 | 3687.0 | 3483.9 | keep | 稳定 | derived |
| tormentor_kills | 75.0 | 2844.9 | 2697.5 | 2208.3 | conditional-reroll | 边界 | exact |
| stuns | 61.6 | 2336.8 | 2318.7 | 1517.1 | conditional-reroll | 稳定 | exact |
| roshan_kills | 61.0 | 2312.2 | 2225.7 | 1728.5 | conditional-reroll | 稳定 | exact |
| courier_kills | 51.4 | 1950.7 | 1919.5 | 1258.5 | conditional-reroll | 稳定 | exact |
| first_blood | 50.7 | 1923.4 | 1685.4 | 1065.9 | conditional-reroll | 边界 | exact |

## Support · Blue

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| camps_stacked | 100.0 | 3326.6 | 3236.4 | 2714.7 | keep | 稳定 | exact |
| wards_placed | 99.0 | 3292.4 | 3028.3 | 2776.4 | keep | 边界 | exact |
| watchers_taken | 95.8 | 3186.4 | 3046.7 | 2402.1 | keep | 边界 | exact |
| lotuses_gained | 92.1 | 3065.2 | 2702.7 | 2015.4 | keep | 边界 | exact |
| smokes_used | 92.0 | 3059.4 | 2770.0 | 2523.5 | keep | 边界 | exact |
| runes_grabbed | 63.4 | 2109.4 | 1566.2 | 1309.3 | conditional-reroll | 稳定 | exact |

## Support · Green

| Stat | 指数 | 最佳队期望 | 第二 | 16队均值 | 分档 | 稳定性 | Provenance |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| teamfight_participation | 100.0 | 3425.2 | 3354.7 | 3210.8 | keep | 稳定 | derived |
| tormentor_kills | 78.4 | 2684.2 | 2262.9 | 1970.9 | conditional-reroll | 边界 | exact |
| courier_kills | 65.7 | 2249.3 | 1996.4 | 1364.6 | conditional-reroll | 稳定 | exact |
| stuns | 54.4 | 1861.9 | 1797.0 | 1486.4 | conditional-reroll | 稳定 | exact |
| first_blood | 45.8 | 1569.1 | 1448.8 | 1144.7 | conditional-reroll | 边界 | exact |
| roshan_kills | 17.7 | 607.3 | 593.6 | 397.2 | priority-repair | 稳定 | exact |

## Quality 精确表

| Tier | 基础加成 | 不降级 +1 增量 | 主模型随机重随后期望加成 |
| --- | ---: | ---: | ---: |
| T1 | +10% | +20pp | +44.68% |
| T2 | +30% | +30pp | +44.68% |
| T3 | +60% | +40pp | +44.68% |
| T4 | +100% | +50pp | +44.68% |
| T5 | +150% | 0pp | +44.68% |

主模型下单格随机品质重随只对 T1/T2 为正期望；Rate-agnostic 只把 T1 视为任何结果都
不降。操作 23 永不降级，操作 24 则必须同时看三格品质与基础贡献，不能当作固定增益。

## Trait 三格精确配方

令未计 Trait 的三格贡献为 `B1,B2,B3`，`E=B1+B3`，`M=B2`：

| 配方 | 条件 | Trait 增量 | 使用边界 |
| --- | --- | ---: | --- |
| Friendly/Friendly/Friendly | 三格均 Friendly | `0.5(E+M)` | 品质不全异且贡献均衡 |
| Fractal/Fractal/Fractal | 三品质两两不同 | `0.6(E+M)` | 品质全异且贡献不极端偏置 |
| Vampiric/Benevolent/Vampiric | 始终 | `0.7E-0.2M` | 胜 Friendly 需 `E>3.5M` |
| Benevolent/Vampiric/Benevolent | 始终 | `0.9M-0.1E` | 胜 Friendly 需 `M>1.5E` |
| 单个 Unique | 全旗恰好一个 Unique | 该格 `+0.3B` | 不能成套时的稳定填充 |

以上由全部 `5^3=125` 个有序 Trait 组合核对。局部 Trait 名称没有脱离位置、Quality 和
三格贡献后的独立等级。
