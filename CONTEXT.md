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

**Community tournament tier / 社区赛事档位**:
A time-bounded Tier 1/2/3/4 classification published by a named community source for a Main
tournament. A Qualifier may display its destination tier, but does not thereby become a Main event.
_Avoid_: League tier, prize pool, model weight

**Event prize pool / 赛事总奖金**:
The announced monetary award pool scoped to one event. A Qualifier never inherits its Main
tournament's pool; an unannounced value remains unknown rather than becoming zero.
_Avoid_: Community tournament tier, team winnings, parent-event prize

**Team year-to-date prize winnings / 战队年度已获奖金**:
At a fixed `as_of`, the sum of publicly confirmed gross USD awards assigned to one stable Team
identity by completed prize-bearing events in the UTC calendar year, including published club or
team rewards. Individual awards, unknown payouts and another organization's results before a
roster transfer are excluded.
_Avoid_: Event prize pool, player career earnings, roster-lineage winnings, estimated payout

**Event nature / 赛事性质**:
Whether an event is a completed Main tournament or a Qualifier whose result is advancement rather
than a championship placement.
_Avoid_: League tier, tournament prestige

**Tournament placement bin / 赛事最终名次档**:
A mutually exclusive final-place range earned by one stable Team identity in one completed Main
tournament, such as champion, runner-up, 3–4 or 5–8.
_Avoid_: Qualifier advancement, Series record, power ranking

**Qualification outcome / 资格赛结果**:
Whether one stable Team identity advanced from a completed Qualifier to its named Main tournament.
It is not a Tournament placement bin.
_Avoid_: Qualifier champion, tournament title, final placement

**Patch / 游戏版本**:
The Dota gameplay version active when a Game started, derived from OpenDota's patch timeline when
the match response does not provide it directly.
_Avoid_: API version, replay parser version

**Exact gameplay patch / 精确游戏小版本**:
The literal gameplay Patch active when a Game started, preserving any letter suffix such as `7.41a`
or `7.41e`.
_Avoid_: Major gameplay patch, report version, calendar period

**Current exact gameplay patch / 当前精确游戏小版本**:
The latest declared Exact gameplay patch active at a Forecast run's fixed `as_of`, identified by
its reviewed UTC activation boundary.
_Avoid_: Major gameplay patch, latest Patch seen in match data, current calendar period

**Major gameplay patch / 游戏大版本**:
The normalized Patch family used to compare model evidence: lettered hotfixes share their numeric
family (`7.41d` and `7.41e` are `7.41`), while `7.41` and `7.42` are different families.
_Avoid_: Exact hotfix Patch, calendar year, API version

**Game evidence weight / 单局证据权重**:
A preregistered non-negative measure of how much one historical Game informs a Forecast, based
only on its Major gameplay patch, whether it is on the Current exact gameplay patch, League tier
and age at the run's `as_of`.
_Avoid_: Sampling probability, confidence score, post-hoc performance adjustment

**Target-team evidence network / 目标队证据网络**:
The union of connected components in the positive-weight, `as_of`-prior professional Game graph
that contain a declared Forecast target team. It recursively includes opponents while excluding
disconnected competition ecosystems.
_Avoid_: Target-team-only history, complete professional catalog, current-team history

**Tournament holdout / 赛事留出集**:
A complete tournament excluded from model fitting and parameter selection, then evaluated only
after the candidate model and evaluation protocol are locked.
_Avoid_: Calibration window, rolling validation window, training tournament

**Data snapshot / 数据快照**:
An immutable view of raw and normalized evidence available at a fixed collection time.
_Avoid_: Forecast run

## Fantasy

**Fantasy performance sample / Fantasy 表现样本**:
One player's observed statistics in one completed Game, used as historical evidence for estimating
future Fantasy points. It is not a prediction or a player card.
_Avoid_: Fantasy prediction, Fantasy recommendation, player count

**Native Fantasy counter / Fantasy 原生计数**:
A per-player cumulative value emitted by Valve match state whose meaning directly matches one
Fantasy scoring stat. An observed native zero is `exact`; an absent or untrusted counter is `null`.
_Avoid_: Combat-log event count, inferred proxy, default zero

