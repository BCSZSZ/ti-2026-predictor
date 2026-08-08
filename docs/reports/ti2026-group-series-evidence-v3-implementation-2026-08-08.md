# TI 2026 系列赛证据 v3：赛事档位、奖金、问题与验收

状态：**最小实现、反算验收和项目级审查已完成；Git 发布状态以仓库历史为准**

- 原 Forecast / 比赛数据截止：`2026-08-08T04:11:08Z`
- 发布资料 `as_of`：`2026-08-08T06:05:53Z`
- 比赛数据快照：`cf7f2ab715e45a44031bfb5a7acaed73cde69902ef701dbb677692dc448849eb`
- 阶段起点：`d2605804b8888c124636a9ef38bef98d2b907ad3`，`main == origin/main`，工作树干净
- 玩家版：[7.41 系列赛证据展开](ti2026-group-current-patch-series-evidence-2026-08-08.md)
- 前一阶段：[系列赛证据 v2 实施记录](ti2026-group-series-evidence-v2-implementation-2026-08-08.md)

## 全体代码状态和最小实装计划

阶段开始前复核了仓库、现有 7.41 玩家报告、`leagues.parquet` 和 `matches.parquet`。底层只有
OpenDota `league_tier`，18 个目标赛事全部是 `professional`；没有社区 Tier 或奖金字段。
现有 409 个完整 Series、866 个 Series 内 Game、5 个不完整片段和 871 个全部合格 Game 已在
v2 反算通过，不需要重新同步、重新训练或重新生成 Forecast。

本阶段目标是回答玩家提出的“社区 Tier 1/2/3 能否区分，以及能否用奖金直观看赛事规模”。
最小修改范围固定为：

1. 在 `CONTEXT.md` 增加“社区赛事档位”和“赛事总奖金”两个互斥术语；
2. 扩展既有玩家版的 18 行赛事表；
3. 新增本技术与问题 Memo，并更新 README 入口；
4. 不修改 `src/`、配置、规则快照、模型、Forecast artifact、Parquet 或随机种子。

验收标准固定为：18 个赛事都有可读档位；9 个主赛事反算为 6 个 Tier 1、3 个 Tier 2，公布
总奖金合计 `US$7,472,000`；9 个资格赛都明确是“通往 Tier 1”，只有证据明确的两项写成
“无独立奖金”，其余保持“未公布”；原 409 Series 和 871 Game 守恒；玩家版不显示来源，
技术记录保留 URL、请求、抓取时间、修订号和 SHA-256；全量 CI 与项目级审查通过。

## 口径：两个“级别”不能混用

- **OpenDota 赛事级别**是数据目录字段。本报告涉及的 18 个赛事全部为 `professional`，没有
  `premium`；它仍是既有模型的赛事权重输入。
- **社区赛事档位**是按明确冻结时点读取的 Tier 1/2/3/4 分类，用于玩家理解赛事规模。本阶段
  只展示，不回填底层数据，也不改变模型权重。
- 资格赛行显示“通往 Tier 1”，表示获胜者进入 Tier 1 主赛事。它不是把资格赛本身包装成主赛事。
- **赛事总奖金**采用赛事范围内公布的美元总池。资格赛不继承主赛事奖金；没有独立金额的公开
  证据时保持“未公布”，绝不以 `$0` 回填。

## 主赛事档位和奖金反算

| 主赛事 | 页面修订 | 修订时间（UTC） | 社区档位 | 总奖金 |
| --- | ---: | --- | --- | ---: |
| ESL One Birmingham 2026 | `2401680` | `2026-07-09T13:06:18Z` | Tier 1 | US$1,000,000 |
| Premier Series | `2377388` | `2026-04-30T19:33:48Z` | Tier 2 | US$100,000 |
| PGL Wallachia S8 | `2376736` | `2026-04-27T15:51:17Z` | Tier 1 | US$1,000,000 |
| ESL Challenger China x ACL | `2410964` | `2026-08-05T17:00:35Z` | Tier 2 | US$172,000 |
| DreamLeague 29 | `2401671` | `2026-07-09T13:01:49Z` | Tier 1 | US$1,000,000 |
| BLAST SLAM VII | `2401670` | `2026-07-09T12:59:10Z` | Tier 1 | US$1,000,000 |
| Esports World Cup 2026 | `2410968` | `2026-08-05T17:04:20Z` | Tier 1 | US$2,000,000 |
| 1win Essence II | `2411040` | `2026-08-05T21:44:57Z` | Tier 1 | US$200,000 |
| Games of the Future 2026 | `2410959` | `2026-08-05T16:31:11Z` | Tier 2 | US$1,000,000 |
| **合计** |  |  | **6 个 Tier 1、3 个 Tier 2** | **US$7,472,000** |

