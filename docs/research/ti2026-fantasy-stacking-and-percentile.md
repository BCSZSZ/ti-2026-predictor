# TI 2026 Fantasy 叠加、聚合与百分位规则调查

## 调查状态

- 调查日期：`2026-08-02`
- 范围：Fantasy 的 Emblem/Coach 加成、Series 最高两局、百分位奖励与 Teamfight Participation。
- 本机客户端：`ClientVersion=6882`、`ServerVersion=6882`、`SourceRevision=10875429`、`VersionDate=Jul 31 2026`。
- Steam manifest build ID：`24503204`。
- 客户端标识来源：`C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\steam.inf` 与 `C:\Program Files (x86)\Steam\steamapps\appmanifest_570.acf`。
- 已保存的客户端规则快照：`data/raw/rules/20260801T123258Z-bf12ece4a64b/`，其中 `rule_snapshot.json` 记录 build `6882:10875429`。
- 当前 `pak01_dir.vpk` SHA-256：`be4f38aeec64fb84de73e11be98a6f159e6b7438d01a0bfad012f139ccbfc6db`。
- 当前 `client.dll` SHA-256：`d0ee9df6556a49e55046bb46b689944abeb70cadc8e0ab97364d714e039df319`。

本文使用三种结论等级：

- **已证明（exact）**：当前客户端资源、当前客户端界面或协议字段直接表达该规则。
- **强推断（strong inference）**：多个一手证据一致支持，但没有找到最终算术函数本体。
- **未找到（unknown）**：当前公开/本机可读取资源不足以确定，不能冒充 Valve 规则。

## 结论摘要

| 问题 | 结论 | 等级 |
| --- | --- | --- |
| Series 的最高两局如何合并 | 将同一 Series 内得分最高的两个 Game **相加** | 已证明（规则文案） |
| Quality、self trait、相邻 trait 如何叠加 | 先合成为该 Emblem 的一个总百分比；现有证据更支持百分比**相加** | 强推断 |
| Emblem 与 Coach 的层次 | 先得到逐项 Emblem 分，再由满足条件的 Coach title 增加该选手的最终 Game 分数 | 已证明到层次，具体算术顺序未完全证明 |
| Prefix 与 suffix 同时触发 | Valve 算法未找到；项目 owner 暂定分别作为乘法因子 | 未找到；owner 临时约定 |
| 九个 percentile 锚点之间如何映射奖励 | 未找到 TI 2026 的中间映射函数；不得擅自线性插值 | 未找到 |
| Teamfight Participation | `(选手击杀 + 选手助攻) / 本队总击杀` 与 Valve replay 字段逐人吻合 | 强推断；owner 临时公式 |

## 1. Series 的 top two scoring games

### 直接证据

当前客户端英文资源同时保留两条规则文案：

- `data/raw/rules/20260801T123258Z-bf12ece4a64b/resource/localization/dota_english.txt:45056` 明确写着：`We then add the top two scoring games within a series to get their final score.`
- 同文件 `:52451` 的 TI 2026 专用文案写着：`The top two scoring games within a series are used to get the role's final score for the match.`

第一条明确使用 `add`，第二条把计算对象从单名选手改成 2026 的 Fantasy role，但没有提出另一种聚合运算。当前客户端截图也显示了第二条文案。

因此项目应采用：

```text
series_score(role) = highest(game_scores) + second_highest(game_scores)
```

通俗例子：一个 BO3 中某个 role 的三局分数分别为 `1,200 / 900 / 600`，最终 Series 分数为 `1,200 + 900 = 2,100`；第三局的 `600` 不计入。它不是三局平均，也不是只取最高一局。

TI 2026 文案还规定：先分别算 role 内每名选手的单局分数，再求该 role 的选手平均分，最后在 Series 内选择两个最高的 role Game 分数。若一个 Period 内参加多个 Series，再取其中 Series 分数最高者。

### 尚未覆盖的边界

客户端文案没有说明只完成一局、取消局或缺失统计的 Series 如何处理。该边界仍应保持 `unknown`，不得把缺失值当成零。

## 2. Emblem 内部的 quality、trait 与相邻效果

### 已证明的数据结构

`data/raw/rules/20260801T123258Z-bf12ece4a64b/scripts/fantasy_crafting.vdata:379-444` 定义：

- 五种 shape behavior：`UniqueQualities`、`AdjBonus`、`StealBonus`、`OnlyOne`、`NeedMultiples`；
- 五档 quality bonus：`10 / 30 / 60 / 100 / 150`。

对应资源 SHA-256 为 `23a2f198c0ddb1632ae3d2a95592ede2397e77bbc2bcd1b8a7a826244aaae76c`。

客户端本地化提供了更关键的运算语义：