**Diagnostic event proxy / 诊断事件代理**:
A nearby item-use, ability-use or kill-event count retained only for source comparison when it does
not share the Native Fantasy counter's scoring semantics. It never fills an exact `null`.
_Avoid_: Exact fallback, reconstructed Fantasy counter, publishable stat

**Fantasy player history scope / Fantasy 选手历史范围**:
The completed `premium` or `professional` Games in a fixed UTC year that include at least one
reviewed TI Fantasy player account. Membership follows stable player identity, including Games
played for former teams.
_Avoid_: Current-team history, public match history, all professional Games

**Fantasy recommendation / Fantasy 推荐**:
A proposed set of three role cards plus Emblem and Coach choices for one settlement Period.
_Avoid_: Fantasy performance sample, official lineup

**Common Fantasy scenario / Fantasy 公共情景**:
One fixed Group outcome and aligned set of sampled full-Series performance blocks for every eligible
Team and Fantasy role. Candidate Banners reuse its stable scenario ID so paired differences contain
no avoidable resampling noise.
_Avoid_: Independent candidate simulation, Roll transition outcome, observed match

**Series resampling block / Series 重采样块**:
All played Games from one eligible Series for the required current-role player or player pair,
retained as one indivisible historical unit with stable IDs and one governed sampling weight.
_Avoid_: Independently sampled Game, randomly re-paired players, Team-average row

**Period / 结算期**:
A stage for which one Fantasy lineup is locked and scored; in 2026 the Periods are Group and Main.
_Avoid_: Series, tournament day

**Fantasy role / 梦幻定位**:
One of `core` (position 1/3 pair), `mid` (position 2), or `support` (position 4/5 pair).
_Avoid_: Carry, individual lane assignment

**War Banner / 战旗**:
The Emblem container attached to one Fantasy role; it has three slots in Group and five in Main.
_Avoid_: Player card, lineup

**Emblem / 徽标**:
A Fantasy modifier with a color, statistic, quality and trait.
_Avoid_: Player card, Coach title

**Attribute reroll / 属性重随**:
A mutation that replaces only the named stat, quality or trait on its targeted Emblem or Emblems
while retaining their other attributes.
_Avoid_: Complete Emblem reroll, War Banner reset, attribute bundle

**Roll option / 重随选项**:
One of three distinct Emblem mutation operations offered at the same time and shared by all War
Banners. Applying it changes only the selected War Banner and replaces all three offered options.
_Avoid_: Emblem result, War Banner-specific option

**Apply Roll option / 执行重随选项**:
Applying one offered Roll option to one selected War Banner at the cost of one Roll token. The
operation can contain random outcomes and replaces all three offered options after it resolves.
_Avoid_: Operation refresh, free action, deterministic outcome

**Operation refresh / 刷新操作选项**:
Discarding all three offered Roll options and drawing three replacements at the cost of one Roll
token, without mutating a War Banner.
_Avoid_: Free refresh, applying an option, refreshing one option

**Roll / 重随**:
One spend of a Roll token, either by applying a Roll option or by refreshing the offered options.
_Avoid_: Stat reroll, option only, free action

**Roll decision / 重随决策**:
One state-dependent choice among every legal offered-option-and-War-Banner pairing and Operation
refresh, made from the complete observed state and reconsidered after the result. It has no fixed
Stat, Quality or Trait phase.
_Avoid_: Roll, fixed attribute phase, isolated option ranking

**Unresolved Roll decision / 未决重随决策**:
A Roll decision whose leading actions remain statistically indistinguishable within the declared
calculation budget. It is reported as unresolved and falls back to the Rate-agnostic safety baseline
rather than forcing a model-dependent recommendation.
_Avoid_: Arbitrary tie-break, unlimited simulation, failed Forecast run

**Group roll policy / 小组赛重随策略**:
A state-dependent rule for choosing how to spend the 40 Group Roll tokens from the current three
War Banners, shared Roll options and remaining tokens, including when to refresh all three options.
Main is a future extension, not its objective.
_Avoid_: Fixed click script, Main roll policy, team-first commitment

**Observed starting state / 已观测初始状态**:
The complete Group War Banners and shared Roll options visible before the first Roll decision. It is
a fixed condition for policy value, not future Roll randomness requiring an initial-rate model.
_Avoid_: Random starting-state prior, Locked Roll baseline, future Roll outcome

