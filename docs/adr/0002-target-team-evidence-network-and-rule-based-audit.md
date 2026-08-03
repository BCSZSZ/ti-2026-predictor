---
status: accepted
---

# Use a target-team evidence network and rule-based audit

The team-strength model retains the patch, tier, time, Elo, Glicko, ensemble, and calibration
constants from ADR-0001, but replaces the complete positive-weight professional catalog with the
**Target-team evidence network**. After applying the preregistered eligibility weights at an
explicit `as_of`, build an undirected stable-team-ID graph from positive-weight Games and retain
the union of connected components containing the declared Forecast target teams. This preserves
the recursive opponent-strength evidence required by Elo and Glicko while excluding disconnected
competition ecosystems that cannot affect their raw ratings.

TI 2025 evaluation uses the 16 team IDs declared below and all 144 Games from league `18324` as the
retrospective Tournament holdout. Its training audit passes by reproducing the declared filtering
rule on an identified data snapshot, covering every declared team by at least 14 target-patch
Games, and satisfying the probability-skill gate. Eligible Game counts are observations, not pass
thresholds: `751` was an erroneous union of TI 2025 and TI 2026 cohorts, while `661` is the observed
TI 2025 direct target-patch count in the corrected snapshot. Neither number is a model gate.

Rolling calibration uses the same target-team evidence network and remains strictly before the
holdout. The data snapshot hash, selected match-ID hash, target-team IDs, scope rule, observed
counts, policy version, Git state, and random seed are recorded for every run. TI 2025 outcomes are
already known, so this is a transparent corrected retrospective comparison, not a fresh blinded
test; a future untouched tournament remains necessary for prospective confirmation.

## Considered options

- Target-team-only history was rejected because it cannot reliably value opponents.
- The complete professional catalog was rejected because disconnected components do not affect
  target-team raw Elo/Glicko ratings and unnecessarily broaden calibration and audit scope.
- The target-team evidence network was selected because it keeps recursively relevant opponent
  evidence with a deterministic, `as_of`-safe membership rule.
