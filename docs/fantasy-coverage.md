# Fantasy field coverage contract

| Field | Formal normalized source | Provenance when observed | Default use |
| --- | --- | --- | --- |
| kills | `kills` | exact | yes |
| deaths | `deaths` | exact | yes |
| creep_score | `last_hits + denies` | derived | yes |
| gpm | `gold_per_min` | exact | yes |
| madstone_collected | replay `m_iNeutralTokensFound` | exact | yes, subject to coverage |
| tower_kills | `towers_killed` | exact | yes |
| wards_placed | `obs_placed` | exact | yes |
| camps_stacked | `camps_stacked` | exact | yes |
| runes_grabbed | `rune_pickups` | exact | yes |
| smokes_used | replay `m_iSmokesUsed` | exact | yes, subject to coverage |
| watchers_taken | replay `m_iWatchersTaken` | exact on admitted build/schema cohorts | yes, subject to coverage |
| lotuses_gained | replay `m_iLotusesTaken` | exact | yes, subject to coverage |
| roshan_kills | `roshans_killed` | exact | yes |
| teamfight_participation | `(kills + assists) / team_total_kills` | derived | yes |
| first_blood | `firstblood_claimed` | exact | yes |
| stuns | `stuns` | exact | yes |
| tormentor_kills | replay `m_iTormentorKills` | exact | yes, subject to coverage |
| courier_kills | `courier_kills` | exact | yes |

Presence is not semantic validation. For the five native fields, a value is `exact` only when the
replay hash matches, the final DataTeam entity and property were actually observed, and the stable
player-slot join succeeds. An observed native zero is exact; a missing/truncated replay, absent
entity/property, failed join or parse remains `null/unavailable`. Watcher additionally requires an
admitted `(build_number, game_version, schema_fingerprint)` cohort with a complete ten-player
non-zero fixture, so known old all-zero builds cannot masquerade as exact zero.

The legacy OpenDota maps remain only in `fantasy_proxy_diagnostics.parquet`:

| Field | Diagnostic proxy | Formal fallback |
| --- | --- | --- |
| madstone_collected | `item_uses.madstone_bundle` | forbidden |
| smokes_used | `item_uses.smoke_of_deceit` | forbidden |
| watchers_taken | `ability_uses.ability_lamp_use` | forbidden |
| lotuses_gained | `item_uses` lotus-family keys | forbidden |
| tormentor_kills | `killed.npc_dota_miniboss` | forbidden |

They never fill an exact `null`, even when non-null or zero. The full P1 coverage snapshot and any
unresolved historical gaps are recorded in
[`docs/reports/p1-native-replay-stats-implementation-2026-08-06.md`](reports/p1-native-replay-stats-implementation-2026-08-06.md).

Evidence, semantic differences, and six replay comparisons are recorded in
[`docs/research/ti2026-fantasy-proxy-stat-validation.md`](research/ti2026-fantasy-proxy-stat-validation.md).

The project does not use OpenDota's precomputed
`teamfight_participation` field. It derives the ratio from player kills and assists plus the
Radiant/Dire team kill total. A team with zero kills has an undefined denominator and remains
`null`; other missing inputs also remain `null`.

Recommendation code requires every normalized value's provenance to match the current rule. Older
proxy rows therefore fail closed; replay-backed rows are overlaid only after the native gates above.
