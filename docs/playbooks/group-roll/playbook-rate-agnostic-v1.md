# Group 40 Roll 人工手册：生成率无关版 v1

状态：**P4 v1 独立验证结果为 `draft`，不是 baseline-reliable**  
适用范围：只适用于 Group 的 3 格战旗与 40 次 Roll；不适用于 Main。  
核心原则：不假装知道后台出现率或结果率；只使用合法结果集合、Stat 分档和精确
Quality/Trait 算术。三个战旗都 Roll 完后，再分别为 Core、Mid、Support 匹配最合适队伍。

发布警告：冻结后的 12 条规则在三种验证模型的 229 个 Common 情形中有 5 个超过 10%
单侧损失上界，且只有 RA01、RA03、RA08 同时通过三模型规则消融。本文件保留原候选规则以
便审计，但目前只能作为实验性操作稿，不能宣称已经证明可靠。详见
[P4 报告](../../reports/p4-independent-human-playbooks-2026-08-06.md)。

## 快查页 1：先看当前三格

位置固定为：Core `Red / Green / Red`，Mid `Red / Blue / Green`，Support
`Blue / Green / Blue`。

| 位置 | keep（看见就保留） | conditional-reroll（有精确机会再动） | priority-repair（优先修） |
| --- | --- | --- | --- |
| Core Red | Creep Score | Deaths, GPM, Tower, Kills, Madstones | 无 |
| Core Green | Teamfight, Tormentor | Roshan, First Blood | Stuns, Courier |
| Mid Red | Creep Score, Deaths | GPM, Kills, Tower, Madstones | 无 |
| Mid Blue | Runes | Camps, Lotuses | Watchers, Wards, Smokes |
| Mid Green | Teamfight | Tormentor, Stuns, Roshan, Courier, First Blood | 无 |
| Support Blue | Camps, Wards, Watchers, Lotuses, Smokes | Runes | 无 |
| Support Green | Teamfight | Tormentor, Courier, Stuns, First Blood | Roshan |

边界项要更保守：Core Green 的 Teamfight/Roshan/First Blood/Stuns/Courier，Core Red 的
Deaths，Mid Red 的 Deaths/GPM/Kills/Madstones，Mid Blue 的 Lotuses，Mid Green 的
Tormentor/First Blood，Support Blue 除 Camps、Runes 外的四个 keep，Support Green 的
Tormentor/First Blood。完整数值见
[Stat、Quality 与 Trait 证据表](stat-quality-trait-evidence-v1.md)。

Trait 只认完整三格：品质全异且贡献不偏时追三 Fractal；否则均衡旗追三 Friendly；
`Vampiric / Benevolent / Vampiric` 仅在两边未计 Trait 的贡献和超过中间 3.5 倍时胜过
三 Friendly。单 Unique 是不能成套时的填充，不要保留两个 Unique。

## 快查页 2：按顺序执行 12 条规则

阶段：前期 `40–26`，中期 `25–11`，末期 `10–1`。每次从第 1 条向下检查；命中第一条
就用该选项。多个战旗都命中时，先修更低 Stat 档，再修更低品质，再修 Trait。

1. **随机 +1 品质（操作 23）**：只要有战旗不是全 T5 就拿；优先给低品质且 Stat 较好的旗。
2. **绿色 C 档精确修复（31/32/33）**：Core 的 Stuns/Courier、Support 的 Roshan 先洗。
3. **Mid 单格 C 档修复（11/14/17）**：对应颜色在 Mid 只有一格；先洗蓝色
   Watchers/Wards/Smokes。
4. **整色 Stat（11/14/17）**：Core 的两 Red 或 Support 的两 Blue 必须两格都是
   priority-repair 才用；只要会碰到 keep 就跳过。
5. **精确品质 T1（25/26/27）**：只洗 T1；随机同色一格时也要确认可能命中的格都是 T1。
6. **整色品质（9/12/15）**：受影响的格全部 T1 才用。
7. **精确蓝色 Trait（28/29/30）**：只清理未触发 Friendly/Fractal/重复 Unique；不拆完整
   套装，且目标格贡献至少是相邻格的 20%。
8. **末期保护**：最后十次只拿操作 23、洗类别最差 Stat、洗 T1 品质或满足第 7 条的失效
   Trait；其余刷新。
9. **绿色 B 档**：前中期可用 31/32/33 精确洗稳定的 conditional-reroll；边界项默认不洗。
10. **精确品质 T2**：前中期可洗 T2，但不能打散已生效的三 Fractal 品质全异结构。
11. **差一格的 Trait 套装**：前中期，只有蓝色精确选项命中唯一缺口时才追；整色不追。
12. **二升一降（操作 24）**：只在前期、三格均不高于 T3、且任何一格未计 Trait 贡献不
    超过总和 45% 时使用。

统一兜底：**没有任何一条支持应用当前三个选项时，花 1 次 Roll 刷新全部选项。**

风险修正不复制规则：均值优先可在前期放宽边界 B 档；默认档按上文；下行优先禁用第 12
条并把边界项都当作上一档保护。这里没有“本局在线学习生成率”。

P4 点估计风险前沿中，`epsilon=1%` 将均值从 54,361.79 降到 53,849.25，同时把 CVaR10
从 40,391.58 提到 40,802.25；`epsilon=2%` 的 CVaR10 更高（40,894.44），但均值进一步
降到 53,421.62。故本版的保守 knee 暂记 1%，追求更强下行保护时显示 2%；两者都只是
点估计，尚未作为通过消融的风险覆盖规则发布。

## 这版与主模型版的差别

这版不会因为“随机重随的平均值看起来更高”就应用操作；它要求 T1、类别底部、失效 Trait
或完整结构条件能由合法结果集合直接解释。因此刷新更多、上行可能较低，但不依赖客户端权重
等于真实后台概率的假设。
