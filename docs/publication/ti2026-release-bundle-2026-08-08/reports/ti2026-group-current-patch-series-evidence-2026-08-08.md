# TI 2026 小组赛：7.41 系列赛证据展开

状态：**玩家可读的赛果账本；已补充精确小版本、社区档位、总奖金和最终名次，不单独决定排名**

- 比赛数据截止：`2026-08-08T04:11:08Z`
- 发布信息截止：`2026-08-08T06:05:53Z`；只补版本边界和赛事资料，不加入新比赛
- 版本范围：7.41 全体，并细分 7.41（无字母）、7.41a、7.41b、7.41c、7.41d、7.41e
- 完整系列赛：409 个，共 866 局
- 全部合格单局：871 局；另有 5 局不能组成完整系列，仍保留给单局模型
- 其中本届 16 队直接交手：176 个系列，覆盖 80 组对手
- 排列方式：最近赛事在前；日期为系列赛最后一局的 UTC 日期

综合排名、模型对位和填写建议见 [最终预测正文](ti2026-group-forecast-publication-2026-08-08.md)，
一页版本见 [易懂总结](ti2026-group-forecast-publication-summary-2026-08-08.md)。

## 这份表能说明什么

这份文件把当前 7.41 大版本里，涉及本届 16 支队伍的完整 BO1、BO2、BO3 和 BO5 都展开。
它适合回答三件事：某队最近实际打过谁、系列赛结果怎样、两支参赛队有没有直接交手。

它不能直接把“38 胜”解释成比“23 胜”更强。各队参加的赛事、对手和系列数量不同；正式排名还会
逐局考虑对手强弱、比赛时间和赛事级别，并通过完整对手网络比较没有直接交手的队伍。因此：

- 本页的“胜–平–负”是已经发生的完整系列赛记录；
- 预测正文里的百分比是中立条件下一局的模型倾向；
- 这些模型百分比没有通过概率校准，也不是 BO3 或完整系列赛胜率；
- 两者可以互相核对，但不是同一个数字，也不要求方向永远一致。

## 7.41 全体和小版本怎么读

“7.41 全体”就是本页原有的总口径；下面再按比赛开始时实际生效的精确版本拆开。同一个系列的
每一局都落在同一小版本，本次没有跨版本系列。小版本不是新的强度权重，也没有重算 Forecast，
只是让玩家看出一段战绩究竟来自 7.41a、7.41b 还是更近的 7.41e。

| 精确版本 | 起算时间（UTC） | 完整系列赛 | 全部单局 | 占 409 个系列 |
| --- | --- | ---: | ---: | ---: |
| 7.41（无字母） | 03-24 00:50:59 | 27 | 56 | 6.6% |
| 7.41a | 03-27 22:15:21 | 18 | 45 | 4.4% |
| 7.41b | 04-07 20:24:46 | 83 | 204 | 20.3% |
| 7.41c | 05-06 22:17:55 | 150 | 271 | 36.7% |
| 7.41d | 06-05 00:45:14 | 105 | 237 | 25.7% |
| 7.41e | 07-30 23:58:15 | 26 | 58 | 6.4% |
| **7.41 全体** | 03-24 至数据截止 | **409** | **871** | **100%** |

“全部单局”包含那 5 局无法组成完整系列的片段，所以各行单局总数合计为 871，而完整系列里只有
866 局。下面的小版本队伍表只用完整系列；没列出的队伍表示该小版本没有完整系列样本。

### 7.41（无字母）

| 队伍 | 完整系列 | 系列胜–平–负 | 单局胜–负 |
| --- | ---: | ---: | ---: |
| Team Yandex | 4 | 4–0–0 | 8–1 |
| Team Falcons | 4 | 1–2–1 | 4–4 |
| TEAM VISION | 6 | 5–0–1 | 8–2 |
| BoomBoys | 4 | 2–0–2 | 4–3 |
| Team Spirit | 5 | 3–0–2 | 8–4 |
| Aurora Gaming | 4 | 3–0–1 | 7–2 |
| OG | 3 | 0–1–2 | 1–5 |
| GamerLegion | 4 | 1–0–3 | 2–5 |
| Xtreme Gaming | 5 | 3–1–1 | 7–5 |

### 7.41a

| 队伍 | 完整系列 | 系列胜–平–负 | 单局胜–负 |
| --- | ---: | ---: | ---: |
| Team Yandex | 3 | 1–0–2 | 3–6 |
| TEAM VISION | 4 | 3–0–1 | 7–2 |
| Aurora Gaming | 3 | 2–0–1 | 4–4 |
| Vici Gaming | 2 | 1–0–1 | 3–2 |
| GamerLegion | 4 | 4–0–0 | 8–2 |
| Xtreme Gaming | 5 | 4–0–1 | 9–3 |

### 7.41b

| 队伍 | 完整系列 | 系列胜–平–负 | 单局胜–负 |
| --- | ---: | ---: | ---: |
| Team Yandex | 3 | 0–0–3 | 1–6 |
| Team Falcons | 9 | 6–0–3 | 13–8 |
| TEAM VISION | 11 | 8–0–3 | 19–8 |
| BoomBoys | 13 | 12–0–1 | 27–7 |
| Team Liquid | 14 | 8–0–6 | 21–15 |
| Team Resilience | 10 | 7–0–3 | 13–8 |
| Team Spirit | 9 | 3–0–6 | 9–14 |
| Aurora Gaming | 8 | 6–0–2 | 13–9 |
| Vici Gaming | 13 | 9–0–4 | 21–12 |
| OG | 3 | 1–0–2 | 2–4 |
| GamerLegion | 11 | 6–0–5 | 15–12 |
| Xtreme Gaming | 9 | 4–0–5 | 10–10 |

### 7.41c

| 队伍 | 完整系列 | 系列胜–平–负 | 单局胜–负 |
| --- | ---: | ---: | ---: |
| Team Yandex | 14 | 10–0–4 | 13–5 |
| Team Falcons | 23 | 17–0–6 | 28–11 |
| TEAM VISION | 11 | 10–0–1 | 22–11 |
| BoomBoys | 21 | 13–0–8 | 21–15 |
| Team Liquid | 22 | 11–0–11 | 19–19 |
| Team Spirit | 24 | 14–0–10 | 25–16 |
| Aurora Gaming | 27 | 16–0–11 | 30–22 |
| LGD Gaming | 14 | 10–0–4 | 13–6 |
| Vici Gaming | 8 | 2–0–6 | 7–12 |
| HULIGANI | 3 | 2–0–1 | 4–3 |
| OG | 12 | 3–0–9 | 3–10 |
| Nigma Galaxy | 10 | 5–0–5 | 12–10 |
| GamerLegion | 9 | 3–0–6 | 8–13 |
| Xtreme Gaming | 22 | 7–0–15 | 13–21 |
| Iron Wing | 16 | 5–0–11 | 8–16 |

### 7.41d

| 队伍 | 完整系列 | 系列胜–平–负 | 单局胜–负 |
| --- | ---: | ---: | ---: |
| Team Yandex | 10 | 8–1–1 | 19–5 |
| Team Falcons | 9 | 5–1–3 | 12–7 |
| TEAM VISION | 3 | 3–0–0 | 6–1 |
| BoomBoys | 12 | 7–2–3 | 19–9 |
| Team Liquid | 9 | 3–3–3 | 10–10 |
| Team Resilience | 3 | 3–0–0 | 6–0 |
| Team Spirit | 10 | 7–2–1 | 16–6 |
| Aurora Gaming | 8 | 4–2–2 | 11–7 |
| LGD Gaming | 16 | 10–2–4 | 24–14 |
| Vici Gaming | 16 | 10–0–6 | 20–15 |
| HULIGANI | 5 | 4–0–1 | 9–5 |
| OG | 9 | 5–2–2 | 13–8 |
| Nigma Galaxy | 12 | 7–1–4 | 16–10 |
| GamerLegion | 8 | 4–1–3 | 10–7 |
| Xtreme Gaming | 6 | 1–2–3 | 5–8 |

### 7.41e

