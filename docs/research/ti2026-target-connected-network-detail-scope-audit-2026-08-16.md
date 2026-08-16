# TI 2026 十六队连通网络与逐场详情口径审计

- 调查日期：2026-08-16
- 调查方式：只读、离线；本调查没有发出 OpenDota 数据 API 请求
- 冻结目录事件截止：`2026-08-16T12:23:21.8307329Z`
- 冻结目录审计：`data/raw/opendota/audits/20260816T122321Z/manifest.json`
- 冻结目录审计文件 SHA-256：`21f65556f6945575c8194879314948589ca2a4fbc7b3cd2d5c14fe4afaa44f60`

## 结论

用户本次明确要求的逐场详情目标集合应定义为：

```text
UTC 2026 年已完成 /proMatches
∩ 当前 Team-strength policy 的正权重比赛
∩ 包含 16 支 TI 目标队的稳定队伍 ID 连通分量
```

它不是全年 `14,109` 场 `/proMatches` 的全部详情，也不是 Fantasy player history scope。
在当前冻结目录、配置与身份桥下，离线重算得到：

| 项目 | 数量 |
| --- | ---: |
| 冻结的 UTC 2026 `/proMatches` Game | 14,109 |
| 版本、赛事级别和时间权重为正的 Game | 4,284 |
| 十六队连通网络 Game | 3,857 |
| 连通稳定队伍 ID | 416 |
| 缺少正权重证据的目标队 | 0 |
| TI 2026（league `19719`）目录 Game | 109 |
| 其中属于十六队连通网络 | 109 |
| 定向补抓启动前已有有效详情 | 2,405 |
| 定向补抓启动前缺少有效详情 | 1,452 |

关键语义哈希：

- 16 个目标队 ID：`9adf3f9d357c6e59be48cb2afed407e1924b068d1a6385e148ee29764bcdf4ac`
- 416 个连通队 ID：`5864d9cbc35286edbc17ef198875d8e3e58f2a0f7ba383b900111bf0c06738b1`
- 3,857 个选中 `match_id`：`cc83e021a9de08a26782724a489056f5ad008e6c7f320c7e394a592c57fa236b`
- 1,452 个缺口 `match_id`，按 canonical JSON 数组计算：
  `c6af2304ad5e54a0bd5bc94756b75faf0dbdce2910a1a11cf57a73d4e7a6c7bc`

暂停的全年详情任务新增了 735 个详情，其中 418 个属于这 3,857 场，317 个不属于；后者应保留为
不可覆盖的原始响应，但不得因此进入本次连通网络。TI 2026 的 109 场在定向补抓启动前已经全部
有详情，因此后续 1,452 场是 TI 之外的连通证据缺口。

2026-08-16 13:15Z 后出现的 raw 详情变化来自用户明确授权的 corrected-scope 定向 backfill，
不是原先的全年 broad 抓取。该任务已于 `13:58:17Z` 完成：复用前有效详情 2,405 个，新增
1,452 个，最终 3,857/3,857、缺口 0、unavailable 0、失败 0；1,456 次请求尝试中有 4 次
受控重试。最终 manifest 位于
`data/raw/opendota/audits/target-connected-2026-detail-backfill/20260816T131517Z/manifest.json`，
SHA-256 为 `623e417adac973e4ea20730f257068336638a109a63b074de14bb4dc46c534fa`。

补抓后又进行了两轮独立 `/proMatches` 尾部刷新。两轮各取得两个完整重叠页，均观察到新增目录
ID 0、变更 0、身份敏感变更 0；网络仍为 3,857 场/416 队且 hash 不变，详情增量为 0。
第二轮通过“连续两轮 hash 相同”的稳定门槛，Snapshot availability time 为
`2026-08-16T14:06:16.32068Z`。最终 tail manifest 位于
`data/raw/opendota/audits/target-connected-2026-tail-refresh/20260816T140527Z/manifest.json`，
SHA-256 为 `6169e2d7fb12c7b4ff388d027c714749d817e1550321f6f58f449d25c5192f97`。
整个流程没有修改 processed、DuckDB、Replay、模型、预测或 runtime。

## 三个容易混淆、但必须分开的集合

### 1. Professional match catalog

