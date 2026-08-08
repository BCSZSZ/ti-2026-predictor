# TI 2026 Fantasy 客户端规则截图归档

## 文档状态

- 文档类型：本机 Dota 客户端界面的人工转录与规则整理。
- `as_of`：`2026-08-02T04:42:23.961Z`，表示这些证据最迟已在此时提供给项目并完成读取；截图实际拍摄时间未知。
- 来源优先级：本机当前 Dota 客户端，符合仓库规定的最高优先级规则来源。
- 客户端 build：截图没有显示，无法识别。
- 结论边界：本文可以证明客户端界面显示了什么，但还不能作为 `CONTEXT.md` 所定义的正式 **Rule snapshot / 规则快照**，因为后者要求关联一个可识别的客户端 build。
- 实现边界：截图转录与项目补充约定严格分开；当前可执行约定记录在第 10 节，并同步到 `config/rules/ti2026.json` 与 Fantasy 计算实现。
- 原图处理：遵守仓库规则，不把截图提交到 Git。下文记录文件名、尺寸与 SHA-256，便于核验原图是否相同。

截图外的客户端源码调查及其证据等级见 [`research/ti2026-fantasy-stacking-and-percentile.md`](research/ti2026-fantasy-stacking-and-percentile.md)。

本文使用以下标记：

- **截图确认**：可以直接从截图文字或数字读出。
- **项目解释**：为了使用项目中的 Game、Series、Period 等统一术语所做的等义整理。
- **待验证**：截图没有给出足够信息，不能据此写成可执行公式。

## 1. Crafting Basics（制作基础）

### 英文原文转录

> Craft your own team from The International competitors! Choose the core, mid, and support players from three teams and use roll tokens to mutate and improve your team to increase their fantasy score. Make sure to check in after each period as new options for crafting will appear.

### 截图确认

- 从 TI 参赛者中选择 core、mid、support 三个 Fantasy 角色。
- 选择涉及三个队伍；截图没有明确这三个队伍是否必须互不相同。
- 可以消耗 roll token（重随代币）改变并强化阵容。
- 每个 Period 结束后会出现新的制作选项，需要重新查看。

### Rolling（重随）原文转录

> You always have 3 unique roll options for emblems available to you which are the same for every War Banner. Each roll costs a single roll token, only affects the currently selected War Banner, and will replace all available roll options when used.

### 截图确认

- 任意时刻有 3 个互不相同的 Emblem 重随选项。
- 这 3 个选项对所有 War Banner 相同。
- 使用一个选项消耗 1 枚 roll token。
- 效果只作用于当前选中的 War Banner。
- 使用后，当前全部可用重随选项都会被替换。

截图没有说明新选项的抽取概率，也没有说明是否允许放弃选项或免费刷新。

### Coaching Titles（指导员称号）原文转录

> As the coach of your fantasy team, you can choose a prefix and suffix (known as Titles) to provide bonuses to all of your players during their games. Each title provides a percentage increase to the final score in a game if a condition is met. You may freely change your titles without spending roll tokens.

### 截图确认

- 指导员称号由一个 prefix（前缀）和一个 suffix（后缀）组成。
- 称号作用于 Fantasy 阵容中的所有选手。
- 某个称号条件满足时，它对该 Game 的最终分数提供百分比加成。
- 改变称号不消耗 roll token。

第一批帮助页截图没有列出具体称号，也没有说明前缀与后缀同时触发时百分比是相加还是相乘。随后提供的 `Change Titles` 截图补齐了可选项与条件。

### Change Titles（具体称号）

客户端要求同时选择一个 prefix 和一个 suffix；它们共同作用于完整 Fantasy 阵容。黄色高亮只表示截图拍摄时选择了 `Otherworldly` 与 `the Flayed Twins Acolyte`，不证明这两个选项最优。

#### Prefixes

