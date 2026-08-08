# Group Stat 队伍 Top 3 发布版 r3：移除来源显示

状态：**玩家版已移除来源列；内部 provenance、分档状态和全部计算保持不变**

- 日期：2026-08-08
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- 实现提交：`52a4c27`
- 正式 run：`fantasy-609a4e6859d66b0b`
- 报告版本：`publication-v3`

## 修改范围

本次从玩家表中删除“数据来源”以及“精确数据/推导数据”显示，原列缩减为“分档状态”。
“分档稳定/分档边界”继续保留，因为它会影响玩家是否应把前三都当作接近候选。

机器 JSON、旧技术表和审计链继续保存 `exact/derived` provenance。本次没有把 provenance 从
领域模型中删除，也没有把“发布表不显示”解释为以后无需做来源门禁。

## 正式重生成

正式命令为：

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

连续两次均生成 `fantasy-609a4e6859d66b0b`，墙钟分别为 19.14 秒和 19.01 秒。新旧
`group-fantasy-evidence.json` 与 `model.json` 逐字节相同，证明 42 项排名、126 个候选和全部
平均分、低迷分、样本、差距与稳定率均未改变。

发布 Markdown 中“数据来源”“精确数据”“推导数据”命中均为 0；42 行分档状态完整保留。
正式审计为 `publishable: true`、无 blocking issue，既有 warning 继续保留在机器证据中。

| 产物 | SHA-256 |
| --- | --- |
| evidence semantic | `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2` |
| `group-fantasy-evidence.json` | `c4d36205f811c0daccca752bf3d9068fc27158ef7fce5136c9a4273389032763` |
| `model.json` | `f5b8e88a491e606b23ef1762278130c2d48cdaa2d1182a613da50941ef0e8bd5` |
| `group-stat-team-top3-publication.md` | `1f090a550d66b14ca0813e7e95dd220dde9f0fb8603a2c3ad970c15461e58061` |
| `run.json` | `cfa7e1dbc5519f8f87415d57d0218675864896f8c70aab7efb478c60f7aea03a` |

## 验收与清理

- 发布渲染红测试先失败，最小修改后转绿；相关测试 17/17 通过；
- 完整离线测试 155 passed、1 skipped；Ruff、format、依赖、规则与 diff 检查通过；
- [当前发布表](../playbooks/group-roll/stat-team-top3-publication-v2.md)与正式 artifact 规范化内容一致；
- 未修改排名算法、Forecast、replay/parser、规则、Main、手册、Quality、Trait 或发布 gate。

清理审查删除了发布渲染器中不再使用的 provenance 中文映射，但保留机器 evidence 中的
`provenance` 字段和来源门禁。旧 publication artifact 与报告仍承担历史复现职责，没有删除。
