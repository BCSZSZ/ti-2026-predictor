# TI 2026 Main Fantasy 重随策略与模拟器调查

## 调查范围与结论状态

- 调查日期：`2026-08-14`
- 目标：为 Main Fantasy 的 30 次 Roll、三面五槽 War Banner 建立策略模拟研究边界；本报告不实装模拟器，也不修改当前顾问。
- 一手来源优先级：本机当前 Dota 客户端 > Valve 随客户端发布的帮助与数据配置 > 随客户端发布的 schema/protobuf 公共镜像 > 本项目历史实验。
- 本机当前客户端：`ClientVersion=6901`、`SourceRevision=10910149`、Steam build ID `24725046`。来源：
  `C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\steam.inf`、
  `C:\Program Files (x86)\Steam\steamapps\appmanifest_570.acf`。
- 当前 `steam.inf` SHA-256：
  `8E871DFF3C7445234F53C32FDC053995582288AB73DA13A7D16FFA2DD351E247`；当前
  `pak01_dir.vpk` SHA-256：
  `97BB73D9273E31FC5E875967E663FBFB85FF8A30D4AD7E206E4DE3EE56E8AFC1`。
- 从 build 6901 临时解出的 `fantasy_crafting.vdata`、`international_2026.eventdef`、
  `dota_english.txt` SHA-256 分别为
  `EBD26EC79C49C055BEECDF1D55AC0175B88DF0F0C22E6447A6B38BAEC5B5EFD9`、
  `81B8B5910FD8E339D8A8D141E4070D8A553534520D4BBA7143E04AD84CDAFB12`、
  `4A243EE1F9DC349BF05C9583EA78C5BBDCF25987A16FB4EA28419954AA364BE6`。
  三者与仓库中冻结的 build 6898 规则快照
  `data/raw/rules/20260813T132319Z-9728c506baf6/` 逐文件同 hash，因此下文用该可复现快照的行号引用。

本文使用三种结论等级：

- **已证实（exact support / exact rule）**：客户端帮助、数据字段或协议直接表达。
- **模型假设（model assumption）**：为了产生概率而声明的可替换假设，不是 Valve 后台真值。
- **未知（unknown）**：客户端和公开协议都未给出，必须通过敏感性模型或实际观测处理。

## 结论摘要

1. 现在已经具备做模拟器的**结构支持集**：Main 有三面五槽 Banner、30 枚 token、每次显示三个唯一且跨 Banner 共享的操作；Apply 和 Refresh 都消耗一枚 token并刷新整组操作。多格随机结果的联合支持仍需声明保守假设。
2. 现在还不具备宣称“真实出率”的证据。客户端给出了 20 个可出现操作的权重和五档 Quality 权重，但没有公开 GC 的抽样函数。协议反而证明当前操作列表和操作结果由 GC 返回。
3. 三种策略可以严谨定义为：
   - **一步贪心**：只最大化这一步后的终局估值，不计未来形状潜力；
   - **组合目标导向**：允许短期让分，以降低到高价值 Quality/Trait 目标的可达成本；
   - **剩余步数混合**：早期使用目标导向，晚期退化为一步贪心，切换阈值必须在独立训练种子上选择。
4. “最好的 Trait 形状”不是固定 Trait tier list。Benevolent/Vampiric 的价值取决于相邻槽的基础贡献，Fractal 同时依赖五档 Quality 全异，Friendly 是至少三枚的阈值，Unique 要求全 Banner 只有一枚。目标必须由完整 Banner 终局价值产生。
5. 应先做可复现的前向 Monte Carlo 模拟器和概率敏感性比较，再讨论更强求解器。既有 Group P5 的组合潜力求解器在有限正式样本中弱于一步贪心，而且没有积分未知未来 offer；Main 从三槽扩成五槽后，单 Banner 的 Quality×Trait 全枚举已从 `25^3=15,625` 增至 `25^5=9,765,625`，不能直接照搬。

## 1. Valve 已经明确的规则支持集

### 1.1 Period、槽位与 token

