---
status: accepted
---

# Separate Group and Main Fantasy stacks

TI 2026 Group and Main have different Banner sizes, Roll budgets, eligible-team lifecycles and
settlement scenarios. We keep them as separately versioned state, rule, OCR, solver and release
stacks behind one two-tab interface; only period-independent Emblem arithmetic and client-observation
primitives are shared. This accepts some duplication to prevent a Main screen from being truncated
or valued with Group scoring assumptions, while preserving frozen Group outputs for historical
reproduction.

Main calculability is independent from final-roster availability. Before the eight advancing Teams
and seeds are known, the Main stack is usable in `projected` eligibility mode: the client-facing
candidate set remains all sixteen Teams, while every coherent Scenario admits exactly eight and a
non-advancing candidate scores zero. The projected seed order is explicitly identified as a Group
category plus Team-strength proxy. It must not be presented as an official advancing list.

After Group completes, maintainers first refresh the time-bounded match and Fantasy raw evidence,
then import the eight stable Team IDs in official seed order and rebuild an `actual` Main release.
That release embeds its refreshed Fantasy Series pools and reduces the selectable candidate set to
the eight entrants. Failure to refresh the pool blocks the `actual` transition, but does not disable
the preceding projected Main calculator.
