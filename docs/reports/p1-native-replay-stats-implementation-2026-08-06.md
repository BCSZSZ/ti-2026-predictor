# P1 native replay Fantasy statistics implementation

Status: complete

Completed: 2026-08-06

## Baseline and scope

- Branch: `codex/group-roll-playbook-v1`
- Starting commit: `1b98040623ec7a6cc82864bbd63639c3055d2804`
- Remote divergence at start: `0 / 0`
- Starting gate: Ruff passed; `54` offline tests passed at the P0 baseline
- P1 boundary: native Fantasy evidence only; no Roll transition, valuation, playbook, solver or UI
  behavior was added

P1 replaces the formal OpenDota event-map approximations for Madstone, Smoke, Watcher, Lotus and
Tormentor with Valve's final per-player DataTeam counters. The old mappings remain only in a
separate diagnostic table and never fill a native `null`.

## Implemented path

The accepted minimum path is now present:

1. A pinned Java 21+ `Clarity 4.0.1` helper reads only final `CDOTA_DataRadiant` and
   `CDOTA_DataDire` entities. It emits ten stable player slots, five native values, explicit schema
   and observation flags, engine/build/game version, schema fingerprint and replay SHA-256.
2. Python owns the explicit UTC `as_of`, immutable Valve replay capture, match/URL identity checks,
   retry history, BZip2/Zstandard detection, temporary decompression, bounded subprocess and
   ten-player account join.
3. `ti data replay-fantasy` supports bounded workers, targeted match IDs, resumable batches,
   atomic checkpoints, progress output and intentional refresh.
4. Native, per-match status, Watcher cohort and diagnostic-proxy tables are separate. Only a
   current parser version and JAR hash with observed fields can overlay formal samples.
5. Watcher additionally requires a complete ten-player non-zero fixture in its
   `(build_number, game_version, schema_fingerprint)` cohort.
6. A changed JAR hash forces local re-parsing; a JAR change during one sync fails closed.

The five production rules now point to:

| Stat | Formal replay property |
| --- | --- |
| `madstone_collected` | `m_iNeutralTokensFound` |
| `smokes_used` | `m_iSmokesUsed` |
| `watchers_taken` | `m_iWatchersTaken` |
| `lotuses_gained` | `m_iLotusesTaken` |
| `tormentor_kills` | `m_iTormentorKills` |

## Frozen backfill result

The completed historical target is `as_of=2026-08-02T00:00:00Z`, UTC year 2026.

| Measure | Result |
| --- | ---: |
| Scoped Games | 2,055 |
| Scope membership rows | 12,486 |
| First / last scoped start | 2026-01-02 01:57:04Z / 2026-08-01 20:45:39Z |
| Status `exact` | 2,055 |
| Missing / failed / join-failed / build-untrusted / unattempted | 0 |
| Native rows | 20,550: exactly ten stable accounts and slots per Game |
| Formal sample rows covered in this scope | 20,550, all five fields `exact` |
| Diagnostic-proxy rows | 20,550 |
| Watcher cohorts | 113 admitted / 0 untrusted |
| Distinct replay builds / game versions / schema fingerprints | 9 / 113 / 113 |
| Compression | 2,006 BZip2 / 49 Zstandard |
| Compressed captures | 197,435,437,515 bytes (183.876 GiB) |
| Decompressed audit volume | 295,888,851,501 bytes (275.568 GiB), temporary only |
| Request attempts | 2,008 first-attempt / 46 second-attempt / 1 third-attempt successes |

The shared performance table also contains 1,440 historical player-Game rows outside these 2,055
target Games. Their five native fields correctly remain `null/unavailable`; they are outside the
frozen target, not hidden P1 failures.

## Integrity and determinism

- Scope match-ID SHA-256:
  `f16e5b070a2b2119e04e08270500b4059e29cad0c4012f8bef8d7c6bf7973b6c`
- Reproducible shaded JAR SHA-256:
  `fc109d605ab7d190b95fcb5fa7b5619db2495c1372dfc89640eb5dbc190e40b1`
  (`18,190,089` bytes; three consecutive normal builds were byte-identical)
- Native semantic SHA-256, excluding packaging-only metadata:
  `40982d8432ecafc981b503d9fe80daf854d92ba69c1029fa5a9f68a5b0e92848`
- Persisted five-table content SHA-256:
  `b7bf3b3e91daa7fe251c40f16ef50f26e09077f1417011cdf8972586c1883b77`

The final byte-level Parquet hashes are:

