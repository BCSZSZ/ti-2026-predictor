# P3 Group Stat scenarios and exact terminal valuation

Status: complete

## Baseline

- Branch: `codex/group-roll-playbook-v1`
- Starting commit: `2577469c54069c7153243e969a4cd1d95ef3bea5`
- Remote divergence: `0 / 0`
- Starting worktree: clean
- P1 native-Stat gate: complete
- P2 Roll-transition gate: complete
- Reference `as_of`: `2026-08-06T08:15:00Z`

P3 is the last shared arithmetic layer before the two Human Roll playbooks are independently
derived. It may generate governed Stat evidence and evaluate supplied Banner states. It must not
generate, inspect or distil any Reference Roll solver result.

## Stage objective

Build a reproducible Group-only Scenario set from complete historical Series blocks, then value a
complete three-Emblem Banner with the real per-Game, top-two-Games-per-Series and best-Series-in-
Period order of operations. Every candidate comparison must reuse the same scenario IDs, and Team
matching must retain one whole Team vector rather than selecting a different Team for each Stat.

## Frozen minimum modification scope

1. Add one versioned Group Scenario policy; do not add a player-performance ML model.
2. Add an immutable Series-block and common-Scenario builder using the existing governed Game
   evidence weights and stable manifest IDs.
3. Add vectorized Stat, complete-Banner and three-role terminal valuation, including exact Quality
   and positioned Trait arithmetic.
4. Add one reproducible Group-evidence entry point and machine-readable summary for P4.
5. Add focused offline fixtures/tests and update only the domain/rule documentation needed to make
   the new terms unambiguous.

P3 does not create either Human Roll playbook, a Roll policy, the Branch-capped solver, a Main
Scenario implementation or the Interactive advisor.

## Frozen Scenario contract

### Evidence eligibility

- `as_of` is mandatory and UTC. A Game starting at or after the cutoff is excluded.
- Start from the existing global Fantasy player-history evidence calculation. Only positive
  patch/tier/age-weight Games are eligible.
- A Stat value is usable only when its provenance exactly matches the current rule (`exact` or
  `derived`). `proxy`, `unavailable`, a missing provenance column and `null` all fail closed.
- The P3 common matrix requires all 18 formal Stats. It never imputes a missing value and never
  substitutes a proxy.
- Current Team/role membership comes from the manifest's stable account IDs and roster-effective
  interval at `as_of`. Historical display names and current Team names are not join keys.

### Full-Series blocks

- Group Series are BO3. The first real-snapshot gate showed that BO3-only history leaves OG Core
  with only three complete blocks and Nigma Core with five, below the frozen ten-block minimum.
  The predictive pool therefore admits historical BO3 (`series_type = 1`) and BO2
  (`series_type = 3`): both contain exactly two or three played Games and require no invented Game.
  BO1 and BO5 remain counted in the audit but excluded; the project does not lower the sample gate
  or give a BO5's extra Games to a Group BO3 forecast.
- A block contains every played Game in one completed accepted Series (two Games for BO2 or a BO3
  sweep, three for a full BO3). An incomplete one-Game Series is rejected.
- Core keeps the current position-1/3 pair together; Support keeps the position-4/5 pair together;
  Mid keeps the current position-2 player. Every required player must appear for the same stable
  historical Team in every Game, and that historical Team must remain consistent through the
  Series.
- Per-player Stat scoring occurs first. Core/Support then average the paired player scores inside
  each Game. A block is the indivisible resampling unit: neither a Game nor one member of a pair is
  sampled independently.
- The Series sampling weight is the mean of its governed Game evidence weights. Predictive Series
  are sampled with replacement; this is a declared empirical model, not a Valve Roll-rate claim.

### Group opportunity model

The client-backed result capacities are `1/2/5/5/2/1`. Under the published modified-Swiss shape,
the corresponding number of Group-period Series opportunities is frozen as:

| Result category | Series |
| --- | ---: |
| `four_zero` | 4 |
| `four_one` | 5 |
| `elimination_winner` | 6 |
| `elimination_loser` | 6 |
| `one_four` | 5 |
| `zero_four` | 4 |

The existing capacity-preserving `balanced_pairing` Group model supplies one joint category vector
per Scenario. It is still an approximation of the unpublished/local-unavailable exact 2026 pairing
execution, and the output must retain that warning. All three Fantasy roles share the same Team
category in a Scenario. Conditional on that category, role performance blocks are independently
sampled; cross-role historical performance correlation is therefore an explicit v1 limitation.

