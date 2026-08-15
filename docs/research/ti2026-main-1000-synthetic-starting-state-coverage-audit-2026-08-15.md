# TI 2026 Main：1000 个 synthetic starting-state coverage 规则与实验设计审计

## 审计结论

可以开始 1000 个 Main 起点的研究，但结论必须限定为：**在当前冻结规则、projected
Main release 和人为定义的 uniform-legal 生成设计下，对 G/T/H 做广覆盖压力测试**。
它不能被表述为“1000 个真实玩家起点”“Valve 初始状态概率”或“玩家总体期望收益”。

本机 Dota 客户端快照足以确定以下结构支持：三面 Banner、每面五槽、各槽颜色与合法
Stat、T1–T5、五种 Trait、三个互不重复且共享的正权重 Roll operation，以及 Main 首次
决策前的 30 枚 Roll。它没有公开 15 枚 Emblem 与初始 offer 的联合生成算法。尤其不能
把客户端的 operation / Quality `roll_weight` 自动解释成 Main 初始画面的分布。

因此，本研究可以使用“各合法类别均匀、相互独立”的 synthetic generator；这是一项
由研究者冻结的抽样设计，不是对 Valve 后台的估计。100 个 development cases 与 900 个
confirmation cases 必须在任何策略得分产生前固定；G/T/H 在同一 case 内使用 common
random numbers；五模型 sensitivity 若只跑子集，子集也必须在看结果前由 state hash
确定，并且每个入选 state 必须完整跑五个模型。

本次审计只新增本文，没有修改 `src/`、`config/`、`tests/`、Web 或 runtime，也没有运行
正式模拟。

## 1. 一手证据边界

### 1.1 冻结客户端身份

