# TI 2026 Main projected 16 队与派生八队策略选型审计（2026-08-15）

> 状态说明：这是实装前的只读审计，保留当时发现和建议。后续协议、完整实验与最终
> G/T/H 决策见 `ti2026-main-roll-projected16-strategy-selection-2026-08-15.md`；其中的
> 实验规模和当前实现状态取代本文的“尚未完成”描述。

## 审计范围与结论

- 审计日期：`2026-08-15`。
- 目标：核查“先用 projected 16 队完成 Main Roll 策略选型，再从这 16 队派生八队情景做稳健性验证”是否能在当前冻结证据上成立。
- 边界：本次只读取 `CONTEXT.md`、冻结 Main release、研究配置、研究模拟器和测试；未访问网络、未运行完整 tuning/confirmation、未修改 Web、生产求解器、运行时指针或配置。
- 当前结论：**可以在现有 projected release 上比较 G/T/H，但结论只能表述为对固定 release、固定已观测起点和当前 16 队聚合目标成立。当前 runner 尚不能单独证明对未来八队阵容稳健，也不能把结果称为 actual。**

要完成用户批准的研究路线，需要先补齐一个研究层协议，而不是改 Web：

1. 保留当前 16 队 projected 聚合作为策略筛选目标；
2. 从冻结 Group 情景派生带完整 provenance 的八队**预测阵容情景**；
3. 在八队情景内重新限制 Team matching，并用独立的 Main bracket / Fantasy 表现内层样本估值；
4. 冻结八队非劣门槛、概率模型稳定门槛和 T/H 决胜规则后，才运行完整 confirmation；
5. actual 到来后建立新 manifest，用新数据和实际种子做最小复验，绝不覆盖或拼接 projected 报告。

## 1. 术语与不可跨越的边界

仓库已有三个稳定事实：

- `Main Fantasy scenario` 在 actual 名单未知时从 16 个候选中选八队；actual 已知后八个候选全部入场（`CONTEXT.md:150-155`）。
- `Projected Main eligibility` 暴露 16 个候选，但每个情景只有八队入场，未晋级队记零，预测种子只是 proxy（`CONTEXT.md:163-168`）。
- `Actual Main eligibility` 只有在赛后原始证据刷新、八个稳定 Team ID 和正式种子顺序导入后才成立（`CONTEXT.md:170-174`）。

本报告建议在研究产物中临时使用以下更窄术语，避免把派生八队误写成 actual：

| 术语 | 定义 | 禁止写法 |
| --- | --- | --- |
| `projected-16 selection` | 在一个固定 projected release 的 16 队候选空间和预测晋级分布上选择 Roll 策略 | actual 选型、正式八队选型 |
| `projected-derived eight-team roster scenario` | 由冻结 Group Scenario 的晋级掩码派生的八个稳定 Team ID、预测种子及研究内层抽样；仍是 Forecast 情景 | actual roster、官方晋级名单、Main 正式名单 |
| `actual-8 revalidation` | 实际名单、正式种子和赛后刷新证据进入新 actual release 后的独立复验 | projected 报告续跑、把预测八队改名为 actual |

这些是本次研究审计中的候选术语，不修改 `CONTEXT.md`。在真正增加跨模块研究合约前，应由 owner 决定是否把它们纳入正式领域词汇。

## 2. 一手证据与冻结身份

### 2.1 设计和运行边界

- ADR 0008 明确：projected 模式保留 16 队、每个连贯情景只允许八队、种子由 Group category 和 Team strength proxy 构造；actual 则必须先刷新原始证据再导入正式八队（`docs/adr/0008-separate-group-and-main-fantasy-stacks.md:14-23`）。
- 当前指针是 `status=provisional`、`eligibility_mode=projected`、16 个候选、8 个 entrant，`as_of=2026-08-13T13:23:17Z`，release SHA-256 为 `94c00919f01395dae7f1eb371db0156cc8225c5b9aa9f5b02ccb9083d6d714c9`（`deploy/runtime/main-current.json:2-16`）。
- Main policy 冻结了 256 个情景、seed `20260820`、Group 情景晋级来源、预测种子 proxy、五槽和 30 Roll（`config/models/fantasy-main-current-screen-advisor-v1.json:2-16`）。
- 研究 manifest 固定为 `research_only=true`、禁止 Web integration、runtime pointer write 和 Dota control，并绑定上述 release、规则和 Roll rule hash（`config/research/fantasy-main-roll-simulator-v1.json:2-18`）。
- 研究 runbook 明确 projected 与 actual 必须使用不同 manifest 和报告（`docs/runbooks/main-roll-strategy-research.md:47-59`）。

