# Streamlit 手动版发布说明

本目录只说明公开的 Fantasy Roll 手动求解器部署。公开版可在 `Main（当前 · 五格）` 与
`小组赛（历史 · 三格）` 之间切换，并在 Main 使用默认 G 或用户主动选择的 G-Lite。OCR、屏幕
捕获、Dota 进程检查和本地数据同步均不在这条云端路径中；手动版和本地 OCR 版的求解事实来源
统一放在 `deploy/runtime/`。

Main Roll 用完后，手动版只要求最终 15 格，并并列显示 V1、B1 与 10% Series 限额混合三套
终局 Forecast。页面不平均、不投票，也不把任何一套静默设为真值。

## Community Cloud 参数

在 [Streamlit Community Cloud](https://share.streamlit.io/) 新建应用时使用：

| 参数 | 值 |
| --- | --- |
| Repository | `BCSZSZ/ti-2026-predictor` |
| Branch | 包含本发布内容的分支；合并后使用 `main` |
| Main file path | `streamlit_app.py` |
| Python | `3.12` |
| Secrets | 不需要 |

Streamlit 当前会优先识别仓库根目录的 `uv.lock` 并使用 uv 安装依赖。本仓库不再额外提供
`requirements.txt`，避免出现两个依赖事实来源。官方说明见
[App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)和
[Deploy your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)。

## 冻结求解上下文

公开入口只读取：

- `../runtime/current.json`；
- `../runtime/main-current.json`；
- `../runtime/main-forecast-current.json`；
- `../runtime/releases/` 中由该清单指向的 `.json.zst` 与 `.sha256`；
- 仓库中的版本化 `src/` 与 `config/`。

当前 Group/Main 文件身份分别以两个 current 指针为准。Group 发布包包含：

- 响应情景 256 个；
- 可用队伍×位置池 47 个（核心 16、中单 15、辅助 16）；
- 客户端 Roll 规则片段、Series 数值块、Title 边际证据和完整来源哈希。

Main 当前发布包为 `ready / actual`，包含正式 8 个 Main entrant、小组赛与突围赛后重建的
Fantasy Series pool、五槽/30 Roll 规则、256 个完整双败 Scenario、动态 Title 证据，以及冻结的 G/G-Lite 策略
目录。云端只允许手动录入 15 格、三个当前选项和剩余 Roll；G-Lite 仅按发布包内的固定 seed 与
主出率模型做受限下一轮抽样。当前截止为 `2026-08-16T15:31:30Z`。

终局三模型证据不提交进 Git：`main-forecast-current.json` 锁定 GitHub Release URL、字节数、ZIP
SHA-256 与内部 manifest SHA-256。第一次 0 Roll 求解会下载约 `266.1 MiB` 并缓存；普通页面不
下载。每套模型使用 `16,384 × 16 × 3 = 786,432` 个加权情景。

它不提供原始 API 响应、处理后数据集、运行产物、截图、OCR 模型或写入接口。加载时会依次验证
当前指针、文件清单、发布内容、源码树、配置、P3、Title、规则快照、Pool 和 Scenario 身份；任一
不一致即停止计算。Group/Main 滚动求解包缺失时不会联网重建；终局大包只有在指针给出固定
HTTPS URL 且所有内容哈希通过时才允许下载，不会访问原始 API 或本机数据仓。

## 重新生成

只有在新的 P3、Title、客户端规则和发布政策已经各自通过审计后，才重新生成：

```powershell
uv sync --locked --extra dev
uv run ti fantasy solver-release --as-of 2026-08-10T13:45:12Z
uv run ti fantasy main-solver-release --mode actual --as-of 2026-08-16T15:31:30Z --hero-source data/raw/rules-title/20260810T134512Z-7d89d1a71895/scripts/npc/npc_heroes.txt
uv run ti fantasy main-publication-evidence --as-of 2026-08-16T15:31:30Z --hero-source data/raw/rules-title/20260810T134512Z-7d89d1a71895/scripts/npc/npc_heroes.txt
uv run pytest tests/test_solver_release.py tests/test_fantasy_main_solver_release.py tests/test_web.py
```

生成命令必须接收显式 UTC `as_of`，不会从系统当前时间猜测数据截止。若 `src/` 或 `config/` 在
生成后变化，云端加载器会因源码树或配置哈希漂移而 fail closed，必须重新审计并发布一个新的
内容寻址文件。旧文件保持不可变；只更新 `current.json` 指向已审核的新文件。

## 本地烟雾测试

```powershell
uv sync --locked
uv run streamlit run streamlit_app.py
```

验收要点：

1. 页面标题为 `Fantasy Roll 手动求解器`；
2. 页面没有识别、上传截图或实时监视按钮；
3. Main Tab 显示 15 格与 30 次 Roll，小组赛 Tab 显示九格与 40 次 Roll；
4. Main 显示 `ready / actual`，三个位置各只提供正式 8 队；
5. Main 策略选择只包含默认 G 和可选 G-Lite，两者都能从手填状态得到建议；
6. Main 剩余次数设为 0 后，三个选项消失并显示 V1 / B1 / 10% 混合三套独立结果；
7. 本地 `local_ocr_app.py` 额外显示 Main/Group 单次识别按钮，但使用相同求解包；
8. 任何快照或源码哈希错误都会显示阻断信息，而不是退回未经验证的默认值。