| 队伍 | 完整系列 | 系列胜–平–负 | 单局胜–负 |
| --- | ---: | ---: | ---: |
| Team Falcons | 6 | 4–0–2 | 8–5 |
| BoomBoys | 7 | 4–0–3 | 9–7 |
| Team Liquid | 6 | 5–0–1 | 11–3 |
| LGD Gaming | 2 | 0–0–2 | 0–4 |
| Vici Gaming | 7 | 3–1–3 | 9–8 |
| OG | 6 | 2–2–2 | 7–6 |
| Nigma Galaxy | 2 | 0–1–1 | 1–3 |
| GamerLegion | 4 | 1–0–3 | 2–6 |

## 赛事档位、总奖金和赛事性质

截至发布信息截止时点，9 个主赛事中有 **6 个 Tier 1、3 个 Tier 2**。Tier 是社区对赛事阵容、
竞争强度和影响力的综合分档，不是由奖金单独换算，也不直接进入本页的队伍排名。比如 Games of
the Future 2026 奖金达到 100 万美元，但当前仍是 Tier 2；1win Essence II 奖金只有 20 万美元，
当前是 Tier 1。

9 个主赛事公布的总奖金合计 **US$7,472,000**：1 个 200 万美元、5 个 100 万美元，另有
20 万、17.2 万和 10 万美元各 1 个。资格赛不继承主赛事奖金；“无独立奖金”表示规则明确说明
没有奖金，“未公布”只表示在截止时点没有找到可确认的独立金额，不能当成 0。

“通往 Tier 1”描述资格赛的晋级目标，不表示资格赛本身等同于 Tier 1 主赛事。底层目录口径仍然
保留：下列 18 个赛事、409 个完整系列全部属于职业赛事（professional），没有 premium。

| 赛事 | 性质 | 社区档位 | 总奖金 | 精确版本 | 完整系列 | 全部单局 |
| --- | --- | --- | ---: | --- | ---: | ---: |
| ESL One Birmingham 2026 | 主赛事 | Tier 1 | US$1,000,000 | 7.41、7.41a | 32 | 70 |
| BLAST SLAM VII 中国资格赛 | 资格赛 | 通往 Tier 1 | 无独立奖金 | 7.41a | 5 | 11 |
| BLAST SLAM VII 欧洲资格赛 | 资格赛 | 通往 Tier 1 | 无独立奖金 | 7.41a | 4 | 10 |
| Premier Series | 主赛事 | Tier 2 | US$100,000 | 7.41a、7.41b | 15 | 39 |
| DreamLeague 29 资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41b | 20 | 51 |
| PGL Wallachia S8 | 主赛事 | Tier 1 | US$1,000,000 | 7.41b | 40 | 99 |
| ESL Challenger China x ACL | 主赛事 | Tier 2 | US$172,000 | 7.41b | 12 | 25 |
| DreamLeague 29 | 主赛事 | Tier 1 | US$1,000,000 | 7.41c | 68 | 164 |
| BLAST SLAM VII | 主赛事 | Tier 1 | US$1,000,000 | 7.41c、7.41d | 79 | 101 |
| EWC 2026 地区资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41c | 10 | 26 |
| TI 2026 中国区资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41d | 8 | 18 |
| TI 2026 南美区资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41d | 4 | 10 |
| TI 2026 东南亚区资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41d | 4 | 11 |
| TI 2026 欧洲区资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41d | 14 | 35 |
| TI 2026 北美区资格赛 | 资格赛 | 通往 Tier 1 | 未公布 | 7.41d | 3 | 7 |
| Esports World Cup 2026 | 主赛事 | Tier 1 | US$2,000,000 | 7.41d | 60 | 126 |
| 1win Essence II | 主赛事 | Tier 1 | US$200,000 | 7.41d、7.41e | 28 | 60 |
| Games of the Future 2026 | 主赛事 | Tier 2 | US$1,000,000 | 7.41e | 3 | 8 |
| **合计** | **9 个主赛事、9 个资格赛** | **主赛事：6 个 Tier 1、3 个 Tier 2** | **主赛事 US$7,472,000** | **7.41 全体** | **409** | **871** |

## 已结束主赛事的最终名次

这里统计的是“同一支已登记队伍”在 9 个已结束主赛事里的最终名次。每次参赛只落入一个档：冠军、
亚军、3–4、5–8、9–16 或 17 名以后，所以不会把“八强”和“十六强”重复累计。相似队名、曾用名，
或者看起来阵容相近但登记身份不同的队伍，不会自动合并。

| 综合排名 | 队伍 | 主赛事参赛 | 冠军 | 亚军 | 3–4 | 5–8 | 9–16 | 17名以后 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Team Yandex | 4 | 1 | 1 | 1 | 0 | 1 | 0 |
| 2 | Team Falcons | 6 | 0 | 1 | 2 | 3 | 0 | 0 |
| 3 | TEAM VISION | 4 | 2 | 0 | 1 | 1 | 0 | 0 |
| 4 | BoomBoys | 6 | 1 | 1 | 2 | 1 | 1 | 0 |
| 5 | Team Liquid | 6 | 1 | 0 | 1 | 2 | 2 | 0 |
| 6 | Team Resilience | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| 7 | Team Spirit | 6 | 0 | 0 | 1 | 5 | 0 | 0 |
| 8 | Aurora Gaming | 5 | 0 | 2 | 1 | 1 | 1 | 0 |
| 9 | LGD Gaming | 3 | 0 | 1 | 0 | 1 | 1 | 0 |
| 10 | Vici Gaming | 6 | 1 | 0 | 1 | 2 | 2 | 0 |
| 11 | HULIGANI | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 12 | OG | 4 | 0 | 0 | 0 | 1 | 2 | 1 |
| 13 | Nigma Galaxy | 3 | 0 | 0 | 0 | 1 | 2 | 0 |
| 14 | GamerLegion | 6 | 0 | 0 | 1 | 1 | 3 | 1 |
| 15 | Xtreme Gaming | 6 | 0 | 0 | 2 | 1 | 3 | 0 |
| 16 | Iron Wing | 2 | 0 | 0 | 0 | 0 | 2 | 0 |

“主赛事参赛”为同一稳定队伍身份在本页 9 个主赛事中的出现次数，不是队伍历史生涯参赛总数。
例如 HULIGANI 的 0 表示当前 7.41 账本里只有资格赛，没有可计最终名次的主赛事。

### 名次来自哪些赛事

| 主赛事 | 本届队伍的最终名次 |
| --- | --- |
| ESL One Birmingham 2026 | Yandex 亚军；VISION、Xtreme 3–4；Falcons、Spirit、Aurora 5–8；Boom、OG、Gamer 9–16 |
| Premier Series | VISION 冠军；Gamer 3–4；Liquid、Spirit 5–8 |
| PGL Wallachia S8 | Boom 冠军；Aurora 亚军；Falcons、Liquid 3–4；VISION、Spirit 5–8；Yandex、Vici、Gamer、Xtreme 9–16 |
| ESL Challenger China x ACL | Vici 冠军；Resilience 亚军；Xtreme 3–4 |
| DreamLeague 29 | VISION 冠军；Aurora 亚军；Falcons、Spirit 3–4；Boom、Xtreme 5–8；Liquid、Vici、Nigma、Gamer、Iron 9–16 |
| BLAST SLAM VII | Yandex 冠军；LGD 亚军；Boom、Aurora 3–4；Falcons、Liquid、Spirit 5–8；OG、Xtreme、Iron 9–16 |
| Esports World Cup 2026 | Boom 亚军；Yandex、Vici 3–4；Falcons、Spirit、Nigma 5–8；Liquid、Aurora、LGD、Xtreme 9–16；OG、Gamer 17名以后 |
| 1win Essence II | Liquid 冠军；Falcons 亚军；Boom 3–4；Vici、OG、LGD、Gamer 5–8；Nigma 9–16 |
| Games of the Future 2026 | Vici 5–8 |

### 资格赛只看是否晋级