全部九个页面修订均早于发布资料 `as_of`。社区档位的定义页说明：Tier 1 面向世界最强队伍，
Tier 2 的顶级队伍较少；因此档位是综合分类，不是按奖金机械切线。当前数据也直接给出反例：
Games of the Future 2026 为 100 万美元但属于 Tier 2，1win Essence II 为 20 万美元但属于 Tier 1。

## 资格赛的档位和奖金语义

| 资格赛 | 目标主赛事 | 玩家版档位 | 独立奖金 |
| --- | --- | --- | --- |
| BLAST SLAM VII 中国资格赛 | BLAST SLAM VII | 通往 Tier 1 | 无独立奖金 |
| BLAST SLAM VII 欧洲资格赛 | BLAST SLAM VII | 通往 Tier 1 | 无独立奖金 |
| DreamLeague 29 资格赛 | DreamLeague 29 | 通往 Tier 1 | 未公布 |
| EWC 2026 地区资格赛 | Esports World Cup 2026 | 通往 Tier 1 | 未公布 |
| TI 2026 中国区资格赛 | The International 2026 | 通往 Tier 1 | 未公布 |
| TI 2026 南美区资格赛 | The International 2026 | 通往 Tier 1 | 未公布 |
| TI 2026 东南亚区资格赛 | The International 2026 | 通往 Tier 1 | 未公布 |
| TI 2026 欧洲区资格赛 | The International 2026 | 通往 Tier 1 | 未公布 |
| TI 2026 北美区资格赛 | The International 2026 | 通往 Tier 1 | 未公布 |

BLAST 两个页面分别以稳定 `leagueid` `19520` 和 `19539` 对上本地账本，并明确标为
`liquipediatiertype=Qualifier`；页面奖金区只列晋级名额。赛事方 2026 规则手册进一步明确所有
Closed Qualifier 没有奖金池，因此这两行可写“无独立奖金”。其余七项没有同等明确的独立金额
证据，保持“未公布”比猜测 `$0` 更可靠。

## 来源快照和冻结边界

玩家版不显示来源；以下技术记录用于复现。所有原始响应和元数据保存在 Git 忽略的
`data/raw/publication/`，不会提交大型缓存。

| 原始响应 | 请求摘要 | 抓取时间（UTC） | SHA-256 |
| --- | --- | --- | --- |
| Dota 2 社区档位、奖金及定义页 | `GET https://liquipedia.net/dota2/api.php`，`action=query`、`prop=revisions`、`rvprop=ids\|timestamp\|content`，11 个页面 | `2026-08-08T06:02:03.925433Z` | `29ef52e69514b118fb863238c20ccdbd10a25dd598ae72bd812d71241f0b4716` |
| BLAST 2026 Dota Slam 规则手册 PDF | `GET https://assets.blast.tv/rulebook/2026_BLAST_DOTA_SLAM_Rulebook.pdf` | `2026-08-08T06:02:04.282069Z` | `0fa1b9f8315f2242f895dcdbddbab1fee642414cf64a9e28b8483c7bd4422d28` |
| Games of the Future 2026 奖金公告 | `GET https://gofuture.games/news/item/dota-2-returns-for-gotf-2026-with-1m-prize-pool/` | `2026-08-08T06:02:05.574819Z` | `31a5152ab461de16b969544be5cb3aad6e17d9b81167d5ed948f164bd3af5f9e` |
| BLAST VII 资格赛页面搜索 | `GET https://liquipedia.net/dota2/api.php`，`list=search` | `2026-08-08T06:05:36.899163Z` | `f01c31bbab11d0b89690bc391ed61ccbb742a1fad144a35a8c139c4a56b80169` |
| BLAST VII 中国/欧洲资格赛页面 | `GET https://liquipedia.net/dota2/api.php`，`prop=revisions`，2 个页面 | `2026-08-08T06:05:52.250767Z` | `5396b6738b7b2938156dbaeefdc32252e038a2b70884e3e275cefe4e0c983d3d` |

