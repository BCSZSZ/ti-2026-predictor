# TI 2026 Main 条件化 Fantasy 研究真值计算报告

- 计算日期：2026-08-17
- 数据截止：`2026-08-16T15:31:30Z`
- 状态：`ready / research-only`
- 正式证据：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b`
- 证据 manifest SHA-256：`e43bfaaad33cc4e3be7428d45548e66a83baabe8a7d0d23148ba74a9c5a936dd`
- 个人状态 SHA-256：`337c126fac348ca4d02fabc720b4cf24984e52691ae9e6749afcd20e609c789b`
- 个人解 SHA-256：`fc141e3327fc90f9324cc6c535e810f10b32eb881c5c98f1927f8b1127aed3f0`
- 发布边界：没有修改 Web、求解器 release、部署包或任何 runtime pointer

## 结论

方案二的离线研究参考真值已经算完。它不是“未来比赛的真实结果”，而是当前冻结 Team-strength
模型、历史 Fantasy 数据和客户端规则之下，用来校验快速近似方案的高精度条件化基准。

对用户此前由当前 OCR 完整确认的 Main 五旗画面，按**最大数学期望**选择：

| 位置 | 建议队伍 | 模型均值 | 第二名 | 领先 |
| --- | --- | ---: | --- | ---: |
| Core | **TEAM VISION** | 27,481.901 | Team Falcons，25,468.183 | +7.907% |
| Mid | **Nigma Galaxy** | 21,815.839 | Iron Wing，19,376.447 | +12.589% |
| Support | **BoomBoys** | 13,762.199 | Team Liquid，13,519.458 | +1.795% |

三面合计模型均值为 **63,059.939**，联合 CVaR10 为 **48,291.015**。三个独立内层种子都选择
同一组队伍。Support 的优势明显小于另外两个位置，所以它是最需要在数据或规则变化后复查的一项，
但本次并不是由单个随机种子翻出来的偶然排序。

当前正式 Web 的旧 Main terminal 对同一个画面选择
`TEAM VISION / Nigma Galaxy / Team Liquid`。方案二只改变 Support：从 Team Liquid 改为
BoomBoys。两个模型的绝对分值来自不同 Scenario 分布，不能直接拿绝对值互相做百分比比较；可以比较的
是同一画面下的队伍排序。

## 现行 BO5 规则判定

客户端同一快照里存在新旧文案冲突：

- 旧通用 Fantasy 文案 `DOTA_FantasyHelpDetailsSub3Text3` 写 BO5 取最高三局；
- 当前活动通用 tooltip `DOTA_FantasyCraft_BestSeriesTooltip` 写每个系列取最高两局；
- **TI 2026 专用** `DOTA_FantasyCraftHelp_ScoringDetails2026` 明确写每个定位最终积分来自
  一个系列赛中积分最高的两场比赛，随后再在该结算期取最佳系列。

证据位于客户端不可变快照：

- `data/raw/rules/20260813T132319Z-9728c506baf6/resource/localization/dota_english.txt`
  第 44,793、52,445 行；
- 同快照 `dota_schinese.txt` 第 44,584、52,227 行。

按仓库的规则来源优先级，年份专用的 2026 Fantasy Craft 文案优先于旧版通用 Fantasy Card 文案。
本次因此对 BO3 和总决赛 BO5 都执行：

```text
series_score = 该系列所有实际比赛中得分最高的两局之和
period_score = 该队本阶段所有 series_score 的最大值
```

所以 BO5 的价值来自 3–5 次争取高分局的机会，但最后仍只取最高两局。

## 冻结输入

### 数据和模型身份

| 项目 | 冻结值 |
| --- | --- |
| Main actual snapshot | `4b189f4726d7e996a70a174feb6be04c4ccaf6148dd006f46fffe523c7cc8bcb` |
| Team-strength model | `bf7bd372f1ebc57dee0e238bca21d776411bc0e25f4a28c1f72aafc9dfed76c2` |
| 客户端规则 | `401e8d89222320d42eac3dba3b97d2f9b72b97134c4e707a558c97f7ebed2f60` |
| 研究配置 | `02e3322f6677e361ade2a2e9e54424ec218337db8dd8efd6968cb9a98c5f4581` |
| 研究源码树 | `a488fac94d1a2645ed3dad73681c1f81a94f7458a15f514fdba07c0042bb066d` |
| Git source version | `a5c5acdf7b0dc86ac706173c40400e16817d6736-dirty-a488fac94d1a` |

Fantasy evidence 筛选器从 45,056 场比赛目录中得到 4,555 场正权重比赛；当前 TI 小组赛与突围赛
109 场均进入 evidence，stage multiplier 为 **1.5**。条件化模拟进一步要求同一局中当前阵容五名
选手的 18 项 Stat 都具有要求的 provenance，最终形成 358 个完整 Series、863 个联合五人 Game
模板。缺失值没有按零填充。

### 完整联合 Series 模板

| 队伍 | BO2 | BO3 | BO5 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| Iron Wing | 22 | 28 | 2 | 52 |
| Team Liquid | 14 | 45 | 4 | 63 |
| Nigma Galaxy | 6 | 10 | 0 | 16 |
| TEAM VISION | 5 | 19 | 2 | 26 |
| BoomBoys | 21 | 59 | 4 | 84 |
| Team Falcons | 22 | 36 | 1 | 59 |
| Team Yandex | 5 | 23 | 2 | 30 |
| Team Spirit | 5 | 23 | 0 | 28 |
| **合计** | **100** | **243** | **15** | **358** |

Nigma Galaxy 和 Team Spirit 没有满足完整五人条件的历史 BO5，因此 BO5 需要预先冻结的层级回退；
本次没有把缺少 BO5 的队伍排除，也没有把 BO3 冒充为观测到的 BO5。

## 方案二计算契约

1. 枚举官方八队双败树全部 `2^14 = 16,384` 条合法路径，不再抽 256 条 bracket 路径。
2. 冻结模型给出的单局胜率为 `p`；BO3/BO5 Series 胜率由 IID binomial 转换：
   `P(BO3)=p²(3-2p)`，`P(BO5)=p³(10-15p+6p²)`。
3. 每条路径保留精确模型概率；没有把 16,384 条路径等权处理。
4. 每个外层路径生成 16 个条件化内层样本，使用 3 个独立 seed：
   `2026081701`、`2026081702`、`2026081703`。
5. 总面板为 **786,432** 个加权未来情景、22,020,096 次 Team-Series 侧抽样、
   57,408,762 次未来 Game 模板抽样。
6. 每个未来 Series 先抽一条共享的 2–0/2–1 或 3–0/3–1/3–2 比分序列；双方局数完全一致，
   每局胜负相反。
7. 一支队伍同一局的五名选手来自同一个历史 Game 模板，保留 Core/Mid/Support 的队内相关性；
   对阵双方的模板在给定共同局结果后独立抽样。
8. Series 来源池按 Team、BO 格式、Series 胜负、对手强度带 `<40% / 40%–60% / >60%`
   条件化；稀疏单元使用固定层级回退。
9. 未来每局的 Game 模板始终与该队当局胜负一致；正式构建同时验证双方 Series 局数一致和每局
   结果相反，否则构建失败。
10. 每面旗帜的队伍在所有未来揭晓前固定选择，不允许在模拟里先看到谁晋级再换队。

按转换后的 BO3/BO5 概率，八队预期 Series 数为：

| 队伍 | 预期 Series |
| --- | ---: |
| Iron Wing | 3.5611 |
| Team Liquid | 4.0219 |
| Nigma Galaxy | 3.7186 |
| TEAM VISION | 4.3173 |
| BoomBoys | 2.8775 |
| Team Falcons | 3.2400 |
| Team Yandex | 3.0388 |
| Team Spirit | 3.2248 |

这解释了为什么不能只把每队“单系列平均 Fantasy 分”乘一个共同常数：不同队伍拥有不同数量的
刷新最佳 Series 的机会，而且收益是取最大值后的边际递减，不是 Series 分数简单相加。

## 条件池回退审计

### Series 来源选择

| 层级 | 条件 | 占比 |
| ---: | --- | ---: |
| 0 | Team + 格式 + Series 结果 + 对手带 | 68.6105% |
| 1 | Team + 格式 + Series 结果 | 19.3359% |
| 2 | Team + Series 结果 + 对手带 | 5.1060% |
| 3 | Team + Series 结果 | 0.6975% |
| 4 | Team + 格式 + 对手带 | 5.8036% |
| 5 | Team + 格式 | 0.0000% |
| 6 | Team + 对手带 | 0.4464% |
| 7 | Team 全池 | 0.0000% |

Series 来源有 **93.75%** 在层级 0–3 就保留了要求的 Series 胜负。层级 4/6 只用于选择相似
来源 Series；随后每个未来 Game 仍强制从相同胜负结果的 Game 模板中抽取，因此没有生成与 bracket
胜负矛盾的未来比赛。

### Game 模板选择

| 层级 | 条件 | 占比 |
| ---: | --- | ---: |
| 0 | 所选来源 Series 内、相同单局结果 | 88.9310% |
| 1 | 同 Team + 相同单局结果 + 对手带 | 10.8496% |
| 2 | 同 Team + 相同单局结果 | 0.2194% |

没有使用“结果不一致”的最终回退。正式构建对 57,408,762 个引用逐项验证了模板的单局胜负。

## 个人画面完整排名

个人输入为
`config/research/states/ti2026-main-reference-screen-20260814.json`。它来自用户提供画面，并已由
当前 OCR 对 15 格逐字段确认，无 OCR warning。若用户此后已经 Roll 过任意一格，本节必须用新画面
重算，不能把旧画面结果沿用。

### Core

| 排名 | 队伍 | Mean | CVaR10 |
| ---: | --- | ---: | ---: |
| 1 | **TEAM VISION** | 27,481.901 | 22,240.733 |
| 2 | Team Falcons | 25,468.183 | 18,526.831 |
| 3 | Iron Wing | 25,246.474 | 19,761.657 |
| 4 | Team Spirit | 24,641.461 | 20,879.238 |
| 5 | Nigma Galaxy | 23,662.207 | 18,211.632 |
| 6 | Team Liquid | 22,730.216 | 18,590.187 |
| 7 | BoomBoys | 22,580.809 | 17,471.741 |
| 8 | Team Yandex | 20,747.293 | 16,387.289 |

### Mid

| 排名 | 队伍 | Mean | CVaR10 |
| ---: | --- | ---: | ---: |
| 1 | **Nigma Galaxy** | 21,815.839 | 10,756.686 |
| 2 | Iron Wing | 19,376.447 | 11,517.494 |
| 3 | Team Liquid | 18,647.745 | 11,005.348 |
| 4 | Team Falcons | 17,581.642 | 11,915.754 |
| 5 | TEAM VISION | 17,489.107 | 10,588.751 |
| 6 | BoomBoys | 16,944.374 | 9,980.393 |
| 7 | Team Spirit | 16,040.637 | 11,336.646 |
| 8 | Team Yandex | 13,712.869 | 8,495.419 |

### Support

| 排名 | 队伍 | Mean | CVaR10 |
| ---: | --- | ---: | ---: |
| 1 | **BoomBoys** | 13,762.199 | 7,392.887 |
| 2 | Team Liquid | 13,519.458 | 7,921.213 |
| 3 | TEAM VISION | 12,933.741 | 7,654.747 |
| 4 | Iron Wing | 12,811.978 | 8,085.560 |
| 5 | Team Falcons | 12,432.046 | 8,523.404 |
| 6 | Nigma Galaxy | 12,132.853 | 7,774.234 |
| 7 | Team Spirit | 11,263.837 | 8,631.460 |
| 8 | Team Yandex | 10,553.169 | 7,070.571 |

本次配置的 `mean_retention_epsilon=0`，所以结论严格选择 Mean 第一。若目标改成优先保底而不是最大
期望，Support 会体现明显权衡：BoomBoys 的均值第一，但 Team Liquid、Team Falcons、Team Spirit
的各自 CVaR10 更高。这不是本次用户指定的目标，因此没有用 CVaR 覆盖 Mean 第一。

## Title 的独立结果

Title 没有进入本次方案二的逐局联合真值。原因是现有 Title evidence 只有边际触发率，没有冻结的
Prefix/Suffix 联合逐局触发分布。为了不把纸面估算冒充逐局真值，本次 Team 选择完全不含 Title。

在选定 `TEAM VISION / Nigma Galaxy / BoomBoys` 后，沿用当前独立 Title evidence 的纸面推荐为：

- Prefix：**Otherworldly**，估计触发率 32.336%，纸面平均加成 2.264%；
- Suffix：**the Clutch**，估计触发率 14.798%，纸面平均加成 2.368%；
- 简单相加的纸面组合加成为约 **4.631%**。

Cerulean 的纸面平均加成为 2.250%，只比 Otherworldly 低约 0.014 个百分点，属于几乎并列。Title
可以免费调整，但上述数字仍是边际近似，不能当成已进入 63,059.939 分的确定加成。

## 稳定性与限制

### 已验证

- 16,384 条外层路径完整、权重和为 1；
- 前 13 个节点为 BO3，总决赛为 BO5；
- 同一个未来 Series 的双方局数一致、逐局结果相反；
- 每个未来 Game 模板与要求的胜负一致；
- 严格执行 Series 内 Top 2、Period 内最佳 Series；
- 三个 seed 的 Core/Mid/Support 第一名完全一致；
- 同一配置重复构建命中同一内容寻址证据，没有覆盖原始数据；
- 研究模块没有进入 Web import path、solver release 或 runtime pointer。

### 仍然不是现实保证

- 单局胜率来自冻结的 Team-strength 模型，再用 IID binomial 转换为 BO3/BO5；没有单独校准一套
  BO3/BO5 模型；
- 历史 Fantasy 表现按 Team、结果、格式和对手带重采样，仍不能预测版本临场变化、英雄选择、
  选手状态和比赛时长的全部联合结构；
- 对阵双方共享赛果和长度，但双方五人表现模板在给定结果后独立；
- Nigma Galaxy、Team Spirit 等队的历史 BO5 数据稀疏，回退比例已公开，不能把这些抽样称为
  真实 BO5 观测；
- Title 被有意排除；
- 用户画面是 2026-08-14 确认状态，不代表任何后续 Roll 后的新画面。

因此这里的“研究真值”准确含义是：**相对于当前生产 256 路径代理更完整、更一致的离线参考模型**，
而不是比赛结束前可观测的客观真值。

## 性能与复现入口

在本机 i5-13600KF / 32 GB 环境：

- 正式证据构建约 36.06 秒；
- 单个五旗状态求解约 10.51 秒；
- 最终证据目录约 83.42 MiB。

它远短于此前 G/T/H 的数小时研究，因为这里没有为每个状态模拟 30 次 Roll 决策树；昂贵部分是
一次性生成并压缩静态未来比赛证据，个人旗帜只在其上做向量化重评分。

实现与配置：

- `src/ti_predictor/fantasy/main_conditional_truth.py`
- `config/research/fantasy-main-conditional-truth-v1.json`
- `tests/test_fantasy_main_conditional_truth.py`

离线证据：

- `artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/manifest.json`
- `artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/pool-audit.json`
- `artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/draws-*-audit.json`
- `artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/solutions/337c126fac34.json`

本次没有执行发布，也没有建议把完整 83 MiB 面板直接塞入 Web。是否把这一结论压缩为静态生产
terminal，应作为后续独立任务处理。
