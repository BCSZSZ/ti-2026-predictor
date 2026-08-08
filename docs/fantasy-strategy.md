# TI 2026 Fantasy 策略草案

## 文档状态

- 目的：把第三方作业截图中的可迁移思路，整理成能够由本项目计算、模拟和审计的 Fantasy 策略。
- 规则基准：[`fantasy-client-rules-screenshots-2026-08-02.md`](fantasy-client-rules-screenshots-2026-08-02.md) 与 `config/rules/ti2026.json`。
- 证据边界：本次四张图是第三方策略参考，来源日期、客户端 build、数据样本和回测方法未知；它们不是 Valve 规则证据，也不能证明图中的固定选手或统计优先级适用于 TI 2026。
- 当前阶段：策略内核已经形成；最终选手、徽标和称号推荐仍需使用显式 UTC `as_of`、TI 2026 赛程、当时可用数据以及用户实际战旗状态计算。
- 当前 Group 数据驱动优先级与制作指南见 [`reports/ti2026-fantasy-data-driven-guide-2026-08-02.md`](reports/ti2026-fantasy-data-driven-guide-2026-08-02.md)。旧的固定阵容报告保留为历史运行记录，不再代表当前版本加权结论。
- Maroomm 的 Reddit 2026 指南已作为独立社区基线审计，见 [`research/fantasy-league-2026-reddit-guide-audit.md`](research/fantasy-league-2026-reddit-guide-audit.md)；它不覆盖客户端规则或当前项目默认模型。
- P4 已把 Group 40 Roll 单独落实为两版人工手册和七张 Stat 表，见
  [`playbooks/group-roll/README.md`](playbooks/group-roll/README.md)。两版 v1 均为 `draft`；本文
  后续的旧口诀不能覆盖 P4 的精确分档、条件 Trait 配方或发布门槛。
- P5 限枝 solver 已完成失败门禁审查，见
  [`reports/p5-branch-capped-solver-2026-08-06.md`](reports/p5-branch-capped-solver-2026-08-06.md)。
  它保留为实验性反例/本地 advisor 内核，不能覆盖人工手册，也不能称为可靠或全局最优。
- P6 只读交叉审计见
  [`reports/p6-read-only-playbook-cross-audit-2026-08-06.md`](reports/p6-read-only-playbook-cross-audit-2026-08-06.md)。
  它的留出索引与 P4/P5 都不交，但只完成 9/108 行，因此只能披露两个 5% 严格警告，
  不能补完手册或升级两个 `draft` 标签。
- P7 本地交互顾问见
  [`reports/p7-local-interactive-group-roll-advisor-2026-08-06.md`](reports/p7-local-interactive-group-roll-advisor-2026-08-06.md)。
  它只跟踪人工确认的 Group 状态；默认一步层不含未来 offer 价值，P5 长视野交互被性能门禁
  阻断，不能反向改写本页或两份人工手册。

## 1. 参考作业做了什么

参考作者采用了三层决策。

### 1.1 按 Fantasy role 选择队伍与选手组

- Core 示例选择 `Xxs + Ame`。
- Mid 示例选择 `Malr1ne`。
- Support 示例选择 `Sneyking + Cr1t-`。

这说明作者不是只挑一个明星选手，而是按客户端的 role 结算单位选择：Core 和 Support 分别要考虑两名选手的平均分，Mid 考虑一名选手。

### 1.2 为不同 role 排统计项

截图给出的经验排序包括：

- Core Red：正反补 > 击杀 > GPM > 死亡 > 防御塔最后一击 > 魔石。
- Core Green：魔方 > 团战参与 > 眩晕 > Roshan > 第一滴血 > 信使。
- Support Blue：诡计之雾约等于假眼 > 瞭望台 > 莲花 > 神符 > 堆野。
- Support Green：魔方 > 眩晕 > 团战参与 > 信使 > 第一滴血约等于 Roshan。
- Mid 示例实际采用正反补、神符和眩晕。

这些排序的真正含义应当是“基础计分系数 × 该 role/选手产生该统计的数量”，而不是只比较客户端给出的单次分值。它们是作者当时数据的结论，不是永久规则。

### 1.3 联合安排 quality、trait 与槽位

作者的口诀可以整理为：

- Benevolent（仁爱）通常放在中间，让它同时强化两个相邻槽。
- Vampiric（吸血）通常放在边缘，只削弱一个相邻槽。
- 已经有两个 Friendly（友好）时，第三个具有很高的阈值价值，因为它会同时激活至少三个 Friendly。
- Unique（唯一）通常只保留一个；第二个会破坏“唯一”条件。
- Fractal（分形）只有在全旗 quality 互不相同时才有价值，不能脱离 quality 组合单独评价。

这部分是参考作业最值得保留的策略内核：**评价整面 War Banner 的总分，而不是逐个徽标贪心。**

## 2. 截图中的 `Vampiric - Benevolent - Vampiric`

令三个槽未计算 quality/trait 前的预期基础分为 `B1、B2、B3`。截图中的布局是：

