from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

from ti_predictor.paths import PATHS

PATCHES = ("7.41（无字母）", "7.41a", "7.41b", "7.41c", "7.41d", "7.41e")
EXPECTED_LEADERS = {
    "7.41（无字母）": "Team Yandex",
    "7.41a": "GamerLegion",
    "7.41b": "BoomBoys",
    "7.41c": "TEAM VISION",
    "7.41d": "Team Resilience",
    "7.41e": "Team Liquid",
}
ROW_PATTERN = re.compile(
    r"\| (?P<rank>\d+) \| (?P<team>[^|]+?) \| (?P<series>\d+) \| "
    r"(?P<wins>\d+)–(?P<draws>\d+)–(?P<losses>\d+) \| "
    r"(?P<score_rate>\d+\.\d)% \| (?P<map_wins>\d+)–(?P<map_losses>\d+) \|"
)


@dataclass(frozen=True)
class PatchRow:
    rank: int
    team: str
    series: int
    wins: int
    draws: int
    losses: int
    score_rate: Decimal
    map_wins: int
    map_losses: int

    @property
    def series_score_rate(self) -> Fraction:
        return Fraction(2 * self.wins + self.draws, 2 * self.series)

    @property
    def map_win_rate(self) -> Fraction:
        return Fraction(self.map_wins, self.map_wins + self.map_losses)


def _patch_rows(text: str, patch: str) -> list[PatchRow]:
    section = text.split(f"### {patch}", maxsplit=1)[1]
    section = re.split(r"\n#{2,3} ", section, maxsplit=1)[0]
    rows = []
    for match in ROW_PATTERN.finditer(section):
        values = match.groupdict()
        rows.append(
            PatchRow(
                rank=int(values["rank"]),
                team=values["team"],
                series=int(values["series"]),
                wins=int(values["wins"]),
                draws=int(values["draws"]),
                losses=int(values["losses"]),
                score_rate=Decimal(values["score_rate"]),
                map_wins=int(values["map_wins"]),
                map_losses=int(values["map_losses"]),
            )
        )
    return rows


def _publication_paths() -> tuple[Path, Path]:
    report = PATHS.root / "docs/reports/ti2026-group-current-patch-series-evidence-2026-08-08.md"
    bundle = (
        PATHS.root / "docs/publication/ti2026-release-bundle-2026-08-08/reports/"
        "ti2026-group-current-patch-series-evidence-2026-08-08.md"
    )
    return report, bundle


def test_exact_patch_tables_are_ranked_by_patch_results() -> None:
    report_path, _ = _publication_paths()
    text = report_path.read_text(encoding="utf-8")

    assert "该版本内部独立排名" in text
    assert "（系列胜 + 0.5 × 系列平）÷ 完整系列" in text
    for patch in PATCHES:
        rows = _patch_rows(text, patch)
        assert rows
        assert [row.rank for row in rows] == list(range(1, len(rows) + 1))
        assert rows[0].team == EXPECTED_LEADERS[patch]
        assert all(row.wins + row.draws + row.losses == row.series for row in rows)

        expected_order = sorted(
            rows,
            key=lambda row: (
                -row.series_score_rate,
                -row.map_win_rate,
                -row.series,
                row.team.casefold(),
            ),
        )
        assert rows == expected_order
        for row in rows:
            expected_percentage = (
                Decimal(row.series_score_rate.numerator)
                / Decimal(row.series_score_rate.denominator)
                * Decimal("100")
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            assert row.score_rate == expected_percentage


def test_release_bundle_has_the_same_exact_patch_rankings() -> None:
    report_path, bundle_path = _publication_paths()
    report = report_path.read_text(encoding="utf-8")
    bundle = bundle_path.read_text(encoding="utf-8")

    for patch in PATCHES:
        assert _patch_rows(bundle, patch) == _patch_rows(report, patch)