### 2.2 projected Main 情景是怎样构造的

`build_projected_main_scenario_set_from_group` 的实现给出完整路径（`src/ti_predictor/fantasy/main_scenarios.py:251-310`）：

1. 候选 Team 必须恰好为 16 个稳定 ID；
2. 若 Main 和 Group 情景数相同，按 Group 行 `0..N-1` 一一使用；否则才有放回抽 Group 行；
3. `group_category < 3` 的 Team 被视为八个 entrant；
4. entrant 按 Group category、Team strength、稳定 Team ID 排序形成预测种子；
5. 在该八队上抽一条双败 bracket path，得到每队 Series 数；
6. 非 entrant 的 Series 数保持零。

`MainScenarioSet` 进一步强制每行恰好八队 active，并且 projected 可以有零，actual 的八个候选则必须全部 active（`src/ti_predictor/fantasy/main_scenarios.py:67-94`）。Main 终局 evaluator 对 projected 的空 Series 明确赋零（`src/ti_predictor/fantasy/main_current_advisor.py:40-73`）。

### 2.3 对当前冻结包的轻量只读矩阵核查

对当前 release 解压后仅统计元数据和 `series_counts > 0`，未执行策略 rollout，得到：

| 核查项 | 结果 |
| --- | ---: |
| Group Scenario 行数 | 256 |
| Main Scenario 行数 | 256 |
| 每行 active Team 数 | 始终 8 |
| Main active mask 是否逐行等于 `group_categories < 3` | 是 |
| Main 与 Group Scenario ID 是否同为 `0..255` | 是 |
| 256 行中的不同八队集合 | 240 |
| 因重复八队集合产生的额外行 | 16 |
| 同一八队集合出现次数 | 1 至 3 次 |

冻结 release 还记录了 source Group Scenario SHA-256
`12e6b771845c4df5b3c6da495f27a84f17ca7faf4c7264eb882b26f507b8a1c0` 和 source Group `as_of=2026-08-10T13:45:12Z`；Main Scenario SHA-256 为
`bae9b31d109fca11cd66983156bb8edb2010f7b864f15d4fc892bdfeb1358ead`。

因此：

- 当前 256 行是晋级模型的经验分布，默认每行等权；**不能把 240 个 unique roster 去重后再均匀加权**，否则会改变预测晋级概率和 bracket 路径变异。
- 同一八队集合的重复行也可能有不同 Group category、预测种子和 Main bracket path；只能在报告中聚合观察，不能在主估计中丢弃。
- 当前构造在 `N_main=N_group=256` 时确实是一一映射，但 release 的情景 payload 没有为每行单独存 `source_group_scenario_id`。派生研究产物应把这个字段显式保存，不能只靠行号巧合推断。

## 3. 16 队上哪些结论成立

### 3.1 可以成立的结论

在以下条件全部固定时，可以完成 G/T/H 的**条件性策略选型**：

- release SHA、Rule snapshot、Roll-rule hash 和 `as_of`；
- 当前 16 个稳定 Team ID、256 个 projected Main 情景和预测种子方法；
- 一份完整、人工确认的三面五槽 Banner、共享三操作和剩余 Roll 数；
- 冻结的五个 Roll transition model；
- 分离的 tuning 与 confirmation Roll seeds。

在此范围内，可以回答：

- T 或 H 是否在当前 projected 目标上比 G 有更高 mean；
- lower-tail CVaR10 是否满足冻结非劣门槛；
- 首选策略是否对五个 Roll transition model 敏感；
- T 的 target 完成率、H 的切换行为和 token 使用是否符合设计；
- 对该**具体已观测起点**，哪个策略值得继续作为 actual 复验候选。