社区分类入口为 [Dota 2 赛事档位说明](https://liquipedia.net/dota2/Portal%3ATournaments)。奖金优先用
赛事方页面交叉核对，包括 [BLAST SLAM VII](https://blast.tv/dota/tournaments/blast-slam-vii)、
[Esports World Cup 2026 规则手册](https://cdn.esportsworldcup.com/resources/uploads/Dota_2_at_2026_Esports_World_Cup_Rulebook_dec2d6e169.pdf)
和 [Games of the Future 2026 公告](https://gofuture.games/news/item/dota-2-returns-for-gotf-2026-with-1m-prize-pool/)。
上一阶段已经保存 Birmingham、PGL、BLAST、EWC、1win 等赛事页的不可变快照和 SHA-256，本阶段
没有覆盖这些原始响应。

## 已知限制和问题 Memo

1. **社区档位会变化。** 这里记录的是 `2026-08-08T06:05:53Z` 以前的页面修订，不声称永久不变；
   后续变更必须生成新快照和新报告，不能静默改写。
2. **奖金不是实力分。** 奖金能直观表达赛事规模，但邀请阵容、竞争强度、赛制和地区覆盖同样影响
   社区档位，因此没有用奖金重排五个实力带或调整模型权重。
3. **“总奖金”不等于冠军到手金额。** 赛事方可能把名次奖金、队伍收益或其他奖励都计入总池；
   BLAST 的 100 万美元就是按其手册所定义的赛事总池展示。本报告不拆分税费或单队实得。
4. **七项资格赛奖金仍未知。** “未公布”不是“没有奖金”，也不是 `$0`；如果以后出现明确规则，
   应在新的 `as_of` 下更新。
5. **底层 OpenDota 分类没有消失。** 18 个赛事仍全部是 `professional`；玩家表移除重复列只是为了
   腾出空间展示更有区分度的社区档位和奖金。
6. **本阶段不改变预测。** 没有新增比赛、重训、重排、修改胜率或修改游戏内填写建议。

## 自动验收和项目级审查

专用读回验收通过：

- 玩家表恰有 18 个赛事行；完整 Series 合计 409，全部合格 Game 合计 871；
- 9 个主赛事为 6 个 Tier 1、3 个 Tier 2，逐行奖金相加为 `US$7,472,000`；
- 9 个资格赛全部写“通往 Tier 1”，奖金列恰有 2 个“无独立奖金”和 7 个“未公布”，没有 `$0`；
- 玩家表未显示 URL、来源名或 SHA-256；技术 Memo 的内部链接全部存在；
- 九个主赛事页面、两个 BLAST 资格赛页面的修订时间均不晚于发布资料 `as_of`；
- 五份新增原始响应的正文哈希、元数据 SHA-256、HTTP 200 和 UTC 抓取时间全部一致；
- BLAST 中国/欧洲资格赛的页面 `leagueid` 分别与本地 `19520`、`19539` 对上，规则手册原始
  PDF 读回确认 Closed Qualifier 无奖金池。

仓库 CI 同口径验收结果：

- `uv run ruff format --check src tests`：72 个文件格式正确；
- `uv run ruff check src tests`：通过；
- `uv run pytest`：155 passed，1 skipped。

项目级审查确认 Git 变更只包含 `CONTEXT.md`、`README.md` 和两份报告 Markdown，没有修改
`src/`、测试、配置、规则快照、模型、Forecast artifact、Parquet 或随机种子；因此既有实力带、
精确排名、对局概率和游戏内填写建议保持不变。大型 HTML、JSON 和 PDF 原始响应仍在
`data/raw/` 忽略目录，没有进入提交。

没有需要清理的生产旧代码：本阶段只是发布信息增量。README 的当前入口已从 v2 实施记录收口到
v3；v2 继续作为不可变历史复现记录保留，删除它反而会破坏前一阶段的证据链。
