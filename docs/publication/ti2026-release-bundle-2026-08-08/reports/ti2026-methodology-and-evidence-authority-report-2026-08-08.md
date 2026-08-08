# TI 2026 梦幻挑战与赛事预测：方法与证据权威性报告

状态：**正式方法报告；可追溯、可复算，但不是 Valve 背书，也不代表预测必然正确**

- 报告版本：`2026-08-08`
- Fantasy 数据截止：`2026-08-06T17:27:00Z`
- Title 独立分析截止：`2026-08-08T13:12:00Z`
- 赛事 Forecast 数据截止：`2026-08-08T04:11:08Z`
- 赛事档位与奖金资料截止：`2026-08-08T06:05:53Z`
- 当前规则版本：`2026-08-06-group-roll-v4`
- 正式队伍强度策略：`team-strength-adr-0002-v2`

## 先说结论

这套工程最有权威性的部分，不是“模型很聪明”，而是四件事：

1. **规则先从当前 Dota 客户端取证。** 规则文件、客户端 build、抓取时间和 SHA-256 都已冻结；
2. **每个输入都有时间边界和来源身份。** 晚于显式 UTC `as_of` 的比赛、阵容和规则不会进入运行；
3. **观测、派生和预测严格分层。** `exact`、`derived`、模型估计和草案结论不会混写；
4. **结论经过冻结回测或重采样。** 同一快照、配置和随机种子可以复算同一推荐 JSON。

因此，可以把本报告当作项目当前的**正式方法说明和证据总账**。但不能把它理解为：

- Valve 官方认可了我们的公式或推荐；
- Fantasy 队伍 Top 3 一定会按表中顺序发生；
- 赛事模型给出的 58% 就是经过校准的真实概率；
- 小组赛 16 个填写槽位是对 2026 瑞士轮的逐场精确复刻；
- 仍为草案的 Roll 全局策略已经证明最优。

当前总体判断如下。

| 部分 | 当前证据强度 | 可以怎样使用 | 不能怎样声称 |
| --- | --- | --- | --- |
| Fantasy 客户端规则、颜色、品质、特性和 Roll 操作 | 很高 | 当作当前客户端规则快照 | 不声称服务器隐藏随机率已经完全公开 |
| Fantasy 18 项历史统计 | 高 | 正式计算只用 16 项 `exact` 和 2 项 `derived` | 不把派生项说成 Valve 原生计数，不使用 proxy 冒充 exact |
| Stat 队伍 Top 3、均值与 CVaR10 | 中高 | 比较当前证据下的期望和低迷情景 | 不当作确定排名或已校准概率 |
| Quality / Trait 组合算术 | 高（给定规则快照） | 比较同一底层 Stat 下的组合倍率 | 不代表未来 Stat 表现本身确定 |
| Group Roll 玩家规则 | 分层 | 使用已通过审计的保守规则 | 两本完整 v2 候选仍是 `draft`，不能称全局最优 |
| Fantasy Title | Prefix 中低、Suffix 中等 | 未知最终战旗时用 `Cerulean + the Clutch` 作默认 | 不称为完整 P3 联合最优；Prefix 需随最终阵容复查 |
| 队伍综合实力和中立单局关系 | 中等 | 做实力带、相对排序和对局倾向判断 | 不当作 BO3 胜率，也不承诺高准确率 |
| 小组赛 16 槽联合填写 | 中等偏低 | 在已知容量下做一致性更好的组合选择 | 不是精确瑞士轮模拟，前 10%/前 100 目标仍是代理 |

## “权威”在本报告中的精确定义

本报告的“权威性”指**来源优先级明确、过程可审计、结果可复算、限制可见**，不等于“永远正确”。
为避免把不同性质的数字放在一起，本报告使用以下证据等级。

| 等级 | 含义 | 典型例子 |
| --- | --- | --- |
| A：官方或当前客户端事实 | Valve 官方公告，或本机当前客户端可冻结的规则内容 | TI 日期、参赛队、40 次 Group Rolls、Stat 颜色和分值因子 |
| B：受治理的直接观测 | 有稳定 ID、UTC 时间、原始响应或 replay、SHA-256 的已发生数据 | 单局胜负、击杀、GPM、replay 原生 Watcher 计数 |
| C：确定性派生 | 给定 A/B 输入即可唯一复算的算术 | 正反补相加、团战参与率、Series 胜平负、品质/特性倍率 |
| D：经验证的模型推断 | 有预注册策略、时间回测、基线比较和冻结随机种子的估计 | Elo/Glicko 概率、Fantasy 情景均值、CVaR10、重采样稳定率 |
| E：实验或未闭合 | 仍有关键假设、门禁未过，或缺少正式输入 | 完整 Roll 草案、Main Roll、完整情景对齐的 Coach/Title 终局推荐、精确瑞士轮复刻 |
| X：不可用并排除 | 缺值、来源不符或规则冲突，正式计算不使用 | proxy 冒充的五项原生统计、未知 Coach 情景 |

这里的 `exact` 只表示“该字段来自获准的直接计数源”，不表示数据供应链绝不可能出错；
`derived` 只表示“公式确定”，不表示公式一定是 Valve 未公开的服务器实现；D 级概率更不表示事实。

## 一、共同的数据治理基础

### 1. 来源优先级

项目按以下顺序裁决冲突：

1. 本机当前 Dota 客户端与 Valve 官方公告；
2. Valve/OpenDota 的公开 API、开源数据契约和 replay 解析；
3. 社区赛事资料，仅用于补充 Tier、奖金和赛事背景；
4. 项目自己的统计假设与模型推断。

