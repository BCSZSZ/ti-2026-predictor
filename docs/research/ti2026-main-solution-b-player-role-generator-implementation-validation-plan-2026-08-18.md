# TI 2026 Main 方案 B：Player×Role 条件生成模型实装与验证计划

- 计划日期：2026-08-18
- 生产边界：研究专用；通过门槛前不得修改 Web、solver release 或 runtime pointer
- 最终客户端锁定：`2026-08-20T02:00:00Z`（日本时间 2026-08-20 11:00）
- 目标：替换“直接重用一个历史 Game 的五人绝对 Stat 向量”的研究抽样层；保留完整双败路径、BO3/BO5、Series Top 2 与 Period 最佳 Series 逻辑

## 1. 能证明什么，不能证明什么

未来 Main 的真实表现尚未发生，因此不能在赛前数学证明方案 B 一定比所有方法更准。可以证明两类性质：

1. **结构性质**：无时间泄漏、单 Game/Series 的参数影响受上限约束、不直接复制一局绝对表现、相同快照与 seed 可复现。
2. **经验性质**：在严格晚于训练数据的冻结比赛上，方案 B 的 proper scoring rule、校准、Series Top-2 分布和选择 regret 优于或不劣于当前联合模板基线，并且差异的 Series-block 置信区间通过预注册门槛。

只有两类证据同时通过，才可称为“相对当前模型更准确、更客观”；仍不得称为现实真值或未来保证。

## 2. 为什么数据足够启动

以 `2026-08-16T15:31:30Z` 为截止，当前 Main evidence 中：

- 全目录 45,056 场；Fantasy 正权重比赛 4,555 场；
- `fantasy_performance_samples.parquet` 有 23,080 条 player-game；
- 八队当前 40 名选手共有 7,172 条正权重 player-game；
- 单名选手最少 99 局、中位数 184 局、最多 222 局；
- 现有方法因要求“五名当前阵容选手同局全部完整”，最终只保留 863 个联合 Game 模板。

方案 B 在拟合个人长期表现时使用完整的个人样本，不再因为队友缺失而丢弃该选手的有效历史；联合波动层再使用完整 team-game 残差。

## 3. 预测对象

模型的基本输出不是一个预先合成的 Fantasy 总分，而是未来每局的：

```text
5 名当前阵容选手 × 18 项原始 Fantasy Stat
```

随后才按客户端规则执行：

```text
原始 Stat -> Valve Stat 得分 -> 玩家旗帜倍率
-> Core 两人平均 / Mid 单人 / Support 两人平均
-> Series 最高两局之和 -> Main 阶段最佳 Series
```

因此模型训练与具体旗帜分离。同一份未来 Stat 面板可以给任意合法旗帜重评分，不需要为每位用户重新拟合。

## 4. 方案 B 的生成公式

对选手 `p`、Fantasy 位置 `r`、Stat `s`、未来 Game 条件 `x`：

```text
η[p,r,s,x]
= Role 总体基线
 + Player×Role 长期偏差（分层收缩）
 + Current-Team 偏差（分层收缩）
 + 胜负 / 连续对手强度 / BO / Series 比分与局序修正
 + 有界近期状态修正
```

最终生成：

```text
future_stat_vector = inverse_marginals(η, shared_joint_residual)
```

### 4.1 长期 Player×Role 基线

- 使用稳定 player ID 与每局已记录 role；名字只显示，不连接。
- 使用 2026 正权重 Fantasy evidence，并遵守 roster interval、provenance 与显式 `as_of`。
- 现有 tier、patch、60 天半衰期、当前精确版本 1.5 倍和 TI 小组赛/突围赛 1.5 倍继续作为 evidence weight；不另行重复施加同一种权重。
- Player 效应向 Role 总体收缩，样本少或有效样本量低时自动更接近 Role 基线。
- 单一 Game 的归一化参数权重上限预注册为 2%，单一 Series 上限为 5%；超出质量重新分配而不是删除真实极端表现。

### 4.2 近期状态修正

- 近期修正来自长期模型残差，不直接再算一次近期均值。
- 使用 60 天半衰期的 residual EWMA；收缩系数为 `n_eff / (n_eff + κ_s)`。
- `κ_s` 和最大修正幅度只在 tuning folds 选择；最大幅度候选为该 Stat 条件残差标准差的 `0.25/0.50/0.75`。
- 小样本修正自动趋近零，防止三四局“近期爆发”覆盖全年基线。

### 4.3 场景修正

未来路径已经生成以下条件，因此可以合法使用：

