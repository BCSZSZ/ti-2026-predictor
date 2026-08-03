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

As of policy `2026-08-02-owner-policy-v1`, the project does not use OpenDota's precomputed
`teamfight_participation` field. It derives the ratio from player kills and assists plus the
Radiant/Dire team kill total. A team with zero kills has an undefined denominator and remains
`null`; other missing inputs also remain `null`.

Rows created under the earlier `exact` mapping are stale under this policy. Recommendation code
requires each normalized value's provenance to match the current rule, so those rows fail closed
until they are normalized again from the retained raw match details.