**Starting-state coverage suite / 初始状态覆盖集**:
A non-probability-weighted set of legal Observed starting states spanning declared Stat and
Quality-and-Trait conditions. Every stratum is validated conditionally rather than averaged into a
claimed population Expected Group score.
_Avoid_: Initial-state probability model, uniform state distribution, live starting state

**Starting Stat readiness / 起始统计项成熟度**:
The best-team-matched expected value of a War Banner's current Stats relative to its Fantasy role's
best legal Stat combination, with Quality and Trait effects neutralized. Its low, middle and high
rank thirds are coverage labels rather than Baseline Stat grades.
_Avoid_: Baseline Stat grade, Stat quality probability, complete Banner value

**Starting configuration readiness / 起始组合成熟度**:
The expected value of a War Banner's current positioned Quality-and-Trait configuration relative to
its best legal configuration while holding Stats fixed and repeating Team matching. Its low, middle
and high rank thirds are non-probabilistic coverage labels.
_Avoid_: Trait configuration value, configuration target, initial-state probability

**Starting-state coverage stratum / 初始状态覆盖格**:
One of the nine per-role crossings of low, middle or high Starting Stat readiness with low, middle
or high Starting configuration readiness. Complete Group starts balance those role-level cells
without expanding their full Cartesian product or assigning population weights.
_Avoid_: Nine-cubed start enumeration, tactical grade, probability bucket

**Rollout-improved policy / 滚动改进策略**:
A model-conditional Group roll policy that compares current Roll decisions by simulating the full
remaining token horizon under a declared continuation policy, then replans after the observed
result. It is a bounded policy improvement rather than an exact global optimum.
_Avoid_: One-step greedy policy, fixed 40-step script, exact dynamic-programming solution

**Reference Roll solver / 参考重随求解器**:
A bounded model-conditional evaluator that independently benchmarks the Human Roll playbook and
secondarily powers the Interactive Roll advisor. Its preferred policy is approximate rather than a
proven global optimum.
_Avoid_: Exact solver, exhaustive 40-Roll enumeration, user-facing strategy

**Branch-capped Roll solver / 限枝重随求解器**:
The preferred Reference Roll solver that expands only the current legal Roll decisions and values
each through one fixed continuation heuristic with precomputed Quality and Trait synergy potential.
It deliberately trades planner strength for bounded complexity and runtime.
_Avoid_: Full configuration Roll planner, recursive decision tree, Human Roll playbook

**Synergy-potential continuation / 协同潜力延续规则**:
The Branch-capped Roll solver's sole simulated continuation, which compares the Group roll objective
after adding a precomputed best Quality-and-Trait gain within three attribute differences while
holding Stats fixed. Its credit decays as `(remaining Rolls - 1) / 39`, reaching zero on the final
Roll, and never creates a configuration target or recursive branch.
_Avoid_: Target-directed continuation, static Trait bonus, runtime configuration search

**Full configuration Roll planner / 全量组合重随规划器**:
The retained fallback Reference Roll solver design that explicitly evaluates configuration targets,
reachability and model-aware race-and-confirm under the full Analysis runtime envelope. It is not
the default implementation and requires an explicit escalation decision.
_Avoid_: Branch-capped Roll solver, automatic fallback, exact global solver

**Branch-capped solver effectiveness gate / 限枝求解器有效性门槛**:
The predeclared requirement that exact one-to-three-Roll oracle regret has a one-sided 95% upper
bound at or below 2%, complete 40-Roll results are not statistically worse than both simple
baselines, and at most 10% of Common playbook situations are unresolved. Failure permits an
escalation review but never activates the Full configuration Roll planner automatically.
_Avoid_: Runtime target, automatic fallback, subjective quality judgment

**Human Roll playbook / 人类重随手册**:
The primary user-facing Group guide, with Rate-agnostic and Primary-model editions expressed as
concise Stat priorities, Quality and Trait recipes, ordered Roll guidance and one generic fallback.
It is not a state-complete near-optimal decision engine.
_Avoid_: Raw solver trace, state-by-state policy table, Interactive Roll advisor

**Playbook Stat priority table / 手册统计项优先表**:
One of seven role-and-color tables listing all six legal Stats in value order with their Baseline
Stat grade, best-equals-100 relative index and compact stability or evidence markers. Its visible
top three are descriptive ranks, never an automatic lock rule, and evidence gaps receive no
fabricated grade.
_Avoid_: Top-three lock list, sixteen-team data dump, complete Emblem ranking

