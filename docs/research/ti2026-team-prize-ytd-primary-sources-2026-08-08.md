# TI 2026 当前 16 队：2026 年赛事获奖额调查

- 研究截止：2026-08-08T14:37:14Z
- 状态：研究账本；可用于正式实现前的来源审计
- 主口径：当前组织在 2026 年已结束、且有明确现金分配的赛事中获得的完整参赛方名义奖金

## 结论

当前 16 队合计公开名义获奖额为 **US$8,204,268.51**，来自 **122 条**可逐项核对的付费赛事记录。这个数字不是赛事总奖池之和，也不是根据名次猜出来的分配。

“完整参赛方奖金”指：若赛事把金额拆成 Player Prize Money 与 Club/Team Reward，本报告把两项相加。它比只统计选手份额的常见队伍成绩页更高，但更符合“这支队伍/组织在赛事中斩获了多少”的问题。个人 MVP 奖不进入队伍合计。

公开资料通常只能证明赛事授予了这笔奖金，不能证明款项已经进入银行账户。因此正式发布时应写“公开获奖额”或“名义奖金”，不能写“已到账奖金”。

## 16 队合计

| 排名 | 当前显示队名 | stable team_id | 付费赛事数 | 2026 累计（USD） |
| ---: | --- | ---: | ---: | ---: |
| 1 | TEAM VISION | 9572001 | 8 | 1,365,000 |
| 2 | Team Yandex | 9823272 | 8 | 1,177,500 |
| 3 | Team Liquid | 2163 | 10 | 1,002,500 |
| 4 | BoomBoys | 8255888 | 9 | 985,500 |
| 5 | Aurora Gaming | 9467224 | 9 | 777,000 |
| 6 | Team Falcons | 9247354 | 9 | 540,000 |
| 7 | Team Spirit | 7119388 | 9 | 501,250 |
| 8 | Xtreme Gaming | 8261500 | 11 | 461,250 |
| 9 | Vici Gaming | 726228 | 8 | 347,000 |
| 10 | LGD Gaming | 10150538 | 3 | 237,500 |
| 11 | OG | 2586976 | 7 | 185,000 |
| 12 | Team Resilience | 5017210 | 3 | 166,000 |
| 13 | Nigma Galaxy | 10136357 | 7 | 165,000 |
| 14 | GamerLegion | 9964962 | 8 | 143,250 |
| 15 | Iron Wing | 10150413 | 6 | 108,500 |
| 16 | HULIGANI | 10149530 | 7 | 42,018.51 |

直接以 USD 公布的记录合计 **US$8,201,250**；唯一跨币种记录是 HULIGANI/L1GA TEAM 在 Esports League Super Cup Pro Division 的 250,000 RUB，明细页按 2026-03-21 汇率列为 **US$3,018.51**。

## 本轮关键纠错

- 补入 Team Spirit 在 DreamLeague Season 28 的 11–12 名：Player Prize Money US$17,500 + Club Reward US$10,000 = US$27,500。
- 补入 GamerLegion 在 PGL Wallachia Season 8 的 9–11 名：US$20,000。
- 排除 Games of the Future 2026 的 LGD.Pinghu 5–8 名 US$35,000。其稳定 team_id 为 10208068，不是当前 LGD Gaming 的 10150538；不能只因名称含 LGD 就合并。

修正后的净变化是 +27,500 +20,000 −35,000 = +12,500；总账由旧草案的 US$8,191,768.51 修正为 US$8,204,268.51。

## 计算与纳入规则

1. 只统计 2026-01-01 至 as_of 之间已经结束的赛事。
2. 只有来源明确列出该队名次与现金金额的记录才能进入账本；不从赛事总奖池、Tier 或名次自行推算。
3. 现金资格赛可以纳入；只有晋级名额而没有现金的资格赛排除。Team Resilience 的 ESL Challenger China S3 Open Qualifier 1 因为资格赛本身明确支付 US$6,000，所以纳入。
4. DreamLeague、BLAST、ESL One 等赛事若拆分选手奖金与 Club/Team Reward，按两项之和统计。
5. 个人奖排除。EWC 2026 的 US$25,000 MVP 奖属于个人，不进入 TEAM VISION 的队伍合计。
6. 名称只用于显示，主连接键是 config/ti2026.yaml 中的稳定 team_id。event_id 是本研究账本的稳定事件 slug，不声称是主办方官方 ID。
7. 表中 Tier 是来源页的社区赛事档位，不是 OpenDota league tier，也不参与金额计算。

