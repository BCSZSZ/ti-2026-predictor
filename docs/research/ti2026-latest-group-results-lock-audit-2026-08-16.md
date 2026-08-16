# TI 2026 小组赛最新赛果与 Main 晋级锁定核验

- 查询时间：`2026-08-16T09:35:16.5699052Z`（JST `2026-08-16T18:35:16.5699052+09:00`）
- 数据水位：Valve 响应 `info.most_recent_activity = 2026-08-16T09:13:04Z`
- 事件：`league_id=19719`，`The International 2026`
- 范围：只读赛果与数学锁定核验；不是 `Forecast`，没有修改 `src/`、`config/` 或运行时指针
- 来源边界：一手事实以 Valve 官方 API 为准；BLAST 结果页仅作人类可读交叉核对；未访问 Liquipedia

## 结论

**是，而且已经不只是“一大半”：当前有 `7 / 8` 个 Main 晋级名额已数学锁定，占 `87.5%`。**

已晋级：

1. PARIVISION / Valve `TEAM VISION`（`9572001`，Swiss `4-0`）
2. Team Liquid（`2163`，Swiss `4-1`）
3. Nigma Galaxy（`10136357`，Swiss `4-1`）
4. Team Falcons（`9247354`，淘汰轮 `2-0` Vici Gaming）
5. BetBoom Team / Valve `BoomBoys`（`8255888`，淘汰轮 `2-0` Aurora）
6. Team Spirit（`7119388`，淘汰轮 `2-1` Team Resilience）
7. Iron Wing（`10150413`，淘汰轮 `2-0` GamerLegion）

唯一未定的第八席在 **LGD Gaming** 和 **Team Yandex** 之间产生。在本快照中，该 BO3 已开始但未结束，LGD `1-0` 领先；因 Yandex 仍可以连赢两局变成 `2-1`，两队都不能在这个 `as_of` 被标成锁定晋级或锁定淘汰。

## 官方快照与完整性

完整请求：[`GET IDOTA2League/GetLeagueData/v001?league_id=19719`](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719)

- HTTP：`200`
- 原始 bytes：`143388`
- SHA-256：`ae75245ad55dca53a2050dc19218a27e88252f8ba225d2471db51484c1d2f8e2`
- 冻结响应：[`response.json`](../../data/raw/valve_ti2026_league/20260816T093516Z/response.json)
- 请求元数据：[`metadata.json`](../../data/raw/valve_ti2026_league/20260816T093516Z/metadata.json)

对响应的字段级核对得到：

- Swiss `node_group_id=2`：`is_completed=true`；39 个具有非零 `series_id` 的系列赛全部 `is_completed=true`。
- Playoff 根组已经有 3 条 standings：`TEAM VISION`、`Team Liquid`、`Nigma Galaxy`，与 Swiss `4-0 / 4-1 / 4-1` 一致。
- Elimination Round `node_group_id=3`：共 5 个 BO3 节点，5 个都已开始，4 个 `is_completed=true`，最后一个 `is_completed=false`。
- 四个已完成节点的胜者 standings 均为 `wins=1, losses=0`；败者均为 `wins=0, losses=1`。