| Title | 截图显示的触发条件 | 加成 |
| --- | --- | ---: |
| Crimson | 使用红色英雄 | +6% |
| Cerulean | 使用蓝色英雄 | +11% |
| Emerald | 使用绿色英雄 | +6% |
| Royal | 使用紫色英雄 | +10% |
| Golden | 使用黄色或棕色英雄 | +8% |
| Elemental | 使用水生、火焰或冰霜英雄 | +8% |
| Otherworldly | 使用亡灵、恶魔或精魂英雄 | +7% |
| Heroic | 使用披风或面具英雄 | +9% |

#### Suffixes

| Title | 截图显示的触发条件 | 加成 |
| --- | --- | ---: |
| the Tormented | 任意选手死于 Tormentor | +23% |
| the Flayed Twins Acolyte | 任意选手在开场号角前取得第一滴血 | +9% |
| the Patient | 第一滴血在 10 分钟后才发生 | +23% |
| the Underdog | 该选手在本局落败 | +6% |
| the Decisive | 比赛少于 25 分钟 | +24% |
| the Clutch | 参加系列赛最后可能进行的一局 | +16% |
| the Lucky | 比赛时间的末位数字为 8 | +21% |
| the Cruel | 任意选手在自己的泉水内被击杀 | +13% |

#### 与本机客户端数据的冲突

同一客户端 build 的 `scripts/fantasy_crafting.vdata` 与可见文案有两处冲突：

- `the Flayed Twins Acolyte`：可见界面只写“号角前”；内部条件同时列出“号角前”或“1 分钟前”。
- `the Patient`：可见界面写“10 分钟后”；内部统计字段名是 `first_blood_after_6_minutes`。

这里的“内部条件/字段”是客户端 `fantasy_crafting.vdata` 里的数据驱动配置，不是公开的结算函数
源码。它为每个 Title 列出统计项 ID、Game/Team/Player 作用域、阈值、最小/最大比较方向以及
`Any/All` 组合模式；本机 `server.dll`/`client.dll` 能确认这些配置结构和内部源文件名，但没有公开
服务器怎样填充三个一血统计项的函数体。因此字段名是强证据，却不能被当成执行代码逐字解释。

对比赛计时必须区分两个区间：号角前的准备阶段显示负数倒计时，所以“号角前”对应一血时刻
`< 0`；号角响起后从 `0:00` 正计时，`0 <= 一血时刻 < 60` 属于“号角后一分钟内”。如果
`first_blood_before_1_minute` 按字面执行，Flayed 的内部 `Any` 配置可能把后一段也算入；但在拿到
服务器计算代码或结算观察前不能确认。Patient 的 `6_minutes` 也可能是旧 ID 而不是当前实际阈值，
所以不能只凭变量名推翻界面的 10 分钟文字。两项继续阻止发布级推荐。

项目按负责人本次提供的可见规则分别采用“号角前”和“10 分钟后”，同时把冲突保留在审计中。在获得 GC 实际结算证据前，这两个 suffix 不进入可发布的默认最优选择。`the Cruel` 的内部字段从击杀方描述为“在敌方泉水取得击杀”，与可见界面从被击杀方描述的“死在自己的泉水”语义等价，不构成冲突。

## 2. Scoring（计分流程）

### 英文原文转录

> Once matches for a period begin, a snapshot of your roster is saved and used for scoring. For each role, each player's score is calculated individually in every game they participate in. Players receive points only for the stats present on their War Banner, amplified if any of the conditions of your coach Titles are met. We then average the score of all players for a role and use that to decide the final score for a game. The top two scoring games within a series are used to get the role's final score for the match. If a role participates in more than one series in a period, the best scoring series will be used. The base amount of points for each stat are listed below:

### 通俗整理

