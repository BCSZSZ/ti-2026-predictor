# TI 2026 activity rules

Sources: Valve's 2026 announcement, the installed Dota client event definition and Fantasy crafting data. The normalized executable form is `config/rules/ti2026.json`.

## Predictions

- Group capacities: one 4-0, two 4-1, five Elimination winners, five Elimination losers, two 1-4 and one 0-4.
- Group correct-count points: `0, 30, 60, 120, 360, 720, 1200, 1800, 2520, 3360, 4320, 5400, 6600, 7920, 9360, 10920, 12000`.
- Main Event: eight-team double elimination with fourteen prediction nodes.
- Main correct-count points: `0, 120, 360, 720, 1200, 1800, 2520, 3360, 4320, 5400, 6600, 7920, 9360, 10920, 12000`.

## Fantasy

- Core averages the selected team's position 1 and 3 players; Support averages positions 4 and 5; Mid uses position 2.
- Per role, sum the two highest-scoring games in one series, then take the highest-scoring series in the period.
- Only stats present on the role's War Banner score.
- Group has three emblem slots. Main keeps those three and adds slots four and five.
- Prefix and suffix conditions apply to all selected players and do not consume reroll tokens.

## Known uncertainties

- The client internal name for late first blood says six minutes while localization says ten minutes.
- Multiple Fantasy percentile tables coexist in current client resources.
- Derived OpenDota counters for Madstone, lotus, watcher, smoke and Tormentor require differential validation.

Until validated, these are surfaced as warnings and excluded from a publishable claim that depends on them.
