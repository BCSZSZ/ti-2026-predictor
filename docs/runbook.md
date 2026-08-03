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

For paid OpenDota access, copy `.env.example` to the Git-ignored `.env`, place the key only in
`OPENDOTA_API_KEY`, and run commands with `uv run --env-file .env ...`. Do not put the key on the
command line. The local paid-request ceiling is 50,000 keyed attempts per UTC month ($5 at the
currently verified price) and cannot be raised through environment configuration. Full details are
in [OpenDota API usage and safety](opendota-api-usage.md).

## Refresh and generate

```powershell
uv run --env-file .env ti data sync --as-of 2026-08-12T23:00:00Z --year 2026 --request-limit 500
uv run ti forecast backtest --as-of 2026-08-12T23:00:00Z
uv run ti forecast group --as-of 2026-08-12T23:00:00Z --profile all
uv run ti fantasy recommend --as-of 2026-08-12T23:00:00Z --period group --profile all
uv run ti audit <run_id>
uv run ti web
```

Run the TI 2025 holdout before the 2026 group Forecast. Continue to the group command only when the
backtest has no blocking issue; the default holdout league and all weighting constants come from
the versioned team-strength policy selected by `config/ti2026.yaml`. Policy replacement and
post-holdout changes follow [model policy governance](model-governance.md).

The strength model derives the target-team evidence network from the complete time-bounded
`/proMatches` catalog after patch/tier weighting. It does not discover that network by recursively
calling every opponent's team-history endpoint. Each run records the selected match-ID hash and
observed network size; no exact catalog count is a release gate.

The default sync walks OpenDota `/proMatches` backwards until it covers the requested UTC calendar
year, then joins `/leagues` and `/constants/patch`. `--no-pro-catalog` skips this year catalog when
only a targeted league refresh is needed. `/proMatches` summaries are complete for the requested
time window as exposed by OpenDota; replay-level player details remain a separately bounded set.
Without `OPENDOTA_API_KEY`, the client respects the anonymous minute window and pauses between
pagination batches; a full-year first sync therefore takes several minutes.

Both data commands stop before exceeding their per-run `--request-limit` (default 5,000), and keyed
attempts are reserved in `data/cache/opendota_api_usage.json` before the network call. A repeated
successful path/query in one process stops immediately. Transient network/5xx responses receive at
most four total attempts with 1/2/4-second backoff; `429` honors `Retry-After`.

`--max-matches 5` limits detailed match downloads for a smoke test while still collecting
current-team summary history. Use `--no-team-history` only for isolated tests. Detailed matches
resume by `match_id`; use `--refresh-details` only when intentionally replacing the normalized copy
with a newly captured OpenDota response.

## Main Event

After Valve publishes the bracket, place the eight team IDs in seeding order under
`main_event_seeds` in `config/ti2026.yaml`, or pass them once with `--teams`.
Without real seeds, bracket output is deliberately `blocked`.

## Exit meanings

- `publishable`: no blocking audit issue.
- `warning`: usable only after reading the listed caveats.
- `blocked`: must not be copied into the game.

The app never logs into Steam and never writes a game selection.