The production policy uses `8,192` common Scenarios. Each Team/role pool needs at least ten complete
Series blocks. Random streams are derived from the declared seed plus stable Team and role IDs, so
iteration order cannot change the result.

## Frozen terminal valuation contract

1. A block retains Game-level base Stat scores. Three Emblem Stats are combined at Game level
   before any Series/Period maximum; independently aggregated Stat maxima must never be added.
2. Quality and all active self/adjacent Trait modifiers use the existing exact positioned Banner
   arithmetic and apply additively to each Emblem's base score.
3. A Coach multiplier may enter only through a validated, scenario-aligned per-Game candidate.
   Current production evidence cannot form complete validated prefix-plus-suffix future scenarios,
   so Coach is explicitly `unavailable/excluded` in P3 production—not silently treated as a zero-
   bonus title. The valuation API may exercise a supplied validated multiplier in fixed tests.
4. For each Team, each sampled Series sums its best two complete-Banner Game scores; the Period
   value is the maximum sampled Series.
5. A Banner evaluation retains all 16 Team outcome vectors on identical Scenario IDs. A one-Banner
   match selects one whole Team by the declared risk configuration; it never selects per Stat or
   per Scenario.
6. Three-role matching examines whole `(Core Team, Mid Team, Support Team)` combinations and scores
   their Scenario-wise sum. It maximizes lower-tail `CVaR10` among combinations whose mean is within
   `epsilon` of the maximum mean. Thus it never sums separately optimized Banner CVaRs. P3 verifies
   `epsilon = 0`; P4/P5 may request `0%, 1%, 2%, 5%` through the same interface.
7. Lower-tail `CVaR10` means the arithmetic mean of the worst ten percent of complete Group
   Scenario outcomes, using a deterministic fractional boundary when the sample count is not a
   multiple of ten.
8. Terminal cache identity includes the data snapshot, Scenario semantic hash, complete Banner,
   Coach-candidate identity and risk configuration. Cache contents are arithmetic only and contain
   no policy.

## Stat evidence and uncertainty contract

- A single-Stat Forecast uses a neutral multiplier of `1.0`, then performs the same top-two/best-
  Series aggregation and all-16-Team matching.
- For every role/color/Stat, report the best-Team mean, runner-up mean, all-16 mean, selected-Team
  lower-tail CVaR10, descriptive maximum among eligible observed Series, complete block counts and
  provenance coverage.
- Grade-stability uncertainty resamples complete Series blocks. The fixed implementation target is
  400 clustered bootstrap replicates with 512 predictive Scenarios per replicate and a 95% interval
  on the best-equals-100 relative index.
- P3 reports the point index and interval only. P4 applies the already accepted 84.6%/44% grade
  boundaries. An interval crossing a boundary is a separate `boundary` marker and never changes the
  point grade.

## Acceptance contract

P3 passes only if all of the following hold:

1. Fixed scoring fixtures reproduce base Stat, Quality, adjacent/self Trait, duo mean, top-two and
   best-Series arithmetic, including a supplied validated Coach multiplier.
2. Tests prove that a Series resample cannot separate its Games or Core/Support players.
3. Future Games, non-positive evidence, wrong provenance, `null`, incomplete Series, cross-Team
   pairs and non-BO3 Series fail closed and are audited.
4. All five P1-native Stats enter production only with exact provenance and complete-block coverage.
5. Team matching chooses exactly one Team per role, retains its whole vector and is rerun after a
   candidate Banner change.
6. Three-role valuation uses Scenario-wise sums and joint CVaR; a fixture must distinguish this
   from summing per-Banner CVaRs.
7. Every paired comparison shares identical Scenario IDs and sampled Series references.
8. A fixed snapshot/config/seed reproduces byte-identical Scenario, Stat-evidence and terminal-value
   semantic hashes.
9. The reference cached-snapshot run completes comfortably inside the later three-hour target and
   records its wall times separately from P1 replay backfill.
10. Ruff, focused tests, full offline tests and project-level regression review pass.

## Review and cleanup gate

After acceptance, search for duplicated scoring/aggregation paths, any proxy fallback, player-name
joins, per-Stat Team cherry-picking, unpaired Scenario draws, hidden Coach neutrality and P3 code in
Notebook/UI paths. Remove only a verified superseded production path. Then change this report to
`complete`, record evidence/hashes/runtime, commit and push P3. A failed gate is documented and
pushed truthfully instead.

