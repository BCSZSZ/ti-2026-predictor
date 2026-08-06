# Group 40 Roll 人工手册：主模型 best-guess 版 v1

状态：**P4 v1 独立验证结果为 `draft`，不是 baseline-reliable**  
适用范围：只适用于 Group 的 3 格战旗与 40 次 Roll；不适用于 Main。  
主模型：把客户端公开的操作权重和品质权重当作当前 best guess，不声称它们就是真实后台
概率，也不在一局 40 Roll 内在线改率。三个战旗完成后才分别匹配队伍。

发布警告：冻结后的 12 条规则在主模型的 93 个 Common 情形中全部通过 10% 重大损失线，
但只有 PM05、PM12 通过规则消融；其余十条没有同时取得均值与 CVaR10 的单侧 95% 无损
证据。因此整版仍是实验性操作稿，不得标成可靠手册。详见
[P4 报告](../../reports/p4-independent-human-playbooks-2026-08-06.md)。

## 快查页 1：当前三格与主模型重随线

| 位置 | keep | 主模型下通常值得改善 | 最优先修 |
| --- | --- | --- | --- |
| Core Red | Creep Score | Deaths/GPM；Tower/Kills/Madstones 低于本色随机均值 | 无硬 C 档 |
| Core Green | Teamfight/Tormentor | Roshan；First Blood | Stuns/Courier |
| Mid Red | Creep Score/Deaths | GPM；Kills/Tower/Madstones 低于本色随机均值 | 无硬 C 档 |
| Mid Blue | Runes | Camps/Lotuses | Watchers/Wards/Smokes |
| Mid Green | Teamfight/Tormentor | Stuns/Roshan/Courier/First Blood 低于本色随机均值 | 无硬 C 档 |
| Support Blue | Camps/Wards/Watchers/Lotuses/Smokes | Runes 低于本色随机均值，但整色会毁两格 keep | 无硬 C 档 |
| Support Green | Teamfight/Tormentor/Courier | Stuns/First Blood | Roshan |

主模型品质重随后平均加成为 `44.68%`，所以只把 T1/T2 当作正期望品质重随；T3 及以上
不洗。Trait 默认顺序：品质全异且不偏置用三 Fractal；否则均衡用三 Friendly；仅当边贡献
和超过中间 3.5 倍才用 `Vampiric / Benevolent / Vampiric`。完整表及边界项见
[Stat、Quality 与 Trait 证据表](stat-quality-trait-evidence-v1.md)。

## 快查页 2：按顺序执行 12 条规则

阶段：前期 `40–26`，中期 `25–11`，末期 `10–1`。从第 1 条向下命中第一条；同条有多项
时，选择按表中指数计算的预期提升最大者。

1. **随机 +1 品质（23）**：有非全 T5 战旗就拿；优先低品质且 Stat 好的旗。
2. **绿色 C 档精确修复（31/32/33）**：Core Stuns/Courier、Support Roshan 优先。
3. **单格颜色 Stat（11/14/17）**：Mid 的每种颜色、所有旗的 Green 都只影响一格；当前
   指数低于本色六项平均时可洗，末期需至少约 5% 改善。
4. **两格整色 Stat**：Core Red 或 Support Blue 只有在两格指数合计低于两次随机重随均值、
   没有 hard-protect 且不在末期时才洗。
5. **精确品质（25/26/27）**：T1/T2 可洗；不要打散已经生效的三 Fractal 品质全异结构。
6. **整色品质（9/12/15）**：受影响格的当前品质加成合计低于每格 44.68%，且不拆三
   Fractal，前中期才用。
7. **精确蓝色 Trait（28/29/30）**：洗失效 Trait 或负协同；不拆认可套装，完整三格平均
   改善必须为正。
8. **单格颜色 Trait（10/13/16）**：Mid 单色或 Green 单格可在前中期按完整三格正期望洗；
   Core Red、Support Blue 的整色 Trait 不属于本条。
9. **二升一降（24）**：仅前期、三格均不高于 T3、任何一格贡献不超过总和 45% 时用。
10. **绿色 B 档**：前中期用 31/32/33 精确洗，但只有六项均值高于当前时执行。
11. **差一格 Trait 套装**：前中期且蓝色精确选项命中唯一缺口时追；整色不追。
12. **末期正期望门槛**：最后十次，默认要求相对代理值至少 +2%；均值优先为 >0，
    下行优先为 +5%，且都不得破坏 keep 或完整套装。

统一兜底：**没有任何一条支持应用当前三个选项时，花 1 次 Roll 刷新全部选项。**

风险修正：均值优先用 0% 最低改善并允许第 9 条；默认档用 2%；下行优先用 5% 且禁用
第 9 条。它们只是同一手册的三个小修正，不是三套额外规则。

P4 点估计支持把 2% 作为当前 knee：相对 `epsilon=0`，均值由 61,807.96 降至
61,597.75（仅 -0.34%），CVaR10 由 47,287.57 升至 48,474.64（+2.51%）；放宽到 5%
不再提高 CVaR10。该结论仍需风险覆盖规则的独立置信确认，所以不改变本版 `draft` 状态。

## 哪些结论依赖 best guess

第 3、4、6、7、8、10、12 条使用了主模型平均值；后台率若不同，方向可能改变。第 1 条的
不降级、第 2 条的 C 档修复、T1 品质重随和完整 Trait 算术不依赖操作出现频率。遇到无法
判断的组合，切换到生成率无关版，不要在本局用短样本“校准”概率。