1. 一个 Period 的比赛开始时，系统锁定当时的阵容快照；之后按这个快照结算。
2. 对每个 Fantasy role，先分别计算其中每名选手在每个 Game 的得分。
3. 一名选手只从其 War Banner 上实际存在的统计项得分；没有装到战旗上的统计项不计分。
4. 如果指导员称号的条件在该 Game 中成立，再对 Game 最终分数给予百分比加成。
5. 同一 role 包含多名选手时，取这些选手的平均分作为该 role 的 Game 分数。
6. 一个 Series 内只采用得分最高的两个 Game，形成该 role 的 Series 得分。
7. 一个 Period 内如果该 role 对应的队伍参加多个 Series，只采用得分最高的那个 Series。

第 5 步中的 core、mid、support 具体包含哪些位置并未在这些截图中重述。项目现有规则把 core 定义为 position 1/3 的平均值、mid 定义为 position 2、support 定义为 position 4/5 的平均值；这是其他客户端证据形成的项目规则，不是本批截图单独证明的内容。

### 待验证的聚合细节

- TI 2026 截图中的 “top two scoring games ... are used” 本身没有写明运算符，但同一客户端保留的通用规则文案明确写着 “add the top two scoring games”。因此项目采用求和；证据见源码调查报告。
- 如果一个 Series 只完成一个可计分 Game，截图没有说明是否仍可结算；现有实现要求至少两个非空 Game。
- 截图没有说明 prefix 与 suffix 同时触发时的叠加顺序，也没有说明称号加成与 Emblem 加成的先后顺序。
- 截图没有说明平分时如何处理；对取最大值本身通常没有数值影响，但可能影响界面归属显示。

## 3. 基础统计项与分值

下表中的数值保持客户端截图的显示单位，不做除以 100 等归一化。

| 颜色 | 客户端统计项 | 截图确认的基础计分 | 规则表达 |
| --- | --- | ---: | --- |
| Red | Kills | 每次击杀 `+107.00` | `107 × kills` |
| Red | Deaths | 初始 `1,950.00`，每次死亡 `-195.00` | 截图只确认 `1950 - 195 × deaths`；项目负责人另行规定最低为 `0` |
| Red | Creep Score | 每次正补或反补 `+3.00` | `3 × (last hits + denies)` |
| Red | GPM | GPM 乘以 `2.00` | `2 × GPM` |
| Red | Madstone Collected | 每个 Madstone `+13.00` | `13 × count` |
| Red | Tower Kills | 每次防御塔最后一击 `+352.00` | `352 × count` |
| Blue | Wards Placed | 每个放置的 observer ward `+117.00` | `117 × count` |
| Blue | Camps Stacked | 每次堆野 `+234.00` | `234 × count` |
| Blue | Runes Grabbed | 每个装瓶或拾取的神符 `+141.00` | `141 × count` |
| Blue | Watchers Taken | 每次占领 watcher `+147.00` | `147 × count` |
| Blue | Lotuses Grabbed | 每个拾取的 lotus `+176.00` | `176 × count` |
| Blue | Smokes Used | 每个使用的 Smoke of Deceit `+293.00` | `293 × count` |
| Green | Roshan Kills | 每次 Roshan 击杀 `+1,172.00` | `1172 × count` |
| Green | Teamfight Participation | 团战参与最高 `2,124.00` | 截图只确认上限；项目负责人另行定义参与率，见第 10 节 |
| Green | Stuns | 每秒眩晕 `+10.00` | `10 × stun seconds` |
| Green | Tormentor Kills | 每次 Tormentor 击杀 `+879.00` | `879 × count` |
| Green | Courier Kills | 每次信使击杀 `+703.00` | `703 × count` |
| Green | First Blood | 选手取得一血时 `1,934.00` | 条件成立取 `1934`，否则通常推定为 `0`；截图未单独写出失败值 |

截图 2 与截图 3 在 Camps Stacked 至 Lotuses Grabbed 之间有重叠；上表只保留一次，不把重复截图当成额外规则。

### 统计语义边界

