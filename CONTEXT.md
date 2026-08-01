# TI 2026 decision support domain

This project separates Valve's in-game activities from the historical evidence and model outputs
used to recommend what the player should enter.

## Predictions

**InGamePrediction / 游戏内预测**:
A result slot or bracket node that a player fills in Valve's TI activity.
_Avoid_: Forecast, model prediction

**Forecast / 模型预测**:
A probability distribution produced by this project at a fixed `as_of` time.
_Avoid_: In-game prediction, official answer

**Forecast run / 预测运行**:
One reproducible calculation with fixed rules, data, configuration, code and random seed.
_Avoid_: Data sync, Fantasy performance sample

**Publishable / 可发布**:
An audited recommendation that may be used as an in-game entry; it is not a guarantee of correctness.
_Avoid_: Official, confirmed winner

## Match evidence

**Game / 单局**:
One Dota map from draft through one team's victory.
_Avoid_: Series, match day

**Series / 系列赛**:
A BO1/BO2/BO3/BO5 contest between two teams made up of one or more Games.
_Avoid_: Game, tournament

**Professional match catalog / 职业比赛目录**:
The time-bounded set of Games returned by OpenDota's `/proMatches` feed, enriched with league and
patch metadata. Membership describes the upstream feed, while `league tier` describes event level.
_Avoid_: Fantasy predictions, all parsed match details

**League tier / 赛事级别**:
OpenDota's league classification (`premium`, `professional`, `amateur`, `excluded` or `unknown`).
It is not an invented Tier 1/2/3 ranking.
_Avoid_: Match type, patch

**Patch / 游戏版本**:
The Dota gameplay version active when a Game started, derived from OpenDota's patch timeline when
the match response does not provide it directly.
_Avoid_: API version, replay parser version

**Data snapshot / 数据快照**:
An immutable view of raw and normalized evidence available at a fixed collection time.
_Avoid_: Forecast run

## Fantasy

**Fantasy performance sample / Fantasy 表现样本**:
One player's observed statistics in one completed Game, used as historical evidence for estimating
future Fantasy points. It is not a prediction or a player card.
_Avoid_: Fantasy prediction, Fantasy recommendation, player count

**Fantasy recommendation / Fantasy 推荐**:
A proposed set of three role cards plus Emblem and Coach choices for one settlement Period.
_Avoid_: Fantasy performance sample, official lineup

**Period / 结算期**:
A stage for which one Fantasy lineup is locked and scored; in 2026 the Periods are Group and Main.
_Avoid_: Series, tournament day

**Fantasy role / 梦幻定位**:
One of `core` (position 1/3 pair), `mid` (position 2), or `support` (position 4/5 pair).
_Avoid_: Individual lane assignment

**War Banner / 战旗**:
The Emblem container attached to one Fantasy role; it has three slots in Group and five in Main.
_Avoid_: Player card, lineup

**Emblem / 徽标**:
A Fantasy modifier with a color, statistic, quality and trait.
_Avoid_: Player card, Coach title

**Coach title / 指导员称号**:
A prefix and suffix condition shared by the complete Fantasy lineup.
_Avoid_: Emblem, team coach

## Identity and rules

**Team identity / 战队身份**:
A stable Valve/OpenDota team ID, distinct from its display name.
_Avoid_: Team name

**Roster interval / 阵容区间**:
The half-open time interval `[valid_from, valid_to)` during which a player belongs to a team.
_Avoid_: Current roster applied to history

**Rule snapshot / 规则快照**:
A hashed set of activity rules extracted from one identified Dota client build.
_Avoid_: Data snapshot, forecast run
