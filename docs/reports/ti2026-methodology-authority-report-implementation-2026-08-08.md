# TI 2026 方法与证据权威性报告：实施、问题与验收记录

状态：**最小文档实现与数值验收完成；Git 发布状态以仓库历史为准**

- 阶段开始：`main == origin/main == e38f3b778e7dd580adfc7c80c0e588a95094771d`
- 开始时工作树：干净
- 实施分支：`codex/methodology-authority-report`
- 正式报告：
  [TI 2026 梦幻挑战与赛事预测：方法与证据权威性报告](ti2026-methodology-and-evidence-authority-report-2026-08-08.md)

## 1. 阶段目标、最小范围和验收标准

本阶段目标是把梦幻挑战和赛事预测分散在规则、代码、数据契约、运行产物和旧实施报告中的依据，
收口为一份可发布、可追溯、不会夸大预测能力的方法报告。

最小修改范围固定为：

1. 新增正式权威性报告；
2. 新增本实施、问题与验收记录；
3. 更新 README 的当前入口；
4. 不修改 `src/`、测试、配置、客户端规则、模型政策、数据、artifact 或随机种子。

验收标准固定为：

- 每个关键数字能回指受版本控制的配置/代码或冻结本地产物；
- Valve 官网事实、客户端事实、OpenDota 第三方数据、`exact`、`derived` 和模型推断不混写；
- Fantasy 的 18 项 provenance、replay 原生替代、Series 抽样、CVaR10、bootstrap 和 Roll 门禁写全；
- 赛事的时间权重、连通证据图、Elo/Glicko、滚动校准、TI 2025 留出和 Group 近似写全；
- 明确 Coach、Main Roll、完整 v2 Roll、概率校准和精确 Swiss 的缺口；
- 本地链接、冻结身份和主要指标反算通过；
- 全量项目测试通过，且项目级审查确认没有改变任何推荐结果。

## 2. 全体代码和证据状态审计

阶段开始前检查了：

- `CONTEXT.md`、`docs/data-contracts.md`、`docs/modeling.md`、`docs/forecast-protocol.md`、
  `docs/fantasy-coverage.md` 和 `docs/leakage-policy.md`；
- `config/rules/ti2026.json`、`config/models/team-strength-v2.json`、
  `config/models/fantasy-group-scenarios-v1.json` 和 `config/ti2026.yaml`；
- Fantasy 的 scoring、scenario、valuation、roll 和 playbook validation 正式代码；
- Forecast 的 ingest、evidence、ratings、backtesting、group simulation、run manifest 和 audit 代码；
- P1 replay、P3 Fantasy、v2 Roll、TI 2025 backtest、当前 Group Forecast 和 7.41 Series 证据；
- 两个客户端规则快照 build `6888:10887746` 与 `6891:10893022`。

审计结论：现有生产逻辑与冻结产物足以支撑方法报告，不需要为了“显得更权威”重训或改模型。
真正需要做的是把证据级别和限制收紧。没有发现需要本阶段修改的 domain behavior。

## 3. 一手来源核验

本阶段依照 research workflow 做了独立来源核验，内部备忘保存于 Git 忽略的
`.scratch/authority-report/primary-source-findings.md`。主代理随后逐项回看正式源文件和冻结 JSON，
没有直接把研究备忘当成未经复核的结论。

来源边界确认如下：

- Valve 2026 官网公告可直接支持活动、Swiss/Bracket Prediction、Core/Mid/Support 新结构、Coach
  高层作用和相对参与者奖励；
- 18 项分值、颜色、槽位、品质、操作权重、league `19719`、40/30 Rolls、Period 计分顺序和
  1/2/5/5/2/1 容量，需要当前本机 Valve 客户端快照充分支撑；
- OpenDota 是公开源码、可审计的高可信第三方，不是 Valve 官方比赛数据库；
- Clarity 是 replay decoder，不单独证明 Fantasy 字段业务语义；
- 社区 Tier 与奖金只用于赛事背景展示，不进入当前队伍强度模型。

正式报告引用了 Valve、OpenDota、固定协议/parser commit 和 Clarity 的直接链接；玩家结论仍以本地
不可变抓取时间和 SHA-256 为复现锚点。

## 4. 专项反算验收

### Fantasy

从 `config/rules/ti2026.json` 和
`artifacts/fantasy-5e21be304ea57672/group-fantasy-evidence.json` 读回确认：

- 18 项 Stat = 16 `exact` + 2 `derived`；
- 正式情景 8,192；
- 正权重 Game 4,388；
- 完整 BO2/BO3 Series 1,405；
- 48 个 team×role pool；
- 10,334 个目标玩家单局行；
- 42 个 bootstrap 组、672 个队伍排名行；
- 400 次 replicate，每次 512 个情景。

从 P1 报告和 replay 产物身份读回确认：2,055 局、20,550 原生玩家行、113 个获准 Watcher cohort、
183.876 GiB 压缩 replay 和 6 个真实 fixture 的 300 个玩家统计值。

