# TI 2026 Main Player-role Generator B2：冻结实验协议

## 结论

B2 保留 B1 已选定的选手—定位边际模型、比赛时长模型和全部证据治理规则，只替换五人联合残差层。B2 使用带 Game/Series 权重上限的历史条件残差形状，并与平滑因子噪声混合；它不复制任何历史 Game 的五人绝对 Stat 向量。

本文在读取 B2 指标前冻结参数网格、选择规则、验证块与通过门槛。TI 2026 面板已经被用于发现 B1 的联合 Energy 问题，因此在 B2 中只能作为诊断，不能再次声称是独立 confirmation。

## 固定不变的 B1 部分

- `ridge_alpha = 1.0`
- `recent_effective_sample_constant = 8.0`
- `recent_residual_cap_sigma = 0.5`
- 平滑联合残差底座：`factor_rank = 12`、`covariance_shrinkage = 0.25`
- 参数证据上限：单 Game 2%、单 Series 5%
- 联合残差上限：单 Game 1%、单 Series 2%
- 所有训练、特征与回测继续接受显式 UTC `as_of`，fold 内不得读取 cutoff 之后的信息。

## B2 候选

经验残差与平滑因子残差独立抽样，使用方差保持混合：

`z = latent_scale × (sqrt(empirical_mix) × z_empirical + sqrt(1 - empirical_mix) × z_factor)`

- `empirical_mix ∈ {0.25, 0.50, 0.75, 0.90}`
- `latent_scale ∈ {0.90, 1.00, 1.10, 1.20}`
- 共 16 个候选。

经验样本只贡献条件边际被移除后的 Gaussian-rank 残差形状。`empirical_mix < 1` 保证生成向量几乎必然不等于任一训练残差行；更不会等于历史绝对 Stat 向量。

## 参数选择

只使用 B1 原四个 tuning fold：DreamLeague 29、BLAST Slam VII、EWC 2026、1win Series Dota 2 Summer。主指标为五人联合 Energy，附加两个先验约束：

1. 聚合 Series Top2 CRPS 相对冻结 B1 不得恶化超过 2%。
2. 80% 与 90% 区间覆盖率依次以距离目标区间 `[75%, 85%]`、`[86%, 94%]` 的总距离作为第二选择准则。

满足 CRPS 约束的候选中，依次选择联合 Energy 最低、覆盖距离最低、`empirical_mix` 较低、`latent_scale` 更接近 1 的候选。若没有候选满足 CRPS 约束，则实验停止，不得用事后放宽门槛选型。

## 未查看 B2 结果的固定验证面板

以下四个赛事块仅在参数选择完成后一次性运行。每个块仍是滚动时间回测：训练数据严格截止于 `train_as_of`，之后到 `test_end` 的对应联赛作为 holdout。

| fold | league_id | train_as_of (UTC) | test_end (UTC) |
|---|---:|---|---|
| PGL Wallachia S7 | 19435 | 2026-03-07T08:00:31Z | 2026-03-15T20:24:45Z |
| ESL One Birmingham | 19422 | 2026-03-22T11:59:55Z | 2026-03-29T19:34:21Z |
| PGL Wallachia S8 | 19543 | 2026-04-18T07:00:07Z | 2026-04-26T14:11:02Z |
| TI 2026 Europe Qualifier | 19892 | 2026-06-21T08:02:15Z | 2026-06-28T17:21:39Z |

BLAST Slam VI 原计划作为第六块，但在读取任何 B2 指标前完成的可运行性检查证明：其 `2026-02-03T08:57:33Z` cutoff 之前，两名当前 Main 阵容选手没有合法历史证据。B1/B2 都无法在不使用未来数据的情况下拟合，因此按缺失证据原因预先排除；不得把未来样本回填，也不得在看到 B2 结果后恢复或替换该块。

DreamLeague 28 随后也在读取任何 B2 指标前因硬约束不可行而排除：其 cutoff 前完整联合样本不足 50 个 Series，无法在总概率为 100% 时同时满足单 Series 2% 上限。该上限不因早期数据较少而放宽。

这四块是“盲留赛事块验证”，不是晚于 tuning 赛事的纯前向 confirmation；原因是当前没有尚未发生且能在客户端截止前取得真值的职业赛事。它们的每个 fold 都保持时间因果，但整体面板用于独立结果核对而非冒充未来验证。

## 固定通过门槛

- 相对历史绝对模板 v1：Series Top2 CRPS 改善至少 2%，95% 单侧区间下界大于 0。
- 相对 v1：联合 Energy 点估计更好，Series-block bootstrap 的 95% 单侧相对损失上界不超过 1%。
- 相对冻结 B1：联合 Energy 点估计更好，95% 单侧相对损失上界不超过 0%。
- 80% 区间覆盖在 75%–85%；90% 区间覆盖在 86%–94%。
- Core、Mid、Support 各自 CRPS 相对 v1 最多恶化 2%。
- 队伍选择 regret 不劣于 v1。

任一门槛失败都只允许报告失败和诊断，不允许接入 Web、求解器发布包或运行时指针。
