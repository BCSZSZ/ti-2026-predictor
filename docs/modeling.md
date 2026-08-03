# Modeling protocol

## Team strength

The current operational policy is `team-strength-adr-0002-v2`, recorded in
[ADR-0002](adr/0002-target-team-evidence-network-and-rule-based-audit.md) and implemented by the
versioned configuration at `config/models/team-strength-v2.json`. The tournament manifest selects
the active policy. A run records its policy ID, policy hash, data snapshot hash and selected
match-ID hash.

For a Game `d` days before the run's explicit UTC `as_of`:

\[
w = w_{patch}\,w_{tier}\,2^{-d/60}
\]

The target Major gameplay patch has patch weight `1.00`, its chronological predecessor `0.15`,
and older versions zero. OpenDota `premium` has tier weight `1.00`, `professional` has `0.75`, and
all other or unknown values are excluded and audited. Letter hotfixes share their numeric family.

After weighting, the model builds an undirected stable-team-ID graph from positive-weight Games
and retains the union of connected components containing the declared Forecast target teams. This
target-team evidence network recursively preserves opponents and opponents of opponents while
removing disconnected competition ecosystems. For TI 2025, `661` target-patch Games directly
involve the declared 16 teams, but that observed count is not a pass threshold.

Production Elo applies `K × w × (result - probability)` and does not retain the superseded
120-day rating-to-1500 decay. Glicko multiplies both its score residual and information gain by
`w`. The old time-decayed, unweighted Elo/Glicko implementation remains callable only as the
explicit benchmark required by ADR-0001; Forecast generation uses the weighted model.

Calibration uses the same target-team evidence network and is checked without random splitting.
For the target patch's pre-holdout Games, the
first 55% establish the initial history and the remaining 45% form three expanding-origin rolling
validation folds. The first two fold predictions fit the isotonic candidate; the third accepts it
only when both log loss and calibration error do not worsen. An accepted curve is then fitted to
all three pre-holdout out-of-fold prediction sets. TI 2025 outcomes never fit that curve.

TI 2025 league `18324` is evaluated as a fixed 144-Game holdout on patch `7.39`. The report compares
50%, unweighted Elo, unweighted Glicko, their raw ensemble, weighted Elo, weighted Glicko, the
weighted raw ensemble, the calibration candidate and the deployed weighted model. Publication
requires the deployed model to beat 50% on both log loss and Brier, match the declared stable-ID
cohort and give every target team at least 14 direct target-patch Games. Exact eligible-Game counts
are reported but never used as gates. A failed gate blocks the 2026 group Forecast even when
probability metrics improve.

At least 12 of the 16 current TI teams must have five positive-weight earlier Games, or group
recommendations are blocked.

## Group projection

Until Valve publishes full Swiss pairing rules, the simulator draws joint random-utility
rankings under strength-seeded, balanced and high-variance scenarios. Every draw preserves the
exact `1/2/5/5/2/1` capacity and assigns every team once. Results include scenario sensitivity;
this approximation is always visible as a warning.

## Main Event

The standard eight-team double-elimination topology has fourteen binary nodes. All `2^14 =
16,384` coherent grids are enumerated. Nonlinear activity points are evaluated on a deterministic
shortlist formed from exact node marginals and complete path probability. Missing real seeds is a
blocking condition.

## Fantasy

Player/stat estimates use the same preregistered evidence policy as team strength: target Major
gameplay Patch `1.00`, immediately previous Major gameplay Patch `0.15`, older Patches `0`;
OpenDota `premium` `1.00`, `professional` `0.75`, other tiers `0`; and a 60-day time half-life.
Production generation fails closed if that patch/tier evidence set cannot be built. An
eight-observation hierarchical prior remains for sparse players. Core and Support combine the two
configured players; Mid uses one. Scoring keeps missing fields as null, applies two best games per
series and the best series per period, and only allows `exact`/`derived` fields with at least 50%
coverage into default recommendations. A selected player with fewer than eight observations
blocks publication.

The role/color priority guide is calculated over the top 25% of teams under the expected-points
role model, rather than over every tournament team or one hand-picked player. It publishes three
descriptive heuristics: stable (`mean - 0.85 × std`, floored at zero), expected (`mean`), and upside
(`mean + 1.65 × std`). These are ranking scores, not calibrated percentile forecasts. Proxy fields
are reported in a separate sensitivity section and never silently mixed into the default arrows.

The target-connected opponent network applies to team-strength fitting. Fantasy player/stat
history instead uses every positive-weight Game containing a target player ID, including Games for
former teams; otherwise the graph scope could silently discard legitimate personal history. Team
strength and player-stat evidence therefore share patch/tier/time weights but intentionally differ
in scope.

The top-10% and top-100 objectives are explicitly low-confidence proxies until Valve's server
percentile behavior is confirmed. The top-100 choice must retain at least 85% of the expected
score baseline.