- 单局胜负；
- 连续 Team-strength 胜率，而不是 `<40/40–60/>60` 三档；
- BO3/BO5；
- 已抽到的 Series 最终长度/比分与当前 Game 局序。

这些修正使用 ridge/empirical-Bayes shrinkage，并在标准化尺度上有界。没有足够样本时修正趋近零，不再硬筛到只剩三条 Series。实际比赛时长不可提前知道，必须先由同一场 Game 的共享 pace/duration 层生成；端到端测试不得喂入真实未来时长。

### 4.4 边际分布

- 所有 Stat 保持 `null`，不得补零。
- 零值较多的事件 Stat 使用 hurdle 结构：先生成是否发生，再生成正值大小。
- 非负计数/连续 Stat 在 `log1p` 或相应有界尺度建模，逆变换后执行非负、整数及客户端 cap 约束。
- 最终一律回到原始 Stat，再调用现有 `score_stat`，不得直接伪造客户端得分。

### 4.5 联合残差

不能独立抽 90 个 Stat。对历史完整 team-game：

1. 用上述条件均值去掉 Player、Role、结果、对手和格式效应；
2. 把五人 18 Stat 与 duration 的残差转成按 Role/Stat 标准化的秩残差；
3. 拟合低秩共享 Game pace/team factor，加上 Role/player-level idiosyncratic residual；
4. 因子数从固定小网格 `3/5/8/12` 中只按 tuning folds 选择；协方差使用 shrinkage；
5. 从平滑后的 factor/residual 分布生成新残差，而不是复制某个历史 Game 的绝对 Stat 向量。

这样保留“长局同时抬高若干经济/战斗 Stat”“五人资源分配相关”等主要结构，同时同一历史 Game 不再携带某队的绝对高分反复进入未来。方案 B 仍不是双方十人的完整守恒模型；跨队击杀/死亡等完全一致性属于方案 C。

## 5. 与当前 Main 双败模拟的连接

不改变：

- 官方八队双败树的 16,384 条完整路径；
- 每条路径的精确 Team-strength 概率；
- BO3/BO5 合法比分序列；
- BO3 与 BO5 都取 Series 最高两局；
- 每队在整个 Main 取最佳 Series；
- 在未来揭晓前固定 Team 选择。

只替换：

```text
旧：选择历史 Series -> 有放回选择历史完整五人 Game 绝对向量
新：条件 Player×Role 均值 -> 共享联合残差 -> 合成未来五人 Game
```

## 6. 预注册时间回测

禁止随机拆分 Game。采用 rolling-origin/event-block：

### Tuning folds

依次用测试赛事开赛前的全部可用数据训练，并在其后完整赛事块测试。候选块包括：

- DreamLeague Season 29；
- BLAST SLAM VII；
- Esports World Cup 2026；
- 1win Essence II。

它们只用于选择 shrinkage、近期修正上限、联合因子数和残差尺度。

### Frozen confirmation

- 最终确认块为 TI 2026 小组赛与突围赛；
- 训练截止固定在 TI 首场之前；
- 在看到方案 B 的确认结果前冻结代码、超参数选择规则、指标、seed 和门槛；
- 确认完成后才用包含 TI 的全量 evidence 重拟合 Main 最终模型。

当前已经看过 TI 的原始比赛，但尚未用它调方案 B 参数，因此它可以作为预注册后的 confirmation；报告必须明确它不是完全盲化的外部数据集。

## 7. 比较对象和评价层次

相同 folds、相同 `as_of`、相同路径/随机数比较：

1. 当前 v1 条件化联合模板 bootstrap；
2. 简单 Player×Role 60 天 EWMA；
3. 方案 B；
4. 方案 A 只作为可选安全对照，不参与 B 的参数选择。

### 7.1 单 Stat / 单选手

- 条件均值：MAE 与归一化 RMSE；
- 完整预测分布：CRPS；
- 50%/80%/90% 区间覆盖率与 PIT 校准；
- 稀有事件另外报告 Brier score。

### 7.2 五人联合 Game

- Energy score；
- residual correlation / covariance 误差；
- Game duration、胜负、对手强度分层后的分布覆盖；
- 合法值与 provenance 检查。

### 7.3 Series 和最终选择

- 用测试期真实 Series 的最高两局得分计算 Series-level CRPS；
- 对 hash 固定的合法 Banner 面板计算 Team 排名和选择 regret；
- 用户自己的 Banner 只在全部门槛通过后求解，不参与调参或模型选择。

