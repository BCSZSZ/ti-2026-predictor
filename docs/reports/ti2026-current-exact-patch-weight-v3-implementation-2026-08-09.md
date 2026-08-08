# 7.41e 双倍证据权重：实施、验收与影响报告

状态：**阶段完成；中央逻辑已统一，正式产物审计可发布，旧 Roll 操作规则保持原验证状态**

## 阶段目标、最小范围与验收标准

阶段目标是只给当前精确版本 7.41e 额外 2 倍证据权重，并让所有使用比赛证据权重的流程自动
继承；7.41 其他字母版本、7.40、赛事目录等级和时间衰减全部保持原值。

最小修改范围：

1. 在唯一的队伍强度政策中增加带 UTC 生效时间的精确版本倍率；
2. 在中央证据集构建器中把倍率乘进原公式；
3. 把权重政策哈希纳入 Group Forecast、Fantasy Stat、Title、Playbook 和 Solver 的运行身份；
4. 更新当前发布表、方法文档和审计说明；不改 Fantasy 基础计分、Series 规则、Elo/Glicko 参数、
   Roll 规则或客户端规则快照。

验收标准：

- 7.41e 在生效边界后为 2 倍，同大版本其他小版本为 1 倍，7.40 仍为 0.15；
- 显式小版本标签优先，标签与时间边界冲突时报警且不强行倍权；
- 历史回测不被 2026 的精确版本策略倒灌；
- Group、Stat、Title 均以同一源码提交重跑，`ti audit` 返回 `publishable: true`；
- 全项目测试、格式和静态检查通过；旧产物不冒充当前结果。

## 实装

统一公式为：

`weight = major_patch_weight × exact_patch_multiplier × tier_weight × 2^(-age_days/60)`

当前政策：

| 因子 | 当前值 |
| --- | ---: |
| 7.41 大版本 | 1.00 |
| 7.41e 精确版本倍率 | ×2.00 |
| 其他 7.41 字母版本倍率 | ×1.00 |
| 7.40 大版本 | 0.15 |
| 更早版本 | 0.00 |
| `premium` / `professional` | 1.00 / 0.75 |
| 时间半衰期 | 60 天 |

处理后比赛表目前只保存 7.41 大版本，因此精确版本由冻结的 UTC 边界
`2026-07-30T23:58:15Z` 和 Game `start_time` 识别。代码也支持显式 `7.41e` 标签：明确标签优先；
若标签与时间边界矛盾，保留普通大版本权重并写入 `model-evidence-exact-patch-conflict`，不静默猜测。

政策 ID 为 `team-strength-adr-0005-v3`，权重公式审计版本为 `major_exact_tier_time_v3`。正式逻辑
仍只存在于 `src/`；决策记录见 ADR-0005。

## Title 内部字段结论

本机可见的不是服务器结算函数体，而是客户端 `scripts/fantasy_crafting.vdata` 的数据驱动配置：

- Flayed 使用 `Any` 组合，登记 `first_blood_before_the_horn` 和
  `first_blood_before_1_minute` 两个 Game 级统计项；
- Patient 登记 `first_blood_after_6_minutes`；
- 配置还包含阈值、比较方向和加成，但没有说明服务器怎样填充这些统计项。

比赛准备阶段按负数倒计时，号角响起后从 0:00 正计时。因此“号角前”是时间 `< 0`，而
0:00–0:59 是号角后第一分钟。即使变量名叫 `before_1_minute`，也不能在看不到服务器实现时断言
它必然包含这段；`after_6_minutes` 也可能是沿用旧名，不能只凭名字推翻界面的 10 分钟文字。

结论是：优先使用真实可见代码行为，但当前只有配置和符号名，没有结算函数体。两项继续保留
`conflicted_excluded`，不进入发布级默认推荐。

## 正式重跑与审计

四个产物均由源码提交 `a959deac6834550d0cd41343db2cddbf34ae060e` 生成：

