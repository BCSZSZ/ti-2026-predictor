# TI 2026 最终排行榜奖励与预测计分截图归档

## 文档状态

- 文档类型：本机 Dota 客户端界面的人工转录、规则整理与项目解释。
- `as_of`：`2026-08-02T06:02:48.617Z`，表示两张证据图最迟已在此时提供并完成读取；实际拍摄时间未知。
- 客户端 build：截图自身没有显示，不能只凭图片确定。
- 规则范围：最终排行榜固定奖励、小组赛预测计分、The International 淘汰赛预测计分。
- 实现状态：数值已同步到 `config/rules/ti2026.json`。截图原图不提交 Git，只保存文件指纹。

本文严格区分三种分数/结果：

1. **Fantasy 原始分数**：由选手表现、War Banner 和 Coach 计算。
2. **活动点数**：Fantasy 期内百分位及预测答对数量所授予的 points。
3. **最终排行榜奖励**：活动结束后按最终名次档位发放的 Dota Plus、Terrain Token、Aegis Discount 和 Tyrian Regalias。

## 1. 最终排行榜固定奖励

### 英文标题与说明

> REWARDS FOR TOP PERFORMERS

> Determined after The International on August 27th

### 客户端表格

| 最终排行榜档位 | Dota Plus | Terrain Tokens | Aegis Discount | Tyrian Regalias（紫色宝瓶） |
| --- | ---: | ---: | ---: | ---: |
| Top 100 Players | 12 Months | ×1 | 100% Off | ×5 |
| Top 1500 Players | 6 Months | ×1 | 100% Off | ×2 |
| 95th Percentile | 2 Months | ×1 | 50% Off | ×1 |
| 90th Percentile | 1 Month | ×1 | 0% Off | ×0 |
| 85th Percentile | 1 Month | ×0 | 0% Off | ×0 |

客户端还写明：

> Earn 300 Dota+ Shards for every 1,000 points

因此每取得完整的 1,000 活动点数，对应 300 Dota+ Shards。截图没有展示不足 1,000 点的余数处理代码，项目只保存 `1,000 → 300` 的步长规则。

### 项目负责人确认

- Tyrian Regalias 是用户所称的“紫色宝瓶”。
- 紫色宝瓶按最终排行榜档位给出固定总数：Top 100 为 5、Top 1500 为 2、95th percentile 为 1、90th/85th percentile 为 0。
- 配置使用 `highest_qualified_row_total`：取玩家达到的最高一行所列总奖励，不把多行的 `×N` 相加。

### 尚未由截图说明

- “August 27th” 没有显示时区；配置只保存日期 `2026-08-27`，不伪造 UTC 锁定时刻。
- 没有展示同分玩家在第 100、1,500 名边界的处理和 tiebreak。
- 没有展示绝对排名档位与 percentile 档位发生边界重叠时的服务端判定代码。最高档位优先是项目负责人确认的固定奖励解释。

## 2. Group Stage 预测规则

### 英文原文转录

> Predict the performance of the teams competing in the swiss and elimination stages of the Group Stage.

> After the Group Stage, you'll get escalating points based on how accurate your predictions were.

### 截图确认的计分表

| 答对数量 | 活动点数 |
| ---: | ---: |
| 0 | 0（项目的自然零点；截图从 1 开始） |
| 1 | 30 |
| 2 | 60 |
| 3 | 120 |
| 4 | 360 |
| 5 | 720 |
| 6 | 1,200 |
| 7 | 1,800 |
| 8 | 2,520 |
| 9 | 3,360 |
| 10 | 4,320 |
| 11 | 5,400 |
| 12 | 6,600 |
| 13 | 7,920 |
| 14 | 9,360 |
| 15 | 10,920 |
| 16 | 12,000 |

这些数值表示“总共答对 N 项时获得的总活动点数”，不是把前面各行再次累加。例如答对 8 项获得 2,520 点，而不是 `30+60+...+2520`。

