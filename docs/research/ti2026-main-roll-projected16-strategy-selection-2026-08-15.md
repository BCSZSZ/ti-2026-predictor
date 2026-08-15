# TI 2026 Main Roll projected 16 队策略选型结论（2026-08-15）

## 结论

在当前冻结的 projected Main release、用户提供的 30 Roll 五槽起点和预注册的
G/T/H 三个策略族上，**保留 G（`main-greedy-immediate-v1`）**。

- T（`main-target-shape-distance-v2`）在五个概率模型中的平均差值全部为负，停止。
- H（`main-horizon-hybrid-v2`）在主模型中的点估计为 `+0.143%`，但没有达到
  `+0.5%` 门槛，95% 单侧下界小于零，CVaR10 下界失败，七个确认 fold 未全部非劣，
  且五个概率模型中三个平均差值为负。
- 因此 H/T 都没有资格替换当前 Web 的一步即时建议。当前 Web 已属于 G 的
  current-screen / one-step 策略族，不需要生产代码改动。

这不是“G 对所有起点和所有真实出率全局最优”的证明。结论只表示：在本报告绑定的
release、起点、projected-derived 名单分布、内层 Main 路径和五个敏感性模型下，两个
已实现 challenger 都没有通过替换 G 的冻结门槛。

## 冻结输入

| 输入 | 冻结身份 |
| --- | --- |
| Main release | `94c00919f01395dae7f1eb371db0156cc8225c5b9aa9f5b02ccb9083d6d714c9` |
| Group Scenario | `12e6b771845c4df5b3c6da495f27a84f17ca7faf4c7264eb882b26f507b8a1c0` |
| Main Scenario | `bae9b31d109fca11cd66983156bb8edb2010f7b864f15d4fc892bdfeb1358ead` |
| Main Series pool | `6a01d321a8956211ebeb27a0537e8a311b7d6d6c6d90fb15843715901d2ed72d` |
| Team-strength model | `7cfc89b3c6dd11992315e6475856bf0d5334e1ff3854e736aaa82d4fd9218f58` |
| Rule snapshot | `9728c506baf6b5b2a706d0c70e4869fc6354c543d0cb4b911a4bf8427276bf06` |
| Research manifest | `b7ae27c63109d5ea9e56c2fc33fca5247db0817c4f02d1516a2c6075f81adcec` |
| Starting state | `ea11a7652749213b8916b67b13a8a5035f27672d80f1e455f00ff86439ff3a0c` |
| Source image | `f857aa380787e520808c934f7027b648824c812f3e60b3bddd2cdb3751ac623c` |
| OCR observation | `952e59f1adff6ba0706ed80cc8b619e651c3b92580527e786001d25a1a74e02d` |
| `as_of` | `2026-08-13T13:23:17Z` |
| 起点 Roll 数 | 30 |

当前 Main OCR 路径在参考图上确认了 3 面五槽 Banner 共 45 个字段、3 个 operation 和
30 Roll，无 warning。确认后的状态保存在
`config/research/states/ti2026-main-reference-screen-20260814.json`；研究 runner 在 tuning
和 confirmation 模式拒绝其他起点文件或不匹配的文件/语义哈希。

## 名单条件目标

本次不把 projected 16 队整体上的一次固定 Team matching 当成未来八队选择。研究面板
实现的是：

```text
E over projected-derived eight-Team rosters r
    [ max Team choices available in r
        E(score | r, independent selection paths) ]
```

关键隔离如下：

1. 冻结 Group Scenario 的 256 行全部保留，每行原始权重为 `1/256`；240 个 unique
   八队集合不去重、不重新均匀加权。
2. 固定 salt 把 256 行确定性分为 8 个 fold，每个 32 行。fold 0 只用于 tuning，
   fold 1–7 只用于 confirmation。
3. 每个外层名单分别生成 4 条 Team-selection Main 路径和 4 条独立 evaluation Main
   路径。Team 只能从该名单的八队中选择，不能看到 evaluation 路径的已实现得分。