资格赛有单名额、多名额和分赛区结构，不能把“最后一场赢了”统一叫冠军。本页只记录它是否完成
对应的晋级任务。

| 资格赛 | 晋级的本届队伍 | 未晋级的本届队伍 |
| --- | --- | --- |
| BLAST SLAM VII 中国资格赛 | Xtreme | Vici |
| BLAST SLAM VII 欧洲资格赛 | VISION、Aurora | 无 |
| DreamLeague 29 资格赛 | Liquid、Boom、Vici、Gamer | Resilience、OG |
| EWC 2026 地区资格赛 | LGD、Nigma、Gamer | HULIGANI |
| TI 2026 中国区资格赛 | Resilience、Vici | 无 |
| TI 2026 南美区资格赛 | LGD | 无 |
| TI 2026 东南亚区资格赛 | OG | 无 |
| TI 2026 欧洲区资格赛 | VISION、Spirit、Nigma、HULIGANI | 无 |
| TI 2026 北美区资格赛 | Gamer | 无 |

## 五个实力带的数据展开

下表按正式综合排名排列。“系列赛”统计所有合格对手，不只统计本届队伍之间的交手。原始记录适合
看近期表现和样本量，但不能脱离对手强弱直接重排队伍。

| 排名 | 实力带 | 队伍 | 完整系列赛 | 系列胜–平–负 | 单局胜–负 |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | 单独领先 | Team Yandex | 34 | 23–1–10 | 44–23 |
| 2 | 第一追赶组 | Team Falcons | 51 | 33–3–15 | 65–35 |
| 3 | 第一追赶组 | TEAM VISION | 35 | 29–0–6 | 62–24 |
| 4 | 第一追赶组 | BoomBoys | 57 | 38–2–17 | 80–41 |
| 5 | 第一追赶组 | Team Liquid | 51 | 27–3–21 | 61–47 |
| 6 | 上中游 | Team Resilience | 13 | 10–0–3 | 19–8 |
| 7 | 上中游 | Team Spirit | 48 | 27–2–19 | 58–40 |
| 8 | 上中游 | Aurora Gaming | 50 | 31–2–17 | 65–44 |
| 9 | 胶着中游 | LGD Gaming | 32 | 20–2–10 | 37–24 |
| 10 | 胶着中游 | Vici Gaming | 46 | 25–1–20 | 60–49 |
| 11 | 胶着中游 | HULIGANI | 8 | 6–0–2 | 13–8 |
| 12 | 胶着中游 | OG | 33 | 11–5–17 | 26–33 |
| 13 | 胶着中游 | Nigma Galaxy | 24 | 12–2–10 | 29–23 |
| 14 | 后段 | GamerLegion | 40 | 19–1–20 | 45–45 |
| 15 | 后段 | Xtreme Gaming | 47 | 19–3–25 | 44–47 |
| 16 | 后段 | Iron Wing | 16 | 5–0–11 | 8–16 |

这张表最明显地支持两点：追赶组和上中游整体有较多正战绩，后段三队的单局总记录更弱；同时，
Resilience、HULIGANI 和 Iron Wing 的完整系列样本明显更少，精确名次自然更容易变化。

完整 Series 局数不一定等于强度报告里的 7.41 单局数：Resilience 另有 2 局，Liquid、LGD 和
GamerLegion 各另有 1 局无法组成完整系列。模型仍会使用这 5 局，本页只是不编造它们缺失的
Series 比分；文末单独列出这些片段。

## 实力带之间的直接交手

这里只统计本届 16 队彼此之间的完整系列。箭头左侧为本行统计对象；例如“追赶组 → 胶着中游
19–1–6”表示追赶组对胶着中游取得 19 个系列胜、1 平、6 负。

| 对位 | 系列数量 | 左侧胜–平–负 | 单局胜–负 | 怎么理解 |
| --- | ---: | ---: | ---: | --- |
| Yandex → 第一追赶组 | 6 | 3–0–3 | 5–5 | 直接交手完全打平，符合“小优也会经常输”，不支持稳胜。 |
| Yandex → 上中游 | 6 | 5–0–1 | 9–2 | 对下一档的直接结果更清楚。 |
| Yandex → 胶着中游 | 7 | 5–1–1 | 11–4 | 跨层优势比对追赶组明显。 |
| Yandex → 后段 | 4 | 4–0–0 | 6–1 | 当前样本方向一致，但仍只有 4 个系列。 |
| 第一追赶组 → 上中游 | 27 | 15–1–11 | 34–28 | 有优势但不大，两档边缘可能互换。 |
| 第一追赶组 → 胶着中游 | 26 | 19–1–6 | 35–17 | 是“跨层通常约 60%–65%”最直接的赛果支撑。 |
| 第一追赶组 → 后段 | 25 | 22–0–3 | 40–9 | 当前版本最清楚的跨层差距之一。 |
| 上中游 → 胶着中游 | 16 | 10–1–5 | 21–13 | 整体方向支持分层，但不是压倒性差距。 |
| 上中游 → 后段 | 15 | 11–0–4 | 21–9 | 上中游整体占优。 |
| 胶着中游 → 后段 | 10 | 7–0–3 | 11–6 | 有方向，但样本比追赶组的跨层交手少。 |

## 六条关键胜负关系，证据到底有多少

1. **Yandex 对追赶组是小优，不是稳胜。** 六个直接系列为 3 胜 3 负、单局 5–5。模型给出的
   56%–58% 小优主要来自全部对手网络，而不是直接交手碾压；原始记录反而提醒我们不要把它当稳胜。
2. **追赶组内部应按五五开。** 四队内部共有 22 个系列，21 个分出胜负、1 个打平。VISION 为
   5–0–1，Falcons 为 6–1–8，BoomBoys 为 5–1–5，Liquid 为 5–0–7；样本量和比赛时间不同，
   单次赛事就能明显改变表面顺序，因此模型把四队压在 48%–52% 更适合作为玩家判断。
3. **Resilience、Spirit、Aurora 的精确顺序证据不足。** Resilience 与另两队都没有完整直接
   系列；Spirit 与 Aurora 的四次交手正好各赢两次、单局 4–4。这里的 50–50 和 48% 主要是
   通过共同对手推出来的，不是充分的直接交手结论。
4. **胶着中游确实“胶着”，但直接样本很少。** 五队内部只有 5 个完整系列，HULIGANI 没有与
   同带队伍直接交手。46%–54% 是模型在更大对手网络上的判断，不能说成这五队已经互相打遍。
5. **后段三队的内部排序最不该写死。** 只有 3 个直接系列：Xtreme 以 2–0 赢过 GamerLegion，
   Iron Wing 则两次击败 Xtreme，GamerLegion 与 Iron Wing 没有直接交手。模型仍把三队放在
   51–49 和 53%–54% 的窄差距内，说明它采用的是完整赛程强度，而不是三场直接赛果投票。
6. **第一追赶组对胶着中游是最有直接支撑的关键关系。** 26 个系列打成 19–1–6、单局 35–17；
   这比同一实力带内部的细小排名更值得在实际判断中使用。

## 当前版本全部完整系列赛

每个系列只列一次；结果中的胜者放在前面，平局的左右顺序不表示强弱。本届 16 队用粗体表示。遇到
与本届队伍同名、但稳定队伍身份不同的历史记录，会标成“非本届队伍”，不会错误合并。