研究报告已经要求三策略共享起点、match-performance scenario、transition model 和随机 tape，并把调参 seed 与最终 seed 分开（`docs/research/ti2026-main-fantasy-roll-strategy-simulator-2026-08-14.md:351-372`）。runner 也把起点 hash 和剩余 Roll 写入报告（`src/ti_predictor/fantasy/main_roll_research_experiment.py:337-355`）。

### 3.2 不可以从 16 队结果推出的结论

以下表述都越过了证据：

- “这就是 actual 八队的最优策略”；
- “预测种子等于官方 Main seed”；
- “已包含小组赛结束后的最新 Fantasy 表现”；
- “该策略对所有可能起点都更好”；当前 manifest 只接受一个外部 state，没有 starting-state coverage split；
- “五个概率模型证明了 Valve 真实出率”；它们只是敏感性模型；
- “通过研究 gate 就可以自动替换 Web 顾问”；manifest 和 runner 都明确禁止自动 promotion。

目前磁盘中只有两个 `smoke` 产物，都是一枚剩余 Roll、一个 primary seed，gate 为 `not-evaluated`；它们只证明管线可运行，不是策略证据。

## 4. 当前 16 队终局目标与“名单出来后再选队”并不相同

这是本次审计最重要的实现边界。

`FrozenMainTerminalAdapter` 先为每个 role 构造 16 队 × 256 情景矩阵，然后调用一次
`match_group_roles`，得到三个固定 Team ID 和一条 256 维结果向量
（`src/ti_predictor/fantasy/main_roll_research_simulator.py:184-220`）。`match_group_roles` 根据每队跨全部情景的均值挑选固定 Team（`src/ti_predictor/fantasy/valuation.py:462-483`）。

这对应的近似目标是：

```text
max over one fixed Team per role
    average over projected advancement/Main scenarios(score; non-entrant = 0)
```

而用户描述的实际决策时序是“现在可以 Roll，名单锁定后候选才缩到八队”，其自然目标是：

```text
average over projected eight-Team rosters r
    max over Team choices available in r
        expected Main score conditional on roster r
```

两者是 `max E` 与 `E max` 的区别。当前聚合目标可以作为保守筛选器，但不能单独证明第二个目标。

也不能在每个现有单行情景里直接挑当行得分最高的 Team：这会在选 Team 时看到该情景已经实现的未来 bracket 和 Fantasy 表现，构成 look-ahead。由于 256 行包含 240 个不同 roster，绝大多数 roster 只有一个结果样本，不能从单行可靠估计条件期望。

## 5. 派生八队稳健性情景的合规构造

### 5.1 外层 roster 来源

八队 roster 只能来自冻结 Group Scenario 的 `category < 3` 掩码，不得手工猜实际晋级队，也不得遍历全部 `C(16,8)` 后均匀加权。每个外层记录至少保存：

```yaml
scenario_kind: projected-derived-eight-team-roster
source_main_release_sha256: 94c00919...
source_group_scenario_sha256: 12e6b771...
source_group_as_of: 2026-08-10T13:45:12Z
source_group_scenario_id: 0..255
entrant_team_ids: [8 stable IDs]
group_categories: [category for each entrant]
projected_seed_order: [8 stable IDs]
seeding_method: projected_group_category_then_strength
empirical_weight: 1/256
fold_id: <predeclared deterministic fold>
```

若按 roster 汇总，权重必须是出现次数除以 256；主估计仍保留原 256 行。名称、Logo 或队伍简称只能用于显示。

### 5.2 内层 Main 条件样本

对用于 roster-specific 稳健性判断的八队 roster，需从同一冻结 Team-strength model、Series pools、规则和 `as_of` 生成多条内层 Main bracket / Fantasy performance 路径。seed 应由
`release_sha256 + source_group_scenario_id + replicate_id` 确定，保证复现且不与 Roll tape 共用随机流。

