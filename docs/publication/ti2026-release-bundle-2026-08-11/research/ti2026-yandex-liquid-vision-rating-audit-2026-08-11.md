# TI 2026：Yandex、Liquid、TEAM VISION 强度评级审计

- 审计日期：2026-08-11
- 被审计发布运行：`group-a5d3e4484ebf918e`
- 统一截止时间（`as_of`）：`2026-08-10T13:45:12Z`
- 结论性质：除特别标成 `derived` / `counterfactual` 的项目外，数字均直接来自冻结运行产物、正式代码或冻结比赛快照。

> **实施跟进（2026-08-11）：** 本文以下主体保留对旧运行的原始诊断。建议的身份修复现已正式
> 实施：manifest schema v3 以半开区间把 `9824702` 规范化到 `9572001`，并保留 raw ID 和逐层
> 审计。正式重算运行是 `group-275030258cd6412d`；30 局映射清单 SHA-256 为
> `fc62041e35998833a0ddab535260bef2abc9489496a55aa45ced497f752f305d`，有效权重 `13.8645`。
> TEAM VISION 重算后为 Elo `1674.993`、Glicko `1838.610`、综合 `1756.802`，185 局中 116 局
> 为 7.41；原始别名 `9824702` 不再形成独立发布评级状态。下文“发布版”仍专指被审计的旧运行，
> “counterfactual”也只描述当时尚未落地的诊断阶段。

## 结论

发布结果中 **Team Yandex 1723.4 > Team Liquid 1699.4 > TEAM VISION 1678.6**，对当前模型输入而言计算是可复现的；但这个排序不应解释成“完整的现役 TEAM VISION 比 Liquid/Yandex 弱”。审计发现两个层次的原因：

1. **奖金和赛事名次根本不进入 Elo/Glicko。** 奖金报告把 TEAM VISION/PARIVISION 的 2026 组织成绩合计为 `$1,365,000`，而评级代码只按逐局胜负、赛前对手评级及 `patch × tier × age` 权重更新。奖金、最终名次、奖池规模都不在模型输入中。
2. **存在高影响的队伍身份断裂。** 发布模型只取 TI 参赛 ID `9572001` 的评级；冻结比赛明细中，同一套五人阵容另有 `9824702`（显示名 `PVISION`）的 30 局 7.41 比赛，其中包括 BLAST SLAM VII 和 EWC 2026。两组比赛没有在评级前桥接。`9572001` 的证据因此停在 2026-06-25，而 `9824702` 延续到 2026-07-19。
3. **Liquid 确有一个合法而很强的近期驱动。** 7.41e 边界后的 14 局，Liquid 为 11–3，有效权重 `14.582`；路径重放中这 14 局贡献 `+131.423` 综合评级分。它们单独就相当于发布版 TEAM VISION 全部有效权重的 `66.6%`，因此 Liquid 的 Elo 被明显推高。

最有解释力的反证是：被拆开的 `PVISION (9824702)` 在同一个发布模型里本身已有 **1752.7** 综合强度，高于 Yandex、Liquid 和 `TEAM VISION (9572001)`。把两 ID 在诊断副本中桥接后，TEAM VISION 的综合强度为 **1756.8**，成为这三队第一。这个数只是身份修复的只读反事实，不是可发布的新预测；正式修复必须建立有生效区间、以选手稳定 ID 证明的身份桥。

## 1. 发布运行和精确评级

运行清单 `artifacts/group-a5d3e4484ebf918e/run.json` 给出的 `as_of` 是 `2026-08-10T13:45:12Z`，数据指纹是 `cf7f2ab715e45a44031bfb5a7acaed73cde69902ef701dbb677692dc448849eb`，Git 状态是 `f63bc5495f096d73b6c021fcf935a528dd07ebc6-dirty-d63f2756bcf0`。模型 JSON 的审计 SHA-256 是 `f9067ee1bee7d833ec7e7a133334f397fd1f158662d317fae427c847ac4d9d4b`。

| 队伍（稳定 ID） | Elo | Glicko | RD | 50/50 综合 | 入模局数 | 7.41 局数 | 有效权重 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Team Yandex (`9823272`) | 1619.175 | 1827.586 | 86.649 | **1723.381** | 155 | 67 | 23.138 |
| Team Liquid (`2163`) | 1647.802 | 1750.949 | 63.404 | **1699.375** | 218 | 109 | 45.355 |
| TEAM VISION (`9572001`) | 1596.892 | 1760.399 | 94.569 | **1678.646** | 155 | 86 | 21.884 |

三队都从 1500 开始，故最终差值可直接分解：

