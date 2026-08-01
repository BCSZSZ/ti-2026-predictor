# OpenDota 比赛详情采样标准调查

调查日期：2026-08-01  
研究范围：OpenDota `GET /matches/{match_id}` 是否可作为 TI 2026 胜负模型与 Fantasy 表现样本的统一详情来源。  
主来源版本：[`odota/core@2d67379`](https://github.com/odota/core/tree/2d67379fbba90b2fd015c6f0f4080d394a5741e9)、[`odota/parser@a0ded4a`](https://github.com/odota/parser/tree/a0ded4a2857ba94df4d5865301998a6df67dcb89)。

## 结论

`GET /matches/{match_id}` 可以作为本项目的统一“详情响应”采样接口，也可以对以后指定的赛事按同一标准继续采样，但必须满足以下条件：

1. HTTP 200 只代表 OpenDota 找到了比赛，不代表 replay 已解析。详情样本必须检查 `od_data.has_parsed == true` 且 `version` 非空；否则只有 Steam API/GC 基础数据，不具备大多数 Fantasy 字段。
2. 原始 JSON 必须不可变保存；规范化层另行保存 `has_api`、`has_gcdata`、`has_parsed`、`has_archive`、解析 `version`、字段覆盖率和缺失原因。
3. 每场必须检查 10 个合法玩家槽位、稳定 `account_id`、队伍 ID、开始时间、版本、赛事 ID/级别与系列赛信息。失败的比赛进入缺口清单，不能以零补齐。
4. OpenDota 能稳定提供基础赛果和常规终局数据；14/18 个当前 Fantasy 统计依赖 replay 解析。魔石、烟雾、瞭望台、莲花和魔方等内部事件映射仍不等于 Valve Fantasy 结算真值，必须继续标为 `proxy` 或单独验证。
5. 对当前目录中 `premium/professional` 且涉及 TI 16 队的 2026 比赛做全量详情采样在请求量和磁盘量上可行；真正的不确定性是历史 replay 是否已经被 OpenDota 解析，而不是 JSON 下载本身。

因此，当前 257 场更准确的评价是：**255 场合格的 replay 详情样本 + 2 场基础详情样本**，不是 257 场都具备完全相同的信息质量。

## `/matches/{match_id}` 实际是什么

OpenDota 的公开路由调用 `buildMatch` 生成响应，[路由定义](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/api/spec.ts#L216-L240)本身没有要求比赛必须已经解析。`buildMatch` 会把以下来源合并到一个对象中：

- Steam/API 基础比赛数据；
- Dota GC 数据，如 replay salt、series ID/type 和非匿名账号；
- replay parser 产生的细粒度事件；
- OpenDota 历史归档。

合并逻辑及 `od_data.has_api/has_gcdata/has_parsed/has_archive` 标记见 [`getMatchBlob.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/getMatchBlob.ts)，响应丰富逻辑见 [`buildMatch.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/buildMatch.ts)。这意味着同一 endpoint 会返回不同完整度的响应。

OpenDota 的 `MatchResponse` schema 罗列字段但没有声明统一的 `required` 集合；客户端必须接受字段缺失。完整 schema 见 [`MatchResponse.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/api/responses/MatchResponse.ts)。

### 比赛级信息

响应可包含：

- 身份与时间：`match_id`、`match_seq_num`、`start_time`、`duration`、`patch`、`region`、`cluster`；
- 赛果与赛事：`radiant_win`、双方比分、双方队伍对象/ID、`leagueid`、league 对象、`series_id`、`series_type`；
- 模式与状态：`game_mode`、`lobby_type`、塔/兵营 bitmask、首血时间；
- draft：`picks_bans`，以及 replay 解析后的 `draft_timings`；
- replay 细节：`objectives`、`teamfights`、聊天、暂停、逐分钟金钱/经验优势；
- 数据状态：解析 `version`、`replay_salt/replay_url` 和实现提供的 `od_data`。

### 玩家级信息

Steam/API 基础层主要提供玩家槽位和账号、英雄/命石、K/D/A、正反补、GPM/XPM、等级、英雄伤害、治疗、塔伤、终局物品、离开状态等。OpenDota 在类型定义中把这些列为基础 `Player`，把事件日志和解析统计列为 `ParsedPlayer`；参见 [`global.d.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/global.d.ts#L20-L176)。

replay 解析层还可提供：

- `ability_uses`、`item_uses`、`killed/killed_by`；
- 击杀、购买、买活、神符、眼位、连接等事件日志；
- `camps_stacked`、`rune_pickups`、`obs_placed`、`stuns`；
- `firstblood_claimed`、`teamfight_participation`、`towers_killed`、`roshans_killed`；
- 逐分钟 gold/xp/last-hit、lane、teamfight、ward 坐标等分析字段。

这些字段由 replay parser 明确定义和填充，见 [`CreateParsedDataBlob.java`](https://github.com/odota/parser/blob/a0ded4a2857ba94df4d5865301998a6df67dcb89/src/main/java/opendota/CreateParsedDataBlob.java#L14-L82)及其从游戏实体属性读取终局统计的实现 [`Parse.java`](https://github.com/odota/parser/blob/a0ded4a2857ba94df4d5865301998a6df67dcb89/src/main/java/opendota/Parse.java#L650-L690)。

## 18 项 Fantasy 统计的来源分层

下表评价的是“当前项目如何从 OpenDota 响应取值”，不是 Valve 对 Fantasy 结算语义的官方背书。

| Fantasy 统计 | OpenDota 字段/映射 | replay 依赖 | 当前可信度 |
|---|---|---:|---|
| 击杀 | `kills` | 否 | `exact` |
| 死亡 | `deaths` | 否 | `exact` |
| 正补与反补 | `last_hits + denies` | 否 | `derived` |
| GPM | `gold_per_min` | 否 | `exact` |
| 魔石拾取 | `item_uses.madstone_bundle` 等 | 是 | `proxy`：记录使用事件，未证明等于“拾取” |
| 防御塔最后一击 | `towers_killed` / `tower_kills` | 是 | `exact`，需锁定别名 |
| 假眼放置 | `obs_placed` | 是 | `exact` |
| 堆叠野怪营地 | `camps_stacked` | 是 | `exact` |
| 神符拾取 | `rune_pickups` | 是 | `exact` |
| 诡计之雾使用 | `item_uses.smoke_of_deceit` 等 | 是 | `proxy`，需按 patch 审计内部键 |
| 瞭望台占领 | `ability_uses.ability_lamp_use` | 是 | `proxy` |
| 莲花拾取 | `item_uses.famango/great_famango/...` | 是 | `proxy`：使用事件未证明等于获得 |
| Roshan 击杀 | `roshans_killed` / `roshan_kills` | 是 | `exact`，需锁定别名 |
| 团战参与 | `teamfight_participation` | 是 | `exact`（OpenDota 终局属性语义） |
| 第一滴血 | `firstblood_claimed` | 是 | `exact` |
| 眩晕秒数 | `stuns` | 是 | `exact` |
| 魔方击杀 | `killed.npc_dota_miniboss` | 是 | `proxy`：内部单位名与 Valve Fantasy 语义待核对 |
| 信使击杀 | `courier_kills` | 是 | `exact`（由解析击杀对象计算） |

也就是说，只有前 4 项不依赖 replay；其余 14 项都必须把 `has_parsed` 作为前置条件。OpenDota parser 当前把解析版本写为 `22`，见 [`CreateParsedDataBlob.java`](https://github.com/odota/parser/blob/a0ded4a2857ba94df4d5865301998a6df67dcb89/src/main/java/opendota/CreateParsedDataBlob.java#L14-L17)。历史样本可能携带不同版本，不能在不记录版本的情况下直接混合。

### “缺少键”不总是“缺失值”

解析器会初始化 `item_uses`、`ability_uses`、`killed` 等计数 map，并只在事件出现时递增；见 [`CreateParsedDataBlob.java`](https://github.com/odota/parser/blob/a0ded4a2857ba94df4d5865301998a6df67dcb89/src/main/java/opendota/CreateParsedDataBlob.java#L68-L81)和[事件累计逻辑](https://github.com/odota/parser/blob/a0ded4a2857ba94df4d5865301998a6df67dcb89/src/main/java/opendota/CreateParsedDataBlob.java#L1355-L1400)。因此应区分：

- `has_parsed == false` 或整个 map 缺失：未知，保存 `null`；
- 已完整解析且 map 存在，但指定键没有出现：在 OpenDota 事件计数语义中是 `0`；
- map 存在但项目使用的内部键可能已经随 patch 改名：仍应视为映射未验证，而不是盲目记零。

当前规范化实现对 map 中未出现的目标键经常返回 `null`。这符合“不能把真正缺失当零”的保守规则，但会把“已解析、实际零次”也当成缺失，尤其会压低烟雾、莲花、魔方等字段覆盖率。正式全量采样前应按上述三态逻辑修正，并保留原始 map 供审计。

## 历史详情与 replay 解析限制

1. `GET /matches/{id}` 不会保证或等待 replay 解析，它只合并当前可用数据。
2. 如需主动请求解析，OpenDota 提供 `POST /request/{match_id}`；该请求按 10 次 API 调用计算，见[官方路由说明](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/api/spec.ts#L1520-L1588)。
3. parser 在处理前会对 Valve replay URL 发 HEAD；文件不存在时直接返回 `Replay not found`，见 [`ParsedFetcher.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/fetcher/ParsedFetcher.ts#L21-L59)。因此老比赛若此前未解析/归档，事后无法保证补齐。
4. OpenDota 对新鲜 league match 会自动排入 replay 解析队列，并给予 `AUTO_LEAGUE` 优先级；见 [`insert.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/insert.ts#L480-L535)和[优先级定义](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/priority.ts)。这使近期职业赛事通常具有较高解析覆盖率，但不是完整性承诺。
5. GC/replay 取得本身有平台容量限制。OpenDota retriever 源码记录的近似限制为每账号每天 100、每 IP 每天 500，且实际 worker 会受账号与队列容量影响；见 [`retriever.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/retriever.ts#L1-L25)。这是 OpenDota 服务端解析限制，不是普通详情 GET 的客户端配额。

历史采样的正确策略是：先 GET 并测量已有解析覆盖率；最近结束而尚未解析的职业比赛可以稍后重试。不要把“批量 POST 解析所有历史缺口”当作可保证成功的方案。

## API 速率限制

当前 OpenDota core 默认配置为：

- 无 API key：60 次/分钟；免费额度 3,000 次/天；
- 有 API key：300 次/分钟；超过免费调用量进入 API key 的用量/计费机制；
- `POST /request` 的 rate cost 为 10，普通 `GET /matches` 为 1。

默认值见 [`config.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/config.ts#L57-L66)，实际限速、响应头和 429 逻辑见 [`web.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/web.ts#L414-L508)。生产部署值可能调整，因此采集器仍应以 `X-Rate-Limit-Remaining-Minute`、`X-Rate-Limit-Remaining-Day` 和 `Retry-After` 为准。

本项目当前每次请求至少间隔 1.05 秒，适配无 key 的 60 次/分钟限制。全量执行应支持断点续传、429 退避、原始响应去重，以及明确的失败清单。

## 本地 257 场样本审计（截至 2026-08-01）

对 `data/raw/opendota/matches/<match_id>/.../response.json` 每个比赛目录的最新不可变响应检查结果：

- 唯一比赛：257；全部响应都有 10 名玩家；
- `od_data.has_parsed == true` 且 `version == 22`：255 场（99.22%）；
- 只有 API + GC、没有 parsed/archive：2 场（0.78%）；
- 最新原始 JSON 合计 70.46 MiB；均值 280.73 KiB/场，P50 278.31 KiB，P95 353.77 KiB，最大 401.39 KiB/场。

这解释了规范化表中多数 replay 字段约 99.22% 的比赛级覆盖。烟雾、莲花、魔石、魔方等更低的非空率主要还混有“map 中无目标键被记为 null”和内部键/语义未验证两类问题，不能直接解释为 OpenDota 没有解析 replay。

当前采样保留了完整 raw JSON，但 `fantasy_performance_samples.parquet` 只规范化了身份、时间、时长和上述 18 项统计，并不是 OpenDota 全部详情字段的扁平副本。若模型将来需要 draft、逐分钟曲线、对线或道具时序，应从不可变 raw 另建版本化特征表，不应重新定义“详情采样”为另一个接口。

## TI 16 队 premium/professional 全量采样可行性

按 2026-08-01 本地比赛目录与 `config/ti2026.yaml` 的 16 个稳定 team ID 过滤：

- `league_tier in {premium, professional}` 且任一方为 TI 队伍：1,470 个唯一 Game；
- 当前这 1,470 场全部标为 `professional`，没有 `premium` 候选；
- 时间范围：2026-01-04 至 2026-08-01；
- 预期玩家-Game 行数：约 14,700；
- 已有详情交集：113 场；尚需 GET：1,357 场；
- 按当前均值估算，全部 raw JSON 约 403 MiB，剩余约 372 MiB。建议为日志、重复快照和未来增量至少预留 1–2 GiB；该估算不含 replay `.dem`，本项目也不需要自行下载 `.dem`。

1,470 次普通 GET 低于源码默认匿名日额度；按项目当前 1.05 秒节流，纯请求理论下限约 26 分钟，实际应为重试和落盘留出更长时间。若缺口需要 POST 解析，则成功率受 replay 是否仍存在和 OpenDota 队列影响，不能纳入“当天必定补齐”的验收承诺。

候选集合应使用 `match_id` 去重：两支 TI 队伍互相比赛仍只下载一次。筛选时必须同时固定 UTC `as_of`、稳定 team ID、OpenDota 原始 league tier 和 patch；如果目标实际是“当前五名选手的历史表现”，还必须按阵容生效区间补充其在旧 team ID 下的比赛，不能用当前战队名称回填历史。

## 建议的正式详情验收状态

每个 Game 建议记录一个互斥状态：

- `parsed_complete`：响应存在、10 名玩家、`has_parsed`、解析版本及必需字段通过；可进入完整 Fantasy 统计。
- `base_complete`：基础赛果与 10 名玩家存在，但未解析；仅进入胜负/基础 4 项模型，不进入其余 14 项 Fantasy 统计。
- `identity_incomplete`：玩家账号或队伍 ID 不完整；保留 raw，阻止依赖身份的训练。
- `parsed_field_incomplete`：声明已解析但必需字段/map 缺失；保留 null 并进入解析版本/patch 分组诊断。
- `unavailable`：404、请求失败或无法恢复；保留错误、尝试时间和请求元数据。

只有 `parsed_complete` 才与当前 255 场合格样本属于同一级别。发布 Fantasy 推荐前还必须单独通过 proxy 语义审计；解析完整不等于 Valve 结算语义已经验证。
