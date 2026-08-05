# TI 2026 Group Fantasy 当前最佳可用结论

> **历史运行，已被替代。** 本文使用旧的 Fantasy 时间口径；当前版本/级别/60 天权重运行及按颜色优先级请见 [`ti2026-fantasy-data-driven-guide-2026-08-02.md`](ti2026-fantasy-data-driven-guide-2026-08-02.md)。保留本文仅用于审计，不应继续把其中的 BoomBoys Mid 固定阵容当作当前均值结论。
>
> **来源更新（2026-08-06）：** 本运行也早于五项 replay 原生计数的确认与回填；其
> Madstone、Smoke、Watcher、Lotus、Tormentor 相关排除或 proxy 结论只代表当时数据状态。
> 见 [`ti2026-fantasy-proxy-stat-validation.md`](../research/ti2026-fantasy-proxy-stat-validation.md)。

## 运行口径

- `as_of`：`2026-08-02T07:11:53Z`
- Period：Group，三槽 War Banner
- 运行 ID：`fantasy-0e4c5bd5a445d209`
- 运行状态：`warning`，不是 `blocked`
- 规则版本：`client-visible-2026-08-02+owner-policy-v3`
- 规则 SHA-256：`406ace33728b2fa36572c575d67f6d742d236ec9dce448f9c222949da9497c9e`
- 规则快照：`20260802T071030Z-803d58a3f861`，客户端 build `6882:10875429`
- 数据 SHA-256：`571c44c6e302994c1ae34d17c9747d0517d3650af656e0efed52430a92b5391e`
- Fantasy 历史范围：2026 UTC 年、`premium/professional`、80 名目标选手、2,055 局完整比赛详情、12,486 个目标选手-单局样本。
- 本次数据重规范化：94 次请求尝试，其中 14 场新详情、2,041 场复用本地不可变原始响应；0 失败、0 待补。运行没有使用 keyed premium 请求计数。

本文中的“最佳”表示在现有可验证字段、当前模型和未读取用户个人战旗的前提下，最高的模型目标值；不是 Valve 官方答案，也不是对未知徽标库存的全局最优证明。

## 推荐结论

三个策略 profile 对队伍选择完全一致，说明队伍结论对“均值还是上尾”的选择较稳健：

| Role | 推荐队伍 | 选手 | Group 三槽目标（按槽位颜色顺序） |
| --- | --- | --- | --- |
| Core | Team Yandex | watson + DM | 正补与反补（Red）／团战参与（Green）／死亡（Red） |
| Mid | BoomBoys | gpk | 死亡（Red）／神符拾取（Blue）／团战参与（Green） |
| Support | Team Yandex | Saksa + Maladych | 堆叠野怪营地（Blue）／团战参与（Green）／假眼放置（Blue） |

这里采用上尾 profile 的槽位版本，因为项目最终目标是排行榜高位；相对于均值 profile，它几乎不牺牲模型期望：

- Core 的均值版本会把“正补与反补”换成 GPM；两者在 Team Yandex 上非常接近。
- Mid 和 Support 的统计集合在三个 profile 中不变，只出现同色槽位次序变化。
- 团战参与在三面旗上都是首选。它在数据重规范化后按负责人公式标为 `derived`，2026 样本覆盖率为 `99.951%`，不再被旧的错误 provenance 排除。

作为量级参照，均值 profile 在尚未加入用户实际 quality、trait 和 Title 前的内部比较值为 `25,306.46`。这个数字使用当前简化 Series/可用性估计，只用于候选间比较，不能当成客户端最终结算分。

## Title 结论

### Suffix

当前可计算的默认首选是 **the Clutch（+16%）**。

对推荐的五名选手，历史混合赛制估计为：

| Suffix | 历史触发率 | 纸面期望加成 |
| --- | ---: | ---: |
| the Clutch | 33.42% | 5.35% |
| the Lucky | 11.44% | 2.40% |
| the Underdog | 36.14% | 2.17% |
| the Decisive | 5.00% | 1.20% |

混合赛制会因 BO1/BO2 高估 Clutch。只保留这些选手的历史 BO3 后，敏感性结果为：

| Suffix | BO3 触发率 | 纸面期望加成 |
| --- | ---: | ---: |
| the Clutch | 16.22% | **2.59%** |
| the Lucky | 11.89% | 2.50% |
| the Underdog | 37.03% | 2.22% |
| the Decisive | 3.24% | 0.78% |

因此 Clutch 仍是第一，但只比 Lucky 高约 `0.10` 个百分点，优势很小。若 Valve 后续公布的 Group Series 结构或实际赛程改变，Lucky 是最稳妥的替代项。

以下 suffix 暂不参与最优排序：

- the Tormented、the Cruel：当前规范化样本没有可靠的逐局触发字段。
- the Flayed Twins Acolyte、the Patient：除缺少逐局一血时间外，可见文案还分别与内部“一分钟前”和“六分钟后”字段冲突。

截图黄色高亮的 the Flayed Twins Acolyte 只是当前选择，不是可证明的最优选择。按现有证据，应改为 the Clutch。

### Prefix

现在还不能诚实宣布某个 prefix 最优。OpenDota 样本尚未保存逐局 `hero_id`，而 Valve 的红/蓝/绿/紫、Elemental、Otherworldly、Heroic 英雄分类映射也没有出现在可读规则表中。仅按 `+11%` 最大就选择 Cerulean 会把触发概率假定为相同，这是没有证据的。

因此当前操作建议是：**暂时保留截图中的 Otherworldly，不把它标记为最优；在补齐英雄分类映射后免费更换。** 这不会消耗 roll token。

## Quality 与 Trait 的理想目标

对三面推荐战旗穷举所有三槽 `quality × trait` 组合后，如果假设任何结果都可自由取得，三面旗的理论最大值都是：

```text
Tier V Friendly | Tier V Friendly | Tier V Friendly
```

原因是三枚 Friendly 同时激活，每槽均得到 `+150% quality + 50% trait`，总倍率均为 `3.00`。这只是理论目标；Tier V 很稀有，实际重随不能不计 token 成本追求它。

实际操作优先级：

1. 已有两个 Friendly 时，第三个是最高优先级的结构性升级。
2. Support 的中槽团战参与基础值明显最高，应优先保护其 quality 和正面 trait。
3. Mid 的团战参与与神符接近，均高于死亡；Core 三项很接近。
4. 未达到三枚 Friendly 时，不能提前把 `+50%` 算进当前分数；应对眼前的三个 roll option 做整旗净增量计算。

## 为什么仍是 warning

- 尚未读取用户当前三面 War Banner、剩余 token 和三个实时重随选项，因此只能给目标配置，不能给逐次点击答案。
- Prefix 缺少英雄分类触发率。
- 部分高分统计仍是 proxy，默认推荐已排除它们。
- 团队强度模型的滚动校准对部分新队没有正权重证据，但本次选中的 Team Yandex 与 BoomBoys 拥有充足 Fantasy 选手样本；该问题仍降低整体赛事/晋级建模置信度。
- 当前 Fantasy 推荐器仍使用简化的 Series 倍率与队伍可用性估计，完整赛程 Monte Carlo 和真实战旗联合优化尚未实现。

因此，可以把本文队伍、统计项和 Clutch 当作当前最佳可用起点；要形成可直接照着点击的最终答案，还需要用户当前三面战旗与三个 roll options 的截图。
