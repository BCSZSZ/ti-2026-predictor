# TI 2026 Main：1000 个合成初始状态策略覆盖研究

日期：2026-08-15
研究截止：`as_of=2026-08-13T13:23:17Z`
结论：**保留 `main-greedy-immediate-v1`（G），不修改 Web。**

## 1. 结论

本研究在 1,000 个确定性生成、逐项通过客户端规则校验的 Main 五槽起点上运行了冻结的
G/T/H。100 个 development 起点只验证管线；最终比较使用此前未见的 900 个 confirmation
起点。每个起点在 Primary 模型下只提供一个独立的 `state + Roll tape` 配对单位，G/T/H
共享 keyed random numbers。

结果不支持用 T 或 H 替代 G：

- T 的 900 状态平均终值比 G 低 `626.29`，相对为 `-0.7975%`，95% 双侧区间为
  `[-846.30, -406.28]`；明显劣于 G。
- H 的平均终值比 G 低 `60.28`，相对为 `-0.0768%`，95% 双侧区间为
  `[-263.23, 142.68]`；区间跨零，既不能证明优于 G，也达不到预注册的 `+0.5%` 最小收益。
- H 在固定的 100 状态 sensitivity 子集上五个 Roll 模型的均值差都为正，但这只是较小
  子集的敏感性结果，不能覆盖完整 900 状态 Primary 主分析的失败。
- T 与 H 都未通过全部冻结 gate，最终选择是 G fallback。该选择不会自动写入 Web；当前
  Web 本来就继续使用 G 类的一步即时优化，因此无需生产改动。

完整机器可读结果见
[`final-report.json`](../../artifacts/research/main-roll-starting-state-coverage/20260813T132317Z-8a6fc98a8308/final-report.json)。

## 2. 研究问题与解释边界

本研究回答的是：**在当前冻结规则、projected Main release 和人为定义的 uniform-legal
起点设计下，G/T/H 对起点变化是否稳健？**

它不回答“真实玩家平均能提高多少”。客户端证据能够确定三面 Banner、每面五槽、槽色与
合法 Stat、五档 Quality、五种 Trait、三个 distinct offer 以及 30 Rolls，但没有公开玩家
Main 初始画面的联合分布。尤其是 Main 的前三槽由 Group 带入；本研究把 15 个槽全部独立
生成，有意忽略玩家历史相关性，只能作为宽覆盖压力测试。规则与分布边界的独立审计见
[`ti2026-main-1000-synthetic-starting-state-coverage-audit-2026-08-15.md`](./ti2026-main-1000-synthetic-starting-state-coverage-audit-2026-08-15.md)。