当前研究 manifest 绑定的 Rule snapshot 是
`20260813T132319Z-9728c506baf6`，`as_of=2026-08-13T13:23:17Z`，客户端 build 为
`6898:10904633`。快照保存了原始客户端文件的逐文件 SHA-256；其中
`scripts/fantasy_crafting.vdata` 是 Banner、Gem、Quality、Trait 和 operation 的主要
一手证据（[rule_snapshot.json:2-32](../../data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json#L2-L32)）。

客户端 event definition 给 Main period 发放 30 Rolls
（[international_2026.eventdef:134-148](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/events/international_2026.eventdef#L134-L148)）；
规范规则同时把 Group/Main 记录成 3/5 槽、40/30 Rolls，并把 Main 的槽 1–3 标为 carried
（[config/rules/ti2026.json:45-56](../../config/rules/ti2026.json#L45-L56)）。后者意味着
“把 Main 的 15 枚 Emblem 全部独立随机生成”会有意忽略玩家从 Group 带入前三槽的历史
相关性，只能作为 synthetic 压力测试。

### 1.2 Main 状态的已证实结构支持

| 字段 | 可用于生成器的结构约束 | 证据 |
| --- | --- | --- |
| Period / Roll | `period=main`；首次决策固定 `remaining_rolls=30` | 客户端快照记录 40/30 两期 Roll（[rule_snapshot.json:79-83](../../data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json#L79-L83)）；Main validator 接受范围 0–30（[main_roll.py:67-82](../../src/ti_predictor/fantasy/main_roll.py#L67-L82)） |
| Banner | 严格按 `core, mid, support` 排列；每面恰好 5 枚 Emblem | 客户端解析结果（[rule_snapshot.json:273-364](../../data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json#L273-L364)）；validator（[main_roll.py:67-82](../../src/ti_predictor/fantasy/main_roll.py#L67-L82)） |
| Core 槽色 | `red, green, red, green, red` | 客户端原文件（[fantasy_crafting.vdata:445-474](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata#L445-L474)） |
| Mid 槽色 | `red, blue, green, red, green` | 客户端原文件（[fantasy_crafting.vdata:476-504](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata#L476-L504)） |
| Support 槽色 | `blue, green, blue, green, blue` | 客户端原文件（[fantasy_crafting.vdata:505-536](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata#L505-L536)） |
| Stat | 每种颜色各 6 个；每槽只能取本槽颜色的 6 个之一 | 客户端 Gem 定义（[fantasy_crafting.vdata:338-378](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata#L338-L378)）；构造时要求 18 个 Stat 唯一且与客户端完全匹配（[roll.py:303-343](../../src/ti_predictor/fantasy/roll.py#L303-L343)） |
| Quality | 每槽可为整数 T1–T5；重复允许 | 客户端定义五档 bonus/roll weight（[fantasy_crafting.vdata:412-444](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata#L412-L444)）；状态校验（[roll.py:506-534](../../src/ti_predictor/fantasy/roll.py#L506-L534)） |
| Trait | 每槽可为 `fractal, benevolent, vampiric, unique, friendly`；重复允许 | 客户端五种 Shape behavior（[fantasy_crafting.vdata:379-411](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata#L379-L411)）；项目语义（[config/rules/ti2026.json:130-136](../../config/rules/ti2026.json#L130-L136)） |
| Offer | 恰好 3 个互不重复的 operation ID；只能来自 20 个正权重 operation；offer 跨三面 Banner 共享 | 客户端解析结果含 `offer_size=3` 和 operation 表（[rule_snapshot.json:178-218](../../data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json#L178-L218)、[rule_snapshot.json:365-777](../../data/raw/rules/20260813T132319Z-9728c506baf6/rule_snapshot.json#L365-L777)）；规范 offer contract（[config/rules/ti2026.json:71-88](../../config/rules/ti2026.json#L71-L88)）；数据结构和校验（[roll.py:83-96](../../src/ti_predictor/fantasy/roll.py#L83-L96)、[roll.py:536-543](../../src/ti_predictor/fantasy/roll.py#L536-L543)） |

三色 Stat 的完整集合是：

- Red：`kills, deaths, creep_score, gpm, madstone_collected, tower_kills`；
- Blue：`wards_placed, camps_stacked, runes_grabbed, smokes_used, watchers_taken, lotuses_gained`；
- Green：`roshan_kills, teamfight_participation, first_blood, stuns, tormentor_kills, courier_kills`。

20 个可进入 offer 的 operation ID 是
`9–17, 23–33`（其中不存在 `18–22`）；`1–8` 是零权重模板，不能出现在合法 offer。
构造器会逐项核对客户端与规范规则，并检查正权重 ID、总权重 168 以及每项 mutation
support（[roll.py:404-469](../../src/ti_predictor/fantasy/roll.py#L404-L469)）。

这里的“合法”准确地说是**冻结客户端规则与项目 validator 接受的状态支持**。它不等于
Valve 已经证明所有这些属性组合都会作为某位玩家的 Main 初始画面出现。

现有测试已经覆盖 Main 五槽/30 Roll、Group/Main 路由隔离、五槽 operation 24 的精确
支持、offer 三项唯一性、五个概率模型不改变合法支持和确定性采样
（[test_fantasy_main_roll.py:64-145](../../tests/test_fantasy_main_roll.py#L64-L145)、
[test_fantasy_main_roll_research_probability.py:51-106](../../tests/test_fantasy_main_roll_research_probability.py#L51-L106)）。
这些测试证明实现按冻结规则工作，不证明真实初始联合分布。

### 1.3 没有被客户端证实的部分

对本地 `fantasy_crafting.vdata` 的 setup 定义、当前 Rule snapshot 和公开协议接口的审计
没有找到下列初始联合分布：

1. Main 新增第 4、5 槽的 Stat、Quality、Trait 如何生成；
2. Group 带入的前三槽在玩家总体中的分布，以及它们与新增槽的相关性；
3. 同一 Banner 内或三面 Banner 之间的初始 Quality/Trait 相关性；
4. Main 第一次可见 offer 是否与后续 replacement offer 使用同一分布；
5. operation/Quality 的客户端 `roll_weight` 是否、以及如何用于首次画面；
6. Trait、Stat、随机目标和多格结果的服务端真实概率。

客户端 schema 只把 operation 的 `m_nRollWeight` 描述为放入 roll board 时的权重，并把
Quality 的同名字段描述为被 reroll 到的相对可能性；Shape/Gem schema 没有相应的
per-item weight。可交叉核对
[`FantasyCraftOperation_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftOperation_t.h#L11-L22)、
[`FantasyCraftingQualityData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingQualityData_t.h#L8-L17)、
[`FantasyCraftingShapeData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingShapeData_t.h#L8-L17)
和
[`FantasyCraftingGemData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingGemData_t.h#L9-L16)。
这些是客户端字段语义，不是 GC 的抽样实现。公开 protobuf 也显示 Apply/Refresh 由 GC
返回更新后的 UserData/TabletData
（[`PerformOperation`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/Protobufs/dota_gcmessages_client_fantasy.proto#L431-L464)、
[`RerollOptions`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/Protobufs/dota_gcmessages_client_fantasy.proto#L622-L639)）。

“未在已审计客户端表面发现”不是“Valve 一定没有服务端规则”。它要求我们把初始分布
保持为 unknown，而不是反推一个未经证实的概率。

## 2. 1000 个起点的合规生成解释

### 2.1 建议冻结的 uniform-legal generator

如果目标是用户已批准的“完全随机也可以”，最小、可复现且不伪装后台概率的生成规则是：

1. 固定一个 master seed、generator ID/version、Rule snapshot hash、Main release hash 和
   显式 UTC `as_of`；
2. 对每个 `state_index=0..999` 用独立的 hash-keyed RNG 命名空间生成，不能依赖前一个
   state 消耗了多少随机数；
3. 按 canonical role/slot 顺序生成 15 枚 Emblem；每槽 Stat 从对应颜色 6 项中均匀取一项，
   Quality 从 T1–T5 均匀取一项，Trait 从五项中均匀取一项；三个属性及各槽在**生成设计**
   中相互独立；
4. 从 20 个正权重 operation 中无放回均匀抽 3 项，并随机排列为一个 ordered offer；
5. 固定 `period=main`、`slot_count=5`、`remaining_rolls=30`；
6. 每个 state 必须通过 `validate_main_state`，保存 canonical payload SHA-256；1000 个
   state hash 必须唯一；
7. 起点 RNG、split RNG（若有）和未来 Roll tape RNG 使用不同的 domain salt。

本协议中的“1000 个研究”应计为 1000 个 starting-state cases，而不是 1000 个单策略
episode。Primary 至少会产生 `1000 × 3` 条 G/T/H episode；五模型 sensitivity 会在其
预注册子集上额外产生对应的 state × model × policy episode。

这里的“均匀”只描述 generator。未来 30 步仍由冻结的 Primary / sensitivity Roll
transition model 决定。不要调用 Primary provider 的 weighted `draw_offer` 来生成初始
offer，然后把它写成“真实 Main 起点”；现有 provider 的职责是给未来 transition 的同一
合法支持赋模型概率（[main_roll_research_probability.py:128-169](../../src/ti_predictor/fantasy/main_roll_research_probability.py#L128-L169)）。

### 2.2 这 1000 个 case 能覆盖什么、不能覆盖什么

每槽有 `6 × 5 × 5 = 150` 个合法属性组合，15 槽加一个 ordered 三选项后，synthetic
状态空间超过 `2.9 × 10^36`。1000 个随机 case 只是宽覆盖样本，不是枚举。

在独立均匀设计下可以预期：

- 15,000 个 Emblem 槽中，每档 Quality 和每种 Trait 各约出现 3,000 次；
- 每个 state 有 5 个 Red、4 个 Blue、6 个 Green 槽，因此每个同色 Stat 的期望频数分别
  约为 833、667、1,000；
- 3,000 个 offer 位置中，每个 operation 的期望频数为 150；
- 一面 Banner 的五档 Quality 恰好全异概率仅为 `5!/5^5 = 3.84%`；某一指定档位占满
  五槽的概率只有 `1/5^5 = 0.032%`。因此极端配置或某些 readiness cell 仍可能为空。

所以正式运行前应冻结 coverage diagnostics，但不能看策略结果后再补“有利”起点：

- 各 role × slot × Stat/Quality/Trait 的边际计数；
- 各 operation 的 offer 计数与 offer 重复数；
- 各 role 的 Starting Stat readiness、Starting configuration readiness 以及九个交叉 cell
  的 case 数；
- Fractal 全异、Friendly 至少三枚、Unique 恰一枚等结构条件的出现数；
- 重复 state hash、非法 state 和空的预声明必需 cell。

如果协议只承诺“1000 个 i.i.d. uniform-legal case”，空极端 cell 是限制，不应在生成后
替换样本。如果协议要求“九个 cell 必须平衡”，则应在得分前改成预注册的分层随机生成，
并产生新的 generator version；两种设计不能在结果出来后混用。

## 3. 100 development / 900 confirmation 的隔离

### 3.1 合规切分

建议把 state index、split、state hash 和 roll-tape seed 在任何 terminal/策略调用前写入
一个不可变 index：

```text
state 0000..0099 -> development
state 0100..0999 -> confirmation
```

固定连续索引是可接受的，前提是每个 state 使用按 index 独立派生的 RNG；也可以使用固定
salt 的 hash split。关键不是 10/90 本身，而是**分配先于得分且永不因结果变化**。

当前 G/T/H 的 policy ID 与参数已经由前一轮单起点研究冻结，所以本路线中的 100 个
development case 默认只用于：

- generator/validator、序列化、并行确定性和耗时/内存验证；
- 检查 coverage diagnostics、报告 schema 和预注册数值容差是否可执行；
- 发现非法状态或实现 bug 后修复，并从同一 generator spec 重新生成全套 hash。

它们不应被静默用于重新选择 T/H 参数或发现 state-conditioned meta-policy。若确实要把
development 用于这类策略开发，必须显式启动新的 policy/version 与候选选择协议，并在
首次读取 900 个 confirmation 得分前冻结；本轮原定的“固定 G/T/H 广覆盖确认”结论随之
失效，不能把两种研究口径合并。

900 个 confirmation case 不能用于：

- 看哪类起点输得多后再改变 T/H 参数或切换阈值；
- 根据 Primary 得分挑出“好看的”五模型 sensitivity state；
- confirmation 失败后修改策略，再用同一 900 case 宣称新的独立确认。

如果 development 导致任何 policy behavior 改动，应先冻结新的 policy ID/config/hash，再
首次打开 confirmation。若看过 confirmation 后仍要开发 state-conditioned meta-policy，
这 900 个 case 已变为探索数据，必须另建未见 holdout；不能把同一批数据同时用于发现
“在哪些状态切换策略”和证明该切换有效。

### 3.2 统计单位

每个 confirmation state 在 Primary 下至少产生一个独立的 `state + roll-tape` 配对单位，
G/T/H 都在这个单位内比较。900 是主分析的最大独立样本数；每个 terminal evaluation
内部的 224 个 projected-derived roster、1792 条 selection/evaluation paths 是同一个
冻结估值面板，不能把 `900 × 1792` 当成独立样本数。

Primary 的报告可以包含：

- 900 个 state-level paired terminal-mean difference 的均值、中位数、win/tie rate 与
  95% 区间；
- state-level conditional CVaR10 difference；
- paired difference 的最差 10% / material-loss rate；
- 预声明 readiness/trait/offer strata 的条件结果及 case count；
- 七个 roster confirmation fold 的既有非劣检查。

总体平均只能叫 `uniform-legal design average` 或 `synthetic coverage average`。它是对
本次生成设计的 Monte Carlo 平均，不是 `Expected Main score for players`，也不是玩家
真实起点加权结果。现有领域词汇也要求 Starting-state coverage suite 不承担初始概率模型
含义（[CONTEXT.md:254-283](../../CONTEXT.md#L254-L283)）。

若一个 state 以后增加多个 roll-tape replicate，置信区间应以 state 为 cluster，或者先在
state 内聚合再跨 state 推断，不能把同一 state 的 replicate 当完全独立。若要对大量 strata
逐一宣称显著性，还要预注册 family/multiplicity 处理；否则 strata 结果保持描述性。

## 4. G/T/H 的配对随机性

当前 simulator 已按 `episode_seed / spent-step / draw-kind` 创建 hash-keyed RNG，且不把
policy ID 写入 key；同一 seed 的 G/T/H 因而得到 common random numbers
（[main_roll_research_simulator.py:284-287](../../src/ti_predictor/fantasy/main_roll_research_simulator.py#L284-L287)、
[main_roll_research_simulator.py:308-366](../../src/ti_predictor/fantasy/main_roll_research_simulator.py#L308-L366)）。
runner 也要求 paired policies 拥有相同 episode seed
（[main_roll_research_experiment.py:275-305](../../src/ti_predictor/fantasy/main_roll_research_experiment.py#L275-L305)）。

对 1000-state runner，需进一步满足：

1. 每个 state 有唯一的 roll-tape seed，或 tape key 显式包含 state ID；不能让 1000 个
   state 都复用同一个 seed；
2. 同一 state × probability model 内，G/T/H 共享同一组 keyed uniforms；
3. strategy 不得读取未来 key、future offer 或未实现 mutation；
4. state 生成 RNG 与 roll tape 完全分离；
5. pairing identity 至少是 `(state_id, state_sha256, model_id, tape_seed)`，不能只靠 seed
   偶然唯一；
6. action 不同会把同一 uniform 映射到不同分布/结果，提前 Stop 也会少消费后续步。因此
   准确表述是“共享 keyed random-number tape / common random numbers”，不是“三策略得到
   完全相同的已实现操作结果”。

这种配对降低策略差值的无关 Monte Carlo 噪声，但不会消除 starting-state 设计偏差、
transition-model 不确定性或固定 match-performance panel 的条件性。

## 5. 五模型 sensitivity 子集

当前单起点 confirmation 合约要求全部五模型完整出现，否则 runner 会拒绝 gate；现有
manifest 也把 “五模型 mean 全部非负”设为替代 G 的条件
（[fantasy-main-roll-simulator-v1.json:49-101](../../config/research/fantasy-main-roll-simulator-v1.json#L49-L101)、
[fantasy-main-roll-simulator-v1.json:146-157](../../config/research/fantasy-main-roll-simulator-v1.json#L146-L157)、
[main_roll_research_experiment.py:540-665](../../src/ti_predictor/fantasy/main_roll_research_experiment.py#L540-L665)）。

若 1000-state 研究为了计算预算只在 confirmation 的一个子集跑五模型，必须建立新的、
明确缩小范围的 coverage contract，不能静默绕过当前 guard。合规设计为：

1. Primary 跑全部 900 confirmation states；
2. 在看任何 Primary/G/T/H 得分前，用固定 salt 对 900 个 state hash 排序，冻结 sensitivity
   子集大小和成员；
3. 每个入选 state 完整运行 Primary、flattened、sharpened、repeat-suppressed 和
   correlated-multi-target，且每个模型内 G/T/H 配对；
4. 跨模型比较使用**同一个 sensitivity 子集**。不能拿 variant 的子集均值与 Primary 的
   全 900 均值直接比较；
5. 报告写成“在预注册 sensitivity 子集上”的模型稳健性。它不支持“900 个起点在五模型
   下全部验证”的说法；
6. 子集样本量、门槛和区间方法必须在运行前冻结。若该 sensitivity 结果参与最终策略 gate，
   子集必须来自 900 个 held-out states，而不能只用已看过的 100 个 development states。

五个模型共享同一 legal support，只改变 offer/Quality 权重、repeat-current 或 multi-target
相关性；现有测试逐 operation 验证了这一点
（[test_fantasy_main_roll_research_probability.py:78-92](../../tests/test_fantasy_main_roll_research_probability.py#L78-L92)）。
它们是合理性区间，不是五种“可能同样真实”的 Valve 官方概率。

## 6. 当前实现不能原样扩成 1000-state confirmation

以下是实现前必须处理的研究层兼容点，不是 Web 阻断：

1. **Manifest 类型不兼容**：当前 `FrozenStartingState` 强制一个文件、state hash、截图
   hash 和 OCR hash，并且 schema 只表达单一已观测起点
   （[main_roll_research_contract.py:50-66](../../src/ti_predictor/fantasy/main_roll_research_contract.py#L50-L66)）。
   Synthetic case 不能伪造 image/OCR provenance；应有独立 generator/index contract。
2. **Worker 固定单 state**：当前 worker context 为一个 state，一个 task 只是
   `(model_id, seed)`；1000-state runner 需要把 state identity 纳入 task 和 report
   （[main_roll_research_experiment.py:133-159](../../src/ti_predictor/fantasy/main_roll_research_experiment.py#L133-L159)）。
3. **Pairing key 太窄**：当前 `_paired_comparison` 用 `episode_seed` 建索引；新 runner 应
   使用 state/tape 复合身份，显式拒绝 hash/seed 错配。
4. **Sensitivity gate 语义不同**：当前 confirmation 只有“所有模型全量完成”或“不评价”
   两种状态；子集 sensitivity 需要新的 scoped gate，不能改旧报告含义。
5. **术语存在窄化问题**：`CONTEXT.md` 的 `Observed starting state` 必须是真实可见起点，
   而 `Starting-state coverage suite/stratum` 的当前正文仍写 `Expected Group score`、
   `Complete Group starts`。生成 case 不应命名为 Observed state；代码增加公开 contract 前
   应先把词汇扩展为 Main-safe 的 synthetic coverage case，或使用一个明确的研究内局部名称。
6. **隔离必须保留**：当前 research manifest 已冻结 `research_only=true`、
   `web_integration=false`、`runtime_pointer_writes=false`、`dota_client_control=false`
   （[fantasy-main-roll-simulator-v1.json:2-18](../../config/research/fantasy-main-roll-simulator-v1.json#L2-L18)）。
   新 runner/artifact 必须继承这些边界，且不能写现有 runtime pointer。

这些问题应通过新的 research-only generator/manifest/runner 解决，不应把 1000 个 synthetic
状态塞进当前 OCR 单起点字段，也不应修改 Web 来配合离线实验。

## 7. 预注册的停止条件与阻断项

### 可以直接继续，不构成阻断

- 没有 Valve 初始联合分布：用户已授权 synthetic uniform-legal 研究；只要不冒充总体
  概率，这不是阻断。
- actual 八队尚未导入：起点覆盖研究可以继续使用冻结 projected-derived roster panel；
  结论继续标记 projected，不得改名 actual。
- 1000 个随机 state 没有覆盖全部组合：状态空间决定了这不可能；如实报告 coverage count
  即可。

### 必须停止并修正后重启该阶段

- 任一生成 state 未通过 `validate_main_state`、出现重复 hash、缺少固定 provenance 或
  development/confirmation 成员在得分后变化；
- G/T/H 在同一 state/model 上没有相同复合 pairing identity，或不同 worker 数不能产生
  相同 canonical state/index/report hash；
- sensitivity 子集是在看过策略结果后选择，或五个模型没有在同一子集完整运行；
- development 之后改过 policy/config/code，却仍沿用旧 candidate hash；
- 打开 confirmation 后再修改 policy，并继续把同一 900 cases 当独立确认；
- 研究路径改动 Web、生产 advisor、`deploy/runtime/` 或现有 frozen research artifact；
- Rule snapshot、Main release、projected roster panel、generator spec 或 `as_of` 与 manifest
  不一致。

若纯随机生成后某个预先声明为“必须非空/必须平衡”的 readiness cell 为空，应按运行前
协议处理：要么停止并发布新的分层 generator version，要么保留原 1000 cases 并降低结论
范围；不能根据该 cell 的策略得分做定向补样。

## 8. 最终审计判断

| 问题 | 判断 |
| --- | --- |
| 能否生成 1000 个完全随机 Main 起点？ | 能。按合法支持均匀生成，并逐 state validation/hash。 |
| 这些起点是否代表真实玩家初始分布？ | 不代表；没有客户端/GC 联合分布证据。 |
| Quality/operation roll weight 能否直接用于初始状态？ | 不能据此断言；它们属于 reroll/board 字段，首次画面规则未知。 |
| 100/900 是否可用于开发/确认隔离？ | 可以，但必须先切分、后得分；confirmation 一旦打开就不能回填调参。 |
| G/T/H 是否应共享同一 tape？ | 应共享 keyed uniforms；不是强求不同动作得到相同 realized outcome。 |
| 五模型能否只跑子集？ | 可以，但要预注册同一个 held-out 子集、完整跑五模型，并缩小报告/gate 范围。 |
| 现有单起点 runner 能否原样使用？ | 不能；需要独立 research-only coverage contract/runner，旧 gate 语义保持不变。 |
| 是否存在需要用户补充 Valve 概率才能开始的阻断？ | 没有。synthetic coverage 可立即开始；不能把其平均值包装为总体概率。 |
