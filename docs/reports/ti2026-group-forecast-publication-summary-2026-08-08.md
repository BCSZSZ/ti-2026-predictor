# TI 2026 小组赛最终预测：易懂总结

完整版本见 [综合实力排名与胜负关系](ti2026-group-forecast-publication-2026-08-08.md)，当前版本的
逐场依据见 [7.41 系列赛证据展开](ti2026-group-current-patch-series-evidence-2026-08-08.md)。

## 先接受模型的真实水平

正式模型在上一届 TI 的 144 局留出比赛上猜对 56.25%，相对理论上的 50% 随机猜测只高 6.25
个百分点。这说明它能提供一点方向，但远远不足以把 52% 和 48% 当成确定差距。

所以本次最值得看的不是谁一定 4–0，而是谁属于哪个实力带。

## 当前五个实力带

1. **单独领先：Team Yandex**
2. **第一追赶组：Team Falcons、TEAM VISION、BoomBoys、Team Liquid**
3. **上中游：Team Resilience、Team Spirit、Aurora Gaming**
4. **胶着中游：LGD Gaming、Vici Gaming、HULIGANI、OG、Nigma Galaxy**
5. **后段：GamerLegion、Xtreme Gaming、Iron Wing**

精确排名仍是 Yandex、Falcons、VISION、BoomBoys、Liquid、Resilience、Spirit、Aurora、LGD、
Vici、HULIGANI、OG、Nigma、GamerLegion、Xtreme、Iron Wing，但同一实力带内部经常就是五五开。

## 最关键的胜负关系

- Yandex 对第一追赶组只有 56%–58%，是小优，不是稳胜；
- Falcons、VISION、BoomBoys、Liquid 互相都在 48%–52%；
- Resilience 与 Spirit 是 50–50，Aurora 对它们约 48%；
- LGD、Vici、HULIGANI、OG、Nigma 内部大多在 46%–54%；
- GamerLegion 与 Xtreme 是 51–49，它们对 Iron Wing 也只有 53%–54%；
- 真正更清楚的是跨层关系：第一追赶组打胶着中游通常约 60%–65%。

这些百分比表示中立条件下的一局地图，而且模型概率没有通过校准，不是 BO3 胜率。

## 为什么近期排名变了

8 月 2 日以后进入模型的当前版本比赛中：

- Team Liquid 7 胜 3 负，从第 9 升到第 5；
- Team Falcons 6 胜 3 负，从第 4 升到第 2；
- BoomBoys 3 胜 5 负，从第 2 降到第 4；
- Vici Gaming 4 胜 6 负，综合强度下降；
- LGD Gaming 0 胜 2 负，从第 8 降到第 9。

模型还会计算对手强弱和时间权重，所以这些原始胜负不是单独的排名公式。

## 如果现在必须填写

| 槽位 | 队伍 |
| --- | --- |
| 4–0 | Aurora Gaming |
| 4–1 | Team Resilience；Team Spirit |
| 淘汰轮胜者 | Team Yandex；Team Falcons；TEAM VISION；BoomBoys；Team Liquid |
| 淘汰轮败者 | LGD Gaming；Vici Gaming；HULIGANI；OG；Nigma Galaxy |
| 1–4 | GamerLegion；Xtreme Gaming |
| 0–4 | Iron Wing |

### 为什么 4–0 填 Aurora，而综合第一仍是 Yandex

把六类结果想成六排座位：4–0 只有一个座位，淘汰轮胜者有五个座位，而且每支队只能坐一次。
所以不能只问“谁的 4–0 机会更高”，还要看把这支队从另一个座位移走会损失多少。

只看 Yandex 和 Aurora 的换位：

| 安排 | 4–0 位置 | 淘汰轮胜者位置 |
| --- | --- | --- |
| 当前建议 | Aurora：6.4% | Yandex：36.5% |
| 两队互换 | Yandex：8.4% | Aurora：32.1% |

把 Yandex 换进 4–0，那里只增加约 2.0 个百分点；但 Aurora 接替 Yandex 的淘汰轮胜者位置会
减少约 4.4 个百分点。因此，让 Yandex 留在更适合它的宽槽位，整体少浪费一点机会。

这里比较的只是一个座位多了多少、另一个座位少了多少，方便理解“换座位代价”；**它不是两项
同时猜中的胜率**。正式方案仍然把 16 支队、六类容量和活动积分一起模拟。它相对直接按实力排名
填写只多约 1.3% 模型期望分，主要分位点也完全相同，所以这个特殊排法的优势很小。实际判断时，
仍应优先相信实力带和对位关系。