| File | SHA-256 |
| --- | --- |
| `fantasy_native_stats.parquet` | `de8ce4f17e1237b65bcd09c5e705c530b86bc898eb816282c4d9437ffe6ba5c6` |
| `fantasy_replay_status.parquet` | `20c6506fbf52eeb7a1bb46cdf0dce0321df920a73b421bc82c14c5f6d12d912a` |
| `fantasy_proxy_diagnostics.parquet` | `4828705fddf57055dd3902eb23cc18b23bf323e5b4c63e6a1cde25c1e1d26b0d` |
| `fantasy_watcher_support.parquet` | `6b4fb28839714bed84875c00214ab190d104f07fb6b26738f3b8a8f0975f6b1f` |
| `fantasy_performance_samples.parquet` | `9053a10544891284771e03352e871ec8eb51cfbc41204b2fffb77999d1d481f0` |
| `fantasy_player_history_scope.parquet` | `de58539d4d1d5ef5cc02f23c2616b2272f13b623faa9eb4e0e8eea44c19bdc71` |

Three consecutive no-op syncs reused all 2,055 Games, attempted no network or parser work, returned
the same content hash in `4.51` to `5.26` seconds, and left all six Parquet files byte-identical.

The final local reparse itself re-read and SHA-verified every compressed capture, decompressed and
hashed every replay, and required the parser's decompressed hash to match. A separate audit then
re-read all 2,055 current parser JSON captures (`9,235,906` JSON bytes), verified their immutable
metadata/content hashes and replay double hashes, and matched build/schema plus every one of the
20,550 × 5 values and presence flags to the native table. Errors: zero.

## Performance evidence

The six frozen real replay fixtures pass all 300 per-player values. Direct OpenJDK 25.0.2 process
measurement on the reference i5-13600KF, executing Java 21 bytecode, produced:

| Match | Wall seconds | Process CPU seconds | Parser internal seconds |
| --- | ---: | ---: | ---: |
| 8631262616 | 2.27 | 3.89 | 2.08 |
| 8680265600 | 1.44 | 2.64 | 1.31 |
| 8743439140 | 2.41 | 4.52 | 2.26 |
| 8813352696 | 1.87 | 3.73 | 1.72 |
| 8904419709 | 2.21 | 3.84 | 2.06 |
| 8924770688 | 2.54 | 4.88 | 2.39 |

Median wall time was `2.243` seconds, median CPU time `3.867` seconds and both maxima remained below
the accepted five-second bound.

Fresh external acquisition was deliberately recorded as separate bounded batches. The 2,049 Games
not already held as the six fixtures took approximately `5h44m` cumulative observed wall time:
two 100-Game probes (`7.78m` at four workers and `6.75m` at six), three 500-Game batches
(`81m41s` and `94m05s` at four; `98m46s` at six), and one 349-Game batch (`55m16s` at six).
Network long-tail behavior dominates, so these runs do not justify a claim that six workers are
always faster. Re-parsing the final 2,005 local captures took `55m40s`, reusing 50 immediately prior
deterministic checkpoints.

The plan's three-hour target and five-hour ceiling apply to one cached-snapshot P3-P6 analysis, not
this one-time 183.876-GiB acquisition. The fresh acquisition would miss a five-hour acquisition
ceiling by about 44 minutes; after capture, a complete local reparse is under one hour and a normal
verified no-op is under six seconds. Later analysis timers must start from this frozen cache.

## Verification and project review

- `uv lock --check`, `uv pip check`, Ruff and format checks pass.
- `76` tests collect; the default offline run has `75` passes and one explicit cached-replay
  integration skip.
- The skipped six-real-replay integration was enabled separately and passed against the final JAR.
- A clean `uv run --isolated --frozen --extra dev pytest -q` environment passed the same offline
  suite.
- The shaded class reports Java major version `65` (Java 21).
- Current client rule snapshot `20260806T073626Z-2e6c25f7c49e` matches the changed canonical rule
  hash. Validation has only the three pre-existing warnings: early First Blood semantics, late First
  Blood 6/10-minute conflict and competing percentile tables.
- Project recommendation smoke `fantasy-c35b7f13f5660e48` completed with expected pre-existing
  warnings. All five new native fields report `1.0` coverage and participate in formal profiles;
  they are not sensitivity-only.
- Repository-wide review found no remaining formal call to the old event-map helpers, no accidental
  live network test and no unrelated behavior change.

After acceptance, verified-replacement cleanup removed only the dead formal `_mapping_value`,
`_mapping_sum` and their unused `Iterable` import from `opendota.py`. The following were
intentionally retained:

- `extract_proxy_diagnostics`: active, separate differential evidence;
- `fantasy_proxy_diagnostics.parquet`: migration/audit output, never a formal fallback;
- the six golden replays and dated proxy reports: evidence and historical audit records;
- unavailable rows outside the frozen target: correct fail-closed coverage behavior.

## Remaining boundaries

There is no unresolved gap inside the frozen 2,055-Game target. Games after the explicit cutoff,
Games outside that scope, genuinely missing future replays and any future unadmitted Watcher cohort
remain `null/unavailable` until separately ingested and verified. The three client-rule warnings
above are unrelated to native replay counters and continue to block only their affected features.
