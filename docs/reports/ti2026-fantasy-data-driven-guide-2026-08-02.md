# TI 2026 Group Fantasy 数据驱动制作指南

## 结论状态

- `as_of`：`2026-08-02T13:32:19Z`
- 运行 ID：`fantasy-1f251dcd21e52138`
- Period：Group；Core `Red / Green / Red`，Mid `Red / Blue / Green`，Support `Blue / Green / Blue`
- 状态：`warning`。统计优先级可以使用，但在读取个人 War Banner、剩余 roll 和三个实时选项前，不能给出逐次点击的全局最优证明。
- 规则快照：`20260802T071030Z-803d58a3f861`
- 规则 SHA-256：`406ace33728b2fa36572c575d67f6d742d236ec9dce448f9c222949da9497c9e`
- 数据 SHA-256：`571c44c6e302994c1ae34d17c9747d0517d3650af656e0efed52430a92b5391e`

本文把 Maroomm 社区指南的表现形式保留下来，但箭头来自本项目当前数据，而不是照抄帖子的固定顺序。社区指南仍作为独立基线，见 [`fantasy-league-2026-reddit-guide-audit.md`](../research/fantasy-league-2026-reddit-guide-audit.md)。机器可读的完整分数、覆盖率和候选队伍位于本次运行的 [`details.json`](../../artifacts/fantasy-1f251dcd21e52138/details.json) 与 [`recommendations.json`](../../artifacts/fantasy-1f251dcd21e52138/recommendations.json)。

## 一页版 TL;DR

### 选手组

当前数据的前四候选为：

| Role | 按均值排序的候选组 |
| --- | --- |
| Core | Team Yandex：watson + DM；BoomBoys：Kiritych + MieRo；TEAM VISION：Satanic + Noticed；LGD Gaming：Yuma + Wisper |
| Mid | TEAM VISION：No[o]ne；BoomBoys：gpk；Team Resilience：Echozz；Team Falcons：Malr1ne |
| Support | Team Yandex：Saksa + Maladych；Team Spirit：rue + not_me；LGD Gaming：Thiolicor + KingJungles；Team Falcons：Cr1t- + Sneyking |

不考虑个人已有 Quality/Trait 时：

- 均值目标：`Yandex Core + TEAM VISION / No[o]ne Mid + Yandex Support`。
- Top 10% 与极高上限的 Top 100 代理目标：把 Mid 换成 `BoomBoys / gpk`，其余不变。

这些是候选池，不是要求无条件选择第一名。随机获得的 Emblem 差距可能大于相邻候选选手组的差距。

### Emblem 实用优先级

这里的 `≈` 表示差距很小；`≫` 表示出现了明显断层。

| War Banner | 当前实用顺序 | 怎么用 |
| --- | --- | --- |
| Core Red（两个槽） | `Creeps ≈ GPM ≈ Deaths（少死） ≫ Towers ≈ Kills ≫ Madstones*` | 前三项均可。两个 Red 槽从前三项中留下 Quality/Trait 最好的两项，不值得为了微小顺序差距反复烧 roll。Towers 是高波动选择。 |
| Core Green | `Teamfight ≫ Roshan ≫ Stuns > First Blood > Courier` | Teamfight 是默认。高 Quality Roshan 可以作为上限路线；First Blood 是彩票。 |
| Mid Red | `Deaths ≈ GPM > Creeps > Kills ≫ Towers ≫ Madstones*` | 稳健偏 GPM/Deaths，上限偏 Deaths/Creeps/Kills。Towers 即使高 Quality 也通常不值。 |
| Mid Blue | `Runes ≫ Camps ≫ Wards` | Runes 是硬锁定项；不要为了高 Tier Camps 放弃普通 Tier Runes。 |
| Mid Green | `Teamfight ≫ Stuns ≈ Roshan > Courier ≈ First Blood` | Teamfight 是硬锁定项；其余只在无法得到 Teamfight 时考虑。 |
| Support Blue（两个槽） | `Wards（稳） ≈ Camps（上限） ≫ Runes` | 默认保留 Wards + Camps；二者谁拿更高 Quality 由现有旗决定。Watchers/Smokes/Lotuses 见 proxy 敏感性。 |
| Support Green | `Teamfight ≫ Stuns ≈ Courier ≫ First Blood ≫ Roshan` | Teamfight 是硬锁定项。上限路线中 Courier 会超过 Stuns，但仍明显落后 Teamfight。 |