- Tower Kills 明确要求防御塔最后一击，不是团队推塔参与。
- Wards Placed 明确是 observer ward，不应把 sentry ward 自动合并进去。
- Runes Grabbed 同时包括装瓶和直接拾取。
- Teamfight Participation 只给出“最高 2,124 分”，没有展示参与率的定义、分母或线性关系。
- Roshan、Tormentor 和 First Blood 的归属字段仍需与数据源做语义核验；显示规则本身不能证明 OpenDota 字段与客户端结算完全一致。

## 4. Period 奖励

### 英文原文转录

> At the end of the matches for a period, your roster's fantasy score is compared against everyone else who submitted a roster for the period. Earn points based on your performance in the group.

### 截图确认的档位

| Percentile | 奖励点数 |
| ---: | ---: |
| 100th | 12,000 |
| 99th | 11,400 |
| 95th | 10,000 |
| 90th | 8,400 |
| 80th | 5,800 |
| 60th | 3,300 |
| 40th | 1,700 |
| 20th | 400 |
| 10th | 200 |

截图中的奖励点数旁有活动货币图标，但没有显示该货币的正式名称，因此本文只称“奖励点数”。

### 待验证

- 截图只给出九个锚点，没有说明锚点之间是线性插值、阶梯档位还是其他函数。
- 没有说明低于第 10 百分位的奖励。
- “everyone else who submitted a roster” 表明排名来自实际提交阵容的人群；截图没有定义服务器、地区或其他分组边界。
- 该可见表支持 `10/20/40/60/80/90/95/99/100` 这一组客户端档位，但尚不足以解释客户端资源中并存的旧 percentile 表究竟是否仍参与结算。

## 5. Emblem Stats（徽标统计项）

### 英文原文转录

> Modifying War Banners is the primary way to influence your fantasy score. Each banner is comprised of emblems that correspond to different fantasy stats and can have their base value adjusted up or down by the emblem's quality and trait. Try and optimize your stats around the specific player you have chosen to get the best result!

> Which fantasy stat an emblem could be is controlled by the emblem's color. Rerolling the stat of an emblem will guarantee a new stat and there are no duplicate stats on a War Banner. Below is a breakdown of which stats belong to which color of emblem:

### 截图确认

- War Banner 由多个 Emblem 组成。
- 每个 Emblem 对应一个 Fantasy 统计项。
- Emblem 的 quality 与 trait 可以提高或降低该统计项的基础价值。
- Emblem 能出现的统计项由颜色限制。
- 重随一个 Emblem 的统计项时，保证得到一个新统计项。
- 同一 War Banner 上不会出现重复统计项。

| 颜色 | 可出现的统计项 |
| --- | --- |
| Red | Kills、Deaths、Creep Score、GPM、Madstone Collected、Tower Kills |
| Blue | Wards Placed、Camps Stacked、Runes Grabbed、Watchers Taken、Smokes Used、Lotuses Grabbed |
| Green | Roshan Kills、Teamfight Participation、Stuns、Tormentor Kills、First Blood、Courier Kills |

截图没有展示一个 War Banner 有多少槽位、槽位颜色排列、重随概率或是否可以在同色池耗尽时继续重随。

## 6. Emblem Quality（徽标品质）

### 英文原文转录

> Higher qualities amplify the benefit you receive from different stats. Qualities with a larger boost are more rare when crafting. Here are the available qualities and their boost to the emblem's base fantasy stat score:

| 品质 | 对基础 Fantasy 统计分的加成 |
| --- | ---: |
| Tier I | +10% |
| Tier II | +30% |
| Tier III | +60% |
| Tier IV | +100% |
| Tier V | +150% |

截图确认高品质提供更大加成、在制作时也更稀有，但没有给出各品质的抽取权重。百分比最自然的解释是相对基础分增加，例如 Tier V 的单独品质倍率为 `1 + 150% = 2.5`；这仍不能决定它与 trait、相邻徽标和指导员称号如何叠加。

## 7. Emblem Traits（徽标特性）

### 英文原文转录