### 1win Essence II（28 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-08-05 | BO5 | **Team Liquid** 3–0 **Team Falcons** |
| 2026-08-05 | BO3 | **Team Liquid** 2–0 1w |
| 2026-08-05 | BO3 | 1w 2–1 **BoomBoys** |
| 2026-08-04 | BO3 | **Team Falcons** 2–0 **Team Liquid** |
| 2026-08-04 | BO3 | 1w 2–0 **Vici Gaming** |
| 2026-08-04 | BO3 | **BoomBoys** 2–1 **OG** |
| 2026-08-03 | BO3 | **Team Liquid** 2–1 **Vici Gaming** |
| 2026-08-03 | BO3 | **Team Falcons** 2–0 **BoomBoys** |
| 2026-08-03 | BO3 | **OG** 2–0 **GamerLegion** |
| 2026-08-03 | BO3 | 1w 2–0 **LGD Gaming** |
| 2026-08-02 | BO2 | **Vici Gaming** 2–0 **OG** |
| 2026-08-02 | BO2 | **Team Falcons** 2–0 1w |
| 2026-08-02 | BO2 | **GamerLegion** 2–0 MOUZ |
| 2026-08-02 | BO2 | **Nigma Galaxy** 1–1 **OG** |
| 2026-08-01 | BO2 | **Team Liquid** 2–0 **GamerLegion** |
| 2026-08-01 | BO2 | **OG** 2–0 **Team Falcons** |
| 2026-08-01 | BO2 | **BoomBoys** 2–0 **GamerLegion** |
| 2026-08-01 | BO2 | 1w 1–1 **OG** |
| 2026-08-01 | BO2 | **BoomBoys** 2–0 **LGD Gaming** |
| 2026-07-31 | BO2 | **Team Falcons** 2–0 **Nigma Galaxy** |
| 2026-07-31 | BO2 | **Team Liquid** 2–0 **BoomBoys** |
| 2026-07-31 | BO2 | 1w 1–1 **Vici Gaming** |
| 2026-07-31 | BO2 | **BoomBoys** 2–0 MOUZ |
| 2026-07-30 | BO2 | MOUZ 1–1 **Team Liquid** |
| 2026-07-30 | BO2 | **Team Falcons** 2–0 **Vici Gaming** |
| 2026-07-30 | BO2 | **Vici Gaming** 2–0 **Nigma Galaxy** |
| 2026-07-30 | BO2 | **LGD Gaming** 1–1 MOUZ |
| 2026-07-30 | BO2 | 1w 2–0 **Nigma Galaxy** |

### The Games of the Future 2026（3 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-08-03 | BO3 | Yakult Brothers 2–1 **Vici Gaming** |
| 2026-08-01 | BO3 | **Vici Gaming** 2–0 Yellow Submarine |
| 2026-07-31 | BO3 | **Vici Gaming** 2–1 Amaru Gaming |

### Esports World Cup 2026（60 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-07-19 | BO5 | PVISION 3–1 **BoomBoys** |
| 2026-07-19 | BO3 | **Team Yandex** 2–0 **Vici Gaming** |
| 2026-07-18 | BO3 | PVISION 2–1 **Team Yandex** |
| 2026-07-18 | BO3 | **BoomBoys** 2–0 **Vici Gaming** |
| 2026-07-17 | BO3 | **BoomBoys** 2–0 **Nigma Galaxy** |
| 2026-07-17 | BO3 | **Vici Gaming** 2–0 **Team Falcons** |
| 2026-07-16 | BO3 | **Team Yandex** 2–0 **Team Spirit** |
| 2026-07-15 | BO3 | **BoomBoys** 2–0 **LGD Gaming** |
| 2026-07-15 | BO3 | **Vici Gaming** 2–1 1w |
| 2026-07-15 | BO3 | **Team Spirit** 2–1 **Team Liquid** |
| 2026-07-15 | BO3 | Rune Eaters 2–0 **Aurora Gaming** |
| 2026-07-14 | BO3 | **LGD Gaming** 2–0 MOUZ |
| 2026-07-14 | BO3 | **Team Liquid** 2–1 **Xtreme Gaming** |
| 2026-07-12 | BO2 | Virtus.pro 2–0 **OG** |
| 2026-07-12 | BO2 | **LGD Gaming** 2–0 Inner Circle x Insanity |
| 2026-07-12 | BO2 | **Team Yandex** 2–0 1w |
| 2026-07-12 | BO2 | PVISION 1–1 **Team Spirit** |
| 2026-07-12 | BO2 | **Vici Gaming** 2–0 MOUZ |
| 2026-07-11 | BO2 | **Nigma Galaxy** 2–0 PTime |
| 2026-07-11 | BO2 | **Aurora Gaming** 1–1 **Team Liquid** |
| 2026-07-11 | BO2 | **Team Falcons** 2–0 **Xtreme Gaming** |
| 2026-07-11 | BO2 | **BoomBoys** 2–0 **GamerLegion** |
| 2026-07-10 | BO2 | **Team Yandex** 2–0 **LGD Gaming** |
| 2026-07-10 | BO2 | 1w 1–1 **OG** |
| 2026-07-10 | BO2 | **Team Spirit** 2–0 REKONIX |
| 2026-07-10 | BO2 | **Vici Gaming** 2–0 Team Nemesis |
| 2026-07-10 | BO2 | **Nigma Galaxy** 2–0 Level UP esports |
| 2026-07-10 | BO2 | **Aurora Gaming** 2–0 PTime |
| 2026-07-10 | BO2 | **Team Liquid** 2–0 L1 TEAM |
| 2026-07-10 | BO2 | **GamerLegion** 1–1 Rune Eaters |
| 2026-07-10 | BO2 | **BoomBoys** 2–0 **Xtreme Gaming** |
| 2026-07-10 | BO2 | **Team Falcons** 2–0 _PowerRangers |
| 2026-07-09 | BO2 | 1w 2–0 **LGD Gaming** |
| 2026-07-09 | BO2 | **Team Yandex** 2–0 Virtus.pro |
| 2026-07-09 | BO2 | **OG** 2–0 Inner Circle x Insanity |
| 2026-07-09 | BO2 | **Team Spirit** 2–0 **Vici Gaming** |
| 2026-07-09 | BO2 | **Nigma Galaxy** 2–0 **Team Liquid** |
| 2026-07-09 | BO2 | **Aurora Gaming** 2–0 L1 TEAM |
| 2026-07-09 | BO2 | **Team Falcons** 2–0 **GamerLegion** |
| 2026-07-09 | BO2 | **BoomBoys** 1–1 Rune Eaters |
| 2026-07-09 | BO2 | _PowerRangers 1–1 **Xtreme Gaming** |
| 2026-07-08 | BO2 | **Team Yandex** 2–0 Inner Circle x Insanity |
| 2026-07-08 | BO2 | **LGD Gaming** 2–0 **OG** |
| 2026-07-08 | BO2 | PVISION 2–0 **Vici Gaming** |
| 2026-07-08 | BO2 | **Team Spirit** 2–0 Team Nemesis |
| 2026-07-08 | BO2 | **Aurora Gaming** 1–1 **Nigma Galaxy** |
| 2026-07-08 | BO2 | **Team Liquid** 2–0 Level UP esports |
| 2026-07-08 | BO2 | **Xtreme Gaming** 2–0 **GamerLegion** |
| 2026-07-08 | BO2 | **Team Falcons** 2–0 Rune Eaters |
| 2026-07-08 | BO2 | **BoomBoys** 2–0 _PowerRangers |
| 2026-07-07 | BO2 | **OG** 1–1 **Team Yandex** |
| 2026-07-07 | BO2 | **LGD Gaming** 1–1 Virtus.pro |
| 2026-07-07 | BO2 | MOUZ 1–1 **Team Spirit** |
| 2026-07-07 | BO2 | **Vici Gaming** 2–0 REKONIX |
| 2026-07-07 | BO2 | **Aurora Gaming** 2–0 Level UP esports |
| 2026-07-07 | BO2 | PTime 1–1 **Team Liquid** |
| 2026-07-07 | BO2 | **Nigma Galaxy** 2–0 L1 TEAM |
| 2026-07-07 | BO2 | Rune Eaters 1–1 **Xtreme Gaming** |
| 2026-07-07 | BO2 | **BoomBoys** 1–1 **Team Falcons** |
| 2026-07-07 | BO2 | **GamerLegion** 2–0 _PowerRangers |