**Playbook guidance rule / 手册指导规则**:
A broad, ordered instruction using only a few conditions a person can recognize directly while
rolling. It expresses a reusable priority rather than a dedicated action for every configuration.
_Avoid_: Solver branch, Diagnostic state slice, exhaustive exception list

**Diagnostic state slice / 诊断状态分组**:
An internal validation subgroup used to reveal where manual simplicity loses value. It can justify
a broadly explainable rule or a documented limitation but never becomes a manual branch by itself.
_Avoid_: Playbook guidance rule, mandatory quick-reference condition, post-hoc rule patch

**Common playbook situation / 手册常见情形**:
A directly recognizable condition encountered at least once in ten percent or more of complete
40-Roll sessions within any Starting-state coverage stratum and Roll transition model in that
edition's Playbook model validation scope. Its share of the combinatorial state space is irrelevant.
_Avoid_: Frequent individual state, ten percent of Roll decisions, rare adversarial configuration

**Playbook-significant exception / 手册重大例外**:
A diagnostic weakness that makes published guidance directionally wrong or exceeds the Playbook
material-loss threshold in a Common playbook situation. It blocks release; other diagnostic
weaknesses are disclosed without expanding the manual into state-specific branches.
_Avoid_: Every Diagnostic state slice, rare solver disagreement, automatic rule insertion

**Playbook material-loss threshold / 手册重大损失阈值**:
The working release limit is a ten-percent conditional loss in final Expected Group score or
lower-tail CVaR10 after a Common playbook situation, judged by a one-sided 95% upper bound. Five
percent is a predeclared stricter candidate rather than the initial release requirement.
_Avoid_: Playbook simplification tolerance, immediate Banner loss, post-hoc threshold

**Playbook reliability tier / 手册可靠性等级**:
An independently confirmed edition is `baseline-reliable` when every Common playbook situation has
a one-sided 95% loss upper bound at or below 10%, and `strict-reliable` when the same confirmation is
also at or below 5%. Failure at 10% leaves the edition draft or unresolved; changing its rules starts
a new version that requires fresh held-out confirmation.
_Avoid_: Point-estimate pass, reused confirmation, solver agreement

**Independent playbook derivation / 独立手册推导**:
The origin constraint under which Playbook guidance rules are proposed from governed Stat evidence,
exact Quality and Trait analysis and client-visible Roll semantics before Reference Roll solver
results are inspected. Solver traces are not rule-generating evidence.
_Avoid_: Solver distillation, post-hoc exception patch, Read-only cross-audit

**Playbook rule ablation / 手册规则消融**:
A paired whole-session comparison of a frozen candidate playbook with one guidance rule retained
versus removed or directionally reversed, sharing the same future scenarios. It measures the rule's
incremental value without using the Reference Roll solver as its teacher.
_Avoid_: Solver imitation, unpaired score comparison, rule search

**Core playbook rule / 手册核心规则**:
A Playbook guidance rule admitted only when paired ablation throughout its edition's validation
scope gives one-sided 95% evidence of no loss in both Expected Group score and lower-tail CVaR10,
with a strict improvement in at least one.
_Avoid_: Risk-overlay rule, plausible heuristic, model-reversing rule

**Risk-overlay rule / 风险修正规则**:
A Playbook guidance rule that may exchange Expected Group score within its declared Mean-retention
tolerance for a one-sided 95%-confirmed lower-tail CVaR10 improvement. It is visibly separate from
the Core playbook rules.
_Avoid_: Unbounded mean sacrifice, Core playbook rule, hidden objective change

**Playbook evidence package / 手册证据包**:
The versioned body of governed Stat Forecasts, exact Quality and Trait analysis, Roll-rate
assumptions, standalone validation and read-only counterexamples supporting both Human Roll
playbook editions. It makes manual conclusions auditable without turning solver traces into rules.
_Avoid_: Human Roll playbook, raw solver output, Interactive Roll advisor artifact

**Playbook release gate / 手册发布门槛**:
The boundary allowing a Human Roll playbook edition to be called reliable only after its governed
evidence, independent derivation, standalone validation and Read-only cross-audit are complete.
Interactive Roll advisor completion is not part of this gate.
_Avoid_: UI completion gate, solver agreement as proof, draft recommendation