| 产物 | run ID | `as_of` | 审计 |
| --- | --- | --- | --- |
| TI 2025 时间回测 | `backtest-cae85ecc9c4e2f9b` | `2026-08-08T04:11:08Z` | `publishable: true` |
| Group Forecast，100,000 次 | `group-b9c2bd18c201d91a` | `2026-08-08T04:11:08Z` | `publishable: true` |
| Fantasy Stat / Top 3 | `fantasy-26bccc9da5be9e7d` | `2026-08-08T13:12:00Z` | `publishable: true` |
| Fantasy Title | `fantasy-4701c25efe319121` | `2026-08-08T13:12:00Z` | `publishable: true` |

历史回测的正式模型为：命中率 56.25%、log loss 0.68255、Brier 0.24471；历史目标版本为 7.39，
所以 7.41e 倍率不生效，结果与旧政策一致。这验证了时间边界与实现隔离，但不是 2 倍参数的效果
回测。

当前证据审计：

| 用途 | 正权重 Game | 7.41e Game | 7.41e 有效权重 | 总有效权重 |
| --- | ---: | ---: | ---: | ---: |
| Group 目标连通图 | 3,943 | 141 | 199.648 | 791.480 |
| Fantasy 全局玩家历史 | 4,405 | 141 | 198.783 | 919.975 |

## 提升与退步

### 小组赛 Forecast

- Liquid 由第 5 升到点估计第 1，强度约 +66.8；其 7.41e 合格记录为 11–3；
- OG 由第 12 升到第 9；
- LGD 由第 9 降到第 13，强度约 -40.2；其 7.41e 记录为 0–4；
- Yandex、VISION、Resilience、Spirit、Aurora、Xtreme、Iron Wing 在 7.41e 窗口没有直接新局，
  但仍会因对手网络相对变化而处于新的横向排序。

提升在于模型更快响应当前版本；退步在于 141 局会影响更大，短期赛程和样本偶然性也会被放大。
Liquid–Yandex 只有 51–49，所以新版发布结论改为“第一集团”，不把点估计第一写成单独领先。

### Fantasy Stat

与旧权重的正式 Top 3 表相比：42 行中 26 行的前三组成或顺序改变，10 行点估计第一改变；只有
2 行基础建议跨档：核心位红色 `deaths` 从“可以改善”变为“可以保留”，辅助位绿色
`first_blood` 从“可以改善”变为“优先改善”。17/42 行仍处于分档边界。

这说明扩大当前版本权重确实更新了查表内容，但没有把不确定性消除。新版 Top 3 表不自动证明旧
Roll 操作规则在新权重下仍通过全套消融。

### Fantasy Title

默认组合仍是 **Cerulean + the Clutch**。Cerulean 的综合触发率为 19.3%、纸面平均加成 2.12%，
Clutch 为 18.1% 和 2.90%；触发率略有变化，但推荐方向稳定。Flayed 和 Patient 仍因规则冲突排除。

## 项目级审查与收口

- 中央证据层覆盖队伍实力、Fantasy P3、Title、P4 Playbook、P5 Solver 与交互顾问的共同入口，
  未发现旁路权重公式；
- Fantasy 基础分、Quality、Trait、Series 结构和客户端冻结规则未改；
- 旧 `team-strength-v2.json` 文件名为兼容入口保留，但内部 schema/policy 已升级，删除文件会破坏
  现有清单，因此没有为“清理”而改名；
- 旧 8 月 8 日报告作为历史证据保留，新发布包只指向 8 月 9 日版本；
- 大型缓存和 run artifacts 继续由 Git 忽略，不进入提交。

本阶段不清理旧 Roll v2 规则，因为替代规则尚未在新权重下完成 standalone 与 held-out
cross-audit；提前删除会丢失仍有效的验证证据。后续若要升级整套 Roll 手册，应单独执行 v3 验证，
预计约 70 分钟，不需要重跑历史上约 15 小时的 full-session P5。

最终工程验收：`167 passed, 1 skipped`；Ruff lint 通过，78 个文件格式检查通过；规则校验只有三项
已治理的客户端冲突 warning，没有新增 blocking issue。8 月 9 日发布包内全部本地 Markdown 链接
已解析验证。