4. confirmation 面板包含 224 个外层名单记录、1792 条内层情景；面板语义哈希为
   `52c81fcc9df72b8baaba816df4e25d27a635849201312c8d50a71d306c8120ae`。

这些名单仍是 `projected-derived` Forecast 情景，不是 actual 晋级名单，也没有写入
`main_event_seeds` 或任何 runtime pointer。

## 策略定义

| 策略 | 冻结行为 |
| --- | --- |
| G | 只比较当前三个 offer 的精确一步期望；有正向 Apply 时选即时值最高者，否则按剩余步数 refresh/stop。 |
| T | 生成有界 Q/T 目标形状，以精确期望配置距离进展加即时值选动作；`potential_weight=0.1`，不允许即时均值损失。 |
| H | 剩余 Roll `>20` 时使用 T，之后使用 G；本起点最多前 10 步进入 target mode。 |

早期 sampled-reachability T 在 16/32/64 样本下方向不稳定，因此没有进入正式候选；正式
T/H 使用确定性的 `exact-distance-potential`。这次否定的是上述具体 T/H 实现，不是否定
所有可能的长期动态规划策略。

## Tuning

Tuning 使用 fold 0 和主概率模型，共 8 个 Roll seed：

- `202608140000..202608140003`：参数搜索；
- `202608140004..202608140007`：独立候选验证。

实现优化前后两次正式 tuning 的候选屏幕逐字段相同。最终实现版 artifact：

```text
artifacts/research/main-roll-simulator/20260813T132317Z-d2522def9715
```

独立验证结果：

| Challenger vs G | mean 差值 | 相对差值 | CVaR10 差值 | 决定 |
| --- | ---: | ---: | ---: | --- |
| T | -1,134.7 | -1.513% | -817.8 | futility stop |
| H | +725.8 | +0.968% | +875.0 | advance to confirmation |

四个验证 seed 的区间仍很宽，因此 H 的 advance 只表示“值得确认”，不是最终选择。

## Confirmation

Confirmation 使用完全不重叠的 32 个 Roll seed `202608150000..202608150031`、fold 1–7
和全部五个概率敏感性模型。三个策略都完整运行，所以研究包包含
`32 × 5 × 3 = 480` 个 episode。

正式 artifact：

```text
artifacts/research/main-roll-simulator/20260813T132317Z-38c10a553698
experiment_sha256 = 38c10a5536989dd5a1b5ce61675619fd975b2ee97d67d0938a1124d4bb5c324e
report file SHA-256 = e28b0a920172b81df68833e9168515193ec478ffddcbf3478319fa511036c2c0
```

`checksums.json` 管理 483 个文件；逐文件复核为 483/483 匹配、0 mismatch。加上
`checksums.json` 本身，研究包共 484 个文件。

### 主概率模型

| 指标 | G | T vs G | H vs G |
| --- | ---: | ---: | ---: |
| terminal mean | 74,741.5 | -1,152.2 | +107.1 |
| relative mean | — | -1.542% | +0.143% |
| mean 95% 单侧下界 | — | -2,260.6 | -847.9 |
| terminal CVaR10 | 62,151.3 | -666.6 | +305.7 |
| CVaR10 95% 单侧下界 | — | -1,836.2 | -762.8 |
| win rate | — | 43.75% | 46.88% |
| tie rate | — | 0% | 12.5% |

H 的主模型点估计略高，但同时失败三项总体门槛：

- mean 单侧下界必须 `>0`，实际为 `-847.9`；
- relative mean 必须至少 `+0.5%`，实际为 `+0.143%`；
- CVaR10 单侧下界必须不低于 `-1% × |G CVaR10| = -621.5`，实际为 `-762.8`。

### 五模型敏感性

| 概率模型 | T mean 差值 | H mean 差值 |
| --- | ---: | ---: |
| client-weight-primary | -1,152.2 | +107.1 |
| flattened-weights | -699.4 | -1,070.0 |
| sharpened-weights | -621.5 | +218.0 |
| repeat-suppressed | -490.0 | -411.0 |
| correlated-multi-target | -1,036.2 | -267.5 |