- Yandex 相对 VISION：Elo `+22.282`，Glicko `+67.188`，综合 `+44.735`。
- Liquid 相对 VISION：Elo `+50.909`，Glicko反而 `-9.450`，综合 `+20.730`。换言之，**Liquid 高于 VISION 完全由 Elo 腿推动；VISION 的 Glicko 点估计其实略高于 Liquid。**
- Liquid 的 RD 最低，来自更多且更新的证据；VISION 的最后一局（按 `9572001`）较早。正式实现只会在下一场比赛前按空窗期膨胀 RD，并未把最后一场之后至 `as_of` 的空窗单独结算进序列末端 RD，因此表中 RD 应理解为“最后一次更新后的 RD”，不是完整的 `as_of` 空窗校正值。

## 2. 模型实际看了什么

正式路径是 `src/ti_predictor/forecasting.py::_load_strength_model` → `src/ti_predictor/models/evidence.py::build_evidence_set` → `src/ti_predictor/models/ratings.py::_weighted_sequential_elo/_sequential_glicko`。

单局权重为：

```text
evidence_weight = patch_weight × tier_weight × 2^(-age_days / 60)
```

- 目标大版本 7.41：`1.0`；上一个大版本 7.40：`0.15`。
- 7.41e 自 `2026-07-30T23:58:15Z` 起再乘 `1.5`。
- OpenDota `premium` / `professional`：`1.0` / `0.75`。
- Elo：初值 1500，`K=28`；Glicko：初值 1500、初始 RD 350；综合为 Elo/Glicko 各 50%。

这三队所有正权重比赛在处理表中都标为 `professional`，因此赛事之间没有进一步的“TI/EWC/大赛名次”级别差异。当前数据的 7.41 比赛甚至没有字母小版本名；7.41e 加权由 UTC 生效边界派生。赛事奖金和最终名次只存在于 `config/publication/ti2026-team-prize-ytd-2026-08-08.json` 及发布报告，评级加载函数没有读取这些文件。

| 队伍 | 胜–负 | 加权胜率 | 7.40：局/权重 | 7.41：局/权重 | 最后一局 |
|---|---:|---:|---:|---:|---|
| Yandex | 96–59 | 70.33% | 88 / 1.337 | 67 / 21.801 | 2026-07-19 11:15Z |
| Liquid | 133–85 | 61.37% | 109 / 1.677 | 109 / 43.678 | 2026-08-05 19:53Z |
| VISION `9572001` | 98–57 | 70.63% | 69 / 1.046 | 86 / 20.839 | 2026-06-25 17:25Z |

加权胜率不是评级：胜负发生时的对手强度、预期胜率、Glicko RD 和顺序都会改变单局增量。这也解释了 VISION 的加权胜率略高，却未自动高于 Liquid。

## 3. 近期比赛对差值的贡献

以下“综合增量”是按正式代码逐局重放后的 `0.5 × (Elo 增量 + Glicko 增量)`；它在给定排序、权重和赛前状态下可加总到最终评级，但不是独立的因果估计。

| 队伍/赛事块 | 局分 | 有效权重 | Elo 增量 | Glicko 增量 | 综合增量 |
|---|---:|---:|---:|---:|---:|
| Liquid：7.41e 生效后的 14 局 | 11–3 | 14.582 | +125.175 | +137.672 | **+131.423** |
| Liquid：1win Essence II 全赛事 | 12–4 | 15.907 | +121.563 | +130.510 | **+126.037** |
| Yandex：EWC 2026 | 14–3 | 9.214 | +65.784 | +91.811 | **+78.797** |
| Yandex：BLAST SLAM VII | 18–7 | 8.359 | +56.488 | +203.334 | **+129.911** |
| VISION `9572001`：DreamLeague 29 | 22–11 | 9.391 | +32.028 | +33.980 | **+33.004** |
| VISION `9572001`：TI 欧洲区预选 | 6–1 | 3.051 | +19.821 | +12.937 | **+16.379** |

Liquid 在 7.41e 的代表结果包括：对 BoomBoys 2–0、GamerLegion 2–0、Vici 2–1、1w 2–0，以及对 Falcons 3–2。每局权重约 `1.003–1.065`；相比之下，VISION `9572001` 最后七局每局约 `0.44`，Yandex 在 EWC 的末段约 `0.53–0.58`。

共同对手的路径增量也显示了这个差异：

