# TI 2026 activity rules

Sources: Valve's 2026 announcement, the installed Dota client event definition and Fantasy crafting data. The normalized executable form is `config/rules/ti2026.json`.

The visible Fantasy help text supplied from the local client on 2026-08-02 is transcribed and audited in [fantasy-client-rules-screenshots-2026-08-02.md](fantasy-client-rules-screenshots-2026-08-02.md). That evidence has no visible client build identifier, so it is supporting source material rather than a complete hashed rule snapshot.

The project strategy derived from those rules, while keeping third-party heuristics separate from Valve evidence, is documented in [fantasy-strategy.md](fantasy-strategy.md).

The visible final leaderboard rewards and prediction point tables are transcribed in [client-final-rewards-and-prediction-rules-screenshots-2026-08-02.md](client-final-rewards-and-prediction-rules-screenshots-2026-08-02.md).

## Predictions

- Group capacities: one 4-0, two 4-1, five Elimination winners, five Elimination losers, two 1-4 and one 0-4.
- Group correct-count points: `0, 30, 60, 120, 360, 720, 1200, 1800, 2520, 3360, 4320, 5400, 6600, 7920, 9360, 10920, 12000`.
- Main Event: eight-team double elimination with fourteen prediction nodes.
- Main correct-count points: `0, 120, 360, 720, 1200, 1800, 2520, 3360, 4320, 5400, 6600, 7920, 9360, 10920, 12000`.
- Both arrays are total event points looked up by the final correct count; their rows are not added together.

## Final leaderboard rewards

- Rewards are determined after The International on August 27; the screenshot does not state a timezone.
- Tyrian Regalias fixed totals by highest achieved tier: Top 100 `×5`, Top 1500 `×2`, 95th percentile `×1`, 90th/85th percentile `×0`.
- The same rows grant Dota Plus `12/6/2/1/1` months, Terrain Tokens `1/1/1/1/0`, and Aegis discounts `100/100/50/0/0%`.
- Every 1,000 event points grants 300 Dota+ Shards.

## Fantasy

- Fantasy scores use the same point unit displayed by the client; no implicit division by 100 is applied.
- Coaching requires exactly one prefix and one suffix. Both apply to all Fantasy players' final Game scores when their conditions trigger, and changing them costs no roll tokens.
- The visible `Change Titles` screen confirms eight prefixes and eight suffixes. The visible rules use “before the starting horn” for the Flayed Twins Acolyte and “after 10 minutes” for the Patient; both remain audited against conflicting internal client fields and are excluded from the publishable default until GC behavior is observed.
- Deaths score `max(0, 1950 - 195 × deaths)`.
- Until a client formula is verified, Teamfight Participation follows owner policy `2026-08-02-owner-policy-v1`: `(player kills + player assists) / team total kills`, multiplied by 2,124 and capped at 2,124. Zero team kills have an undefined denominator and remain `null`; missing inputs also remain `null`.
- Within one Emblem, quality, active self-trait and adjacent-trait percentages add against the base stat score. This is a strong inference from the client's combined Quality-and-Trait display, not a recovered arithmetic function.
- After Emblem scores are summed, triggered Coach prefix and suffix bonuses multiply the final Game score separately. Prefix/suffix multiplication is an owner policy until Valve arithmetic is verified.
- Core averages the selected team's position 1 and 3 players; Support averages positions 4 and 5; Mid uses position 2.
- Per role, sum the two highest-scoring games in one series, then take the highest-scoring series in the period.
- Only stats present on the role's War Banner score.
- Group has three emblem slots. Main keeps those three and adds slots four and five.
- Prefix and suffix conditions apply to all selected players and do not consume reroll tokens.
- The nine visible percentile reward anchors are recorded, but rewards between anchors remain unavailable; the project does not interpolate them.

### Group Roll contract

- Group grants 40 Roll tokens. The screen exposes three unique options shared by all three War
  Banners. Applying an option to one selected Banner or refreshing the offer costs one token and
  replaces all three options; an application never mutates another Banner.
- The hashed build `6888:10887746` snapshot `20260806T081345Z-702ddf2a6953` contains 28 operation
  definitions. IDs `1–8` have zero offer weight and are audit templates only. The 20 offered IDs
  are `9–17` and `23–33`; their positive weights sum to `168`.
- The same snapshot supplies the six legal Stats per color, five Trait Shapes, five Quality values
  and Quality Roll weights, role slot colors, mutation enums and target flags. A parser or contract
  mismatch blocks use of the transition engine.
- The client does not expose every random sub-choice rate. The project therefore separates exact
  legal support from probability models. Support allows a reroll to repeat the current value,
  includes every matching slot as a possible `OneColor` target, treats affected slots as separate
  draws, and clamps Quality changes to T1–T5. None of those support assumptions is labelled as a
  recovered Valve probability.
- Model-conditional work preregisters client weights, square-root-flattened weights and squared
  weights. All three preserve the same legal support. The Rate-agnostic route assigns no
  probabilities. Group is executable; Main fields are reserved but rejected until its policy is
  separately implemented and verified.

### Group Fantasy Scenario contract

- P3 maps the six client-visible Group result categories to `4/5/6/6/5/4` Series opportunities.
  The existing `1/2/5/5/2/1` capacities remain exact client evidence; the opportunity mapping and
  capacity-preserving `balanced_pairing` draws are explicit model assumptions until exact 2026
  Swiss execution is locally captured and hashed.
- Historical performance resamples complete BO2/BO3 Series only. BO3-only history fails the
  ten-block minimum for two Core pairs; BO2 restores coverage without inventing a third Game.
  BO1 and BO5 are excluded and counted.
- Every candidate reuses the same common Scenario IDs. Complete Banner Game score is formed before
  top-two Games and best-Series aggregation; a different Team may not be selected for each Emblem.
- Production Coach effects are unavailable/excluded until a complete validated prefix-plus-suffix
  future Scenario exists. This is not equivalent to asserting that a zero-bonus Coach is selected.
- A standalone descriptive Title layer may rank observable conditions for manual use without changing
  that production gate. Its current neutral default is `Cerulean + the Clutch`; Prefix must be
  revisited once the three final Banner teams are known.

## Known uncertainties

- The client internal name for late first blood says six minutes while localization says ten minutes.
- Multiple Fantasy percentile tables coexist in current client resources.
- Madstone, Smoke, Watcher, Lotus and Tormentor semantics are resolved to Valve's native per-player
  replay counters. The native replay pass overlays only presence-verified `exact` rows; OpenDota
  event maps remain diagnostic proxies and never fill a native `null`. The frozen P1 coverage is
  recorded in the linked implementation report.
- Missing replays and unvalidated client builds remain `null`; known old Watcher-zero replay builds
  must not be interpreted as exact zero.

The source decision and validation evidence are recorded in
[`ti2026-fantasy-proxy-stat-validation.md`](research/ti2026-fantasy-proxy-stat-validation.md), with
the completed coverage in
[`p1-native-replay-stats-implementation-2026-08-06.md`](reports/p1-native-replay-stats-implementation-2026-08-06.md).
The Roll extraction, assumptions and pure-transition acceptance evidence are recorded in
[`p2-roll-transition-engine-implementation-2026-08-06.md`](reports/p2-roll-transition-engine-implementation-2026-08-06.md).
