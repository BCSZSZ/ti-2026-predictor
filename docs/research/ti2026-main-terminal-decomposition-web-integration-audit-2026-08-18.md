# TI 2026 Main 终局分解与 Web 接入审计

- 审计日期：2026-08-18
- 数据截止：`2026-08-16T15:31:30Z`
- 用户终局截图时间：`2026-08-17T15:01:22.565545Z`
- 截图 SHA-256：`51d9fa7f5e641be7d8e62b7dc6ea755046f1c21b402dd491d29622ea63480b36`
- 条件化研究证据：`artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b`
- 证据 manifest SHA-256：`e43bfaaad33cc4e3be7428d45548e66a83baabe8a7d0d23148ba74a9c5a936dd`
- 本次边界：只调查、复现和形成接入计划；没有修改 Web、求解器、发布包或 runtime pointer

## 结论

用户提出的“两阶段”方向合理，但需要做一处重要修正：

1. **Roll 尚未结束时**，Title 可以不进入 Roll 目标；当前正式 G 本来就是这样做的。
2. **Roll 尚未结束时，不建议把 Team 固定成一套通用最优答案。** Team 对不同 Stat 的历史表现分布不同，
   固定 Team 会改变一次重随的边际价值。当前 256 情景快速 terminal 已经会对每个候选旗帜重新选择 Team，
   这个能力应保留。
3. **Roll 结束时**，不再计算动作，只对最终 15 格运行一次完整双败条件化 terminal，得到当前冻结模型下的
   Banner-specific Team 最优解；随后再用选中的 Team 和各位置基础贡献计算 Title。
4. 这里的“终局最优”仍是当前冻结模型下的高精度参考，而不是未来赛果意义上的客观真值。当前 Title 又只有
   边际触发率，因此只能称为“现有 Title 模型内的最优”，不能称为已联合模拟验证的绝对最优。

建议的实际路由是：

```text
剩余 Roll > 0
  -> 当前轻量 256 情景 terminal
  -> 每个候选结果都重新选 Team
  -> G / G-Lite 给动作
  -> Title 不进入动作价值

剩余 Roll = 0
  -> 不要求也不伪造三个 Roll offer
  -> 完整或经验证压缩的条件化终局 terminal
  -> 按最终三面旗帜重新选 Team
  -> 再计算 Title 边际推荐
```

这比“通用 Team + 通用 Title 先代入”更准确，同时把昂贵计算限制在每局最后一次。

## “每条路径 16 个 Fantasy 样本”是什么

它不是 16 名选手、16 支队伍，也不是整个研究只用了 16 场历史比赛。正确含义是：

1. 外层先固定一条完整双败路径。八队双败树共有 14 个 Series，因此全部胜负组合为
   `2^14 = 16,384` 条路径。
2. 一条路径只说明每轮谁赢、谁输，还没有说明每个 BO3/BO5 打了几局，也没有说明选手在每局打出什么
   Fantasy 数据。
3. 对同一条路径，内层独立生成 16 个“可能发生的具体比赛版本”：
   - 已知路径赢家后，按冻结的单局胜率抽合法比分序列；BO3 可能是 2–0 或 2–1，BO5 可能是
     3–0、3–1 或 3–2；
   - 对阵双方共享同一 Series 长度，每局胜负严格相反；
   - 按 Team、BO 格式、Series 胜负和对手强度带选择历史 Series 来源池；
   - 每个未来 Game 再从符合该局胜负的历史 Game 模板中抽取；同一队同一局五名当前阵容选手来自同一个
     历史 Game，保留队内 Core/Mid/Support 的联合波动；
   - 一个 Game 模板携带五名选手的 18 项 Fantasy Stat 原始得分。
4. 整个 16-sample 面板又用 3 个独立随机种子重做，以检查队伍排名是否被某个随机种子偶然翻转。

因此总面板为：

```text
16,384 条完整 bracket 路径
× 16 个内层具体比赛版本
× 3 个独立 seed
= 786,432 个加权情景
```

同一路径的 16 个样本等权；不同路径按冻结 Team-strength 模型给出的路径概率加权；三个 seed 再等权合并。
`16` 是在计算预算和内层抽样方差之间冻结的重复次数，不是历史数据量。历史来源池本身来自 4,555 场
正权重 Fantasy evidence，并进一步筛成 358 个当前阵容完整联合 Series、863 个联合五人 Game 模板。
TI 小组赛与突围赛在该 evidence 中使用 1.5 倍阶段权重。

## Banner、Team、Title 当前怎样相互影响

### 当前正式实现的依赖方向

