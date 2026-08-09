---
status: accepted
---

# Use 1.5× current exact-patch evidence

ADR-0005 established one shared Current exact gameplay patch factor, but its `2.0` multiplier made
the 141 identified `7.41e` Games disproportionately sensitive to short schedules: Team Liquid's
strong window moved it from fifth to first while Team Yandex had no eligible `7.41e` Game. Keep the
shared factor and reviewed UTC boundary, but reduce the multiplier to `1.5` so current-version
evidence remains preferred without counting it as strongly as two otherwise identical Games.

Major gameplay patch, League tier and age weights are unchanged. Historical artifacts produced
under ADR-0005 remain valid snapshots but are not current. Team-strength Forecasts, Fantasy Stat
evidence, Coach Title evidence and future Playbook/Solver runs must inherit `1.5` from the same
central evidence policy; no consumer may maintain a separate exact-patch multiplier.