截图说明预测对象覆盖 Group Stage 的 Swiss 与 elimination stages；具体要填的 4-0、4-1、淘汰轮胜负等槽位由同一活动的其他客户端规则定义，见 `docs/rules-ti2026.md`。

## 3. The International 淘汰赛预测规则

### 英文原文转录

> Once the Group Stage is complete, fill out your tournament bracket.

> Review the matchups and pick the team you think is going to win each series, all the way to the winner of TI.

> After The International you'll get escalating points based on how accurate your predictions were.

### 截图确认的计分表

| 答对数量 | 活动点数 |
| ---: | ---: |
| 0 | 0（项目的自然零点；截图从 1 开始） |
| 1 | 120 |
| 2 | 360 |
| 3 | 720 |
| 4 | 1,200 |
| 5 | 1,800 |
| 6 | 2,520 |
| 7 | 3,360 |
| 8 | 4,320 |
| 9 | 5,400 |
| 10 | 6,600 |
| 11 | 7,920 |
| 12 | 9,360 |
| 13 | 10,920 |
| 14 | 12,000 |

同样，这是一张“答对数量 → 总活动点数”查表规则，不是逐行累加。玩家在 Group Stage 完成后填写完整 bracket，并为每个 Series 选择胜者，直至 TI 冠军。

## 4. 项目目标链条

当前项目按以下层次理解最终目标：

```text
小组赛游戏内预测 ─┐
淘汰赛游戏内预测 ─┼─> 活动点数 ─> 最终排行榜名次 ─> 固定档位奖品
Fantasy 两个 Period ─┘                         └─> Tyrian Regalias × 5 / 2 / 1 / 0
```

因此，“尽量让 Fantasy 原始分数更高”仍然正确，但它只是完整目标的一部分：

- Fantasy 原始分数先决定该 Period 的相对百分位；
- 百分位再授予该 Period 的活动点数；
- 小组赛和淘汰赛预测按答对数量直接授予活动点数；
- 最终活动点数影响排行榜位置；
- 最终排行榜档位决定固定数量的紫色宝瓶及其他奖品。

截图没有提供“总活动点数 → 最终排行榜名次”的人群分布，所以模型目前可以精确计算预测答对数量对应的活动点数，却仍不能仅凭这些规则预知进入 Top 100 或 Top 1500 所需的点数阈值。

## 5. 与当前配置的对应关系

- `prediction.group.cumulative_points`：包含 `0` 在内的 17 个 Group Stage 总点数档位。
- `prediction.main.cumulative_points`：包含 `0` 在内的 15 个 The International bracket 总点数档位。
- 两张表都声明 `points_table_semantics = total_event_points_by_correct_prediction_count`。
- `event.final_leaderboard_rewards`：五个最终排行榜固定奖励档位。
- `event.final_leaderboard_rewards.dota_plus_shards`：每 1,000 活动点数对应 300 shards。
- `event.nominal_total_points = 48,000`：项目根据小组赛预测 12,000、淘汰赛预测 12,000、两个 Fantasy Period 各 12,000 得出的名义总上限；这是跨规则合计，不是本批任一张截图单独展示的数字。

## 6. 来源完整性

| ID | 原始文件名 | 尺寸 | 内容 | SHA-256 |
| --- | --- | ---: | --- | --- |
| R1 | `codex-clipboard-2b19f0fd-0f5d-45ba-8060-5f2c89a47c7d.png` | 602×798 | 最终排行榜奖励 | `408050a283ca297d56e14f5696f5a56ab185e00e38b06ac876e4d2d47ee7e090` |
| P1 | `codex-clipboard-e2154430-5a08-459f-b630-a5d090632301.png` | 1402×905 | Group Stage 与 The International 预测计分 | `f947c4244030bf3d0b1609992450025ee0f1deb78d43d34fd07dbb89fc71bb63` |