### The International 2026 - Regional Qualifier Europe（14 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-28 | BO3 | **Nigma Galaxy** 2–1 Yellow Submarine |
| 2026-06-28 | BO3 | **HULIGANI** 2–1 Virtus.pro |
| 2026-06-27 | BO3 | **HULIGANI** 2–1 Natus Vincere |
| 2026-06-26 | BO3 | **HULIGANI** 2–0 enjoy |
| 2026-06-25 | BO3 | **TEAM VISION** 2–1 Virtus.pro |
| 2026-06-25 | BO3 | **Team Spirit** 2–1 **Nigma Galaxy** |
| 2026-06-24 | BO3 | **TEAM VISION** 2–0 _PowerRangers |
| 2026-06-24 | BO3 | **HULIGANI** 2–1 RE ARISE |
| 2026-06-23 | BO3 | **Nigma Galaxy** 2–0 Natus Vincere |
| 2026-06-23 | BO3 | **Team Spirit** 2–0 enjoy |
| 2026-06-22 | BO3 | **TEAM VISION** 2–0 RE ARISE |
| 2026-06-22 | BO3 | _PowerRangers 2–1 **HULIGANI** |
| 2026-06-21 | BO3 | **Nigma Galaxy** 2–0 Rune Eaters |
| 2026-06-21 | BO3 | **Team Spirit** 2–0 VP.Prodigy |

### The International 2026 - Regional Qualifier North America（3 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-27 | BO5 | **GamerLegion** 3–0 4 Anchors + Ilmeria |
| 2026-06-26 | BO3 | **GamerLegion** 2–0 The Bug |
| 2026-06-25 | BO3 | **GamerLegion** 2–0 4 Anchors + Ilmeria |

### The International 2026 - Regional Qualifier Southeast Asia（4 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-23 | BO5 | **OG** 3–1 TEAM GRIND |
| 2026-06-22 | BO3 | **OG** 2–1 REKONIX |
| 2026-06-21 | BO3 | **OG** 2–0 GLYPH |
| 2026-06-20 | BO3 | **OG** 2–0 InterActive Philippines |

### The International 2026 - Regional Qualifier South America（4 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-19 | BO5 | **LGD Gaming** 3–0 PlayTime |
| 2026-06-19 | BO3 | **LGD Gaming** 2–1 PlayTime |
| 2026-06-17 | BO3 | **LGD Gaming** 2–0 Amaru Gaming |
| 2026-06-16 | BO3 | **LGD Gaming** 2–0 Lindorfitos |

### The International 2026 - Regional Qualifier China（8 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-18 | BO3 | **Vici Gaming** 2–1 Yakult Brothers |
| 2026-06-18 | BO3 | **Team Resilience** 2–0 Yakult Brothers |
| 2026-06-17 | BO3 | **Vici Gaming** 2–1 Team Refuser |
| 2026-06-17 | BO3 | **Vici Gaming** 2–0 Cloud Rising |
| 2026-06-16 | BO3 | Yakult Brothers 2–0 **Vici Gaming** |
| 2026-06-16 | BO3 | **Team Resilience** 2–0 Team Refuser |
| 2026-06-15 | BO3 | **Vici Gaming** 2–0 Grey Track |
| 2026-06-15 | BO3 | **Team Resilience** 2–0 Cloud Rising |

### BLAST SLAM VII（79 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-07 | BO5 | **Team Yandex** 3–1 **LGD Gaming** |
| 2026-06-07 | BO3 | **LGD Gaming** 2–1 **BoomBoys** |
| 2026-06-06 | BO3 | **LGD Gaming** 2–1 **Aurora Gaming** |
| 2026-06-06 | BO3 | **Team Yandex** 2–1 **BoomBoys** |
| 2026-06-05 | BO3 | **Aurora Gaming** 2–1 **Team Falcons** |
| 2026-06-05 | BO3 | **LGD Gaming** 2–0 **Team Liquid** |
| 2026-06-05 | BO3 | **BoomBoys** 2–0 **Team Falcons** |
| 2026-06-04 | BO3 | **Team Yandex** 2–1 **LGD Gaming** |
| 2026-06-04 | BO3 | **Team Falcons** 2–0 **Team Liquid** |
| 2026-06-04 | BO3 | **Team Yandex** 2–0 **Aurora Gaming** |
| 2026-05-30 | BO3 | **Aurora Gaming** 2–0 **Team Liquid** |
| 2026-05-30 | BO3 | **Team Yandex** 2–0 **Team Spirit** |
| 2026-05-30 | BO3 | **Aurora Gaming** 2–1 **Iron Wing** |
| 2026-05-30 | BO3 | **Team Spirit** 2–0 **OG** |
| 2026-05-29 | BO1 | **Team Liquid** 1–0 **OG** |
| 2026-05-29 | BO1 | **LGD Gaming** 1–0 **Iron Wing** |
| 2026-05-29 | BO1 | **BoomBoys** 1–0 GLYPH |
| 2026-05-29 | BO1 | PVISION 1–0 **Team Falcons** |
| 2026-05-29 | BO1 | **LGD Gaming** 1–0 **Team Yandex** |
| 2026-05-29 | BO1 | **Aurora Gaming** 1–0 **Xtreme Gaming** |
| 2026-05-29 | BO1 | **Iron Wing** 1–0 GLYPH |
| 2026-05-29 | BO1 | **Team Spirit** 1–0 **OG** |
| 2026-05-29 | BO1 | PVISION 1–0 **Team Liquid** |
| 2026-05-29 | BO1 | **BoomBoys** 1–0 **Team Falcons** |
| 2026-05-29 | BO1 | **LGD Gaming** 1–0 **Xtreme Gaming** |
| 2026-05-29 | BO1 | **Aurora Gaming** 1–0 **OG** |
| 2026-05-29 | BO1 | **Team Yandex** 1–0 GLYPH |
| 2026-05-29 | BO1 | **Team Spirit** 1–0 PVISION |
| 2026-05-29 | BO1 | **Team Liquid** 1–0 **Team Falcons** |
| 2026-05-29 | BO1 | **BoomBoys** 1–0 **Iron Wing** |
| 2026-05-28 | BO1 | **Xtreme Gaming** 1–0 GLYPH |
| 2026-05-28 | BO1 | **Team Spirit** 1–0 **Team Liquid** |
| 2026-05-28 | BO1 | PVISION 1–0 **Aurora Gaming** |
| 2026-05-28 | BO1 | **BoomBoys** 1–0 **Team Yandex** |
| 2026-05-28 | BO1 | **OG** 1–0 **LGD Gaming** |
| 2026-05-28 | BO1 | **Team Falcons** 1–0 **Iron Wing** |
| 2026-05-28 | BO1 | **Aurora Gaming** 1–0 **Team Yandex** |
| 2026-05-28 | BO1 | **Xtreme Gaming** 1–0 **Team Spirit** |
| 2026-05-28 | BO1 | **OG** 1–0 GLYPH |
| 2026-05-28 | BO1 | **LGD Gaming** 1–0 PVISION |
| 2026-05-28 | BO1 | **BoomBoys** 1–0 **Xtreme Gaming** |
| 2026-05-28 | BO1 | **Aurora Gaming** 1–0 **Team Liquid** |
| 2026-05-28 | BO1 | **Team Yandex** 1–0 **Iron Wing** |
| 2026-05-28 | BO1 | **Team Falcons** 1–0 **Team Spirit** |
| 2026-05-28 | BO1 | **BoomBoys** 1–0 **OG** |
| 2026-05-27 | BO1 | **Iron Wing** 1–0 **Xtreme Gaming** |
| 2026-05-27 | BO1 | **Team Liquid** 1–0 **LGD Gaming** |
| 2026-05-27 | BO1 | **Team Falcons** 1–0 **Team Yandex** |
| 2026-05-27 | BO1 | **Aurora Gaming** 1–0 **Team Spirit** |
| 2026-05-27 | BO1 | **Team Liquid** 1–0 GLYPH |
| 2026-05-27 | BO1 | PVISION 1–0 **BoomBoys** |
| 2026-05-27 | BO1 | **OG** 1–0 **Iron Wing** |
| 2026-05-27 | BO1 | **LGD Gaming** 1–0 **Team Spirit** |
| 2026-05-27 | BO1 | **Team Yandex** 1–0 **Xtreme Gaming** |
| 2026-05-27 | BO1 | **Team Falcons** 1–0 **Aurora Gaming** |
| 2026-05-27 | BO1 | **Team Liquid** 1–0 **BoomBoys** |
| 2026-05-27 | BO1 | PVISION 1–0 **Iron Wing** |
| 2026-05-27 | BO1 | **Team Yandex** 1–0 **OG** |
| 2026-05-27 | BO1 | **Team Spirit** 1–0 GLYPH |
| 2026-05-27 | BO1 | **LGD Gaming** 1–0 **Aurora Gaming** |
| 2026-05-27 | BO1 | **Team Falcons** 1–0 **Xtreme Gaming** |
| 2026-05-26 | BO1 | **BoomBoys** 1–0 **Team Spirit** |
| 2026-05-26 | BO1 | **Iron Wing** 1–0 **Team Liquid** |
| 2026-05-26 | BO1 | **Team Yandex** 1–0 PVISION |
| 2026-05-26 | BO1 | GLYPH 1–0 **Aurora Gaming** |
| 2026-05-26 | BO1 | **Team Falcons** 1–0 **LGD Gaming** |
| 2026-05-26 | BO1 | **Xtreme Gaming** 1–0 **OG** |
| 2026-05-26 | BO1 | **Team Yandex** 1–0 **Team Liquid** |
| 2026-05-26 | BO1 | **Team Spirit** 1–0 **Iron Wing** |
| 2026-05-26 | BO1 | **BoomBoys** 1–0 **Aurora Gaming** |
| 2026-05-26 | BO1 | PVISION 1–0 **Xtreme Gaming** |
| 2026-05-26 | BO1 | **LGD Gaming** 1–0 GLYPH |
| 2026-05-26 | BO1 | **Team Falcons** 1–0 **OG** |
| 2026-05-26 | BO1 | **Team Yandex** 1–0 **Team Spirit** |
| 2026-05-26 | BO1 | **Aurora Gaming** 1–0 **Iron Wing** |
| 2026-05-26 | BO1 | **Team Liquid** 1–0 **Xtreme Gaming** |
| 2026-05-26 | BO1 | **LGD Gaming** 1–0 **BoomBoys** |
| 2026-05-26 | BO1 | PVISION 1–0 **OG** |
| 2026-05-26 | BO1 | GLYPH 1–0 **Team Falcons** |