```text
Banner 的五个 Stat / Quality / Trait
  -> 各 Team 在该位置的情景得分
  -> 自动选择 Team
  -> 三个位置的基础贡献权重
  -> Title 边际推荐
```

具体关系如下：

| 关系 | 当前实现 | 影响 |
| --- | --- | --- |
| Banner -> Team | 有，而且每个候选 Roll 结果都会重选 | 强；不同 Team/选手的 Stat 结构不同 |
| Team -> Banner 动作价值 | 有 | 候选 Banner 最终由哪支 Team 使用，会改变该动作的期望增益 |
| Team -> Title | 有 | Prefix/Suffix 触发率按选中 Team×role 的历史池计算 |
| Banner -> Title | 间接有 | Banner 改变三个位置的基础贡献，从而改变 Title 汇总时的 role 权重 |
| Title -> Roll 动作 | 无 | 当前 G/G-Lite 都没有把 Title 放进动作分值 |
| Title -> Team | 无 | 当前先选 Team，后展示 Title；没有做 Team×Title 联合优化 |

默认 `mean-first` 下，Team 以每个位置的 Mean 第一为目标。非零 mean-retention epsilon 的风险档位还会在
三位置合计均值约束内用联合 CVaR 决胜，因此三个位置在该模式下不完全独立。

### 哪些可以离线先算

可以一次性离线冻结，而且不随玩家旗帜改变的部分：

- 16,384 条双败路径及其概率；
- 每条路径的 BO3/BO5 比分序列样本；
- 未来 Game 对应的历史五人模板引用；
- 每个模板中五名选手的 18 项原始 Stat；
- Team、赛制、赛果和对手强度的条件化回退记录。

玩家点击时只需要把当前 Banner 的五个 Stat 和 Trait/Quality 倍率作用到这份冻结证据上，不需要重新模拟
bracket，也不需要重新抽历史比赛。

### 哪些不能精确拆开后简单相加

Fantasy 结算包含两个非线性步骤：

```text
Series 分数 = 该 Series 各局综合 Banner 分数的 Top 2 之和
阶段分数 = 该 Team 所有 Series 分数的最大值
```

因为“Top 2”和“最大值”取决于五个 Stat 合成后的整局分数，不能先分别算出 18 个 Stat 的期望，再把
五个 Stat 的期望简单相加。可以预生成静态原始证据并在 Web 中快速向量化重评分，但不能把任意 Banner
压缩成 18 个互不影响的标量期望而仍保持完全精确。

Team 也不能永久先算成一支通用答案：Banner 的 Stat 变化后，Team 排名可能改变。Title 则可以在最后算，
因为它可以免费修改，且当前证据没有进入 Roll 目标。

## 终局截图 Bug 的确定原因

对用户提供的终局截图运行当前 `RollScreenReader`，结果为：

- 15 枚 Emblem 的 `Stat / Quality / Trait` 共 45 个字段全部确认正确；
- 状态仍为 `incomplete`；
- 缺失字段只有 `offer.0`、`offer.1`、`offer.2`、`remaining_rolls`；
- 画面实际显示 `No Roll Tokens Available`，且客户端已隐藏三个 Roll offer。

当前代码有三层不兼容：

1. `_parse_remaining` 只识别 `Roll Tokens: N`/中文数字形式，不把
   `No Roll Tokens Available` 识别为 `0`；
2. `parse_roll_screen_tokens` 对任何状态都无条件要求三个 offer；
3. `MainRollState` 与 `validate_main_state` 即使在 `remaining_rolls=0` 时也强制要求合法 `RollOffer`。

因此这不是 Banner OCR 失败，而是状态契约没有表示“终局无 offer”这一种真实客户端状态。手动 Streamlit
也存在同一语义问题：即使剩余次数填 0，表单仍要求三个互不相同的 offer。

不建议在公开 payload 中伪造一组三选项。推荐新增独立的 `MainTerminalState`（三面 Banner、
`remaining_rolls=0`、无 offer），或等价的明确终局观察类型；Roll 状态仍保持三个 offer 的严格契约。

## 用户终局画面的量化对照

研究输入已冻结为：
`config/research/states/ti2026-main-zero-roll-screen-20260818.json`。

### 当前正式 256 情景 terminal

为了只验证现有零步分析路径，诊断时临时在内存中提供了一组合法但不参与计算的 offer。结果为：

| 位置 | Team |
| --- | --- |
| Core | Team Spirit |
| Mid | Nigma Galaxy |
| Support | TEAM VISION |

- Mean：`86,618.163`
- CVaR10：`70,964.630`
- Title：`Elemental + the Clutch`
- Title 纸面边际加成：`4.5960%`

