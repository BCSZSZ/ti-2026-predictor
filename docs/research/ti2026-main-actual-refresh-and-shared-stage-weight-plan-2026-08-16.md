# TI 2026 Main actual refresh and shared stage-weight research plan

状态：**预注册研究计划；尚未修改正式模型、Web、运行时指针或发布包**  
决策冻结时间：`2026-08-16T12:19:58Z`  
目标 Main lock：`2026-08-20T02:00:00Z`

## 1. 已冻结的研究决定

在以 Main 为目标、且 `as_of` 已晚于 TI 2026 赛前阶段 Game 完成时间的运行中，对
`league_id=19719` 的已完成 Swiss 小组赛及突围赛 Game 使用当前赛事阶段证据乘数：

| 证据通道 | 主配置 | 说明 |
|---|---:|---|
| Team-strength Elo/Glicko | `1.5` | 在现行版本、级别和时间权重之后额外乘一次 |
| Fantasy 历史证据 | `1.5` | 使用相同系数，但保留独立政策字段和审计 |

两个通道使用相同数值表达共同的证据判断，但不能共享一个不可拆分的配置开关。两种模型对
权重的响应不同：Elo/Glicko 顺序更新评分和不确定性，Fantasy 则改变统计估计及完整 Series
重采样概率。因此“同等加权”指证据系数相同，不声称数值影响完全相同。

该决定在 Main 赛果产生前冻结。不得根据某套淘汰赛概率或某个 Fantasy 推荐看起来更顺眼而
事后改成 `1.0`、`2.0` 或 `3.0`。

## 2. 权重语义

现行基础权重为：

```text
w_base = major_patch_weight
       × current_exact_patch_multiplier
       × league_tier_weight
       × 2^(-age_days / 60)
```

本研究候选正式权重为：

```text
w_team_strength = w_base × 1.5  # 仅适用已完成的 TI 2026 赛前阶段 Game
w_fantasy       = w_base × 1.5  # 同一 Game 范围，独立政策字段
```

对刚结束、OpenDota `premium`、当前精确版本 `7.41e` 的 Game，典型最终权重约为
`1.0 × 1.5 × 1.0 × 1.0 × 1.5 = 2.25`。

Fantasy 的 `1.5` 不乘到观测分数或原生计数上。每个 Game 只附加一次证据权重；选手统计估计
使用该权重，完整 Series block 使用所含 Game 权重的均值，再在池内归一化为抽样概率。禁止在
Game、Series 和最终得分三个层级重复乘算。

## 3. 时间、赛事和数据边界

- 所有入口继续要求显式 UTC `as_of`，只接受 `start_time < as_of` 且在 `as_of` 前可用的证据。
- 当前赛事阶段范围是 TI 2026 Main 开始前的 Swiss 小组赛及突围赛；Main Game 不属于本次
  “先前阶段”样本，也不得在发生前进入模型。
- 使用稳定 `match_id`、`league_id`、Team ID 和 player account ID；名称只作显示。
- Fantasy 缺失仍为 `null`，不会因加权变成零。
- 其他赛事、版本、级别和时间衰减规则保持不变。
- Team-strength 与 Fantasy 的阶段乘数必须分别出现在 policy ID、manifest、语义哈希和审计
  breakdown 中，即使两者当前都等于 `1.5`。

## 4. 已知 actual 八队和首轮槽位

用户提供的官方直播截图已披露下列胜者组首轮；客户端仍待解锁复核：

| 节点 | 对阵（稳定 Team ID） |
|---|---|
| `upper_r1_a` | Iron Wing `10150413` vs Team Spirit `7119388` |
| `upper_r1_b` | TEAM VISION `9572001` vs BoomBoys `8255888` |
| `upper_r1_c` | Team Liquid `2163` vs Team Yandex `9823272` |
| `upper_r1_d` | Nigma Galaxy `10136357` vs Team Falcons `9247354` |

截图 SHA-256：`1D064175A276845067A8AC65355BC4A7BFC948109FA80A2E261C4E75C03F8C99`。
现有 BracketEngine 的槽位拓扑可表达这四组对阵；内部顺序是由已见槽位派生，不应被表述为
直播额外公布了数字种子。客户端解锁后必须复核；不一致时阻止 actual 发布并重新生成。

