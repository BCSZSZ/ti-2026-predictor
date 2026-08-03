# Fantasy League 2026 Reddit 指南审计与策略基线

> 本文中的“当前项目选择”是研究当时旧 Fantasy 运行的对照快照。版本/级别/60 天加权后的当前阵容与数据优先级见 [`ti2026-fantasy-data-driven-guide-2026-08-02.md`](../reports/ti2026-fantasy-data-driven-guide-2026-08-02.md)；这里不回写历史比较，以保留研究审计链。

## 研究状态

- 研究对象：[Maroomm，Fantasy League 2026 Guide](https://www.reddit.com/r/DotA2/comments/1vble84/fantasy_league_2026_guide/)
- 检索时间：`2026-08-02T07:47:03Z`
- 项目规则基准：[`fantasy-client-rules-screenshots-2026-08-02.md`](../fantasy-client-rules-screenshots-2026-08-02.md)、[`ti2026.json`](../../config/rules/ti2026.json)
- 当前模型基准：[`ti2026-fantasy-group-recommendation-2026-08-02.md`](../reports/ti2026-fantasy-group-recommendation-2026-08-02.md)
- 结论性质：**高价值社区策略基线，不是 Valve 官方规则来源，也不是可以直接并入训练集的数据快照。**

作者称统计覆盖 13 个“Tier 1”赛事、1,601 场 `matches`，并在评论中说明时间范围是 2026 年初至发帖前。帖子没有列出赛事、match ID、抓取截止 UTC、代码、版本筛选或原始数据，因此这些数字只能作为作者自述。这里的“Tier 1”也不是本项目定义的 OpenDota `premium/professional` League tier；`matches` 究竟指 Game 还是 Series 同样没有明确。

## 总体判断

这篇指南在社区资料中质量很高，理由是：

- 作者连续多年制作同类指南，2026 帖子给出了完整选手表、统计项表、Prefix 频率和明确的风险偏好。
- 样本量不小，且作者公开回答了历史范围。
- 指南不是只抄客户端分值，而是把统计出现频率、选手差异和重随操作的不对称性纳入判断。
- 作者过去会公开修正错误；例如 [2025 Main 阶段指南](https://www.reddit.com/r/DotA2/comments/1nblgct) 说明曾修正 Madstone 字段和 Watcher 数据问题。这提高了透明度，也同时说明社区计算仍需要独立审计。

因此，更准确的定位是：**它是很强的专家基线和候选生成器，但不是规则权威，也不足以替代可复现模型。** Valve 当前客户端与规则快照仍具有更高优先级。

## 1. 指南的策略内核

### 1.1 决策顺序

指南把重随资源的优先顺序概括为：

1. 先获得适合该 role 的统计项；
2. 再提高 Quality；
3. 最后优化 Trait。

这个顺序是合理的。一个很高 Quality 的低产出统计项，仍可能输给普通 Quality 的高产出统计项。它与项目现有的“先估计基础贡献，再联合评价整面 War Banner”方向一致。

### 1.2 选手策略

作者按历史 `Average` 由高到低列选手组合，并建议不想深入计算的用户从靠前组合中选择。表中第一名分别是：

| Role | 指南 Average 第一名 | Average | Top |
| --- | --- | ---: | ---: |
| Core | Team Resilience：YSR-04E + niu | 1,620 | 2,751 |
| Mid | Team Liquid：Nisha | 798 | 2,524 |
| Support | LGD Gaming：Thiolicor + KJ | 1,505 | 5,047 |

这应理解为“历史表现候选”，不能直接当成 TI 2026 Group 的最终阵容。帖子没有显式加入 TI 赛程、对手、当前版本、Series 结算或阵容生效区间。

### 1.3 统计项优先级

以下是指南 TL;DR 的策略基线，不是本项目确认的永久排序：

| Role / 颜色 | 指南排序 |
| --- | --- |
| Core Red | Creeps ≫ GPM > Deaths（稳健）或 Towers（高风险）> Kills > Madstones |
| Core Green | Roshan > Teamfight > Tormentor ≫ Stuns ≫ Courier / First Blood |
| Mid Red | Creeps > GPM > Deaths（稳健）或 Kills（高风险）≫ Madstones > Towers |
| Mid Blue | Runes ≫ Camps / Lotuses ≫ 其他 |
| Mid Green | Teamfight > Stuns（稳健）或 Tormentor（高风险）≫ Roshan ≫ Courier / First Blood |
| Support Blue | Wards / Smokes > Lotuses / Camps ≫ Watchers ≫ Runes |
| Support Green | Teamfight > Tormentor > Courier ≫ First Blood / Roshan |

它的真正可迁移含义不是死记顺序，而是区分：

- 稳定、高频的统计；
- 低频但上限很高的统计；
- 因 role 和选手打法而明显不同的统计。

### 1.4 Trait 策略

指南给出的经验排序是：

```text
Friendly（成功激活时） > Vampiric > Benevolent >> Unique > Fractal
```

具体操作思想是：

- Friendly 只在已经有可成形结构时追求；两枚但无法凑到三枚会留下两个 `0%` Trait。
- Support 更适合追 Friendly，因为 Blue 有更细粒度的 Trait 重随操作。
- Mid 的三种颜色各一枚，也较容易定向处理。
- 不建议在 Core 上盲追 Friendly，因为两个 Red 的 Trait 常被一起重随，容易破坏已有好结果。
- Benevolent 通常放中槽以影响两个相邻槽。
- Vampiric 通常放边缘以只伤害一个相邻槽；若中槽基础贡献极高，也可以例外。
- Unique 可用但上限较低，并且不能保留两枚。
- Fractal 只有 Quality 全不同时激活，通常不值得为了它牺牲多个高 Quality。

这比“所有旗都追三枚 Tier V Friendly”的理论上限更可执行：理论最优不等于有限 token 下的最优策略。

### 1.5 Title 策略

指南把 Suffix 分成两类：

- 稳健：`the Clutch`、`the Underdog`；
- 赌博：`the Lucky`、`the Cruel`。

作者认为其他 Suffix 不值得选。这里应保留为启发式，而不是硬排除：帖子没有提供所有触发统计和置信区间，而且 Flayed/Patient 还存在客户端可见文案与内部字段冲突。

Prefix 不应全阵容固定抄一个名字。指南给每位选手列出各英雄类别的历史触发频率，正确的使用方式是把：

```text
选手条件触发率 × Prefix bonus × 该选手在阵容分数中的权重
```

在整套阵容上求和。

### 1.6 重随策略

指南最值得保留的在线操作建议是：

- `Randomly increase one Quality` 与 `Randomly increase two Qualities and reduce one` 是高价值选项；
- 这些选项优先考虑 Support，因为 Blue 缺少像 Red Quality 那样的定向单槽重随机会；
- 每次先选中正确的 War Banner，再点击操作，因为一次操作只影响当前旗并刷新三个公共选项；
- 40 枚 Group roll 与 30 枚 Main roll 是分阶段发放的，但“未用 token 是否一定不结转”没有从当前静态规则文件中得到同等强度证明，因此不把“无条件用光”写成项目硬规则。

本机客户端规则快照 [`fantasy_crafting.vdata`](../../data/raw/rules/20260802T071030Z-803d58a3f861/scripts/fantasy_crafting.vdata) 确认了操作结构：Red 有细粒度 Quality 操作、Blue 有细粒度 Trait 操作、Green 有细粒度 Stat 操作，并确认两种 Quality 增长操作存在。[`international_2026.eventdef`](../../data/raw/rules/20260802T071030Z-803d58a3f861/scripts/events/international_2026.eventdef) 确认 Group/Main 分别发放 40/30 枚 roll。

## 2. 证据审计

| 主张 | 判定 | 说明 |
| --- | --- | --- |
| Group/Main 为 3/5 槽，前三槽延续 | verified | 当前客户端 War Banner 定义确认。 |
| Core/Mid/Support 槽位颜色 | verified | 当前 `fantasy_crafting.vdata` 确认。 |
| Group/Main 发放 40/30 roll | verified | 当前 `international_2026.eventdef` 确认。 |
| Prefix + Suffix 免费更换并作用于全阵容 | verified | 客户端可见规则与内部定义一致。 |
| Red/Blue/Green 有不同的定向重随操作 | verified | 当前客户端 operation IDs 25–33 确认。 |
| Stat > Quality > Trait | community heuristic | 方向合理，但实际应比较整旗净增量。 |
| 玩家、统计项和 Prefix 排名 | community empirical | 无 match ID、代码、快照或稳定 ID，不能复现。 |
| Clutch/Underdog 稳健 | community empirical，且与项目结果一致 | 当前项目也把 Clutch 排第一。 |
| Lucky/Cruel 适合赌博 | community heuristic | Lucky 可估计；Cruel 当前字段不可用。 |
| Friendly 优先在 Support/Mid 追 | inferred from verified operations | 操作不对称已验证，最优性仍取决于当前旗。 |
| Core Green 固定 Roshan 第一 | unsupported as a universal rule | 与帖子自身多数表格的直观量级不一致。 |

## 3. 指南内部的两个重要问题

### 3.1 双人 role 表疑似使用求和尺度

Core 和 Support 的 `Average/Top` 大致是 Mid 的两倍；例如 Support 第一名 `Top=5,047`，几乎正好是 Mid 第一名 `2,524` 的两倍。结合表格结构，双人 role 很可能直接把两名选手相加。

客户端规则则要求先计算每名选手，再对同一 role 的选手取平均。若该推断正确：

- 同一 role 内所有队伍都乘同一常数，排序通常不受影响；
- 表格绝对值不能当客户端最终分；
- Core/Support 与 Mid 不能直接横向比较；
- 不能把三行 `Average` 直接相加估计阵容分。

帖子没有公布代码，因此这里只能标记为强推断，不能断言作者实际实现。

### 3.2 TL;DR 与表格并非机械一致

例如：

- TL;DR 把 Core Green 的 Roshan 排在 Teamfight 前，但表中多数 Core 组合的 Teamfight 数值明显更高。
- 部分 Support 的 Watchers/Stacks 表值很高，TL;DR 却把 Watchers 排到 Wards、Smokes、Lotuses、Camps 后面。

可能解释包括：作者混合了均值、最高局、稳定性、数据质量和主观风险修正。但帖子没有给出从表格到 TL;DR 的明确算法，因此 **TL;DR 适合人工参考，不适合直接编码成不可变排序。**

## 4. 与当前项目方案的对照

指南自己的 Average 表中，我们当前阵容的位置约为：

| Role | 当前项目选择 | 指南名次 | 当前模型名次 |
| --- | --- | ---: | ---: |
| Core | Team Yandex：watson + DM | 4 | 1 |
| Mid | BoomBoys：gpk | 3 | 1 |
| Support | Team Yandex：Saksa + Maladych | 2 | 1 |

因此，两套方法并没有出现“社区指南认为我们的选手很差”的冲突。当前三组全部属于指南靠前候选，只是指南的单纯年度 Average 与项目的时间、可用字段和 Series 代理排序不同。

若强行把指南三项 Average 第一名放进当前模型，并让当前模型为它们选择各自最佳可用统计，当前模型目标约为 `23,364.36`；现有阵容为 `25,306.46`，前者低约 `7.67%`。这只说明在**当前项目模型**里不应直接换成指南第一名，不是对指南历史表的回测。

统计项的主要差异是：

- Core：双方都认可 Creeps/Deaths/GPM 和 Teamfight；指南更偏向 Roshan 上限，项目更偏向 Teamfight 的稳定贡献。
- Mid：双方都选 Runes + Teamfight；Red 上指南偏 Creeps/GPM，当前上尾 profile 选择 Deaths。
- Support：双方都认可 Teamfight 与 Wards/Camps；指南还把 Smokes/Lotuses 列为强项，而项目因其当前数据为低覆盖 proxy，没有把它们放入默认可发布搜索。

## 5. 用指南补齐当前阵容的 Prefix 先验

指南为当前五名选手列出了 Prefix 类别触发频率。这里把 `Malady` 与当前名单的 `Maladych` 视为同一显示身份，但指南没有稳定 account ID，因此该连接只是一项人工身份假设，不写入规范化数据。

用当前模型三项 role 基础分：

- Core `8,720.8191`，watson/DM 各取一半；
- Mid `9,064.3116`，全部给 gpk；
- Support `7,521.3336`，Saksa/Maladych 各取一半；

再采用“英雄类别与该选手当局基础分独立”的简化假设，得到：

| Prefix | 加权触发率 | 近似阵容增幅 |
| --- | ---: | ---: |
| Elemental | 27.389% | **2.191%** |
| Cerulean | 18.467% | 2.031% |
| Otherworldly | 26.898% | 1.883% |
| Crimson | 30.548% | 1.833% |
| Golden | 20.940% | 1.675% |
| Royal | 14.923% | 1.492% |
| Heroic | 16.194% | 1.457% |
| Emerald | 13.995% | 0.840% |

这不是作者原结论，而是本项目基于作者频率做的派生近似。它忽略了“某类英雄是否也会让该选手拿到更高 Fantasy 基础分”的相关性，且第一、第二只差 `0.16` 个百分点。

可执行结论是：**若现在必须选择 Prefix，可把 Elemental 作为社区先验第一名，Cerulean 第二，Otherworldly 第三。** 由于 Title 免费更换，可以暂用 Elemental；但在补齐逐局 hero ID、Valve 英雄类别映射和条件得分后必须重新计算。该结果不进入官方规则配置。

## 6. 落盘策略：`community-maroomm-2026-v1`

这套策略作为未来回测的独立外部基线保存，不替代当前模型：

### 阵容

- 候选只从指南各 role Average 靠前组合中产生。
- 默认仍使用当前模型阵容：Yandex Core / BoomBoys Mid / Yandex Support，因为它们在指南中同样靠前，并在当前模型中均为第一。
- 指南第一名（Resilience Core / Nisha / LGD Support）保留为敏感性候选，不直接覆盖当前选择。

### Emblem

- 先避免低价值 Stat，再提高 Quality，最后处理 Trait。
- Core 目标：Creeps、Deaths/GPM、Teamfight；高 Quality Roshan 可作为上尾候选，不因固定口诀无条件重随。
- Mid 目标：Runes、Teamfight、Creeps/GPM/Deaths 中与当前选手最匹配者。
- Support 目标：Teamfight，以及 Wards/Smokes/Camps/Lotuses 中数据或当前 Quality 最好的两项。
- 项目无法可靠观测的 Smokes/Lotuses 只作为保留现有好徽标的社区先验，不能伪装成精确模型输入。

### Trait 与重随

- Support、Mid 已有两个 Friendly 时优先追第三个。
- Core 不主动从零追三 Friendly，除非当前公共选项能在低损失下直接成形。
- Benevolent 优先中槽，Vampiric 优先边槽，但每次以整旗净增量为准。
- Quality 增长选项优先比较 Support；`increase two/decrease one` 必须确认被降低槽的损失小于另外两槽收益。
- 不根据 Trait 名字逐槽贪心；每次比较三个 Banner × 三个公共选项。

### Title

- Prefix：`Elemental`（社区先验，低到中置信）；`Cerulean` 为接近的备选。
- Suffix：`the Clutch`（当前模型与指南共同首选）。
- 稳健备选：`the Underdog`。
- 只有明确追求高方差时才用 `the Lucky`；`the Cruel` 因缺少可靠触发字段暂不作为项目默认。

### 发布门槛

该策略当前状态为 `community_baseline`，不是 `publishable`。要升级为可发布策略，至少需要：

1. 作者数据或我们自己的可复现 match ID 清单与 UTC `as_of`；
2. 稳定 player ID 映射；
3. 目标版本与时间权重；
4. Prefix 英雄分类与逐局 hero ID；
5. 用户当前三面 War Banner、剩余 token 和三个实时重随选项；
6. 按客户端 Series 聚合规则完成同快照模拟。

## 7. 最终采用与不采用的部分

立即采用：

- Stat > Quality > Trait 的资源顺序；
- 根据颜色的定向操作差异分配 token；
- Friendly 主要在 Support/Mid 有条件追求；
- Clutch 稳健首选；
- Prefix 必须按所选阵容估计，当前临时选 Elemental。

作为候选保留：

- 指南的选手榜和各 role 统计项优先级；
- Smokes/Lotuses、Roshan 等高上限统计；
- Underdog/Lucky 的不同风险 profile。

不直接采用：

- 把 1,601 个未公开 match 直接视为可复现数据集；
- 把“Tier 1”映射成本项目 League tier；
- 把双人表绝对分直接用于客户端总分；
- 把 TL;DR 固化为无条件排序；
- 因社区指南而改写 Valve 规则配置或绕过 `as_of`、版本、provenance 和稳定 ID 约束。
