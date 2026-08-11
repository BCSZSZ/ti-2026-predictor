# TI 2026 Fantasy 选手历史采样范围

调查日期：2026-08-01
快照边界：本地职业比赛目录最新 `start_time = 2026-08-01T12:26:20Z`。

## 口径

目标集合定义为：赛事清单中 80 个稳定 `account_id` 在 UTC 2026 年参加的所有
OpenDota `premium/professional` Game，按 `match_id` 去重。正在进行、尚未进入
OpenDota 职业目录的比赛不属于本次快照，后续通过重叠窗口增量同步补入。

玩家历史接口不能直接可靠地返回赛事级别，因此计算采用以下交集：

1. 从 `/players/{account_id}/matches` 取得 80 人的 2026 比赛 ID；
2. 从 `/proMatches` 取得完整职业比赛目录；
3. 将目录的 `leagueid` 与 `/leagues` 的 tier 关联；
4. 保留 `premium/professional`，再按 `match_id` 与玩家历史取交集。

`date=N` 是相对请求时刻的天数窗口，不是绝对日期，所以请求多取 366 天，再在本地严格按
`2026-01-01T00:00:00Z <= start_time <= as_of` 过滤。实现见
[`filter.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/filter.ts#L44-L57)。
不传 `limit` 时，玩家历史接口没有固定结果条数上限；`limit/offset` 在过滤和排序后应用，见
[`buildPlayer.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/util/buildPlayer.ts#L69-L88)。

`/proMatches` 每页固定 100 条，只支持 `less_than_match_id` 游标，不能在服务端按玩家、日期或
tier 过滤，见 [`spec.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/api/spec.ts#L1092-L1137)。

## 结果

80 个玩家历史请求全部成功，且所有账号都有匹配的职业比赛。

| 项目 | 数量 |
|---|---:|
| 80 人口径唯一 Game | 2,043 |
| 原 16 战队口径 Game | 1,470 |
| 两者交集 | 1,470 |
| 旧队或其他 team ID 带来的新增 Game | 573 |
| 已识别 Series | 958 |
| 缺少 `series_id` 的 Game | 9 |
| League | 39 |
| `professional` | 2,043 |
| `premium` | 0 |
| 7.40 | 987 |
| 7.41 | 1,056 |
| 80 名目标选手的 player-Game 关联 | 12,376 |
| 下载完整详情后全部玩家行 | 20,430 |
| 已有 raw 详情 | 113 |
| 尚需 GET 详情 | 1,930 |

每名目标选手的职业 Game 数量为 43–256，中位数 166，平均 154.7；没有 0 场玩家。
原战队口径的 1,470 场全部已被新口径覆盖，因此本快照直接以 2,043 场玩家口径为准即可。

OpenDota 对已识别职业选手有隐私例外；本次 80 个账号均可从玩家历史接口返回数据。相关
判断见 [`api.ts`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/svc/api/api.ts#L42-L67)。

## 体量估计

按现有 257 个详情响应的均值 280.73 KiB/Game、P95 353.77 KiB/Game 估算：

- 2,043 场完整 raw JSON：约 560 MiB；按 P95 约 706 MiB；
- 尚缺 1,930 场：约 529 MiB；按 P95 约 667 MiB；
- 保留现有非目标样本、重复快照、日志与 Parquet 后，建议预留 1–2 GiB。

该估算不包含 `.dem` replay。本项目保存 OpenDota 完整详情 JSON，不主动下载 replay 文件。

## 增量策略

每次更新应重新取得 80 人最近一段重叠时间窗口的比赛 ID，刷新 `/proMatches` 和 league tier，
再按 `match_id` 去重。重叠窗口用于捕获本次快照时仍在进行、刚结束但尚未进入索引，或稍后才
完成 replay 解析的比赛。
