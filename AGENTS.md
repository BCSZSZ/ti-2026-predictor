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

## Liquipedia access

- Liquipedia 属于社区二手来源；自动化访问必须遵守其当前 API Terms。禁止自动抓取赛事页、百科页或其他生成的 HTML，也不得把 HTML fallback 当作 API。
- Liquipedia API Terms 允许定向客户端为自己的项目使用 MediaWiki API，无需仅因 `robots.txt` 另取书面许可。只允许按需调用明确的 `/dota2/api.php` Action API 模块；不得把定向查询扩张为递归遍历或通用索引。若实现属于 crawler，仍必须按真实 User-Agent 遵守当前 `robots.txt`。
- 全部 MediaWiki API 请求必须跨线程、跨进程共享同一个串行限流预算：不得高于每 2 秒 1 个请求，实现时相邻请求起始时间至少间隔 2.1 秒，禁止并发或突发请求。`action=parse` 同时使用独立限流预算，相邻请求至少间隔 30.1 秒；它只可在常规 `query` 无法满足需求时使用。
- LiquipediaDB API 是独立路径，必须先申请获批并遵循 Dashboard 文档；获批后每小时不得超过 60 个请求，API key 不得共享。
- API 客户端必须使用诚实、可联系的自定义 User-Agent，支持 gzip 并复用连接；不得使用库默认 User-Agent、冒充浏览器或伪装成其他机器人。API key 不得写入仓库、日志、产物或第三方消息。
- 尽可能长时间复用内容寻址缓存，不得重复请求相同数据；允许的响应仍须记录 URL、参数、抓取 UTC 和 SHA-256。发布或派生使用 Liquipedia 内容时，必须保留来源链接及适用的 CC BY-SA 3.0 署名。
- 人工解封只恢复受上述条款约束的访问，不放宽任何限制。遇到 `401`、`403`、`429`、CAPTCHA、挑战页或封锁提示时立即停止且零重试；若实现属于 crawler，遇到适用的 robots 禁止也必须停止。代理不得代替用户接受条款、求解 CAPTCHA 或解封，也不得通过更换 IP/VPN/代理、轮换或伪造 User-Agent、改 URL 抓 HTML、并发或重试来规避限制；只可报告状态并等待用户完成正常恢复流程或取得 Liquipedia 明确授权。
- 有限重试只适用于明确的瞬时网络错误或 `5xx`，且必须服从共享限流器；外部 API 不可用时保留旧快照并标注陈旧度，不得把缺失值当成零。

## Local-only boundaries

- 不存储 Steam 凭据，不控制 Dota 客户端，不自动填写预测。
- Web 服务默认只监听 `127.0.0.1`。
- 大型原始数据、缓存、截图和运行产物不得提交 Git。

## Agent skills

### Issue tracker

Work is tracked as local Markdown under `.scratch/<feature>/` when a durable ticket is needed. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository. Read `CONTEXT.md` before changing domain behavior and use `docs/adr/` only for hard-to-reverse decisions. See `docs/agents/domain.md`.