这与截图上已经选择的三支 Team 和 Title 一致。当前发布包为 337,862 bytes、256 个情景；本机加载共享
Group+Main context 约 0.256 秒，终局首次分析约 0.0074 秒，缓存命中约 0.0006 秒。用同一画面模拟一组
尚有 1 次 Roll、7 个合法动作的 G 计算，首次约 1.37 秒、缓存后约 0.30 秒。

### 完整条件化研究 terminal

对同一最终 15 格运行 786,432 加权情景：

| 位置 | 第一名 | Mean | 当前 256 选择在完整证据中的位置 |
| --- | --- | ---: | --- |
| Core | **Team Falcons** | 31,562.966 | Team Spirit 第 4，29,750.697 |
| Mid | **Nigma Galaxy** | 25,419.727 | 同第一名 |
| Support | **TEAM VISION** | 34,783.171 | 同第一名 |

- 三位置合计 Mean：`91,765.865`
- 联合 CVaR10：`71,621.359`
- 三个独立 seed 都选择 `Falcons / Nigma / Vision`
- 解 SHA-256：`586211f2d1046f1fa74131c93c93f388a75c002da34b293324cdbcc51610fbd7`

两个 terminal 的情景定义不同，绝对分数不能直接相减来声称提升；可比较的是同一 Banner 下的 Team 排名。
本例中通用/旧代理 Team Spirit 的 Core Mean 比完整证据第一名 Falcons 低约 5.74%，直接说明固定通用 Team
可能影响 Roll 选择。

完整证据 v1 有意排除了 Title。若只在完整证据选出的 Team 和 role Mean 上套用当前独立 Title 边际模型，
结果为：

- Prefix：`Otherworldly`，纸面边际 `2.2775%`；
- Suffix：`the Clutch`，纸面边际 `2.8898%`；
- 简单相加约 `5.1673%`。

这只能称为当前边际 Title 模型内的下游推荐。它从截图的 `Elemental` 变为 `Otherworldly`，也说明 Title
确实会受最终 Team 和三个位置贡献权重影响。

## 最新静态证据为什么还没有进入 Web

研究 manifest 明确写明：

- `research_only: true`
- `web_integration: false`
- `runtime_pointer_writes: false`

当前本地 Web 与 Streamlit 仍共同读取：

- `deploy/runtime/main-current.json`
- `deploy/runtime/releases/main-roll-20260816T153130Z-b2a9f1af5835.json.zst`

它们使用实际八队和最新 Main Fantasy 数据，但 terminal 仍是 256 情景快速代理。最新完整条件化证据目录约
87,461,222 bytes（约 83.4 MiB），单个终局状态现有研究入口约需 9–10.5 秒，并且每次都会解压/装载研究
数组。直接把研究目录原样塞进 Streamlit，会增加分发体积、冷启动内存和每次点击延迟；若让 G 为大量候选
Banner 反复调用它，压力更大。

“静态证据”指未来情景和原始 Stat 已冻结，不等于所有玩家都共享一个静态 Team 答案。Banner-specific
重评分仍然必须发生，但可以在不重新模拟比赛的前提下完成。

## 推荐的低负载接入方案

### 1. 保持两个职责不同的 terminal

- `RollTerminal`：继续使用小型 256 情景或后续经验证的轻量面板，服务 G/G-Lite；每个候选 Banner
  自动重选 Team。
- `FinalLineupTerminal`：只在 `remaining_rolls=0` 或用户点击“高精度终局复核”时调用；使用完整条件化
  证据或其经验证压缩版，输出三个位置的八队完整排名。

两者必须使用不同的证据 ID、状态 hash 和显示标签，不能把快速代理结果冒充完整条件化结果。

### 2. 单独构建可发布的终局证据包

不要直接让生产 Web import `main_conditional_truth.py` 或读取 research 目录。应从冻结 manifest 生成一个新的、
内容寻址、只读、无原始数据/OCR 的 portable release。推荐先构建确定性加权压缩面板：

- 从 786,432 加权情景中按冻结规则做分层/系统抽样，保留完整 bracket 暴露量、BO5 和 Team 条件；
- 每条保留情景仍引用联合五人 Game 模板，不把 18 个 Stat 拆成可错误相加的边际均值；
- 目标规模可先比较 4,096 与 8,192 情景；
- 用合法随机 Banner、极端 Banner、已观察 Banner 和本终局 Banner 对完整 786,432 面板做差分；
- 冻结 Team 第一名一致率、Mean 相对误差、CVaR 误差和最小名次间隔门槛后，才能标为 Web-ready。

