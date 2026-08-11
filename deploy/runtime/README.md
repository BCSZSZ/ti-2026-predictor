# 冻结求解发布包

`current.json` 是两个玩家入口共同使用的唯一当前指针：

- `streamlit_app.py`：公开 Streamlit，仅手动输入；
- `local_ocr_app.py`：Windows 本地 OCR，也可手动输入。

指针指向 `releases/` 中不可变、内容寻址的压缩包。压缩包足以在固定 `as_of` 下复现当前屏幕的一步
建议，但不含原始响应、处理后表、维护者运行产物、截图或 OCR 模型。用户 clone 仓库后不需要
下载或生成 `data/raw`、`data/processed`、`data/cache` 或 `artifacts`。

正常用户不需要执行本目录的生成流程。维护者只有在 P3、Title、客户端规则与发布政策全部通过
审计后，才从本机证据仓生成新版本：

```powershell
uv sync --locked --extra dev
uv run ti fantasy solver-release --as-of 2026-08-10T13:45:12Z
uv run pytest tests/test_solver_release.py tests/test_web.py
```

生成命令写入新的 `releases/group-roll-<as_of>-<release-sha>.json.zst`，同时更新 `current.json`。
任何缺失或校验失败都必须 fail closed；消费者不得回退到数据同步、本机重建或网络下载。
