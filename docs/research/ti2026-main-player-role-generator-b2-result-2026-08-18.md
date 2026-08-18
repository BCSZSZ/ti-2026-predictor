# TI 2026 Main Player-role Generator B2：结果

## 决策

**B2 不通过发布门槛，不接入 Web、求解器发布包或运行时指针。**

B2 的经验 Copula 联合层确实修复了 B1 联合依赖误差的一大部分：盲留赛事块 Energy 相对 B1 改善 6.91%，TI 已消费面板改善 5.85%，而且两者的 Series-block bootstrap 上界均明确优于 B1。但它仍不如历史绝对模板 v1 的五人联合 Energy，80%/90% 区间继续明显欠覆盖，盲留队伍选择 regret 也仍差于 v1。因此不能把“比 B1 好”误写成“已经足够准确”。

## 冻结选择

- 候选：`4 empirical_mix × 4 latent_scale = 16`
- 通过 B1 Top2 CRPS 2% 保护线：12 个
- 选中：`empirical_mix = 0.90`、`latent_scale = 1.00`
- 选择发生在四个既定 tuning fold；其后未再改参数。

| tuning 指标 | B1 | B2 | B2 相对 B1 |
|---|---:|---:|---:|
| 五人联合 Energy | 6.6541 | 6.1987 | 改善 6.84% |
| Series Top2 CRPS | 1911.89 | 1936.63 | 恶化 1.29%，仍在 2% 护栏内 |
| 80% 覆盖率 | — | 70.18% | 目标 75%–85% |
| 90% 覆盖率 | — | 81.37% | 目标 86%–94% |

`latent_scale = 0.90` 的候选可得到约 11%–13% tuning Energy 改善，但 CRPS 恶化 2.19%–2.49%，均按预注册保护线淘汰，没有事后放宽。

## 盲留赛事块验证

最终合法面板包含 PGL Wallachia S7、ESL One Birmingham、PGL Wallachia S8、TI 2026 Europe Qualifier，共 186 条 Team-Game 联合记录、924 条 Series × 旗帜投影记录。

BLAST Slam VI 在读取任何 B2 成绩前因两名当前阵容选手在 cutoff 前无证据而排除；DreamLeague 28 因 cutoff 前不足 50 个完整 Series、无法同时满足总质量 100% 和单 Series 2% 上限而排除。两者都没有用未来数据回填，也没有放宽上限。

| 指标 | 结果 | 门槛 | 判定 |
|---|---:|---:|---|
| B2 Energy vs B1 | 6.2273 vs 6.6897，改善 6.91% | 点估计更好 | 通过 |
| B2 vs B1 Series-block 相对 Energy 损失 95% 上界 | -6.09% | ≤ 0% | 通过 |
| B2 vs v1 Series-block 相对 Energy 损失均值 / 95% 上界 | +5.74% / +7.67% | 点估计 ≤ 0%，上界 ≤ 1% | 失败 |
| B2 Series CRPS vs B1 | 1988.19 vs 1956.14，恶化 1.64% | tuning 护栏 2% | 护栏内 |
| B2 Series CRPS vs v1 | 改善约 12.40%；绝对改善 95% 下界 +197.74 | ≥ 2%，下界 > 0 | 通过 |
| 80% 覆盖率 | 70.56% | 75%–85% | 失败 |
| 90% 覆盖率 | 80.95% | 86%–94% | 失败 |
| Core/Mid/Support CRPS vs v1 | 三者均非劣 | 最多恶化 2% | 通过 |
| 队伍选择 regret | B2 2622.01；v1 2400.80 | B2 ≤ v1 | 失败 |

覆盖率不是“差一点”：盲留 B1 原为 74.35% / 84.63%，B2 反而降至 70.56% / 80.95%。这说明当前 Energy 主导的选择倾向了较窄分布；经验相关形状改善不能替代边际不确定性校准。

## TI 已消费面板诊断

TI 2026 已被用于发现 B1 问题，只能诊断，不能充当独立 confirmation。

| 指标 | B1 | B2 | 解释 |
|---|---:|---:|---|
| 五人联合 Energy | 6.6755 | 6.2852 | B2 改善 5.85% |
| B2 vs B1 相对 Energy 损失 95% 上界 | — | -4.57% | B2 的改善不是抽样噪声 |
| B2 vs v1 相对 Energy 损失均值 / 95% 上界 | — | +7.13% / +9.27% | 仍明确差于 v1 |
| Series Top2 CRPS | 2074.65 | 2074.80 | B2 相对 B1 +0.007%，基本不变 |
| 80% 覆盖率 | 72.29% | 70.35% | B2 更欠覆盖 |
| 90% 覆盖率 | 82.36% | 81.01% | B2 更欠覆盖 |
| 队伍选择 regret | 3894.27 | 3413.60 | B2 改善，但该面板非独立验证 |

## 真实训练集边界检查

用 TI diagnostic cutoff 重建的 B2 模型具有：

- 735 条条件残差来源、628 个稳定 Match、267 个 Series；有效来源行数 374.15。
- 最大单来源行质量 0.584%；同一 Match 双方合计最大 1.000%；单 Series 最大 2.000%。
- 256 个五人 × 18 Stat 生成样本全部 finite、非负，形状为 `256 × 5 × 18`。
- `copies_absolute_historical_stats = false`；经验行只提供条件边际被移除后的 Gaussian-rank 形状，并以 10% 独立平滑噪声打散。

## 对 B2 的解释

结果支持两个同时成立的结论：

1. B1 的低秩 Gaussian 联合层确实丢失了重要的五人相关结构；经验 Copula 能稳定找回约 6%–7% Energy。
2. v1 的优势不只来自“相关系数”。整场模板天然保留团队资源守恒、击杀/助攻/团战等非线性约束，而 B2 仍在 18 个独立边际反变换后组合数值。仅复制残差秩形状，还不足以复原这些物理一致性；同时 `latent_scale = 1.00` 造成明显欠覆盖。

因此下一步若继续，不应再微调 `empirical_mix`。更有价值的是预注册 B3，在不复制绝对历史 Game 的前提下显式建模团队总量与五人份额，并单独校准预测区间；B3 必须使用新的未消费验证设计，不能在这四块结果上反复调到通过。

## 可复现产物

- Artifact 根目录：`artifacts/research/main-player-role-generator-b2/2026-08-16-9d43f82cc8bc`
- Config SHA-256：`B45B5F3DF54BC3FFB63555035241AB4A170869FC222D488C14ACCE09DA7FF3E3`
- `selected-parameters.json` SHA-256：`2762ABD695151428616813C0FC8D5E657B36A9A28059A14147E221AFBBFBF21D`
- `confirmation-unused-event-blocks.json` SHA-256：`5009A56C4E822743CBE289094DA0D3D75C0F62F87ECDCC8A741C2085D3809D6B`
- `diagnostic-ti-consumed.json` SHA-256：`3807DB394607E6AFCFCBC0A7CC373EF890EC6EAAF21AD2107F25FAF7B117CBE3`

Web、正式求解器 release、runtime pointer 和用户当前发布包均未修改。

## 工程验证

- Ruff：`src` 与 `tests` 全量通过。
- Pytest：收集 356 项；355 通过、1 项按既有条件跳过，退出码 0。
- `git diff --check`：通过。
- 重跑前补入 `team_id` 后，前 5 个 tuning 候选与首次运行逐位一致；记录身份修正没有改变生成或评分。
- 既有用户修改 `docs/publication/ti2026-release-bundle-2026-08-11/MANIFEST.sha256` 未触碰。
