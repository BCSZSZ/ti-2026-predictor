# Fantasy field coverage contract

| Field | OpenDota mapping | Provenance | Default use |
| --- | --- | --- | --- |
| kills | `kills` | exact | yes |
| deaths | `deaths` | exact | yes |
| creep_score | `last_hits + denies` | derived | yes |
| gpm | `gold_per_min` | exact | yes |
| madstone_collected | `item_uses.madstone_bundle` | proxy | no |
| tower_kills | `towers_killed` | exact | yes |
| wards_placed | `obs_placed` | exact | yes |
| camps_stacked | `camps_stacked` | exact | yes |
| runes_grabbed | `rune_pickups` | exact | yes |
| smokes_used | `item_uses.smoke_of_deceit` | proxy | no |
| watchers_taken | `ability_uses.ability_lamp_use` | proxy | no |
| lotuses_gained | `item_uses` lotus-family keys | proxy | no |
| roshan_kills | `roshans_killed` | exact | yes |
| teamfight_participation | `(kills + assists) / team_total_kills` | derived | yes |
| first_blood | `firstblood_claimed` | exact | yes |
| stuns | `stuns` | exact | yes |
| tormentor_kills | `killed.npc_dota_miniboss` | proxy | no |
| courier_kills | `courier_kills` | exact | yes |

Presence is not semantic validation. Proxy fields remain excluded even when OpenDota returns a
non-null value; differential validation against a second source is still required.

## Resolved replay sources not yet wired into normalization

The five proxy rows above are limitations of the current OpenDota-map adapter, not limitations of
the replay. Current Dota client schema and replay differential tests identify dedicated per-player
`DataTeamPlayer_t` counters for all five fields:

| Field | Exact replay property | Provenance after ingestion | Proxy fallback |
| --- | --- | --- | --- |
| madstone_collected | `m_iNeutralTokensFound` | exact | forbidden |
| smokes_used | `m_iSmokesUsed` | exact | forbidden |
| watchers_taken | `m_iWatchersTaken` | exact on validated builds | forbidden |
| lotuses_gained | `m_iLotusesTaken` | exact | forbidden |
| tormentor_kills | `m_iTormentorKills` | exact | forbidden |

This is a resolved source contract, not a claim that existing normalized rows are already exact.
Until replay ingestion and re-normalization land, the top table remains the production contract and
these five fields stay excluded. Once landed, a successfully observed native zero is exact; a
missing/truncated replay, absent final entity or field, invalid player/team-slot join, or an
unvalidated client build remains `null`. In particular, known old Watcher-zero replay builds must
not be treated as exact zero. The OpenDota maps may remain as diagnostic proxy columns, but must
never fill an exact `null`.

Evidence, semantic differences, and six replay comparisons are recorded in
[`docs/research/ti2026-fantasy-proxy-stat-validation.md`](research/ti2026-fantasy-proxy-stat-validation.md).

As of policy `2026-08-02-owner-policy-v1`, the project does not use OpenDota's precomputed
`teamfight_participation` field. It derives the ratio from player kills and assists plus the
Radiant/Dire team kill total. A team with zero kills has an undefined denominator and remains
`null`; other missing inputs also remain `null`.

Rows created under the earlier `exact` mapping are stale under this policy. Recommendation code
requires each normalized value's provenance to match the current rule, so those rows fail closed
until they are normalized again from the retained raw match details.