```text
Vampiric | Benevolent | Vampiric
```

按当前项目采用的 Emblem 内加法规则：

- 左槽：自身 Vampiric `+50%`，再吃到中间 Benevolent `+20%`，净 trait 效果 `+70%`；
- 中槽：被左右两个 Vampiric 各削弱 `-10%`，净 trait 效果 `-20%`；
- 右槽：同左槽，净 trait 效果 `+70%`。

所以 trait 带来的增量为：

```text
0.70 × B1 - 0.20 × B2 + 0.70 × B3
```

这正好解释了 Mid 截图里的三个界面总倍率：

- Tier V + `+70%` 净 trait = `100% + 150% + 70% = 320%`；
- Tier III + `-20%` 净 trait = `100% + 60% - 20% = 140%`；
- Tier V + `+70%` 净 trait = `320%`。

但“仁爱永远放中间、吸血永远放两边”只能作为启发式，不是数学定律。如果中间统计项远高于两边，把 Vampiric 放中间、两个 Benevolent 放两边可能更好。最优位置必须代入各槽真实的 `B` 值比较。

## 3. 我们采用的策略内核

### 3.1 目标函数

在不知道完整 percentile 换算函数时，每个 Period 的主目标是最大化该 Period 的原始 Fantasy score。原始分越高，percentile 不会变差，因此这与争取最终排行榜和 Tyrian Regalias 奖励方向一致。

稳健默认目标为：

```text
Group：maximize E[Group raw score]
Main： maximize E[Main raw score]
```

不能直接把两个 raw score 相加，因为 Main 有五个槽、Group 只有三个槽，两个原始分的尺度可能不同。Group 前三槽会带入 Main，所以遇到“当前 Group 得分”和“Main 延续价值”冲突时，应保留两者的 Pareto 候选；若业务上必须给出唯一选择，再使用两个 Period 等权的**归一化**分数作为显式项目 policy，并做权重敏感性分析。

若以后能估计排行榜阈值，可以再提供“前 95%、前 1500、前 100”目标，直接最大化超过相应阈值的概率；在阈值未知时不伪造该优化。

### 3.2 统计项按贡献值估价

对每个 `team × role × stat`，计算该统计在一局中的预测分布，而不是套用固定口诀：

```text
base contribution = 客户端计分公式(raw stat)
```

估计至少要考虑：

- 当前大版本与时间衰减；
- 稳定 player ID 和当时 roster interval；
- 选手在该 role 下的历史均值、波动和样本量；
- 对手、比赛时长和比赛胜负对统计的影响；
- `exact / derived / proxy / unavailable` 数据 provenance。

默认可发布推荐只使用覆盖充分的 `exact` 或 `derived` 项。高分但无法可靠观测的 proxy 项只进入敏感性分析，不能偷偷当成零或精确值。

### 3.3 按真实结算流程模拟赛程

不能用“平均每局分 × 预计总局数”代替客户端结算。每次模拟必须按以下顺序：

1. 分别计算 role 内每名选手的单局分；
2. Core/Support 对两名选手取平均，Mid 使用单名选手；
3. 同一 Series 取最高两个 Game 求和；
4. 同一 Period 有多个 Series 时，只取该 role 的最高 Series；
5. 三个 role 的 Period 分相加形成阵容原始分。

因此，更多 Series 的主要价值是增加“抽到一个高分 Series”的机会，而不是把全部 Series 线性累加。BO3 的第三局也主要提供替换低分局的选择权。

### 3.4 队伍、统计项与整面战旗联合优化

对每个 role，不应先锁死队伍再独立挑每个槽。应联合搜索：

```text
队伍/选手组
× 每槽 stat（同旗不得重复）
× 每槽 quality
× 每槽 trait
× trait 的槽位顺序
× 全阵容 Coach prefix/suffix
```

候选组合使用完整赛程模拟评分。这样可以自动处理：

- 高 quality 应优先放在高 `B` 的统计项上；
- Benevolent 要强化哪两个相邻值；
- Vampiric 的自增能否覆盖对邻槽的损失；
- Friendly 的三枚激活阈值；
- Unique 只留一枚时应给哪个高价值槽；
- Fractal 的 `+60%` 是否足以补偿为了 quality 全不同而放弃的高档 quality。

特别是在 Main 的五槽战旗上，Fractal 条件意味着五个 quality 必须全部不同，也就是必须同时包含 Tier I 到 Tier V。它不应仅因“已激活”就被认为最优。

### 3.5 Coach title 按“加成 × 触发概率”选择

Coach title 免费更换，因此不应固定追逐显示百分比最大的称号。对每个候选 prefix/suffix，应在模拟 Game 中计算：

```text
expected title gain
  = 触发时所覆盖的该局基础分 × title bonus × 触发概率
```

同一个 title 作用于整个 Fantasy 阵容，故必须用所选三个 role 的英雄/比赛联合分布评价。条件触发频繁的小加成可能胜过几乎不触发的大加成。