> Traits will amplifying [sic] the stat bonus of emblems, sometimes dependent on certain conditions. Rerolling a trait will guarantee a different trait for that emblem. Listed below are all the available traits:

### 截图确认

- Trait 会改变 Emblem 的统计加成，其中一些需要满足条件。
- 重随 trait 时，保证得到与当前不同的 trait。
- 截图声称下列五项是全部可用 trait。

| Trait | 截图规则 |
| --- | --- |
| Fractal | 如果 War Banner 上所有 Emblem 的品质都不同，该 Emblem 的统计加成 `+60%` |
| Benevolent | 相邻 Emblem 的统计值 `+20%` |
| Vampiric | 自身 Emblem 的统计值 `+50%`，相邻 Emblem 的统计值 `-10%` |
| Unique | 如果它是该 War Banner 上唯一的 Unique Emblem，该 Emblem 的统计加成 `+30%` |
| Friendly | 如果 War Banner 上至少有 3 个 Friendly Emblem，该 Emblem 的统计加成 `+50%` |

### 待验证的 trait 计算细节

- “相邻”依赖 War Banner 的槽位拓扑。截图没有明确是否是线性相邻、首尾是否相邻，或 Main Period 新槽位怎样连接。
- 多个 Benevolent 或 Vampiric 同时影响一个 Emblem 时，效果是否相加未说明。
- quality、self trait、adjacent trait 与 Coach title 的计算顺序未说明。
- 百分比作用于“stat bonus”还是完整“stat value”的措辞并不完全一致，不能只凭截图断言所有效果都进入同一个加法倍率。
- Fractal 要求“all emblem qualities ... are different”，但截图没有说明尚未填满的 War Banner 如何判定。

## 8. 与当前项目规则的对照

对照对象：[`config/rules/ti2026.json`](../config/rules/ti2026.json) 与 [`src/ti_predictor/fantasy/scoring.py`](../src/ti_predictor/fantasy/scoring.py)。本节是审计记录，不是对实现正确性的最终裁决。

### 已一致的部分

- 18 个统计项及其 Red/Blue/Green 颜色分组一致。
- 五档 quality 的 `+10/+30/+60/+100/+150%` 一致。
- Fractal、Benevolent、Vampiric、Unique、Friendly 的条件与百分比一致。
- core/support 取角色内选手平均、Series 取两个最高 Game、Period 取最高 Series 的整体结构与截图描述相符；其中“两个最高 Game 求和”仍是项目实现补足的运算细节。
- 客户端可见奖励表确认最高奖励为 12,000，并确认当前界面显示 `10/20/40/60/80/90/95/99/100` 百分位锚点。

### 需要显式化或继续验证的部分

1. **客户端分值尺度已经采用。** 截图的 `107/1950/3/...` 曾在配置中统一缩小 100 倍。根据项目负责人 2026-08-02 的决定，配置与实现改用客户端显示分值，并用 `score_unit = client_fantasy_points` 显式声明。
2. **Deaths 的零下限是项目负责人规则。** 截图只写 `1950 - 195 × deaths`；项目负责人明确规定最低为 `0`。这是已采用的项目规则，不冒充截图原文。
3. **Teamfight Participation 使用临时项目定义。** 截图只明确最大分为 2,124。项目负责人规定在找到更高优先级证据前，参与率按 `(kills + assists) / team_total_kills` 计算，再乘 2,124 并封顶。
4. **Emblem 内加法是客户端证据支持的强推断。** 截图本身没有运算顺序；额外的客户端本地化把界面总值称为 Quality 与 Trait 的 combined score，并把 Trait 称为对 base fantasy score 的 additional percentage bonus。因此当前实现把 quality、自身 trait 与相邻 trait 的百分比相加。最终算术函数和舍入仍未找到。
5. **只有可见奖励锚点，没有完整结算函数。** 不能据此实现任意 percentile 到奖励的映射。
6. **本批截图未覆盖的现有配置。** Period 的 3/5 槽、固定槽位颜色、每期 roll 数、quality 抽取权重、具体 Coach title 清单与条件都需要引用其他来源，不能把本批截图当作它们的证据。
7. **后续 Title 截图已补齐清单。** 八个 prefix、八个 suffix、各自百分比与可见条件现由截图 S6 直接确认；其中两个一血条件仍保留与内部 `vdata` 的冲突审计。