## 5. 原始数据完成门槛

当前首先等待既定 Codex 定时任务完成 OpenDota API-only 原始数据审计与补抓。全年目录与逐场
详情是两个不同集合；不得把 `/proMatches` 目录数量直接当成 `/matches/{match_id}` 详情门槛。
任务必须：

1. 完整分页核对 `[2026-01-01T00:00:00Z, as_of]` 的 `/proMatches`；
2. 按冻结的 16 个稳定队伍 ID、身份桥、版本/赛事等级/时间正权重政策，确定 2026
   Target-team evidence network；
3. 只对该网络的 unique `match_id` 检查和补齐 `/matches/{match_id}` 详情，不补网络外目录；
4. 单独证明 TI 2026 全部 Game 均属于该网络，不再另设会扩大总体范围的 TI 并集；
5. 只新增不可变 `data/raw` 响应和独立 raw audit manifest/checkpoint；
6. 不运行 processed、Replay、Elo/Glicko、Fantasy、Bracket 或发布流程；
7. 定向补抓结束后刷新 `/proMatches` 尾部，以新的 Scope event cutoff 重算网络并只补增量；
8. 分开记录 Scope event cutoff 与 Snapshot availability time，正式 Forecast `as_of` 不得早于后者；
9. 若受请求预算或 API 安全停止限制，精确报告网络内剩余 `match_id`，不得切回全年详情口径。

本次冻结目录 `as_of=2026-08-16T12:23:21.830732Z` 的离线门槛为：全年目录 14,109 个
Game、正权重 4,284 个、目标网络 3,857 个/416 支队、目标网络详情已有 2,405 个且缺
1,452 个。网络 match-ID SHA-256 为
`cc83e021a9de08a26782724a489056f5ad008e6c7f320c7e394a592c57fa236b`。TI 2026 的
109 个 Game 全部在网络中，且在定向补抓开始前已具备有效详情。

在 raw 报告证明数据全部获取完成前，以下处理与计算阶段保持暂停。

## 6. 数据完成后的研究和发布顺序

1. **Raw 验收**：校验 manifest SHA-256、请求统计、全年覆盖率、TI 和 TI 前一赛事缺口；任何剩余
   `match_id` 都显式列出。
2. **Processed 快照**：用新的显式 `as_of` 生成独立快照，校验身份桥、阵容生效区间、Patch、
   league tier、Series 完整性及 Fantasy 原生统计覆盖。
3. **权重实现**：增加两个独立的当前赛事阶段乘数字段，主值均为 `1.5`；不得改变 Group 冻结包。
4. **Team-strength 研究**：重算 Elo/Glicko 及 50/50 集成；执行滚动时间回测，并与 50%、现行
   无阶段加权模型比较 log loss、Brier 和校准。
5. **Fantasy 研究**：比较阶段乘数 `1.0` 与预注册主值 `1.5` 对有效 Series 权重、选手/定位统计、
   八队 Team matching 和 G/G-Lite 终局结果的影响；`2.0` 只作上界敏感性，不具有候选资格。
6. **Actual bracket**：按四个已知首轮槽位生成完整 14 节点双败 Forecast 和不确定性报告。
7. **Actual Main Fantasy**：以八队重建 Main Series 情景和 G/G-Lite 求解发布包；projected 与
   actual 的 manifest、产物和运行时指针保持隔离。
8. **验证发布**：执行单元、集成、确定性、差异检查和 Web 双 Tab 验收。全部通过后才原子切换
   bracket 与 Main Fantasy actual 指针；G 继续为默认，G-Lite 保留为用户可选。

## 7. 停止与报告规则

- 原始数据任务未完成、manifest 无法校验或存在未解释缺口：停止，先报告，不进入 processed。
- 阶段乘数造成代码门禁、历史滚动验证或 Fantasy 完整性检查阻断：停止并报告，不静默回退。
- 研究参数、数据快照和发布指针不得在同一个未审计步骤中同时变更。
- 本计划不是 actual 发布授权；它只冻结研究路径和后续验收顺序。
