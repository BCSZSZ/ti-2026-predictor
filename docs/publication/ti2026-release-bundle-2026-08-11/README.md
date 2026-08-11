# TI 2026 玩家发布包（2026-08-11，16 队身份归一 + LGD 0.60 版）

这是按 Valve 当前 16 队身份、官方 Swiss 首轮和 LGD 正胜算 odds `×0.60` 主情景重新生成的
玩家发布版。数据、规则与阵容统一冻结在 `2026-08-10T13:45:12Z`；旧的 2026-08-09 发布包保持
不变。

状态：**可用于当前决策，但赛事 Forecast、16 槽建议和 Fantasy Stat 保留 `warning`；不是 Valve
官方赛果。**

## 先看结果

- 100,000 次主情景模拟后，推荐组合的**期望正确数为 5.1561 / 16**，即
  **最终期望正确比例 32.23%**；期望值 95% Monte Carlo 区间为 **5.1440–5.1682 个**，
  正确个数 P10 / 中位数 / P90 为 **3 / 5 / 8**。
- `32.23%` 是 16 个类别槽位的期望命中比例，不是单场胜负命中率；随机合法填写的先验期望为
  `3.75 / 16 = 23.44%`。
- 官方首轮 Team Falcons / LGD Gaming 的 BO3 Forecast 为 **75.65% / 24.35%**；TEAM VISION /
  Team Resilience 为 **68.08% / 31.92%**。
- LGD 在正式 0.60 主情景下的晋级率为 **17.35%**，0–4 类别概率为 **20.82%**，因此进入唯一
  0–4 推荐槽。
- Fantasy 当前有 **47 / 48** 个合格队伍×位置池；唯一不可用的是 LGD 中单。
- Title 的中性默认仍为 **Cerulean + the Clutch**，但应在三面战旗确定后复查。

## 赛事结果怎样算出来

完整的 Elo/Glicko 分量、BO3 选择、Swiss 约束、全部首轮概率和 16 项概率求和见
[赛事 Forecast 正文](reports/ti2026-group-forecast-publication-2026-08-10.md)。Falcons–LGD 可按以下
链条复算：

1. LGD 阵容冲击前概率为 `0.349120`，Falcons 为 `0.650880`。
2. LGD 原正胜算为 `0.349120 / 0.650880 = 0.536381`。
3. 应用 0.60 后为 `0.536381 × 0.60 = 0.321829`。
4. 换回概率得到 LGD `24.3472%`、Falcons `75.6528%`。
5. 五轮 Swiss 联合模拟后，优化器在固定 `1 / 2 / 5 / 5 / 2 / 1` 容量下选择 16 个答案。
6. 16 个所选边际概率合计 `5.15608`，所以
   `5.15608 / 16 = 32.2255% ≈ 32.23%`。

## 16 队身份的处理

本版把身份审计横向扩展到全部 16 支 TI 队伍，不按名称字符串模糊合并：

1. 博彩品牌相关展示别名为 BoomBoys/BetBoom、TEAM VISION/PARIVISION、HULIGANI/L1GA、
   Iron Wing/1win；BoomBoys 已使用同一 Valve 稳定 ID，无需 bridge。
2. Team Resilience、Xtreme Gaming 和 LGD Gaming 还存在赛事临时注册 ID。配置共
   **9 条 identity bridge**，在冻结比赛中映射 **203 场不同比赛**；原始 parquet 和 raw team ID
   均保留。
3. `10150413 Iron Wing` 只从 `2026-06-01T00:00:00Z` 起承认当前身份，排除此前 24 场 Tundra
   阶段比赛；`5017210 Team Resilience` 也有防止历史 ID 复用的 registration identity window。
4. `8291895 Tundra`、`9303484 HEROIC` 和无关同名 BoomBoys 明确不合并。五人阵容连续不能覆盖
   真实组织转会边界。
5. 身份扩展后 TEAM VISION、Iron Wing、HULIGANI 的综合强度分别为 `1754.5 / 1643.0 / 1487.0`，
   对应入模局数为 `184 / 30 / 110`。

完整证据、每条有效期和不得合并的反例见
[16 队展示别名与注册身份审计](research/ti2026-team-display-alias-audit-2026-08-11.md)；VISION 早期
专项诊断保留在
[VISION 身份审计](research/ti2026-yandex-liquid-vision-rating-audit-2026-08-11.md)。

## LGD 的处理

赛事 Forecast 与 Fantasy 对 LGD 分开处理：

1. 客户端事件名单中 TaiLung 已无效，Topson（`account_id=94054712`）是当前有效中单。阵容使用
   半开生效区间，Topson 不会被回填到更早比赛。
2. 赛事模型不把绝对 Elo/Glicko rating 直接乘 `0.60`；每场未来 BO3 只把 LGD 的正胜算 odds
   乘 `0.60`。这是负责人确认的风险情景，不是历史样本估出的客观效应量。
3. LGD 晋级率在 `1.00 / 0.90 / 0.75 / 0.60` 情景下分别为
   **35.28% / 31.31% / 24.05% / 17.35%**。0.60 下随机与对抗性选对手敏感性为
   **17.73% / 18.25%**，主结论保持。