## Implemented result

P3 adds two policy-free arithmetic modules and one governed generation entry point:

1. `fantasy/scenarios.py` validates the versioned Scenario policy, builds immutable complete-Series
   blocks, samples order-independent Team/role streams and hashes the resulting common Scenario set.
2. `fantasy/valuation.py` evaluates a neutral single Stat or a supplied complete Banner without
   collapsing Game order early. It supports validated scenario-aligned Coach multipliers, one-
   Banner matching, joint three-role matching, lower-tail CVaR10, an arithmetic-only cache and
   complete-Series clustered bootstrap intervals.
3. `ti fantasy group-evidence --as-of <UTC> --bootstrap` composes the current governed evidence,
   capacity-preserving Group model and those pure layers into an immutable JSON evidence package.
   `--no-bootstrap` remains a development smoke route and is explicitly `blocked` as formal
   P3/P4 evidence.

The old `FantasyRecommender` and its `2.08` Series approximation remain available only as the
existing generic recommendation/baseline route. They are not consumed by the P3 evidence command
or future P4 manual evidence. Removing them would change a separate user-facing command and is not
a verified P3 replacement cleanup.

## BO3-only gate finding

The first real-snapshot smoke run failed the frozen ten-block minimum:

- BO3 only: `1,732` Team/role blocks in total; OG Core `3`, Nigma Core `5`;
- BO3 + BO2: `2,373` blocks; minimum `10`, with no sparse pool;
- BO3 + BO2 + BO5: `2,506` blocks; minimum `11`.

Lowering the minimum to three would have hidden severe sampling uncertainty. Including BO5 would
give a Group BO3 forecast up to five historical Game opportunities. The implemented compromise is
therefore complete BO2 plus BO3 only: every admitted block still contains exactly two or three
played Games, no player/Game is split, and BO1/BO5 exclusions remain visible. This is an empirical
implementation correction recorded before any P4 grade or manual rule was generated.

## Frozen production evidence

- Clean-commit evidence run: `fantasy-f6f311d72ccbea4a`.
- Recorded Git commit: `362ddb7b97bd1e6c26192b7cc3a8a40003fe4331`.
- Explicit cutoff: `2026-08-06T08:15:00Z`.
- Seed: `20260813`.
- Scenario policy SHA-256:
  `e28876f6573afcdd261c044c215ece5fbbf6bc9ff0cf02324defcf445b961065`.
- Data snapshot SHA-256:
  `931cd7e06cefc5fbae44025d4b31c3e0f15c583740bc989e2fa09152d084e203`.
- Series-pool set SHA-256:
  `47bb84b129cb503dcf52ddec2bdd1312b24a3ed02f1fb8f63f532802b531786d`.
- Common Scenario SHA-256:
  `872533c3a40cb8a23bb90158234fca40294b940631805ae192d0813ec699e6a2`.
- Stat Forecast SHA-256:
  `0bd1d204b2b4c405ae8ca1ea03e45e8a685a8efd4bd4751ca9c4a99c6afd38d1`.
- Cluster-bootstrap SHA-256:
  `1faa90a05fdc34958081793a823f29ce759ad69a90cb026656e19d3b605c17b8`.
- Non-optimized terminal smoke SHA-256:
  `bbcfc0585001286fd2ccf6900d4fcf908951d5d28002f057a0a20c9974a45ec5`.
- Evidence semantic SHA-256:
  `f42517fa5c0c596f2b15397ad2206136d48b0ff7fef578e131b4a919aa7fd9b8`.
- Serialized evidence file SHA-256:
  `dfc07e05e8d3425cdd3d2a50eb58be28c031756be69f9ae79dc6e9fe7da89d80`.

The semantic and serialized hashes differ deliberately: the semantic hash is computed over the
payload before its self-hash field is added, while the file hash covers formatted JSON including
that field.

## Coverage and uncertainty evidence

- Positive-weight evidence Games: `4,388`.
- BO1/BO5 Games excluded for Group format mismatch: `936`.
- Eligible BO2/BO3 Games: `3,452`, forming `1,405` structurally complete Series before current-
  player pairing.
- Final pools: all `48` required `16 Team × 3 role` keys; minimum `10`, maximum `88` complete
  Series blocks.
- Stat Forecast rows: all `42` legal role/color/Stat combinations (`12 Core + 18 Mid + 12
  Support`).
