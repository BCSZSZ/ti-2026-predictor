# TI 2026 Fantasy 五项 proxy 的来源核验

日期：2026-08-06

范围：Red / Madstones；Blue / Smokes、Watchers、Lotuses；Green / Tormentor

结论状态：已找到并接入可落地的 exact 来源；历史 backfill 进度见
[`P1 实装报告`](../reports/p1-native-replay-stats-implementation-2026-08-06.md)

## 结论

**这五项可以完全解决，但解决方式不是把现有 OpenDota map proxy 改名为 exact，而是从完整 replay 的 `CDOTA_DataRadiant` / `CDOTA_DataDire` → `m_vecDataTeam` 读取 Valve 原生逐人计数。**

当前客户端存在五个对应的网络字段：

| Fantasy stat | replay 原生字段 | 接入后 provenance |
|---|---|---|
| Madstone Collected | `m_iNeutralTokensFound` | `exact` |
| Smokes Used | `m_iSmokesUsed` | `exact` |
| Watchers Taken | `m_iWatchersTaken` | `exact` |
| Lotuses Grabbed | `m_iLotusesTaken` | `exact` |
| Tormentor Kills | `m_iTormentorKills` | `exact` |

本机客户端、Valve 的 Fantasy protobuf，以及六场跨越 2026 年 1 月至 8 月的 replay 实测差分三条证据互相吻合。现有 `item_uses`、`ability_uses`、`killed` 只能描述相邻事件，在五项上均已观察到与原生计数不一致，因此不能作为正式 exact 数据。

## 游戏实际计分语义

本机保存的 TI 2026 客户端规则快照明确写着：

- Smoke：玩家**使用**一枚 Smoke of Deceit；
- Madstone：玩家**收集的每一片** Madstone；
- Watcher：玩家**完成 capture**；
- Lotus：玩家**从池中拿取** Lotus；
- Tormentor：玩家**参与**一次 Tormentor 击杀。

来源是 `data/raw/rules/20260802T071030Z-803d58a3f861/resource/localization/dota_english.txt` 第 45065–45090、45136–45140 行；对应 TI 2026 基础分值在 `scripts/events/international_2026.eventdef` 第 1023–1027 行。尤其要注意，Tormentor 的英文是 “participates in a Tormentor kill”，不是最后一击。

本机当前客户端为 build 6884、SourceRevision 10879186；`steam.inf` 标注 `Aug 03 2026 15:49:07`。核验文件：

- `C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\bin\win64\client.dll`
  - 修改时间（UTC）：2026-08-04 04:01:02
  - SHA-256：`1D2B2AD077AE34B8F7F94083A65B32F32BC423142124C6C2E195CABE100C0C48`
- `C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\steam.inf`
  - SHA-256：`2BE6EFD2415706090AA6348797FB6F816CDB2CB19240CDE3E071C1AC5677D7A5`

