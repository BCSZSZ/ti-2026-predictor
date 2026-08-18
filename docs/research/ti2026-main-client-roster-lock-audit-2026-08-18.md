# TI 2026 Main 客户端阵容锁定时间核验（2026-08-18）

## 结论

本机当前 Dota 客户端定义的 TI 2026 Main Fantasy period 起点，即客户端阵容锁定时刻，是：

- UTC：`2026-08-20T02:00:00Z`
- 上海/北京时间（UTC+8）：`2026-08-20 10:00`
- 日本时间（JST，UTC+9）：`2026-08-20 11:00`

用户为本研究任务指定的交付截止时间是另一件事：

- 日本时间：`2026-08-19 08:00`
- UTC：`2026-08-18T23:00:00Z`
- 它比客户端锁定时间早 `27` 小时。

## 一手证据

2026-08-18 重新从本机已安装的 Dota 客户端提取规则，而非仅沿用仓库配置。新快照为
[`rule_snapshot.json`](../../data/raw/rules/20260818T114350Z-c20ffb525cf4/rule_snapshot.json)：

- 捕获时间：`2026-08-18T11:43:50Z`（[第 2–7 行](../../data/raw/rules/20260818T114350Z-c20ffb525cf4/rule_snapshot.json#L2)）
- 客户端 build：`6905:10917981`
- 快照语义 SHA-256：`c20ffb525cf441a2b1025d2b0b4002ff4c46d2f411da7a69439cf4b12eeed0cb`
- Main period 原始 Unix 时间戳：`1787191200`（[第 171–173 行](../../data/raw/rules/20260818T114350Z-c20ffb525cf4/rule_snapshot.json#L171)）

当前客户端的
[`international_2026.eventdef`](../../data/raw/rules/20260818T114350Z-c20ffb525cf4/scripts/events/international_2026.eventdef#L1053)
把 period `1` 明确标为 `Main Event`，并定义：

```text
"start" "1787191200" // Thursday, August 20th 10:00am Shanghai Time
```

同一当前客户端的中英文 UI 文案分别把倒计时称为“阵容锁定”和 “Roster Locks”：
[`dota_schinese.txt`](../../data/raw/rules/20260818T114350Z-c20ffb525cf4/resource/localization/dota_schinese.txt#L26004)、
[`dota_english.txt`](../../data/raw/rules/20260818T114350Z-c20ffb525cf4/resource/localization/dota_english.txt#L26156)。

Valve 官方赛事页也把 Main 日期列为 8 月 20–23 日：
<https://www.dota2.com/esports/ti15>。精确到小时的锁定依据来自当前客户端自身的 period 时间戳。

## 可信度与边界

结论可信度为高：时间戳来自当天更新后的本机客户端，且其内嵌注释和 Unix 时间换算一致。
快照状态为 `warning`，但三条 warning 只涉及 First Blood Title 与百分位表歧义，均与 period 时间和锁定时刻无关。