Team matching 只能使用该 roster 的八队，并根据内层分布选择 Team；不得根据某一条已实现的内层结果再选 Team。Roll 策略在 projected 阶段仍看不到未来 roster ID。

### 5.3 selection 与 robustness 的隔离

当前 manifest 的 `32 tuning + 128 confirmation` 只切分 Roll episode seed
（`config/research/fantasy-main-roll-simulator-v1.json:99-107`；`src/ti_predictor/fantasy/main_roll_research_experiment.py:62-74`），没有切分八队 roster。

在完整实验前还应冻结：

1. 一个只按 source scenario ID、roster mask 和固定 salt 构造的 roster fold 分配；不得看策略得分后再分层；
2. selection 使用的 roster folds 与八队 robustness folds；
3. 每个 roster/stratum 的内层 replicate 数；
4. 多重比较修正；
5. 若只做小型代表 panel，panel 的选取规则和原始经验权重。

建议主报告同时给两层结果：

- **分布内稳健性**：在预注册的若干平衡 folds 上报告，不对单个稀疏 roster 作强结论；
- **条件 roster 压力测试**：对事先选定的代表 roster 生成足够内层样本，单独报告且不改变主分布权重。

所有文件必须留在 research artifact 路径，不能写 `config/ti2026.yaml:main_event_seeds`、不能调用 `--mode actual`、不能移动 `deploy/runtime/main-current.json`。

## 6. 策略定型门槛

### 6.1 已经冻结的总体门槛

当前 manifest 已冻结以下规则（`config/research/fantasy-main-roll-simulator-v1.json:109-115`），runner 的实现位于
`src/ti_predictor/fantasy/main_roll_research_experiment.py:301-335`：

| 门槛 | 当前值 |
| --- | ---: |
| confirmation seeds | 128，且与 32 个 tuning seeds 不重叠 |
| probability models | confirmation 必须包含全部五个 |
| primary paired mean | 95% 单侧下界 `> 0` |
| relative mean gain | 至少 `+0.5%` |
| paired CVaR10 | 95% 单侧下界不低于 `-1% × |G 的 CVaR10|` |
| Web promotion | 永远为 false |

这些门槛足以判断 T/H 是否在**总体 projected 聚合目标**上通过相对 G 的研究 gate。

### 6.2 仍缺少、必须在完整实验前冻结的门槛

当前实现有四个空缺：

1. `require_probability_sensitivity_report=true` 只要求报告存在；即使 challenger 在部分模型上反向，primary gate 仍可能通过。
2. T 和 H 都通过相对 G 的 gate 时，没有直接的 T-vs-H 决胜规则。
3. 没有八队 roster fold 的非劣 gate。
4. 没有跨起点 gate；因此默认结论只能绑定一个 `starting_state_sha256`。

建议由 owner 在运行完整 confirmation 前批准以下最小补充规则；这些是研究决策，不是 Valve 规则：

- **八队 fold 非劣**：每个预注册 robustness fold 上，challenger 相对 G 的 mean 与 CVaR10 配对差值之 95% 单侧下界均不低于该 fold 基线的 `-1%`；对多个 folds/challengers 做预注册修正。总体 `+0.5%` 优越门槛不要求每个 fold 都达到，但任何 fold 的 material regression 会阻止“八队稳健”标签。
- **概率模型默认资格**：若五模型的总体 mean 差值不是全部非负，结果只能标记 `model-dependent`，不能定为默认策略；Primary 结果仍可作为带假设的单独建议。
- **T/H 决胜**：若两者都通过，使用相同 paired tape 直接比较 T-H；只有差值达到冻结 material threshold 且单侧下界大于零才选较复杂者 H，否则选通过门槛的较简单者 T。若 T、H 都不通过，保留 G。
- **未决**：样本预算内不能区分时报告 unresolved，不因排名点估计强行选胜者。

如果研究目标是为所有 Main 起点发布通用策略，而不只是当前玩家的已观测状态，还需另建 starting-state coverage suite；这不属于当前单状态最小实验。

## 7. actual 到来后的最小复验

