# Data contracts

## Raw captures

Each HTTP or client-rule capture is immutable and records:

- source name and URL/path;
- request parameters;
- `fetched_at` in UTC;
- payload SHA-256;
- HTTP status or client build;
- a canonical JSON serialization of JSON responses, or the original compressed bytes for a replay.

Valve replay captures additionally record the replay URL, match ID, salt/cluster when available,
HTTP status, retry history, compressed byte count and SHA-256. Decompressed replay files are
temporary; their byte count and SHA-256 are retained in the replay status/native-stat tables.

## Normalized records

- The professional match catalog is the requested UTC-year slice of OpenDota `/proMatches`. It is
  paginated with `less_than_match_id` and does not include `/publicMatches` rows.
- Match identity: `match_id`, `league_id`, `series_id`, `start_time`, Radiant/Dire stable team IDs and winner.
- Match filters: `patch`/`patch_name` from the OpenDota patch timeline and `league_tier` from
  OpenDota league metadata. Tier values are preserved rather than re-labelled as Tier 1/2/3.
- Player identity: `account_id`, stable team ID, display name and temporally valid Fantasy role.
- Every normalized row carries the raw response `source_sha256`, `fetched_at` where applicable,
  and the run cutoff `as_of`.
- Unknown numeric data is `null`, never zero-filled.
- Fantasy fields additionally carry one of `exact`, `derived`, `proxy`, `unavailable`.

`matches.parquet` is the match catalog and modeling history. `fantasy_performance_samples.parquet`
contains player-Game observations extracted only from downloaded match details; its row count is
not a player count or a Fantasy prediction count.

Native Fantasy replay ingestion adds four keyed tables:

- `fantasy_native_stats.parquet`: ten player-slot rows per parsed Game, including field-presence and
  parser/replay audit columns;
- `fantasy_replay_status.parquet`: exactly one latest status row per attempted scoped `match_id`;
- `fantasy_proxy_diagnostics.parquet`: legacy OpenDota event-map comparisons only;
- `fantasy_watcher_support.parquet`: the build/game/schema admission boundary for Watcher values.

Only presence-verified native rows are overlaid into `fantasy_performance_samples.parquet`. A
diagnostic proxy never fills a native `null`.

Team-history summaries are retained for strength modeling. The canonical Fantasy player history
scope is selected by stable `account_id`: collect the reviewed TI players' UTC-year match IDs,
intersect them with the professional match catalog, retain OpenDota league tier `premium` or
`professional`, and deduplicate by `match_id`. This includes a current player's Games for former
teams and excludes Pub matches. Player-history responses and match details are immutable raw
captures. Detail synchronization checkpoints normalized rows and resumes from existing raw
captures without requesting an already parsed Game again.

An HTTP 200 OpenDota detail response is not proof of OpenDota event-log parsing. A complete
event-map diagnostic sample requires
`od_data.has_parsed == true`, a non-null parser `version`, and ten player slots. Base-only responses
remain available for basic statistics and are retried by a later overlapping incremental update.
This OpenDota parser state is independent of the native Valve replay status above.

Primary endpoint definitions: [OpenDota API implementation](https://github.com/odota/core/blob/master/svc/api/spec.ts),
[league tier schema](https://github.com/odota/core/blob/master/svc/api/responses/LeagueObjectResponse.ts),
and [patch timeline](https://github.com/odota/dotaconstants/blob/master/build/patch.json).

## Run artifacts

Every forecast run writes `run.json`, `recommendations.json`, `model.json` and `details.json`;
`ti audit` adds `audit.json`. The run manifest includes `as_of`, source/Git revision, exact client
rule snapshot ID and hash, canonical rule hash, data/config hashes, model parameters and seed.
