# Main Roll strategy research runbook

This path is intentionally separate from the current Web advisor. It reads the same frozen
Main release but never writes `deploy/runtime/`, never controls Dota, and never promotes a
research strategy into the Web application.

## Frozen input state

Save the confirmed OCR/manual Main state as JSON with all three five-slot Banners, the shared
three-operation offer, and the observed remaining Roll count:

```json
{
  "period": "main",
  "slot_count": 5,
  "remaining_rolls": 30,
  "banners": [
    {
      "role": "core",
      "emblems": [
        {"stat_id": "kills", "quality_tier": 3, "trait_id": "fractal"}
      ]
    }
  ],
  "offer": {"operation_ids": [23, 14, 31]}
}
```

The example shows the schema only: each of `core`, `mid`, and `support` must contain all five
client-valid Emblems in canonical role order. Tuning and confirmation accept only the state path,
file SHA-256, semantic state SHA-256, image SHA-256 and OCR observation SHA-256 frozen by the
research manifest. A smoke run may use another confirmed state but remains release-ineligible.

## Safe smoke run

```powershell
uv run python -m ti_predictor.fantasy.main_roll_research_experiment `
  --state config/research/states/ti2026-main-reference-screen-20260814.json `
  --mode smoke `
  --smoke-count 2 `
  --models client-weight-primary-v1 `
  --smoke-roll-limit 2 `
  --workers 1
```

Smoke results are always marked release-ineligible. Output is written below
`artifacts/research/main-roll-simulator/`; individual episode traces retain the complete
before/action/after states and deterministic draw keys.

## Projected roster-conditional experiments

Schema v2 derives all 256 eight-Team outer rosters from the frozen Group Scenario rows without
deduplicating or reweighting them. A deterministic salt assigns eight balanced folds. For every
outer roster, Team matching uses independent inner Main selection paths, and settlement uses a
different inner evaluation phase. This estimates roster-conditional `E max` without selecting a
Team after seeing its realized evaluation score.

The current manifest uses fold 0 for tuning and folds 1–7 for confirmation. Each outer roster has
four inner paths per phase. These are projected-derived Forecast rosters, never actual rosters.

## Frozen experiments

Use `--mode tuning` only for policy-parameter research. The first declared tuning seeds are the
parameter-search segment and the remaining seeds are an independent candidate-validation segment.
Only challengers passing that screen proceed to confirmation.

```powershell
uv run python -m ti_predictor.fantasy.main_roll_research_experiment `
  --state config/research/states/ti2026-main-reference-screen-20260814.json `
  --mode tuning `
  --models client-weight-primary-v1 `
  --workers 4
```

After parameters and the manifest are frozen, run confirmation. Confirmation refuses partial
probability-model families, uses the held-out Roll seeds and roster folds, and evaluates every
frozen gate. `--workers` changes only execution scheduling: each model/seed task runs an entire
G/T/H batch and the parent merges batches in deterministic order. One- and multi-worker smoke
episode files must be byte-identical before a parallel confirmation is trusted.

```powershell
uv run python -m ti_predictor.fantasy.main_roll_research_experiment `
  --state config/research/states/ti2026-main-reference-screen-20260814.json `
  --mode confirmation `
  --workers 4
```

Passing a research gate still performs no Web promotion. A failed gate selects the frozen greedy
safety baseline; if the current Web already implements that one-step family, no production change
is required.

Projected and actual Main releases require separate manifests and separate reports. When the
actual eight-Team release replaces the projected release, create a new manifest version with the
new `as_of` and source hashes rather than editing an old experiment result.

The manifest records the current client Rule snapshot, the canonical Rule file hash, the Main
release's canonical JSON hash, and the effective Roll-rule hash separately. This prevents a newer
client evidence snapshot from being mistaken for a rebuilt Main release.

## Artifact integrity

Every run writes `manifest.json`, `report.json`, an optional projected roster panel, one complete
JSON trace per episode, and `checksums.json` below
`artifacts/research/main-roll-simulator/<run-id>/`. Verify every listed SHA-256 before interpreting
the report. The report must show the expected seed range, model family, roster folds, starting-state
hash, release hash and `automatic_web_promotion=false`.

The projected 16-Team selection completed on 2026-08-15 is documented in
`docs/research/ti2026-main-roll-projected16-strategy-selection-2026-08-15.md`.

## Synthetic starting-state coverage

The separate coverage contract creates 1,000 deterministic, client-legal synthetic Main states.
It is a non-probability-weighted stress test, not an initial-state population model.  Indices 0--99
are pipeline-only; indices 100--999 are held-out confirmation.  A fixed hash selects 100 of those
confirmation states for the complete five-model sensitivity panel.

Prepare and validate the immutable index before scoring:

```powershell
uv run python -m ti_predictor.fantasy.main_roll_research_coverage --stage prepare
```

Run development, Primary confirmation, the four additional sensitivity models, and finalization in
order.  Do not modify `src/` or `config/` after opening confirmation:

```powershell
uv run python -m ti_predictor.fantasy.main_roll_research_coverage `
  --stage development-primary --workers 8

uv run python -m ti_predictor.fantasy.main_roll_research_coverage `
  --stage confirmation-primary --workers 10

uv run python -m ti_predictor.fantasy.main_roll_research_coverage `
  --stage confirmation-sensitivity --workers 10

uv run python -m ti_predictor.fantasy.main_roll_research_coverage --stage finalize
```

Each task is committed independently and may be resumed only when its result and all three episode
file hashes match.  Finalization refuses incomplete stages or different confirmation source
versions and writes a whole-bundle checksum manifest.  The 2026-08-15 result retained G and is
documented in
`docs/research/ti2026-main-roll-1000-starting-state-coverage-2026-08-15.md`.
