# Valve GetLeagueData 一手来源与 TI 2026 initial group 推断核验

- 研究截止：`2026-08-11T00:45:52Z`
- 赛事数据 `as_of`：`2026-08-10T13:45:12Z`（冻结 API/规则快照共同抓取时间）
- 范围：Valve 官方域名、仓库冻结响应及元数据
- 边界：未使用或访问 Liquipedia；未修改 `AGENTS.md`、`src/`、`config/`、`reports/` 或 `docs/publication/`
- 标记：`exact` = Valve 响应/规则原文直接给出；`derived` = 由多个 `exact` 事实推导；`absent` = 已核对响应结构但没有该字段

## 结论

1. 用户给出的 [`GetLeagueData?league_id=19719`](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719) 是 **Valve/Dota 官方一手机器可读来源**：它由 Dota 2 官方网站 `www.dota2.com` 的 HTTPS `/webapi/` endpoint 返回。Valve 自营的 [Dota 2 Steam 产品页](https://store.steampowered.com/app/570/Dota_2/?l=english)把 Developer、Publisher 都列为 Valve，并把 `www.dota2.com` 链接为 Dota 2 官方网站。
2. `league_id=19719`、`name="The International 2026"`、名为 `Swiss` 且 `node_group_id=2` 的阶段、16 支参赛队、8 个首轮节点、每个节点的稳定 team IDs 和 Unix 时刻，都是 `exact`。
3. API 的 8 个节点直接命名为 `Match 1.A`…`Match 4.A` 与 `Match 1.B`…`Match 4.B`。Valve 官方规则又直接规定 R1 拆成两个 Groups、首轮在组内比赛，R2/R3 只对 initial group，R4 只对 other group。因此，把四个 `.A` 节点内的八队派生为一个 initial group、四个 `.B` 节点内的八队派生为另一个 initial group，是 **高置信 `derived`**，不是 API 独立字段。
4. 冻结 API 响应没有逐队 `initial_group` 或 `group_id`；16 条 Swiss `team_standings` 也没有分组字段。8 个节点全部共享 `node_group_id=2`。所以不能把 `node_group_id=2` 误解为某一个 initial group，也不能把 A/B 成员表标成 API `exact`。
5. 该 endpoint 是官方一手数据，但本次没有找到 Valve 发布的稳定 schema/版本兼容承诺。应把它视为“指定 `as_of` 的官方响应快照”，而不是永远不变的公开 API 合约。

## 1. 域名与 endpoint 的官方性

### 1.1 域名证据

Valve 官方 Steam 商店的 [Dota 2 产品页](https://store.steampowered.com/app/570/Dota_2/?l=english)直接列出：

- Developer：Valve
- Publisher：Valve
- `Visit the website`：链接到 `www.dota2.com`

因此 `www.dota2.com` 是由 Valve 官方渠道指认的 Dota 2 官方网站。用户 URL 的 scheme/host 是 `https://www.dota2.com`，并非社区镜像或第三方代理。

### 1.2 endpoint 与冻结响应

完整请求：

`https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719`

仓库冻结材料：

- 响应：[response.json](../../data/raw/valve/ti2026-league/20260810T134512Z-73519bcb40a4/response.json)
- 元数据：[metadata.json](../../data/raw/valve/ti2026-league/20260810T134512Z-73519bcb40a4/metadata.json)
- `fetched_at`：`2026-08-10T13:45:12Z`
- bytes：`85,406`
- SHA-256：`73519bcb40a40a02de7a3b343ce3daf4a5786d449d058d3300569b1bbea84c2a`

本次重新计算文件 SHA-256，与元数据一致。元数据把资源记为 `IDOTA2League/GetLeagueData/v001`、参数记为整数 `league_id=19719`。这足以确认该结论针对哪一次官方响应；后续 live endpoint 即使变化，也不改变此快照在 `as_of` 时的内容。

官方性必须与解释范围分开：官方域名与官方响应使其中字段成为一手事实，但不会自动把项目对字段的组合解释也变成 Valve 原话。

## 2. API 直接事实（`exact`）

### 2.1 联赛与 Swiss 容器

| JSON 位置/字段 | API 值 | 标记 | 说明 |
| --- | --- | --- | --- |
| `info.league_id` | `19719` | `exact` | 请求参数与响应联赛 ID 一致 |
| `info.name` | `The International 2026` | `exact` | 赛事名由响应直接给出 |
| `info.url` | `https://www.dota2.com/esports` | `exact` | 响应自身指向官方电竞入口 |
| `info.start_timestamp` | `1786492800` | `exact` | 转换为 `2026-08-12T00:00:00Z` 是确定性 `derived` |
| `info.end_timestamp` | `1787554800` | `exact` | 转换为 `2026-08-24T07:00:00Z` 是确定性 `derived` |
| Swiss `name` | `Swiss` | `exact` | 位于顶层赛事阶段容器的嵌套 `node_groups` |
| Swiss `node_group_id` | `2` | `exact` | 这是整个 Swiss 阶段的 node group ID |
| Swiss `parent_node_group_id` | `1` | `exact` | 上级阶段容器 |
| Swiss `team_count` / standings 数量 | `16` / `16` | `exact` | 全部 16 队列在同一 Swiss standings 中 |
| Swiss `round` / `max_rounds` | `1` / `5` | `exact` | 快照时阶段轮次字段与最多轮数 |
| Swiss nodes 数量 | `8` | `exact` | 当前填充的 8 个节点 |

### 2.2 八个节点、稳定 team IDs 与时刻

下表的节点名、IDs、队伍字符串、`scheduled_time` 均为 API `exact`；UTC 文本是对 Unix seconds 的无损确定性转换，标记为 `derived`。名称仅用于显示，连接应使用 team ID。API 中 `Nigma Galaxy ` 末尾带空格，下表为显示而 trim，不改变 ID。

| node | 名称 | team_id_1 / API 名称 | team_id_2 / API 名称 | `scheduled_time` (`exact`) | UTC (`derived`) | `node_group_id` |
| ---: | --- | --- | --- | ---: | --- | ---: |
| 1 | `Match 1.A` | `9247354` Team Falcons | `10150538` LGD Gaming | `1786586400` | `2026-08-13T02:00:00Z` | `2` |
| 2 | `Match 2.A` | `10150413` Iron Wing | `10136357` Nigma Galaxy | `1786586400` | `2026-08-13T02:00:00Z` | `2` |
| 3 | `Match 3.A` | `8255888` BoomBoys | `2586976` OG | `1786586400` | `2026-08-13T02:00:00Z` | `2` |
| 4 | `Match 4.A` | `9572001` TEAM VISION | `5017210` Team Resilience | `1786586400` | `2026-08-13T02:00:00Z` | `2` |
| 5 | `Match 1.B` | `7119388` Team Spirit | `8261500` Xtreme Gaming | `1786597200` | `2026-08-13T05:00:00Z` | `2` |
| 6 | `Match 2.B` | `2163` Team Liquid | `726228` Vici Gaming | `1786597200` | `2026-08-13T05:00:00Z` | `2` |
| 7 | `Match 3.B` | `9467224` Aurora Gaming | `9964962` GamerLegion | `1786597200` | `2026-08-13T05:00:00Z` | `2` |
| 8 | `Match 4.B` | `9823272` Team Yandex | `10149530` HULIGANI | `1786597200` | `2026-08-13T05:00:00Z` | `2` |

在该 `as_of`，这 8 个节点还共同具有 `actual_time=0`、`series_id=0`、`has_started=false`、`is_completed=false`。这些状态也是 `exact`，但只表示抓取时点，不能外推到赛后。

## 3. API 明确没有给出的信息（`absent`）

对冻结 JSON 做了字段级核对：

- 完整响应中字符串 `initial_group` 出现次数为 `0`。
- 完整响应中独立属性名 `"group_id"` 出现次数为 `0`。
- Swiss `team_standings` 的属性是 `standing`、`team_id`、名称/标志、胜负/分数及 tiebreak 字段，没有 initial group 字段。
- 节点具有 `node_group_id`，但 8 个节点该值全部为 `2`。
- Swiss 容器内 16 条 standings 也全部放在同一 `node_group_id=2` 的阶段对象中，没有拆成两个嵌套 node group。

因此以下说法不成立：

- “API 有一个逐队 `initial_group=A/B` 字段。”
- “A 组是 `node_group_id=1`，B 组是 `node_group_id=2`。”
- “`.A/.B` 成员表是从两个独立 node group 对象直接读取的。”

这里的 `node_group_id=2` 是名为 `Swiss` 的赛制阶段容器；`.A/.B` 是节点 `name` 的后缀。两者是不同层级的概念。

## 4. Valve 官方规则直接事实（`exact`）

规则证据来自 Valve 官方 TI 规则页面所加载的 English localization chunk：

- 官方规则入口：[TI 2026 Rules](https://www.dota2.com/esports/ti15/tirules)
- 官方响应 URL：[dota_react/6777.js](https://www.dota2.com/public/javascript/dota_react/6777.js?contenthash=652ea487b0024989f20b&l=english&_cdn=fastly)
- 冻结响应：[response.js](../../data/raw/valve/ti2026-rules/20260810T134512Z-e55e2d979f0d/response.js)
- 元数据：[metadata.json](../../data/raw/valve/ti2026-rules/20260810T134512Z-e55e2d979f0d/metadata.json)
- `fetched_at`：`2026-08-10T13:45:12Z`
- bytes：`214,643`
- SHA-256：`e55e2d979f0de1f2b16890b4ea6ed4d1e8ba0c47752a2bfdb1dc86e8829bbf6c`

本次重新计算规则文件 SHA-256，同样与元数据一致。相关 token 原文：

| 轮次 | Valve token | 官方英文 | 标记 |
| --- | --- | --- | --- |
| R1 | `ti15_swiss_rules3_1_1` | `Teams are split into two different Groups` | `exact` |
| R1 | `ti15_swiss_rules3_1_2` | `Matchups are set by the tournament organizer, with teams playing other members of their group` | `exact` |
| R2 | `ti15_swiss_rules3_2_1` | `Teams are only matched against other members of their initial group` | `exact` |
| R3 | `ti15_swiss_rules3_3_1` | `Teams are only matched against other members of their initial group` | `exact` |
| R4 | `ti15_swiss_rules3_4_1` | `Teams are only matched against members of the other group` | `exact` |

这些规则直接证明 initial groups 真实存在，并决定 R1–R4 的组内/跨组约束；它们仍没有逐队列出 A/B 成员。

## 5. `.A/.B` initial group 成员推断（`derived`）

### 5.1 证据链

1. **API `exact`：** Swiss 阶段恰有 8 个已填充节点；4 个节点后缀为 `.A`，另 4 个为 `.B`。
2. **API `exact`：** 每一批包含 4 场、8 个互不重复的稳定 team IDs；A 批统一在 `02:00Z`，B 批统一在 `05:00Z`。
3. **规则 `exact`：** R1 把队伍拆成两个 Groups，且首轮对手来自本组。
4. **规则 `exact`：** R2/R3 继续使用 initial group，R4 改为 other group，说明这两个初始组具有后续赛制语义，不只是转播时段。
5. **项目 `derived`：** 将 `.A` 四场的八队称为 initial group A，将 `.B` 四场的八队称为 initial group B。

第 5 步是强依据推断。高置信来自“恰好两种后缀 + 恰好两个官方 Groups + 每批正好八队 + R1 组内赛”的共同约束；但 Valve API 没有字段直接写出 `team 9247354 initial_group A`，所以不能升级成 `exact`。

### 5.2 派生的两个 initial groups

| 派生标签 | 稳定 team ID | API 显示名 | 来源节点 | 标记 |
| --- | ---: | --- | --- | --- |
| A | `9247354` | Team Falcons | `Match 1.A` | `derived` |
| A | `10150538` | LGD Gaming | `Match 1.A` | `derived` |
| A | `10150413` | Iron Wing | `Match 2.A` | `derived` |
| A | `10136357` | Nigma Galaxy | `Match 2.A` | `derived` |
| A | `8255888` | BoomBoys | `Match 3.A` | `derived` |
| A | `2586976` | OG | `Match 3.A` | `derived` |
| A | `9572001` | TEAM VISION | `Match 4.A` | `derived` |
| A | `5017210` | Team Resilience | `Match 4.A` | `derived` |
| B | `7119388` | Team Spirit | `Match 1.B` | `derived` |
| B | `8261500` | Xtreme Gaming | `Match 1.B` | `derived` |
| B | `2163` | Team Liquid | `Match 2.B` | `derived` |
| B | `726228` | Vici Gaming | `Match 2.B` | `derived` |
| B | `9467224` | Aurora Gaming | `Match 3.B` | `derived` |
| B | `9964962` | GamerLegion | `Match 3.B` | `derived` |
| B | `9823272` | Team Yandex | `Match 4.B` | `derived` |
| B | `10149530` | HULIGANI | `Match 4.B` | `derived` |

“A/B”在本表中是对官方节点后缀的项目标签，不应被描述成 Valve 单独发布的 per-team 分组字段。实现或产物中应继续保留类似 `initial_group_provenance="derived"` 的来源标记。

## 6. 可发布表述与不可发布表述

| 表述 | 是否准确 | 推荐措辞 |
| --- | --- | --- |
| “这是 Valve/Dota 官方 API 的一手响应。” | 是 | 同时注明 URL、`fetched_at`、SHA-256 与 `as_of` |
| “API 直接给出了 8 场节点、team IDs 和时间。” | 是 | 节点/原始 Unix time 标 `exact`；UTC 转换标 `derived` |
| “Valve 规则明确存在两个 initial groups。” | 是 | 引 R1–R4 官方 token |
| “API 直接给出了每队 initial group。” | 否 | 改为“由 `.A/.B` 节点和官方 R1 组内规则派生” |
| “A/B 是两个不同的 `node_group_id`。” | 否 | 说明 8 节点都属于 Swiss `node_group_id=2` |
| “`.A/.B` 与 initial groups 完全无关，只是时间段。” | 证据不支持 | 两批时刻不同是 `exact`，但结合规则，成员池解释为 high-confidence `derived` |

## 7. 复现检查

对冻结快照可执行以下只读检查：

1. 核对响应 SHA-256 与元数据。
2. 读取 `info.league_id`、`info.name`。
3. 在嵌套 `node_groups` 中按 `node_group_id=2` 定位 `name="Swiss"`。
4. 断言 Swiss `nodes` 数量为 8、名称集合为 `Match 1.A`…`Match 4.B`。
5. 断言 8 节点的 `node_group_id` 唯一集合为 `{2}`。
6. 断言所有 `team_id_1/team_id_2` 共 16 个且无重复，并用 Swiss standings 的稳定 ID 映射显示名。
7. 断言不存在逐队 `initial_group`/`group_id` 属性；再以规则 token 记录 A/B 派生证据。

这一顺序能保证 API 直接事实和项目派生事实不会在后续模拟或发布中混写。