### Road To EWC 2026 Regional Qualifiers（10 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-06-04 | BO5 | **GamerLegion** 3–0 IGNITE |
| 2026-06-03 | BO3 | **GamerLegion** 2–0 Stormrage |
| 2026-06-03 | BO5 | **Nigma Galaxy** 3–0 K.O. |
| 2026-06-03 | BO3 | **HULIGANI** 2–1 enjoy |
| 2026-06-02 | BO3 | Poor Rangers 2–0 **HULIGANI** |
| 2026-06-02 | BO3 | **Nigma Galaxy** 2–0 sifr00 |
| 2026-06-02 | BO3 | **LGD Gaming** 2–1 Natus Vincere |
| 2026-06-02 | BO3 | **Nigma Galaxy** 2–0 K.O. |
| 2026-06-01 | BO3 | **HULIGANI** 2–0 Inner Circle x Insanity |
| 2026-05-31 | BO3 | **LGD Gaming** 2–0 BALU TEAM |

### DreamLeague Season 29（68 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-05-24 | BO5 | **TEAM VISION** 3–2 **Aurora Gaming** |
| 2026-05-24 | BO3 | **Aurora Gaming** 2–0 **Team Spirit** |
| 2026-05-23 | BO3 | **Aurora Gaming** 2–0 **Team Falcons** |
| 2026-05-23 | BO3 | **TEAM VISION** 2–1 **Team Spirit** |
| 2026-05-23 | BO3 | **Team Falcons** 2–0 PlayTime |
| 2026-05-22 | BO3 | **Aurora Gaming** 2–0 **Iron Wing** |
| 2026-05-22 | BO3 | PlayTime 2–1 **BoomBoys** |
| 2026-05-22 | BO3 | **Iron Wing** 2–1 **Xtreme Gaming** |
| 2026-05-21 | BO3 | **Team Spirit** 2–1 **Aurora Gaming** |
| 2026-05-21 | BO3 | **TEAM VISION** 2–1 **Team Falcons** |
| 2026-05-20 | BO3 | **Xtreme Gaming** 2–1 **Team Liquid** |
| 2026-05-20 | BO3 | **BoomBoys** 2–1 **Vici Gaming** |
| 2026-05-20 | BO3 | **Iron Wing** 2–1 Virtus.pro |
| 2026-05-19 | BO3 | **Aurora Gaming** 2–1 Natus Vincere |
| 2026-05-19 | BO3 | **TEAM VISION** 2–1 **Team Liquid** |
| 2026-05-19 | BO3 | **Team Spirit** 2–0 **BoomBoys** |
| 2026-05-19 | BO3 | **Team Falcons** 2–0 **Iron Wing** |
| 2026-05-18 | BO1 | Tundra Esports 1–0 **Xtreme Gaming** |
| 2026-05-18 | BO1 | PlayTime 1–0 **Xtreme Gaming** |
| 2026-05-17 | BO3 | **TEAM VISION** 2–1 REKONIX |
| 2026-05-17 | BO3 | **BoomBoys** 2–0 **Nigma Galaxy** |
| 2026-05-17 | BO3 | Natus Vincere 2–0 **Xtreme Gaming** |
| 2026-05-17 | BO3 | **Team Falcons** 2–1 **GamerLegion** |
| 2026-05-17 | BO3 | **Aurora Gaming** 2–1 Virtus.pro |
| 2026-05-17 | BO3 | **Team Liquid** 2–1 **Vici Gaming** |
| 2026-05-17 | BO3 | **Team Spirit** 2–0 ex-HEROIC |
| 2026-05-16 | BO3 | PlayTime 2–1 **TEAM VISION** |
| 2026-05-16 | BO3 | **BoomBoys** 2–0 **Xtreme Gaming** |
| 2026-05-16 | BO3 | **Nigma Galaxy** 2–0 REKONIX |
| 2026-05-16 | BO3 | **Team Falcons** 2–1 **Team Spirit** |
| 2026-05-16 | BO3 | **Aurora Gaming** 2–1 **Vici Gaming** |
| 2026-05-16 | BO3 | **GamerLegion** 2–1 Virtus.pro |
| 2026-05-16 | BO3 | **Team Liquid** 2–0 ex-HEROIC |
| 2026-05-16 | BO3 | Tundra Esports 2–1 **BoomBoys** |
| 2026-05-16 | BO3 | **Xtreme Gaming** 2–0 REKONIX |
| 2026-05-16 | BO3 | **TEAM VISION** 2–0 **Nigma Galaxy** |
| 2026-05-15 | BO3 | **Vici Gaming** 2–0 ex-HEROIC |
| 2026-05-15 | BO3 | **Aurora Gaming** 2–0 **GamerLegion** |
| 2026-05-15 | BO3 | **Team Falcons** 2–0 **Team Liquid** |
| 2026-05-15 | BO3 | **Team Spirit** 2–0 Virtus.pro |
| 2026-05-15 | BO3 | **BoomBoys** 2–1 PlayTime |
| 2026-05-15 | BO3 | **TEAM VISION** 2–0 Natus Vincere |
| 2026-05-15 | BO3 | **Nigma Galaxy** 2–0 **Xtreme Gaming** |
| 2026-05-15 | BO3 | **Team Spirit** 2–0 **GamerLegion** |
| 2026-05-15 | BO3 | **Team Falcons** 2–0 **Vici Gaming** |
| 2026-05-15 | BO3 | **Team Liquid** 2–0 Virtus.pro |
| 2026-05-15 | BO3 | **Aurora Gaming** 2–0 ex-HEROIC |
| 2026-05-14 | BO3 | **TEAM VISION** 2–1 **Xtreme Gaming** |
| 2026-05-14 | BO3 | Tundra Esports 2–1 **Nigma Galaxy** |
| 2026-05-14 | BO3 | Natus Vincere 2–0 **BoomBoys** |
| 2026-05-14 | BO3 | **Team Liquid** 2–0 **GamerLegion** |
| 2026-05-14 | BO3 | **Team Falcons** 2–0 ex-HEROIC |
| 2026-05-14 | BO3 | Virtus.pro 2–0 **Vici Gaming** |
| 2026-05-14 | BO3 | **Team Spirit** 2–0 **Aurora Gaming** |
| 2026-05-14 | BO3 | **TEAM VISION** 2–1 **BoomBoys** |
| 2026-05-14 | BO3 | PlayTime 2–0 **Nigma Galaxy** |
| 2026-05-14 | BO3 | **Xtreme Gaming** 2–0 Tundra Esports |
| 2026-05-13 | BO3 | **Team Spirit** 2–1 **Team Liquid** |
| 2026-05-13 | BO3 | **Team Falcons** 2–0 **Aurora Gaming** |
| 2026-05-13 | BO3 | **Vici Gaming** 2–0 **GamerLegion** |
| 2026-05-13 | BO3 | **Xtreme Gaming** 2–0 PlayTime |
| 2026-05-13 | BO3 | **TEAM VISION** 2–1 Tundra Esports |
| 2026-05-13 | BO3 | Natus Vincere 2–0 **Nigma Galaxy** |
| 2026-05-13 | BO3 | **BoomBoys** 2–0 REKONIX |
| 2026-05-13 | BO3 | **Team Falcons** 2–1 Virtus.pro |
| 2026-05-13 | BO3 | **Team Liquid** 2–1 **Aurora Gaming** |
| 2026-05-13 | BO3 | ex-HEROIC 2–0 **GamerLegion** |
| 2026-05-13 | BO3 | **Team Spirit** 2–0 **Vici Gaming** |