它是指定 UTC 时间窗内 `/proMatches` 返回的 Game 目录；目录成员资格不代表必须下载
`/matches/{match_id}`。领域定义明确要求不要把目录理解为“全部已解析详情”
([CONTEXT.md](../../CONTEXT.md#L34-L37))。同步器分页获取全年目录时也把目录行设置成
`detail_eligible=False`，证明目录摘要本身就是独立的建模输入
([opendota.py](../../src/ti_predictor/ingest/opendota.py#L1432-L1524))。

### 2. Target-team evidence network

它是在明确 `as_of` 下，先完成正权重筛选，再在规范稳定队伍 ID 上构造无向图，最后保留包含
目标队的连通分量。它递归保留对手的对手，而不是只保留 16 队直接参加的比赛，也不是保留完整
职业目录 ([CONTEXT.md](../../CONTEXT.md#L107-L111)，
[ADR-0002](../adr/0002-target-team-evidence-network-and-rule-based-audit.md#L7-L34))。

### 3. Fantasy player history scope

Fantasy 的成员键是受审核玩家的稳定 `account_id`。它取这些玩家在固定 UTC 年参加的比赛 ID，
与职业目录相交，再保留 `premium/professional`；玩家曾为旧队出场的 Game 仍属于 Fantasy 范围
([CONTEXT.md](../../CONTEXT.md#L139-L143)，[data-contracts.md](../data-contracts.md#L59-L65))。
实现先请求 `/players/{account_id}/matches`，再与职业目录取交集，最后只为该玩家集合获取详情
([opendota.py](../../src/ti_predictor/ingest/opendota.py#L872-L935)，
[opendota.py](../../src/ti_predictor/ingest/opendota.py#L970-L1077)，
[opendota.py](../../src/ti_predictor/ingest/opendota.py#L1123-L1212))。

因此，不能再用“全年目录 14,109 减 Fantasy 已有详情 2,055”来描述连通网络缺口；两个集合的
成员规则不同。

## 连通网络的精确过滤顺序

以下顺序来自当前生产实现，顺序本身会改变集合，不能交换：

1. **固定输入与时间窗**：从冻结 `/proMatches` 页恢复目录，按 `match_id` 去重，只保留目标 UTC
   年和事件截止前已经完成且有结果的 Game。`match_id` 是唯一连接键，名称只用于显示。
2. **补充规则元数据**：用 `/leagues` 的 OpenDota tier 和 `/constants/patch` 的时间线给每场
   Game 标注 `league_tier` 与精确 Patch；Patch 按 Game `start_time` 解析
   ([match_catalog.py](../../src/ti_predictor/match_catalog.py#L20-L44))。
3. **规范队伍身份**：在构图前保留 raw team ID，按 `as_of` 可用的 registration identity window
   排除窗口外记录，再应用有效期内的 raw-to-canonical bridge。桥的证据在 `as_of` 后才可用时不得
   回填 ([identity.py](../../src/ti_predictor/identity.py#L38-L178))。当前预测加载顺序也是先身份
   规范化、再拟合模型 ([forecasting.py](../../src/ti_predictor/forecasting.py#L107-L154))。
4. **结构有效性**：排除无效时间、`start_time >= as_of`、任一队伍 ID 或胜负缺失、规范化后同队
   对局以及重复 `match_id`；重复 ID 会产生 blocking issue
   ([evidence.py](../../src/ti_predictor/models/evidence.py#L89-L139))。
5. **确定 Patch 窗口**：从不晚于 `as_of` 的 Patch 时间线确定 target family 与 immediate-prior
   family ([evidence.py](../../src/ti_predictor/models/evidence.py#L51-L86))。
6. **计算单局权重**：当前 policy 为 target family `1.0`、immediate prior `0.15`、更早版本
   `0.0`；精确 `7.41e` 自配置 UTC 边界起额外乘 `1.5`；`premium=1.0`、
   `professional=0.75`；时间半衰期 60 天
   ([team-strength-v2.json](../../config/models/team-strength-v2.json#L1-L22))。实现把 Patch、tier、
   time 三项相乘，只保留最终 `evidence_weight > 0`
   ([evidence.py](../../src/ti_predictor/models/evidence.py#L250-L371))。
7. **最后构图**：每场正权重 Game 在双方 canonical team ID 之间增加无向边，从 16 个目标队做
   确定性 BFS，保留双方都在可达队伍集合中的 Game
   ([evidence.py](../../src/ti_predictor/models/evidence.py#L189-L231)，
   [evidence.py](../../src/ti_predictor/models/evidence.py#L371-L407))。
8. **记录审计身份**：至少记录 policy/config/source hashes、目标队与连通队 hashes、选中
   `match_id` hash、各阶段计数、Git revision 和随机种子。ADR 明确要求每次运行记录这些内容
   ([ADR-0002](../adr/0002-target-team-evidence-network-and-rule-based-audit.md#L22-L26))。

### “2026 年连通网络”和“模型完整证据网络”并不完全相同

Evidence builder 本身没有日历年参数；日历年由传入的 catalog 决定。当前 immediate-prior
Patch `7.40` 从 2025-12-16 开始，而其权重为 `0.15`，所以直接对完整 `matches.parquet` 拟合时，
2025 年末的正权重职业比赛也会进入模型。

离线把冻结的 2026 目录与本地 2026 年前目录合并后，同一 policy 在上述事件截止得到：

- 完整正权重集合：4,531 场；
- 完整模型连通网络：4,069 场、456 队；
- 其中 2025 年末 212 场，UTC 2026 年 3,857 场；
- 完整模型选中 ID hash：`cf54d074a5f49172f36b3ab2489b08aa24e1c383677c40f9870795024c17d178`。

本次用户明确要求的是 **UTC 2026 年的 3,857 场详情覆盖**。Elo/Glicko 以后仍可从摘要使用那
212 场 2025 年末证据；如果未来要把“详情全部覆盖”扩张为“模型完整证据网络全部年份”，必须把
它作为另一个明确任务，不能悄悄并入本次 2026 backfill。

## 构造 scope match IDs 所需的 API 资源

| 资源 | 对构造连通网络是否必要 | 用途 |
| --- | --- | --- |
| `GET /proMatches?less_than_match_id=...` | 必要 | 冻结全年职业 Game 摘要，提供 ID、双方队伍、胜负、league、开始时间和时长 |
| `GET /leagues` | 必要 | 把 `leagueid` 映射为 OpenDota `premium/professional/...` tier |
| `GET /constants/patch` | 必要 | 按开始时间映射精确 Patch 和 major Patch family |
| 本地 `config/ti2026.yaml` | 必要但不是 API | 16 个稳定目标队、身份窗口与身份桥 |
| 本地 Team-strength policy | 必要但不是 API | Patch、tier、时间权重和 evidence scope mode |
| `GET /matches/{match_id}` | **不参与确定 scope** | 只在 scope 已冻结后补齐逐场玩家/解析详情 |
| `GET /leagues/19719/matches` | 交叉核对 | 核对 TI 联赛是否完整；不用于递归发现对手网络 |
| `GET /teams/{team_id}/matches` | 不需要 | 旧的有限队伍摘要路径；不能替代全年目录上的图遍历 |
| `GET /players/{account_id}/matches` | 仅 Fantasy 需要 | 构造 Fantasy player history scope，不构造 Team-strength 连通网络 |

项目客户端对这些端点的直接定义见
[opendota.py](../../src/ti_predictor/ingest/opendota.py#L483-L528)。运行手册同样规定连通网络应从
完整 `/proMatches` 目录本地生成，不递归调用每个对手的 team-history endpoint，且 replay/player
详情是另一个有界集合 ([runbook.md](../runbook.md#L39-L49))。

Elo/Glicko 训练实际只读取规范队伍 ID、胜负和 `evidence_weight`；它不读取玩家数组或事件日志
([ratings.py](../../src/ti_predictor/models/ratings.py#L261-L286))。所以下载 3,857 个详情是用户要求的
数据完整性/后续复用目标，不是计算这些比赛 Elo/Glicko 的先决条件。

## 离线确定 ID 与审计详情缺口的方法

### A. 冻结 scope

1. 对每个 `/proMatches` raw page 校验 metadata、body SHA-256 与请求游标；确认游标单调递减、页间
   没有冲突 ID。
2. 将所有页合并成 `match_id -> row`，发现同 ID 不同内容时 blocking，不得任意 keep-first/last。
3. 严格执行上一节的身份、权重和连通顺序，得到排序后的 `selected_match_ids`。
4. 记录完整 ID 数组以及实现使用的 hash。当前 `selected_match_ids_sha256` 不是 JSON hash，而是
   `_stable_id_hash`：对去重升序 ID 用英文逗号连接后做 SHA-256
   ([evidence.py](../../src/ti_predictor/models/evidence.py#L184-L186))。缺口 manifest 当前使用
   `sha256_json(sorted_ids)`；两种编码必须标明，不能直接拿 hash 值互相比对。
5. 断言 16 个目标队全部 present、TI 的 109 场全部 selected；任一不满足就停止补抓并调查 tier、
   Patch、身份或目录异常。

### B. 扫描已有详情

对每个 `data/raw/opendota/matches/{match_id}/*/` 捕获，只有同时满足以下条件才计为有效：

- `response.json` 是 JSON object，内部 `match_id` 等于目录 ID；
- `metadata.json.resource == "matches/{match_id}"`，请求参数 ID 一致；
- 去掉文件末尾换行后的原始 body SHA-256 等于 `metadata.content_sha256`，字节数一致；
- `fetched_at` 可解析为 UTC，且满足这次最终数据快照的可用时间边界；
- 详情的 `start_time`、`leagueid`、双方 team ID 与冻结目录不冲突；冲突必须 fail closed。

然后做集合运算：

```text
valid_in_scope = selected_match_ids ∩ valid_detail_capture_ids
missing        = selected_match_ids - valid_detail_capture_ids
extra          = valid_detail_capture_ids - selected_match_ids
```

`extra` 只表示“不属于本次目标”，原始捕获仍保持不变。最终缺口必须重新扫描 raw 目录计算，不能
只沿用旧 broad manifest 中已经陈旧的 `remaining_match_ids`。

对于本次“存在一个可信 OpenDota 详情响应”的覆盖目标，合法且身份完整的 base response 可算作
详情存在；Fantasy 是否可发布另有更严格门槛。Fantasy detail status 把十个已识别玩家且带解析
标志/版本的响应标成 `parsed_complete`，否则可能只是 `base_complete` 或 incomplete
([opendota.py](../../src/ti_predictor/ingest/opendota.py#L824-L860))。不得把 Team-strength 详情覆盖
和 Fantasy parsed/native replay 覆盖混成一个数字。

### C. 定向 API 补抓

只有冻结的 `missing` 升序/确定性列表可以进入 `GET /matches/{match_id}` 队列。每场成功后立即：

1. 校验响应身份与冻结目录；
2. 通过不可覆盖的 content-addressed raw store 写入 body、请求、UTC `fetched_at` 和 SHA-256；
3. 原子更新检查点、请求账本、成功/失败列表；
4. 重启时先重新校验本地 capture，已有效的 ID 只复用，不重发。

当前 `DataStore.write_raw_json` 以 `fetched_at + content hash` 建新目录；已有目录内容不一致会抛出
collision，而不是覆盖 ([storage.py](../../src/ti_predictor/storage.py#L20-L55))。请求预算、有限重试、
游标停滞和账本锁的既有规则继续适用 ([opendota-api-usage.md](../opendota-api-usage.md#L16-L49))。

## `as_of` 与快照时间必须修正命名

当前 broad manifest 把 `2026-08-16T12:23:21.8307329Z` 写为 `as_of`，但 142 个目录页实际抓取于
`12:29:01Z` 至 `12:33:54Z`；corrected-scope 详情则在 13:15Z 后继续抓取。因此这个时间只能解释为
**scope 的 Game 事件截止**，不能直接当作“这些响应当时已经可用”的 Forecast `as_of`。

生产加载器会同时检查 normalized row 的 `as_of` 和 `fetched_at`，晚于 Forecast cutoff 的捕获会被
排除 ([forecasting.py](../../src/ti_predictor/forecasting.py#L93-L104))。后续正式处理必须：

1. 分别记录 `scope_event_cutoff` 与 `snapshot_available_at=max(all used fetched_at)`；
2. Forecast `as_of` 不早于所有实际使用捕获的 `fetched_at`；
3. 在定向详情补抓结束后再刷新一次 `/proMatches` 尾部，冻结新的最终目录；
4. 用完全相同的算法重算 scope。若 hash 改变，只补抓新增的 scope delta；
5. 重复“尾部刷新—离线重算—定向 delta”直到一个明确截止下 scope 稳定，再生成 processed 数据、
   Elo、Fantasy、Forecast 和发布包。

这样既不会把抓取之后才观察到的信息伪装成 12:23Z 已知，也不会因为补抓耗时而遗漏刚进入
`/proMatches` 的职业 Game。

## 最终验收门槛

- 输入目录每页 body/metadata 完整，目录 ID 无冲突，来源只允许 OpenDota API；
- scope 规则、16 个目标队、identity config、Team-strength policy 和所有输入 hash 固定；
- 重新计算的 selected ID 集合可重复，且所有 16 队有正权重证据；
- TI 2026 league `19719` 的目录集合是连通网络子集，并与定向联赛核对一致；
- `missing = 0`，或每个不可取得的 ID 有明确失败状态并阻止“详情全覆盖”结论；
- 所有 raw capture 校验 SHA-256，任何旧响应都没有被覆盖；
- final manifest 记录 event cutoff、snapshot availability、请求数、API 账本、scope/present/missing/extra
  hashes、Git commit 和配置 hashes；
- 在完成上述 raw 审计之前，不修改 processed、DuckDB、模型、runtime pointer 或 Web 发布包。

## 本次离线复算使用的本地输入

| 输入 | SHA-256 |
| --- | --- |
| `config/ti2026.yaml` | `cf527bc9953edb1908be6a9531ec7579322e581a8db9cd3799cd8ba62c42722c` |
| `config/models/team-strength-v2.json` | `aa826cf3ef95fe9535192fd390dbe27541c13764ab4dbc88dd94ea579cadc0d4` |
| `data/processed/leagues.parquet` | `58b1a63c40e303f55dfbd7f1d7e1df7079d5791dab3089540b3ef0b7c0c961bb` |
| `data/processed/patches.parquet` | `cc0e6734bf88c0a404674482a4d35fa766aa85db080bf7c0b7946f88bc78e6a7` |

这些值是本次只读复算时核验的输入身份；正式处理仍须重新记录当次文件 hash。scope 的权威身份是
16 队 hash、policy hash、冻结目录 manifest hash 与选中 ID hash 的组合，而不是文件名或显示名称。
