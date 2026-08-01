# Leakage policy

- A match is eligible only when its start time is strictly earlier than the run `as_of`.
- A roster mapping is eligible only inside its effective interval.
- A rule snapshot or public announcement captured after `as_of` cannot be retroactively used in a backtest.
- Post-match replay-derived statistics may train later forecasts only after the capture time recorded for them.
- Time-series evaluation uses expanding or rolling windows; random train/test splits are forbidden.
- Tests must fail when any feature row, label, roster or rule timestamp exceeds `as_of`.