actual 转换的生产证据条件已经明确：`main_event_seeds` 目前为空（`config/ti2026.yaml:13-14`）；actual 需要八个正式种子、赛后 processed snapshot、晚于 Group freeze 的本届 Fantasy Game，并且八队都有本届 Fantasy 行（`src/ti_predictor/cli.py:805-845`；`src/ti_predictor/fantasy/main_evidence.py:180-203`）。

若 projected 选型已通过上述八队稳健门槛，actual 最小复验为：

1. 保留 projected manifest、报告和哈希不变；建立新的 actual manifest/version，绑定新的 `as_of`、actual release hash、规则 hash、八个 stable Team ID 和官方 seed order。
2. 验证 actual release 为 `eligibility_mode=actual`、八个候选全部 active、Series pool 已刷新且不同于 Group freeze。
3. 比较 Rule snapshot、operation support/weight 和 Roll-rule hash：
   - 全部相同：不重调 T/H 参数，不重复大范围 target/switch 网格；
   - 任一发生影响转移的变化：先重做 1-3 Roll exact kernel 验证，再启动新的 actual tuning/confirmation。
4. 重新确认当时真实的五槽 Banner、三操作和剩余 Roll，绑定新的 `starting_state_sha256`。
5. 在 actual release 上只跑 `G + projected winner`，使用与 projected tuning/confirmation 均不重叠的新 paired seeds，并包含全部五个概率模型；用同一总体 mean/CVaR gate 复验。
6. 若 projected 的 T/H 决胜仍是 unresolved，actual 最小范围增加另一个并列策略；不得先看 actual 结果再改变参数。
7. actual gate 失败时，回退 G 或标记 unresolved。任何 actual 调参都必须启动新的 tuning/confirmation，不能把第一次 actual 结果同时当调参和确认。

若 actual 到来时已经没有剩余 Roll，则不存在待复验的 Roll 策略；只需用刷新后的 actual release 做八队 Team matching 和最终 Banner 估值。

## 8. 建议执行顺序（研究层，不改 Web）

1. **信息冻结**：确认当前用户 state、projected release hash、规则 hash和 256 行 provenance。
2. **协议冻结**：由 owner 批准 roster fold、内层 replicate、八队非劣门槛、概率模型默认资格和 T/H 决胜规则。
3. **最小验证**：先用极小 seed/replicate 验证 outer roster 与 inner Main 路径隔离、稳定 ID、无 look-ahead、确定性和 report schema；smoke 永不评价 gate。
4. **tuning**：只使用 32 个 tuning Roll seeds 和 selection roster folds 调 T/H 参数。
5. **冻结候选**：固定参数、代码 hash、state hash 和 winner rule。
6. **confirmation**：在 128 个独立 Roll seeds、全部五模型和未参与选择的 roster robustness folds 上做配对确认。
7. **修正循环**：若数值/隔离测试失败，修 simulator；若研究 gate 失败，保留 G 或 unresolved。任何策略规则变化都会产生新版本和新 confirmation，不能复用旧确认样本。
8. **actual 最小复验**：按第 7 节建立独立 actual manifest，不自动推广到 Web。

## 9. 最终审计判断

| 问题 | 判断 |
| --- | --- |
| 现在能否用 projected 16 队研究三策略？ | 能，但只对冻结 release、具体起点和 projected 聚合目标成立。 |
| 当前 256 行是否已经各自是八队 Main 情景？ | 是；每行恰好八队，逐行来自冻结 Group 晋级掩码。 |
| 能否把 unique 八队集合均匀化？ | 不能；会破坏经验概率，重复行还承载种子/bracket 变异。 |
| 当前 runner 是否已经完成八队稳健验证？ | 没有；它只切 Roll seeds，并做一次 16 队全局 Team matching。 |
| 派生八队能否叫 actual？ | 不能；必须标记 projected-derived 并绑定 source Scenario provenance。 |
| actual 到来后是否必须重跑全量调参？ | 规则不变且 projected 稳健 gate 已通过时不必；但必须用新 actual release 和新 paired seeds 做 G-vs-winner 最小确认。 |
