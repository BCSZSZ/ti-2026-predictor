# TI 2026 战队展示别名与注册身份审计（2026-08-11）

## 结论

以 `2026-08-10T13:45:12Z` 为 `as_of`，Valve 当前 The International 2026 名单共有 16 支队伍。确认其中 4 支使用了与博彩品牌名称不同的 TI 展示名：

- `BoomBoys` = `BetBoom Team`
- `Iron Wing` = `1win / 1w Team` 在 TI 的展示名
- `HULIGANI` = `L1GA TEAM` 在 TI 的展示名
- `TEAM VISION` = `PARIVISION` 在 TI 的展示名

这 4 项属于展示名或赛事注册身份变化，不是新战队。全量比赛身份审计还确认了 Team Resilience、Xtreme Gaming 和 LGD Gaming 的赛事临时注册 ID。最终需要 9 条有明确有效期的 identity bridge。

名称只用于展示；连接、训练和统计仍必须使用稳定队伍 ID，并受显式 UTC 有效期和 `as_of` 约束。

## 冻结基准

Valve 联赛响应是当前 16 队名单和展示名的最高优先级基准：

- 路径：`E:/Code/TI预测/data/raw/valve/ti2026-league/20260810T134512Z-73519bcb40a4/response.json`
- 请求：`https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719`
- 抓取 UTC：`2026-08-10T13:45:12Z`
- SHA-256：`73519bcb40a40a02de7a3b343ce3daf4a5786d449d058d3300569b1bbea84c2a`
- 元数据：`E:/Code/TI预测/data/raw/valve/ti2026-league/20260810T134512Z-73519bcb40a4/metadata.json`

本机客户端规则快照用于交叉核对 TI Fantasy 注册阵容：

- 路径：`E:/Code/TI预测/data/raw/rules/20260810T134439Z-f26cfd47ab1d/rule_snapshot.json`
- 快照 UTC：`2026-08-10T13:44:39Z`
- SHA-256：`eb3c30f542a2ee7fde1d101fdf57bd9f2f729730ccf6707c893d4e9b938cccb3`

## 当前 16 队全表

| Valve 稳定 ID | Valve 当前展示名 | 身份审计结论 | 需要的处理 |
|---:|---|---|---|
| `2163` | Team Liquid | 当前组织名；未发现博彩展示别名 | 无 |
| `8255888` | BoomBoys | BetBoom Team 的 TI 展示别名 | 保留当前 ID；不要按名称吸收其他同名 ID |
| `8261500` | Xtreme Gaming | 当前组织名；GOTF 使用了临时注册 ID | bridge `10208071 → 8261500` |
| `9247354` | Team Falcons | 当前组织名；未发现博彩展示别名 | 无 |
| `9467224` | Aurora Gaming | 当前组织名；未发现博彩展示别名 | 无 |
| `9823272` | Team Yandex | 当前组织名；未发现博彩展示别名 | 无 |
| `10150413` | Iron Wing | 1win / 1w Team 当前阵容的 TI 展示名 | bridge `10182357 → 10150413`；应用 registration identity window |
| `726228` | Vici Gaming | 当前组织名；未发现博彩展示别名 | 无 |
| `5017210` | Team Resilience | 当前组织名；存在一次性和 GOTF 注册 ID | bridge `9316703/10207984 → 5017210`；应用 registration identity window |
| `10150538` | LGD Gaming | 当前 LGD 组织；GOTF 使用 LGD.Pinghu 注册名 | bridge `10208068 → 10150538`；不得继承 HEROIC 历史 |
| `2586976` | OG | 当前组织名；未发现博彩展示别名 | 无 |
| `9964962` | GamerLegion | 当前组织名；未发现博彩展示别名 | 无 |
| `10136357` | Nigma Galaxy | 当前组织名；未发现博彩展示别名 | 无 |
| `10149530` | HULIGANI | L1GA TEAM 的 TI 展示别名 | bridge `9303383/10182299/10208009 → 10149530` |
| `9572001` | TEAM VISION | PARIVISION 的 TI 展示别名 | bridge `9824702 → 9572001` |
| `7119388` | Team Spirit | 当前组织名；未发现博彩展示别名 | 无 |

## 4 个博彩展示别名

