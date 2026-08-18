# 冻结求解发布包

运行时按阶段使用两个独立指针：

- `current.json`：已冻结的历史 Group 三槽求解包；
- `main-current.json`：当前 Main 五槽求解包；八队形成前为可计算的 `provisional/projected`，
  形成后为 `ready/actual`。
- `main-forecast-current.json`：0 Roll 终局的 V1 / B1 / 10% Series 限额混合证据包。

两个玩家入口共同使用这些指针：

- `streamlit_app.py`：公开 Streamlit，仅手动输入；
- `local_ocr_app.py`：Windows 本地 OCR，也可手动输入。

玩家统一运行 `uv run ti web`；服务会自动校验并选择这两个 current 指针。Windows 默认启用
本地 OCR，`--manual` 只启用手动录入。后续所有发布命令仅供维护者移动经审查的 current 指针，
不是玩家启动服务的前置步骤。

就绪指针指向 `releases/` 中不可变、内容寻址的压缩包。Main schema 3 包同时冻结默认 `G` 与
可选 `G-Lite` 策略目录；`G-Lite` 只允许使用包内冻结的主出率模型和 seed 做受限下一轮抽样。
压缩包足以在固定 `as_of` 下复现当前屏幕建议，但不含原始响应、处理后表、维护者运行产物、
截图或 OCR 模型。用户 clone 仓库后不需要
下载或生成 `data/raw`、`data/processed`、`data/cache` 或 `artifacts`。

终局三模型是独立的大型只读派生证据。只有 `remaining_rolls=0` 时，消费者才读取
`main-forecast-current.json`，从 GitHub Release 下载精确 SHA-256 对应的约 `266.1 MiB` ZIP，
校验后解压到被 Git 忽略的 `data/cache/main-forecast/`。普通 G/G-Lite 不触发下载；任何字节数、
ZIP 哈希、内部 manifest 或文件校验失败都会阻断终局输出。

当前 Main 指针已是 `ready / actual`：数据截止 `2026-08-16T15:31:30Z`，正式八队的三个位置
均为 8 个候选，并内嵌赛后重建的 Main Fantasy Series pool。此前 projected 16 队流程保留为
维护者历史说明，不是当前玩家运行时。

正常用户不需要执行本目录的生成流程。维护者只有在 P3、Title、客户端规则与发布政策全部通过
审计后，才从本机证据仓生成新版本：

```powershell
uv sync --locked --extra dev
uv run ti fantasy solver-release --as-of 2026-08-10T13:45:12Z
uv run pytest tests/test_solver_release.py tests/test_web.py
```

Group 命令写入新的 `releases/group-roll-<as_of>-<release-sha>.json.zst`，同时更新
`current.json`。它是自包含历史冻结包；后续 Main 源码变化不会让它失效。

正式八队形成前即可执行：

```powershell
uv run ti fantasy main-solver-release --mode projected --as-of <UTC截止时间>
uv run pytest tests/test_fantasy_main_solver_release.py tests/test_web.py
```

它发布 16 队候选、每情景 8 队晋级的 Main 内容寻址包，并把 `main-current.json` 标为
`provisional`；Main 识别、手填和计算均可使用。它复用冻结 Group 晋级分布作为显式 Forecast
输入，但始终使用 Main 五槽、30 Roll 和双败 bracket 结算逻辑，不会回退到 Group Fantasy 计分。

Group 结束后先运行 `ti data sync` 与 `ti data replay-fantasy` 更新原始响应和处理后 Fantasy 样本，
再把实际八个稳定 ID 按正式种子顺序写入 `main_event_seeds`，最后执行：

```powershell
uv run ti fantasy main-solver-release --mode actual --as-of <UTC截止时间> --hero-source <npc_heroes.txt>
```

该命令从刷新后的证据重建并内嵌 Main Series pools 与动态 Title 证据，将候选
列表缩为八队并把指针改为 `ready`。
缺少晚于 Group 冻结点的本届赛事 Fantasy Game、任一实际参赛队缺少本届赛事 Fantasy 行，或
样本池仍等于 Group 冻结池时都会失败。消费者仍不得自行同步、重建或访问网络。
