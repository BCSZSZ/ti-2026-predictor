# TI 2026 首轮、16 队身份与 LGD 阵容：正式实装及重算

状态：**9 条规范身份桥、2 个注册身份窗口、LGD 0.60 主情景与正式重算已完成；赛事产物保留
`warning`，两个最终 run 均为 `publishable: true`。**

- 统一 `as_of`：`2026-08-10T13:45:12Z`
- 正式赛事产物：`artifacts/group-4cfa61a8f4a47746`
- 正式 Stat Top 3 证据：`artifacts/fantasy-8b0113b26a7da1c7`
- 当前顾问 P3：`artifacts/fantasy-5ea8bdfd5fb528cb`
- 沿用的 Title 证据：`artifacts/fantasy-b2240b141540675d`
- 主情景：LGD 正胜算 odds `×0.60`
- 模拟量：主情景 100,000 次；五个敏感性情景各 20,000 次
- 随机种子：`20260813`

## 最小实现范围

1. `config/ti2026.yaml` 只增加经稳定选手 ID 与时间边界核验的 bridge/window，不增加名称模糊
   匹配。
2. canonicalization 保留 `radiant_raw_team_id/dire_raw_team_id`，仅在
   `valid_from <= start_time <= valid_to` 且 `evidence_as_of <= run.as_of` 时映射。
3. canonical ID 的 registration identity window 在训练与特征入口继续生效；窗口外记录设为
   不可归属，而不是回写原始数据。
4. 历史 run、规则、数据、模型配置和种子仍进入运行身份；相同输入产生相同推荐 JSON。
5. 历史审计只比较其 `as_of` 当时已可用的客户端规则快照，之后捕获的快照不会制造伪 drift。

## 9 条 bridge 与两个窗口

| raw ID | canonical ID | 当前身份 |
| ---: | ---: | --- |
| `9824702` | `9572001` | PVISION → TEAM VISION |
| `10182357` | `10150413` | 1w → Iron Wing |
| `9303383` | `10149530` | L1GA TEAM → HULIGANI |
| `10182299` | `10149530` | L1 TEAM → HULIGANI |
| `10208009` | `10149530` | GOTF L1GA → HULIGANI |
| `9316703` | `5017210` | 临时注册 → Team Resilience |
| `10207984` | `5017210` | GOTF → Team Resilience |
| `10208071` | `8261500` | GOTF → Xtreme Gaming |
| `10208068` | `10150538` | LGD.Pinghu → LGD Gaming |

冻结比赛中共映射 203 场不同比赛。两个窗口为：

- `10150413 Iron Wing`：从 `2026-06-01T00:00:00Z` 起承认当前 1win 身份；排除 24 场转会前
  Tundra 比赛。
- `5017210 Team Resilience`：从 `2026-04-08T09:08:01Z` 起承认当前身份；阻止早年无关 ID
  复用进入当前路径。

`8291895 Tundra`、`9303484 HEROIC` 和无关同名 BoomBoys 明确不合并。完整证据见
[16 队身份审计](../research/ti2026-team-display-alias-audit-2026-08-11.md)。

## 正式赛事结果

正式运行保持直接 BO3 Series 概率和 LGD 0.60 odds 情景。官方首轮为：

| 节点 | 对阵 | 左队 | 右队 |
| --- | --- | ---: | ---: |
| Match 1.A | Team Falcons vs LGD Gaming | **75.65%** | **24.35%** |
| Match 2.A | Iron Wing vs Nigma Galaxy | **60.44%** | **39.56%** |
| Match 3.A | BoomBoys vs OG | **60.83%** | **39.17%** |
| Match 4.A | TEAM VISION vs Team Resilience | **68.08%** | **31.92%** |
| Match 1.B | Team Spirit vs Xtreme Gaming | **60.82%** | **39.18%** |
| Match 2.B | Team Liquid vs Vici Gaming | **66.41%** | **33.59%** |
| Match 3.B | Aurora Gaming vs GamerLegion | **66.62%** | **33.38%** |
| Match 4.B | Team Yandex vs HULIGANI | **78.24%** | **21.76%** |

