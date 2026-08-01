# Modeling protocol

## Team strength

Matches are ordered by UTC start time. The baseline keeps a time-decayed Elo rating and a
Glicko rating/deviation for every stable team ID. Pre-match probabilities are recorded before
each update. Evaluation uses chronological 70% training, 15% calibration and 15% untouched
validation windows; a 50% baseline, Elo, Glicko and their ensemble are reported with log loss,
Brier score, calibration error and accuracy.

Isotonic calibration is deployed only when it improves both log loss and calibration error on
the untouched window. Otherwise the run records `model-calibration-rejected` and uses the raw
Elo/Glicko ensemble. At least 12 of the 16 TI teams must have five earlier matches, or group
recommendations are blocked.

TI 2025 is also evaluated as a fixed, completely untouched tournament holdout. The release gate
requires both log loss and Brier score to beat the 50% predictor. Failure blocks the 2026 group
run instead of silently publishing a higher-accuracy but worse probability model.

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

Player/stat estimates use 150-day exponential decay and an eight-observation hierarchical prior.
Core and Support combine the two configured players; Mid uses one. Scoring keeps missing fields
as null, applies two best games per series and the best series per period, and only allows
`exact`/`derived` fields with at least 50% coverage into default recommendations. A selected
player with fewer than eight observations blocks publication.

The top-10% and top-100 objectives are explicitly low-confidence proxies until Valve's server
percentile behavior is confirmed. The top-100 choice must retain at least 85% of the expected
score baseline.
