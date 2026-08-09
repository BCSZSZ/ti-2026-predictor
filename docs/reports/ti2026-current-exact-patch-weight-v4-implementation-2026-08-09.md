# 7.41e 1.5 倍权重与单表对阵矩阵：实施和验收记录

## 阶段目标

本阶段只做两项发布变更：把共享的 7.41e 精确版本倍率由 2.0 调整为 1.5，并把小组赛两张半宽
对阵表合成一张完整 16×16 表。验收标准是权重只能有一个中央实现，Group、Fantasy Stat 和 Title
全部按新政策重算，正式产物通过审计，发布包不再把 2 倍写成当前政策，矩阵完整且双向概率守恒。

## 最小修改范围

- `config/models/team-strength-v2.json`：倍率改为 1.5，策略升级为
  `team-strength-adr-0006-v4`；
- `src/ti_predictor/models/evidence.py`：审计公式身份升级为
  `major_exact_tier_time_v4`；
- ADR-0006 记录新取舍，ADR-0005 保留为被取代的历史决策；
- 正式重跑 Group、TI 2025 backtest、Fantasy Stat Top 3 和 Title；
- 同步当前报告、玩家发布包、权重说明和方法报告；
- 增加单张 16×16 矩阵的结构与概率守恒测试。

没有改变 Elo/Glicko、赛事目录等级、60 天半衰期、7.40 的 0.15 权重、Fantasy 计分公式、
Trait/Quality 算术或 Swiss 容量近似。约 70 分钟的旧 Roll standalone/cross-audit 没有冒充在新
权重下重跑；本轮只更新共享证据层及由它直接生成的 Stat、队伍 Top 3 和 Title 数值。

## 为什么从 2.0 改为 1.5

当前证据中有 141 局 7.41e。Team Yandex 在识别出的 7.41e 窗口没有合格比赛，而 Team Liquid
为 11–3；旧 2 倍政策会让这段不均衡的短赛程对点估计产生过强影响。1.5 倍仍然明确优先当前版本，
但同条件下一局 7.41e 只比其他 7.41 字母版本多 50% 影响。它是版本化的建模取舍，不是由 TI 2025
回测证明出的理论最优常数。

## 正式运行与审计

| 内容 | 正式运行 | 结果 |
| --- | --- | --- |
| TI 2025 时间留出回测 | `backtest-9aa63d3ba42671a9` | `publishable: true`；56.25% accuracy，log loss 0.682552，Brier 0.244712 |
| 小组赛 Forecast | `group-d90f0b006fe33908` | `publishable: true`；3,943 局正权重连通证据 |
| Fantasy Stat Top 3 | `fantasy-2b1ae75dcde6a1ab` | `publishable: true`；42 个组合完成 400 次 Series 重采样 |
| Fantasy Title | `fantasy-80de5a937166a04a` | `publishable: true`；默认仍为 Cerulean + the Clutch |

Group 的 141 局 7.41e 贡献 149.736 有效权重，总有效权重 741.568；Fantasy 的对应数值为
149.087 和 870.279。两个范围的 `as_of` 不同，因此有效权重略有差异。

## 发布结果变化

- 综合实力点估计改为 Yandex 第一、Liquid 第二；两队中立单局约 53–47，应视为同一第一集团；
- 新版完整顺序为 Yandex、Liquid、Falcons、VISION、BoomBoys、Resilience、Spirit、Aurora、
  OG、Vici、HULIGANI、LGD、Nigma、Xtreme、GamerLegion、Iron Wing；
- 对局关系改为一张 16×16 表，不再要求读者在两张表之间按数字对齐；
- 当前 16 槽方案为 Aurora 4–0，Resilience/Spirit 4–1，Liquid/Boom/Falcons/Yandex/VISION
  淘汰轮胜者，Vici/LGD/OG/Nigma/HULIGANI 淘汰轮败者，Xtreme/GamerLegion 1–4，Iron Wing 0–4；
- Fantasy Stat Top 3 全表已重算：23/42 个点估计第一的 P1 高于 50%，其余 19 个更易随历史
  Series 重采样换人；核心位红色 `deaths` 与辅助位绿色 `first_blood` 的分档随新证据变化；
- Title 默认组合不变；the Clutch 为 34/48 个队伍×位置池的 Suffix 第一。

## 测试与项目级审查

- 全项目测试：`uv run pytest -q`，通过；仅 1 项既有跳过；
- 静态检查：`uv run ruff check .`，通过；
- 格式检查：`uv run ruff format --check src tests`，79 个文件通过；
- 规则校验：`uv run ti rules validate`，只有已登记的一血和 percentile 客户端冲突 warning；
- 四个正式运行逐一 `ti audit`，均为 `publishable: true`；
- 新矩阵测试确认只有一张对阵表、16 个表头、16 个队伍行、对角线为空且任意双向概率相加为 100%；
- 当前发布包已扫描，不再把 2 倍或 ADR-0005 写成当前政策；旧 v3 实施报告和 ADR-0005 仅作为
  可复现历史保留。

审查未发现对其他功能的破坏。既有 warning 仍完整披露：概率未校准、Swiss 逐轮规则未冻结、
Title 两个一血条件冲突、Fantasy 跨定位相关性未建模，以及完整 Roll 策略仍为 `draft`。
