# TI 2025 weighted team-strength evaluation

> Historical v1 result. Superseded by
> [the v2 target-team evidence-network evaluation](team-strength-v2-connected-network-2026-08-02.md).
> The blocked status below records the erroneous exact-count gate and is intentionally preserved.

- Run: `backtest-1713cdae07049ceb`
- Execution `as_of`: `2026-08-01T18:17:31Z`
- Training cutoff: `2025-09-04T08:04:55.999999Z`
- Policy: `team-strength-adr-0001-v1`
- Result: **blocked; TI 2026 was not run**

## Outcome

The weighted deployed model passed the probability-skill gate: it beat the constant 50% predictor
on both log loss and Brier and also improved over the old unweighted ensemble. The complete run did
not qualify because the preregistered 751 same-patch Game assertion could not be reproduced without
using the later TI 2026 participant list. The leakage-safe TI 2025 team scope contains 661 Games,
so the configured count gate correctly blocked continuation.

| Candidate | Log loss | Brier | Calibration error | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| 50% | 0.693147 | 0.250000 | 0.048611 | 45.14% |
| Old unweighted Elo | 0.695326 | 0.250109 | 0.098366 | 56.25% |
| Old unweighted Glicko | 0.678977 | 0.245034 | 0.169746 | 52.78% |
| Old unweighted ensemble | 0.681508 | 0.245403 | 0.141458 | 54.86% |
| New weighted Elo | **0.672658** | **0.240097** | **0.067457** | **57.64%** |
| New weighted Glicko | 0.705073 | 0.253541 | 0.138328 | 56.25% |
| New weighted ensemble | 0.682552 | 0.244712 | 0.113417 | 56.25% |
| New calibrated/deployed ensemble | 0.677564 | 0.242600 | 0.085973 | 56.94% |

Lower log loss, Brier and calibration error are better. Relative to the old unweighted ensemble,
the deployed weighted model reduced log loss by `0.003944` and Brier by `0.002803`. Weighted Elo was
the strongest individual candidate; weighted Glicko alone was worse than 50%, which should be a
specific target of a future, independently evaluated experiment rather than a post-holdout fix.

## Evidence and calibration audit

- The holdout contains all 144 TI 2025 Games, all on `7.39` and all OpenDota `premium`.
- Before weighting, 19,452 completed training Games were available.
- 10,466 had positive weight: 5,694 on target `7.39` and 4,772 on prior `7.38`.
- Total effective weight was 2,610.13: `7.39` contributed 2,509.93 and `7.38` only 100.20.
- 5,867 known unsupported-tier Games and 142 unknown patch/tier Games were assigned zero and
  audited; none updated Elo or Glicko.
- Same-patch coverage among the 16 holdout teams was 661 unique Games. The weakest team had exactly
  14, satisfying the minimum coverage threshold.
- Rolling calibration used three pre-holdout folds of 854, 855 and 854 Games. The first two folds
  supplied 1,709 calibration observations; the third accepted isotonic calibration before the
  tournament holdout was scored.

## Why 751 failed

The value 751 is exactly reproduced by taking the union of Games involving either a TI 2025 team
or a current TI 2026 team. Those sets overlap by only seven team IDs. Current TI 2026 membership was
not available at the TI 2025 cutoff, so using that union to certify a TI 2025 backtest would violate
the repository's `as_of` rule. The implementation therefore retains the locked mismatch as a
blocking issue instead of changing the scope after seeing the result.

Artifacts: [backtest](../../artifacts/backtest-1713cdae07049ceb/backtest.json),
[model and audit detail](../../artifacts/backtest-1713cdae07049ceb/model.json),
[run manifest](../../artifacts/backtest-1713cdae07049ceb/run.json).
