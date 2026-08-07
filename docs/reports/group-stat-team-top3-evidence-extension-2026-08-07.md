# Group Stat 队伍 Top 3 证据扩展：实施与验收报告

状态：**扩展完成并正式重生成；描述性证据可用，v2 手册与发布标签不变**

- 日期：2026-08-07
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- 实现提交：`bc8afcc62aba25eaf30bf279518d1a43b0399d47`
- 正式 run：`fantasy-c2b2c058910766ab`
- 正式 evidence semantic SHA-256：
  `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2`

## 阶段目标、最小范围与验收标准

本阶段只解决一个问题：原 Stat 表告诉读者每个位置/颜色下哪些 Stat 最好，却没有列出每个
Stat 对应的前三队伍和排名不确定性。最小实现范围因此限定为既有 P3 Series cluster bootstrap
的可选扩展、确定性 Markdown 渲染、CLI 开关、测试和文档；不改 Stat 指数、Quality、Trait、
Scenario、手册规则、模型参数、发布门禁或历史 v1/v2 证据。

验收标准是：

1. 默认命令继续生成旧 schema 与旧语义哈希；
2. 开启扩展后，每个位置/颜色/Stat 都有全部 16 队记录，并显示点估计前三；
3. 每组 bootstrap 的 `P1` 总和为 1、`P3` 总和为 3，平手按稳定 `team_id` 确定性处理；
4. 同一快照、配置、seed 连续复跑得到同一 run ID 和相同 JSON/Markdown；
5. 正式 artifact 在干净实现提交上通过审计，项目级回归不出现新 blocker。

## 最小实现

`fantasy group-evidence` 新增默认关闭的 `--team-rank-bootstrap`。开启后，原 400 次完整 Series
分组重采样会同时记录每队在各组中的第一名频率和前三频率；点估计和每次重采样都按 Expected
mean 降序、稳定 `team_id` 升序打破平手。机器输出从 schema 1 扩展为 schema 2，并新增
`team_rankings`；默认关闭时仍走原 schema 1 路径。

生成器另写不可变的 `group-stat-team-top3.md`，每行展示：

- 点估计前三的稳定队伍 ID，队名只用于显示；
- Expected mean、CVaR10、完整 Series blocks 数和相对第一名差距；
- `P1`（重采样第一名频率）和 `P3`（重采样进入前三频率）；
- Stat 的 `exact/derived` 来源和分档区间是否跨线。

这些频率的机器标记是
`series_resampling_frequency_not_calibrated_future_probability`。它们不是经校准的未来真实排名
概率，也不是置信区间。

## 正式重生成与确定性

正式命令为：

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

结果包含 42 个位置/颜色/Stat 组、每组 16 队，共 672 条排名记录；点估计 Top 3 共 126 格。
全部 42 组都满足 `ΣP1=1`、`ΣP3=3`，没有概率守恒失败。连续两次正式复跑均得到
`fantasy-c2b2c058910766ab`、相同 evidence semantic、相同 JSON 和 Markdown；两次墙钟分别为
25.90 秒和 25.38 秒。

| 产物 | SHA-256 |
| --- | --- |
| evidence semantic | `076d23de4f6a8ea04a9ac55594f20cb36b42f460fd56747467e0c7870d6845b2` |
| cluster bootstrap semantic | `2dac3eac1acb091bf1b710160e79a4159cfdc32f761cb3b6847f7242d1c50a50` |
| `group-fantasy-evidence.json` 文件 | `c4d36205f811c0daccca752bf3d9068fc27158ef7fce5136c9c4273389032763` |
| `group-stat-team-top3.md` 文件 | `39e027aeee6d5b93b8e749fb4e149e8167dbd6749943055b6d4afd117c42bfc6` |
| `model.json` 文件 | `f5b8e88a491e606b23ef1762278130c2d48cdaa2d1182a613da50941ef0e8bd5` |
| `run.json` 文件 | `f810baf3c6c427600b630d0242f662602054672e7c1d4d1d7c50620e3602d508` |

正式 run 的状态是 `warning`，但在干净的 `bc8afcc` 上审计为 `publishable: true` 且无 blocking
issue；warning 仍是既有的校准、赛事层级和 Swiss 规则边界，没有新增数据质量或代码问题。
受 Git 忽略策略约束，完整 artifact 留在本地；被纳入文档的
[Top 3 附表](../playbooks/group-roll/stat-team-top3-evidence-v2.md)与生成 Markdown 的规范化内容
一致，仅可能因 Git 行尾规范化而有原始文件字节差异。

## 兼容性与项目级审查

默认关闭扩展的兼容复跑继续得到旧 evidence semantic
`de84baa3081ac5d81e55ec9110766d96c26071a907b7a74824bff8e8faf7a42f` 和旧 Scenario
`22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3`。扩展 run 的
`as_of`、数据快照、Scenario、Stat forecasts、原 bootstrap rows 和 terminal smoke 与冻结 v2
逐字段一致；新增内容只有队伍排名 bootstrap 与附表。

项目审查没有发现 replay/parser、客户端规则、网页、Main、Forecast、手册模型或发布 gate 的
行为变化。默认兼容路径仍有历史复现用途，不能清理；新路径是明确可选的加法，没有被完整替代
的旧 production 代码，因此本阶段不删除历史逻辑或证据。

## 回归验收

- 红测试先证明旧代码缺少报告模块、排名参数和不可变文本 writer；最小实现后全部转绿；
- 新测试覆盖排序/平手、42×16 完整性、概率守恒、Markdown 可信度提示、默认 schema/hash
  兼容和扩展 run 身份；
- 相关测试 42/42 通过；完整离线测试 155 passed、1 skipped；
- Ruff、format、`git diff --check`、lock 和依赖兼容检查通过；
- `ti rules validate` 只有 3 条既有语义 warning，无新增 blocker。

## 结果应如何理解

这次提升的是可查性和诚实的不确定性披露，不是模型突然更准。42 项中有 19 项 Stat 分档区间
跨线；8 项点估计第一与第二差距小于 1%，5 项第一与第三差距小于 2%；20/42 个点估计第一的
`P1` 低于 50%，35/42 低于 80%。因此只列一个“最佳队伍”会掩盖大量接近或不稳定的排序，
列前三并同时看差距、样本数和 `P1/P3` 更合适。

扩展仍不能证明未来赛事排名，也不能替代完整三格同队 Team matching。阵容、对手、赛制和
未来版本变化不在这 400 次历史 Series 重采样中；使用时必须保留显式 `as_of`，并把附表视为
候选比较证据而非自动锁队规则。