**Rate-agnostic playbook / 出率无关手册**:
The Human Roll playbook edition that compares legal Roll results without assigning probabilities
to their occurrence. It remains executable when the true Roll transition rates are unknown.
_Avoid_: Rate-agnostic safety baseline, equally weighted outcomes, probability-free match evidence

**Primary-model playbook / 主出率模型手册**:
The Human Roll playbook edition independently derived under the declared Primary Roll transition
model. It exposes the assumptions behind its rate-sensitive rules rather than treating them as
Valve's true rates.
_Avoid_: Solver distillation, known backend rates, exact optimal policy

**Default playbook edition / 默认手册版本**:
The Primary-model playbook is the normal first operational recommendation, while the Rate-agnostic
playbook remains the separately visible robust fallback. Default order does not merge their rules
or establish that the primary model is true.
_Avoid_: Hidden policy blending, sole published playbook, proven backend rate

**Playbook applicability / 手册适用性**:
An edition-level status requiring its Rule snapshot and declared model provenance to match the
current activity. An inapplicable Primary-model playbook yields default status to the Rate-agnostic
playbook rather than being repaired through local rule substitutions.
_Avoid_: Per-decision model sensitivity, silent model update, hybrid playbook

**Rate-sensitive playbook decision / 出率敏感手册决策**:
A state where the two playbook editions disagree or the Primary-model recommendation reverses under
a declared Roll transition variant. It is visibly flagged but does not change either edition or
automatically select between them.
_Avoid_: Playbook inapplicability, automatic robust override, policy blending

**Playbook model validation scope / 手册模型验证范围**:
The Primary-model edition is release-tested under the Primary Roll transition model while variants
remain sensitivity evidence; the Rate-agnostic edition is release-tested under the primary model
and every declared variant. Neither scope claims coverage of all possible backend rates.
_Avoid_: One shared release scope, true backend rate, variant-triggered policy blending

**Manual complexity frontier / 人工手册复杂度前沿**:
The standalone comparison of preregistered nested playbook sizes, formed before solver inspection,
that reports the shortest independently derived candidate within one, two or five percent of the
best candidate's Expected Group score and lower-tail CVaR10.
_Avoid_: Solver audit regret, per-rule percentage cutoff, solver-selected playbook

**Solver audit regret / 求解器审计损失**:
The held-out loss of a frozen Human Roll playbook relative to the Reference Roll solver, measured
only during Read-only cross-audit. It can expose a Playbook-significant exception but cannot select
the playbook's rules or length.
_Avoid_: Manual complexity frontier, rule-generation signal, solver distillation

**Playbook fallback / 手册兜底动作**:
The single generic manual instruction to refresh the shared Roll options when no Playbook guidance
rule supports an application. Its cost is included in held-out evaluation, so fallback coverage
does not imply a specialized near-optimal rule for every state.
_Avoid_: Free refresh, Interactive Roll advisor, unmeasured exception handling

**Playbook complexity budget / 手册复杂度预算**:
The per-edition working readability limit of two quick-reference sheets, twelve ordered decision
rules and at most three observable conditions per rule; lookup tables are separate. Eight-, twelve-
and sixteen-rule candidates expose the Manual complexity frontier without consulting the solver.
_Avoid_: Hidden arithmetic, unrestricted rule growth, explanation appendix as required reading

**Playbook risk overlay / 手册风险修正**:
A small set of modifiers within each Human Roll playbook edition that expresses mean-first, default
and downside-first preferences. The default follows the measured Group risk frontier's knee; exact
reported tolerances do not create further complete playbooks.
_Avoid_: Four duplicated playbooks, fixed two-percent default, hidden risk preference

**Playbook Roll phase / 手册重随阶段**:
One of at most three human-readable remaining-token bands whose boundaries are proposed and
validated within the independent Human Roll playbook route, then rounded to a multiple of five.
The Interactive Roll advisor and solver retain the exact remaining Roll count.
_Avoid_: Forty token-specific rules, evidence-free phase boundary, solver horizon compression