### ESL challenger China powered By ACL（12 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-05-03 | BO5 | **Vici Gaming** 3–1 **Team Resilience** |
| 2026-05-03 | BO3 | **Vici Gaming** 2–1 **Xtreme Gaming** |
| 2026-05-02 | BO3 | **Vici Gaming** 2–1 Yakult Brothers |
| 2026-05-02 | BO3 | **Team Resilience** 2–0 **Xtreme Gaming** |
| 2026-05-02 | BO3 | **Vici Gaming** 2–0 Roar |
| 2026-05-01 | BO3 | **Team Resilience** 2–0 **Vici Gaming** |
| 2026-05-01 | BO3 | **Xtreme Gaming** 2–0 Yakult Brothers |
| 2026-05-01 | BO1 | **Team Resilience** 1–0 Team Refuser |
| 2026-05-01 | BO1 | **Vici Gaming** 1–0 Cloud Dawning |
| 2026-05-01 | BO1 | **Xtreme Gaming** 1–0 Roar |
| 2026-04-19 | BO1 | **Team Resilience** 1–0 Cloud Dawning |
| 2026-04-19 | BO3 | **Team Resilience** 2–1 Mideng dreamer |

### PGL Wallachia 2026 Season 8（40 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-04-26 | BO5 | **BoomBoys** 3–0 **Aurora Gaming** |
| 2026-04-26 | BO3 | **Aurora Gaming** 2–0 **Team Falcons** |
| 2026-04-25 | BO3 | **Team Falcons** 2–1 **Team Liquid** |
| 2026-04-25 | BO3 | **BoomBoys** 2–1 **Aurora Gaming** |
| 2026-04-25 | BO3 | **Team Liquid** 2–0 SouthAmericaRejects |
| 2026-04-25 | BO3 | **Team Falcons** 2–0 **TEAM VISION** |
| 2026-04-24 | BO3 | **BoomBoys** 2–1 **Team Liquid** |
| 2026-04-24 | BO3 | **Aurora Gaming** 2–1 **TEAM VISION** |
| 2026-04-24 | BO3 | **Team Falcons** 2–0 **Team Spirit** |
| 2026-04-23 | BO3 | **BoomBoys** 2–0 **Team Spirit** |
| 2026-04-23 | BO3 | **Team Liquid** 2–0 **Team Falcons** |
| 2026-04-23 | BO3 | **Aurora Gaming** 2–0 HEROIC |
| 2026-04-23 | BO3 | **TEAM VISION** 2–1 SouthAmericaRejects |
| 2026-04-22 | BO3 | **Team Spirit** 2–0 **Xtreme Gaming** |
| 2026-04-22 | BO3 | HEROIC 2–0 **GamerLegion** |
| 2026-04-21 | BO3 | **TEAM VISION** 2–1 SouthAmericaRejects |
| 2026-04-21 | BO3 | **Xtreme Gaming** 2–0 **Vici Gaming** |
| 2026-04-21 | BO3 | **Team Falcons** 2–0 **GamerLegion** |
| 2026-04-21 | BO3 | **Team Spirit** 2–1 Natus Vincere |
| 2026-04-21 | BO3 | **Team Liquid** 2–0 HEROIC |
| 2026-04-20 | BO3 | **Aurora Gaming** 2–1 **TEAM VISION** |
| 2026-04-20 | BO3 | Natus Vincere 2–1 **Team Yandex** |
| 2026-04-20 | BO3 | **BoomBoys** 2–1 **Team Falcons** |
| 2026-04-20 | BO3 | SouthAmericaRejects 2–1 **Xtreme Gaming** |
| 2026-04-20 | BO3 | **Team Liquid** 2–1 **Vici Gaming** |
| 2026-04-20 | BO3 | **GamerLegion** 2–0 **Team Spirit** |
| 2026-04-19 | BO3 | **TEAM VISION** 2–0 HEROIC |
| 2026-04-19 | BO3 | **Team Falcons** 2–1 **Team Spirit** |
| 2026-04-19 | BO3 | SouthAmericaRejects 2–0 **Team Yandex** |
| 2026-04-19 | BO3 | **GamerLegion** 2–0 MOUZ |
| 2026-04-19 | BO3 | **BoomBoys** 2–0 **Team Liquid** |
| 2026-04-19 | BO3 | **Vici Gaming** 2–1 Natus Vincere |
| 2026-04-19 | BO3 | **Aurora Gaming** 2–1 **Xtreme Gaming** |
| 2026-04-18 | BO3 | **Team Falcons** 2–0 **Team Yandex** |
| 2026-04-18 | BO3 | **BoomBoys** 2–0 Virtus.pro |
| 2026-04-18 | BO3 | **TEAM VISION** 2–0 MOUZ |
| 2026-04-18 | BO3 | **Aurora Gaming** 2–1 SouthAmericaRejects |
| 2026-04-18 | BO3 | **Team Liquid** 2–1 **GamerLegion** |
| 2026-04-18 | BO3 | **Team Spirit** 2–1 **Vici Gaming** |
| 2026-04-18 | BO3 | **Xtreme Gaming** 2–0 Natus Vincere |

### DreamLeague Season 29 Qualifiers（20 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-04-14 | BO5 | **GamerLegion** 3–0 Amaru Gaming |
| 2026-04-14 | BO5 | **BoomBoys** 3–1 L1GA TEAM |
| 2026-04-14 | BO3 | **Team Liquid** 2–1 MOUZ |
| 2026-04-14 | BO3 | **BoomBoys** 2–1 Nemiga Gaming |
| 2026-04-14 | BO3 | **Team Liquid** 2–0 Team Lynx |
| 2026-04-14 | BO5 | **Vici Gaming** 3–0 Roar |
| 2026-04-14 | BO3 | Roar 2–0 **Team Resilience** |
| 2026-04-13 | BO3 | **BoomBoys** 2–0 _PowerRangers |
| 2026-04-13 | BO3 | **GamerLegion** 2–0 Amaru Gaming |
| 2026-04-13 | BO3 | **BoomBoys** 2–0 enjoy |
| 2026-04-13 | BO3 | **Vici Gaming** 2–0 **Team Resilience** |
| 2026-04-13 | BO3 | **BoomBoys** 2–0 Rune Eaters |
| 2026-04-13 | BO3 | REKONIX 2–0 **OG** |
| 2026-04-12 | BO3 | Natus Vincere 2–1 **Team Liquid** |
| 2026-04-12 | BO3 | **Team Resilience** 2–0 Cloud Dawning |
| 2026-04-12 | BO3 | Ivory 2–0 **OG** |
| 2026-04-12 | BO3 | **Vici Gaming** 2–0 Mideng dreamer |
| 2026-04-12 | BO3 | Breeki Cheeki 2–1 **BoomBoys** |
| 2026-04-12 | BO3 | **OG** 2–0 GLYPH |
| 2026-04-12 | BO3 | **Team Resilience** 2–0 Cloud Rising |

