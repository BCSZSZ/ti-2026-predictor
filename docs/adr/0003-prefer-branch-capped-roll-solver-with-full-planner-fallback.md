---
status: accepted
---

# Prefer the branch-capped Group Roll solver and retain the full planner as fallback

The Group Human Roll playbook is the primary product, while the Reference Roll solver is a
secondary independent auditor and the basis of a later local advisor. We will implement the
Branch-capped Roll solver first because the previously designed full planner adds substantial
configuration, statistical and runtime complexity. The full three-hour design remains recorded as
a dormant fallback rather than being discarded or silently mixed into the simpler solver.

## Preferred implementation: branch-capped solver

The preferred implementation keeps the exact terminal valuation of complete War Banners, repeated
Team matching over all 16 eligible teams and the declared Group roll objective. At each observed
state it expands only the currently legal actions: at most three shared Roll options applied to
three War Banners plus Operation refresh. Each root action is simulated through the remaining
40-Roll horizon under one fixed continuation heuristic; simulated future decisions do not create a
recursive search tree.

Quality and Trait interactions remain exact at terminal valuation, but their multi-step promise is
compressed into a precomputed synergy-potential lookup instead of branching over configuration
targets. Each Roll transition model and Mean-retention tolerance is evaluated as a separate bounded
run. Candidate comparison uses a fixed paired screen and fresh independent confirmation; a result
that the budget cannot distinguish is reported as an Unresolved Roll decision.

The fixed continuation compares each simulated future action using the same Expected Group score
and lower-tail CVaR10 objective after adding one synergy-potential term. Holding Stats fixed, the
term is the best exact Quality-and-Trait configuration gain within three attribute differences; all
15,625 positioned Quality-and-Trait configurations are reduced to a lookup rather than runtime
branches. Its multiplier is `(remaining Rolls - 1) / 39`, so early paths can pursue a multi-step
recipe while the final Roll uses immediate terminal value only. Stat changes receive no separate
future-potential term, and ties follow the Rate-agnostic safety ordering before refresh.

The planning estimate is approximately 2.4 million full-horizon-equivalent paths. At the measured
prototype rate of about `0.75 ms` per path this is roughly 30 minutes of raw simulation; confirmation,
overhead and reporting give the simplified solver a provisional ceiling of about 60 minutes. These
figures are performance hypotheses that must be benchmarked against the production implementation,
not release guarantees. Playbook evidence and freezing remain ahead of solver work.

## Retained fallback: full three-hour planner

The original design remains available as the **Full configuration Roll planner**. It includes:

- explicit Configuration target sets for complete positioned Quality and Trait states;
- Configuration target value, Reachability signatures and Structural target screening;
- Configuration challengers with Simulation target commitment and Target-directed continuation;
- candidate retention across the primary Roll transition model, two declared variants and
  `epsilon = 0%, 1%, 2%, 5%`;
- adaptive Race-and-confirm evaluation with simultaneous false-elimination control; and
- independent confirmation of every reported advantage.

Its recorded sampling plan allocates at most 96,000 of 480,000 paths per current decision to the
race (`52,000` primary and `22,000` per variant) and at least 384,000 to independent confirmation
(`208,000` primary and `88,000` per variant). Across the 40 Group decisions this was estimated as
about 9.84 million full-40-equivalent paths and 123 minutes of simulation at `0.75 ms` per path. The
complete run targets three hours, has an absolute five-hour ceiling, stops new computation at four
hours forty-five minutes and reserves the final fifteen minutes for reporting.

## Consequences

The preferred solver is easier to implement, test and explain, and reserves more of the runtime
envelope for the independently derived playbook evidence. It may miss uncommon long-horizon
Quality or Trait chains, so it must be described as an approximate counterexample finder rather
than an optimum.

The full planner is neither deleted nor automatically enabled. It may be reconsidered only after
the simplified solver fails this accepted effectiveness gate:

1. on stratified states with one to three Rolls remaining, where legal outcomes can be exhaustively
   evaluated, the one-sided 95% upper bound on decision regret must be at most 2%;
2. on independent complete 40-Roll paths, Expected Group score and lower-tail CVaR10 must not be
   statistically worse than both one-step greedy and the Rate-agnostic safety baseline; and
3. no more than 10% of Common playbook situations may end in an unresolved comparison.

Failure of any quality condition opens an escalation review; it does not activate the fallback.
Exceeding the simplified solver's provisional 60-minute ceiling is a performance failure to
optimize or rescope, not evidence for enabling the more expensive full planner. A later activation
still requires a new explicit decision accepting the added complexity.