**Interactive Roll advisor / 实时重随顾问**:
A secondary local interface that accepts manually confirmed War Banners, shared Roll options,
remaining tokens and risk preference, then explains a Roll recommendation. It may either track a
confirmed event history or recompute from a complete current screen. It never controls the Dota or
Steam client.
_Avoid_: Client automation, Human Roll playbook, unconfirmed OCR action

**Current-screen Roll advice / 当前屏幕重随建议**:
One directly executable apply-or-refresh recommendation computed from all War Banners, all three
shared Roll options and the exact remaining-token count currently visible to the player. It values
the legal outcomes of the current options but deliberately excludes the unknown replacement offer;
after acting in Dota, the player supplies the newly observed complete screen and recomputes.
_Avoid_: Next-offer generation, full-horizon Roll plan, automatic client state

**Policy route separation / 策略路线分离**:
The Reference Roll solver and the two Human Roll playbook editions are separately versioned decision
products with distinct execution and outputs. Neither route silently replaces or modifies another,
and their disagreement remains visible.
_Avoid_: Runtime policy blending, shared policy version, hidden disagreement

**Read-only cross-audit / 只读交叉审计**:
An offline comparison in which the Reference Roll solver may expose counterexamples to the Human
Roll playbook but cannot modify it. A playbook revision requires an independently explainable rule,
its own held-out validation and an explicit version release.
_Avoid_: Automated policy distillation, solver agreement as proof, runtime policy blending

**Configuration challenger / 组合挑战策略**:
A model-conditional continuation policy that may accept a temporary non-improvement to pursue a
multi-step Quality and Trait configuration. It may displace the Rate-agnostic safety baseline only
through evaluation over the complete remaining Group Roll horizon.
_Avoid_: Static Trait ranking, guaranteed synergy, Rate-agnostic safety baseline

**Configuration target set / 组合目标候选集**:
The provisional Quality and Trait targets retained for Configuration challengers after soft
screening by terminal value, client-legal mutation distance and Reachability signature. It is not a
hard Pareto frontier or a proof that excluded targets are unreachable.
_Avoid_: Configuration target frontier, Trait tier list, proven optimal target set

**Configuration target value / 组合目标价值**:
The joint Group outcome distribution formed by inserting one configuration target into the current
three War Banners, holding the others fixed, and repeating Team matching under common future match
scenarios. Its mean and lower-tail CVaR10 exclude future Roll reachability.
_Avoid_: Terminal Banner value, sum of per-Banner CVaRs, Group policy outcome

**Reachability signature / 可达路径特征**:
The operation classes and random mutation outcomes required by client-legal paths from the current
War Banner to a configuration target, without assigning them true probabilities. It distinguishes
targets with equal minimum distance but different practical reachability.
_Avoid_: Roll probability, minimum mutation distance, reachability guarantee

**Structural target screening / 结构目标筛选**:
A rate-agnostic first-stage reduction that compares joint mean, lower-tail CVaR10 and minimum
mutation distance only among configuration targets with equivalent Reachability signatures.
Targets with different signatures remain incomparable until model-aware evaluation.
_Avoid_: Weighted target score, cross-signature dominance, optimality proof

**Race-and-confirm evaluation / 竞赛—确认评估**:
A two-stage model-aware comparison in which candidates share random scenarios for adaptive
elimination, then survivors are measured on independent scenarios. Race samples never support a
reported final advantage, and an exhausted budget produces an unresolved result.
_Avoid_: Reusing screening samples, fixed Top-K, noise-selected winner

**Cross-model candidate retention / 跨模型候选保留**:
A race candidate remains active while simultaneous bounds permit it to be selected for any declared
Roll transition model at any reported Mean-retention tolerance. Elimination requires exclusion from
every such combination, while the Rate-agnostic safety baseline is never eliminated.
_Avoid_: Primary-model-only screening, point-estimate elimination, removing the safety baseline

**Analysis runtime envelope / 分析运行时限**:
The target active elapsed time for one pre-session Group Roll analysis is three hours, with an
absolute five-hour ceiling; its release-blocking product is the Playbook evidence package rather
than the Interactive Roll advisor. Passing the target enters bounded grace and never authorizes
broader search scope; time waiting for user input is excluded.
_Avoid_: Strict three-hour cutoff, unlimited runtime, user-waiting timeout

