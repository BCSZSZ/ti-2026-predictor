# P2 Roll rule snapshot and pure transition engine

Status: complete

## Baseline

- Branch: `codex/group-roll-playbook-v1`
- Starting commit: `87fde61eb76618249fb41bf2710618701e56cd30`
- Remote divergence: `0 / 0`
- Starting gate: Ruff and formatting pass; `76` tests collect; the default offline suite passes
- Current client evidence: snapshot `20260806T073626Z-2e6c25f7c49e`, Steam build
  `6888:10887746`

The existing glossary already fixes Emblem, War Banner, Roll option, Apply Roll option, Operation
refresh, Roll decision and Group roll policy. P2 introduces no competing domain term and needs no
new ADR: the source-backed operation schema and pure engine are versioned, local and replaceable.

## Stage objective

Make the client-visible Group Roll rules machine-readable and implement a deterministic, immutable
transition kernel that later playbook and solver routes can share without adding valuation or
policy conclusions.

## Frozen client operation surface

The current `fantasy_crafting.vdata` exposes `28` operation definitions:

- zero-weight audit templates: IDs `1–8`;
- positive-weight offered operations: IDs `9–17` and `23–33` (`20` total);
- sum of positive client weights: `168` (`9×10 + 4 + 8 + 3×(10+6+6)`);
- offered option count: `3`.

The parser must preserve raw client IDs, weights, outer target, localization key and every mutation
operation/target flag. Zero-weight templates remain in the snapshot but can never be sampled.

## Minimal modification scope

1. Extend client-source inspection and snapshot comparison with normalized Gems, Traits, Qualities,
   Tablet slots and all Roll operations from `fantasy_crafting.vdata`.
2. Add only the cross-source Roll contract and declared outcome assumptions to the canonical rule
   file; do not duplicate the full client operation table there.
3. Add one pure `fantasy/roll.py` module containing immutable state/action/rule/outcome types,
   validation, legal actions, support enumeration, realized next-state construction, the three
   preregistered transition models and Rate-agnostic interval ordering.
4. Add fixed offline rule fixtures plus focused unit/property tests.
5. Reserve `period` and `slot_count` in state, but reject Main execution explicitly.

No historical Stat estimation, Team matching implementation, Group valuation, human playbook,
Branch-capped solver, simulation budget or UI is in P2.

## Explicit outcome assumptions

The client exposes operation weights and Quality weights, but not every random sub-choice rate. P2
therefore labels these as model assumptions rather than Valve facts:

- a rerolled attribute may realize its current value again;
- multiple affected Emblems draw independently;
- `OneColor` support includes every matching slot; unweighted target choice is uniform only inside
  a probability model;
- `IncreaseOneQuality` support selects each of the three slots and clamps Quality at T5;
- `IncreaseTwoQualitiesDecreaseOne` support selects each slot as the decreased slot, increases the
  other two and clamps at T1/T5;
- Trait and Stat results are uniform only in model-conditional sampling because the client exposes
  no weights; the Rate-agnostic route assigns no probability;
- unknown enums, missing target colors, malformed offers and zero-weight offered operations fail
  closed.

## Acceptance contract

P2 passes only if all of the following hold:

1. All 28 definitions round-trip from a hashed client fixture; the 20 positive IDs and weights match
   the current client, while IDs 1–8 remain audit-only.
2. Canonical legal Stats by color, five Traits, Quality bonuses/weights, three Group slots per role,
   40 tokens and the three-unique-shared-options contract agree with the snapshot/config evidence.
3. Every positive operation has property-based coverage on every applicable Group Banner and
   produces only legal attribute states.
4. Options stay unique, exactly one token is consumed, applying changes only the selected Banner,
   and apply/refresh both require a complete replacement offer.
5. Same snapshot, transition model and seed produce identical offer and mutation samples.
6. Primary, square-root-flattened and squared-sharpened models preserve identical legal support;
   zero-weight templates never appear.
7. Rate-agnostic action intervals use all legal mutation results without probabilities, order by
   lower then upper bound, and prefer refresh over an exactly `[0, 0]` apply tie.
8. Main, unknown operations and ambiguous/unsupported mutation enums fail closed.
9. Rule validation, focused tests, full offline tests and current-client snapshot smoke pass.
10. Project review finds no change to P1 evidence, scoring, recommendations or unrelated commands.

## Review and cleanup gate

After acceptance, search for stale duplicate Roll constants, guessed enum fallbacks, mutable state,
accidental probability assignment in the Rate-agnostic path and unused scaffolding. Remove only a
verified superseded path; retain fixtures and raw enum evidence. Then update this report to
`complete`, commit and push P2. A failed gate is reported and pushed truthfully instead.

## Implemented result

P2 adds two deliberately separate layers:

1. `rules.py` extracts and audits the client facts. Its normalized snapshot retains Gem/Stat,
   Trait Shape, Quality, Tablet slot and full operation records, including the eight zero-weight
   templates.
2. `fantasy/roll.py` builds a fail-closed immutable rule set and exposes pure Group state,
   legal-action, support, transition, model-conditional sampling and Rate-agnostic interval
   functions. It does not contain Stat valuation, Team matching or a Roll policy.

