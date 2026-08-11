# Streamlit 手动版发布说明

本目录只服务公开的 Group Roll 手动求解器。OCR、屏幕捕获、Dota 进程检查和本地数据同步均不在
这条发布路径中。

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

- `frozen/manual-advisor-v1.json.zst`；
- `frozen/manual-advisor-v1.json.zst.sha256`；
- 仓库中的版本化 `src/` 与 `config/`。

当前文件身份：

- 数据截止：`2026-08-10T13:45:12Z`
- 文件 SHA-256：`f1476863bb1de55bc6ecf7486637cb96029b8ed9a8dd8c4a4ab471a938ef1fd8`
- 发布内容 SHA-256：`cc48b4ba467e651991d77eb94fa0a627180eb6cd907e6f54c2aa0a8266ff29fe`
- 响应情景：256
- 可用队伍×位置池：47（核心 16、中单 15、辅助 16）

该文件是从已验证本地上下文生成的紧凑部署资产。它保留 Series 数值块、情景索引、客户端 Roll
规则片段、Title 边际证据和来源哈希，但不提供原始 API 响应、截图、OCR 模型或写入接口。加载时
会依次验证文件清单、发布内容、源码树、配置、P3、Title、规则快照、Pool 和 Scenario 身份；任一
不一致即停止计算。

## 重新生成

只有在新的 P3、Title、客户端规则和发布政策已经各自通过审计后，才重新生成：

```powershell
uv sync --locked --extra dev
uv run ti fantasy manual-release --as-of 2026-08-10T13:45:12Z
uv run pytest tests/test_manual_streamlit_release.py
```

生成命令必须接收显式 UTC `as_of`，不会从系统当前时间猜测数据截止。若 `src/` 或 `config/` 在
生成后变化，云端加载器会因源码树或配置哈希漂移而 fail closed，必须重新审计并生成快照。

## 本地烟雾测试

```powershell
uv sync --locked
uv run streamlit run streamlit_app.py
```

验收要点：

1. 页面标题为 `Group Roll 手动求解器`；
2. 页面没有识别、上传截图或实时监视按钮；
3. 三个角色合计显示九格，另有三个同屏 Roll 选项和剩余次数；
4. 默认表单可以计算出一步建议、队伍组合与 Title；
5. 任何快照或源码哈希错误都会显示阻断信息，而不是退回未经验证的默认值。