**Performance grace / 性能宽限**:
The interval after the three-hour target used only to finish preregistered Playbook evidence,
validation, cross-audit and reporting when execution is slower than planned. It cannot expand scope
or the Interactive Roll advisor; new computation stops at four hours forty-five minutes.
_Avoid_: Extra candidate search, UI expansion, open-ended overrun

**Simulation target commitment / 模拟目标承诺**:
Within one simulated continuation, a Configuration challenger retains one target until it is
reached, ceases to improve value, becomes unreachable within the remaining tokens, or the horizon
ends. Every realized Roll ends that commitment and the next Roll decision replans without sunk-cost
preference.
_Avoid_: Actual target lock-in, fixed 40-step target, recursive simulated replanning

**Target-directed continuation / 目标导向延续规则**:
During a Simulation target commitment, a Configuration challenger minimizes expected client-legal
distance to its target, breaking ties by worst-case and then expected immediate Terminal Banner
value change. It is a continuation heuristic inside rollout evaluation, not the final Roll decision.
_Avoid_: Final action recommendation, per-Roll loss cap, exact optimal continuation

**Group policy outcome / 小组赛策略结果**:
The final Group Fantasy total produced from one observed starting state by following a Group roll
policy, making its terminal team choices and realizing all future uncertain outcomes.
_Avoid_: Best possible score, expected score, one Emblem result

**Expected Group score / 小组赛期望总分**:
The probability-weighted mean of a Group policy's outcomes conditional on the observed starting
state and the information available at the run's explicit `as_of`.
_Avoid_: Best-case score, guaranteed score, perfect-roll score

**Mean-retention tolerance / 期望保留容差**:
A configured fraction `ε` of the maximum Expected Group score that may be sacrificed before
lower-tail safety can choose another Group roll policy.
_Avoid_: Fixed one-percent rule, variance weight, Roll budget

**Group roll objective / 小组赛重随目标**:
First retain policies whose Expected Group score is at least `(1 - ε)` of the maximum, then choose
among them by the greatest mean score in the lowest 10% of Group policy outcomes (lower-tail
CVaR10).
_Avoid_: Pure variance minimization, perfect-roll optimization, Main carry value

**Group risk frontier / 小组赛风险前沿**:
The comparison of Group roll policies selected at `ε = 0%, 1%, 2% and 5%`, showing each policy's
actual Expected Group score sacrifice and lower-tail CVaR10 gain.
_Avoid_: Permanent risk preset, single recommended percentage, variance profile

**Roll transition model / 重随转移模型**:
A declared probability model for offered Roll options and random mutation results, conditioned on
the observed state and Rule snapshot. Client weights define the primary model without implying
that undisclosed server sampling details are known exactly.
_Avoid_: True Roll rate, match-performance Forecast, Rule snapshot

**Primary Roll transition model / 主重随转移模型**:
The versioned best-supported estimate of Roll option and mutation-result probabilities from the
current Rule snapshot plus explicit assumptions. It is the project's best guess, not a claim about
Valve's undisclosed backend rates.
_Avoid_: True Roll rate, undocumented certainty, Roll-rate robustness variant

**Locked Roll baseline / 锁定重随基准**:
The reusable analysis baseline fixed by one `as_of`, Data snapshot, Rule snapshot, Primary Roll
transition model and reproducibility configuration. It is produced once per version and remains
independent of any actual starting War Banners or Roll options.
_Avoid_: Learned backend rate, live state, in-session model update

**Observed-state replanning / 观测状态重规划**:
Choosing the next Roll decision after replacing the War Banners, options and remaining tokens with
their newly observed values while retaining the Locked Roll baseline.
_Avoid_: Fixed click script, In-session rate learning, probability update

**In-session rate learning / 当局出率学习**:
Changing a Roll transition model from option or mutation outcomes observed during the same 40-Roll
session. Current-session observations may be retained as later evidence but do not alter its Locked
Roll baseline.
_Avoid_: Observed-state replanning, offline policy evaluation, future model revision

**Roll-rate robustness / 重随出率稳健性**:
Whether a model-conditional preferred Roll action remains preferred across declared reasonable
variations of the Roll transition model; an action that changes is explicitly model-dependent.
_Avoid_: Absolute optimality, outcome volatility, Stat grade stability