## 身份口径与转会敏感性

主排名按当前组织口径：同一组织改名继续累计；选手或整套阵容转会到新组织时，旧组织此前的奖金不会随阵容转移。这样不会因为当前五人曾为另一支组织比赛，就把旧东家的奖金记到新东家名下。

| 当前目标 | 主口径：当前组织 | 当前阵容谱系的对照值 | 差异与处理 |
| --- | ---: | ---: | --- |
| Iron Wing / 1w Team | 108,500 | 816,250 | 1w 旧阵容在转会前贡献 46,000；当前五人转会后贡献 62,500。若沿当前五人向前追溯 Tundra，则另有 753,750，替换掉 1w 旧阵容的 46,000，故比主口径高 707,750。主排名不把 Tundra 奖金转给 1w。 |
| LGD Gaming | 237,500 | 410,000 | 当前阵容加入 LGD 后贡献 237,500；若沿阵容谱系追溯 HEROIC/ex-HEROIC，需再加 172,500，故比主口径高 172,500。主排名不把 HEROIC 奖金转给 LGD，也不合并独立的 LGD.Pinghu。 |

[Tundra Esports 记录](https://liquipedia.net/dota2/Tundra_Esports)显示 Pure、bzm、33、Ari、Whitemon 的阵容于 2026-06-01 转到 1w；[1w Team 记录](https://liquipedia.net/dota2/1w_Team)同时显示原 1w 阵容转到 Enjoy。Tundra 谱系的 US$753,750 由 BLAST Slam VI 28,750、DreamLeague 28 290,000、PGL Wallachia 7 60,000、ESL One Birmingham 290,000、PGL Wallachia 8 10,000、DreamLeague 29 55,000、BLAST Slam VII 20,000 构成。BLAST Slam VII 仍以 Tundra 名义列账，且公开资料未证明奖金许可证转给 1w，因此在当前组织主口径中保守排除。

[LGD Gaming 记录](https://liquipedia.net/dota2/LGD_Gaming)显示现阵容于 2026-05-25 加入 LGD。其转会前 HEROIC/ex-HEROIC 的 US$172,500 由 BLAST Slam VI 50,000、PGL Wallachia 7 60,000、PGL Wallachia 8 40,000、DreamLeague 29 22,500 构成；可由 [HEROIC 结果页](https://liquipedia.net/dota2/HEROIC/Results)与各赛事页核对。

其余显示名映射中，BoomBoys 对应同一组织的 BetBoom Team/BB Team，TEAM VISION 对应 PARIVISION，HULIGANI 对应 L1GA TEAM；这些是同一组织/标签链，纳入全年组织累计，不因赛事显示名不同而拆开。

## 来源等级与可信度

| 标记 | 含义 | 可接受的结论 |
| --- | --- | --- |
| 高 | 官方规则明确分配金额，社区明细页用于把队伍映射到最终名次 | 金额表可信度高；队伍映射仍需社区结果页交叉核对 |
| 中高 | 官方赛果可核对，历史奖金分配来自明确明细页 | 可用于研究合计；仍缺主办方旧版分配快照 |
| 中 | 社区赛事页明确逐队列出名次和金额；部分赛事另有官方赛事页但没有官方逐队分配 | 可用于发布版的“公开统计”，不应声称全为官方审计数字 |
| 中低 | 原币金额明确，但 USD 数字经过社区页面汇率折算 | 原币获奖额可信；美元累计受汇率口径影响 |

EWC 2026 与 BLAST Slam VII 的分配可由第一方规则书核对；BLAST Slam VI 的官方赛果可核对，但同一规则书 URL 后来更新为 Slam VII 版本，因此历史分配保留为中高。PGL、DreamLeague/ESL、1win Essence、FISSURE、CCT、PREMIER SERIES 与 Games of the Future 等项目在本次截止前没有找到可用的第一方逐队最终付款表，账本使用明确列出名次和分配的赛事明细页。

高可信条目与中高可信 BLAST Slam VI 条目合计 US$3,491,250，占总账约 42.55%；其余条目都有明确逐项金额，但来源层级主要是社区赛事明细，因此整份报告不能称为“全部官方来源完全确认”。

## 完整逐笔账本

金额列均为 USD；若赛事拆分选手奖金与俱乐部奖励，已经相加。表中“明细”直接打开逐队分配，“核验”打开可用的第一方规则或赛事页。

| 当前队名（必要时含赛事显示名） | stable team_id | event_id / 赛事 | 结束日 | 名次 | 金额 USD | Tier | 来源类型 / 可信度 | 核验说明 |
| --- | ---: | --- | --- | --- | ---: | --- | --- | --- |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 1st | 750,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 7th-8th | 35,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 1st | 290,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | 1win-essence-1<br>1win Essence I | 2026-05-11 | 1st | 50,000 | Tier 2 | [明细](https://liquipedia.net/dota2/1win_Essence/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 5th-6th | 60,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | premier-series-1<br>PREMIER SERIES | 2026-04-11 | 1st | 50,000 | Tier 2 | [明细](https://liquipedia.net/dota2/NarodCast/PREMIER_SERIES/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| TEAM VISION（赛事名：PARIVISION） | 9572001 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 6th | 50,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Yandex | 9823272 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 3rd | 200,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Yandex | 9823272 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 1st | 400,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Yandex | 9823272 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 15th-16th | 10,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Yandex | 9823272 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 2nd | 130,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Yandex | 9823272 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 1st | 300,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Yandex | 9823272 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 11th-12th | 27,500 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Yandex | 9823272 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 3rd-4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Team Yandex | 9823272 | fissure-universe-8<br>FISSURE Universe: Episode 8 | 2026-02-01 | 3rd | 30,000 | Tier 2 | [明细](https://liquipedia.net/dota2/FISSURE/Universe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Liquid | 2163 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 1st | 100,000 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Liquid | 2163 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 9th-12th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Liquid | 2163 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 5th-6th | 55,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Liquid | 2163 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 9th-12th | 30,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Liquid | 2163 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Liquid | 2163 | premier-series-1<br>PREMIER SERIES | 2026-04-11 | 5th-6th | 2,500 | Tier 2 | [明细](https://liquipedia.net/dota2/NarodCast/PREMIER_SERIES/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Liquid | 2163 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 2nd | 175,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Liquid | 2163 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 3rd | 105,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Liquid | 2163 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 1st | 400,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Team Liquid | 2163 | fissure-universe-8<br>FISSURE Universe: Episode 8 | 2026-02-01 | 4th | 15,000 | Tier 2 | [明细](https://liquipedia.net/dota2/FISSURE/Universe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 4th | 12,500 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 2nd | 340,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 3rd | 93,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 7th-8th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 1st | 300,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 11th-12th | 27,500 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 3rd | 120,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 7th | 42,500 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| BoomBoys（赛事名：BetBoom Team） | 8255888 | fissure-universe-8<br>FISSURE Universe: Episode 8 | 2026-02-01 | 5th-6th | 10,000 | Tier 2 | [明细](https://liquipedia.net/dota2/FISSURE/Universe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Aurora Gaming | 9467224 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 9th-12th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Aurora Gaming | 9467224 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 4th | 67,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Aurora Gaming | 9467224 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 2nd | 130,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Aurora Gaming | 9467224 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 2nd | 175,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Aurora Gaming | 9467224 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 5th-6th | 55,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Aurora Gaming | 9467224 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 7th-8th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Aurora Gaming | 9467224 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 2nd | 130,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Aurora Gaming | 9467224 | dreamleague-division-2-3<br>DreamLeague Division 2 Season 3 | 2026-02-12 | 1st | 15,000 | Tier 2 | [明细](https://liquipedia.net/dota2/DreamLeague/Division_2/3)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Aurora Gaming | 9467224 | fissure-universe-8<br>FISSURE Universe: Episode 8 | 2026-02-01 | 1st | 125,000 | Tier 2 | [明细](https://liquipedia.net/dota2/FISSURE/Universe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Falcons | 9247354 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 2nd | 50,000 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Falcons | 9247354 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 5th-8th | 70,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Falcons | 9247354 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 5th-6th | 55,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Falcons | 9247354 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Falcons | 9247354 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 3rd | 120,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Falcons | 9247354 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 7th-8th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Falcons | 9247354 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 12th-14th | 15,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Falcons | 9247354 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 5th | 60,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Falcons | 9247354 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 5th-6th | 50,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Team Spirit | 7119388 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 5th-8th | 70,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Spirit | 7119388 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 7th-8th | 35,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Team Spirit | 7119388 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 3rd | 105,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Spirit | 7119388 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 7th-8th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Spirit | 7119388 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 5th-6th | 55,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Spirit | 7119388 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Spirit | 7119388 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 11th-12th | 27,500 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Team Spirit | 7119388 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 7th-10th | 28,750 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Team Spirit | 7119388 | fissure-universe-8<br>FISSURE Universe: Episode 8 | 2026-02-01 | 2nd | 60,000 | Tier 2 | [明细](https://liquipedia.net/dota2/FISSURE/Universe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Xtreme Gaming | 8261500 | games-of-future-2026<br>Games of the Future 2026 | 2026-08-05 | 5th-8th | 35,000 | Tier 2 | [明细](https://liquipedia.net/dota2/Games_of_the_Future/2026) / [核验](https://gofuture.games/page/games-of-the-future-2026/)<br>官方赛事＋社区分配 / 中 | 官方页核对赛事；明细页逐项给出名次分配。 |
| Xtreme Gaming | 8261500 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 13th-16th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Xtreme Gaming | 8261500 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 11th | 12,500 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Xtreme Gaming | 8261500 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 7th-8th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Xtreme Gaming | 8261500 | esl-challenger-china-3<br>ESL Challenger China Season 3 x ACL 2026 | 2026-05-03 | 3rd | 20,000 | Tier 2 | [明细](https://liquipedia.net/dota2/ESL/Challenger_China/3)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Xtreme Gaming | 8261500 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 9th-11th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Xtreme Gaming | 8261500 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 3rd | 105,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Xtreme Gaming | 8261500 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 9th-11th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Xtreme Gaming | 8261500 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Xtreme Gaming | 8261500 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 7th-10th | 28,750 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Xtreme Gaming | 8261500 | esl-challenger-china-2<br>ESL Challenger China Season 2 | 2026-02-01 | 1st | 80,000 | Tier 2 | [明细](https://liquipedia.net/dota2/ESL/Challenger_China/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Vici Gaming | 726228 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 5th-6th | 5,000 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Vici Gaming | 726228 | games-of-future-2026<br>Games of the Future 2026 | 2026-08-05 | 5th-8th | 35,000 | Tier 2 | [明细](https://liquipedia.net/dota2/Games_of_the_Future/2026) / [核验](https://gofuture.games/page/games-of-the-future-2026/)<br>官方赛事＋社区分配 / 中 | 官方页核对赛事；明细页逐项给出名次分配。 |
| Vici Gaming | 726228 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 4th | 120,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Vici Gaming | 726228 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 9th-12th | 30,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Vici Gaming | 726228 | esl-challenger-china-3<br>ESL Challenger China Season 3 x ACL 2026 | 2026-05-03 | 1st | 90,000 | Tier 2 | [明细](https://liquipedia.net/dota2/ESL/Challenger_China/3)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Vici Gaming | 726228 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 12th-14th | 15,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Vici Gaming | 726228 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 7th-8th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Vici Gaming | 726228 | esl-challenger-china-2<br>ESL Challenger China Season 2 | 2026-02-01 | 3rd | 12,000 | Tier 2 | [明细](https://liquipedia.net/dota2/ESL/Challenger_China/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| LGD Gaming | 10150538 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 7th-8th | 2,500 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| LGD Gaming | 10150538 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 9th-12th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| LGD Gaming | 10150538 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 2nd | 195,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| OG | 2586976 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 5th-6th | 5,000 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| OG | 2586976 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 17th-20th | 10,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| OG | 2586976 | blast-slam-7<br>BLAST SLAM VII | 2026-06-07 | 9th-10th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/7) / [核验](https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| OG | 2586976 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 13th-14th | 25,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| OG | 2586976 | pgl-wallachia-7<br>PGL Wallachia Season 7 | 2026-03-15 | 12th-14th | 15,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| OG | 2586976 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 9th-10th | 30,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| OG | 2586976 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 3rd-4th | 80,000 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Team Resilience | 5017210 | games-of-future-2026<br>Games of the Future 2026 | 2026-08-05 | 3rd | 120,000 | Tier 2 | [明细](https://liquipedia.net/dota2/Games_of_the_Future/2026) / [核验](https://gofuture.games/page/games-of-the-future-2026/)<br>官方赛事＋社区分配 / 中 | 官方页核对赛事；明细页逐项给出名次分配。 |
| Team Resilience | 5017210 | esl-challenger-china-3<br>ESL Challenger China Season 3 x ACL 2026 | 2026-05-03 | 2nd | 40,000 | Tier 2 | [明细](https://liquipedia.net/dota2/ESL/Challenger_China/3)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Team Resilience | 5017210 | esl-challenger-china-3-open-qualifier-1<br>ESL Challenger China Season 3 x ACL 2026: Open Qualifier 1 | 2026-04-19 | 1st | 6,000 | Qualifier (Tier 2 destination) | [明细](https://liquipedia.net/dota2/ESL/Challenger_China/3/Open_Qualifier_1)<br>社区现金资格赛 / 中 | 资格赛自身公布现金分配，故纳入；不是继承主赛事奖池。 |
| Nigma Galaxy | 10136357 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 5th-8th | 70,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Nigma Galaxy | 10136357 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 13th-14th | 22,500 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Nigma Galaxy | 10136357 | 1win-essence-1<br>1win Essence I | 2026-05-11 | 4th | 7,500 | Tier 2 | [明细](https://liquipedia.net/dota2/1win_Essence/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Nigma Galaxy | 10136357 | dreamleague-division-2-4<br>DreamLeague Division 2 Season 4 | 2026-05-01 | 2nd | 10,000 | Tier 2 | [明细](https://liquipedia.net/dota2/DreamLeague/Division_2/4)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Nigma Galaxy | 10136357 | premier-series-1<br>PREMIER SERIES | 2026-04-11 | 2nd | 25,000 | Tier 2 | [明细](https://liquipedia.net/dota2/NarodCast/PREMIER_SERIES/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Nigma Galaxy | 10136357 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 15th-16th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| Nigma Galaxy | 10136357 | dreamleague-division-2-3<br>DreamLeague Division 2 Season 3 | 2026-02-12 | 2nd | 10,000 | Tier 2 | [明细](https://liquipedia.net/dota2/DreamLeague/Division_2/3)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| GamerLegion | 9964962 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 7th-8th | 2,500 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| GamerLegion | 9964962 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 17th-20th | 10,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| GamerLegion | 9964962 | dreamleague-29<br>DreamLeague Season 29 | 2026-05-24 | 15th-16th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/29)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| GamerLegion | 9964962 | pgl-wallachia-8<br>PGL Wallachia Season 8 | 2026-04-26 | 9th-11th | 20,000 | Tier 1 | [明细](https://liquipedia.net/dota2/PGL/Wallachia/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| GamerLegion | 9964962 | premier-series-1<br>PREMIER SERIES | 2026-04-11 | 4th | 7,000 | Tier 2 | [明细](https://liquipedia.net/dota2/NarodCast/PREMIER_SERIES/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| GamerLegion | 9964962 | esl-one-birmingham-2026<br>ESL One Birmingham 2026 | 2026-03-29 | 9th-10th | 30,000 | Tier 1 | [明细](https://liquipedia.net/dota2/ESL_One/Birmingham/2026)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| GamerLegion | 9964962 | dreamleague-28<br>DreamLeague Season 28 | 2026-03-01 | 13th-14th | 25,000 | Tier 1 | [明细](https://liquipedia.net/dota2/DreamLeague/28)<br>社区逐项（选手＋俱乐部）/ 中 | 明细页分别列选手奖金与俱乐部奖励；本数为两项相加。 |
| GamerLegion | 9964962 | blast-slam-6<br>BLAST SLAM VI | 2026-02-15 | 7th-10th | 28,750 | Tier 1 | [明细](https://liquipedia.net/dota2/BLAST/Slam/6) / [核验](https://blast.tv/dota/tournaments/blast-slam-vi/match?view=results)<br>官方赛果＋社区历史分配 / 中高 | 官方赛果核对名次；历史分配由明细页给出，金额含队伍奖励。 |
| Iron Wing（赛事名：1w Team） | 10150413 | 1win-essence-2<br>1win Essence II | 2026-08-05 | 3rd | 22,500 | Tier 1 | [明细](https://liquipedia.net/dota2/1win_Essence/2)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Iron Wing（赛事名：1w Team） | 10150413 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 9th-12th | 40,000 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| Iron Wing（赛事名：1w Team） | 10150413 | 1win-essence-1<br>1win Essence I | 2026-05-11 | 2nd | 25,000 | Tier 2 | [明细](https://liquipedia.net/dota2/1win_Essence/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Iron Wing（赛事名：1w Team） | 10150413 | dreamleague-division-2-4<br>DreamLeague Division 2 Season 4 | 2026-05-01 | 3rd | 8,000 | Tier 2 | [明细](https://liquipedia.net/dota2/DreamLeague/Division_2/4)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Iron Wing（赛事名：1w Team） | 10150413 | cct-s2-series-8<br>CCT Season 2 Series 8 | 2026-03-20 | 2nd | 8,000 | Tier 3 | [明细](https://liquipedia.net/dota2/CCT/Season_2/Europe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| Iron Wing（赛事名：1w Team） | 10150413 | dreamleague-division-2-3<br>DreamLeague Division 2 Season 3 | 2026-02-12 | 5th-6th | 5,000 | Tier 2 | [明细](https://liquipedia.net/dota2/DreamLeague/Division_2/3)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | games-of-future-2026<br>Games of the Future 2026 | 2026-08-05 | 13th-16th | 15,000 | Tier 2 | [明细](https://liquipedia.net/dota2/Games_of_the_Future/2026) / [核验](https://gofuture.games/page/games-of-the-future-2026/)<br>官方赛事＋社区分配 / 中 | 官方页核对赛事；明细页逐项给出名次分配。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | ewc-2026<br>Esports World Cup 2026 | 2026-07-19 | 21st-24th | 7,500 | Tier 1 | [明细](https://liquipedia.net/dota2/Esports_World_Cup/2026) / [核验](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)<br>官方分配＋社区名次 / 高 | 官方规则给出名次金额；明细页把队伍映射到名次。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | dreamleague-division-2-4<br>DreamLeague Division 2 Season 4 | 2026-05-01 | 5th-6th | 4,000 | Tier 2 | [明细](https://liquipedia.net/dota2/DreamLeague/Division_2/4)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | premier-series-1<br>PREMIER SERIES | 2026-04-11 | 5th-6th | 2,500 | Tier 2 | [明细](https://liquipedia.net/dota2/NarodCast/PREMIER_SERIES/1)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | esports-league-super-cup-pro<br>Esports League Super Cup Pro Division | 2026-03-21 | 3rd | 3,018.51 | Tier 3 | [明细](https://liquipedia.net/dota2/Esports_League_Super_Cup/Pro_Division)<br>社区原币＋汇率 / 中低 | 原奖为 250,000 RUB；按明细页所列 2026-03-21 汇率折算。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | cct-s2-series-8<br>CCT Season 2 Series 8 | 2026-03-20 | 3rd | 5,000 | Tier 3 | [明细](https://liquipedia.net/dota2/CCT/Season_2/Europe/8)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |
| HULIGANI（赛事名：L1GA TEAM） | 10149530 | cct-s2-series-7<br>CCT Season 2 Series 7 | 2026-02-20 | 3rd | 5,000 | Tier 3 | [明细](https://liquipedia.net/dota2/CCT/Season_2/Europe/7)<br>社区逐项 / 中 | 明细页直接列出该名次金额；没有按总奖池推算。 |

## Unknown / excluded

- 付款到账状态：所有合计都是公开名义获奖额；没有银行流水、付款确认或扣除处罚后的最终净额。
- 没有公开逐队分配的赛事：不进入账本；本报告没有把“未知”当作零，也没有按总奖池猜分配。
- 零奖金资格赛：只提供晋级名额的记录全部排除。
- EWC 2026 MVP US$25,000：个人奖，排除。
- Iron Wing：Tundra 转会前与 BLAST Slam VII 的组织归属不进入 1w 主合计，只在阵容谱系敏感性中显示。
- LGD Gaming：HEROIC/ex-HEROIC 转会前奖金不进入 LGD 主合计，只在阵容谱系敏感性中显示。
- LGD.Pinghu：Games of the Future 2026 的 US$35,000 属于 stable team_id 10208068，不属于当前 LGD Gaming 10150538，排除。
- HULIGANI 的 250,000 RUB：主表保留来源页的 US$3,018.51 折算；若正式产品要求固定汇率政策，应另行冻结汇率源与取值日。

## 验收记录

- JSON 解析成功，research_draft=true。
- 声明记录数 122，实际记录数 122。
- 16 个 stable team_id 均存在，逐队事件数与逐队金额重算全部一致。
- 122 条 amount_usd 全部大于零。
- 以 stable_team_id + event_id 检查，无重复条目。
- 最早结束日 2026-02-01，最晚结束日 2026-08-05；没有晚于 as_of 的条目。
- 逐条合计 US$8,204,268.51，与声明总额一致。
- 个人 MVP 与无现金资格赛未进入 rows。

可机读研究草案位于 .scratch/team-prize-ytd/prize-ledger-research.json。若把这些数字升级为正式、可复现的数据资产，下一步必须抓取并保存原始响应、请求时间与 SHA-256；本研究 memo 本身不是原始快照。