这里的 Banner 面板只是廉价的下游投影回归测试，不是为了重新估计 Stat，也不需要单独手工制作 64–100 张画面。

## 8. 通过门槛

以下门槛在运行 B confirmation 前冻结：

### 准确度主门槛

1. 相对当前 v1，Series Top-2 Fantasy score 的平均 CRPS 至少改善 2%；
2. 以 Series/event 为 block 的配对 bootstrap 中，改善的 95% 单侧置信下界大于 0；
3. 五人联合 Energy score 点估计更好，且 95% 上界不得比 v1 差 1% 以上；
4. End-to-end Team-choice regret 不劣于 v1；若样本不足以证明改善，必须标记 unresolved，不能冒充通过。

### 校准护栏

- 80% 区间实际覆盖在 75%–85%；
- 90% 区间实际覆盖在 86%–94%；
- Core/Mid/Support 任一角色聚合 CRPS 不得恶化超过 2%；
- 稀有 Stat 单项失败可以降级为 warning，但若它足以翻转 Team 选择则整体失败。

### 稳健性硬门槛

- leave-one-Game 后任一目标 Team×Role Mean 变化不超过 1%；
- leave-one-Series 后不超过 2%；
- 原第一名领先第二名超过 1% 时，删除任一单 Game/Series 不得翻转第一；
- 报告参数权重、残差来源 ESS、最大 Game/Series influence；
- 三个 confirmation seed 的选择一致，且 Monte Carlo 标准误低于对应 Mean 的 0.2%。

### 治理门槛

- 所有读取都接受显式 UTC `as_of`；
- 不使用 `as_of` 后比赛、阵容或规则；
- 训练、tuning、confirmation 的 Series ID 不重叠；
- manifest 记录 Git、配置、数据/规则 SHA、fold、seed；
- 同一输入生成相同 JSON；
- 研究模块没有 Web/consumer import path。

任一准确度主门槛或稳健性硬门槛失败，方案 B 不接入正式求解器。不得为了让当前个人推荐“看起来合理”而在 confirmation 后改阈值；改动必须升版本并使用新的未重叠确认集。

## 9. 为什么能解决 Falcons 单模板翻转

当前 v1 中，历史 Match `8944611964` 同时有很高的抽样概率和很高的当前 Core Banner 得分；移除它使 Falcons Mean 下降 8.084%，并由第一跌到第四。

方案 B 中该 Game：

- 只作为 Player×Role 参数估计的一个受 2% 上限约束的观测；
- 它的绝对 5×18 Stat 向量不会被复制到未来；
- 它最多参与估计一个标准化联合残差/pace 形状；
- 参数和残差两个层面都要通过 leave-one-out 硬门槛。

因此可以在结构上证明“一局不能再以旧方式直接决定 Falcons 的绝对未来分布”；是否因此提高真实预测准确率，则由冻结时间回测决定。

## 10. 实装顺序

1. **冻结研究契约**：配置、fold、指标、门槛、seed、候选超参数；保存 semantic hash。
2. **构建 individual evidence table**：稳定 ID、role、roster interval、18 Stat、result、opponent strength、BO、series context、权重与 provenance。
3. **实现边际层**：长期分层基线、近期/场景有界修正、hurdle/变换与逆变换。
4. **实现联合层**：duration/pace、低秩共享因子、残差 shrinkage 和合法值修复。
5. **接入研究 bracket adapter**：替换 v1 的 Game-template draw；其余路径与评分不变。
6. **运行 tuning folds**：只选择预注册候选，不看用户 Banner。
7. **冻结模型并运行 TI confirmation**：计算 proper scores、校准、regret、置信区间。
8. **运行 influence suite**：leave-one-Game/Series、ESS、最大影响、seed/MC 误差。
9. **仅在全部硬门槛通过后**：用截至 2026-08-16 的全量数据重拟合，离线求解用户最终 Banner。
10. **另行决策发布**：当前任务不更新 Web、Streamlit、GitHub release 或 runtime pointer。

## 11. 建议文件边界

- `config/research/fantasy-main-player-role-generator-v1.json`
- `src/ti_predictor/fantasy/main_player_role_generator.py`
- `src/ti_predictor/fantasy/main_player_role_backtest.py`
- `tests/test_fantasy_main_player_role_generator.py`
- `tests/test_fantasy_main_player_role_backtest.py`
- `artifacts/research/main-player-role-generator/<content-addressed-id>/`

正式 Web 继续使用当前 release，直到独立发布评审明确批准。