**Rate-agnostic safety baseline / 出率无关安全基线**:
A Group roll policy that assigns no probabilities to legal Roll results, applies only an offered
action whose worst result does not reduce Terminal Banner value after Team matching, and otherwise
refreshes the options. It is a monotone safety comparator, not an Expected Group score optimum.
_Avoid_: Model-conditional optimum, known Roll rate, guaranteed globally optimal policy

**Rate-agnostic action interval / 出率无关动作区间**:
The minimum and maximum Terminal Banner value change across every legal result of one offered Roll
action, written `[L, U]` without assigning result probabilities. The safety baseline maximizes `L`,
then `U`, and prefers Operation refresh over an action whose interval is exactly `[0, 0]`.
_Avoid_: Expected action value, equally weighted outcomes, confidence interval

**Team matching / 队伍匹配**:
The free selection of one eligible team for each Fantasy role against the resulting War Banner
state before a Period locks. Every slot on that War Banner scores the corresponding player or pair
from the same selected team.
_Avoid_: Team commitment, per-Emblem team selection, roster interval, Roll

**Team-match breadth / 队伍匹配广度**:
The number or share of eligible teams whose Forecast value for a stat or complete War Banner is
within a stated margin of its best Team matching value. It measures flexibility, not primary value.
_Avoid_: Average-team objective, team strength, best-team value

**Stat combination conflict / 统计项组合冲突**:
A same-role Stat pair whose best common-team expected value is more than 10% below the sum of the
two independently best-matched values. It appears in the playbook as a combination warning; losses
from 5% through 10% remain evidence-only and a single Stat is never labelled narrow by itself.
_Avoid_: Team-match breadth, single-Stat narrowness, mandatory team precommitment

**Stat contribution Forecast / 统计项贡献预测**:
The distribution of one `team × Fantasy role × stat` contribution after applying the Period's
actual Game and Series aggregation, but before Emblem quality and trait modifiers.
_Avoid_: Emblem expected value, raw stat average, historical maximum

**Baseline Stat grade / 基础统计项等级**:
One of `hard-protect`, `keep`, `conditional-reroll` or `priority-repair`, describing how a stat
should normally consume Roll opportunities. Using best-matched Expected Group contribution, the
boundaries are best-with-runner-up-below-44%, at least 84.6%, 44–84.6%, and below 44%; the grade
applies only to the stat attribute and is separate from evidence provenance.
_Avoid_: Complete Emblem grade, Quality grade, Trait grade, data quality, top-three label

**Published Stat handling guidance / 发布版统计项操作建议**:
The player-facing mapping of Baseline Stat grades as `一定保留`, `可以保留`, `可以改善` and
`优先改善`, in that order. It is baseline priority guidance rather than a state-specific Roll action.
_Avoid_: 一定改善, unconditional reroll instruction, final Banner decision, evidence provenance

**Stat grade stability / 统计项分档稳定性**:
A `stable` or `boundary` label from full-Series resampling that preserves Core and Support pair
observations and reports whether sampling variation crosses a Baseline Stat grade boundary. It
supplements the point-estimate grade and does not directly determine a Roll action.
_Avoid_: Baseline Stat grade, outcome volatility, lower-tail CVaR, evidence provenance

**Quality marginal value / 品质边际价值**:
The change in Terminal Banner value from a realized quality-only change after recomputing Trait
effects and Team matching. `T1` through `T5` describe the Quality state rather than a tactical grade.
_Avoid_: Quality grade, isolated tier value, automatic T5 protection

**Trait configuration value / 特性组合价值**:
The Terminal Banner value attributable to the complete positioned Trait configuration after its
Quality, adjacency and count conditions are resolved. An individual Trait has no context-free
tactical grade.
_Avoid_: Trait ranking, isolated Trait bonus, automatic synergy protection

**Stat reroll action value / 统计项重随动作价值**:
The state-conditional change in the Group roll objective from taking one available Stat reroll,
including its possible results, the complete War Banners, remaining tokens and lost Roll options.
_Avoid_: Baseline Stat grade, static ranking, immediate stat gain

**Terminal Banner value / 终局战旗价值**:
The outcome distribution or objective value of a complete War Banner after jointly applying all
slot stats, qualities, traits and positions and performing Team matching.
_Avoid_: Independent Emblem rank, sum of top stats, perfect Banner score

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
