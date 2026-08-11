# TI 2026 瑞士轮首轮与 LGD 中单变更调查

- 调查截止（`as_of`）：`2026-08-10T12:30:00Z`
- 状态：实装前证据审计；本轮未修改 `src/`、`config/` 或任何预测产物
- 术语：下文的概率均指项目产生的模型预测（`Forecast`），不是 Valve 游戏内预测答案（`InGamePrediction`）

## 后续决策附记（2026-08-11）

本文保留的是实装前调查快照，其中对 `0.9` 的讨论属于当时待验收方案。负责人随后把正式风险
情景改为 **LGD 正胜算 odds `×0.60`**；项目没有把绝对 Elo/Glicko rating 直接乘 0.60。当前
首次 0.60 重算为 `group-a5d3e4484ebf918e`；随后修复 TEAM VISION 双 ID 身份断裂后的当前
正式重算为 `group-275030258cd6412d`，期望正确 `5.1175 / 16 = 31.98%`。LGD 中单仍保持
`unavailable/null`，Group Fantasy 的预计 Series 机会数也已按 0.60 Swiss 情景重算。当前结论见
[赛事 Forecast 报告](../reports/ti2026-group-forecast-publication-2026-08-10.md)。下文原始调查内容不
回写，以保留当时证据审计和决策演变。

## 结论

1. **瑞士轮首轮 8 组对阵已由 Valve 官方赛程/API 确认**，可以替换旧的“只保持名额容量”的近似首轮。官方 API 只预建了首轮 8 个 Swiss 节点，后续轮次仍须按官方配对规则在模拟中生成。
2. 官方 API 的前四个节点名为 `Match 1.A` 至 `Match 4.A`，后四个为 `Match 1.B` 至 `Match 4.B`。结合官方规则“首轮只在各初始组内比赛”，可把两批队伍视为初始 A/B 组；但 API **没有独立的 `initial_group_id` 字段**，因此这是有强一手依据的推断，不应写成 Valve 另行公布的显式分组名单。
3. **LGD 的 TaiLung 不再参加 TI 2026、Topson 顶替中单，已由当前本机 Dota 客户端确认。** 当前 TI 2026 Fantasy 名单把 TaiLung 标为无效、Topson 标为有效，并把两人都关联到稳定 `team_id=10150538`。
4. LGD 官方公告只称涉及 TaiLung 的“赛事诚信信息”，并称赛事方禁止他参加 TI 2026、PGL 终身禁止其参加 PGL 赛事。公告没有公开写明假赛、下注、故意输局或具体证据；所以“因为假赛退出”**不能作为已确认事实**。本次未找到独立的 PGL 官方公告，PGL 处罚只能标为“LGD 官方公告所述”。
5. “Topson 没有 7.41 数据”不成立。稳定账号 `94054712` 在公开数据中有 **14 局 7.41 系列比赛**：2 局 7.41c（league 0，未分类）和 12 局 7.41d（TI 2026 欧洲公开预选赛，OpenDota tier=`excluded`），描述性战绩 10–4；**7.41e 为 0 局**。但按本项目当前 Fantasy 历史口径——只纳入 OpenDota `premium/professional`——这 14 局中**合格样本仍为 0**。必须区分“数据存在”和“当前政策允许训练”。
6. 用户提出的 LGD `0.9` 战力倍率目前**没有一手证据或回测支持其幅度**，且“评分乘 0.9”在以 1500 为原点的 Elo/Glicko 上含义不明确。它可作为待验收的下行情景参数，但在定义作用空间、做敏感性比较之前，不宜当成唯一主估计。
7. Fantasy “不为 Topson 编造特殊数据、暂不选 LGD 中单”有保守依据；但“完全不处理”不成立：必须更新稳定选手 ID、阵容生效区间和候选有效性，历史 TaiLung 数据不得转移给 Topson，缺失值必须保持 `null`。排除 LGD 中单应是显式、可审计的候选约束，而不是把缺失值写成 0。

## Valve 官方首轮对阵

