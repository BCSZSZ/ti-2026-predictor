# Model policy governance

An accepted model policy is the current reproducible operating rule, not a claim that the model is
true or optimal. Evidence may justify replacing it. The project keeps decision rationale,
executable constants, experiment work and observed results in separate artifacts so a later change
does not rewrite history.

## Artifact responsibilities

| Artifact | Purpose | Mutation rule |
| --- | --- | --- |
| `docs/adr/NNNN-*.md` | Why a consequential policy was chosen and what trade-off it accepts | Do not rewrite an accepted decision; mark it superseded and link its replacement |
| `config/models/<policy-id>.json` | Machine-readable constants and evaluation gates | Immutable after its first evaluated run; create a new policy ID for behavioral changes |
| `config/ti2026.yaml` | Selects the policy used by the current event | Change only after the replacement passes its declared gate |
| `.scratch/<experiment>/issue.md` | Local proposal, checklist, allowed data and acceptance criteria | Working document; not a model contract |
| `artifacts/<run-id>/` | Immutable inputs, hashes, model state, metrics and audit outcome | Never overwrite; a changed input produces a new run ID |
| `docs/reports/` | Human explanation of one identified run | May be superseded, never silently relabeled as a different run |

Empirical observations such as “this snapshot contains N eligible Games” belong in a run/data
profile with its `as_of`, target-team IDs, selection-rule version and snapshot hashes. They are not
acceptance thresholds. The v1 value `751` was traced to an erroneous union of TI 2025 and TI 2026
cohorts; the corrected TI 2025 snapshot observes `661` direct target-patch Games. ADR-0002 removes
both numbers from the gate. A run passes this part of the audit by applying the locked eligibility
and target-network rules to its identified snapshot, matching the declared target-team cohort and
meeting the intentional per-team minimum coverage threshold.

## Replacement workflow

1. Open `.scratch/<experiment>/issue.md` and state the hypothesis, expected mechanism, candidate
   policy ID, permitted tuning interval, untouched evaluation set, metrics and pass/fail rule.
2. Add a new config file; never modify the evaluated predecessor in place. Unit tests pin every
   changed constant, selection rule and edge case. Record observed counts in the run, not as gates.
3. Use only chronological rolling validation inside the declared tuning interval. Store every
   attempted candidate, including failures, so selection is visible.
4. Run the untouched holdout once after code, configuration and acceptance rules are locked. If its
   outcomes have already been inspected, label it a retrospective benchmark and reserve a new
   future tournament or time block as the next untouched holdout.
5. If the candidate passes, add a superseding ADR that records the evidence and trade-off, mark the
   previous ADR `superseded by ADR-NNNN`, and switch the tournament manifest's policy pointer.
6. If it fails, keep the old policy active and close the experiment with a report; a failed
   experiment does not require an ADR unless the rejection itself is an important lasting decision.

Changing comments, spelling or explanatory prose without changing semantics does not require a new
policy version. Any change that can alter eligible Games, weights, ratings, calibration,
probabilities or publication status requires a new policy ID and run. Once a holdout result is
known, relaxing its gate cannot be described as preregistered; it must be reported as a new,
post-hoc experiment.