- `international_2026.eventdef:134-147` 把 Period 0 和 1 的 Roll grant 分别写成 `40` 与 `30`；
  `:1040-1063` 把 Period 1 标为 Main Event。
- `fantasy_crafting.vdata:445-534` 为 Core、Mid、Support 各定义五个按位置排列的槽位；第 4、5 槽分别要求更高 Tablet level。
- 当前英文帮助 `dota_english.txt:52444-52448` 规定：始终有三个唯一操作、三面 Banner 看到同一组操作、每次 Apply 只影响选中的 Banner、每次 Apply 消耗一枚 token 且替换全部操作；Coach title 可免费调整。
- `dota_english.txt:44947-44999` 给出了 Refresh、全色、随机一格、第一格、最后一格等操作目标的可见语义。

因此 Main 模拟状态中的三面 Banner 必须各有五个 Emblem；策略不能把 30 枚 Main token 当作 Group 的 40 枚，也不能把一个操作分别视为三个 Banner 的独立 offer。

### 1.2 Trait 的结构条件

当前 `fantasy_crafting.vdata:379-444` 定义五种 Shape behavior 和五档 Quality；对应帮助文案位于
`dota_english.txt:44935-44939,52442-52443`：

| Trait | 已证实条件/效果 | Main 五槽上的直接含义 |
| --- | --- | --- |
| Fractal | 全 Banner 的 Emblem Quality 互不相同才给自身 `+60%` | 五槽且只有五档 Quality，因此触发时 Quality 必为 `T1..T5` 的一个排列 |
| Benevolent | 给相邻 Emblem 的 stat value `+20%` | 应放在哪一格取决于两侧 Emblem 的基础贡献；边界与中间位置不同 |
| Vampiric | 自身 `+50%`，相邻各 `-10%` | 不能只看自身 `+50%`；要计入对高价值邻格的外部性 |
| Unique | 全 Banner 只有这一枚 Unique 时自身 `+30%` | 第二枚 Unique 会让两枚都失去该条件收益 |
| Friendly | Banner 至少三枚 Friendly 时，每枚 Friendly 自身 `+50%` | 三枚是门槛，四枚和五枚是否更好仍取决于被替换 Trait 的机会成本 |

“相邻”在可见五槽布局中最合理地建模为线性位置 `i-1/i+1`、首尾不环绕；现有公开资源没有把拓扑写成算术函数，因此应保留为**强推断**并纳入规则版本。Quality、Trait 和相邻效果如何合并仍沿用项目已记录的加法强推断，见
[`ti2026-fantasy-stacking-and-percentile.md`](./ti2026-fantasy-stacking-and-percentile.md)；模拟实验不能把这条推断升级成 Valve exact。

### 1.3 20 个可出现操作及其权重

`fantasy_crafting.vdata:535-890` 定义一个 `m_unOperationCount=3` 的 bucket。ID `1-8` 的权重为零，只是需要用户额外选择目标的模板；实际正权重操作为 `9-17,23-33`：

| 操作族 | ID | 权重 |
| --- | --- | ---: |
| 全部 Red / Blue / Green 的 Quality、Trait、Stat 重随 | `9-17` | 每个 `10` |
| 随机一格 Quality +1 | `23` | `4` |
| 随机两格 Quality +1、另一格 -1 | `24` | `8` |
| 随机 / 第一 / 最后 Red Quality | `25/26/27` | `10/6/6` |
| 随机 / 第一 / 最后 Blue Trait | `28/29/30` | `10/6/6` |
| 随机 / 第一 / 最后 Green Stat | `31/32/33` | `10/6/6` |

正权重总和为 `168`。五档 Quality 的 `(bonus, weight)` 是
`T1=(10%,10)`、`T2=(30%,20)`、`T3=(60%,10)`、`T4=(100%,5)`、`T5=(150%,2)`，见
`fantasy_crafting.vdata:412-444`。

