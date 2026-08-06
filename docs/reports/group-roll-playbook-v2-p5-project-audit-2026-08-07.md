# Group Roll playbook v2 P5 project audit

状态：**P5 工程收口完成；两版手册保持 `draft`，另保留一项 replay JAR 包装身份 warning**

- 日期：2026-08-07
- 显式 `as_of`：`2026-08-06T17:27:00Z`
- 阶段起点：`main@b8848313844700323b2986a310dae70ffa93587d`
- 最终长运行实现提交：`1f48f8a`

## 阶段目标、最小范围与验收

P5 的目标是闭合 v2 证据包、证明同快照/配置/seed 的长运行可复现、做全项目回归和清理判断，
并另交一份不依赖工程术语的易懂总结。P5 不获准调整手册规则、Stat 数值、模型、随机 seed、
release gate 或历史 v1 结论。

最初冻结的最小范围只有证据包、离线哈希测试、README/runbook/索引和报告。确定性预检发现
artifact 来源选择缺陷后，范围只扩到该根因：v2 policy 冻结确切 P3/P5 artifact 路径，加载时
fail closed；v1 默认行为继续不变。没有新增 full-session P5，也没有把 solver/oracle 结果回写
到人工规则。

验收要求是：standalone 语义/文件 hash 复现；path-pinned 108 行 audit 连续两次产生同一
run ID、语义和文件 hash；正式 artifact 在其干净 source commit 上可审计；完整项目测试、规则、
依赖、replay 契约和安全边界无新增 blocker；只有已完整替代且无历史用途的路径才可删除。

## 确定性缺陷与最小修复

P3 standalone 的确定性复跑生成了第二个内容逐字节相同、run 路径不同的 artifact。P4 的旧
来源发现函数只冻结 evidence semantic hash；存在多个相同副本时，它按目录名选择最后一个，
同时把该物理路径写入 source manifest。这不会改变 108 行数值，却会改变 evidence semantic
和文件 hash，违反项目的同输入确定性要求。

诊断先加入秒级红测试：两个 artifact 声明同一语义哈希时，调用方必须能锁定预注册路径。旧
接口按预期因不支持该参数而失败。最小修复随后：

- v2 cross-audit policy 增加冻结的 P3 standalone 与历史 P5 artifact 路径；
- 路径必须位于 `artifacts/`、文件名匹配、文件存在且内部 semantic hash 一致，否则失败关闭；
- `prepare_solver_context` 只在调用方显式传入时采用冻结路径，默认 v1 发现行为不变；
- 新增重复语义 artifact 回归测试，并锁定新的 v2 policy semantic hash；
- 不改变 solver 算法、exact oracle、抽样索引、手册、release gate 或任何一行决策。

修复后的 policy file SHA-256 为 `c591d90dd5725f57ae847462f74cbf75afc35b748ac85a5d713b1ad577649217`，
semantic SHA-256 为 `5aee998b6aab224fbe986fe894558c604db9e96625790cfc3f1847bd36a834d7`。
修复提交前后完整 108 行、summary 和 gate 逐字段相同。

## 确定性长运行验收

### Standalone

- 原正式 run：`fantasy-1c8871c419f59f08`
- P5 复跑：`fantasy-9e3dfc60cc576e79`
- 两者 evidence semantic：`77032ccf42dccd2d6a7bda1e9f51786245b955f0ed548d934c5c9f956bc7e299`
- 两者 artifact file SHA-256：
  `38751743bb44c8f0aa79e7ca75cb02d3d152f15e6bc5a52e38a98ab073a84783`
- 复跑总墙钟：1,494.43s（24 分 54.4 秒）
- 干净 source 审计：`publishable: true`、无 blocking issue

复跑完整重现 Rate 的 23 个 10% Common 失败和 Primary 的零个 10% Common 失败、五条核心
规则失败与两个风险修正失败。它没有因为结果已知而改动候选。

### Path-pinned read-only cross-audit

- 最终 run：`fantasy-26e4f9240b19a518`
- evidence semantic SHA-256：
  `d0f90db675344da733e44e7acd9069b729f5b12fc7ff15d268b7963aa73f3a0a`
