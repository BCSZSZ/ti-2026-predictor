# Group Stat 队伍 Top 3 发布版 r4：Stat 排名与基础建议

状态：**发布表已明确显示 Stat 排名和人类可读的基础建议；模型与原有 Top 3 结果未改变**

- 日期：2026-08-08
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- 实现提交：`c652fd7cb16ff97c6ecb435ab3f361228709969f`
- 正式 run：`fantasy-5e21be304ea57672`
- 报告版本：`publication-v4`

## 阶段目标和最小范围

目标是让玩家一眼分清两种排名：表格从上到下是同一位置、同一颜色内六项 Stat 的排名；
右侧“第 1 / 第 2 / 第 3”则是该 Stat 下的队伍排名。同时把既有 Baseline Stat grade 翻译成
可读建议，并在表内显示直接判断依据“相对强度”。

最小修改只包含发布渲染器、渲染测试、领域词表和发布 Markdown。没有修改 Forecast、bootstrap、
Stat 分数、队伍排序、手册配置、Quality、Trait 或发布 gate。

验收标准为：七张表各有且仅有一组 1–6；四档建议来自既有权威等级函数；42 行原有分档状态、
三支队伍及其全部数值保持不变；正式 run 可复现且无 blocking audit issue。

## 四档建议及判断依据

每张表先取六项 Stat 各自最佳匹配队伍的预测平均贡献，把最高者设为相对强度 100，再比较其余
五项。发布名称与内部等级一一对应：

| 内部等级 | 发布名称 | 判断依据 | 当前 42 行 |
| --- | --- | --- | ---: |
| `hard-protect` | 一定保留 | Stat 排名第 1，且该 Stat 的队伍第 2 名低于队伍第 1 名的 44% | 0 |
| `keep` | 可以保留 | 未触发“一定保留”，且相对强度不低于 84.6 | 13 |
| `conditional-reroll` | 可以改善 | 相对强度从 44（含）到 84.6（不含） | 23 |
| `priority-repair` | 优先改善 | 相对强度低于 44 | 6 |

最后一档采用“优先改善”，没有写成“一定改善”。等级描述的是 Stat 通常应占用重随机会的优先级；
真正是否重随还取决于当前三格、剩余次数、可用操作和完整战旗的同队匹配。

`分档边界` 继续单列显示：它表示完整系列赛重采样后可能跨过相邻门槛，不表示数据错误，也不直接
替代实际操作判断。

## 明确的 Stat 排名

每张位置/颜色表严格按相对强度降序列出 1–6，确定性并列规则仍为 `stat_id`。例如核心位红色现为：

1. `creep_score`
2. `deaths`
3. `gpm`
4. `tower_kills`
5. `kills`
6. `madstone_collected`

这里的“Stat 排名”与右侧队伍第 1–3 名是两个维度，不能混用。

## 实装和冻结边界

发布渲染器直接调用既有 `build_stat_priorities`，没有复制第二套阈值算法。项目级审查曾发现，临时
抽取等级函数会改变冻结的 `playbook.py` 文件哈希并触发候选冻结测试；该临时改动已在提交前完全
撤回。最终候选冻结包、v2 手册实现和证据包均未修改，相关冻结测试恢复通过。

没有遗留的旧发布分支需要删除：`publication-v3` 只作为历史报告版本保留，当前生成入口统一输出
`publication-v4`。

## 正式重生成与一致性

正式命令连续运行两次：

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

两次均生成 `fantasy-5e21be304ea57672`，墙钟分别为 17.46 秒和 17.29 秒。与 r3 正式 run 相比，
`group-fantasy-evidence.json` 和 `model.json` 逐字节相同；规范化比较确认原有 42 行的分档状态、
三支队伍和所有队伍单元格内容变化数为 0。

| 产物 | SHA-256 |
| --- | --- |
| evidence semantic | `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2` |
| scenario | `22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3` |
| `group-fantasy-evidence.json` | `c4d36205f811c0daccca752bf3d9068fc27158ef7fce5136c9a4273389032763` |
| `model.json` | `f5b8e88a491e606b23ef1762278130c2d48cdaa2d1182a613da50941ef0e8bd5` |
| `group-stat-team-top3-publication.md` | `5fddd02d12f188ddea56181d90ca69f6bbc3bd66f37fc4414dba3a1d27e49092` |
| `run.json` | `84803353503c8ddc599afb3de07bb12f3a08e09b7b57240a29140bb9da76ecbb` |
| `audit.json` | `82639556876e99444c0ee9103bd55d3f844322112cbe3c3708f623e25af222db` |

正式审计为 `publishable: true`、0 个 blocking issue、9 个既有 warning。42 个 Stat 行完整；
排名 1–6 各出现 7 次；建议分布为 0 / 13 / 23 / 6。

## 测试与项目级验收

- 新测试先因缺少两列而失败，最小实现后转绿，并覆盖 1–6 和四档发布名称；
- 完整离线测试：155 passed、1 skipped；
- Ruff、format、`git diff --check`、`uv lock --check`、`uv pip check` 均通过；
- `ti rules validate` 只有 3 条既有客户端语义 warning，无新增 blocker；
- 当前发布表与正式 artifact 内容一致；大型 artifact 继续不进入 Git。

## 保留边界

本次提升解决的是“表格有没有明确 Stat 排名、等级能不能直接读懂”，不提高模型本身的预测精度，
也不把基础建议升级为自动重随指令。完整三格仍必须重新进行同队匹配；v2 两份 Roll 手册继续保持
`draft`。
