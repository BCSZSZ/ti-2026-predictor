# Group Stat 队伍 Top 3 发布版 r2：移除队伍 ID

状态：**玩家版已移除全部队伍 ID；计算、机器证据和历史版本均未改变**

> 后续修订：`publication-v3` 又移除了玩家表中的来源显示。以下内容记录 `publication-v2`
> 阶段；当前版本见 [r3 修订说明](group-stat-team-top3-publication-r3-2026-08-08.md)。

- 日期：2026-08-08
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- 实现提交：`cdde501`
- 正式 run：`fantasy-579b5ee31d2dc6b9`
- 报告版本：`publication-v2`

## 修改范围

本次只删除每个候选队名后的内部队伍 ID，并移除页首关于 ID 的说明。平均分、低迷分、样本、
落后第一、第一稳定率、前三稳定率、排序和所有使用边界继续完整显示。机器 JSON 和上一版技术表
仍保留稳定 ID，因此没有破坏数据连接或历史复现。

新旧 `group-fantasy-evidence.json` 与 `model.json` 文件逐字节相同，证明 42 项排名、126 个候选
和全部数值没有变化。新发布 Markdown 包含 126 个候选单元格，“队伍 ID”和示例编号命中均为
0。

## 正式重生成

正式命令为：

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

连续两次均生成 `fantasy-579b5ee31d2dc6b9`，墙钟分别为 21.47 秒和 19.23 秒。正式审计为
`publishable: true`、无 blocking issue；既有客户端语义、校准、赛事层级、Swiss 近似、跨位置
相关性和 Coach 排除 warning 继续保留在机器证据中。

| 产物 | SHA-256 |
| --- | --- |
| evidence semantic | `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2` |
| `group-fantasy-evidence.json` | `c4d36205f811c0daccca752bf3d9068fc27158ef7fce5136c9a4273389032763` |
| `model.json` | `f5b8e88a491e606b23ef1762278130c2d48cdaa2d1182a613da50941ef0e8bd5` |
| `group-stat-team-top3-publication.md` | `12f8fac283dce2e8e484ce470a91592c1343af2c8af067c837316d370ee68141` |
| `run.json` | `6642de28951bd3891817916071bc7f6b04fc5a8eca730c76f48a9d3693bea115` |

## 验收与清理

- 发布渲染红测试先失败，最小修改后转绿；相关测试 17/17 通过；
- 完整离线测试 155 passed、1 skipped；Ruff、format、依赖、规则与 diff 检查通过；
- 该阶段发布表与正式 artifact 规范化内容一致，后来由 `publication-v3` 更新规范路径；
- 未修改排名算法、Forecast、replay/parser、规则、Main、手册、Quality、Trait 或发布 gate。

清理审查没有删除内部 `team_id`：它是项目稳定连接键，仍是机器证据所必需。上一版
`publication-v1` artifact 和 Git 历史同样保留；只从玩家可见的 Markdown 中移除显示。