SteamTracking 的仓库不是 Valve 的生产源码仓库，而是自动下载并导出 Valve 随游戏发布文件的公共镜像；其工作方式由
[`GameTracking README`](https://github.com/SteamTracking/GameTracking#how-it-works) 说明。本机证据可由同 build 的生成 schema 交叉核对：

- [`FantasyCraftOperationBucket_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftOperationBucket_t.h#L8-L12) 把 count 描述为从 bucket 给用户的操作数；
- [`FantasyCraftOperation_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftOperation_t.h#L11-L22) 把 `m_nRollWeight` 描述为把操作放进 roll board 时使用的权重；
- [`FantasyCraftingQualityData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingQualityData_t.h#L8-L17) 明确将 Quality 的 `m_nRollWeight` 描述为其被 roll 到的相对可能性；
- [`FantasyCraftingShapeData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingShapeData_t.h#L8-L17) 与
  [`FantasyCraftingGemData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingGemData_t.h#L9-L16)
  分别只有 Shape 列表和合法 Stat 列表，没有 per-Shape/per-Stat weight 字段。

这些 schema 证明字段语义和支持集，不是 GC 抽样实现本体。

## 2. 为什么“权重已知”仍不等于“概率已知”

公开 protobuf 表明：

- GC 返回的 UserData 包含当前 `available_rolls` 和各 Period 的 token 数，见
  [`CMsgDotaFantasyCraftingUserData`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/Protobufs/dota_gcmessages_client_fantasy.proto#L380-L399)；
- 客户端只向 GC 发送 `tablet_id / operation_id / extra_data`，GC 的响应再返回更新后的 UserData 和 TabletData，见
  [`PerformOperation`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/Protobufs/dota_gcmessages_client_fantasy.proto#L431-L464)；
- 纯 Refresh 也由 GC 响应新的 UserData，见
  [`RerollOptions`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/Protobufs/dota_gcmessages_client_fantasy.proto#L622-L639)。

所以客户端资源里没有下列服务端细节：

1. 三个唯一操作是按权重顺序无放回抽取、对子集按权重乘积抽取，还是等价/其他实现；
2. 新 offer 是否独立同分布，是否与前一 offer、执行的操作、Banner 或账号状态有关；
3. Quality 重随是否允许再次得到当前 Tier；
4. Trait/Stat 在各自五/六个合法值中是否均匀，是否排除当前值；
5. `One random Emblem` 是否在匹配槽中均匀；
6. 全色多格重随是每格独立抽取、共用一次结果，还是存在其他相关性；
7. Quality 已到 T5 或 T1 时，随机增减操作会先排除不可变化槽、clamp 成原值，还是重抽目标；
8. 初次生成 Main 第 4、5 槽时使用什么分布。

这些都必须保持 `unknown`。一次自己的 Main session 最多只有 30 次决策，且只观察被选择操作的结果；它足以发现重大矛盾，远不足以精确估计全部条件概率。

## 3. 建议的概率模型族

模拟器不应接受一个没有名字的“roll probability”。每个模型都应记录规则快照 hash、模型 ID、假设和随机种子。

### 3.1 Primary 候选模型（最佳支持估计，不是真值）

建议的 `client-weight-primary`：

1. offer 按 `m_nRollWeight` 顺序无放回抽三项；
2. Quality 按 `10/20/10/5/2` 抽取；
3. Trait、Stat 和随机目标在合法支持中均匀；
4. 重随可以重复当前值；
5. 多格属性结果条件独立；
6. Quality 增减目标均匀选取，越界 clamp；
7. 每次 replacement offer 与历史条件独立。

这与项目当前 Roll transition primary model 的语义一致，但第 3-7 项全是模型假设。

若 `w_i` 是操作权重、`W=168`，该模型下一个**有顺序**的 offer 概率为：

```text
P(i,j,k) = w_i/W × w_j/(W-w_i) × w_k/(W-w_i-w_j)
```

无序三项集合的概率是六种排列之和。由此得到的派生值只能标注为“Primary 模型条件下”：

| 项目 | 条件概率 |
| --- | ---: |
| weight 10 操作首抽 | `5.9524%` |
| weight 8 操作首抽 | `4.7619%` |
| weight 6 操作首抽 | `3.5714%` |
| weight 4 操作首抽 | `2.3810%` |
| 指定 weight 10 操作进入三项 offer | `17.7257%` |
| 指定 weight 8 操作进入三项 offer | `14.3741%` |
| 指定 weight 6 操作进入三项 offer | `10.9236%` |
| 指定 weight 4 操作进入三项 offer | `7.3762%` |
| offer 至少含一个 Quality / Trait / Stat 重随族 | 各 `69.5912%` |
| offer 至少含一个 Quality 增减操作（ID 23/24） | `21.0304%` |

Primary 模型下，Quality 重随的条件分布是：

| Tier | weight | 条件概率 |
| ---: | ---: | ---: |
| T1 | 10 | `21.2766%` |
| T2 | 20 | `42.5532%` |
| T3 | 10 | `21.2766%` |
| T4 | 5 | `10.6383%` |
| T5 | 2 | `4.2553%` |

如果真实实现排除当前 Tier，上表必须按剩余 Tier 重新归一化；当前证据不能选择两者之一。

### 3.2 必做敏感性模型

至少同时跑：

- `flattened-weights`：所有公开权重取平方根后归一化；
- `sharpened-weights`：所有公开权重平方后归一化；
- `no-repeat`：属性重随排除当前值；
- `correlated-multi-target`：用 `rho` 混合“多格共用一个结果”和独立抽取，且令 `rho<1` 以保留完整保守支持，用来对照 Primary 的独立假设；
- `support-only adversarial`：不赋概率，只报告每个动作的最坏/最好合法结果，作为安全基线。

不建议把“所有 20 个操作完全均匀”当主模型，因为客户端明确给了不同权重；它可以保留为故障注入或极端敏感性检查。

### 3.3 实际观测如何使用

以后若记录真实 session，每一步至少保存：

```text
client_build, rule_snapshot_sha256, observed_at_utc,
period, remaining_before,
all_15_emblems_before, offer_before,
chosen_action, realized_emblems_after, offer_after
```

用途应是离线比较候选模型的 predictive log loss、检查重复值/多格相关性和发现支持集错误。不得在同一 30-Roll session 中边看结果边改当前策略模型；该 session 只能作为以后版本的证据。

## 4. 模拟器的形式化

### 4.1 冻结上下文

一次实验上下文 `c` 必须固定：

```text
as_of_utc
Git commit
Rule snapshot + probability model ID
Main Solver Release / match-performance scenarios
eligible Team set and seeding mode (projected or actual)
random seed / experiment split
```

Main 当前仍可在 projected 队伍情景下模拟；正式八队和小组赛后原始数据更新后，再用同一实验协议重跑 actual。两批结果不可混成一个样本。

### 4.2 Markov 状态

```text
s = (B_core, B_mid, B_support, O, r)

B_role = five positioned Emblems
Emblem = (fixed color, Stat, Quality, Trait)
O = three distinct shared operation IDs
r = remaining Main Roll tokens, 0..30
```

`as_of`、概率模型与表现情景属于冻结上下文，不应在 episode 内变化。Team 和 Coach title 可免费调整，因此不必作为耗 token 的转移动作；每次估值或最终锁定时由同一 Terminal Banner/lineup evaluator 重新选择。

### 4.3 合法动作和转移

```text
A(s) = { Refresh }
     ∪ { Apply(role, operation_id) : operation is in O and applies to that Banner }
     ∪ { Stop }
```

`Stop` 不是客户端按钮，而是“保留未用 token 等待锁定”的分析动作，防止把最后一次只生成不可再使用 offer 的 Refresh 误认为有价值。

- `Apply`：按模型抽取该操作的合法 mutation outcome，只改变选中 Banner，`r -= 1`，再生成完整新 offer。
- `Refresh`：Banner 不变，`r -= 1`，生成完整新 offer。
- `Stop` 或 `r=0`：进入 terminal。

概率实现必须与结构支持分开。未证实多格联合规律前，声明完整 Cartesian product 为保守 next-state union；所有概率敏感性模型共享该 union，只改变概率。若以后实际证据证明某些组合不可能，应发布新的规则/支持版本，而不是在某个概率模型中悄悄删掉结果。

### 4.4 终局价值与风险

建议优化原始 Main Fantasy score，不优化 percentile reward：TI 2026 任意原始分到 percentile/reward 的完整映射仍未公开。

对一个最终 Banner 集 `B`：

```text
J(B; c) = max over legal Team choices and Coach titles
          E_match_scenarios[ raw Main Fantasy total | B, c ]
```

同时保留完整情景分布，报告：

- mean、median、P10/P90；
- lower-tail CVaR10；
- 相对基线的配对差值和置信区间；
- 每个 role 的贡献，避免总分掩盖某一 Banner 的严重退化。

## 5. 三种策略的可执行定义

### 5.1 策略 G：一步贪心（眼前最优）

对每个合法 Apply 计算：

```text
Q_G(s,a) = E_transition_model[J(B_after_one_action; c)] - J(B; c)
```

Refresh 和 Stop 的即时 Banner 改变量均为 `0`。选择最大 `Q_G`；若所有 Apply 都不为正则 Refresh，最后一枚 token 时可以 Stop。并列时先选更高的最坏结果/CVaR，再用固定 role、operation ID 顺序打破，保证复现。

该策略不估值新 offer，也不为将来 Trait/Quality 协同主动承受眼前损失，正好对应“选眼前最优解”。

### 5.2 策略 T：组合目标导向（靠近高价值形状）

不要定义“Fractal 最好”或“Friendly 最好”。先对每面 Banner 按当前 Stat 和位置生成有限的高价值 Quality/Trait target：

- Fractal：五档 Quality 全异，并选择哪些槽保留 Fractal；
- Friendly：至少三枚的门槛组合；
- Unique：恰好一枚且放在高价值槽；
- adjacency：把 Benevolent 的正外部性和 Vampiric 的负外部性按各槽基础贡献计价；
- 混合结构：只保留 terminal mean/CVaR、可达签名和路径成本上不被明显支配的候选。

对 target `z` 估计：

```text
gain(z)       = J(B with z; c) - J(B; c)
p_reach(z,r)  = 在声明概率模型和剩余 r 步内到达 z 的概率
T_hit(z)      = 到达 z 的 token 数分布（未到达记为 censored）
```

建议的形状潜力：

```text
Phi_r(B) = max_z { p_reach(z,r) × gain(z) }
```

动作选择使用潜力差，而不是静态 Trait 分数：

```text
Q_T(s,a) = E[ ΔJ + lambda × (Phi_(r-1)(B') - Phi_r(B)) ]
```

这样 Stat 操作仍能凭即时 `ΔJ` 被接受，Trait/Quality 操作则可以因为推进高价值 target 而接受短期小幅损失。`lambda`、候选半径和最大即时损失 guardrail 都是策略参数，必须先冻结再验证。

实际运行每次看到新完整画面后重新计算；不得因为之前花过 token 就对旧 target 产生 sunk-cost 偏好。为了避免 target 在相近候选间抖动，可只在当前 target 已到达、不可达或净潜力不再为正时切换，并把切换次数作为诊断指标。

### 5.3 策略 H：按剩余步数切换

最简单、可解释的版本：

```text
policy_H(s) = policy_T(s), if r > tau
              policy_G(s), if r <= tau
```

Main 的 `tau` 应只在训练 seeds 上从预注册网格选择，不能沿用 Group 的阶段阈值。也应测试一个更稳健的自适应开关：

```text
使用 target mode 当且仅当
r >= quantile_80(T_hit(best_target)) + safety_buffer
且 p_reach × gain > 0；否则进入 greedy mode。
```

固定 `tau` 是用户容易执行的版本；按完成时间分布切换是研究版。两者都属于同一个“剩余步数混合”策略族，最终只从独立验证集选择一个发布候选。

## 6. 为什么“最短 Hamming 距离”不够

两个 target 即使都只差一枚 Trait，实际到达难度也可能完全不同：

- 当前 offer 是否已有精确第一/最后格操作；
- 目标格是否只能由随机一格或全色操作命中；
- 重随结果是五选一还是 Quality 的非均匀五档；
- 全色操作会不会破坏已经完成的邻格；
- Refresh 会消耗一次 token，且最后一次 Refresh 产生的新 offer 已无法使用。

因此 target 距离至少应是“模型条件下 hitting-time 分布”，Hamming 距离只可用于第一阶段剪枝。现有 `CONTEXT.md` 的 `Reachability signature`、`Configuration target set` 和 `Target-directed continuation` 可以作为概念基础，但它们目前是 Group 语义；若将来实装 Main，必须保留独立的 Main policy/version，不能静默复用 Group 结论。

## 7. 策略比较实验设计

### 7.1 起点

分两层：

1. **当前实战条件**：OCR 确认的当前 Main 15 枚 Emblem、三个 offer 和剩余 token；它是固定条件，不需要猜 initial-state prior。
2. **泛化覆盖条件**：按 Quality 成熟度、Trait 协同成熟度、Stat 成熟度和 role 建立分层 synthetic states；其用途是压力测试，不宣称为真实起点频率。

若以后获得真实初始 Main 状态样本，再单独建立经验分布；在那之前不能用生成模型冒充真实初始分布。

### 7.2 公平比较

- 三策略在同一个 starting state、match-performance scenario、transition model 和配对随机 tape 上运行；
- 随机 tape 按 `episode/step/draw-kind` 键控，尽可能采用 common random numbers 降低方差；
- 策略看不到未来 tape，只能看到当前完整状态；
- hyperparameter 选择使用 train seeds，最终报告只用从未用于调参的 validation/test seeds；
- 多个 `tau/lambda/target radius` 的搜索必须做多重比较控制或独立 confirmation，不能选完最好结果再用同一批样本报置信区间。

### 7.3 主指标

建议预注册：

| 维度 | 指标 |
| --- | --- |
| 收益 | terminal raw Main score 的 paired mean difference、median、胜过 G 的 episode 比例 |
| 下行风险 | paired CVaR10 difference、P10、发生 material loss 的比例 |
| 目标行为 | target 完成率、T_hit、target 切换数、为 target 主动承受的即时损失 |
| token 效率 | Apply/Refresh/Stop 数、最后一枚 token 的无效 Refresh、每 1,000 分增益所需 token |
| 稳健性 | 在 Primary、flattened、sharpened、no-repeat、correlated 和 support-only 下首选策略是否改变 |
| 可解释性 | 每次动作可否还原为即时收益、target 推进或切换条件 |

建议只有在 Primary 的配对 mean 95% 单侧置信下界大于 0、相对增益达到事先冻结的 material threshold，并且 CVaR10 满足非劣门槛时，才说 T/H “优于” G。初始可讨论的门槛是 mean 至少 `+0.5%`、CVaR10 不低于 `-1%`，但这是产品决策，不是 Valve 规则，应在运行实验前由 owner 冻结。

### 7.4 诊断基线

除三种用户策略外，实验中保留但不作为第四个发布策略：

- Rate-agnostic safety：只 Apply 最坏合法结果也不降分的操作，否则 Refresh；
- short-horizon exact oracle：在 1-3 步小状态中穷举 offer 与 mutation，用于验证 simulator 数值；
- clairvoyant oracle：仅作为不可达上界，允许看到随机 tape，绝不能作为可执行策略或正常 regret 基准。

## 8. 从既有 Group P5 必须吸取的教训

[`P5 Branch-capped Reference Roll solver`](../reports/p5-branch-capped-solver-2026-08-06.md) 已经试过“即时终局值 + Quality/Trait 协同潜力”的方向。它提供三个负面证据：

1. 正式一小时门禁只完成 `7/216` 个 session；直接把三槽邻域逻辑扩到五槽会更慢。
2. 已完成样本中 solver 的 mean 比 one-step greedy 低 `4,394.87`；组合潜力不是天然优于贪心。
3. 其 1-3 步 oracle 固定了未来 offer，没有积分 20 个操作的下一 offer 随机性，不能回答本次用户提出的“不同选项和 roll 的概率”问题。

所以本轮顺序应是**前向模拟器 → 三策略比较 → 短 horizon 校验 → 再决定是否需要更强 planner**。不要先实现新的大搜索器，也不要把旧 P5 的 target multiplier 搬到 Main。

## 9. 建议实装计划（本报告未执行）

### 阶段 A：冻结研究合约

1. 以显式 UTC `as_of` 冻结 Main Solver Release、Rule snapshot、当前五槽状态和概率模型清单。
2. 写清每个 unknown 的 Primary 假设及敏感性变体。
3. 冻结三策略的公式、tie-break、超参数搜索空间、material threshold 和 train/test seeds。

交付物：一份只含 schema/config 的 simulator experiment manifest；不接 UI。

### 阶段 B：构建纯前向模拟器

1. 复用现有 Main 五槽合法支持与 realized transition 校验，不复制生产规则。
2. 新增独立 probability-provider 接口：offer distribution、mutation distribution、target selection、correlation。
3. 完整记录每个 episode 的状态、动作、随机 draw、结果与 provenance。
4. 同快照、模型、seed 必须逐 JSON 字节复现。

交付物：离线 episode runner；默认测试无网络。

### 阶段 C：统一终局 evaluator

1. 用当前 Main 发布包计算三 Banner 联合 Team matching、Coach 和 match scenarios。
2. 缓存相同 Banner state 的 terminal distribution；不要按 Emblem 独立相加 CVaR。
3. projected 与 actual 发布包分别实验、分别报告。

交付物：`state -> terminal distribution` 的纯接口和基准。

### 阶段 D：实现三策略插件

1. G：一步期望改善；
2. T：有限 target set、hitting-time potential、即时损失 guardrail；
3. H：固定 `tau` 与自适应完成时间开关的候选，训练后只保留一个；
4. 所有策略共享合法动作、终局 evaluator 和随机环境，不得各自实现一套规则。

交付物：三个只读 policy 函数；无 Dota 控制、无 Web 默认切换。

### 阶段 E：验证 simulator 本身

1. 所有概率和为 1，所有 sampled outcome 都在 exact support 内；
2. 不同概率模型 support 完全一致；
3. 1-3 token 小状态的 Monte Carlo 与枚举 exact 值在预注册误差内；
4. Main 三面五槽、共享 offer、Apply/Refresh token 消耗、最后一步和 Stop 边界均有测试；
5. 性能基准先通过，再扩大 episode 数；避免重演 P5 的 29 小时投影。

### 阶段 F：策略实验与修正循环

1. 先在 train seeds 调 `lambda/tau/target radius`；
2. 在独立 test seeds、所有概率敏感性模型和 starting-state strata 上跑配对实验；
3. 输出 point estimate、置信区间、CVaR、target 完成率和模型依赖，不只给胜负；
4. 若 T/H 未胜过 G，则保留 simulator 和负结果，不回填修改阈值；新策略必须新版本、新 seeds；
5. 只有通过门禁后，才讨论把一个策略作为 Web 的可选“模拟模式”，且不得静默替换当前屏幕建议。

### 阶段 G：真实出率核验

1. 在用户正常手动操作时，由 OCR 只读记录完整 before/action/after；不控制客户端。
2. session 结束后离线比较模型 likelihood 与支持集冲突。
3. 样本不足时只收窄极端模型，不发布“真实概率”；任何模型更新从下一冻结版本生效。

## 10. 当前尚需回答的问题

在写实现计划票据前，建议 owner 明确以下产品选择；它们不阻塞做 simulator kernel，但会改变策略结论：

1. 主要目标是最大化 raw expected score，还是愿意牺牲多少 mean 换 CVaR10？
2. “组合目标导向”允许单步最多损失多少即时价值？
3. Main projected 与 actual 都要作为正式比较范围，还是 projected 只做开发 smoke？
4. 当前真实五槽状态是否作为唯一实战起点保存，还是还要做通用策略手册？
5. 用户是否愿意在剩余 Main rolls 中保留逐步 OCR 观测日志，用于赛后核验出率？

在这些选择冻结前，合理的下一步是只实现可复现 simulator 和三种策略实验框架，不发布“最佳策略”。