这里验证代表性 Banner 的意义只是证明“压缩版没有破坏完整真值”，不是重新训练策略，也不是因为每个玩家
都需要单独模拟未来比赛。

如果不接受任何压缩误差，也可以把 83.4 MiB 完整包作为 GitHub Release asset，在进程启动时一次性加载并
缓存；但 Streamlit 冷启动和单次 9–10.5 秒延迟必须明确接受。对于“降低 Web 压力”目标，压缩终局面板更合适。

### 3. 修正终局状态与 OCR 路由

1. 从当前 Valve 客户端冻结字符串中登记英文及中文“无 Roll token”终局文案；
2. 15 格确认且命中终局文案时，生成 `MainTerminalState`，不要求 offer；
3. 剩余次数大于 0 时仍必须确认三个 distinct offer，不能放宽现有安全门槛；
4. 本地 Web 的 OCR 终局观察直接进入 `FinalLineupTerminal`；
5. Streamlit 云端不带 OCR，手动表单在剩余次数为 0 时隐藏/禁用 offer，并提供“计算最终 Team 与 Title”；
6. 两端对同一个手动终局 JSON 必须给出相同 Team 排名和 Title。

### 4. Title 保持最后一步

终局流程应先使用高精度 terminal 选 Team，再调用现有 Title evidence：

```text
最终 Banner
  -> 每个 role 的八队完整排名
  -> 选中三个 Team
  -> 用最终 role Mean 形成权重
  -> Prefix / Suffix 边际排名
```

在尚未生成 Prefix/Suffix 逐局联合触发证据前，不把 Title 加成写回完整条件化 Mean，也不让它反向改变 Team
和 Roll 决策。若以后要做严格联合最优，必须另建 player-level Title trigger panel；那是独立研究，不应阻塞
本次低负载终局接入。

### 5. 运行时缓存

- Streamlit 用 `st.cache_resource` 按 release SHA 一次加载终局证据；
- 进程内按 Banner semantic hash 缓存 `TeamOutcomeMatrix`；
- 按三面 Banner 的 state hash 缓存最终排名和 Title；
- 不在每次按钮点击时重新解压完整 `.npz`；
- 发布指针更新后自然形成新 cache key，避免旧新数据混用。

## 实装与验证顺序

1. **先修终局状态契约**：加入无 offer 的终局类型和最小 token fixture；不改剩余 Roll > 0 的路径。
2. **修本地 OCR**：用本截图复现的 terminal token 结果验证 45/45 Banner 字段、0 Roll、无 offer。
3. **修手动 UI**：本地与 Streamlit 在 0 Roll 时不再要求三项 offer。
4. **生成 portable final release**：从 manifest `e43bf...36dd` 派生，保留完整来源 hash 与抽样规则。
5. **差分验证压缩面板**：与 786,432 情景全量 terminal 比较后再决定 4,096、8,192 或完整包。
6. **接入双 terminal 路由**：Roll > 0 保持当前 G/G-Lite；Roll = 0 才走高精度终局。
7. **两端一致性测试**：同一终局 JSON 在本地 OCR、本地手动和 Streamlit 手动得到相同结果。
8. **性能门槛**：分别记录冷加载、首次终局、缓存终局、G 首次和 G 缓存延迟；不能只报告总测试通过。
9. **发布隔离**：终局 release 先用独立 pointer 灰度，不覆盖当前 `main-current.json`；验收后再决定是否合并
   schema。

建议的终局 golden case 就是本次截图：完整证据下必须得到
`Team Falcons / Nigma Galaxy / TEAM VISION`；当前边际 Title 模型必须得到
`Otherworldly / the Clutch`。该 golden 只绑定上述 evidence manifest 和状态 SHA，不随未来数据静默变化。

## 证据位置

- 当前 Web Main UI：`src/ti_predictor/fantasy/main_advisor_ui.py`
- 当前 Main G/G-Lite 与 Team/Title 顺序：`src/ti_predictor/fantasy/main_current_advisor.py`
- 当前 Main Roll 状态契约：`src/ti_predictor/fantasy/main_roll.py`
- 当前 OCR 解析：`src/ti_predictor/fantasy/live_ocr.py`
- 完整双败条件化研究实现：`src/ti_predictor/fantasy/main_conditional_truth.py`
- 完整证据结果说明：`docs/research/ti2026-main-conditional-truth-result-2026-08-17.md`
- 本次终局状态：`config/research/states/ti2026-main-zero-roll-screen-20260818.json`
- 本次终局解：
  `artifacts/research/main-conditional-truth/2026-08-16-b3938fc0220b/solutions/efbe026895b5.json`