- `dota_english.txt:44892-44893` 把界面值命名为 `+{d:total_stat_value}%`，说明为 `Total combined score of Quality and Trait`；
- `:45047` 说明 Quality 是对 base fantasy score 的 percentage bonus；
- `:45048` 说明 Trait 是对 base fantasy score 的 **additional percentage bonus**。

当前 VPK 内部资源 `panorama/layout/events/international_2026/international_2026_fantasycraft_tablet.vxml_c` 解出后，在 XML 第 18、24、29 行分别绑定：

- 单一的 `{d:total_stat_value}%`；
- quality 的 `+{d:quality_quality_amount}%`；
- trait/shape 的 `{s:shape_quality_amount}`。

这说明客户端先把 Quality 和 Trait 汇总成一个 Emblem 总百分比用于显示。

### 强推断：Emblem 内采用加法汇总

最符合上述一手证据的临时公式是：

```text
emblem_bonus_pct[i]
  = quality_pct[i]
  + active_self_trait_pct[i]
  + sum(adjacent_effect_pct[j -> i])

emblem_score[i]
  = base_stat_score[i] * (1 + emblem_bonus_pct[i] / 100)
```

例如，一个 Tier II Emblem（`+30%`）自身 Vampiric（`+50%`），左侧又受到 Benevolent（`+20%`），右侧受到另一个 Vampiric（`-10%`），则强推断下总加成为：

```text
30 + 50 + 20 - 10 = 90%
```

其倍率为 `1.90`，而不是把四个因子全部连乘。

这仍是**强推断而非 exact**：`vdata` 只给枚举和 bonus 数字；Panorama XML 只显示 native runtime 已计算好的 `total_stat_value`。没有找到执行加减乘除、多个相邻效果处理或舍入方式的公开函数体。

### 相邻关系

同一 `vdata` 把 War Banner 槽位按 `1..5` 顺序定义，操作目标中还区分 `First` 与 `Last`。结合界面布局，“相邻”最合理地解释为线性槽位 `i-1` 与 `i+1`、首尾不环绕；但没有找到一句正式规则把拓扑写成公式，因此该点也是强推断。

## 3. Coach prefix 与 suffix

### 已证明的层次

`dota_english.txt:52454` 明确说明：

- Coach 由 prefix 和 suffix 构成；
- 每个 title 在条件满足时，对一个 Game 的 **final score** 提供 percentage increase；
- 它适用于阵容中的所有选手。

结合 `:52451` 的顺序，最自然的执行层次是：先计算每名选手在 War Banner 上各 Emblem 的分数，再对该选手的最终 Game 分数应用其已满足的 Coach 条件，然后才在 role 内做选手平均。

### 未找到的部分与 owner 临时约定

没有找到以下算术细节：

- prefix 与 suffix 同时触发时，是 `p + s` 后形成一个倍率，还是两个倍率相乘；
- Coach 与 Emblem 之间是否存在中间舍入；
- 多个条件相关字段的服务端判定和最终取整方式。

按照项目 owner 当前决定，在有新证据前采用：

```text
player_game_score
  = sum(emblem_scores)
  * (1 + triggered_prefix_pct / 100)
  * (1 + triggered_suffix_pct / 100)
```

未触发的 title 对应倍率为 `1`。这条“prefix/suffix 分别相乘”是**项目临时规则**，不是 Valve 已确认规则，配置和报告必须保留这一 provenance。

## 4. Percentile 奖励锚点之间的映射

### 已证明的 TI 2026 可见锚点

当前客户端截图确认九个锚点；归档见 `docs/fantasy-client-rules-screenshots-2026-08-02.md:129-137`：

| Percentile | Points |
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

`dota_english.txt:52416-52424` 同时确认客户端使用 `10/20/40/60/80/90/95/99/100` 这些 tier 名称。

### 为什么不能据此线性插值

VPK 内部的 `international_2026_fantasyhelp_popup.vxml_c` 解出后，其第 36-40 行仅定义运行时占位符 `reward_row_name` 与 `reward_row_value`，第 137-145 行只提供奖励表容器。XML 没有中间函数。

当前客户端协议中的 `CMsgDotaFantasyCraftingUserData.PeriodScore` 直接从 GC 返回 `total_score` 和一个 `float percentile`。可读协议参照 OpenDota 官方源码快照：

