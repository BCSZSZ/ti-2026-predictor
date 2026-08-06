# P4 — 独立人工手册实装与验证报告

## 阶段基线

- 基线 commit：`3dcab4795286df5ddb272a376ad71f4d40adef37`
- 基线状态：P1 原生计数、P2 Group 40-Roll 转移、P3 公共场景与终局估值均已通过测试并推送。
- P3 正式证据：`f42517fa5c0c596f2b15397ad2206136d48b0ff7fef578e131b4a919aa7fd9b8`
- P4 开始前未生成、未读取任何 P5 Reference Roll solver 输出。

## 阶段目标、最小范围与验收标准

P4 只做三件事：

1. 把 P3 的七组 Stat 证据及精确 Quality/Trait 算术变成人可读表；
2. 在求解器路线之外，预先冻结生成率无关版与主模型 best-guess 版的 8/12/16 条嵌套候选，
   发布候选最多 12 条；
3. 独立验证完整 40-Roll 会话、复杂度前沿、规则消融与 10%/5% 重大损失门槛。

最小修改限于 `config/playbooks/`、`src/ti_predictor/fantasy/playbook*.py`、对应离线测试、两份
Markdown 手册及本报告。P4 不实现 P5 搜索、不修改 P1–P3 数学定义、不支持 Main、不接触
Dota 客户端。

验收标准沿用冻结总计划：候选规则和证据 hash 可复现；每版不超过两张快查页、12 条发布
规则、三阶段、每条最多三个直接条件及一个刷新兜底；九种起始覆盖层×三角色的完整 40-Roll
验证；主模型版按主模型过门，生成率无关版需在三种模型均过门；Common 情况 95% 单侧损失
上界不得超过 10%，5% 单独报告；证据不足必须标 draft/unresolved。

## 独立冻结点

以下文件在任何 40-Roll 验证、规则消融或 P5 求解器运行之前写成：

- `config/playbooks/group-rate-agnostic-v1.json`
- `config/playbooks/group-primary-model-v1.json`
- `docs/playbooks/group-roll/stat-quality-trait-evidence-v1.md`
- `docs/playbooks/group-roll/playbook-rate-agnostic-v1.md`
- `docs/playbooks/group-roll/playbook-primary-model-v1.md`

冻结 SHA-256（在首次验证前填入）：

- Rate-agnostic 候选：`c472e65c35837f54ee32dcf171ff7ccf6f53257bf276c855669ad95c37688cfa`
- Primary-model 候选：`b11e398b44c512bc34ef55d087a0afd7c08bb8287909df1d7aa26c405d439b93`
- Stat/Q/T 证据表：`e97c421e4e8bd1cd1dd3e2c9626545c6649768f1c37f1cd7d7e2a26cb6bab5cd`
- Rate-agnostic 手册：`4a064928771a08f605856c7859699c7360ba7cfc3dd2fc276dfa92a069ec6b32`
- Primary-model 手册：`845eeea8f17ea3f53b401e519981bc6eaf38b2373162db5b3f1aec539816d527`
- 联合冻结清单：`26741f869d863e12ac57c3e6f87ba82c3aafa2867e7b1fb6f5dce65a65993424`

候选配置中的前 8、前 12、前 16 条分别构成预注册的嵌套复杂度候选；发布文本只显示前 12
条。后续验证可以把版本判为 `baseline-reliable`、`strict-reliable`、`draft` 或
`inapplicable`，不得就地修补本批规则。任何修订必须另开 v2 并重新完成独立验证。

## 验证结果

### 执行口径

- 正式命令：`ti fantasy group-playbook-evidence --as-of 2026-08-06T08:15:00Z`
- 正式 run：`fantasy-99d3b0ecf4e9c5e9`
- 语义证据 SHA-256：
  `a0361a228629c46663fe844387af7f71eea37113838b3036dc6181dd227ad857`
- 证据文件 SHA-256：
  `25e25d92649689cbd1201939a606950b30ff79286626dc08ec47b859e89da89d`
- 验证配置文件 SHA-256：
  `efaf52c3b774bc412db07a324758b15bd61d1b956246e9ce6295bc2cd092db1b`；
  语义 SHA-256：`19b505159bb7c42b93d952359932e26dd0434ff4ae9283738432784afe685865`。
- P3 源证据、数据、pool 与源场景分别复现为
  `f42517fa…`、`931cd7e0…`、`47bb84b1…`、`872533c3…`；512 个固定无放回验证场景为
  `f1698113b044baf07609fb7d43e94dc3ff45592112ecfd2ba0109f61803ce4dd`。