4. Topson 虽有 14 局公开 7.41c/d 比赛，但正式 `premium/professional` 范围内合格完整 Series
   为 0。因此 LGD 中单保持 `unavailable/null` 并从 Fantasy 中单候选排除；LGD 核心位和辅助位
   继续正常使用。
5. 赛事 0.60 不机械乘到 Fantasy Stat；它只通过重算后的 Swiss 预计 Series 机会数影响估值。
6. LGD 官方公开措辞未披露足以核验具体行为的证据，本发布版不把“假赛”写成已证实事实。

## Fantasy

1. [Stat 与队伍 Top 3 完整表](playbooks/group-roll/stat-team-top3-publication-v4.md)：当前 47 个
   合格位置池的排名、队伍 Top 3 与 400 次 Series 分组重采样稳定率。
2. [Title 分析与推荐](reports/ti2026-fantasy-title-recommendation-2026-08-10.md)：Prefix、Suffix、
   触发率、默认选择和客户端条件冲突。
3. [Group 40 Roll 玩家手册](playbooks/group-roll/group-roll-publication-manual-v4.md)：已刷新当前
   查表和候选池；冻结的 B/C/D 操作规则没有冒充重新认证。

## 瑞士轮 Forecast 与赛果证据

1. [官方首轮、计算过程与 16 槽建议](reports/ti2026-group-forecast-publication-2026-08-10.md)：
   五轮 Swiss 联合模拟、全部首轮概率、LGD 敏感性和逐类期望正确贡献。
2. [Swiss、身份与 LGD 实装记录](reports/ti2026-swiss-round1-roster-update-2026-08-10.md)：身份桥、
   registration identity window、0.60 改动、正式运行和验收记录。
3. [7.41 完整系列赛账本](reports/ti2026-group-current-patch-series-evidence-2026-08-08.md)：继承的
   历史附件，只用于逐场复查，不承载当前排名。
4. [2026 年战队已获奖金累计](reports/ti2026-team-prize-ytd-2026-08-08.md)与
   [赛事档位及总奖池](reports/ti2026-group-event-tier-prize-2026-08-08.md)：背景附件，不进入
   模型权重。

## 方法、权重与审计材料

1. [方法速查](reports/ti2026-methodology-quick-reference-2026-08-10.md)：数据、Fantasy 计分、
   Series、Swiss、身份和最终期望比例的玩家版说明。
2. [统一加权政策](WEIGHTING.md)：7.41e 倍率、赛事目录等级、时间衰减，以及为什么 LGD
   `0.60` 不属于历史证据权重。
3. [方法与证据权威性报告](reports/ti2026-methodology-and-evidence-authority-report-2026-08-10.md)：
   当前产品状态、冻结身份、留出结果、规则与已知限制。
4. [首轮与 LGD 一手调查](research/ti2026-swiss-round1-lgd-roster-2026-08-10.md)与
   [Fantasy 选手历史范围](research/ti2026-player-history-scope.md)：来源分级和范围约束。
5. [文件 SHA-256 清单](MANIFEST.sha256)：用于检查解压后的发布文件是否完整一致。

## 冻结身份

- Group run：`group-4cfa61a8f4a47746`
- Group Fantasy Stat run：`fantasy-8b0113b26a7da1c7`
- 当前顾问 P3 run：`fantasy-5ea8bdfd5fb528cb`
- Title run：`fantasy-b2240b141540675d`
- Tournament manifest SHA-256：
  `cf527bc9953edb1908be6a9531ec7579322e581a8db9cd3799cd8ba62c42722c`
- Team identity bridge config SHA-256：
  `dae7f5b08604a9082661db5034e7f359546950145c21021d3effb0af8201f0bb`
- Registration identity config SHA-256：
  `624ec8492a84eacd2849e823e98bfd23eb5c0a82b07e8afa4a59a57a8c058cd4`
- Swiss 格式 / 策略 SHA-256：
  `b505473a35522df6d8f56de14d1b1eea945bb4d5089855a448b1c4be3f7db7c6` /
  `245f046b3b0c1d02e2ee9bf6034cdf5e8c9682e3366487a0e306eef8bd9d40c5`
- Fantasy Stat evidence SHA-256：
  `1319be5a19029c04ec16496ad49b90807dda31b596492e580c84f986fac328b4`
- Rule snapshot：`20260810T134439Z-f26cfd47ab1d`

## 使用边界

- 首轮是 Valve 官方节点；A/B 初始池由 `.A/.B` 节点名与官方组内规则共同推断，API 没有独立
  `group_id` 字段。
- 后续存在多个合法配对和选对手决定；固定策略与种子保证可复现，但不声称预知赛事方决定。
- 当前赛事强度概率未经校准；TI 2025 留出命中率为 **56.25%**，不能把小幅差距当成确定性。
- 期望正确 5.1561 不是“保证答对 5 个”；单次结果的 P10 / 中位数 / P90 为 3 / 5 / 8。
- Fantasy 稳定率是历史 Series 重采样后排名保持频率，不是未来命中概率；缺失值不是 0。
- 锁定前若出现新比赛、名单或规则更新，必须推进显式 UTC `as_of` 后重新运行。