官方页面：[TI 2026 Schedule](https://www.dota2.com/esports/ti15/schedule)；机器可读来源：[GetLeagueData，league_id=19719](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719)。8 个节点的 `node_type` 均为 `2`；Valve 站点把该类型显示为 BO3。

| 推断初始组 | Valve 节点 | 开赛 UTC | GMT+9 | 对阵（稳定 team_id） |
| --- | --- | --- | --- | --- |
| A（推断） | `Match 1.A` | 2026-08-13 02:00 | 11:00 | Team Falcons (`9247354`) vs LGD Gaming (`10150538`) |
| A（推断） | `Match 2.A` | 2026-08-13 02:00 | 11:00 | Iron Wing (`10150413`) vs Nigma Galaxy (`10136357`) |
| A（推断） | `Match 3.A` | 2026-08-13 02:00 | 11:00 | BoomBoys (`8255888`) vs OG (`2586976`) |
| A（推断） | `Match 4.A` | 2026-08-13 02:00 | 11:00 | TEAM VISION (`9572001`) vs Team Resilience (`5017210`) |
| B（推断） | `Match 1.B` | 2026-08-13 05:00 | 14:00 | Team Spirit (`7119388`) vs Xtreme Gaming (`8261500`) |
| B（推断） | `Match 2.B` | 2026-08-13 05:00 | 14:00 | Team Liquid (`2163`) vs Vici Gaming (`726228`) |
| B（推断） | `Match 3.B` | 2026-08-13 05:00 | 14:00 | Aurora Gaming (`9467224`) vs GamerLegion (`9964962`) |
| B（推断） | `Match 4.B` | 2026-08-13 05:00 | 14:00 | Team Yandex (`9823272`) vs HULIGANI (`10149530`) |

API 的 Swiss 节点组同时给出：16 队、最多 5 轮、`win_loss_limit=4`、默认 BO3；3 队直接进入 Playoff，10 队进入五场 Elimination Round，因此另有 3 队在 Swiss 后淘汰。Valve 的邀请/预选公告也说明：8 月 13–15 日进行五轮 Swiss，星期日再进行五场淘汰赛，最终留下 8 队。

## 官方后续配对与排名规则

官方规则页：[TI 2026 Rules](https://www.dota2.com/esports/ti15/tirules)。动态页面使用的 Valve 官方 English localization 资源明确给出以下规则：

- 排名依次比较：比赛胜场、比赛负场、交手对手的总比赛胜场、Game 胜率、交手对手的平均 Game 胜率、平均比赛时长（越短越好）、掷硬币。
- 一般 Swiss 配对：同战绩队伍相配；尽量避免重赛；尽量缩小双方排名距离。
- 第 1 轮：16 队拆成两个初始组，由赛事方设置组内对阵。
- 第 2、3 轮：只能匹配初始同组队伍。
- 第 4 轮：只能匹配另一个初始组的队伍。
- 第 5 轮：对“负者即淘汰”的比赛，改为**最大化**双方排名距离；其他情况仍受一般规则约束。
- Elimination Round：从排名最好的 3–2 队开始，依次从尚未被选择的五支 2–3 队中挑选对手。

这些规则仍包含“尽量”和主动选对手，故后续配对不是只靠胜负记录就唯一确定。正式模拟必须把有效配对集合、赛事方取舍和淘汰轮选对手策略写成显式假设或分支，不得把任意一种合法配对冒充官方唯一结果。排名规则还要求模拟或代理 BO3 局分、Game 胜率，深层同分时甚至涉及时长/掷硬币。

本机当前 `international_2026.eventdef` 没有 Swiss 配对或赛程，不能用它覆盖上述 Valve 官方网页/API；它只包含活动及客户端通知配置。

## LGD 与 Topson：可确认事实

### 当前本机客户端（最高优先级）

本机已安装客户端快照，不是网页公告：

- `steam.inf`：Client/Server version `6893`，SourceRevision `10895878`，VersionDate `Aug 09 2026`。
- 当前 `EVENT_ID_INTERNATIONAL_2026` 的 MID Fantasy 列表：
  - TaiLung：`account_id=1026694469`，`team_id=10150538`，`m_bIsValid=false`；
  - Topson：`account_id=94054712`，`team_id=10150538`，`m_bIsValid=true`。
- 当前英文客户端通知称 TaiLung 不再参加 TI、由 Topias “Topson” Taavitsainen 替换，Fantasy roster 已自动更新。

这能确认 TI 2026 赛事/Fantasy 范围内的替换和有效性，**不能确认违规的具体性质**。

### LGD 官方公告

[LGD 电子竞技俱乐部官方微博公告](https://weibo.cn/2157471171/RcAAEl9fF)（页面显示 2026-08-09 14:11）可确认：

- 俱乐部获悉涉及 TaiLung 的“赛事诚信信息”，启动内部核查并向赛事相关方报告、配合后续核查；
- 赛事方禁止 TaiLung 参加 TI 2026；LGD 称 PGL 决定终身禁止其参加 PGL 赛事；
- 赛事方批准特别阵容调整，LGD 当时仍在办理新中单与最终参赛阵容。

公告未披露的内容：具体比赛、证据、是否下注、是否故意输局、是否构成通常所说的“假赛”。因此这些内容均为**未确认**。

### 官方 API 的范围冲突

Valve 通用 DPC API 可确认稳定身份：[Topson (`94054712`)](https://www.dota2.com/webapi/IDOTA2DPC/GetPlayerInfo/v001?account_id=94054712)、[TaiLung (`1026694469`)](https://www.dota2.com/webapi/IDOTA2DPC/GetPlayerInfo/v001?account_id=1026694469)、[LGD (`10150538`)](https://www.dota2.com/webapi/IDOTA2DPC/GetSingleTeamInfo/v001?team_id=10150538)。但截至本次抓取，通用队伍注册仍列 TaiLung，Topson 的通用 `team_id` 仍为 0；这与客户端的 TI 事件专属名单不同。

这是**数据范围不同/通用注册滞后**，不是替换未发生。TI 预测与 Fantasy 应采用事件专属客户端状态，同时保留通用 API 冲突记录，不得静默覆盖。

## Topson 的 7.41 数据

数据入口：[OpenDota player matches](https://api.opendota.com/api/players/94054712/matches?date=366)、[league catalog](https://api.opendota.com/api/leagues)。OpenDota 详情的 `patch=60` 只标识 7.41 家族；字母版本按比赛 UTC 与 Valve 官方 [7.41c](https://www.dota2.com/patches/7.41c)、[7.41d](https://www.dota2.com/patches/7.41d)、[7.41e](https://www.dota2.com/patches/7.41e) 发布时间派生。

| Patch | 比赛数 | League/tier | 结果 | 当前 Fantasy 历史口径合格数 |
| --- | ---: | --- | --- | ---: |
| 7.41c | 2 | league `0`，未分类 | 1–1 | 0 |
| 7.41d | 12 | league `19841`，TI 2026 Europe Open Qualifier；OpenDota `excluded` | 9–3 | 0 |
| 7.41e | 0 | — | — | 0 |
| 合计 | **14** | 均非 `premium/professional` | **10–4** | **0** |

逐局详情：

- 7.41c：[8804428478](https://api.opendota.com/api/matches/8804428478)（胜 Brrr）、[8804477738](https://api.opendota.com/api/matches/8804477738)（负 For H&S）。
- 7.41d：[8844963780](https://api.opendota.com/api/matches/8844963780)、[8845108992](https://api.opendota.com/api/matches/8845108992)、[8845224648](https://api.opendota.com/api/matches/8845224648)、[8845303708](https://api.opendota.com/api/matches/8845303708)、[8845419407](https://api.opendota.com/api/matches/8845419407)、[8845506810](https://api.opendota.com/api/matches/8845506810)、[8847534378](https://api.opendota.com/api/matches/8847534378)、[8847594783](https://api.opendota.com/api/matches/8847594783)、[8847665869](https://api.opendota.com/api/matches/8847665869)、[8847774380](https://api.opendota.com/api/matches/8847774380)、[8847943436](https://api.opendota.com/api/matches/8847943436)、[8848026973](https://api.opendota.com/api/matches/8848026973)。

这 12 局发生在 2026-06-09 与 2026-06-11，说明 Topson 在本次 `as_of` 前约两个月仍参加过 TI 公开预选赛；“退役多年所以完全没有近期比赛”不准确。但公开预选赛的对手池、比赛等级与 TI 正赛不同，10–4 不能直接当成 LGD/TI 战力估计。

本项目当前 Fantasy 历史范围见 [TI 2026 Fantasy 选手历史采样范围](./ti2026-player-history-scope.md)：只纳入 `premium/professional`。改变规则以吸收 `excluded` 公开预选赛属于建模政策变更，必须单独验证；若不改政策，Topson 的正式 Fantasy 统计应保持不可用/`null`，不得借用 TaiLung 数据或填 0。

## 对两个假设的证据审计

### 1. LGD 战力评分乘 0.9

方向上，赛前临时更换中单会引入阵容连续性、配合与沟通不确定性；但现有官方材料没有给出“恰好下降 10%”的量化依据。更重要的是，本项目 Elo/Glicko 以 1500 为基准，绝对评分直接乘 0.9 不是尺度不变的操作。

以现有正式基线产物 `group-d90f0b006fe33908`（`as_of=2026-08-08T04:11:08Z`）作**只读敏感性演示**：LGD Elo 为 1507.48、Glicko 为 1643.66、50/50 综合点为 1575.57。字面上把两个绝对评分都乘 0.9，会把综合点降到 1418.01（约减 157.56），并把 Falcons 对 LGD 的中立单局胜率从 65.32% 推到 82.17%；若只把“高于 1500 的部分”乘 0.9，综合点仅降到 1568.01，Falcons 胜率约 66.27%。同一句“0.9 倍”产生完全不同的结果。

因此，在实装前必须先明确它作用于绝对 rating、相对 1500 的 rating 差、胜率、odds 还是 log-odds，并把原始基线与下行情景并列。上述 65.32% 等是**单局 Forecast**，不是 BO3 胜率，也不是本轮要求交付的重模拟结果。

### 2. Fantasy 不特殊处理，但不选 LGD 中单

- 有依据的部分：当前政策下 Topson 合格历史样本为 0；不应为他拟合未经验证的特殊分数，也不应把 TaiLung 历史移植给他。
- 必须处理的部分：阵容身份、有效区间和客户端候选状态必须更新；TaiLung 无效、Topson 有效，不能沿用旧名单。
- “不选 LGD 中单”可作为显式保守约束，直到合格覆盖/发布门槛满足；它是风险控制，不是“Topson 得分必然低”的数据结论。
- Fantasy 缺失必须是 `null/unavailable`，不能当成 0；若现有优化器已自动排除不可发布候选，应避免再造第二套隐式规则。
- 战队层的 roster-shock 情景不应机械地把 Topson 的每项 Fantasy 统计也乘 0.9。它只应通过已明确建模的出场机会、系列数或队伍表现路径传播。

## 对后续实装计划的约束（本轮不实装）

1. 冻结新的 UTC `as_of`，保存 Valve league API、客户端 roster、LGD 公告与 OpenDota 响应的 URL、参数、抓取时间和 SHA-256；不得覆盖旧快照。
2. 用稳定 ID 写入首轮 8 组固定 BO3；把 A/B 归属标为由 `.A/.B` 节点名派生，并保留证据字段。
3. 实现官方 Swiss 状态机：首轮固定；R2/3 同组、R4 跨组、R5 淘汰局最大排名距离；处理避免重赛、排名距离与非唯一配对。Elimination 的选对手必须是显式策略/分支。
4. 先把单局概率转换为经验证的 BO3 系列概率，再推进 Swiss；不得继续把单局胜率直接称作 BO3 胜率。
5. LGD 至少并列输出“未施加 roster shock 的基线”和“版本化下行情景”；在用户确认变换定义前，不把 `0.9` 写死成主模型事实。
6. Fantasy 结束 TaiLung 的事件阵容有效区间、开始 Topson 的事件区间；保留历史归属，不回填。Topson 合格样本为 0 时保持缺失，并用显式候选约束控制 LGD 中单。
7. 最终结果须对每个答案明确显示百分率，并给出“期望正确个数”。若答案槽位的正确指示量为 `I_i`，则 `E[正确个数]=ΣP(I_i=1)`；此求和不要求槽位独立，但每个 `P(I_i=1)` 必须来自同一套联合赛事模拟与对应的游戏内计分映射。
8. 同一快照、配置和随机种子必须复现相同 JSON；运行记录须含 Git commit、规则版本、数据快照、LGD 情景定义和随机种子。

## 尚未确认

- TaiLung 涉及的具体违规行为和证据；“假赛”不能作为事实。
- 独立的 PGL 官方处罚公告；目前只有 LGD 官方公告转述 PGL 决定。
- Topson 替换的精确生效时刻；只能确认它在当前客户端事件名单抓取时已经生效，不能回填更早比赛。
- Valve 独立字段形式的初始 A/B 组名单；现阶段根据官方节点 `.A/.B` 与首轮组内规则推断。
- 赛事方在多个合法 Swiss 配对之间的完整确定性算法，以及 3–2 队实际会选择哪支 2–3 队。
- Topson 在 `premium/professional` 口径下的 7.41/7.41e Fantasy 样本；当前均为 0。

## 来源与抓取账本

| 来源 | 抓取/观察 UTC | SHA-256 / 备注 |
| --- | --- | --- |
| 本机 `C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\steam.inf` | 2026-08-10T06:10:27Z（文件修改时间） | `CD709447303779448B0DF926CF77DDF6C231671CC7810CB75D39FC5FFD225651` |
| 本机 `pak01_dir.vpk` | 2026-08-10T06:10:26Z（文件修改时间） | `E44FA95DFD09F5E0977E5A48B704925378731AB6DA4C446DE8CD8DD492CA1BF7` |
| 临时解包 `scripts/fantasy_crafting.vdata` | 2026-08-10 | `EBD26EC79C49C055BEECDF1D55AC0175B88DF0F0C22E6447A6B38BAEC5B5EFD9` |
| 临时解包 `international_2026.eventdef` | 2026-08-10 | `6A7192CC5C6B954E25E958649378DAA316E02DFB41370FCC3BAAC4B73A5BD357` |
| 临时解包英文客户端 localization | 2026-08-10 | `3974E0DFE64EC182288E3B0731AF678DBCB737F997407AD8D8A0A14E15DC4D7B` |
| [Valve GetLeagueData 19719](https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001?league_id=19719) | 2026-08-10T12:24:58Z | 85,406 bytes；`3F3A7A48DB39107992B2AD4F77F97D88EBE59878718010A77C377F4D479ED292` |
| [Valve TI 2026 Rules](https://www.dota2.com/esports/ti15/tirules) 与其 [官方 English localization chunk](https://www.dota2.com/public/javascript/dota_react/6777.js?contenthash=652ea487b0024989f20b&l=english&_cdn=fastly) | 2026-08-10T12:28:20Z | chunk 214,643 bytes；`E55E2D979F0DE1F2B16890B4EA6ED4D1E8BA0C47752A2BFDB1DC86E8829BBF6C` |
| [Valve TI 2026 Invitations and Qualifiers](https://www.dota2.com/newsentry/1833334318578465)；[Steam News API](https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?appid=570&count=100&maxlength=0&format=json) | 2026-08-10T12:26:13Z | News API 280,876 bytes；`1B2F363F36F3BB84DC6D7E3FE9C7A775ECAC7E2BF865171463C64EE262030239` |
| [LGD 官方微博 RcAAEl9fF](https://weibo.cn/2157471171/RcAAEl9fF) | 2026-08-10T12:27:20Z | 10,994 bytes；`1A502689A06D8C08BDE9139828C696C92DFACD69CB59ABB113E18C961407F2B4` |
| [Valve Topson player info](https://www.dota2.com/webapi/IDOTA2DPC/GetPlayerInfo/v001?account_id=94054712) | 2026-08-10T12:26:37Z | `8C19FE895DF5FA7E9C46BA1C97525E81BB9DCBAA5E58C4D218963F547C8FE6C9` |
| [Valve TaiLung player info](https://www.dota2.com/webapi/IDOTA2DPC/GetPlayerInfo/v001?account_id=1026694469) | 2026-08-10T12:26:37Z | `6599CCE9E8D5A54A0E23100A79EBEDD06E59CC8A0CD46B591F2199926C310330` |
| [Valve LGD team info](https://www.dota2.com/webapi/IDOTA2DPC/GetSingleTeamInfo/v001?team_id=10150538) | 2026-08-10T12:26:37Z | `8121A4C2E5F6D2019B18C2180341119927836E9CDF00AC237776336480643A14` |
| [OpenDota Topson matches](https://api.opendota.com/api/players/94054712/matches?date=366) | 2026-08-10T12:25:28Z | 8,552 bytes；`6B4D65AD021601831E631FC113A7D039FE46B1611C4077B81739C2E535E086E4` |
| [OpenDota leagues](https://api.opendota.com/api/leagues) | 2026-08-10T12:26:27Z | 1,028,254 bytes；`6F0AC596309C5F5757E962467D1D184167226754F52D9B62557426E1F9A3330B` |
| 14 个上列 OpenDota match detail 响应的规范化审计汇总 | 2026-08-10T12:25–12:26Z | `2E34D4D1032FBA34E48A73DE53C738FC0E1061F177C9A21BFCCA317729001E0B`；逐局 URL 已列出 |
