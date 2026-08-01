# Local runbook

All cutoffs are ISO-8601 timestamps with an explicit timezone. The group lock is
`2026-08-13T02:00:00Z`; use an earlier cutoff for the final run.

## First setup

```powershell
uv sync --extra dev
uv run ti rules snapshot --as-of 2026-08-12T23:00:00Z
uv run ti rules validate
```

The rules snapshot locates Dota and the pinned ValveResourceFormat CLI via
`DOTA_PATH` and `VRF_CLI` when the default Windows locations do not apply.

## Refresh and generate

```powershell
uv run ti data sync --as-of 2026-08-12T23:00:00Z
uv run ti forecast group --as-of 2026-08-12T23:00:00Z --profile all
uv run ti fantasy recommend --as-of 2026-08-12T23:00:00Z --period group --profile all
uv run ti forecast backtest --as-of 2026-08-12T23:00:00Z --league-id 18324
uv run ti audit <run_id>
uv run ti web
```

`--max-matches 5` limits detailed match downloads for a smoke test while still
collecting current-team summary history. Use `--no-team-history` only for isolated tests.
Detailed matches resume by `match_id`; use `--refresh-details` only when intentionally replacing
the normalized copy with a newly captured OpenDota response.

## Main Event

After Valve publishes the bracket, place the eight team IDs in seeding order under
`main_event_seeds` in `config/ti2026.yaml`, or pass them once with `--teams`.
Without real seeds, bracket output is deliberately `blocked`.

## Exit meanings

- `publishable`: no blocking audit issue.
- `warning`: usable only after reading the listed caveats.
- `blocked`: must not be copied into the game.

The app never logs into Steam and never writes a game selection.