| 对手 | Yandex（局/胜/权重/综合增量） | Liquid | VISION `9572001` |
|---|---|---|---|
| GamerLegion | 3 / 2 / 0.314 / +19.28 | 10 / 9 / 3.219 / **+45.35** | 5 / 3 / 0.554 / +19.04 |
| Team Falcons | 6 / 3 / 0.769 / -25.87 | 23 / 13 / 8.056 / **+21.33** | 12 / 8 / 1.695 / +13.11 |
| Team Spirit | 19 / 15 / 2.660 / **+71.32** | 14 / 6 / 2.901 / -19.45 | 7 / 2 / 0.934 / +0.66 |

直接交手中，2026-05-26 Yandex 击败 Liquid 的一局（权重 `0.3117`）给 Yandex 路径综合增量 `+16.37`。同日 Yandex 击败 `PVISION 9824702`（权重 `0.3121`）的比赛没有记到 `VISION 9572001` 上；这正是身份断裂对“直接交手”统计的具体影响。

## 4. 高影响身份问题：`9572001` 与 `9824702`

### 可直接确认的事实

- Valve 官方 TI 2026 `GetLeagueData` 把当前参赛队 TEAM VISION 标为 `team_id=9572001`。
- 发布奖金配置明确把来源名 `PARIVISION`、`TEAM VISION` 汇总到 `9572001`，并把 EWC 2026 冠军等 8 项合计为 `$1,365,000`。
- 冻结逐局表中另有 `team_id=9824702`、显示名 `PVISION`：30 局全为 7.41，24–6，有效权重 `13.8645`；BLAST SLAM VII 为 8–3，EWC 2026 为 16–3。
- 冻结选手明细显示，`9572001` 在 2026-05-13 至 06-25 的 40 局，与 `9824702` 在 2026-05-26 至 07-19 的 30 局，五个 account ID **完全相同**：`73401082, 106573901, 164199202, 195108598, 1044002267`。日期区间还存在重叠，因此不是简单的前后两套阵容。
- `config/ti2026.yaml` 和 `roster_intervals.parquet` 把这五人作为 `9572001` 的现役名单；评级代码没有队伍 ID 桥接层。

### 对发布评级的影响

| 实体 | Elo | Glicko | RD | 综合 | 局数 | 7.41 局数 | 权重 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 发布版 `VISION 9572001` | 1596.892 | 1760.399 | 94.569 | 1678.646 | 155 | 86 | 21.884 |
| 同一模型内的 `PVISION 9824702` | 1617.549 | 1887.810 | 103.957 | **1752.679** | 30 | 30 | 13.864 |
| `counterfactual`：按同五人证据桥接后 | 1674.993 | 1838.610 | 75.274 | **1756.802** | 185 | 116 | 35.749 |

桥接反事实同时重放全网络，因此 Yandex/Liquid 会轻微变为 1725.934/1700.374；VISION 仍分别领先 `30.868` 和 `56.428`。这证明当前“VISION 低于两队”的主要异常来自身份分裂，而不是完整比赛结果本身。正式修复不能只按名称替换，须用稳定 account ID、赛事注册 ID 和有效区间建立可审计的别名/继承关系。

## 5. 数据质量与泄漏检查

| 检查 | 结果 | 解释 |
|---|---:|---|
| 原始处理表行数 | 44,906 | `matches.parquet` 全表 |
| capture `as_of/fetched_at` 过滤后 | 44,764 | 晚于运行截止的快照未进入此次运行 |
| 截止前、身份和结果完整的完成局 | 42,300 | 正式 `prepare_completed_games` 输出 |
| 正权重且处于目标连通分量 | 3,943 | 7.40/7.41、允许 tier、463 队连通网络 |
| 未来比赛 | 0 | 没有 `start_time >= as_of` 的入模局 |
| 重复 match ID | 0 | 未发生重复更新 |
| 同队对同队 | 0 | 无此类结构错误 |
| 无效开始时间 | 0 | 无 |
| 缺身份或结果（全局） | 2,464 | 已在完成局准备阶段排除；目标 16 队均在正权重网络中出现 |
| 不支持 tier（全局） | 19,433 | 权重为零；运行已发 warning |
| 选中 match ID 指纹 | `9cd5ed90e2138c6b522e6e1270a8334f2c892ecacd5fe1a83fc9f147e27c9a7e` | 与发布模型审计一致 |

没有发现重复、错边、未来比赛或 `as_of` 泄漏。发现的实质问题是**队伍身份分裂**，外加两个模型解释限制：奖金/名次不作为特征，以及当前有效比赛全部落在同一个 `professional=0.75` 档，无法表达大赛层级差异。初值对所有队都是 1500，没有赛区专属初值；赛区只通过 463 队的共同对手网络间接传递。Yandex/Liquid/VISION 都在同一连通分量，因此不是“不同赛区各自孤立评级”。