- Rule snapshot 为 `20260806T081345Z-702ddf2a6953`，SHA-256 `702ddf2a…`。
- 每版每个 8/12/16 候选、每模型、每覆盖格运行 64 个完整 40-Roll 会话；前 16 个作为
  screening，后 48 个作为 confirmation。主候选共 10,368 个完整会话；48 个发布规则×模型
  消融批次另运行 20,736 个完整会话，总计 31,104 个会话、1,244,160 次人工规则决策。
- 九个完整起始状态让 Core、Mid、Support 各自恰好覆盖 low/middle/high Stat readiness ×
  low/middle/high Configuration readiness。readiness 使用 512 个固定场景的同队期望值相对
  本角色最佳合法值分成秩三等份，不使用初始状态概率。
- 后续三个共享选项由独立 step/model/case/replicate 随机流生成，因此不同手册和消融策略即使
  选择不同动作，下一轮 offer 仍严格配对；mutation 与比赛表现使用另外的固定随机流。

### 验证器审查中修正的两个问题

第一次完整运行暴露两项验证器错误，均在不修改冻结候选的前提下修正并完整重跑：

1. 动作比较字符串带各版规则 ID，使两版即便选了同一 Banner/operation 也被误报为分歧；
   正式结果只比较 `role:operation_id`，首决策真实分歧率为三模型均 33.33%，不是 100%。
2. apply 的 mutation 与 replacement offer 曾共用一个 RNG，导致不同动作消耗不同随机数后
   下一轮 offer 不再严格配对；正式结果把 offer、mutation、比赛表现拆成独立随机流，并用
   单测证明不同策略的 41 个 observed/replacement offers 完全一致。

起始 readiness 也由早期的单项最佳近似升级为正式的同队期望秩三等份。修正后两次完整运行
的所有数学结果逐字段一致。最后从语义证据中移除非确定的墙钟耗时；耗时只写入本报告和 CLI
返回值，不再污染可复现 hash。

### 12 条发布候选的点估计

以下“均衡覆盖”只是九格等量诊断汇总，不能解释为真实起始状态的总体期望：

| 手册 | 验证模型 | ε=0 期望 Group 分 | ε=0 CVaR10 | fallback/决策 |
| --- | --- | ---: | ---: | ---: |
| Rate-agnostic | client-weight-primary-v1 | 54,361.79 | 40,391.58 | 66.7% |
| Rate-agnostic | flattened-weights-v1 | 54,105.18 | 39,727.31 | 65.2% |
| Rate-agnostic | sharpened-weights-v1 | 51,785.24 | 37,695.05 | 68.0% |
| Primary-model | client-weight-primary-v1 | 61,807.96 | 47,287.57 | 41.7% |
| Primary-model | flattened-weights-v1（敏感性） | 62,747.58 | 48,499.92 | 42.6% |
| Primary-model | sharpened-weights-v1（敏感性） | 59,417.58 | 44,518.72 | 40.1% |

Primary-model 相对 Rate-agnostic 的较高点估计只在声明模型下成立，不证明客户端权重就是真实
后台率。两版在每个 576 会话批次中最终都至少有一步不同；第一步有 33.33% 会话不同。

### ε 风险前沿

| 手册（主模型） | ε | 期望 Group 分 | CVaR10 | 相对 ε=0 均值 | 相对 ε=0 CVaR10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rate-agnostic | 0% | 54,361.79 | 40,391.58 | — | — |
| Rate-agnostic | 1% | 53,849.25 | 40,802.25 | -0.94% | +1.02% |
| Rate-agnostic | 2% | 53,421.62 | 40,894.44 | -1.73% | +1.24% |
| Rate-agnostic | 5% | 53,173.35 | 40,776.92 | -2.19% | +0.95% |
| Primary-model | 0% | 61,807.96 | 47,287.57 | — | — |
| Primary-model | 1% | 61,695.81 | 47,731.93 | -0.18% | +0.94% |
| Primary-model | 2% | 61,597.75 | 48,474.64 | -0.34% | +2.51% |
| Primary-model | 5% | 61,222.18 | 48,386.48 | -0.95% | +2.32% |

Primary-model 的点前沿支持 2% 为当前 knee：5% 不再增加 CVaR10。Rate-agnostic 的保守 knee
是 1%，2% 给出更高 CVaR10 但边际交换较差。P4 没有为三个 risk overlay 另做独立下界确认，
所以这些是显示结论，不把任何 risk overlay 标成已通过规则。

### 8/12/16 人工复杂度前沿

在主模型、`epsilon=0` 下：

| 手册 | 8 条相对最佳损失（均值 / CVaR10） | 12 条 | 16 条 |
| --- | ---: | ---: | ---: |
| Rate-agnostic | 3.88% / 6.79% | 0.00% / 0.00% | 0.06% / 0.12% |
| Primary-model | 3.07% / 4.57% | 0.10% / 0.46% | 0.00% / 0.00% |