### Premier Series（15 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-04-11 | BO5 | **TEAM VISION** 3–0 Nigma Galaxy（非本届队伍） |
| 2026-04-10 | BO3 | Nigma Galaxy（非本届队伍） 2–1 **GamerLegion** |
| 2026-04-10 | BO3 | **TEAM VISION** 2–0 MOUZ |
| 2026-04-10 | BO3 | **GamerLegion** 2–1 L1GA TEAM |
| 2026-04-10 | BO3 | Nigma Galaxy（非本届队伍） 2–1 **Team Liquid** |
| 2026-04-09 | BO3 | **Team Liquid** 2–0 HEROIC |
| 2026-04-09 | BO3 | **TEAM VISION** 2–0 Nigma Galaxy（非本届队伍） |
| 2026-04-09 | BO3 | **GamerLegion** 2–1 **Team Spirit** |
| 2026-04-08 | BO3 | L1GA TEAM 2–1 **Team Liquid** |
| 2026-04-08 | BO3 | Nigma Galaxy（非本届队伍） 2–1 **Team Spirit** |
| 2026-04-08 | BO3 | **TEAM VISION** 2–0 **GamerLegion** |
| 2026-04-07 | BO3 | **GamerLegion** 2–1 enjoy |
| 2026-04-06 | BO3 | **GamerLegion** 2–0 Yellow Submarine |
| 2026-04-06 | BO3 | **GamerLegion** 2–1 VP.Prodigy |
| 2026-04-04 | BO3 | **GamerLegion** 2–0 Zero Tenacity |

### RES Unchained - A Blast Dota Slam VII Qualifier EU（4 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-04-03 | BO3 | **TEAM VISION** 2–0 Natus Vincere |
| 2026-04-03 | BO3 | **Aurora Gaming** 2–1 enjoy |
| 2026-04-02 | BO3 | **TEAM VISION** 2–0 Virtus.pro |
| 2026-04-02 | BO3 | **Aurora Gaming** 2–1 Team Lynx |

### BLAST Slam VII China Qualifier（5 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-04-03 | BO3 | **Xtreme Gaming** 2–0 Yakult Brothers |
| 2026-04-03 | BO3 | Yakult Brothers 2–1 **Vici Gaming** |
| 2026-04-03 | BO3 | **Xtreme Gaming** 2–0 Roar |
| 2026-04-02 | BO3 | **Xtreme Gaming** 2–0 Cloud Rising |
| 2026-04-02 | BO3 | **Vici Gaming** 2–0 Cloud Dawning |

### ESL One Birmingham 2026（32 个系列）

| 日期（UTC） | 赛制 | 结果 |
| --- | --- | --- |
| 2026-03-29 | BO5 | Tundra Esports 3–1 **Team Yandex** |
| 2026-03-29 | BO3 | **Team Yandex** 2–1 **Xtreme Gaming** |
| 2026-03-28 | BO3 | **Xtreme Gaming** 2–1 **TEAM VISION** |
| 2026-03-28 | BO3 | Tundra Esports 2–0 **Team Yandex** |
| 2026-03-28 | BO3 | **TEAM VISION** 2–0 **Aurora Gaming** |
| 2026-03-27 | BO3 | **Xtreme Gaming** 2–1 **Team Spirit** |
| 2026-03-27 | BO3 | **TEAM VISION** 2–0 **Team Falcons** |
| 2026-03-27 | BO3 | **Xtreme Gaming** 2–1 MOUZ |
| 2026-03-26 | BO3 | Tundra Esports 2–1 **Aurora Gaming** |
| 2026-03-26 | BO3 | **Team Yandex** 2–1 **Team Spirit** |
| 2026-03-25 | BO1 | **TEAM VISION** 1–0 **BoomBoys** |
| 2026-03-25 | BO1 | **TEAM VISION** 1–0 **GamerLegion** |
| 2026-03-25 | BO2 | **Aurora Gaming** 2–0 paiN Gaming |
| 2026-03-25 | BO2 | **Team Falcons** 2–0 Virtus.pro |
| 2026-03-25 | BO2 | **Xtreme Gaming** 2–0 **OG** |
| 2026-03-25 | BO2 | **Team Spirit** 2–0 Nigma Galaxy（非本届队伍） |
| 2026-03-25 | BO2 | **BoomBoys** 2–0 **GamerLegion** |
| 2026-03-25 | BO2 | **Team Yandex** 2–0 MOUZ |
| 2026-03-25 | BO2 | **TEAM VISION** 2–0 Yakult Brothers |
| 2026-03-24 | BO2 | **OG** 1–1 **Team Falcons** |
| 2026-03-24 | BO2 | **Team Spirit** 2–0 **Xtreme Gaming** |
| 2026-03-24 | BO2 | **Aurora Gaming** 2–0 Virtus.pro |
| 2026-03-24 | BO2 | paiN Gaming 1–1 **Team Falcons** |
| 2026-03-24 | BO2 | **Team Spirit** 2–0 Virtus.pro |
| 2026-03-24 | BO2 | **Aurora Gaming** 2–0 **OG** |
| 2026-03-24 | BO2 | Nigma Galaxy（非本届队伍） 1–1 **Xtreme Gaming** |
| 2026-03-24 | BO2 | **Team Yandex** 2–0 **BoomBoys** |
| 2026-03-24 | BO2 | MOUZ 2–0 **TEAM VISION** |
| 2026-03-24 | BO2 | **GamerLegion** 2–0 REKONIX |
| 2026-03-24 | BO2 | **BoomBoys** 2–0 Yakult Brothers |
| 2026-03-24 | BO2 | **Team Yandex** 2–0 **GamerLegion** |
| 2026-03-24 | BO2 | **TEAM VISION** 2–0 REKONIX |

## 没有冒充成完整系列的 5 个单局片段

下面五局都是真实可用的单局赛果，正式强度模型会按 Game 使用；但当前目录无法证明它们组成了
怎样的完整 BO3，所以不进入上面的 Series 汇总。Team Resilience 的两局对手虽然显示同名，
上游稳定身份不同，也不能为了凑成 2–0 而强行合并。

| 日期（UTC） | 已观测单局 | 为什么不计完整系列 |
| --- | --- | --- |
| 2026-04-09 | **Team Resilience** 1–0 Mideng dreamer | 只有一局；同名对手之一。 |
| 2026-04-09 | **Team Resilience** 1–0 Mideng dreamer | 只有一局；另一稳定队伍身份。 |
| 2026-04-12 | **Team Liquid** 1–0 ALIS VENTORUS | BO3 目录只有一局。 |
| 2026-05-31 | **LGD Gaming** 1–0 Pipsqueak + 4 | BO3 目录只有一局。 |
| 2026-06-03 | **GamerLegion** 1–0 IGNITE | BO3 目录只有一局。 |

## 最后怎样使用这份文件

- 想看“谁整体更强”：看最终预测里的五个实力带；
- 想看“模型为什么认为两队接近”：先看本页直接交手是否充足，再看共同对手网络；
- 想核对某个具体赛果：在下方账本中搜索队名；
- 想填游戏内槽位：仍以最终预测的填写表为准，不按原始系列胜率机械排序。

409 个完整系列中有 12 个因上游系列编号缺失或拆分而恢复；恢复只在同赛事、同一稳定队伍对、
连续比赛时间和合法终局比分同时成立时进行。详细规则与逐项验收见
[Series 发布扩展实施记录](../../../reports/ti2026-group-series-evidence-implementation-2026-08-08.md)。