The executable value types are `EmblemState`, `BannerState`, `RollOffer`, `GroupRollState`,
`ApplyRollAction` and `RefreshRollAction`. State reserves `period` and `slot_count`, while every P2
entry point rejects Main. Applying and refreshing both require a complete legal replacement offer
and consume exactly one token. External realized outcomes are checked against full legal support;
internally sampled outcomes use the same rules but avoid a second redundant support enumeration.

Probability-free `enumerate_mutation_outcomes` is independent of
`mutation_distribution`/`sample_mutation`. Rate-agnostic intervals call a complete-Banner value
function, so P3 may perform whole-Team matching behind that interface. They use every legal result,
rank descending by lower bound and then upper bound, and place refresh before an apply action tied
at exactly `[0, 0]`.

## Source-backed correction

The preregistration draft stated that positive operation weights sum to `162`. Direct arithmetic
and both source copies show that this was a transcription error:

`9×10 + 4 + 8 + 3×(10+6+6) = 168`.

No individual client ID or weight changed. Canonical config, validators, tests and this report now
freeze `168`; preserving `162` would have made a truthful current-client snapshot block.

## Frozen evidence

- Current client snapshot: `20260806T081345Z-702ddf2a6953`.
- Explicit snapshot cutoff: `2026-08-06T08:15:00Z`; capture completed at
  `2026-08-06T08:13:45.887295Z`, before the cutoff.
- Steam build: `6888:10887746`.
- Snapshot SHA-256: `702ddf2a6953f383895efdfa3e45460c770e7c3c37e71d6a2b1d68e547a3235f`.
- Canonical rules SHA-256: `5c0236554e225eea8a494fb705fe08ec0dd3c9b67320602c4220ff7d356fd09d`.
- Client `fantasy_crafting.vdata` SHA-256:
  `23a2f198c0ddb1632ae3d2a95592ede2397e77bbc2bcd1b8a7a826244aaae76c`.
- Fixed focused fixture SHA-256:
  `8208a82d2f8a15f947ba69ffb076df622a19c10803895a230394ad1d4c141b4b`.
- Snapshot status: `warning`, with only the three pre-existing First Blood/percentile warnings and
  no Roll blocking issue.

The existing project vocabulary already covered every required concept, so the domain-model review
introduced no synonym and no hard-to-reverse ADR.

## Acceptance evidence

1. The real client and fixed fixture both parse to 28 unique operations: IDs `1–8` at zero weight
   and 20 offered IDs `9–17, 23–33` at total weight `168`.
2. Snapshot comparison covers all 18 color-legal Stats, five Trait Shape behaviors, five Quality
   bonuses/weights, all role slots/unlock levels, offer count and all operation fields.
3. Property tests exercise all `48` applicable `(positive operation, Group role)` pairs over
   generated valid Emblem states. Every outcome revalidates as a legal three-slot Banner.
4. The three preregistered models have exactly the same support for every tested pair; all
   conditional probabilities are positive and sum to one. Zero-weight IDs never enter an offer.
5. Fixed seeds reproduce 100 consecutive offers and sampled transitions in every model.
6. Tests prove three-option uniqueness, target-color filtering, `OneColor`/first/last target
   behavior, one-token consumption, selected-Banner isolation, full-offer replacement and
   zero-token rejection.
7. Main, unknown IDs, zero-weight offers, incomplete/duplicate offers, unknown mutations,
   ambiguous target flags, Quality drift and assumption drift all fail closed.
8. Rate-agnostic tests compare returned bounds with direct full-support extrema and verify refresh
   wins exact zero ties without creating a mean.
9. Current-client `ti rules validate` returns the expected `warning`; full offline verification is
   `87 passed, 1 optional integration skipped` in `5.78s`. Ruff reports all `49` Python files
   formatted and clean.
10. Existing Fantasy recommendation smoke run `fantasy-2b128cacb8413568` completes with the new
    snapshot/rule hashes and only its governed pre-existing warnings, confirming P1 scoring and
    recommendation entry points still run.

## Performance diagnostic

On the implementation host, CPython 3.12 with the current snapshot and a fixed seed measured:

- 100,000 weighted unique offer draws in best-of-three `1.029396s` (`10.29µs` each);
- 100,000 multi-slot red Stat mutation samples in best-of-three `0.914369s` (`9.14µs` each);
- 20,000 validated sampled apply transitions in best-of-three `0.591068s` (`29.55µs` each).

These are narrow P2 kernel diagnostics, not a promise for P4 search or P6 end-to-end runtime; Team
valuation, scenario arithmetic and policy branching are intentionally absent here.

## Project review

- No P1 native replay, scoring, recommendation, data synchronization or CLI behavior was changed.
- No second mutable Roll state or probability-bearing Rate-agnostic path remains.
- Client enums stay raw in the snapshot; unsupported combinations are rejected rather than mapped
  to a fallback.
- Source fixture and failure diagnostics are retained as reproducibility evidence. There was no
  superseded production Roll engine to delete, so verified-replacement cleanup was not applicable.