两版 12 条候选都在最佳候选的 1% 内；8 条候选只达到 Primary-model 的 5% 档，且
Rate-agnostic 连 5% 档也没有同时通过。因此可读性上限 12 条没有被 16 条比较器推翻。

### Common 情形重大损失与规则消融

Rate-agnostic 在三模型共识别 229 个 Common 情形：

- 5 个情形的均值或 CVaR10 单侧 95% 损失上界超过 10%；46 个超过 5%；
- 10% 失败为 primary/coverage-04/RA06，flattened/coverage-04/RA10，
  flattened/coverage-07/RA12，以及 sharpened/coverage-01 的 RA08、RA10；
- 最大均值损失上界 4.83%，最大 CVaR10 损失上界 12.34%；
- 只有 RA01、RA03、RA08 在三个模型的规则消融中都同时取得均值/CVaR10 单侧无损证据与
  至少一个严格点改善；RA04 在当前七张 Stat 表下从未激活。

Primary-model 在发布模型识别 93 个 Common 情形：

- 0 个超过 10%，10 个超过 5%；最大均值/CVaR10 上界分别为 1.70%/6.73%；
- 只有 PM05（精确洗 T1/T2 品质）和 PM12（末期明显正期望门槛）通过严格规则消融；
- PM10 被更早规则完全遮蔽、从未产生增量；其余规则至少有一个均值或 CVaR10 单侧下界小于
  零，不能仅凭正点估计称为核心规则。

因此两版都必须保持 `draft`。Primary-model 虽通过 10% Common 门槛，但“所有发布核心规则
必须通过消融”的验收项失败；Rate-agnostic 同时失败 10% Common 门槛和跨模型消融。P4 没有
用结果修补 v1，也没有查看或运行 P5 solver。

### 人工产物状态

- 七张 Stat 表、Quality 表和 Trait 精确配方可独立查阅；没有 hard-protect Stat，bootstrap
  边界不改变点估计分档。
- 两份 Markdown 均可在没有 simulator 时执行，但页首现在显式标为 `draft`，不再让“候选
  可读”被误解成“已经证明可靠”。
- 验证后的文档 SHA-256（仅增加状态/结果警告，不修改冻结的 12 条规则）为：
  Rate-agnostic `5db6e0ee6458701b6af0e6ed0d14ca7a7698372f18f96fab752af04bfce3f758`，
  Primary-model `9f00b5fabad27195e87c1c76535c1bcabf50780cd81ab6f6e3a0e9b92623fe1b`。

### 性能

最终正式运行：P3 源证据复现 `15.20s`，分析上下文重建 `14.97s`，P4 standalone validation
`1363.96s`，总计 `1394.13s`（23 分 14 秒）。这比三小时目标少约 2 小时 37 分，也远低于
五小时硬上限。峰值工作集在观察中约 1.4 GB；未触发 4h45 停止新计算兜底。

## 工程审查与收口

- 正式路径只依赖 `playbook.py` 与 `playbook_validation.py`；不存在对 P5 solver 的 import，
  两版配置和规则表保持独立版本与 hash。
- 未来 offer、mutation、Group 表现分别用独立确定性随机流；不同候选、消融和版本的 future
  offers 逐步配对。
- runtime 不进入语义 evidence hash；修正后上一轮移除 runtime/hash 与最终 artifact 深比较
  为逐字段完全相等。
- Main 在 playbook config、状态校验和 CLI 中仍明确不支持；没有客户端控制、Steam 凭据或
  OCR 自动动作。
- 旧推荐、P1 原生字段、P2 转移和 P3 终局接口均未被替换，没有可安全删除的旧生产路径。
- `ruff format --check src tests` 报告 56 个文件均已格式化，`ruff check src tests` 全绿；完整
  离线测试为 `106 passed, 1 skipped in 19.65s`，唯一跳过项仍是缺少可选本地 replay 缓存的
  集成测试。
- `ti audit fantasy-99d3b0ecf4e9c5e9` 返回 `publishable: true`、`status: warning`，输出文件
  SHA-256 与本报告一致；warning 明确包含两版 `draft`，以及既有 First Blood、percentile、
  校准/证据警告，没有新的 blocking issue。
- 在首个 P4 commit `6fd0b61aace858e0760dfb9bdcde003eed358fdd` 的干净工作树上完成独立
  复现 `fantasy-d9e35d3e81c5d466`：语义 evidence SHA-256 仍为
  `a0361a228629c46663fe844387af7f71eea37113838b3036dc6181dd227ad857`，artifact 文件
  SHA-256 仍为 `25e25d92649689cbd1201939a606950b30ff79286626dc08ec47b859e89da89d`；两次
  输出逐字节一致，且 rate-agnostic / primary-model 的门禁结论仍均为 `draft`。
