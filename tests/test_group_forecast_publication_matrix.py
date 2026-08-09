from __future__ import annotations

from pathlib import Path

from ti_predictor.paths import PATHS

TEAM_LABELS = (
    "Yandex",
    "Liquid",
    "Falcons",
    "VISION",
    "Boom",
    "Resilience",
    "Spirit",
    "Aurora",
    "OG",
    "Vici",
    "HULIGANI",
    "LGD",
    "Nigma",
    "Xtreme",
    "GamerLegion",
    "Iron Wing",
)


def _publication_paths() -> tuple[Path, Path]:
    report = PATHS.root / "docs/reports/ti2026-group-forecast-publication-2026-08-09.md"
    bundle = (
        PATHS.root / "docs/publication/ti2026-release-bundle-2026-08-09/reports/"
        "ti2026-group-forecast-publication-2026-08-09.md"
    )
    return report, bundle


def _matrix(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.splitlines()
    header_index = next(index for index, line in enumerate(lines) if line.startswith("| 左侧队伍 / 对手 |"))
    header = [cell.strip() for cell in lines[header_index].strip("|").split("|")]
    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return header, rows


def test_group_forecast_uses_one_complete_matchup_matrix() -> None:
    report_path, _ = _publication_paths()
    text = report_path.read_text(encoding="utf-8")

    assert text.count("| 左侧队伍 / 对手 |") == 1
    assert "对阵 Liquid 至 Aurora" not in text
    assert "对阵 OG 至 Iron Wing" not in text

    header, rows = _matrix(text)
    assert header == ["左侧队伍 / 对手", *TEAM_LABELS]
    assert len(rows) == len(TEAM_LABELS)
    assert all(len(row) == len(TEAM_LABELS) + 1 for row in rows)

    for row_index, row in enumerate(rows):
        assert row[row_index + 1] == "—"
        for column_index in range(len(TEAM_LABELS)):
            if row_index == column_index:
                continue
            probability = int(row[column_index + 1].removesuffix("%"))
            reverse_probability = int(rows[column_index][row_index + 1].removesuffix("%"))
            assert probability + reverse_probability == 100


def test_release_bundle_has_the_same_complete_matchup_matrix() -> None:
    report_path, bundle_path = _publication_paths()
    report = report_path.read_text(encoding="utf-8")
    bundle = bundle_path.read_text(encoding="utf-8")

    assert _matrix(bundle) == _matrix(report)
