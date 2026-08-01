# Data contracts

## Raw captures

Each HTTP or client-rule capture is immutable and contains:

- source name and URL/path;
- request parameters;
- `fetched_at` in UTC;
- payload SHA-256;
- HTTP status or client build;
- a canonical JSON serialization of the response payload.

## Normalized records

- Match identity: `match_id`, `league_id`, `series_id`, `start_time`, Radiant/Dire stable team IDs and winner.
- Player identity: `account_id`, stable team ID, display name and temporally valid Fantasy role.
- Every normalized row carries the raw response `source_sha256`, `fetched_at` where applicable,
  and the run cutoff `as_of`.
- Unknown numeric data is `null`, never zero-filled.
- Fantasy fields additionally carry one of `exact`, `derived`, `proxy`, `unavailable`.

Team-history summaries are retained for strength modeling. For Fantasy, the synchronizer also
fetches a bounded recent detail window for every team in the reviewed TI manifest (20 matches per
team by default). Detail responses are deduplicated by `match_id` and resumed from the existing
Parquet observation set; historical holdout anchors never make unrelated old team matches detail
eligible.

## Run artifacts

Every forecast run writes `run.json`, `recommendations.json`, `model.json` and `details.json`;
`ti audit` adds `audit.json`. The run manifest includes `as_of`, source/Git revision, exact client
rule snapshot ID and hash, canonical rule hash, data/config hashes, model parameters and seed.
