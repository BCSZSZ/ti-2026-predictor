# Group Stat 队伍 Top 3 发布版：实施与验收报告

状态：**发布呈现已完成并正式重生成；排名数值、证据与 v2 状态均未改变**

- 日期：2026-08-08
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- 发布版实现提交：`5137e68a87542fad50f00ffa141680884d2dc000`
- 正式 run：`fantasy-a7970c9769ca1c1a`
- evidence semantic SHA-256：
  `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2`

## 阶段目标、最小范围与验收

本阶段只把上一版技术表改成可直接发布和查阅的版本。排名算法、Series block、8,192 个公共
情景、400 次重采样、Stat 来源、队伍 ID、分数和概率字段都不获准修改。最小代码范围只有
Markdown 渲染、报告文件名、报告版本身份和对应测试；旧 artifact 与旧技术表必须保留。

验收要求是：新表仍有 42 行和 126 个队伍单元格；新旧 evidence JSON 与 model 文件逐字节
一致；同一输入连续生成同一 run 和相同文件；正式 artifact 在干净实现提交上可审计；发布表
不再显示 `μ/C10/n/Δ/P1/P3`，但不得丢失它们代表的信息；全项目回归无新增 blocker。

## 发布呈现修改

单元格字段改为：

| 技术字段 | 发布版名称 | 通俗含义 |
| --- | --- | --- |
| `point_mean` / `μ` | 平均分 | 当前模型下的常规预期得分 |
| `point_cvar10` / `C10` | 低迷分 | 最差 10% 情形的平均分，越高越抗风险 |
| `series_blocks` / `n` | 样本 | 该队该位置可用的完整历史系列赛数量 |
| `gap_to_point_best_fraction` / `Δ` | 落后第一 | 与本行第一名平均分的相对差距 |
| `rank1_probability` / `P1` | 第一稳定率 | 400 次重采样后仍排第一的比例 |
| `top3_probability` / `P3` | 前三稳定率 | 400 次重采样后仍在前三的比例 |

队伍数字由无标签括号改为“队伍 ID”，位置和颜色标题改为中文，`exact/derived` 改为“精确
数据/推导数据”，`#1/#2/#3` 改为“第 1/第 2/第 3”。删除了重复的第一至第三差距列、页首
run/hash 实现细节和逐条原始 warning；必要的数据截止、重采样次数、稳定率边界、赛制近似和
同队匹配限制继续保留。完整 warning、run 与哈希仍在机器 artifact 和本报告中，没有被删除。

## 不可变重生成与数值一致性

为避免同一 run ID 下出现不同 Markdown，`team_rank_bootstrap` 的 run 参数新增
`report_version=publication-v1`，输出文件改为 `group-stat-team-top3-publication.md`。上一版
`fantasy-c2b2c058910766ab` 及其 `group-stat-team-top3.md` 没有覆盖或删除。

正式命令为：

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

连续两次均生成 `fantasy-a7970c9769ca1c1a`，墙钟分别为 16.47 秒和 16.04 秒。新旧
`group-fantasy-evidence.json` 与 `model.json` 的文件哈希分别完全相同，因此 42 项排名、126 个
候选、所有平均分、低迷分、样本、差距与稳定率均未变化。

| 产物 | SHA-256 |
| --- | --- |
| evidence semantic | `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2` |
| Scenario semantic | `22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3` |
| `group-fantasy-evidence.json` | `c4d36205f811c0daccca752bf3d9068fc27158ef7fce5136c9a4273389032763` |
| `model.json` | `f5b8e88a491e606b23ef1762278130c2d48cdaa2d1182a613da50941ef0e8bd5` |
| `group-stat-team-top3-publication.md` | `203866c561e6205d31cad1074214774b7af4a8c84534d49988879e1c6cc140f3` |
| `run.json` | `d4ba3e2e8eaff36fed5bc484c49416904faf8a93e20318d68c4d12ec09f0aa4d` |

生成 Markdown 与被提升的
[发布版速查表](../playbooks/group-roll/stat-team-top3-publication-v2.md)规范化内容一致。发布表
包含 126 个明确标注的队伍 ID，旧缩写命中为 0。

## 审计、回归与清理

正式 run 在干净的 `5137e68` 上审计为 `publishable: true`、无 blocking issue。状态仍是
`warning`，来源是原有客户端语义、校准、赛事层级、Swiss 赛制近似、跨位置相关性和 Coach
排除说明；发布格式没有把 warning 变成数值通过声明。

- 发布渲染红测试先失败，最小修改后转绿；相关测试 17/17 通过；
- 完整离线测试 155 passed、1 skipped；Ruff、format、依赖、规则与 diff 检查通过；
- 新旧 evidence/model 字节一致；正式发布 Markdown 连续复现；
- 未修改 replay/parser、客户端规则、Forecast、Main、手册、Quality、Trait 或发布 gate。

清理审查只移除了发布渲染器已经不再使用的 `run_id` 参数。旧技术表、旧 artifact 和技术报告
承担历史复现职责，不能删除；新发布版是并列的呈现层，不替代机器证据或冻结 v2 手册。