- [`dota_gcmessages_client_fantasy.proto:344-381`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/proto/dota_gcmessages_client_fantasy.proto#L344-L381)

这意味着“原始分数如何换算 percentile”至少有一部分位于 Valve GC，而不是帮助页 XML。

本机 `scripts/events/fantasy/dpc_fantasy_period_pointscore.eventactions:10-101` 确实展示了旧/通用的离散区间：`1-250`、`251-500`、…、`991-1000`。但它：

- 使用旧的 `25/50/75/90/95/99/100` 区间；
- 同时定义三套 Period，而 TI 2026 当前只有 Group 与 Main 两个 Period；
- grant 数值与 2026 截图的九个 points 锚点不一致。

因此该文件只能证明客户端资源中存在一种**旧的阶梯式 action 表**，不能证明 TI 2026 九锚点如何处理中间 percentile。

### 结论

TI 2026 的任意 percentile 到奖励 points 的函数为 **unknown**。例如第 94 percentile 究竟取 90th 的 `8,400`、在 90th 与 95th 之间插值，还是走服务端其他规则，现有证据无法区分。

在获得实际结算样本或更新后的 Valve 资源前：

- 不得实现或宣称线性插值；
- 不得拿旧 eventactions 表替代 2026 表；
- 推荐优化原始 Fantasy 分数，并把奖励换算保持为 `unavailable`；
- 若业务必须展示区间结果，应明确写成项目临时 policy，并与 Valve 规则分开。

## 5. Teamfight Participation

### Valve 客户端能直接证明的内容

`scripts/events/international_2026.eventdef:1017` 定义该 Fantasy stat 的满分系数为 `2124`。客户端帮助文案只说“最高 2,124 分”，没有给出百分比的分子和分母。

OpenDota 官方 parser 并不自行计算该值，而是直接读取 Valve replay entity 属性 `m_flTeamFightParticipation`：

- [`Parse.java:661-665`](https://github.com/odota/parser/blob/84a102cdbed848ec514a586ae1e1ada802fdc79e/src/main/java/opendota/Parse.java#L661-L665)

### 强推断验证

使用 OpenDota 官方仓库 commit `2d67379fbba90b2fd015c6f0f4080d394a5741e9` 中 match `7490235544` 的 API 与 parsed fixtures 逐人核对：

- Radiant 本队总击杀为 `30`；例如 `10 kills + 10 assists` 对应 replay 值 `0.6666667`，即 `20/30`；`5 + 22` 对应 `0.9`，即 `27/30`。
- Dire 本队总击杀为 `7`；例如 `0 + 4` 对应 `0.5714286`，即 `4/7`；`2 + 4` 对应 `0.85714287`，即 `6/7`。
- 十名选手全部吻合，最大差异仅为 float 表示误差约 `3.4e-8`。

Fixtures：

- [`7490235544_api.json`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/json/7490235544_api.json)
- [`7490235544_parsed.json`](https://github.com/odota/core/blob/2d67379fbba90b2fd015c6f0f4080d394a5741e9/json/7490235544_parsed.json)

因此项目 owner 给出的公式与 Valve replay 字段具有很强的一致性：

```text
teamfight_participation
  = (player_kills + player_assists) / team_total_kills

teamfight_points
  = 2124 * clamp(teamfight_participation, 0, 1)
```

第一式应标为 **strong inference / owner-defined until updated**，而不是 Valve 源码已证明。若 `team_total_kills == 0`，当前证据没有定义行为；按照仓库缺失值规则应保持 `null/unavailable`，不得猜成零。

## 6. 为什么没有得到完整“Dota 2 源代码公式”

Valve 官方 GitHub 的两个相关仓库并不包含 Dota 2 生产客户端或 GC 源码：

- [ValveSoftware/Dota2-Gameplay](https://github.com/ValveSoftware/Dota2-Gameplay) 明确是 Public Bug Tracker，代码树只有 `.github` 与 README 等跟踪文件。
- [ValveSoftware/Dota-2](https://github.com/ValveSoftware/Dota-2) 是 Linux/macOS Reborn 客户端问题跟踪器。

本机 `client.dll` 字符串能看到内部源文件名 `dota_fantasy_crafting_schema.cpp`，但编译产物没有公开该文件的函数体。协议还表明最终 Tablet `score`、`best_series` 和 Period `percentile` 由 GC 数据返回。这就是 Emblem 最终算术、Coach 双 title 叠加和 percentile 中间函数无法从公开 Valve 源码核实的边界。

## 7. 当前可执行约定

在 Valve 更新规则或项目获得可差分的实际结算样本前，建议把当前版本记录为：

1. role 内先计算每名选手的 Game 分数；Emblem 的 quality、自身 trait 与线性相邻影响按百分比加法形成 `total_stat_value`（强推断）。
2. owner 临时规定：满足条件的 prefix 与 suffix 分别作为乘法因子作用于该选手最终 Game 分数（未获 Valve 证明）。
3. role 内选手得分取平均；Series 内最高两个 Game 分数求和；Period 内取最高 Series。
4. Teamfight Participation 暂按 `(kills + assists) / team total kills`，本队零击杀时保持 `null`。
5. 百分位奖励只保存九个已知锚点；任意中间 percentile 的奖励保持 `unavailable`，不得插值。

这些约定应带独立规则版本和 provenance。今后若客户端 build、GC 结算样本或 Valve 公告提供相反证据，应通过新的规则版本修改，而不是覆写本报告的历史结论。
