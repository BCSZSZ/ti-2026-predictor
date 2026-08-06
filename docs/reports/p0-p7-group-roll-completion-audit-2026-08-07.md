# P0–P7 Group 40-Roll 完成审计

状态：**工程路线已收口；证据结论不升级**

- 审计日期：2026-08-07
- 冻结数据/规则 `as_of`：`2026-08-06T08:15:00Z`
- 分支：`codex/group-roll-playbook-v1`
- 审计起点：`8b39e3a4b00b4361b39acdbd1909151c63ab9a89`
- 总计划：`docs/plans/group-roll-playbook-v1-implementation.md`

这里的“完成”表示各阶段都按预先声明的 gate 实施、验证并如实记录成功、失败或 partial；不表示
两份人工手册已经被证明可靠，也不表示求解器是全局最优策略。

## 阶段结论

| 阶段 | 主要提交 | 审计结论 |
| --- | --- | --- |
| P0 | `1b9804` | 范围、术语、来源优先级、人工手册/求解器双路线和 P1–P7 gate 已冻结并推送 |
| P1 | `87fde6` | 2,055 局目标比赛全部为 exact；五个 native counter 正式替代 proxy，缺失仍保持 `null` |
| P2 | `257746` | 28 个客户端 operation、纯不可变 Group 转移和三种概率模型完成；Main fail closed |
| P3 | `362ddb`、`3dcab47` | 完整 Series 重采样、共同比赛情景、精确终局估值和同队匹配完成 |
| P4 | `6fd0b61`、`b605803` | 两版人工手册独立生成并冻结；Rate-agnostic 与 Primary-model 都诚实保留为 `draft` |
| P5 | `a7b8755`、`eab526a`、`64030a8` | 限枝求解器完成，但有效性/吞吐 gate 失败，状态为 `failed-escalation-review-required`；不启用 Full planner |
| P6 | `db9c3a1`、`58036bd`、`b911d9d` | 留出审计与 P4/P5 均无情景交集，但只完成 9/108 行，状态为 `partial-draft`；未改写手册 |
| P7 | `b5c76d2`、`f7640d7`、`8b39e3a` | 本地手工确认顾问、确定性重放、一步诊断、末 Roll 按需 P5 和 UI 验收完成；仍是次要实验工具 |

## 证据完整性与可复现性

- `docs/playbooks/group-roll/evidence-package-v1.json` 的 14 个受跟踪文件现全部存在且逐字节
  SHA-256 一致。完成审计发现的唯一漂移是 P7 后续补写总计划造成的旧计划 hash；已做元数据
  校正，并新增离线回归测试锁住文件 hash、人工路线独立性和两版 `draft` 标签。
- P3、P4、P5-clean、P6 四个清单产物的文件 SHA-256 均与证据包一致；P7 产物
  `fantasy-125d96172389a0aa/group-interactive-advisor-evidence.json` 的 SHA-256 仍为
  `0ee561977858f119d2519c71b55b0de1eea0528f8a4c389edc6386b4ddfe84c3`。
- 在 P7 记录的干净实现提交 `f7640d75f6b4ad712469cace7cacae36f803ae2a` 上重新审计正式
  产物，结果为 `status=warning`、`publishable=true`、无 blocking issue，且输出 hash 不变。
  warning 继续保留两版 `draft`、P5 失败、P6 partial、规则歧义和一步估值限制。
- 在更新后的源码提交上审计历史 run 会按设计报告 `source_version-changed`；这是防止把旧产物
  冒充当前代码输出的保护，不是产物损坏。复现判断以产物所记录的干净提交为准。

P1 的一次性 183.876 GiB replay 获取约 5 小时 44 分，按冻结协议与缓存后分析分开计时。保守地
把 P3 clean、P4 正式、P5 clean、P6 partial 和 P7 正式记录耗时相加约 1 小时 54 分 29 秒；
这不是一次单体 benchmark，但即使不扣除重复上下文重建也低于 3 小时目标和 5 小时兜底。

## 最终工程门禁

- 完整离线 Python 测试：`130 passed, 1 skipped in 28.70s`；唯一 skip 是显式可选的本地
  replay-cache 集成测试。
- Ruff lint：通过；Ruff format：127 个 Python 文件全部通过。审计中机械格式化了 7 个既有
  P6/P7 文件，AST 与格式化前逐文件相同，没有逻辑改变。
- `uv lock --check` 与 `uv pip check`：通过，77 个已安装包兼容。
- Java replay parser：离线 Maven package 通过；shaded JAR 仍为 18,190,089 bytes，SHA-256
  `fc109d605ab7d190b95fcb5fa7b5619db2495c1372dfc89640eb5dbc190e40b1`。
- `ti rules validate`：按预期返回 `warning`，只包含已记录的 early/late First Blood 与 percentile
  三项规则歧义，没有 Group Roll blocking issue。

项目级边界复查还确认：人工手册生产模块不导入求解器；P5/P6 不写回手册；P7 不访问 Steam
凭据、不控制 Dota 客户端、不自动填写，也没有顾问专用网络调用；Web 默认仅监听
`127.0.0.1`；Main 在状态和 UI 两层继续 fail closed。

## 最终使用边界

目前最扎实、最适合人工查阅的产物仍是七张 Stat 表、Quality 表和精确 Trait 配方；两版简化
手册可以离线执行，但必须连同页首的 `draft` 警告理解。P5/P6 的失败或未完成结果不能用来
暗中补强手册。P7 只用于跟踪用户手工确认的当前状态和显示路线分歧，不能被描述为 40-Roll
最优策略证明。Main、自动客户端操作、全局精确 40-Roll 最优性和 Full planner 自动启用仍明确
在 v1 范围外。