`*` Madstones 以及下文的 Watchers、Smokes、Lotuses、Tormentor 都是 proxy，不进入默认可发布排序。

### Quality 与 Trait

总的操作顺序仍然是：

```text
先拿对 Stat → 再提升 Quality → 最后整理 Trait
```

但它不是“任何 Stat 差异都高于五个 Quality 档位”。当前数据给出三类情况：

1. **硬锁定 Stat**：Mid Blue 的 Runes、Mid Green 的 Teamfight、Support Green 的 Teamfight。它们的 Tier I 期望值仍高于主要替代项的 Tier V。
2. **Quality 决定胜负**：Core Red 的 Deaths/GPM/Creeps 非常接近；Support Blue 的 Wards/Camps 也接近。拿到其中的好 Stat 后，应把 roll 转向 Quality，而不是执着于第一名的名字。
3. **有条件赌博**：Core Green 的 Tier V Roshan 可以略胜 Tier I Teamfight；但从 Tier II Teamfight 开始，Teamfight 又明显领先。

Trait 的默认口诀：

- 已经有两个 Friendly 且有机会凑第三个时，第三个优先级很高；从零开始不盲追。
- Benevolent 通常放中间，Vampiric 通常放边缘，但必须以三个槽的基础贡献计算净值。
- Unique 最多保留一个。
- Fractal 只在全部 Quality 互不相同时生效；不要为了激活它牺牲多个高 Quality。

### Titles

- Suffix 默认选 **the Clutch**。当前均值阵容历史触发率约 `36.42%`，纸面期望增幅约 `5.83%`。
- the Lucky 约 `1.77%`，适合接受随机性的上限路线。
- the Underdog 约 `1.67%`；the Decisive 约 `1.53%`。社区指南把 Underdog 当稳健项，在当前候选阵容数据中它也略胜 Decisive，但仍明显落后 Clutch。
- the Cruel、the Tormented 和两个一血条件当前缺少可靠触发字段，不参与数据最优排序。
- Prefix 尚不能由本项目数据可靠排序：逐局样本没有 `hero_id`，客户端英雄外观分类映射也未补齐。Title 免费更换，因此不应仅因纸面 `+11%` 就追 Cerulean；补齐映射后再更新。

Clutch 的触发率来自目标选手历史 Series 赛制混合；若 TI 2026 Group 的实际 BO 结构不同，必须在锁阵前重算，`5.83%` 不是固定规则常数。

## 数据口径

Fantasy 不再使用旧的“2026 全年数据统一按 150 天衰减”口径。本次运行使用和团队强度一致的固定证据规则：

```text
比赛权重 = 版本权重 × 赛事级别权重 × 2^(-距 as_of 天数 / 60)
```

- 目标大版本 `7.41`：`1.00`
- 紧邻上一大版本 `7.40`：`0.15`
- 更早版本：`0`
- OpenDota premium：`1.00`；professional：`0.75`；其他：`0`
- 时间半衰期：60 天

战队强度继续使用方案 3 的目标队连通网络，共 3,859 局正权重职业 Game。Fantasy Stat 则按稳定 player ID 读取全部合格个人历史，不用连通网络误删选手效力旧队时的比赛：全局正权重目录为 4,388 局，其中 `7.41` 2,218 局、`7.40` 2,170 局；真正包含当前 80 名 Fantasy 目标选手的部分为 2,033 局、12,460 个选手单局样本，80 名选手全部有正权重记录。两部分共享版本、级别和时间公式，只是证据范围有意不同。

