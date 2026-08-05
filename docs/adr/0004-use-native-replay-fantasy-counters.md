---
status: accepted
---

# Use native replay counters for five special Fantasy stats

Madstone, Smoke, Watcher, Lotus and Tormentor will use Valve's per-player DataTeam replay counters,
not OpenDota `item_uses`, `ability_uses` or `killed` maps. Client semantics, network schema and six
2026 replay comparisons show that the maps count adjacent events and can disagree with Fantasy
credit; they remain diagnostic proxies only.

This decision requires a versioned replay backfill before existing rows, solver inputs or Human Roll
playbooks may call these fields `exact`. A native zero is exact only when field presence is observed
on a validated build; missing replays, absent fields and untrusted Watcher-zero builds remain `null`,
with no proxy fallback. The field mapping and evidence are recorded in
[`ti2026-fantasy-proxy-stat-validation.md`](../research/ti2026-fantasy-proxy-stat-validation.md).
