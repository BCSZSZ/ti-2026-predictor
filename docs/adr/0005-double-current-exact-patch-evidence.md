---
status: accepted
---

# Double the current exact-patch evidence

ADR-0001 and ADR-0002 continue to govern Major gameplay patch eligibility, League tier, age decay,
the target-team evidence network, Elo/Glicko updates and calibration. This decision adds one
versioned factor: a Game on the Current exact gameplay patch receives a `2.0` multiplier, while
every other Game keeps its former weight.

For the 2026-08-08 evidence cutoff, the reviewed Current exact gameplay patch is `7.41e`, active
from `2026-07-30T23:58:15Z`. The processed OpenDota match catalog records only the `7.41` Major
gameplay patch, so the executable policy stores this UTC boundary and classifies Games by
`start_time`. If a source later supplies an explicit letter suffix, it must agree with the boundary;
an explicit conflict keeps the ordinary family weight and produces an audit warning.

The resulting Game weight is:

\[
w_{\text{game}}
= w_{\text{major patch}}
\times m_{\text{current exact patch}}
\times w_{\text{tier}}
\times 2^{-d/60}
\]

where `m_current exact patch` is `2.0` only for `7.41e` Games at or after the reviewed activation
boundary and `1.0` otherwise. The Major gameplay patch weights remain `1.00` for target `7.41`,
`0.15` for immediate-prior `7.40`, and `0.00` for earlier families. Tier weights and the 60-day
half-life are unchanged.

This factor is implemented in the shared evidence builder, so team-strength Forecasts, Fantasy
Stat evidence, Coach Title evidence, playbook evidence and solver evidence cannot silently use
different patch weighting. Every run records the exact-patch policy, whether it was active, the
number of multiplied Games and their effective weight.

## Considered options

- `7.41e`-only evidence was rejected because its sample is still small and would discard useful
  same-family history.
- Replacing the existing time decay was rejected because recency already has a separate, stable
  meaning.
- A `2.0` multiplier on only the current exact patch was selected as a bounded preference that
  preserves all earlier weights and broadens consistently to every formal evidence consumer.

## Consequences

Published artifacts produced under the prior formula remain historical snapshots and must not be
presented as current after this policy is accepted. A later exact patch requires a reviewed UTC
boundary and a new versioned policy update; `7.41e` must not silently remain “current” forever.
