# Repository rules

## Domain and source priority

- “游戏内预测” (`InGamePrediction`) 指 Valve 的 TI 活动答案；“模型预测” (`Forecast`) 指本项目产生的概率分布。不得混用。
- 规则来源优先级：本机当前 Dota 客户端及 Valve 公告，其次是官方/开源 API 与源代码，最后才是社区资料。
- 不得直接复制无明确许可证的社区计算器代码。它们只能用于黑盒差分核对。

## Time and reproducibility

- 所有数据读取、特征生成、训练和推荐入口必须接受显式 UTC `as_of`。
- 任何时间晚于 `as_of` 的比赛、阵容、规则快照或外部信息都不得进入该次运行。
- 原始响应不可覆盖；必须记录来源 URL、请求参数、抓取时间和 SHA-256。
- 每次运行必须记录 Git commit、规则版本、数据快照、模型配置和随机种子。

## Identity and data quality

- 战队和选手只能用稳定 ID 连接；名称仅用于显示。
- 阵容必须具有生效区间；替补和 stand-in 不得回填到更早比赛。
- Fantasy 缺失值必须保持 `null`，不得当成零。统计项须标注 `exact`、`derived`、`proxy` 或 `unavailable`。
- 客户端规则冲突必须显式记录。影响结果的未验证规则默认排除，并阻止相关输出标记为可发布。

## Models and tests

- 不允许随机拆分时间序列；使用滚动时间回测。
- 胜负模型至少与 50%、Elo/Glicko 基线比较，并报告 log loss、Brier 与校准。
- 正式逻辑只能存在于 `src/`；Notebook 只可用于临时探索且不得作为运行依赖。
- 单元测试禁止实时网络访问，只使用固定 fixture。
- 相同快照、配置和随机种子必须产生相同推荐 JSON。

## Local-only boundaries

- 不存储 Steam 凭据，不控制 Dota 客户端，不自动填写预测。
- Web 服务默认只监听 `127.0.0.1`。
- 大型原始数据、缓存、截图和运行产物不得提交 Git。

## Agent skills

### Issue tracker

Work is tracked as local Markdown under `.scratch/<feature>/` when a durable ticket is needed. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository. Read `CONTEXT.md` before changing domain behavior and use `docs/adr/` only for hard-to-reverse decisions. See `docs/agents/domain.md`.