当前独立证据层已经补齐客户端 128 名英雄的 Prefix 分类，并用完整 Series 历史计算逐图纸面值。
未知最终三面战旗时的默认是 **Cerulean + the Clutch**；Cerulean 仍会随最终队伍/位置改变，两个
一血 Suffix 因客户端内部条件和可见文案冲突而排除。这个人工默认没有升级为完整阵容联合最优，
详见 [TI 2026 Title 分析](reports/ti2026-fantasy-title-recommendation-2026-08-08.md)。

### 3.6 重随是一项在线决策

客户端同一时刻给出三个全战旗共享的选项；实际动作是选择：

```text
(当前 War Banner, 三个可用选项之一)
```

使用后会消耗一个 token 并刷新全部选项，所以每次选择都应比较：

- 对当前旗最终期望分的即时增量；
- 是否破坏 Friendly、Unique、Fractal 或有利相邻结构；
- 对另外两面旗放弃当前选项的机会成本；
- Group 前三槽会带入 Main 所产生的延续价值；
- 剩余 token 和未来出现更好选项的价值。

完整方法是有限期动态规划或 Monte Carlo rollout。若抽取概率尚未验证，则采用保守的在线规则：每次对所有 `banner × option` 计算可确认的净增量，只接受最大正增量；阈值和未来价值必须标为项目策略参数，不冒充 Valve 规则。

## 4. 可立即使用的人工口诀

在精确优化器完成前，可以采用以下经过修正的版本：

1. 先看该选手/role 的预期基础分，再看徽标名字；不要只看单次计分系数。
2. 高 quality 给高基础分统计；低基础分槽即使 Tier V 也可能不如高基础分槽的 Tier III。
3. 只有一个 Unique，并优先给高基础分槽。
4. 已有两个 Friendly 时，第三个价值很高；不足三个时不能把未激活的 `+50%` 算进去。
5. Fractal 只在所有 quality 不同时计分；Main 五槽尤其要核算为此牺牲的 quality。
6. Benevolent 优先放能同时邻接两个高基础分槽的位置。
7. Vampiric 优先放边缘或高基础分槽旁的低损失位置，但每次都计算净值。
8. 选队时看模拟后的“最佳 Series”分布，而不是简单追求比赛最多或队伍最强。
9. Coach 选触发后的期望增量，不选纸面百分比最大者。
10. 每次重随比较整面旗和三面旗的净提升；不要为凑一种漂亮组合破坏已经更高的总分。

## 5. 对当前实现的要求

现有 `FantasyRecommender` 可以作为第一版统计排序基线，但还不是上述最佳策略，因为它目前：

- 已阻止同旗重复统计，但仍是按槽贪心，尚未把当前 Quality/Trait 与全部槽位做联合搜索；
- 尚未把用户实际 quality、trait、相邻顺序和可用重随选项纳入推荐；
- 用简化的 Series 倍率与队伍强度可用性系数代替真实赛程 Monte Carlo；
- 尚未联合优化三个 role 与全局 Coach title；
- 对上尾目标使用简单 `mean + λ × std` 代理，尚未直接模拟排行榜阈值。

后续实现应保留当前版本作为基线，并至少比较：

1. 固定统计优先级的参考作业策略；
2. 只最大化均值的逐槽策略；
3. 遵守聚合规则的赛程模拟策略；
4. 队伍、stat、quality、trait、位置与 Coach 的联合优化策略；
5. 加入在线重随决策后的完整策略。

所有比较必须固定 `as_of`、规则版本、数据快照与随机种子，并报告期望原始分、分布区间、缺失覆盖和相对基线增益。

## 6. 参考截图指纹

原图是 Codex 会话临时附件，不提交 Git。这里只记录指纹，以便证明日后讨论的是同一组参考作业。

| ID | 文件 | 尺寸 | 内容 | SHA-256 |
| --- | --- | ---: | --- | --- |
| H1 | `codex-clipboard-125a8f8a-1426-404a-85e0-e1bfe40366f8.png` | 2196×1111 | Core 示例、Red/Green 经验排序 | `aafd8080b6d72fc4eed5f970c44f3daab931fa71f8214650da292eebe36350db` |
| H2 | `codex-clipboard-4550c664-a1ef-49dc-9f7c-166bd4be86bc.png` | 892×1183 | Mid 示例与 `Vampiric-Benevolent-Vampiric` | `3aa9ac563179ed45c109d7a43a9bdd4825e2c94903f7b7157c0e3db4f8d38d45` |
| H3 | `codex-clipboard-8cc8441d-229c-469c-973e-06a881c0d5ea.png` | 2287×1166 | Support 示例、Blue/Green 经验排序 | `5a6c450f99d9438a172b776d5a88ed7931b1fe76deb372bf32b3a6631a93ad63` |
| H4 | `codex-clipboard-178964bc-61ca-402f-96d4-45475c4b8dfe.png` | 2376×1261 | Trait 规则复述与人工口诀 | `20d046ecef6ce50df5047f5827fad0d4fdc4d8b3ab4fa36afbd51795cc419b58` |