从 `docs/playbooks/group-roll/evidence-package-v2.json` 读回确认：

- rate-agnostic 的 10% Common 失败为 23；
- primary-model 的 10% Common 失败为 0，但核心规则/风险门禁仍失败；
- held-out cross-audit 完成 108/108；
- 正常 standalone + cross-audit 为 4,173.599 秒；
- 两份完整候选状态均为 `draft`。

### 赛事 Forecast

从 `artifacts/group-bcf9e6751005c6cf/model.json` 读回确认：

- 当前目标连通图为 463 队、3,943 个正权重 Game；
- 7.41 为 1,936 局，7.40 为 2,007 局；
- 当前入模等级全部是 OpenDota `professional`；
- 总有效权重为 691.656557。

从 `artifacts/backtest-3381891f1fac3f70/backtest.json` 读回确认：

- TI 2025 固定留出 144 局；
- 正式加权集成 accuracy 56.25%、log loss 0.682552、Brier 0.244712、ECE 0.113417；
- 50% 概率基线 log loss 0.693147、Brier 0.25；
- 理论随机猜测 50%，所以正式模型的 accuracy 提升按 6.25 个百分点表述；
- 加权 Elo 在这次 holdout 上更好，但没有在看完 holdout 后事后切换；
- isotonic 候选未通过滚动 log-loss 门禁，当前概率保持未校准。

### 文档结构

- 正式报告 31 个 Markdown 链接中的所有本地目标均存在；
- 关键警示语均存在：不是 BO3/BO5 胜率、未经校准、Coach 排除、Roll 草案、Swiss 近似；
- README 当前入口指向正式报告；
- `git diff --check` 未发现空白错误。

## 5. 旧 run 审计为什么在当前分支阻断

直接执行：

```powershell
uv run ti audit fantasy-5e21be304ea57672
uv run ti audit backtest-3381891f1fac3f70
uv run ti audit group-bcf9e6751005c6cf
```

三个旧 run 都按设计产生 `run-source_version-changed` blocking，因为它们记录的源码 commit 分别是
`c652fd7...` 和 `018965b...`，当前分支则从 `e38f3b7...` 开始且已经新增报告。Fantasy run 还正确
指出当前 processed data 已推进到新的 SHA、规则快照已更新，并有 11 行比赛晚于旧 `as_of`。

这不是冻结产物失效，而是审计器防止用户拿“当前源码/当前数据”冒充“当时源码/当时数据”。三个
artifact 自带的不可变 `audit.json` 仍记录生成当时的 `publishable: true / status: warning`；报告
同时保留 run commit、data SHA、rule snapshot 和 seed。若要原样复验旧 publishable 状态，必须先
还原对应 commit 与处理后数据快照。

## 6. 自动测试

项目级检查结果：

- `uv run ruff format --check src tests`：72 files already formatted；
- `uv run ruff check src tests`：All checks passed；
- `uv run pytest`：155 passed，1 skipped，26.87 秒。

本阶段只改 Markdown，仍执行全量测试，以确认没有意外改变 CLI、模型、Fantasy 或发布审计行为。

## 7. 问题 Memo

正式报告保留以下未解决事项：

1. Coach 没有完整且情景对齐的前缀+后缀未来候选，生产估值排除；
2. Fantasy 三定位在给定队伍赛果后独立抽样，未建模跨定位历史相关性；
3. Group 的 Series 机会数和赛事六类结果是容量保持近似，不是逐轮 Swiss；
4. Roll 的服务器目标/子选择率未完全公开，两份完整 v2 手册仍为 `draft`；
5. Main Roll 与自动 Dota 操作不支持；
6. TI 2025 回测是透明 retrospective holdout，不是未来 untouched tournament；
7. 当前中立单局概率未校准，细小百分比差不能当成确定优势；
8. Early/Late First Blood 与 Percentile 存在客户端内部/可见文案冲突；
9. 社区 Tier/奖金会随页面更新，且不属于当前模型输入；
10. 较早的 8 月 2 日固定 Fantasy 阵容没有被包装成与 8 月 6 日 P3 同截止的最终阵容。

## 8. 工程项目级审查和收口

项目级审查确认：

- 变更仅为正式报告、实施记录和 README 索引；
- 没有修改 `src/`、测试、配置、规则、模型、Parquet、DuckDB、artifact 或 seed；
- 现有 Forecast、InGamePrediction、Fantasy 和 Roll 术语边界保持不变；
- 不可变 raw、replay、缓存和 `.scratch` 研究备忘均未加入 Git；
- 没有生产路径被替换，因此没有可安全删除的旧代码；
- 旧报告继续作为对应历史 `as_of` 的证据，正式 README 新入口负责说明当前总口径。

结论：本阶段没有破坏其他功能，也没有需要清理的 superseded production path。正式报告可合并；
未决问题必须作为报告边界保留，不能通过删掉 warning 来“收口”。
