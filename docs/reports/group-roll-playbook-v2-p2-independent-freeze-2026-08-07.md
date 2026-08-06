# Group Roll playbook v2 P2 independent-freeze report

状态：**P2 已完成；两份 v2 候选已独立冻结，但尚未经过新一轮可靠性验证**

日期：2026-08-07

显式 `as_of`：`2026-08-06T17:27:00Z`

## 阶段目标、最小范围与验收

P2 从 `main@ea8abceed4df5e96803c762d31c2e36e2b07d0fc` 开始。目标是以当前客户端规则和
受治理的 P1-P3 算术为基础，独立冻结两份 v2 Human Roll 候选；不运行新 solver，不从
P5/P6 动作轨迹反向生成、挑选或修补规则。

最小实装范围限定为：

- 新的本地客户端 Rule 快照、显式 UTC `as_of` 与同一数据集上的 P3 重算；
- 两份 versioned v2 配置、三份人工可读证据/手册和一份冻结清单；
- 仅为表达 v2 规则增加的 handler，以及统一 Stats provenance fail-closed 门禁；
- 聚焦测试、索引、阶段报告和计划状态。

验收要求是：Stats 只能是 `exact` 或获准 `derived` 且完整覆盖；每版冻结 8/12/16
嵌套候选、发布序列最多 12 条、每条最多三个可见条件、三个整数阶段和统一刷新兜底；冻结
清单必须能发现文件或语义漂移；生产手册模块不得依赖 solver/cross-audit；全量工程 gate
通过。P3/P4 的可靠性结论不属于本阶段，不能提前标绿。

## 全体代码与数据起点

- v1 两份手册、四阶段证据包、配置及其 hash 均未修改，继续是历史 `draft` 证据。
- P1 的语义保持性能剪枝已经在 `main`；本阶段没有恢复旧全枚举路径。
- 本地 Dota 客户端 build 为 `6888:10887746`，VersionDate 为 2026-08-05。
- 新 Rule snapshot 为 `20260806T172612Z-702ddf2a6953`，语义 SHA-256 为
  `702ddf2a6953f383895efdfa3e45460c770e7c3c37e71d6a2b1d68e547a3235f`；与 v1 的规则
  语义完全相同。
- 对本地数据库的只读检查显示：v1 cutoff `2026-08-06T08:15:00Z` 之后新增可用比赛为
  `0`，新增 Fantasy 样本为 `0`。因此没有重复下载 replay，也没有重新生成先前约 186 GB
  的一次性缓存。
- 新 `as_of` 晚于 Rule snapshot 创建时间，并早于当时墙钟；所有输入继续遵守时间截断。

## 当前基线重算

执行 `fantasy group-evidence --as-of 2026-08-06T17:27:00Z`，墙钟 15.92 秒：

| 身份 | 值 |
| --- | --- |
| run | `fantasy-bcffa25a645c8438` |
| evidence semantic SHA-256 | `de84baa3081ac5d81e55ec9110766d96c26071a907b7a74824bff8e8faf7a42f` |
| common Scenario SHA-256 | `22fd9f2f400cff0a4b08926824f181b8e05287e46de12d1139c5fda6bdeff7c3` |
| data snapshot SHA-256 | `49e373b2c03a4598d51f3de3eb5b85f80f001a097dd26acaa41137862b58f88b` |
| Series pool SHA-256 | `9a86b14e913e6e53fe4a53f7bd7325386b372521fe18c7924004cfbccfa33c16` |
| artifact file SHA-256 | `67917884967a7e43f8925af0c24f2fd52f7be9f4cb370faeb31b0cca25fc8aa6` |

因为没有新样本，新旧差异仅来自预注册时间衰减权重前移。42 个 role/color/stat 行的排序、
分档、bootstrap 边界和 provenance 均为 `0` 项变化；相对指数最大绝对变化为
`5.46411485258802e-05`，即约 0.0055 个百分点。

正式输入包含 16 个唯一 `exact` Stat 与两个获准 `derived` Stat：
`creep_score=last_hits+denies` 和
`teamfight_participation=(kills+assists)/team_total_kills`。42 行的合格 row 与完整
Series-block provenance 最低覆盖率均为 100%；`proxy` 和 `unavailable` 没有进入手册。
生产入口另增加拒绝测试与门禁：任一非 exact/derived 或覆盖率不等于 100% 的行都会直接
抛错，而不是填零或降级使用。

## 独立规则处置

允许使用的既有确认结果只限 v1 P4 人工路线的汇总和规则消融，语义 hash 为
`a0361a228629c46663fe844387af7f71eea37113838b3036dc6181dd227ad857`。冻结清单将
`solver_sources_used_for_derivation` 固定为空数组；P5/P6 的 solver/oracle 动作没有进入规则
来源。