- artifact file SHA-256：
  `0f01ffb2146c73addd96a950e31fc37447d603a3cc1b8518153770242c49db56`
- source manifest SHA-256：`abb3e90fdb9f6a5732c6ff674def2857a77e88ccd060ec8d3fe35a6219295fbd`
- 第一次 / 第二次总墙钟：2,679.16s（44 分 39.2 秒）/
  2,726.74s（45 分 26.7 秒）
- 两次均为同一 run ID、semantic hash、file hash；不可变 writer 没有发现字节差异
- 干净 source 审计：`publishable: true`、无 blocking issue

两次都完成 108/108，audit 索引与 standalone/P5 索引交集均为 0。Rate 没有重大例外，
Primary 在 `coverage-05`、剩余 3 Roll、`P2M02` 保留一个同时劣于刷新的方向性例外。两版
最终标签都是 `draft`，且 `promotion_permitted=false`。

最近一次 standalone 加第一次 path-pinned audit 合计 4,173.60s，即 1 小时 9 分 33.6 秒。
这通过两小时工程目标；第二次 audit 是额外的确定性验收，不是正常使用所需的重复成本。

## Replay JAR 身份 warning

Java replay parser 的受版本控制源码和契约自 v2 起点完全未改。项目当前 target JAR 是
18,190,096 bytes、SHA-256 `8be3def5ecb8fe5dfcb890363e786369bd2fde8044511aab8b1c0ab43e645bd1`，
而 v1 原生回填使用并记录的是 18,190,089 bytes、`fc109d605a…`。因此“当前 JAR 仍等于 v1
历史 JAR”的字节身份检查没有通过。

P5 没有用当前 JAR 重写任何 raw 响应或处理表。两次正常 Maven package 产生完全相同的当前
JAR；冻结的 6 个真实 replay 集成测试也通过全部 300 个逐人值和 build/schema 检查。现有证据
支持“当前构建在现工具链下可复现，已测解析语义一致”，但不足以声称两个 JAR 逐字节相同或
断言唯一漂移原因。历史 raw 元数据继续保留 `fc109d…`；本 warning 随最终证据包披露。

## 项目级回归与安全边界

最终收口门禁记录如下：

| 项目 | 结果 |
| --- | --- |
| 完整离线 Python tests | 通过：152 passed，1 skipped in 24.82s |
| 冻结 6 replay 集成测试 | 通过：1/1，300 个逐人值一致 |
| Ruff / format / diff | 通过；138 files already formatted；`git diff --check` 无错误 |
| lock / 依赖兼容 | 87 packages resolved；77 packages compatible |
| `ti rules validate` | 仅 3 条既有客户端语义 warning，无新增 blocker |
| 正式 standalone / cross-audit artifact | 均在各自干净 source commit 上 `publishable: true` |
| 人工路线隔离 | production manual modules 无 solver/cross-audit import |
| 本地与客户端边界 | 无 `0.0.0.0` bind、Steam 控制或自动填写新增 |
| Main | 既有状态/UI fail-closed 测试通过，P5 未改 Main 代码 |
| debug 残留 | 无 TODO/FIXME/HACK/XXX/debugger 命中 |

v2 正式 Stat 仍是 16 个 `exact`、2 个获准 `derived`、0 个 `proxy`、0 个 `unavailable`；
Coach 继续 `unavailable/excluded`。没有未来信息进入 `as_of`，没有 proxy 填 exact `null`，没有
在线网络进入测试，也没有新增数据读取。

## 清理与最终结论

清理审查没有找到可安全删除的 production 路径：v1 policy、手册和 artifact 是不可变历史兼容
证据；旧 P4 run 是 path-pinning 修复前的有效阶段记录，且与最终 108 行完全一致；新 v2 路径
不是对 v1 的无条件替代。删除任何一项都会破坏复现链，因此没有进行代码或 artifact 删除。

P5 按“工程成功、经验发布门禁失败、另有 JAR 包装身份 warning”收口。最终证据包固定全部输入、
正式输出、复跑、标签和限制；另见面向实际使用的
[易懂总结](group-roll-playbook-v2-summary-2026-08-07.md)。