在上述细节验证前，适合用已确认部分做候选排序或敏感性分析，但不应声称能够逐点复现客户端最终 Fantasy 分数。

## 10. 项目负责人临时规则（2026-08-02）

这些规则用于填补客户端截图没有给出公式的部分，规则版本为 `2026-08-02-owner-policy-v1`。它们可以被后续客户端源码证据或新的明确决策替换，但不得在不更新版本和文档的情况下静默改变。

- 分值单位：直接使用客户端显示的 Fantasy points，不再除以 100。
- Deaths：`max(0, 1950 - 195 × deaths)`。
- Teamfight Participation：
  - `participation = (player kills + player assists) / team total kills`；
  - `score = min(2124, 2124 × participation)`；
  - 团队总击杀为 `0` 时分母无定义，participation 保持 `null`；
  - kills、assists 或团队总击杀缺失时保持 `null`，不得当成零；
  - 不使用 OpenDota 预先计算的 `teamfight_participation` 字段。
- Emblem 内：quality、自身 trait 与相邻 trait 对 base fantasy score 的百分比相加，再形成该 Emblem 的倍率；这是客户端证据支持的强推断。
- Coach 层：先把 Emblem 分数求和，再对满足条件的 prefix 与 suffix 分别乘以各自倍率；prefix/suffix 彼此乘法是项目负责人临时规则，Valve 算术尚未找到。
- Percentile：只保存九个截图确认锚点；锚点之间及低于第 10 百分位的奖励保持 `unknown/unavailable`，不得默认线性插值。

## 9. 来源完整性

原图来自 Codex 会话附件的临时文件。由于截图不得提交 Git，仓库只保存以下指纹；如需长期保存原图，应放入明确的本地、Git 忽略原始证据目录，并保留同一 SHA-256。

| ID | 原始文件名 | 尺寸 | 内容范围 | SHA-256 |
| --- | --- | ---: | --- | --- |
| S1 | `codex-clipboard-72281a81-0d00-4a40-b44b-f7fdbb2d70c7.png` | 804×712 | Crafting Basics、Rolling、Coaching Titles | `8749298492fe5a4a73338015d42fb2d25acce1737087771fac97f251c98c3d46` |
| S2 | `codex-clipboard-86cfd8ef-63fa-43f9-8745-82caefca4e59.png` | 770×951 | Scoring 与基础统计项上半部分 | `afa9c7d8cbba8c367212786cc440a02f4ef064553b00fbead6a8afcde4b0d1cc` |
| S3 | `codex-clipboard-ac34b6fc-672a-44e7-bba0-507577ea88bf.png` | 809×1146 | 基础统计项下半部分与 Rewards | `9cf85bd183ed2f15bcda1652380c2b260efaa0a76d9d3436a77008910acb721f` |
| S4 | `codex-clipboard-1b5436aa-448f-4790-b392-e387e269aca4.png` | 783×961 | Emblem Details、Stats、Quality | `6528e90a228b8d892456d97e8e31ba203adb7a2730e3d5376e1def377e0f05ac` |
| S5 | `codex-clipboard-3ac7f456-77f6-46af-89b9-b7577d8b20f5.png` | 796×482 | Emblem Traits | `7250a0b1ab8ac3eed008e01b9c890c4b3539f3db561591a32955790c14cec3c4` |
| S6 | `codex-clipboard-2b71075a-46d6-4b31-a1bf-5984ee6e0549.png` | 1919×1111 | Change Titles：八个 prefix 与八个 suffix | `772d5955e3b25c308a17805cbeb5c3d17f3839524459c9e414343290007c942b` |
