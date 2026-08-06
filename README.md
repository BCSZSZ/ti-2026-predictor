# TI 2026 游戏内预测决策台

这是一个只在本机运行、可复现的 TI 2026 游戏内活动辅助工具。它覆盖：

- 小组赛 16 项预测；
- 主赛事 14 节点双败预测；
- 2026 新版 Fantasy（核心双人组、中单、辅助双人组、战旗与教练）；
- 规则、数据覆盖、时间泄漏和运行产物审计。

LLM 不参与最终数值结论。推荐由版本化规则、数据快照、统计模型和固定随机种子产生。

## 快速开始

```powershell
uv sync --extra dev
uv run ti rules snapshot --as-of 2026-08-12T23:00:00Z
uv run ti rules validate
uv run ti data sync --as-of 2026-08-12T23:00:00Z --year 2026 --team-detail-limit 20 --request-limit 500
uv run ti forecast group --as-of 2026-08-12T23:00:00Z --profile all
uv run ti fantasy recommend --as-of 2026-08-12T23:00:00Z --period group --profile all
uv run ti web
```

默认网页只监听 `127.0.0.1`。首次同步会访问 OpenDota；测试永远不访问实时 API。
数据同步默认分页获取 `as_of` 所在 UTC 年份的 OpenDota 职业比赛目录，并关联游戏版本与
OpenDota 赛事级别。Web 可按时间、版本和赛事级别过滤。同步还会补齐当前 16 队每队最近
20 场逐场详情，并按 `match_id` 断点续传；可用 `--team-detail-limit 0` 只保留比赛摘要。

付费 OpenDota key 只放在已被 Git 忽略的 `.env`，由 `uv run --env-file .env` 注入。客户端按
`$5/月 = 50,000 次`设置带 key 请求尝试的本地硬上限，并对单次运行上限、重复成功请求和有限
递增重试作统一保护；详见 [OpenDota API 使用计划与安全规范](docs/opendota-api-usage.md)。

Fantasy 的正式历史范围按当前 TI 名单中的稳定玩家 ID 选择，并包含他们在旧战队参加的
`premium/professional` 比赛。首次全量或后续增量同步使用：

```powershell
uv run ti data fantasy-history --as-of 2026-08-01T15:00:00Z --year 2026
```

该命令逐个请求、遵守 OpenDota 响应中的限额、每批落盘并可断点续传；它不会请求 `.dem`
或自动提交 replay 解析任务。五项 replay 原生统计需要 Java 21+，并使用独立的可恢复步骤：

```powershell
Push-Location src/ti_replay_parser
.\mvnw.cmd -q '-DskipTests' package
Pop-Location
uv run ti data replay-fantasy --as-of 2026-08-01T15:00:00Z --year 2026 --workers 4
```

它下载并保存不可变的 Valve replay，解析 Madstone、Smoke、Watcher、Lotus 与 Tormentor
逐人原生计数，并把旧 OpenDota event-map 值隔离到诊断表。命令默认复用已验证检查点；
缺失 replay、缺失字段，以及未获准 build 的 Watcher 保持 `null/unavailable`，绝不以 proxy 或
getter 默认零回填。数据表、状态和历史回填结果见
[Fantasy 覆盖契约](docs/fantasy-coverage.md)与
[P1 实装报告](docs/reports/p1-native-replay-stats-implementation-2026-08-06.md)。

`fantasy_performance_samples.parquet` 中一行表示“一名玩家在一局比赛中的表现”，只是
Fantasy 模型的历史输入。三张定位卡片、徽标、教练及重选策略才是 Fantasy 推荐结果。

完整操作顺序、主赛事种子导入和状态含义见 [docs/runbook.md](docs/runbook.md)。模型的时间
切分、覆盖门槛和三种目标见 [docs/modeling.md](docs/modeling.md)。

## 可选 OCR

```powershell
uv sync --extra dev --extra ocr
uv run ti ocr inspect path\to\fantasy-screenshot.png
```

OCR 结果只生成待确认草稿，不控制 Steam，也不会自动提交游戏内选择。

## 数据与发布状态

- 原始响应、抓取元数据和哈希保存在 `data/raw/`。
- 规范化 Parquet 和 DuckDB 保存在 `data/processed/` 与 `data/ti.duckdb`。
- 每次推荐写入 `artifacts/<run_id>/`，包括输入哈希、Git 版本、模型参数、随机种子和审计结论。
- 当规则、阵容或关键数据覆盖不满足要求时，结果状态为 `blocked`，不能作为可发布推荐。

## 当前边界

- 瑞士轮完整配对细则尚未发布，因此小组结果包含三种合法容量情景的敏感度警告。
- 主赛事实际八队与种子未写入前，14 节点网格会生成但保持 `blocked`。
- Fantasy 默认只用覆盖充分的 `exact/derived` 字段；五项原生 replay 统计只有通过逐场状态、
  字段存在性和 Watcher build 门槛后才参与，OpenDota proxy 永不参与默认最优解。
- OCR 是可选第二阶段，只输出需要人工确认的草稿。