T 被分类为 `stable-nonpositive`；H 被分类为 `model-dependent`。H 没有满足“五模型 mean
差值全部非负”的默认策略资格。

### 七折稳健性

冻结规则要求每个 confirmation fold 的 mean 和 CVaR10 配对差值 95% 单侧下界都不低于
该 fold G 基线的 `-1%`。结果：

- T 在七个 fold 上均未同时满足两项非劣条件；
- H 只有 fold 7 的 mean 下界非劣，只有 fold 3/6 的 CVaR10 下界非劣，没有任何证据
  支持“七折全部非劣”；
- 因此 `every_roster_fold_noninferior=false`。

## 工程验证与 Web 边界

为完成全量研究，名单条件选择从逐 roster Python 循环改为批量 NumPy 运算，并保留标量
reference 处理/核对语义；七折上的 outcome、cohort、roster 和 Team-selection plan 均逐位
差分。完整单 seed 三策略基准由 295 秒降至 40.5 秒。4-worker 与 1-worker 的三份 smoke
episode 文件 SHA-256 完全相同；正式 confirmation 用 4 workers，执行耗时约 38 分 55 秒。

所有性能修改只位于 `main_roll_research_*` 模块。研究前后以下受保护文件/指针 SHA-256
完全相同，并且这些入口没有导入 `main_roll_research`：

| 边界 | SHA-256 |
| --- | --- |
| `src/ti_predictor/web_app.py` | `3f0d3eff210fd19f5ea46046e54d9c3da59f3c8a52e2da032509a5f2a8e0b501` |
| `src/ti_predictor/fantasy/main_advisor_ui.py` | `a64169e12c7bca051d9c0046efecbb8747e25400a42b4709b2dddf09d4db2535` |
| `src/ti_predictor/cli.py` | `5184241b2fa415acf3ba36c59a31c07a84bb2984c88571f35550182c0266efb9` |
| `streamlit_app.py` | `58d85343e19db6ac89e6598fba9189c30f634bed2fa7a41eba677769d4e62dd3` |
| `local_ocr_app.py` | `82dcb2e3a80ab3fbbb5cf541980c5a2cf1be2becb1dc3844096fdf9f99bf9f3c` |
| `deploy/runtime/current.json` | `3466c66165064f608985e75779979821844514620cd1afb36331b0ad7c415802` |
| `deploy/runtime/main-current.json` | `c020a7273ea84983ddf0d9c22013f43df93f291dc8b5e9d886451659c72c7b2e` |

现有 Main Web 顾问由 `analyze_main_current_screen` 进行 current-screen one-step 估值，且
配置冻结 `future_offer_generation=false`。选择 G 因而意味着保留现状，不进行策略 promotion、
runtime pointer 写入或 Web 改造。

最终仓库验证：

- pytest 收集 289 项：288 通过、1 项按既有条件跳过；
- `ruff check .` 通过；
- `git diff --check` 通过；
- 真实本地浏览器可在 `Main（当前 · 五格）` 与 `小组赛（历史 · 三格）` 间双向切换；
  Main 显示 projected 16 队、30 Roll 和五槽状态，Group 保持独立三槽状态；
- 浏览器控制台 warning/error 为 0。

## 适用范围与后续

1. 当前结果可以用于现在的 projected 16 队阶段：Web 继续给一步即时建议。
2. actual 八队和赛后原始数据到来后，仍需生成独立 actual manifest/artifact；projected 与
   actual 结果不得合并或覆盖。
3. actual 最小复验只需比较 G 与当时仍要考虑的 challenger；但本轮没有 challenger 通过，
   默认仍是 G。若规则、Roll operation 或数据目标改变，必须重新建立研究版本。
4. 若未来要继续挑战 G，应研究真正的近似动态规划/价值函数或更广 starting-state coverage，
   使用新的 tuning/confirmation seeds；不能在本次 confirmation 上继续调 T/H。