- Madstone, Smoke, Watcher, Lotus and Tormentor each have `10,334 / 10,334` eligible target-player
  rows at exact provenance. Their complete-block provenance coverage is `1.0`; no proxy or null
  enters a pool.
- Bootstrap: `400` weighted full-Series replicates × `512` predictive Scenarios, 95% intervals.
  Nineteen of 42 role/color/Stat rows cross a working 44% or 84.6% boundary and are marked
  `boundary`; the point indexes remain unchanged for P4 grading.

The terminal smoke uses fixed, visibly non-optimized reference Banners only to exercise production
arithmetic. Its selected Team IDs and score are not a Fantasy recommendation and must not be used
to derive P4 manual rules.

## Acceptance evidence

1. Fixed tests reproduce Stat factors, inverse Death scoring, exact Quality and positioned Trait
   effects, duo mean, complete-Banner Game sums, top-two Games, best Series and supplied validated
   Coach multiplication.
2. A constructed counterexample gives complete-Banner top-two value `220` while independently
   optimizing the two Stats would falsely give `320`; the implementation returns `220`.
3. Series blocks expose read-only matrices and stable player/match IDs. Tests reject proxy
   provenance, future captures, BO5, mixed/cross-Team pairs, duplicate identities, incomplete
   Series and insufficient pools.
4. Every Scenario row satisfies the exact `1/2/5/5/2/1` capacity; block references are paired,
   unused Series slots are `-1`, and a Scenario cannot be evaluated against a different pool hash.
5. Candidate Banners retain a 16-Team matrix. Tests prove matching returns exactly one stored Team
   row and that a changed Banner produces a new value/match hash.
6. A joint-risk counterexample has three separate role CVaR25 values summing to `0`, but the true
   CVaR25 of their Scenario-wise Group sum is `200`; P3 returns `200`.
7. Unknown Traits, malformed Coach evidence, Scenario-misaligned Coach candidates, invalid Group
   capacity and non-hex snapshot identities fail closed.
8. All five P1-native Stats occur in the 42-row formal package only under exact provenance.
9. Two consecutive complete validation runs reused the same immutable artifact successfully. A
   third run from clean commit `362ddb7` reproduced every semantic/file hash above and recorded
   that exact commit in `run.json`. Runtime-only measurements remain outside the deterministic
   evidence payload.
10. The focused P1/P2/P3 scoring/transition suite passes `26` tests. The complete offline suite
    collects `97`: `96 passed`, with only the opt-in cached-replay integration skipped. Ruff finds
    all `52` Python files formatted and clean.

## Runtime evidence

Two consecutive validation runs plus the clean-commit run on the implementation host measured:

| Component | Validation 1 | Validation 2 | Clean commit |
| --- | ---: | ---: | ---: |
| Series-block build | 11.371s | 11.337s | 11.399s |
| 8,192 common Scenarios | 0.079s | 0.079s | 0.078s |
| 42 Stat Forecasts | 0.577s | 0.575s | 0.564s |
| Terminal smoke | 0.034s | 0.034s | 0.034s |
| 400×512 clustered bootstrap | 3.012s | 3.010s | 3.002s |
| Total | 15.073s | 15.035s | 15.076s |

This is about `0.14%` of the three-hour target and far below the five-hour safety ceiling. It is a
P3 foundation benchmark, not a claim about P4 40-Roll manual validation or P5 solver runtime.

## Audit and project review

- `ti audit fantasy-f6f311d72ccbea4a` reports `publishable: true`, with only governed warnings for
  exact Swiss execution, cross-role correlation, unavailable Coach scenarios, known Coach First-
  Blood conflicts, excluded evidence tiers and rejected isotonic calibration.
- No live network is used by tests or the P3 command. The reference run reads only captures locally
  available by its cutoff.
- No name-based join, proxy fallback, null-to-zero conversion, per-Stat Team cherry-pick, separate
  role-CVaR sum, independent candidate resampling, Notebook dependency or UI policy was introduced.
- The terminal cache key contains Scenario/data/pool identity, exact Fantasy rule arithmetic,
  complete Banner/Coach identity and risk identity. It stores arithmetic only.
- P1 replay ingestion, P2 transition support, generic prediction generation and local web binding
  remain intact under the full regression suite.
- No Reference Roll solver result exists or was inspected. The P4 independent-manual origin gate
  remains intact.