### Rate-agnostic v2

- 保留跨三模型通过消融的三项原则：不降级 `+1`、Mid 单格 C 档、末期全支持不降。
- v1 RA06 的整色全 T1 从全阶段收窄到前期 `40-26`。
- v1 RA10 的精确 T2 移出 12 条发布序列；RA12 的前期 T3 二升一降不再发布。
- 用 Stat、Quality、Trait 三个 mutation-specific 的“所有合法结果均不降”规则补足可执行
  路径；不加入 coverage-case 特判。

### Primary-model v2

- 把 v1 P4 中通过消融的 PM05 与 PM12 原则提前到第 1、2 位。
- 其余均值型发布规则统一要求完整战旗相对改善超过风险档门槛：0%/2%/5%。
- 二升一降收窄为前期且三格不高于 T2，并继续受风险档和改善门槛控制。
- 被早期规则遮蔽的 PM10 不再发布；没有新增 solver-action 分支。

两版均冻结 16 条有序候选，复杂度前沿为 `8/12/16`，前 12 条是发布候选；阶段为
`40-26`、`25-11`、`10-1`，每条最多三个可见条件，未命中时统一刷新。当前状态只能是
`candidate-frozen-unvalidated`。

## 冻结身份

冻结清单：
[`candidate-freeze-v2.json`](../playbooks/group-roll/candidate-freeze-v2.json)

| 候选 | semantic SHA-256 | file SHA-256 |
| --- | --- | --- |
| Rate-agnostic v2 | `2e4936c773722ba8979349cef4eb381d9699a10aeb6db1c11ccb33783c1b4e9a` | `f12f4089997d308c0f63aae38e34313c15e7be4f8da56822adbacdcbef00b115` |
| Primary-model v2 | `8a548206fae6072ef83c3979189049d00c9ab63074718a4a85ada7ab3b47cb0a` | `1308ac117f682dda7cdbb1e732667cb6e2395d180af43b977eaf49120b347c16` |

清单还冻结 canonical rule、P3 scenario policy、生产 handler、三份人工文档以及上述 P3
artifact 身份。测试会逐个重算 tracked file hash 和两个 playbook semantic hash；P3 开始后
任何候选改动都会失败，而不是静默变成另一份“v2”。

## 工程级审查与 Gate

| Gate | 结果 |
| --- | --- |
| v2 配置结构与关键顺序 | 通过 |
| provenance fail-closed 红绿测试 | 通过：修复前 `proxy` 未抛错，修复后 proxy/99% coverage 均拒绝 |
| 候选冻结 hash 自校验 | 通过 |
| 全量 Python 测试 | 通过：142 collected，141 passed，1 skipped |
| Ruff / format / diff | 通过：全仓检查无漂移 |
| `uv lock --check` / 依赖兼容 | 通过：77 packages compatible |
| 当前 Rule snapshot 校验 | warning：仅既有 early/late First Blood 与 percentile table 歧义 |
| 生产 route-separation 搜索 | 通过：`playbook.py` 无 solver/cross-audit import |
| v1 历史证据 hash | 通过：既有 evidence-package 自校验未漂移 |
| 大型产物与缓存 | 未纳入 Git；本阶段没有新增 replay 下载或 186 GB 缓存 |
| Parser/JAR | 未触碰 parser 源码或契约，因此不重建；冻结身份保持 |
| Web、客户端控制、凭据、Main | 未触碰 |

`ti audit fantasy-bcffa25a645c8438` 能重算并确认 artifact file hash，但在当前未提交 P2
工作树上按设计返回 `run-source_version-changed` blocker：run 记录的是干净起点
`ea8abce...`，当前源码已经加入 v2 handler 和文档。这不是 artifact 内容漂移；冻结清单
同时记录了 source commit 与文件 hash。既有数据/模型 warning 仍包括非目标联赛过滤、部分
目标队无正权重历史、isotonic 校准被滚动验证拒绝和 Coach 不可用，均没有被隐藏。

## 收口与下一阶段边界

项目级 diff 审查确认：v1 配置与证据没有修改，合法 provenance 下的既有行为没有改变；
预测/数据/推荐/solver 测试均通过，未发现临时探针或第二套 v2 production path。因此没有
可安全删除的旧生产代码；v1 文件必须作为历史证据保留。

P2 至此完成。下一阶段只能加载冻结 hash，使用新 seed 和与后续 held-out 审计分离的索引
运行完整 manual-only standalone validation。无论结果好坏都只更新验证证据与诚实状态，
不得回写候选规则。