## 优先级是怎样计算的

### 1. 把原始统计换成客户端 Fantasy 分

每个 Game 中，每名选手的 Kills、Deaths、Creeps、GPM 等先按当前客户端规则换成 `client_fantasy_points`。例如：

```text
Kills 分 = 107 × kills
GPM 分 = 2 × GPM
Deaths 分 = max(0, 1950 - 195 × deaths)
Teamfight 分 = 2124 × min(1, (kills + assists) / team kills)
```

缺失值保持 `null`，不当成零；并且只接受与规则声明相符的 `exact` 或 `derived` provenance。

### 2. 对每名选手做加权均值和波动估计

一局越接近当前版本、赛事级别越高、时间越近，权重越大。每名选手每个 Stat 得到加权均值和加权标准差；小样本再用 `8` 个样本量的同 role 先验做收缩，避免一两局极端数据霸榜。

### 3. 按客户端 role 合并

- Core 和 Support：两名选手先分别计分，再取平均。
- Mid：使用一名中单。
- 当前第一版排名用 `单局均值 × 2.08` 近似“系列赛最好两局”的均值，用 `单局标准差 × √2` 近似波动，再用队伍强度给“能否获得可用高分 Series”做有限修正。

最后一条仍是简化代理，不是完整赛程 Monte Carlo；因此本文状态是 `warning`，不是最终排行榜概率预测。

### 4. 不用一个明星选手决定全局口诀

先用均值模型对 16 支 TI 队伍的每个 role 排序，再取前 25%，即四个可行候选组。优先级是这四组的平均结果：它不会被弱队稀释，也不会只为一个选手过拟合。

### 5. 同时给三种风险视角

对每个 `role × color × stat` 计算：

```text
稳健分 = max(0, mean - 0.85 × std)
均值分 = mean
上限分 = mean + 1.65 × std
```

它们只是透明的排序指标，不是经过校准的第 20/50/95 百分位。Stat 的真实分布不是正态分布，尤其 Roshan、First Blood、Towers 等离散事件的上限分只应解释为“更偏爱波动”，不能解释为命中概率。

## 完整数值排序

括号中的数字把同一行第一名标准化为 `100`。不同 role、颜色或风险行之间不能直接比较。

| Role / Color | 稳健：`mean - 0.85σ` | 均值 | 上限：`mean + 1.65σ` |
| --- | --- | --- | --- |
| Core Red | GPM 100 > Creeps 90 ≈ Deaths 89 ≫ Kills 45 > Towers 39 | Creeps 100 ≈ GPM 99 ≈ Deaths 96 ≫ Towers 56 ≈ Kills 55 | Creeps 100 > Deaths 93 > GPM 85 > Towers 72 > Kills 62 |
| Core Green | Teamfight 100 ≫ Roshan 22 > Stuns 13 > Courier 3 > First Blood 0 | Teamfight 100 ≫ Roshan 44 ≫ Stuns 21 > First Blood 17 > Courier 14 | Teamfight 100 > Roshan 77 ≫ First Blood 45 > Stuns 33 ≈ Courier 31 |
| Mid Red | GPM 100 ≈ Deaths 93 > Creeps 78 ≫ Kills 53 ≫ Towers 11 | Deaths 100 ≈ GPM 94 > Creeps 86 > Kills 65 ≫ Towers 29 | Deaths 100 > Creeps 88 > GPM 78 ≈ Kills 74 ≫ Towers 47 |
| Mid Blue | Runes 100 ≫ Camps 18 > Wards 12 | Runes 100 ≫ Camps 29 ≫ Wards 12 | Runes 100 ≫ Camps 39 ≫ Wards 13 |
| Mid Green | Teamfight 100 ≫ Stuns 15 ≫ 其他接近 0 | Teamfight 100 ≫ Stuns 27 ≈ Roshan 21 > Courier 13 ≈ First Blood 10 | Teamfight 100 ≫ Roshan 56 > Stuns 44 ≈ First Blood 40 > Courier 35 |
| Support Blue | Wards 100 > Camps 75 ≫ Runes 42 | Wards 100 ≈ Camps 89 ≫ Runes 47 | Camps 100 ≈ Wards 95 ≫ Runes 50 |
| Support Green | Teamfight 100 ≫ Stuns 22 > Courier 12 ≫ First Blood / Roshan 0 | Teamfight 100 ≫ Stuns 31 ≈ Courier 29 ≫ First Blood 13 ≫ Roshan 3 | Teamfight 100 ≫ Courier 54 > Stuns 43 ≈ First Blood 39 ≫ Roshan 14 |