正式 InGamePrediction：

| 类别 | 选择 |
| --- | --- |
| 4–0 | Team Yandex **17.28%** |
| 4–1 | Team Liquid **22.74%**；TEAM VISION **27.97%** |
| 淘汰轮胜者 | BoomBoys **39.46%**；Team Falcons **37.95%**；Aurora Gaming **35.49%**；Iron Wing **37.41%**；Team Spirit **36.85%** |
| 淘汰轮败者 | Xtreme Gaming **39.18%**；Vici Gaming **37.73%**；Team Resilience **34.31%**；OG **37.24%**；Nigma Galaxy **38.61%** |
| 1–4 | GamerLegion **25.32%**；HULIGANI **27.23%** |
| 0–4 | LGD Gaming **20.82%** |

逐类边际概率闭合为：

`0.17280 + 0.50710 + 1.87167 + 1.87074 + 0.52556 + 0.20821 = 5.15608`

- 期望正确：`5.1561 / 16`
- 最终期望正确比例：`32.23%`
- 95% Monte Carlo 区间：`5.1440–5.1682`
- 正确个数 P10 / 中位数 / P90：`3 / 5 / 8`

## Fantasy 重算

正式 Stat 证据重新生成 8,192 个公共情景和 400 次完整 Series 分组重采样，保持 47 / 48 个
队伍×位置池可用；唯一不可用的仍是 LGD 中单。身份扩展改变了预计 Swiss 机会数，因此 Top 3
数值和部分名次已经刷新。Title 输入不依赖队伍 team ID bridge，继续沿用既有 Title run。

- Stat evidence package SHA-256：
  `1319be5a19029c04ec16496ad49b90807dda31b596492e580c84f986fac328b4`
- Stat evidence JSON SHA-256：
  `fd61a9431e79b755fa75bdf6af4805c01de2060e50143fcdbef070805735a6c2`
- Stat Top 3 Markdown SHA-256：
  `e3be9feb7fd47a2e6f529ed4453cea860383d10e6dc545a53ccbed60d060bf95`
- Fantasy data snapshot SHA-256：
  `9208c15c173b7ee0fc05b0e04cc9e89f5aac8d78c1a2b4905d550e2abaf4bc7b`
- Fantasy scenario SHA-256：
  `f1c869662b3bf1f170ac68b843beb90a866c5bf4e46facf1047ecd95de7b7f8c`
- Fantasy pool set SHA-256：
  `6a01d321a8956211ebeb27a0537e8a311b7d6d6c6d90fb15843715901d2ed72d`

## 冻结身份与验收

- Tournament manifest SHA-256：
  `cf527bc9953edb1908be6a9531ec7579322e581a8db9cd3799cd8ba62c42722c`
- Team identity bridge config SHA-256：
  `dae7f5b08604a9082661db5034e7f359546950145c21021d3effb0af8201f0bb`
- Registration identity config SHA-256：
  `624ec8492a84eacd2849e823e98bfd23eb5c0a82b07e8afa4a59a57a8c058cd4`
- Swiss 格式 SHA-256：
  `b505473a35522df6d8f56de14d1b1eea945bb4d5089855a448b1c4be3f7db7c6`
- Swiss 情景策略 SHA-256：
  `245f046b3b0c1d02e2ee9bf6034cdf5e8c9682e3366487a0e306eef8bd9d40c5`
- Group recommendations SHA-256：
  `4c6c21adcf1911d897e870667b0c15bde0c7243df33813844779c2277c2b64ff`
- Group model SHA-256：
  `12006d7425f32a5c5b3f521e235233c927afb4f2dd6e4f64b199f16950c9be0d`
- Group details SHA-256：
  `4f8c34065c5bbdd5d9f7e49f38694375754a73c585c606d2f52246dda23548f0`

两项正式 run 的 `ti audit` 均返回 `publishable: true`。保留的 `warning` 来自客户端已知规则歧义、
未校准概率、非唯一后续配对、对手选择和深层 tiebreak 代理，不是 snapshot drift 或身份冲突。