Valve 在 2026 年 7 月 30 日正式发布了
[The International: Predictions, Fantasy, and Supporter Bundles](https://www.dota2.com/newsentry/678505520073540063)，
确认本届活动包含 Swiss/淘汰赛 Predictions 与 Fantasy，并说明 Fantasy 使用同队 Core 二人组、
Mid 单人、同队 Support 二人组及作用于整队的 Coach，奖励按参与者相对表现发放。Valve 的 2026
邀请与资格赛公告同时给出了 16 队、8 月 13–16 日小组赛、五轮瑞士制和后续淘汰赛的官方外部
边界。更细的 Fantasy 计分、Roll 操作、品质和特性内容来自当时已安装客户端，因为官网公告没有
逐项公开这些机器可读字段。

OpenDota 不是 Valve 官方机构，而是开源社区数据平台；其项目说明明确写明，原始数据来自 Valve
WebAPI 和自动 replay 解析。因此本项目把 OpenDota 当作**可审计的数据管道**，而不是第二个规则
制定者。接口和字段含义分别锚定到
[OpenDota API 源码](https://github.com/odota/core/blob/master/svc/api/spec.ts)、
[League 响应类型](https://github.com/odota/core/blob/master/svc/api/responses/LeagueObjectResponse.ts)和
[版本时间线](https://github.com/odota/dotaconstants/blob/master/build/patch.json)。

### 2. 显式时间边界

所有正式入口都接受 UTC `as_of`。一条记录只有同时满足以下条件才可进入对应运行：

- 比赛开始和结果在 `as_of` 前已知；
- 数据抓取时间不晚于 `as_of`，或有明确的发布资料二次截止；
- 阵容在比赛当时已经生效；
- 规则快照创建时间不晚于运行时间；
- 版本和赛事级别能够映射到冻结策略。

2026-08-08 的首次赛事回测曾因规则快照创建时间比运行 `as_of` 晚 51 秒而被门禁阻止。项目没有
修改时间戳绕过，而是把截止推进到 `2026-08-08T04:11:08Z` 后完整重跑。这是时间防泄漏机制真实
生效的记录，不是纸面约定。详见
[小组赛发布实施报告](../../../reports/ti2026-group-forecast-publication-implementation-2026-08-08.md)。

### 3. 不可变原始数据和稳定身份

- 原始 HTTP 响应、客户端文件和 replay 不覆盖；
- 每次抓取记录 URL、参数、UTC 抓取时间、字节数和 SHA-256；
- 队伍用稳定 `team_id`，选手用稳定 `account_id` 连接；名称只用于显示；
- 阵容有生效区间，stand-in 不回填到更早的比赛；
- 缺失值保持 `null`，不会以 0 代替；
- 大型 raw、缓存和运行产物保留在本地并由 Git 忽略，正式文档记录其身份哈希。

对应契约见 [数据契约](../../../data-contracts.md)、[时间泄漏政策](../../../leakage-policy.md)和
[Forecast 协议](../../../forecast-protocol.md)。

### 4. 每次运行的可复现身份

每个正式运行至少记录：

- Git commit 或带 dirty 哈希的源码身份；
- 规则版本、规则快照 ID 和规则 SHA-256；
- 数据快照 SHA-256；
- 模型策略 ID 与 SHA-256；
- 显式 `as_of` 和随机种子；
- 输出文件及审计状态。

`publishable: true` 只表示工程门禁允许发布，并不表示统计预测已达到“高准确率”。`warning` 则要求
报告保留相应限制；它不是可以从玩家版中删掉的噪声。

## 二、梦幻挑战（Fantasy）

### 1. 规则基础来自哪里

Fantasy 正式证据运行固定在客户端快照 `20260806T172612Z-702ddf2a6953`：

| 身份 | 值 |
| --- | --- |
| 客户端 build | `6888:10887746` |
| 快照取证时间 | `2026-08-06T17:26:12.999472Z` |
| 规范规则 SHA-256 | `5c0236554e225eea8a494fb705fe08ec0dd3c9b67320602c4220ff7d356fd09d` |
| 快照 SHA-256 | `702ddf2a6953f383895efdfa3e45460c770e7c3c37e71d6a2b1d68e547a3235f` |
| 正式规则文件 | `config/rules/ti2026.json` |

8 月 8 日又以当前 build `6891:10893022` 生成快照
`20260808T040729Z-a6265cd07001`；它的规范规则 SHA-256 仍是同一个
`5c0236554e225eea8a494fb705fe08ec0dd3c9b67320602c4220ff7d356fd09d`。因此这里既保留 P3
实际使用的 build 6888 身份，也用 build 6891 复核规则没有语义漂移；不会把后来的快照伪装成
P3 当时的输入。

快照冻结了英文/中文本地化、`international_2026.eventdef`、Fantasy 计分动作和
`fantasy_crafting.vdata`。它直接支持以下 A 级事实：

- Group 有 3 个初始槽位和 40 次新 Rolls；Main 有 5 个槽位、30 次新 Rolls，并继承前三槽；
- Core 是红/绿/红，Mid 是红/蓝/绿，Support 是蓝/绿/蓝；
- 三种颜色各有 6 个 Stat，共 18 个；
- 五档品质加成为 10% / 30% / 60% / 100% / 150%；
- 五种特性、28 个操作模板和三个共享 Roll 选项的客户端定义；
- 每次“应用一个操作”或“刷新全部三个选项”都消耗 1 次 Roll，操作只作用于当前选中的战旗。

其中 28 个操作模板有 20 个正权重操作（ID 9–17、23–33），8 个零权重模板；正权重合计 168。
权重来自客户端文件，但服务器是否还对目标、子选择或条件分支做隐藏处理并未完全公开，因此不能把
客户端权重机械地称为完整的真实 offer 概率。

客户端还固定了活动 league ID `19719` 和 Group/Main 两个 Fantasy period 时间窗。相对奖励的
可见锚点为 10/20/40/60/80/90/95/99/100 百分位；Valve 没有公开锚点之间的完整换算函数，
所以项目优化 raw Fantasy points，不对任意百分位做线性插值。

### 2. 18 项 Stat：来源、公式和状态

下表的“基础分”是单个 Stat 在品质、特性和 Coach 作用前的贡献。正式优化只接受与当前规则要求
相同的 `exact` 或 `derived` 来源。

| 颜色 | Stat | 基础分公式 | 数据来源 | 状态 |
| --- | --- | --- | --- | --- |
| 红 | 击杀 | `107 × kills` | 单局计数 | `exact` |
| 红 | 死亡 | `max(0, 1950 - 195 × deaths)` | 单局计数 | `exact` |
| 红 | 正补与反补 | `3 × (last_hits + denies)` | 两个直接计数相加 | `derived` |
| 红 | GPM | `2 × gold_per_min` | 单局计数 | `exact` |
| 红 | 魔石拾取 | `13 × count` | replay `m_iNeutralTokensFound` | `exact` |
| 红 | 防御塔最后一击 | `352 × count` | 单局计数 | `exact` |
| 蓝 | 假眼放置 | `117 × count` | 单局计数 | `exact` |
| 蓝 | 堆叠野怪营地 | `234 × count` | 单局计数 | `exact` |
| 蓝 | 神符拾取 | `141 × count` | 单局计数 | `exact` |
| 蓝 | 诡计之雾使用 | `293 × count` | replay `m_iSmokesUsed` | `exact` |
| 蓝 | 瞭望台占领 | `147 × count` | replay `m_iWatchersTaken` | `exact` |
| 蓝 | 莲花拾取 | `176 × count` | replay `m_iLotusesTaken` | `exact` |
| 绿 | Roshan 击杀 | `1172 × count` | 单局计数 | `exact` |
| 绿 | 团战参与 | `min(2124, 2124 × (kills+assists)/team_kills)` | 直接计数按项目公式派生 | `derived` |
| 绿 | 第一滴血 | `1934 × flag` | 单局计数 | `exact` |
| 绿 | 眩晕秒数 | `10 × seconds` | 单局计数 | `exact` |
| 绿 | 魔方击杀 | `879 × count` | replay `m_iTormentorKills` | `exact` |
| 绿 | 信使击杀 | `703 × count` | 单局计数 | `exact` |

团战参与在全队 0 击杀时保持 `null`。该派生公式被明确标为
`owner_defined_until_client_formula_verified`；它是确定、透明的项目公式，但不冒充 Valve 已公开的
服务器内部公式。完整契约见 [Fantasy 覆盖说明](../../../fantasy-coverage.md)。

### 3. 为什么五项 replay 统计不是 proxy

魔石、诡计之雾、瞭望台、莲花和魔方曾经只能从事件图做近似。P1 后，正式路径改为解析 Valve
`.dem` replay 中的玩家最终原生计数；旧 proxy 只留作诊断，不参与最优解。固定 commit 的
[Valve GC 协议镜像](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/proto/dota_gcmessages_common.proto#L1107-L1135)
提供了同语义的 Fantasy 字段，[OpenDota parser](https://github.com/odota/parser/blob/02b78c6ca0010b5ed64a800c23212040c28d35ce/src/main/java/opendota/Parse.java#L639-L688)
也证明了按 team slot 读取最终 DataTeam 实体的既有路径。本项目使用固定
[Clarity](https://github.com/skadistats/clarity) `4.0.1` 解码 replay；Clarity 只是 decoder，字段的
Fantasy 业务语义仍由客户端、协议字段和 replay 差分共同支撑。

冻结 replay 范围的验收结果：

| 项目 | 结果 |
| --- | ---: |
| 完整 replay Game | 2,055 |
| 原生玩家行 | 20,550，恰为每局 10 个稳定账号/槽位 |
| 五字段状态为 `exact` 的 Game | 2,055 |
| 获准 Watcher cohort | 113；不可信 cohort 为 0 |
| 压缩 replay 原始捕获 | 197,435,437,515 bytes（183.876 GiB） |
| 三次无操作复跑 | 全部复用 2,055 局；0 次网络或解析工作 |
| 真实 replay fixture 回归 | 6 份、300 个玩家统计值全部一致 |

关键身份包括 match-ID 集合 SHA-256
`f16e5b070a2b2119e04e08270500b4059e29cad0c4012f8bef8d7c6bf7973b6c` 和历史解析 JAR SHA-256
`fc109d605ab7d190b95fcb5fa7b5619db2495c1372dfc89640eb5dbc190e40b1`。当前可复现 JAR 的包装哈希
不同，但真实 fixture 未观察到语义回归；这仍保留为 warning，而不是被改写成“完全相同”。完整记录见
[P1 原生 replay 统计实施报告](../../../reports/p1-native-replay-stats-implementation-2026-08-06.md)。

正式 overlay 只有在实体、解析器版本、replay 哈希、字段 presence 和 Watcher build cohort 都通过
时才写 `exact`。原生值为 0 但字段确实存在时是 exact 0；字段没观察到时仍为 `null`，不会把解析器
默认值或旧 proxy 当成 0。

### 4. 单局分数怎样变成一个 Period 的 Fantasy 分数

正式计分代码在 `src/ti_predictor/fantasy/scoring.py`，计算顺序为：

1. 按上表计算每个徽标的基础 Stat 分；
2. 品质与特性对该 Stat 基础分做加法百分比修正，倍率最低为 0；
3. Core/Support 各取两名选手单局分的平均，Mid 使用该中单一人的分数；
4. 一个 Series 只累计该战旗分数最高的两局；
5. 一个 Period 只取该队所有 Series 中分数最高的一个 Series；
6. 若使用 Coach，再把前缀和后缀条件逐个乘到最终单局分。

品质与特性的百分比叠加是客户端文案和总值行为支持下的强推断；Coach 的乘法顺序仍是项目政策，
因此两者不能被写成同一证据等级。P3 的生产估值没有完整、情景对齐的 Coach 前缀+后缀候选，
所以当前把 Coach 明确标记为 `unavailable_excluded`，没有用一个平均 Coach 奖励偷偷补分。

这不再表示“玩家完全没有 Title 建议”。新增的独立 Title 报告使用当前客户端 128 名英雄的八类
标签、1,512 场原始比赛详情和 2,373 个队伍×位置 Series blocks，给出中性默认
`Cerulean + the Clutch`。它只计算逐图触发率乘显示加成的纸面值，没有并入 P3 的未来战旗和最佳
Series 联合选择，因此补上了人工选择指南，但没有改写上述生产门禁。

### 5. 品质和特性怎样计算

品质倍率为基础 `1` 加对应品质：T1 `+0.10`、T2 `+0.30`、T3 `+0.60`、T4 `+1.00`、
T5 `+1.50`。特性再按位置关系调整：

- Fractal：三枚品质各不相同时，自身 `+0.60`；
- Benevolent：左右相邻各 `+0.20`；
- Vampiric：自身 `+0.50`，相邻各 `-0.10`；
- Unique：整条战旗只有一枚 Unique 时，自身 `+0.30`；
- Friendly：至少三枚 Friendly 时，每枚 Friendly 自身 `+0.50`。

Group 每条战旗有三槽，因此项目穷举全部 `5³ = 125` 个有序特性组合，再应用品质与相邻关系。
这部分是“给定规则后的精确算术”，不会产生 Monte Carlo 误差；不确定性来自底层未来 Stat 表现和
客户端叠加语义，而不是 125 组合漏算。

### 6. Fantasy 历史样本和权重

Fantasy 不只看选手现在所属队伍的比赛。它按 TI 名单中的稳定玩家 ID 选择其全球职业历史，保留
这些选手在旧队伍时的合格表现；否则刚转会选手会被错误地当成没有历史。

正式 P3 证据包 `fantasy-5e21be304ea57672` 的数据审计为：

| 项目 | 数值 |
| --- | ---: |
| 输入 Game | 44,661 |
| `as_of` 前已结束且有身份/结果 | 42,197 |
| 身份或结果缺失 | 2,464 |
| 有正权重的 Fantasy Game | 4,388 |
| 其中 7.41 / 7.40 | 2,218 / 2,170 |
| 赛事目录等级 | 全部 `professional` |
| 总有效权重 | 822.593427 |

证据权重沿用已冻结的队伍强度政策：

`weight = patch_weight × tier_weight × 2^(-age_days / 60)`

当前版本族 7.41 权重 1.0，紧邻版本族 7.40 权重 0.15，更早版本为 0；OpenDota `premium`
权重 1.0、`professional` 权重 0.75，其他等级为 0。时间每过去 60 天，权重减半。

这里的“赛事等级”是 OpenDota 数据目录字段，不是玩家所说的社区 Tier 1/2/3，也不是奖金。
社区 Tier 和奖金只出现在玩家赛果账本中帮助理解背景，没有偷偷进入当前模型权重。

### 7. 为什么按完整 Series 抽样，而不是把所有单局求一个平均

一届 TI 的 Fantasy 结果不是“无限多场比赛后的稳定平均”。队伍能打多少个 Series、每个 Series
打几局，以及某位选手在同一 Series 的连续状态都会影响最终取最高 Series的规则。因此模型保留
完整 BO2/BO3 块，而不是把单局独立打散。

P3 结构审计：

| 项目 | 数值 |
| --- | ---: |
| 合格 BO2/BO3 Game | 3,452 |
| 结构完整 BO2/BO3 Series | 1,405 |
| 不完整或混合 Series | 177 |
| 因 Series 格式不合策略而排除的正权重 Game | 936 |
| 16 队 × 3 定位样本池 | 48 |
| 每池完整 Series 最少 / 最多 | 10 / 88 |
| 目标玩家单局行 | 10,334 |
| 18 项来源匹配覆盖率 | 全部 100% |

早期只用 BO3 会让 OG Core 只剩 3 块、Nigma Core 只剩 5 块，低于预注册最低 10 块；纳入完整
BO2 后才达到门槛。这个选择不是为了把某队排名调高，而是为了在不拆散 Series 的前提下满足覆盖。

### 8. 8,192 个情景、均值、CVaR10 和 Top 3 稳定率

正式情景政策在 `config/models/fantasy-group-scenarios-v1.json`：

- 生成 8,192 个公共 Group 情景，所有候选在同一情景 ID 上比较；
- 六种赛果类别对应的 Series 机会数为 4 / 5 / 6 / 6 / 5 / 4；
- 从完整 Series 块按证据权重有放回抽样；
- 给定队伍赛果后，Core/Mid/Support 分别抽样；
- 每个情景执行真实“Series 取两局、Period 取最佳 Series”的计分；
- 对未来分数同时报告平均值和 CVaR10；
- 当前只验证了“均值不允许损失”的 `epsilon = 0` 终局匹配。

`Expected mean` 是所有情景的平均分；`CVaR10` 是最差 10% 情景的平均分，回答“运气不顺时大概
有多差”。它们都不是把全部历史行直接平均得到的一个确定常数，而是冻结抽样政策后的期望与下尾风险。

为了估计排名对历史样本的敏感程度，项目又做 400 次以完整 Series 为单位的分组重采样，每次
运行 512 个情景。最终得到 42 个“定位 × 颜色 × Stat”组、每组 16 队，共 672 个排名记录：

- `P1`：400 次重采样中该队排第 1 的比例；
- `P3`：排进前 3 的比例；
- `n`：该队该定位可用的完整 Series 块数；
- `Δ`：该队点估计均值相对当前第一名落后的比例。

P1/P3 是**历史 Series 重采样稳定率**，不是经过校准的“未来真实排名概率”。点估计第一只有
20/42 项的 P1 高于 50%，说明其余 22 项第一名对样本变化较敏感，不表示这 22 项没有结果。
完整玩家表见
[Stat 队伍 Top 3 发布版](../playbooks/group-roll/stat-team-top3-publication-v2.md)。

### 9. “一定保留 / 可以保留 / 可以改善 / 一定改善”的依据

发布表的建议档位来自固定阈值，不是人工凭印象逐格填写：

- “一定保留”：当前第一，且第二名均值低于第一的 44%；当前没有项目达到此极强门槛；
- “可以保留”：相对最佳价值至少 84.6%；
- “可以改善”：相对最佳价值在 44% 到 84.6% 之间；
- “一定改善”：相对最佳价值低于 44%。

边界附近再用 bootstrap 标记提醒。这个分档回答“该 Stat 值得多大力度保留或修复”，不等于对应
队伍必然拿到某个赛果。阈值和全部 Quality/Trait 表见
[Stat / Quality / Trait 证据表](../../../playbooks/group-roll/stat-quality-trait-evidence-v2.md)。

### 10. Roll 手册究竟验证到了哪里

Roll 的**机制**属于 A 级：三选一、应用/刷新成本、作用范围、操作列表和客户端权重都可从快照
复算。Roll 的**最优策略**属于 D/E 级，因为未来会刷出什么以及部分子选择率没有完全可观测。

v2 使用三类分布假设：客户端主模型、把权重拉平的保守模型、把高权重进一步放大的尖锐模型；
另有不依赖精确概率的 rate-agnostic 路线。验证结果为：

| 候选 | Common 情景 | 10% 失败 | 5% 失败 | 其他失败 | 状态 |
| --- | ---: | ---: | ---: | --- | --- |
| rate-agnostic | 253 | 23 | 96 | 仅 4 条规则通过所有发布模型消融 | `draft` |
| primary-model | 83 | 0 | 19 | 5 条核心规则、2 个风险修正失败 | `draft` |

只读 held-out 交叉审计完成 108/108，和 standalone/P5 样本均无重叠；rate-agnostic 没有新增重大
反例，primary-model 新增 1 个方向性反例，因此两本完整手册都不允许升级。正常 v2 standalone
与 cross-audit 合计约 4,173.6 秒（69.6 分钟），不需要再追加一次 15 小时运行。

当前发布的
[Group 40 Roll 玩家手册](../playbooks/group-roll/group-roll-publication-manual-v2.md)只保留证据分层的
保守规则；它不是把两本 `draft` 换个标题重新包装。历史 P5 full-session solver 仍为
`failed-escalation-review-required`，v2 没有新跑全程 P5。实验顾问冻结在 v1 身份，只做人工输入后的
本地一步诊断；Main Roll 和自动控制 Dota 客户端均不支持。

### 11. 三项客户端冲突怎样处理

规则快照仍保留三项冲突，因此不能声称“客户端内部与界面文字全部一致”：

- Early First Blood：内部条件包含“号角前或 1 分钟前”，可见文字写“号角前”；
- Late First Blood：内部字段为 6 分钟，可见文字写 10 分钟；
- Percentile：旧 action table 与 2026 可见的九个奖励锚点并存。

发布政策是使用玩家可见条件解释，但两个受冲突的一血 Title 不进入推荐排名；其他可观测 Title
可以进入单独的纸面触发率速查。Percentile 只优化 raw points，不猜中间映射。这些 warning 在新
客户端快照验证前不会被静默清除。

## 三、赛事预测（Forecast）

### 1. 先区分“预测对象”和“游戏内答案”

- **Forecast**：项目产生的队伍强度、单局倾向和联合情景分布；
- **InGamePrediction**：玩家最终在 Valve 活动界面填写的答案。

Forecast 是生成建议的证据，不等于 Valve 的正确答案。对局矩阵中的百分比表示中立条件下一张
Dota 地图的模型倾向，不是 BO3/BO5 系列胜率；本项目也不会自动填写客户端。

### 2. 比赛目录怎样建立

数据同步使用 OpenDota `/proMatches` 职业比赛目录，并以 `less_than_match_id` 向历史分页；不会拿
`/publicMatches` 的普通天梯样本混进职业模型。每局保留：

- `match_id`、开始时间、赛果；
- Radiant/Dire 稳定 `team_id`；
- league ID 和 OpenDota `league_tier`；
- patch ID、版本族和精确小版本；
- 原始响应哈希、抓取时间和 `as_of`。

2026 年同步得到 13,959 条职业比赛目录，和历史目录合并后为 44,906 条；当前 Forecast 实际读取的
冻结输入为 44,764 局，差异来自运行时可用快照和规范化筛选，不把目录行数直接说成训练样本数。

玩家版的 7.41 赛果账本另把 409 个完整系列、866 个系列内单局和 5 个不完整片段展开；那份账本
适合核对近期交手，但模型仍以每一局 Game 更新强度。社区 Tier 与总奖金只用于解释赛事背景，
不进入当前 Forecast 的 `tier_weight`。详见
[7.41 系列赛证据展开](ti2026-group-current-patch-series-evidence-2026-08-08.md)。

### 3. 哪些比赛真正进入当前模型

当前 Group 运行 `group-bcf9e6751005c6cf` 的审计为：

| 项目 | 数值 |
| --- | ---: |
| 输入 Game | 44,764 |
| `as_of` 前已结束且有身份/结果 | 42,300 |
| 身份或结果缺失 | 2,464 |
| 预连接图正权重 Game | 4,405 |
| 目标队连通图内正权重 Game | 3,943 |
| 连通图队伍 | 463 |
| 因不连通排除 | 462 |
| 其中 7.41 / 7.40 | 1,936 / 2,007 |
| 入模赛事目录等级 | 全部 `professional` |
| 总有效权重 | 691.656557 |

模型从当前 16 队出发，保留正权重对手网络中与它们连通的部分。这样没有直接交手的两队仍可通过
共同对手比较，但一个完全不相连的比赛岛不会改变 TI 队伍的相对强度。16 支目标队均在图内且达到
最低证据门槛。

### 4. 版本、赛事级别和时间权重

赛事模型与 Fantasy 使用同一个预注册权重公式：

`w = patch_weight × tier_weight × 2^(-age_days / 60)`

当前参数：

| 因子 | 权重 |
| --- | ---: |
| 目标版本族 7.41 | 1.00 |
| 紧邻版本族 7.40 | 0.15 |
| 更早版本 | 0.00 |
| OpenDota `premium` | 1.00 |
| OpenDota `professional` | 0.75 |
| 其他或未知等级 | 0.00 |
| 时间半衰期 | 60 天 |

这不是宣称“7.40 只有 7.41 的 15% 真理价值”，而是冻结在看结果之前的建模政策。它用来控制版本
漂移、低级别比赛和旧比赛对当前强度的影响，避免在看完 TI 2025 回测后临时调参追分。

### 5. Elo、Glicko 和 50/50 集成

模型对每局只使用比赛开始前已经存在的评分：

1. Elo 初始 1500，scale 400，`K = 28`；
2. 先算预期胜率 `p`，再按 `28 × w × (result - p)` 更新；
3. Glicko 初始 1500、RD 350，并按每 30 天 35 点增加不活跃不确定性；
4. Glicko 的残差和信息量也按证据权重缩放；
5. 最终原始单局概率固定为 `0.5 × Elo + 0.5 × Glicko`。

模型不会用同一场比赛更新后的评分再预测该场比赛。完整实现见
`src/ti_predictor/models/evidence.py` 和 `src/ti_predictor/models/ratings.py`，冻结配置见
`config/models/team-strength-v2.json`。

### 6. 为什么没有部署概率校准

模型使用时间顺序的 expanding-window 验证，不做随机拆分。预留 55% 初始历史后做 3 个滚动折，
候选 isotonic calibration 在前置滚动验证中的结果为：

| 版本 | Log loss | ECE |
| --- | ---: | ---: |
| 未校准 50/50 集成 | 0.680296 | 0.067997 |
| isotonic 候选 | 0.680409 | 0.023539 |

校准候选让 ECE 更好，却让预注册主门槛 log loss 变差，因此被拒绝。项目没有因为“数字看起来更像
概率”就忽略门禁。当前发布的 56%–58% 等数字必须注明**未经校准**。

### 7. TI 2025 固定留出回测

正式回测不是从训练集随机抽一部分，而是冻结整个 TI 2025（league 18324）作为过去未知的赛事：

- holdout 从 `2025-09-04T08:04:56Z` 开始；
- 144 局，全部 patch 7.39、OpenDota `premium`；
- 留出前有 19,452 局训练候选，4,505 局为正权重；
- 涉及该届 16 队的同版本训练证据为 661 局；
- 每队至少 14 局同版本证据；资格门禁通过。

固定留出结果：

| 方法 | Accuracy | Log loss | Brier | ECE |
| --- | ---: | ---: | ---: | ---: |
| 50% 基线 | 45.14%* | 0.69315 | 0.25000 | 0.04861 |
| 无权 Elo | 56.25% | 0.69533 | 0.25011 | 0.09837 |
| 无权 Glicko | 52.78% | 0.67898 | 0.24503 | 0.16975 |
| 无权 50/50 集成 | 54.86% | 0.68151 | 0.24540 | 0.14146 |
| 加权 Elo | 57.64% | 0.67266 | 0.24010 | 0.06746 |
| 加权 Glicko | 56.25% | 0.70507 | 0.25354 | 0.13833 |
| **正式加权 50/50 集成** | **56.25%** | **0.68255** | **0.24471** | **0.11342** |
| 加权 isotonic 候选 | 48.61% | 0.68510 | 0.24712 | 0.08713 |

\* 50% 模型每局都输出恰好 0.5；实现的固定平手阈值把它们全判到一侧，所以这列实际命中率是
45.14%。随机猜测的理论期望仍是 50%。正式模型相对理论瞎猜的提升是 **6.25 个百分点**，与玩家
“只比瞎猜好不到 10%”的体感一致，不能包装成很强的赛果预测器。

正式集成在 log loss 和 Brier 上击败 50% 基线，满足发布门槛；它并没有在所有指标上击败所有
候选。单看这一次 holdout，加权 Elo 的成绩最好，但策略已预注册为 50/50 集成；看完留出集再改成
Elo 会构成事后挑选，所以没有切换。正式集成相对无权集成的 Brier 改善 0.000691，log loss 反而
恶化 0.001044，也必须一并披露。

这说明赛事模型当前真正可靠的用途是**实力排序、实力带和相对对局关系**，不是精确猜每一局。

### 8. 两两胜负关系怎样得到

任意两队 A/B 的百分比由最终 Elo 与 Glicko 评分分别产生一个中立单局概率，再按 50/50 合并。
模型没有加入主客场、选边、英雄 BP、临场阵容变更、赛场状态或 BO3 转换。

所以“Yandex 对 Falcons 57%”只应读成：在当前证据、冻结权重和中立条件下，模型认为 Yandex
在一张地图上小优。它不是：

- Yandex 有 57% 把握赢下一个 BO3；
- 100 次真实比赛一定赢 57 次；
- 已校准后的客观概率；
- 对手无论阵容、版本细节和 BP 都保持 57%。

当前实力带、精确排名和矩阵见
[小组赛最终预测正文](ti2026-group-forecast-publication-2026-08-08.md)。

### 9. 小组赛 16 个槽位怎样联合生成

Valve 已确认五轮瑞士制，但当前本地规则证据不足以逐场、逐配对复刻全部 2026 执行细节。因此
`src/ti_predictor/tournament/group.py` 不声称自己是 Swiss bracket engine，而采用容量保持的联合
排名近似：

1. 对 16 队的强度评分加入 Gumbel 随机效用，生成一个联合次序；
2. 按固定容量 `1 / 2 / 5 / 5 / 2 / 1` 分到六种赛果类别；
3. 对 strength-seeded、balanced、high-variance 三种情景各抽样 100,000 次；
4. 先用 Hungarian assignment 按边际概率生成合法初始方案；
5. 再做 1,800 步成对交换，优化非线性的活动积分目标；
6. 同时输出 expected-points、top-10 和 top-100 三种目标。

该方法保证每个情景的类别人数合法，也让所有队伍在同一个联合情景中竞争；它比逐队独立选最大概率
更一致。但它没有生成真实五轮的对手、比分和 tie-break，所以是 D/E 级近似。

当前 expected-points 方案期望分为 583.559；直接按实力切片为 575.920，联合优化提升 7.639，约
1.3%。两者 P10/中位/P90 都是 60/360/1200。前 10% 和前 100 的服务器总体阈值没有可用分布，
目前只是低置信代理目标，不能与 expected-points 同等看待。

## 四、当前正式产物的可复现身份

### Fantasy P3

| 字段 | 值 |
| --- | --- |
| run ID | `fantasy-5e21be304ea57672` |
| `as_of` | `2026-08-06T17:27:00Z` |
| 源码 commit | `c652fd7cb16ff97c6ecb435ab3f361228709969f` |
| 随机种子 | `20260813` |
| 运行数据 SHA-256 | `1762609498913f6ae458aecfae52e429c61943081b2435562bcf4acb67688f08` |
| 治理数据快照 SHA-256 | `49e373b2c03a4598d51f3de3eb5b85f80f001a097dd26acaa41137862b58f88b` |
| 情景政策 SHA-256 | `e28876f6573afcdd261c044c215ece5fbbf6bc9ff0cf02324defcf445b961065` |
| Series 池 SHA-256 | `9a86b14e913e6e53fe4a53f7bd7325386b372521fe18c7924004cfbccfa33c16` |
| 情景 SHA-256 | `22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3` |
| Stat 预测 SHA-256 | `0ed11f560a82f7745bd5bb435ae0df5d71b37dbfaca96fc3936b3ba419184929` |
| bootstrap SHA-256 | `2dac3eac1acb091bf1b710160e79a4159cfdc32f761cb3b6847f7242d1c50a50` |
| 证据包语义 SHA-256 | `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2` |
| 状态 | `warning`，审计 `publishable: true` |

### 赛事 Forecast

| 字段 | 值 |
| --- | --- |
| run ID | `group-bcf9e6751005c6cf` |
| backtest ID | `backtest-3381891f1fac3f70` |
| `as_of` | `2026-08-08T04:11:08Z` |
| 客户端 build | `6891:10893022` |
| 源码 commit | `018965bec3baf8401e46c6e131db0fedaedf7c0f` |
| 随机种子 | `20260813` |
| 数据快照 SHA-256 | `cf7f2ab715e45a44031bfb5a7acaed73cde69902ef701dbb677692dc448849eb` |
| 规则快照 ID | `20260808T040729Z-a6265cd07001` |
| 规则快照 SHA-256 | `a6265cd07001e2a7710f23622f3bbe855b32d61445f17f4c941578c53a3275dc` |
| 强度政策 SHA-256 | `7eeef175cf50429444bf1aca465fcd4cf84416192575583f4db1f7d1cb2cbf46` |
| 状态 | `warning`，审计 `publishable: true` |

两个运行使用相同规范规则 SHA-256；Fantasy 冻结在较早的 build 和数据截止，赛事 Forecast 则在
8 月 8 日重新同步、回测和生成。报告没有把两个不同 `as_of` 拼成一个假装同时发生的快照。

## 五、主张—证据矩阵

| 主张 | 等级 | 直接依据 | 当前结论 |
| --- | --- | --- | --- |
| Group 有 40 Rolls、每次三选一 | A | 客户端规则快照 | 可按当前 build 视为规则事实 |
| 18 项颜色与计分因子 | A | 客户端 eventdef / scoring actions | 可精确复算 |
| 五项原生计数不是 proxy | B | 2,055 replay、20,550 行、fixture 回归 | 正式范围内可用 `exact` |
| creep score / 团战参与 | C | 公开项目公式和直接输入 | 可复算；团战参与公式不冒充 Valve 内部实现 |
| Stat Top 3 和 P1/P3 | D | 8,192 情景、400×512 Series bootstrap | 是稳定性证据，不是确定未来概率 |
| Quality/Trait 倍率 | C | 客户端参数 + 125 组合穷举 | 给定叠加语义可精确计算 |
| 完整 v2 Roll 策略最优 | E | standalone/cross-audit 门禁未过 | **不能声称** |
| Group Roll 保守规则可发布 | D | 分层规则、独立审计和反例披露 | 可用，但需遵守适用条件 |
| Coach 已有正式最优选择 | X/E | 缺少完整情景对齐候选 | **当前没有** |
| 队伍综合排序比纯猜测好 | D | TI 2025 固定 144 局 holdout | 有小幅优势，约 +6.25pp |
| 对局矩阵是 BO3 胜率 | X | 当前只建模中立单局 | **错误说法** |
| 模型概率已校准 | X | isotonic 候选被预注册门禁拒绝 | **当前未校准** |
| 小组 16 槽是精确 Swiss 结果 | E | 容量保持的 Gumbel 联合近似 | **不能声称精确** |
| 社区 Tier/奖金影响模型权重 | X | 只用于发布版背景展开 | **没有进入当前模型** |

## 六、已知问题与发布边界

1. **Fantasy Coach 缺口。** 条件文字已取证，但缺完整、情景对齐的未来英雄/条件候选；生产估值排除。
2. **跨定位相关性。** Group Fantasy 在给定队伍赛果后独立抽取 Core/Mid/Support，没有保留同一
   历史 Series 的跨定位共同波动；CVaR 可能因此偏乐观或偏平滑。
3. **Series 机会数是近似。** 4/5/6/6/5/4 来自冻结赛果容量政策，不是逐轮 Swiss 赛程生成器。
4. **Roll offer 隐藏率。** 客户端权重可见，但目标/子选择的真实服务器概率未完全确认；完整手册仍草案。
5. **Main Roll 未覆盖。** 当前玩家手册只支持 Group 40 Rolls。
6. **赛事预测准确率有限。** 144 局 holdout 的 56.25% 只比理论随机猜测高 6.25 个百分点。
7. **概率未校准。** ECE 和滚动门禁不允许把当前百分比解释成可靠频率。
8. **精确 Swiss 缺失。** 联合容量模拟不生成实际对阵和 tie-break。
9. **社区元数据会变化。** Tier、奖金和赛事页面只冻结到 `2026-08-08T06:05:53Z`，且不入模。
10. **旧最终 Fantasy 阵容已过时。** 8 月 2 日固定阵容报告使用更早快照；当前最强证据是后续
    Stat/Quality/Trait、队伍 Top 3 和分层 Roll 手册，没有一份同截止时间的新 Coach+三战旗最终阵容。

## 七、复算入口

在已经还原**对应源码 commit、规则快照和处理后数据快照**的前提下，关键入口为：

```powershell
uv run ti rules validate
uv run ti audit fantasy-5e21be304ea57672
uv run ti audit backtest-3381891f1fac3f70
uv run ti audit group-bcf9e6751005c6cf
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
uv run ti forecast group --as-of 2026-08-08T04:11:08Z --profile all
```

如果重新联网抓取，得到的是新的数据快照，不能期待 run ID 与本报告完全相同；要复现这里的哈希，
必须使用这里记录的原始响应、规则快照、源码 commit、配置和种子。若直接在较新的源码或
`matches.parquet` 上审计旧 run，`ti audit` 应当以 `run-source_version-changed`、
`run-data_sha256-changed` 或 `as-of-future-data` 阻断；这是防止历史产物冒充当前产物的正确行为，
不是旧产物的原始 `audit.json` 被改写。

## 八、最终可信度判断

可以高度信任的是：**我们确实用了哪些数据、这些数据如何清洗和加权、公式如何执行、哪些样本被
排除、运行身份是什么、门禁通过或失败在哪里。** 这些内容具备项目级复现证据。

可以有条件信任的是：**Fantasy Stat 的相对价值、队伍综合实力带和两两强弱方向。** 它们比只看
近期胜负或凭印象更系统，但仍受样本、版本、阵容和模型假设影响。

不能完全相信的是：**精确名次、微小概率差、未经校准的百分比、完整 Roll 最优策略、Coach 和精确
Swiss 槽位。** 对这些内容，最权威的表达不是给出更肯定的语气，而是保持 `draft`、`warning`、
`unavailable` 和近似说明。

这也是本报告的核心结论：当前工程的权威性主要来自**诚实而完整的证据链**，而不是把有限的预测
能力写成确定答案。

## 参考与审计入口

- [Valve：TI 2026 Predictions / Fantasy / Supporter Bundles](https://www.dota2.com/newsentry/678505520073540063)
- [Valve / Steam：Dota 2 官方公告流](https://store.steampowered.com/news/posts/?appids=570)
- [OpenDota Core：数据来源与解析架构](https://github.com/odota/core)
- [OpenDota API 机器契约](https://github.com/odota/core/blob/master/svc/api/spec.ts)
- [OpenDota League 响应类型](https://github.com/odota/core/blob/master/svc/api/responses/LeagueObjectResponse.ts)
- [OpenDota patch 时间线](https://github.com/odota/dotaconstants/blob/master/build/patch.json)
- [OpenDota parser](https://github.com/odota/parser)
- [Clarity replay 解析库](https://github.com/skadistats/clarity)
- [Valve 7.41e 补丁页（可回到 7.41 系列）](https://www.dota2.com/patches/7.41e)
- [Fantasy 覆盖契约](../../../fantasy-coverage.md)
- [模型方法说明](../../../modeling.md)
- [Group Roll 证据索引](../../../playbooks/group-roll/README.md)
- [小组赛发布实施报告](../../../reports/ti2026-group-forecast-publication-implementation-2026-08-08.md)