## Stat 与 Quality 的换算阈值

Quality 总倍率分别是 Tier I `1.10`、Tier II `1.30`、Tier III `1.60`、Tier IV `2.00`、Tier V `2.50`，暂不计 Trait。把当前均值代入后：

| 比较 | 结果 | 操作含义 |
| --- | --- | --- |
| Mid Blue：Tier I Runes `3,343` vs Tier V Camps `2,204` | Runes 仍胜 | Runes 是硬锁定项。 |
| Mid Green：Tier I Teamfight `3,414` vs Tier V Stuns `2,069` | Teamfight 仍胜 | 不用为了 Tier V 次级 Stat 放弃 Teamfight。 |
| Support Green：Tier I Teamfight `3,117` vs Tier V Stuns `2,167` / Courier `2,028` | Teamfight 仍胜 | Teamfight 是硬锁定项。 |
| Core Green：Tier I Teamfight `3,041` vs Tier V Roshan `3,061` | Roshan 略胜 | 只有极高 Quality Roshan 才值得替代最低 Quality Teamfight；Tier II Teamfight 已升到 `3,593`。 |
| Mid Red：Tier I Deaths `2,979` vs Tier V Towers `1,947` | Deaths 仍胜 | 不因 Towers 是 Tier V 就保留。 |
| Core Red：Deaths/GPM/Creeps 均值相差不足约 4% | Quality 更重要 | 从三项中选两项，优先现有档位和 Trait。 |
| Support Blue：Wards/Camps 均值相差约 12% | Quality 可翻转 | 稳健偏 Wards，上限偏 Camps；通常正好保留两项。 |

这些比较只适用于当前四组候选的平均数据，并且未加入 Trait。真正点击时仍要把 Quality 和 Trait 对基础分的增减放在同一公式里比较。

## Proxy 敏感性：不能当零，也不能冒充精确

默认箭头排除了 proxy，但它们对实际制作仍有参考价值：

| Role / Color | 当前 proxy 条件均值 | 解释 |
| --- | --- | --- |
| Support Blue | Watchers `2,696`（覆盖 98.8%）；Smokes `2,005`（95.9%）；Lotuses `889`（80.9%） | 若后续客户端/回放验证字段映射，排序可能变成 Watchers > Wards > Smokes ≈ Camps > Runes > Lotuses。已有高 Tier Watchers/Smokes 不应自动销毁。 |
| Mid Blue | Watchers `927`（84.6%），略高于 Camps `881`；Runes 仍为 `3,039` | 即使 proxy 成立，也不动摇 Runes 第一。 |
| Core/Mid/Support Green | Tormentor 分别约 `2,119 / 2,091 / 1,840`，覆盖仅 `32.0% / 14.6% / 5.2%` | 条件样本看起来很高，但缺失机制足以严重抬高估计，只作为赌博候选。 |
| Core/Mid Red | Madstones 约 `473 / 320` | 即使把 proxy 当真，也远低于默认 Red 候选。 |

这里的“覆盖高”只表示当前代理字段经常能生成值，不等于该字段已经被证明与 Valve 结算定义完全一致。升级 provenance 前仍需黑盒差分或回放级核对。

## 有限 roll 的实际使用法

