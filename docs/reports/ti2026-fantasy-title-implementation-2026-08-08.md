# TI 2026 Fantasy Title 实装与验收记录

状态：**阶段完成；可发布玩家建议，保留完整 P3 联合估值 warning**

- 分支：`codex/fantasy-title-analysis`
- 明确截止：`2026-08-08T13:12:00Z`
- 客户端：`6891:10893022`
- 最终证据运行：`fantasy-2544fe02d1940200`
- 证据内容 SHA-256：`3466d4ed11ae039309297a1bb9fda01edda8cced5f01da1c88af6b8696bbfea5`

## 1. 阶段目标、最小范围与验收标准

阶段目标是补上玩家手册遗漏的 Title 选择，并纠正“Prefix 没有官方英雄分类、因此完全无法分析”
这一过时状态。最小范围冻结为：

1. 解析当前客户端 `scripts/npc/npc_heroes.txt` 的稳定英雄 ID 与八类 Title 标签；
2. 从既有不可变 OpenDota 原始详情读取逐局英雄、胜负、时长、一血和魔方死亡；
3. 复用 P3 的完整 BO2/BO3 Series 池和证据权重，单独生成逐图纸面 Title 排名；
4. 不修改 Stat、Roll、队伍强度、原始数据或 P3 终局估值；
5. 把结果加入玩家手册、易懂总结、方法说明和发布包。

验收标准是 128 名英雄与八类标签齐全、所有入选 player-game 稳定 ID 可回查、八个 Suffix
逐项标记可估计/冲突/不可用、同输入可复现、全量测试与静态检查通过。

## 2. 实施内容

### 正式逻辑

- `src/ti_predictor/fantasy/title.py`
  - 处理客户端重复 `DOTAHeroes` 分块，不会覆盖早期英雄；
  - 支持 `Cape / Mask / Masked` 等实际标签；
  - 规范化原始比赛 Title 特征；
  - 对 48 个队伍×位置池做等池汇总，再按完整 Series evidence weight 加权。
- `src/ti_predictor/fantasy/title_reporting.py`
  - 强制显式 `as_of`；
  - 只使用该时点前可用且 SHA-256 匹配的原始响应；
  - 把客户端英雄源不可变归档到
    `data/raw/rules-title/20260808T131200Z-7d89d1a71895/scripts/npc/npc_heroes.txt`；
  - 生成不可变 JSON、玩家 Markdown 和 `run.json`。
- `ti fantasy title-evidence`
  - 新增独立、可复算的 Title 证据入口。

### 已验证替换后的清理

旧的通用 `FantasyRecommender` Suffix 简化估算器、Series 最后局标记器及其专用测试已经删除。
它们属于被新证据入口替代的死路径。通用 Fantasy 入口仍保留战旗推荐，但 Title 字段只指向
`ti fantasy title-evidence`，避免两个不同算法同时自称正式答案。

以下内容有意保留：

- P3 的 `Coach/Title unavailable_excluded`：这是完整未来情景尚未联合估值的有效生产门禁；
- 已标成历史版本的旧报告：属于审计证据，不作为当前发布入口；
- Prefix/Suffix 的乘法顺序政策：尚无 Valve 算术验证，不能静默升级为 exact。

## 3. 数据与结果

| 检查项 | 结果 |
| --- | ---: |
| 客户端英雄映射 | 128 |
| Prefix 分类 | 8 |
| 入选原始比赛详情 | 1,512 |
| 一血事件可观测覆盖 | 97.62% |
| 魔方死亡解析覆盖 | 100% |
| 入选 player-game 身份回查 | 9,076 / 9,076 |
| 正权重职业 Games | 4,405 |
| 结构完整 BO2/BO3 Series | 1,421 |
| 队伍×位置完整 Series blocks | 2,373 |
| 候选池 | 48 |

中性默认结论：

- Prefix：**Cerulean**，触发率 19.4%，纸面平均 `+2.14%`，15/48 池第一；
- Suffix：**the Clutch**，BO3 折算触发率 17.7%，纸面平均 `+2.83%`，31/48 池第一；
- 截图组合 `Otherworldly + Flayed Twins Acolyte` 纸面约 `+2.78%`；
- 默认组合两列相加约 `+4.97%`，量级差约 2.18 个百分点，不作为最终结算保证。

## 4. 测试与工程级审查

- 针对性 Title/通用 Fantasy 测试：通过；
- 全量离线测试：`158 passed, 1 skipped`；
- 全项目 Ruff：通过；
- `git diff --check`：通过；
- 同一输入重复生成：run ID 和 evidence SHA-256 不变；
- 玩家手册、易懂总结、方法摘要、方法速查与 Title 报告的发布副本已核对；
- 发布包 14 份 Markdown 的本地链接检查通过；同时修复一个本轮前已存在的 v2 证据包相对链接；
- 未修改 `config/`、`data/processed/`、既有 P3/Stat/Roll 模型或大型缓存。

## 5. 仍然明确保留的问题

1. **Prefix 依赖最终三面战旗。** Cerulean 是中性默认，不是任何队伍组合都固定最优。
2. **纸面值不是 Period 最终增幅。** 尚未代入实际 Stat、Quality、Trait、最高两局和最佳 Series。
3. **两个一血 Title 有客户端冲突。** 可见条件下的历史数只展示，不进入推荐排名。
4. **the Cruel 不可可靠观测。** 缺少受治理的“选手在自己泉水内死亡”事件位置证据。
5. **完整 P3 Coach 仍未闭合。** 后续若要升级，需要把实际三面战旗、未来 BO3 和 Title 条件放进
   同一情景估值，而不是继续扩大逐图平均表。
