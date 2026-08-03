---
status: superseded by ADR-0002
---

# Preregister game evidence weighting and the TI 2025 holdout

This decision fixes how much each historical Game may influence a team-strength Forecast before
running the new weighted candidates against the TI 2025 holdout. It prevents old patches,
lower-grade events and distant matches from dominating current strength, while preserving the
immediately preceding gameplay version as a weak prior. The repository record was created on
2026-08-02 from the methodology agreed in an earlier session; that date records this transcription,
not the original agreement. An earlier unweighted TI 2025 run already existed, so this is a locked
retrospective comparison rather than proof that the tournament outcomes were unknown to everyone.

The executable constants live in
[`config/models/team-strength-v1.json`](../../config/models/team-strength-v1.json). “Accepted” means
this is the current operational policy; it does not assert that the policy is scientifically true
or globally optimal. Changes follow the [model governance protocol](../model-governance.md).

## Locked Game weight

The symbol `w_match` is retained for continuity, but it applies to one **Game / 单局**, not an
entire Series:

\[
w_{\text{match}}
= w_{\text{patch}}\times w_{\text{tier}}
\times 2^{-d/60}
\]

Here `d` is the non-negative fractional number of days from the Game's UTC `start_time` to the
Forecast run's explicit UTC `as_of`. A Game later than `as_of` is a leakage violation and is
excluded rather than assigned a clamped age.

The following constants are preregistered and must not be retuned from TI 2025 outcomes.

| Dimension | Condition | Weight |
| --- | --- | ---: |
| Major gameplay patch | Target patch family | `1.00` |
| Major gameplay patch | Immediate prior patch family | `0.15` |
| Major gameplay patch | Any earlier family | `0.00` |
| League tier | OpenDota `premium` | `1.00` |
| League tier | OpenDota `professional` | `0.75` |
| League tier | Any other or unknown value | `0.00` |

Letter suffixes are removed when determining a Major gameplay patch: `7.41d` and `7.41e` both
belong to `7.41`; `7.41` and `7.42` do not. “Immediate prior” means the preceding family in the
chronological Valve patch sequence, not the previous value observed in the local dataset and not
the previous calendar year.

The time component has a fixed 60-day half-life:

| Age | Time weight |
| ---: | ---: |
| 0 days | `1.0000` |
| 30 days | `0.7071` |
| 60 days | `0.5000` |
| 120 days | `0.2500` |

Consequently, a 30-day-old `professional` Game on the target patch has weight
`1.00 × 0.75 × 0.7071 ≈ 0.53`. Under the same conditions, a Game on the immediate prior patch has
weight `0.15 × 0.75 × 0.7071 ≈ 0.08`.

Calendar year is not an input. For example, if the target family is `7.41`, `7.40` receives `0.15`
even if that Game occurred in 2025, while `7.39` and earlier receive zero. All 2025 Games are zero
for a 2026 Forecast only when every 2025 Game in its snapshot is older than the target's immediate
prior family.

## Rating updates

For Elo, replace the unweighted update with:

\[
R'_i = R_i + K\,w_{\text{match}}(s_i-p_i)
\]

and apply the corresponding opposite update to the opponent. `K` and any other model parameters
must be locked using only rolling time validation strictly before the TI 2025 holdout.

For Glicko, weight both the score residual and the information contribution. If `g_j`, `E_j` and
`s_j` have their usual Glicko meanings for Game `j`, the rating-period aggregates must contain:

\[
A=\sum_j w_j g_j(s_j-E_j), \qquad
B=\sum_j w_j g_j^2 E_j(1-E_j)
\]

The Glicko update must use both weighted quantities. Scaling only the rating change while leaving
the information gain unweighted is non-conforming because it would still make a low-weight Game
reduce uncertainty as if it were a full observation.

## Eligibility and audit

- An unknown Patch, a Patch that cannot be normalized, an unknown League tier, or an unsupported
  League tier is excluded and recorded in the run audit; it is never silently assigned a useful
  default.
- A zero-weight Game does not update Elo, Glicko rating, or Glicko uncertainty.
- The target Major gameplay patch must come from evidence available at `as_of`. If it is unknown,
  the Forecast is blocked.
- Every run records included and excluded Game counts and total effective weight by normalized
  patch family and League tier. Unknown-patch and unknown-tier exclusions are reported separately.
- The data snapshot, rule/config version, Git commit, formula version, `as_of` and random seed remain
  part of the reproducibility record.

Under the TI 2025 target patch `7.39`, evidence from 2022 and 2023 is therefore zero-weight. The
coverage expectation recorded with this decision is 751 eligible same-family `7.39` training
Games, with each of the 16 TI teams represented by at least 14 such Games. A conforming evaluation
must reproduce these counts from its identified immutable snapshot or report the discrepancy and
stop; it may not change the locked weights to compensate. The immediate prior family remains only
a 15% weak prior and is not responsible for filling same-patch coverage.

## Frozen TI 2025 evaluation

All 144 TI 2025 Games form one untouched Tournament holdout. They are not used to select weight
constants, `K`, Glicko settings, ensemble coefficients, calibration method or any other model
choice. Parameter checks use rolling time validation whose training, calibration and validation
Games all precede TI 2025.

After those choices are locked, the holdout is evaluated once and reports at least log loss,
Brier score and calibration for:

1. a constant 50% predictor;
2. the current unweighted Elo and Glicko baselines;
3. the new weighted Elo;
4. the new weighted Glicko;
5. the weighted Elo/Glicko ensemble, before and after its preregistered calibration step.

TI 2025 outcomes may explain the final comparison but may not change the candidates or their
parameters. Any later change to these locked constants must supersede this ADR and use a new,
previously untouched holdout; it cannot claim a fresh preregistered TI 2025 result.

## Consequences

Existing forecasts that use time-only decay, accept unknown patch/tier evidence, or train on Games
whose version weight is zero do not implement this decision. They remain useful as explicit
unweighted baselines, but they cannot be marked Publishable under this protocol until the weighted
models, exclusion audit and regression tests are implemented.