每次界面提供三个公共选项；使用一个选项只影响当前选中的 War Banner，同时刷新全部三个选项。因此不是分别优化三面旗，而是每一步比较 `3 个 Banner × 3 个 option` 的净提升。

客户端快照确认 Group 新发 40 枚 roll、Main 新发 30 枚，Group 的前三槽会带入 Main；但未用 token 是否结转尚无同等强度证据，所以不写成“无条件在 Group 用光”。颜色定向操作也不对称：Red 更容易定向处理 Quality，Blue 更容易定向处理 Trait，Green 更容易定向处理 Stat。这正是公共 Quality 操作优先检查 Support、Stat 操作优先修 Green 硬错误的原因。

建议按以下顺序处理：

1. **先修硬错误 Stat**：Mid Blue 没有 Runes、Mid/Support Green 没有 Teamfight 时，优先使用合适的 Stat 重随。
2. **接受足够好的集合**：Core Red 已有 Deaths/GPM/Creeps 中任意两种，Support Blue 已有 Wards+Camps，就停止为微小排序差距消耗大量 roll。
3. **再做 Quality**：优先使用 `Randomly increase one Quality` 与 `Randomly increase two Qualities and reduce one`。后者只有在两个高基础槽的期望增益大于被降低槽的损失时才点。
4. **Quality 操作优先检查 Support**：Blue 没有和 Red 相同的细粒度 Quality 定向操作，公共 Quality 增长对 Support 通常更稀缺。
5. **最后追 Trait 结构**：两 Friendly 追第三个；Benevolent 评估两个邻槽；Vampiric 评估自身 `+50%` 与邻槽 `-10%`；不为未激活的 Fractal/Friendly 预支分数。
6. **保留 proxy 好牌**：Tier IV/V Watchers、Smokes 或 Tormentor 不直接按默认箭头销毁，先放入 proxy 敏感性比较。
7. **每次只接受整旗净提升**：如果一个操作破坏高价值中槽或已激活 Trait，不能只看它给某个槽带来的绿色数字。

没有用户当前旗时，本项目不会虚构固定的“第 1 至第 40 次点击脚本”。用户提供三面旗与当下三个选项后，可以用同一分值表逐步计算下一次最优动作。

## 与社区指南的主要差异

- 社区指南 Core Red 把 Creeps 明显排第一；当前目标版本数据认为 Deaths/GPM/Creeps 属于同一档，Quality/Trait 比三者内部顺序更重要。
- 社区指南 Core Green 偏 Roshan；当前数据的均值和稳健路线都明显支持 Teamfight，只有 Roshan 的高 Quality/高波动路线能接近。
- 双方都强烈支持 Mid Runes、Mid/Support Teamfight，以及 Support Wards/Camps。
- 社区指南把 Smokes/Lotuses 直接纳入 Support 默认顺序；本项目因 provenance 尚为 proxy，将它们单列，但不会错误地当成零。
- 社区指南推荐 Clutch/Underdog 作为稳健 suffix；当前候选阵容数据仍选 Clutch，Underdog 略低于 Lucky、略高于 Decisive。

因此，社区指南的正确“策略内核”被保留：**Stat 先于 Quality，Quality 先于 Trait，并且区分稳定与赌博。** 被替换的是未经当前版本、当前参赛名单和可复现样本验证的固定箭头。

## 尚未完成的部分

- 尚未读取个人 War Banner、Quality、Trait、槽位和实时三个 roll options。
- 尚未用真实 TI 2026 Group 赛程逐 Game Monte Carlo 执行“最高两局求和、最佳 Series 结算”；当前是透明的 Series 代理。
- Prefix 缺少逐局 hero 与 Valve 英雄分类映射。
- proxy 字段尚未升级为 exact/derived。
- 稳健/上限分是排序启发式，没有用最终全体玩家分数分布校准 Top 95%、Top 1500 或 Top 100 的命中概率。

在这些缺口补齐前，这份文档适合作为制作决策表和候选池，不应被描述成确定的最终排行榜最优解。