本机客户端 Rule snapshot 绑定 build `6898:10904633`，原始证据包括
[`fantasy_crafting.vdata`](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/fantasy_crafting.vdata)
和
[`international_2026.eventdef`](../../data/raw/rules/20260813T132319Z-9728c506baf6/scripts/events/international_2026.eventdef)。
客户端 schema 仅说明 operation/Quality 的 reroll 权重字段，并未给出初始联合分布；可核对
SteamTracking 的
[`FantasyCraftOperation_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftOperation_t.h#L11-L22)
与
[`FantasyCraftingQualityData_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/00c9adab9729cb68e1b12d169f5a27e066c7f4b1/DumpSource2/schemas/client/FantasyCraftingQualityData_t.h#L8-L17)。

因此文中的总体均值是 `synthetic coverage design average`，不是玩家总体 Expected Main
score，也不是 Valve 后台概率估计。

## 3. 得分前冻结的设计

### 3.1 起点生成

- `state_index=0..999`，每个 index 使用独立 SHA-256 keyed generator；执行顺序和 worker
  数不影响状态。
- canonical role 顺序为 `core, mid, support`，每面五槽。
- 每槽 Stat 在该槽色的六个合法 Stat 中等权选择；Quality 在 T1–T5 中等权选择；Trait
  在五种合法 Trait 中等权选择。
- 初始 offer 从 20 个正权重 operation 中等权、无放回、按顺序选择三项。
- `remaining_rolls=30`；每个状态通过 `validate_main_state`。
- 1,000 个 canonical state SHA-256 全部唯一。

生成 contract 见
[`fantasy-main-starting-state-coverage-v1.json`](../../config/research/fantasy-main-starting-state-coverage-v1.json)，
实现见
[`main_roll_research_states.py`](../../src/ti_predictor/fantasy/main_roll_research_states.py)。

### 3.2 隔离、配对与样本量

- indices `0..99`：development/pipeline only；未用于调 G/T/H 参数。
- indices `100..999`：900 个 held-out confirmation states。
- G/T/H 在同一 `(state, probability model)` 使用相同 episode seed 与 keyed uniforms。
- Primary 在全部 1,000 个状态运行；正式 gate 只读取 900 confirmation states。
- 在看任何得分前，以固定 salt 从 900 状态中按 SHA-256 rank 选择 100 个 sensitivity
  states；这 100 个状态完整运行五模型。Primary 已包含在主阶段，因此附加运行四模型。
- 每个 terminal evaluation 内的 224 个 projected-derived roster、1,792 条 inner path 是同一
  冻结估值面板，不被冒充为额外独立样本。
- projected 与 actual 语义不混合；本报告仍为 `eligibility_mode=projected`。

### 3.3 冻结身份

| 项目 | SHA-256 / 身份 |
| --- | --- |
| Coverage manifest file | `dc54ffc2aeb1e05565a4ff4a32b1d40e5fe037d0bb6948dfa1340cb555b7d206` |
| Coverage manifest semantic | `8a6fc98a830826b50675ab4804d69c8c37368cb0f5dad7aa1a3da9a96d9470cb` |
| 1,000-state index | `48346486905dc51d398b0d9ad6312b8cbfc441efb27579c3b59afaa2c4b04278` |
| Base research manifest | `b7ae27c63109d5ea9e56c2fc33fca5247db0817c4f02d1516a2c6075f81adcec` |
| Main release | `94c00919f01395dae7f1eb371db0156cc8225c5b9aa9f5b02ccb9083d6d714c9` |
| Source version | `876cdb7c9c3e3ec11bffb570a0aac0f2d83df8ba-dirty-96ae9a93faeb` |
| Final report | `cfaf48d897286f5ac6a642624db63ffbf196ca1ea2f78f8a15ba800de6128a45` |

## 4. 起点覆盖诊断

900 个 confirmation states 的预声明边际分层为：

| 覆盖维度 | 样本数 |
| --- | --- |
| 平均 Quality：低 / 中 / 高 | `228 / 430 / 242` |
| 初始 offer 无 / 有直接 Quality increment | `651 / 249` |
| 条件 Trait-ready Banner：0 / 1 / 2–3 | `140 / 369 / 391` |
| 初始 terminal value rank quartile | 每组 `225` |

全部预声明类别都达到 gate 的最小 `n=60`，因此没有空格、后验补样或降级解释。完整状态和
分层标签见
[`starting-states.jsonl`](../../artifacts/research/main-roll-starting-state-coverage/20260813T132317Z-8a6fc98a8308/starting-states.jsonl)。

## 5. Primary：900 状态结果

### 5.1 策略绝对结果

| 策略 | Terminal mean | Terminal median | Mean CVaR10 | 平均使用 Rolls |
| --- | ---: | ---: | ---: | ---: |
| G — `main-greedy-immediate-v1` | `78,530.68` | `78,655.07` | `66,297.81` | `29.643` |
| T — `main-target-shape-distance-v2` | `77,904.39` | `77,786.34` | `65,790.91` | `30.000` |
| H — `main-horizon-hybrid-v2` | `78,470.41` | `78,517.17` | `66,263.41` | `29.652` |

### 5.2 配对差值（challenger − G）

| 指标 | T − G | H − G |
| --- | ---: | ---: |
| Mean difference | `-626.29` | `-60.28` |
| 95% 双侧区间 | `[-846.30, -406.28]` | `[-263.23, 142.68]` |
| 95% 单侧下界 | `-810.87` | `-230.55` |
| Relative mean gain | `-0.7975%` | `-0.0768%` |
| Mean CVaR10 difference | `-506.91` | `-34.40` |
| Win rate | `38.56%` | `35.22%` |
| Tie rate | `3.22%` | `27.78%` |

H 的 tie rate 较高符合其设计：后段会回到 G，且部分起点两者采取相同行为。但剩余差异既
没有正的置信下界，也没有材料性增益，因此不能把“接近 G”改写成“优于 G”。

## 6. 五模型 sensitivity

下表是固定 100-state sensitivity 子集上的 challenger − G mean difference：

| Roll probability model | T − G | H − G |
| --- | ---: | ---: |
| `client-weight-primary-v1` | `-84.29` | `+493.23` |
| `flattened-weights-v1` | `-573.28` | `+165.16` |
| `sharpened-weights-v1` | `-700.87` | `+133.20` |
| `repeat-suppressed-v1` | `+71.09` | `+346.65` |
| `correlated-multi-target-v1` | `-333.24` | `+357.38` |

T 在五模型中的四个为负，直接失败。H 在这个预注册子集的五模型都为正，说明 H 的表现对
Roll 模型扰动并非明显脆弱；但 Primary 子集的 `+493.23` 与完整 900 状态的 `-60.28`
方向不同，也说明 100 状态不能代替主样本。冻结顺序要求以完整 900-state Primary 为主，
因此 H 仍然失败。

## 7. Gate 结果

预注册 gate 要求 challenger 同时满足：Primary mean 的 95% 单侧下界大于 0、相对收益至少
0.5%、CVaR10 非劣、七个 roster fold 非劣、所有合格起点 strata 非劣，以及五模型均值
非负。

| Gate | T | H |
| --- | --- | --- |
| Primary mean CI > 0 | 失败 | 失败 |
| Relative mean gain ≥ 0.5% | 失败 | 失败 |
| CVaR10 noninferiority | 失败 | 通过 |
| Every roster fold noninferior | 失败（fold 1、3–7） | 通过 |
| Every eligible starting-state stratum noninferior | 失败 | 失败 |
| Nonnegative mean in every sensitivity model | 失败 | 通过 |
| 最终 | **失败** | **失败** |

H 唯一失败的起点 robustness 类别是
`conditional-trait-ready-banner-band=none`（`n=140`）：mean difference `-363.97`，95% 单侧
下界 `-933.75`；这超出 1% 非劣容忍。这个结果只能作为下一轮研究假设，不能在已经看过的
900 状态上发明“无 readiness 时切 G”的新策略再称为独立确认。

T 几乎在所有边际类别都失败；只有最低 initial-value quartile 达到 1% 非劣，但其 mean
difference 仍为 `-250.70`，不构成选择 T 的证据。

## 8. 可复现性与完整性

- 一 worker 与两 worker 的真实终端 smoke：8 个 task/episode 管理文件逐字节一致；报告除
  worker 数外语义一致。
- Development：100 tasks、300 episodes，`995.9s`；所有文件哈希通过，未评价 gate。
- Primary confirmation：900 tasks、2,700 episodes，`9,743.8s`；900 个 state hash 与 seed
  均唯一，索引恰为 `100..999`。
- Additional sensitivity：400 tasks、1,200 episodes，`3,552.9s`；四模型各 100 个 state，
  成员与预注册子集完全一致。
- 正式 bundle 合计 1,400 task records、4,200 episode traces；
  [`checksums.json`](../../artifacts/research/main-roll-starting-state-coverage/20260813T132317Z-8a6fc98a8308/checksums.json)
  管理 5,608 个文件、`447,079,689` bytes。独立复核为 5,608/5,608 匹配。
- `final-report.json` 自哈希复核通过。
- 全量软件回归收集 298 项测试：297 passed、1 个既有 skip；全仓 Ruff 与
  `git diff --check` 通过。
- Web、Main advisor UI、共享 CLI、`streamlit_app.py`、`local_ocr_app.py` 以及 Group/Main
  runtime pointer 的七个受保护 SHA-256 全部等于研究前基线。

研究 runner 只写
`artifacts/research/main-roll-starting-state-coverage/`，未写 `deploy/runtime/`，未控制 Dota，
也未被 Web、OCR、advisor 或共享 CLI 引用。执行说明见
[`main-roll-strategy-research.md`](../runbooks/main-roll-strategy-research.md)。

## 9. 决策与后续边界

当前最终研究决策是：

```text
selected_policy_id = main-greedy-immediate-v1
status             = fallback
Web change          = none
```

如果继续研究，最有信息价值的方向不是在同一 900 状态上直接部署一个后验切换器，而是：

1. 把“conditional Trait readiness 为 none 时使用 G、其余状态考虑 H”仅登记为新假设；
2. 使用新的 policy ID、显式状态特征和完全不重叠的新起点/新 Roll tape holdout；
3. actual 八队形成后，用独立 actual manifest 做最小 G-vs-candidate 验证；projected 与 actual
   结果继续分开保存。

在这些新证据出现前，G 是唯一通过安全基线要求的策略。