| Valve 当前身份 | 原组织或常用名 | 生效证据 | 分类 |
|---|---|---|---|
| `8255888 BoomBoys` | BetBoom Team | Valve 在 [2026-05-25 邀请公告](https://steamcommunity.com/games/dota2/announcements/detail/655981180194128454)中以 BoomBoys 列出 Kiritych、gpk、MieRo、Save、Kataomi；[BetBoom 官方 roster](https://betboom.team/)列出同五人 | 同一队伍的展示别名；稳定 ID 已一致 |
| `9572001 TEAM VISION` | PARIVISION | [PARIVISION 官方声明](https://t.me/PARIVISIONDota2/4649)于 `2026-06-22T06:30:13Z` 明确表示因 Valve 规则在 TI 2026 封闭预选期间成为 TEAM VISION；[官方队伍页](https://parivision.gg/teams/dota-2/)阵容一致 | 明确的规则驱动展示别名 |
| `10149530 HULIGANI` | L1GA TEAM | [L1GA TEAM 官方声明](https://t.me/L1GATEAM/3500)于 `2026-06-18T17:00:24Z` 明确宣布 Road to International 2026 使用 HULIGANI tag；同一官方频道继续代表该组织和阵容 | 明确的赛事展示 tag |
| `10150413 Iron Wing` | 1win / 1w Team | [1win 官方声明](https://t.me/Official_1winn/7149)于 `2026-07-26T18:02:56Z` 明确称 Pure、bzm、33、Ari、Whitemon 将以 Iron Wing 参赛；[1win 收购声明](https://www.globenewswire.com/news-release/2026/06/02/3304922/0/en/1win-signs-full-tundra-roster-under-the-1win-team-banner.html)说明该阵容自 `2026-06-01` 起代表 1win | 展示别名，但其前身 Tundra 阶段是真实组织转会边界 |

博彩限制的具体法律解释不是本审计的连接依据。连接依据是 Valve 当前注册身份、俱乐部一手声明、稳定账号 ID 阵容一致性以及有效期；不得仅凭名称相似或社区说法合并。

## 应用的 9 条 identity bridge

所有 `valid_to` 和 `evidence_as_of` 均为 `2026-08-10T13:45:12Z`。`valid_from` 是当前冻结证据允许映射的保守下界，而不是对组织成立日期的声明。

| raw team ID / 原始名 | canonical team ID / 当前名 | `valid_from` UTC | 冻结阵容证据 | 原因 |
|---|---|---|---|---|
| `9303383 L1GA TEAM` | `10149530 HULIGANI` | `2026-03-16T08:17:12Z` | `92487440, 123787715, 140251702, 145065875, 320017600` | 长期组织 ID 与 TI 展示身份接续 |
| `10182299 L1 TEAM` | `10149530 HULIGANI` | `2026-07-07T12:18:00Z` | `92487440, 111030315, 123787715, 140251702, 320017600` | 同组织 EWC 注册；`111030315` 为该期 stand-in，不应把缺少 sayuw 误判成新队 |
| `10208009 L1GA TEAM` | `10149530 HULIGANI` | `2026-07-31T12:27:48Z` | `92487440, 123787715, 140251702, 145065875, 320017600` | GOTF 临时注册 ID，五人完全一致 |
| `10182357 1w` | `10150413 Iron Wing` | `2026-07-07T18:16:19Z` | `86698277, 93618577, 136829091, 331855530, 346412363` | 1win 名称与 TI 展示身份接续，五人完全一致 |
| `9824702 PVISION` | `9572001 TEAM VISION` | `2026-05-26T08:01:27Z` | `73401082, 106573901, 164199202, 195108598, 1044002267` | PARIVISION 注册身份与 TEAM VISION 展示身份接续 |
| `9316703` | `5017210 Team Resilience` | `2026-04-08T09:08:01Z` | `145957968, 150961567, 170896543, 249835593, 315272623` | 一次性赛事注册 ID，五人完全一致 |
| `10207984 Team resilience` | `5017210 Team Resilience` | `2026-07-31T09:33:01Z` | `145957968, 150961567, 170896543, 249835593, 315272623` | GOTF 临时注册 ID，五人完全一致 |
| `10208071 Xtreme Gaming` | `8261500 Xtreme Gaming` | `2026-07-31T17:31:28Z` | `94296097, 101695162, 129958758, 173978074, 898754153` | GOTF 临时注册 ID，名称和五人均一致 |
| `10208068 LGD.Pinghu` | `10150538 LGD Gaming` | `2026-07-31T17:31:28Z` | `81306398, 105045291, 177203952, 292921272, 1026694469` | GOTF 赛事注册名；与当时 LGD 五人完全一致 |

[Games of the Future 官方参赛名单](https://gofuture.games/page/games-of-the-future-2026/)和[官方抽签公告](https://gofuture.games/news/item/official-draw-decides-opening-matches-at-gotf-2026/)分别记录了 Team resilience、Xtreme Gaming、L1GA TEAM 与 LGD.Pinghu 等赛事展示名。赛事网页只用于确认注册名称；实际连接仍由冻结稳定账号 ID 证据完成。

## Registration identity windows

Bridge 只能解决“另一个 raw ID 应映射到谁”，不能阻止当前 canonical ID 在历史上被其他身份复用。因此还必须给当前注册身份设置生效窗口。

| canonical ID | 当前注册身份从何时生效 | 处理 |
|---:|---|---|
| `10150413 Iron Wing` | `2026-06-01T00:00:00Z` | 只从 1win 收购 Tundra 当前五人正式生效后承认该 canonical identity；例如 `2026-05-30` 使用此 raw ID 的行不得因 ID 相同自动进入当前 Iron Wing 历史 |
| `5017210 Team Resilience` | `2026-04-08T09:08:01Z` | 只从当前 Team Resilience 冻结身份首次被验证时承认该 canonical identity；更早年代复用 `5017210` 的比赛必须排除 |

两个窗口的上界均为本审计 `as_of`：`2026-08-10T13:45:12Z`。未来证据不得回流进本次运行。

## 不得合并的反例

### Tundra Esports 与 Iron Wing

`8291895 Tundra Esports` 不得映射到 `10150413 Iron Wing`。Valve 的 2026-05-25 邀请公告仍将 Pure、bzm、33、Ari、Whitemon 列为 Tundra Esports；1win 的一手声明明确收购从 `2026-06-01` 生效。这是同一阵容发生真实组织转会，不是单纯显示名变化。

阵容连续性可以用于解释转会，但不能把 Tundra 组织历史和奖金继承给 Iron Wing / 1win。

### HEROIC 与 LGD Gaming

`9303484 HEROIC` 不得映射到 `10150538 LGD Gaming`。[HEROIC 官方 2026 roster](https://heroic.gg/atc/changing-lanes---heroic-dota-2%E2%80%99s-2026-roster-moves)证明这些选手此前属于 HEROIC；[LGD 官方签约公告](https://x.com/LGDgaming/status/2059140327219577215)记录了 2026-05-26 的新组织身份。该边界同样属于真实转会。

GOTF 的 `10208068 LGD.Pinghu` 位于 LGD 签约之后且五人完全一致，因此可以桥接；签约前 HEROIC 历史不可以。

### 无关同名 BoomBoys

`10163435 BoomBoys` 不得映射到 `8255888 BoomBoys`。前者只出现在 2026-05-31 至 2026-06-07 的 SIVVIT League，缺少与 BetBoom 当前五人的稳定账号证据，是无关同名碰撞。

这也是禁止“按规范化队名自动合并”的直接反例。BetBoom 的 TI 展示身份应由 Valve ID `8255888` 和已核验阵容确定，而不是由字符串 `BoomBoys` 确定。

## 实现约束

- 先保留 `radiant_raw_team_id` / `dire_raw_team_id`，再在有效期内生成 canonical team ID，确保审计可逆。
- bridge 必须同时满足 `valid_from <= match.start_time <= valid_to` 和 `evidence_as_of <= run.as_of`。
- registration identity window 必须在 bridge 后的训练与特征入口继续生效，不能只在展示层过滤。
- 真实转会、stand-in 和赛事临时注册必须分别记录；不得把“5 人相同”提升成无时间边界的组织等同规则。
- 新出现的同名 ID 默认不合并，直到有 Valve、俱乐部或赛事一手来源和稳定账号 ID 证据。
