# Team-strength v2 target-team evidence-network evaluation

- Evaluation `as_of`: `2026-08-02T02:35:10Z`
- Policy: `team-strength-adr-0002-v2`
- TI 2025 run: `backtest-effe4c58fa20777b`
- TI 2026 group run: `group-e96e904c6ed4456f`
- Data snapshot: `162d895434804d7ae9ee83bd4d4316fbf3b1ba7731bb6de7acc5b7c41b4532c4`

## Outcome

Policy v2 passed the corrected retrospective TI 2025 release gate and the resulting TI 2026 group
run passed artifact audit. Both runs are `publishable=true` with `warning` status; neither has a
blocking issue. The warnings remain material: complete Swiss-pairing rules are not yet verified,
unknown or unsupported evidence is excluded, and the connected-scope rolling validation rejected
isotonic calibration.

The change validates the main reason for using the target-team evidence network. It removed 5,961
positive-weight Games that were disconnected from the TI 2025 cohort while leaving raw weighted
Elo, weighted Glicko and their uncalibrated ensemble metrics exactly unchanged. Those Games were
not necessary for the target teams' raw ratings.

## Corrected audit rule

The pass gate no longer contains an exact eligible-Game count. It now requires:

- the complete holdout league and declared stable target-team IDs;
- patch, tier, time and `as_of` eligibility from the versioned policy;
- the union of positive-weight graph components containing those target teams;
- at least 14 direct target-patch Games for every TI 2025 target team;
- the deployed candidate to beat 50% on both log loss and Brier;
- recorded policy, data snapshot and selected match-ID hashes.

The corrected snapshot observes 661 direct TI 2025 target-patch Games. This is an audit output,
not a threshold. The earlier 751 value remains only in v1 historical evidence, where it documents
the erroneous union of TI 2025 and TI 2026 cohorts.

## TI 2025 network and metrics

| Item | Complete catalog | Target-team network |
| --- | ---: | ---: |
| Positive-weight Games | 10,466 | 4,505 |
| Teams | 1,182 | 501 |
| Effective weight | 2,610.13 | 1,082.87 |
| Disconnected Games excluded | — | 5,961 |
| Direct target-patch Games | — | 661 |
| Minimum direct Games for one target team | — | 14 |

Selected match-ID hash:
`37bdb6270adb6b8b5a4873d0ce1fe3a97beedf0378235931219e46d40d398024`.

| Candidate | Log loss | Brier | Calibration error | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| 50% | 0.693147 | 0.250000 | 0.048611 | 45.14% |
| Old unweighted ensemble | 0.681508 | 0.245403 | 0.141458 | 54.86% |
| Weighted Elo | **0.672658** | **0.240097** | **0.067457** | **57.64%** |
| Weighted Glicko | 0.705073 | 0.253541 | 0.138328 | 56.25% |
| Weighted raw ensemble | 0.682552 | 0.244712 | 0.113417 | 56.25% |
| Connected-scope calibrated candidate | 0.685103 | 0.247120 | 0.087127 | 48.61% |
| Deployed model | 0.682552 | 0.244712 | 0.113417 | 56.25% |

The rolling pre-holdout validation rejected isotonic calibration because its log loss was slightly
worse than the raw ensemble, despite better calibration error. The deployed model is therefore the
raw weighted Elo/Glicko ensemble. It beats 50% on both required metrics. Against the old unweighted
ensemble, its Brier improves by `0.000691`, but its log loss is worse by `0.001044`; it is not an
unambiguous two-metric improvement over the old model. Weighted Elo remains the strongest observed
candidate, but the holdout result is not used to change the locked 50/50 deployment ensemble.

## TI 2026 catalog refresh and network

The existing complete `/proMatches` catalog already supported local graph construction, so no
recursive opponent-team crawl was needed. A bounded incremental refresh was still appropriate
because the prior snapshot ended on August 1:

- command scope: 2026 professional catalog, leagues and patch metadata;
- detailed match downloads: disabled;
- team-history downloads: disabled;
- request attempts: 144;
- keyed monthly attempts after the run: 621 of the 50,000 hard ceiling;
- 2026 professional catalog: 13,856 Games, 19 more than the prior snapshot.

The refreshed TI 2026 target-team network contains 3,859 of 4,388 positive-weight Games across
455 connected teams and excludes 529 disconnected Games. All 16 target teams have final-model
evidence.

| Patch family | Games | Effective weight |
| --- | ---: | ---: |
| Target 7.41 | 1,852 | 648.45 |
| Immediate prior 7.40 | 2,007 | 28.54 |
| Total | 3,859 | 676.98 |

Selected match-ID hash:
`540e0ef365e2c9277d031e2fc002af1e112df4004b027a7e3a36e5a3f2327e6e`.

Six current team IDs had no positive-weight evidence in the historical pre-TI-2025 calibration
period; this is reported specifically as a calibration-period warning. It is not missing coverage
in the final 2026 model.

## Current expected-points group recommendation

This is the `balanced_pairing` scenario from 20,000 deterministic samples. It remains a warning,
not a final in-game answer, until the Swiss-pairing rules are verified.

| Slot | Teams |
| --- | --- |
| 4–0 | Vici Gaming |
| 4–1 | Aurora Gaming; Team Resilience |
| Elimination winner | BoomBoys; Team Falcons; Team Yandex; TEAM VISION; Team Spirit |
| Elimination loser | Team Liquid; LGD Gaming; OG; Nigma Galaxy; HULIGANI |
| 1–4 | Xtreme Gaming; GamerLegion |
| 0–4 | Iron Wing |

## Verification

- 45 offline tests passed.
- Ruff passed with no findings.
- Backtest audit: `publishable=true`, no blocking issue.
- Group audit: `publishable=true`, no blocking issue.
- Raw responses and previous v1 artifacts were not overwritten.

Artifacts: [TI 2025 backtest](../../artifacts/backtest-effe4c58fa20777b/backtest.json),
[TI 2025 model](../../artifacts/backtest-effe4c58fa20777b/model.json),
[TI 2026 recommendations](../../artifacts/group-e96e904c6ed4456f/recommendations.json),
[TI 2026 model](../../artifacts/group-e96e904c6ed4456f/model.json), and
[TI 2026 details](../../artifacts/group-e96e904c6ed4456f/details.json).