赛事结果页也逐场列出了同样的四个淘汰轮已完赛结果：[BLAST TI 2026 Results](https://blast.tv/dota/tournaments/the-international-2026/series?view=results)。BLAST 使用 `PARIVISION` 与 `BetBoom Team` 的显示名，Valve 这份 API 使用同一稳定 ID 下的 `TEAM VISION` 与 `BoomBoys`；本文以稳定 team ID 连接，不把显示名差异当成不同队。

## 16 队当前战绩与最终状态

| 稳定 team ID | 队伍（当前常用显示名） | Swiss 战绩 | 淘汰轮状态 | Main 结论 |
| ---: | --- | ---: | --- | --- |
| `9572001` | PARIVISION / Valve `TEAM VISION` | `4-0` | 无需参加 | **锁定晋级** |
| `2163` | Team Liquid | `4-1` | 无需参加 | **锁定晋级** |
| `10136357` | Nigma Galaxy | `4-1` | 无需参加 | **锁定晋级** |
| `7119388` | Team Spirit | `3-2` | `2-1` 击败 Team Resilience | **锁定晋级** |
| `10150413` | Iron Wing | `3-2` | `2-0` 击败 GamerLegion | **锁定晋级** |
| `9247354` | Team Falcons | `3-2` | `2-0` 击败 Vici Gaming | **锁定晋级** |
| `9467224` | Aurora Gaming | `3-2` | `0-2` 负 BetBoom Team | **锁定淘汰** |
| `10150538` | LGD Gaming | `3-2` | 对 Yandex `1-0`，进行中 | **未定** |
| `8255888` | BetBoom Team / Valve `BoomBoys` | `2-3` | `2-0` 击败 Aurora | **锁定晋级** |
| `726228` | Vici Gaming | `2-3` | `0-2` 负 Falcons | **锁定淘汰** |
| `9823272` | Team Yandex | `2-3` | 对 LGD `0-1`，进行中 | **未定** |
| `5017210` | Team Resilience | `2-3` | `1-2` 负 Spirit | **锁定淘汰** |
| `9964962` | GamerLegion | `2-3` | `0-2` 负 Iron Wing | **锁定淘汰** |
| `8261500` | Xtreme Gaming | `1-4` | 未进入淘汰轮 | **锁定淘汰** |
| `2586976` | OG | `1-4` | 未进入淘汰轮 | **锁定淘汰** |
| `10149530` | HULIGANI | `0-4` | 未进入淘汰轮 | **锁定淘汰** |

这张表不是根据当前排名的概率判断，而是已完成赛系的确定性分类。当前同时已有 `7 / 8` 个晋级队与 `7 / 8` 个淘汰队被锁定；LGD–Yandex 的胜者/败者将分别填满最后一席。

## “数学锁定”的判定口径

本次使用的是赛制可达性，不是实力模型：

1. Swiss 已 `is_completed=true`，官方 Playoff 根组已列入的 3 队不再有任何小组赛路径会使其失去资格，故直接锁定。
2. 淘汰轮 BO3 节点在 `is_completed=true` 且一方已有2个 Game 胜场时，系列赛结果无法再翻转；胜者占有 Main 名额，败者离开赛事。
3. Swiss `1-4` 与 `0-4` 队伍既不在 Playoff 根组，也不在 10 队 Elimination Round standings 中；Swiss 已完结，故不存在返回晋级路径。
4. LGD–Yandex 仍 `is_completed=false`。`1-0` 只是实时比分，不是 BO3 终局，所以不做提前宣布。

赛制的官方入口是 [Valve TI 2026 Rules](https://www.dota2.com/esports/ti15/tirules)；仓库已冻结其官方规则资源（`2026-08-10T13:45:12Z`，SHA-256 `e55e2d979f0de1f2b16890b4ea6ed4d1e8ba0c47752a2bfdb1dc86e8829bbf6c`），见 [`response.js`](../../data/raw/valve/ti2026-rules/20260810T134512Z-e55e2d979f0d/response.js) 与 [`metadata.json`](../../data/raw/valve/ti2026-rules/20260810T134512Z-e55e2d979f0d/metadata.json)。

## 不确定性与使用边界

- 这是一个明确 `as_of` 的快照，不是持续刷新的 live tracker。最后一场可能在本文写完后结束。
- `info.most_recent_activity` 是 Valve 响应自身的内容水位；不应把网络抓取时间误写成每个字段的最后更新时间。
- 不把 `config/ti2026.yaml:main_event_seeds` 的当前空值当成官方未晋级；该字段是本项目未导入 actual 种子的运行状态，不是赛果来源。
- 本文不将任何 `Forecast` 或 projected Main 情景写成官方结果。