`client.dll` 的 schema strings 包含上述五个字段。相同 build 的生成 schema 可在 [SteamTracking `DataTeamPlayer_t`](https://github.com/SteamTracking/GameTracking-Dota2/blob/b23a34da9b83ab798b726885dc81be881e3496e4/DumpSource2/schemas/client/DataTeamPlayer_t.h#L87-L95) 复核。该结构同时包含 `m_nAcquiredMadstone` 和 `m_nCurrentMadstone`，但它们不应凭名称猜测为 Fantasy Madstone：实测及 2025 的纠错记录都指向 `m_iNeutralTokensFound`。

## Valve 服务端也保存了同一组 Fantasy 计数

Valve GC / game-server protobuf 的 `CMsgDOTAFantasyPlayerStats` 直接包含 `smokes`、`watchers`、`lotuses`、`tormentors`、`madstone` 五个字段，见 [OpenDota 同步的 Valve protobuf](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/proto/dota_gcmessages_common.proto#L1107-L1135)。比赛 sign-out 消息也携带 `fantasy_stats`，见 [`dota_gcmessages_server.proto`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/proto/dota_gcmessages_server.proto#L325-L337)。

这证明服务器本身计算的是独立 Fantasy 计数，而不是临时用 `item_uses` 等 map 拼出来。不过，当前 OpenDota match API 没有把这组 sign-out 字段作为标准逐人响应公开出来；因此现实可用的 exact 路线是重放 replay，从 DataTeam 网络实体读取同源的逐人累积值。

OpenDota parser 本来就会按玩家的 team slot 从同一个 DataTeam 实体读取 deny、wards、camps、runes、tower、Roshan 等计数，见 [`Parse.java`](https://github.com/odota/parser/blob/02b78c6ca0010b5ed64a800c23212040c28d35ce/src/main/java/opendota/Parse.java#L639-L688)。新增这五个属性读取不需要重建战斗事件或猜测归属。

## 六场 replay 的差分实测

最初在临时 clone 的 `odota/parser@02b78c6ca0010b5ed64a800c23212040c28d35ce` 中，仅为逐人输出增加上述五个 DataTeam 字段，然后解析六场完整 replay。P1 的正式最小 parser 改为读取 replay 最终 DataTeam 实体，而不是 OpenDota parser 最后一个固定间隔采样。样本覆盖 2026-01-02、02-06、03-25、05-16、07-19 和 08-01；每场 10 名玩家的五个 DataTeam 字段都被实际观察到。proxy 列严格复现本项目旧映射。

P1 回归发现并纠正了一处冻结前的 fixture 误差：8680265600 的 Dire slot 131 在最后一个固定间隔采样时为 40，但最终 DataTeam 值为 43；因此该场 Madstone 正式 exact 合计为 104，而非 101。其余 299 个逐人字段与临时审计输出一致。正式 fixture 以最终实体值为准，这也是 Fantasy 结算所需的累积终值。

| Match | Madstone exact / proxy | Smoke exact / proxy | Watcher exact / proxy | Lotus exact / proxy | Tormentor exact / proxy |
|---|---:|---:|---:|---:|---:|
| 8631262616 | 335 / 104 | 14 / 14 | 23 / 34 | 17 / 15 | 6 / 2 |
| 8680265600 | 104 / 34 | 5 / 5 | 12 / 17 | 10 / 10 | 0 / 0 |
| 8743439140 | 360 / 110 | 14 / 14 | 37 / 64 | 21 / 14 | 8 / 2 |
| 8813352696 | 184 / 62 | 8 / 8 | 20 / 34 | 16 / 8 | 2 / 1 |
| 8904419709 | 290 / 93 | 13 / 12 | 20 / 32 | 19 / 12 | 0 / 0 |
| 8924770688 | 360 / 115 | 12 / 12 | 29 / 44 | 26 / 18 | 8 / 2 |
| **合计** | **1633 / 518** | **66 / 65** | **141 / 225** | **109 / 77** | **24 / 7** |

按逐人值比较，proxy 与原生计数相等的比例分别为 Madstone `10/60`、Smoke `59/60`、Watcher `23/60`、Lotus `38/60`、Tormentor `47/60`。Tormentor 的相等率被大量双方均为零的行抬高；在有击杀的场次中差异很大。

临时诊断输出：

- `ti-proxy-match-8904419709.json` SHA-256：`7321212C4A7D65BE4169FF665676449E5584D8E365BB37E204A4036ADB6A6426`
- `ti-proxy-match-8924770688.json` SHA-256：`107E915ADB68AB2353EEA1B3489C7E2E743CEBF7C72DD8573D2319E1911DA284`
- `ti-proxy-match-8631262616.json` SHA-256：`7F01F2BBF0AD359500FD448D22FA5075EEE16A74FBF1399E987BD1CA26821A08`
- `ti-proxy-match-8680265600.json` SHA-256：`568B3E9175F6C6B6BC4F85B6BC08AF24E403F10B4AB1C71938056F3BDD5224B6`
- `ti-proxy-match-8743439140.json` SHA-256：`736C2971387B257AEF6E1957549441A8111AA9923921C1D74C4A299E07E3ECB8`
- `ti-proxy-match-8813352696.json` SHA-256：`A01EDC5F04F2B7748C81082D104F525E933EEA566DB93F33999FE60F5F5B19A5`

这是决定性反例：五个 proxy 中连最接近语义的 Smoke 也在 8904419709 Dire 出现 5 对 6；Tormentor 在 8924770688 Dire 是五名参与者合计 8 次，而 `killed.npc_dota_miniboss` 只有两个最后击杀事件。

这些临时文件只用于来源审计，不是可复现训练快照。正式接入时仍必须保存 replay 原始响应、下载参数、抓取时间与 SHA-256，并记录 parser commit、客户端规则版本和 `as_of`。

## 为什么五个现有 proxy 都不能升级

OpenDota parser 会初始化 `item_uses`、`ability_uses`、`killed` map，并在 combat log 事件出现时递增。其实现见 [`CreateParsedDataBlob.java`](https://github.com/odota/parser/blob/02b78c6ca0010b5ed64a800c23212040c28d35ce/src/main/java/opendota/CreateParsedDataBlob.java#L690-L776)。这些 map 的精确定义是“物品 use 事件”“技能 use 事件”和“攻击者杀死某单位”，不是 Fantasy 字段本身。

### Madstone

当前 proxy 是 `item_uses.madstone_bundle`。客户端 `item_madstone_bundle` 为拾取即施放，而且一个 bundle 的配置值为 `madstone_primary = 2 3 4`、`madstone_secondary = 1 2 3`；一次 use 可以增加多片 Madstone。实测 exact 大约是 bundle use 的三倍，不能用固定倍数修复，因为 bundle 档位不同。

判定：现 proxy 继续标 `proxy`，正式值改读 `m_iNeutralTokensFound` 并标 `exact`。

### Smoke

当前 proxy 是 `item_uses.smoke_of_deceit`，语义最接近，但 combat-log item use 并不保证与 DataTeam 最终累计值逐场等价。六场 60 个逐人值中已有一人出现少计，合计为 65 对 66。

判定：现 proxy 仍标 `proxy`，不得因为大多数样本相同而升级；正式值读 `m_iSmokesUsed`。

### Watcher

当前 proxy 是 `ability_uses.ability_lamp_use`。它统计技能 use/cast 事件；Fantasy 要求 capture 成功。开始引导、重复尝试或被打断都可能使 use 数高于成功 capture。六场中 proxy 合计为 225，原生计数仅 141，逐人只相等 23/60。

判定：现 proxy 继续标 `proxy`；正式值读 `m_iWatchersTaken`。

### Lotus

当前 proxy 汇总 `item_uses.famango`、`great_famango`、`greater_famango`。这统计的是拿到背包之后的消耗，不是从 Lotus Pool 取出。Lotus 还能转交；三个普通 Lotus 可合成 Great、两个 Great 可合成 Greater，因此既会错归玩家，也会错计基础 Lotus 数量。

判定：现 proxy 继续标 `proxy`；正式值读 `m_iLotusesTaken`。

### Tormentor

当前 proxy 是 `killed.npc_dota_miniboss`，只归给击杀事件的 attacker；Fantasy 明确给每个参与者计分。8924770688 的 8 对 2 已直接证伪尾刀映射。

判定：现 proxy 继续标 `proxy`；正式值读 `m_iTormentorKills`。

## Reddit 指南能证明什么、不能证明什么

[用户给出的 2026 指南](https://www.reddit.com/r/DotA2/comments/1vble84/fantasy_league_2026_guide/) 确实给出了这五项的非零历史统计和排序，因此是“replay 内存在可取数据”的强线索；但帖子没有公开代码、逐场 match id、字段映射和缺失处理，不能单独把本项目的 proxy 升为 exact。

更关键的是作者的 [2025 TI 更新](https://www.reddit.com/r/DotA2/comments/1nblgct/fantasy_league_guide_2025_the_international/)：作者明确纠正了 Madstone，称先前使用了类似 acquired-Madstone 的字段，正确值在 `m_iNeutralTokensFound`；同时说明旧赛事 replay 的 Watcher 字段曾恒为 0，Valve 后来修复。这与本机 schema 和本次 replay 差分一致，但也提出一个必要限制：**字段存在不等于所有历史 build 的值都可信。**

所以社区指南应当用于发现字段和结果 sanity check；正式来源仍是当前客户端规则、Valve 网络 schema、完整 replay 与版本化差分测试。

## `0`、`null` 与发布规则

### DataTeam exact 字段

- replay 完整解析成功；对应 client/parser build 已在支持白名单；玩家 stable ID 与 team slot 有效；最终 DataTeam 实体和字段确实被观察到：原生整数 `0` 是有效的 `exact` 零。
- replay 不可得、下载/解析失败或截断、字段在该 schema 中不存在、最终实体未观察到、玩家/slot 无法可靠连接：必须为 `null`，不得把 getter 默认的 0 当作观测值。
- Watcher 所属旧 build 已知有“恒 0” replay bug，或者 build 尚未通过非零 fixture：该字段应为 `unavailable` / `null`，不能发布为 exact 0。
- protobuf 字段为 optional 时必须保留 presence；未出现不能按生成代码 getter 的默认 0 处理。

### 旧 OpenDota maps

- `has_parsed` 且完整 map 存在、目标 key 不存在，只能说明该 **proxy 事件**为 0。
- 它不能说明对应 Fantasy exact 值为 0；Madstone、Watcher、Lotus、Tormentor 已证明二者语义不同，Smoke 也已出现实测漏计。
- 因此 maps 可保留在敏感性分析或旧覆盖报告中，provenance 必须是 `proxy`；不得回填 exact 列，也不得让 proxy 的 0 覆盖 exact 的 `null`。

## 正式接入的最小验收门槛

1. 在受版本控制的 replay parser/adapter 中读取五个 DataTeam 字段；正式逻辑放在 `src/`，不依赖临时 clone。
2. 记录 replay SHA-256、match id、抓取时间、来源参数、parser commit、客户端 build、规则快照与显式 UTC `as_of`。
3. 先用本次六场作为回归 fixture，逐人而非仅队伍汇总验证 exact 数值；另补一场五项均有非零值的受控 fixture。
4. 对每个受支持 build 做“字段 presence、合法 team slot、最终状态已读取”的断言；失败输出 `null`，不静默降级。
5. 单独建立 Watcher build 白名单；已知 replay bug 的旧版本排除，不把全零数据纳入历史期望。
6. 若能取得 GC / 游戏结算页的 `CMsgDOTAFantasyPlayerStats`，对同一场逐人差分；完全一致后才把新列发布为 `exact`。
7. 现有五项 proxy 只保留为诊断对照。正式统计、求解器与人工手册只使用 exact 数据；缺失就明确降覆盖，不混合口径。

## 最终判定

用户的问题可以肯定回答：**能完全解决。** 完整 replay 已经携带与 Fantasy 语义一一对应的逐人原生计数，计算成本只是解析 replay 和读取五个累积字段，不需要用事件规则重新推断。但“完整解决”有两个边界：没有 replay 就不能从现有 OpenDota match JSON 无损恢复；旧 Watcher bug 等版本必须保留 `null`。在这两个边界内，五项均可从 `proxy` 升为 `exact`。