## 6. 可复核命令

```powershell
# 核对运行截止、数据指纹和运行 ID
Get-Content -Raw artifacts/group-a5d3e4484ebf918e/run.json

# 从冻结模型提取三队与 9824702 的精确状态
$m = Get-Content -Raw artifacts/group-a5d3e4484ebf918e/model.json | ConvertFrom-Json
foreach ($id in '9823272','2163','9572001','9824702') {
  [pscustomobject]@{
    id=$id; elo=$m.model.ratings.$id; glicko=$m.model.glicko_ratings.$id
    rd=$m.model.glicko_deviations.$id
    combined=($m.model.ratings.$id+$m.model.glicko_ratings.$id)/2
    games=$m.model.matches_played.$id
    patch_games=$m.model.target_patch_matches.$id
    weight=$m.model.effective_weight.$id
  }
}

# 核对冻结处理表指纹
Get-FileHash -Algorithm SHA256 data/processed/matches.parquet,
  data/processed/fantasy_performance_samples.parquet,
  data/processed/roster_intervals.parquet

# 重新生成相同发布运行（会写新的/相同 run artifact，审计时谨慎执行）
uv run ti forecast group --as-of 2026-08-10T13:45:12Z --profile all \
  --samples 100000 --sensitivity-samples 20000 --seed 20260813
```

路径增量的审计方法是：对 `build_evidence_set(...)` 返回的 3,943 局，严格按 `start_time, match_id` 排序，逐局调用正式 `_weighted_sequential_elo` 等价公式及 `_glicko_update`；每队每局记录更新前后差。最终三队重放值与 `model.json` 逐浮点位一致。

## 7. 来源与冻结指纹

| 来源 | 用途 | 抓取/截止 | SHA-256 / 标识 |
|---|---|---|---|
| `artifacts/group-a5d3e4484ebf918e/run.json` | 发布运行清单 | `2026-08-10T13:45:12Z` | data `cf7f2ab715e45a44031bfb5a7acaed73cde69902ef701dbb677692dc448849eb` |
| `artifacts/group-a5d3e4484ebf918e/model.json` | 精确 Elo/Glicko/RD/证据审计 | 同上 | `f9067ee1bee7d833ec7e7a133334f397fd1f158662d317fae427c847ac4d9d4b` |
| `config/models/team-strength-v2.json` | 权重、初值、组合策略 | 同上 | 发布 policy `aa826cf3ef95fe9535192fd390dbe27541c13764ab4dbc88dd94ea579cadc0d4` |
| `data/processed/matches.parquet` | 冻结比赛目录 | 最晚可用抓取 2026-08-08；运行再按 `as_of/fetched_at` 过滤 | `25cb708e91c7c668d885093c32ef642b60a0e6beb9a43427d34db4579b3b5c75` |
| `data/processed/fantasy_performance_samples.parquet` | 稳定 account ID 阵容交叉核验 | 冻结处理表 | `9053a10544891284771e03352e871ec8eb51cfbc41204b2fffb77999d1d481f0` |
| [Valve `GetLeagueData`, league 19719](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719) | 官方 TI 参赛 team ID | `2026-08-10T13:45:12Z` | `73519bcb40a40a02de7a3b343ce3daf4a5786d449d058d3300569b1bbea84c2a` |
| [OpenDota match 8866148821](https://api.opendota.com/api/matches/8866148821) | `9572001` 最后一场系列的冻结逐局/选手证据 | `2026-08-01T11:13:23.419869Z` | `926208775918ec4499ddb7a5786d42f8f57c97d28fe105cbcd7eeef40fb291d2` |
| [OpenDota match 8904012666](https://api.opendota.com/api/matches/8904012666) | `9824702` EWC 决赛阶段同五人证据 | `2026-08-01T15:06:06.533021Z` | `c68fbbc61bbf14b9ed0f15e2a03bd804c852f12562f75d3bb46e68ae7522ba1a` |
| `config/publication/ti2026-team-prize-ytd-2026-08-08.json` | 2026 奖金/组织名映射；不进评级 | `as_of=2026-08-08T14:37:14Z` | 该配置声明 VISION `$1,365,000`、Yandex `$1,177,500`、Liquid `$1,002,500` |

限制：历史比赛主证据是仓库冻结的 OpenDota API 响应，不应表述为 Valve 官方比赛结果；Valve 一手接口在本审计中只用于确认 TI 2026 当前参赛 ID。身份桥接结论由冻结选手 account ID 的一致性、日期重叠和仓库现有组织名映射共同支持，属于高置信 `derived`。
