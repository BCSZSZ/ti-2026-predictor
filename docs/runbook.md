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

Madstone, Smoke, Watcher, Lotus and Tormentor require Java 21+ and a separate native-replay pass after
`fantasy-history`. Build the pinned parser once, then run the resumable backfill with the same
explicit cutoff:

```powershell
Push-Location src/ti_replay_parser
.\mvnw.cmd -q '-DskipTests' package
Pop-Location
uv run ti data replay-fantasy --as-of 2026-08-12T23:00:00Z --year 2026 --workers 4
```

The command defaults to one atomic Parquet checkpoint per completed match and refreshes DuckDB when
the command exits normally. `--max-matches` bounds a batch,
repeatable `--match-id` targets known fixtures, and `--refresh` intentionally creates a new immutable
capture instead of reusing the latest verified URL/hash. Do not run two replay backfills against the
same processed directory concurrently. After a fully accounted run, the status table records every
scoped match as `exact`, `missing`, `download_failed`, `decompress_failed`, `parse_failed`,
`join_failed` or `build_untrusted`; bounded batches additionally report the not-yet-attempted count.
Rerunning retries non-final failures and reuses complete rows only when both parser version and JAR
SHA-256 match. A JAR change during one sync fails closed; restart the command after an intentional
rebuild. OpenDota event-map values are diagnostic-only and never fill a native `null`.

Use `fantasy_replay_status.parquet` and `fantasy_watcher_support.parquet` as release gates before a
recommendation. The implementation order and acceptance contract are in the
[Group 40-Roll v2 implementation plan](plans/group-roll-playbook-v2-implementation.md); measured
coverage and performance are in the
[P1 implementation report](reports/p1-native-replay-stats-implementation-2026-08-06.md).

The Group Stat evidence and its optional team-ranking extension use the same cached snapshot and
explicit cutoff:

```powershell
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap
uv run ti fantasy group-evidence --as-of 2026-08-06T17:27:00Z --bootstrap --team-rank-bootstrap
```

The first command remains the compatibility default and preserves the frozen v2 schema and
semantic hash. The second adds 16 team rows to each of the 42 role/color/Stat groups and writes
`group-stat-team-top3-publication.md`. The publication table labels the internal `P1` and `P3`
fields as first-place and Top-3 stability rates; they remain deterministic Series-cluster bootstrap
frequencies, not calibrated future probabilities or confidence intervals. Names are display-only
and joins use stable team IDs. Each role/color table also ranks its six Stats from 1 through 6 and
renders the frozen Baseline Stat grade as a player-facing handling suggestion with its relative
strength; that suggestion is not an unconditional Roll action. See the promoted
[v2 Stat team Top 3 publication table](playbooks/group-roll/stat-team-top3-publication-v2.md) and its
[r4 publication report](reports/group-stat-team-top3-publication-r4-2026-08-08.md).

The frozen Group manual validation is a separate cached-snapshot command:

```powershell
uv run ti fantasy group-playbook-evidence --as-of 2026-08-06T17:27:00Z --playbook-version v2
```

It first reproduces the P3 source hash, then evaluates both independently frozen manuals over the
nine non-probability-weighted starting-state strata. It does not invoke the Reference Roll solver.
The current v2 result is `warning`: both editions remain `draft`. Primary has no standalone 10%
Common loss failure but does not pass every rule/risk gate; Rate has 23 such failures. Consult the
[manual index](playbooks/group-roll/README.md) and
[v2 standalone report](reports/group-roll-playbook-v2-p3-standalone-validation-2026-08-07.md)
before operational use. Omit `--playbook-version v2` only when intentionally reproducing v1.

The bounded P5 Reference Roll solver has its own historical v1 cached-snapshot evidence command:

```powershell
uv run ti fantasy group-solver-evidence --as-of 2026-08-06T08:15:00Z
```

It requires the immutable P4 artifact, rebuilds and verifies the P3/Rule context, then runs the
frozen one-hour effectiveness protocol. The v1 run completed all 18 fixed-offer short-horizon
diagnostics but only 7/216 full-session units; its status is
`failed-escalation-review-required`. Do not use it as a reliable or globally optimal recommendation,
and do not enable the dormant Full configuration planner from this failure. See the
[P5 report](reports/p5-branch-capped-solver-2026-08-06.md).
There is no new v2 full-session P5 run; v2 uses the historical failure only as explicitly labelled
diagnostic evidence.

The P6 read-only audit is a separate command and never rewrites either manual:

```powershell
uv run ti fantasy group-cross-audit --as-of 2026-08-06T17:27:00Z --cross-audit-version v2
```

It reconstructs standalone/P5 validation indexes, draws an audit Scenario subset explicitly
disjoint from both, and compares the frozen manual, bounded solver and conditional exact oracle.
The path-pinned v2 run completes 108/108 in about 45 minutes. Rate has no material exception in this
conditional matrix; Primary has one directionally wrong Common case. Both labels remain `draft`
because the audit can never promote a failed standalone candidate. See the
[v2 cross-audit report](reports/group-roll-playbook-v2-p4-read-only-cross-audit-2026-08-07.md).

The P7 local advisor has a separate reproducible evidence command:

```powershell
uv run ti fantasy group-advisor-evidence --as-of 2026-08-06T08:15:00Z
uv run ti web
```

Open `Group Roll 顾问（实验）`, keep `Group` selected, and manually enter the nine ordered
Emblems, exactly three shared operations and remaining Rolls. Creating a session verifies the
frozen P3–P6 identities. The page shows the selected draft manual first, then exact one-step
mutation/performance diagnostics under all three rate models and four epsilon values, followed by
the best Team match for each role. The one-step table deliberately excludes future-offer option
value and remaining-Roll reachability.

After acting in Dota, select the action actually used, confirm the realised Banner result and the
new three-operation offer, tick the manual-confirmation box, then record the event. A refresh must
leave all Banners unchanged. Downloaded session JSON stores the initial state and confirmed events;
loading it replays every transition and rejects baseline/hash drift. `Main` fails closed. The app
never controls or fills Dota and never learns rates from the current session.

The P5 button remains secondary and retains
`failed-escalation-review-required`. It is available only when exactly one Roll remains: the formal
last-Roll run took 8.60 seconds, while prior long-horizon P5 sessions had a roughly 749-second
median and are blocked from the responsive UI. See the
[P7 report](reports/p7-local-interactive-group-roll-advisor-2026-08-06.md).
This experimental advisor remains frozen to v1 identities. Use the v2 Markdown manuals directly;
do not assume the page silently applies v2 rules.

The OpenDota `data sync` and `data fantasy-history` commands stop before exceeding their per-run
`--request-limit` (default 5,000), and keyed
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
