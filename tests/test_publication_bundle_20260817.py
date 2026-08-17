from __future__ import annotations

import hashlib
import re
from zipfile import ZipFile

from ti_predictor.paths import PATHS

BUNDLE = PATHS.root / "docs/publication/ti2026-release-bundle-2026-08-17"
ARCHIVE = PATHS.root / "docs/publication/ti2026-release-bundle-2026-08-17.zip"
REQUIRED_FILES = {
    "MANIFEST.sha256",
    "README.md",
    "WEIGHTING.md",
    "assets/ti2026-main-event-double-elimination-bracket-2026-08-17.png",
    "assets/ti2026-main-event-double-elimination-bracket-2026-08-17.svg",
    "playbooks/main-roll-publication-manual-v1.md",
    "playbooks/main-stat-team-top3-publication-v1.md",
    "reports/ti2026-main-event-publication-2026-08-17.md",
    "reports/ti2026-main-fantasy-title-recommendation-2026-08-17.md",
    "reports/ti2026-main-probability-reference-2026-08-17.md",
}


def _bundle_files() -> set[str]:
    return {path.relative_to(BUNDLE).as_posix() for path in BUNDLE.rglob("*") if path.is_file()}


def test_main_release_bundle_is_complete_and_linked_from_root() -> None:
    assert _bundle_files() == REQUIRED_FILES

    root_readme = (PATHS.root / "README.md").read_text(encoding="utf-8")
    assert "docs/publication/ti2026-release-bundle-2026-08-17/README.md" in root_readme
    assert "docs/reports/ti2026-main-probability-reference-2026-08-17.md" in root_readme

    player_hub = (PATHS.root / "docs/playbooks/main-roll/README.md").read_text(encoding="utf-8")
    assert "ti2026-main-probability-reference-2026-08-17.md" in player_hub
    assert "这四份资料" in player_hub

    release_readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
    assert "3.7500 / 14" in release_readme
    assert "1367.525" in release_readme
    assert "5.4122 / 14" in release_readme
    assert "80.20%" in release_readme
    assert "Otherworldly + the Underdog" in release_readme
    assert "当前三队动态重算" in release_readme

    title_report = (BUNDLE / "reports/ti2026-main-fantasy-title-recommendation-2026-08-17.md").read_text(
        encoding="utf-8"
    )
    assert "公开 Streamlit 手填版和本地 OCR 版" in title_report
    assert "Otherworldly + the Underdog" in title_report
    assert "+4.28%" in title_report


def test_main_probability_reference_contains_full_explanatory_contract() -> None:
    report = (BUNDLE / "reports/ti2026-main-probability-reference-2026-08-17.md").read_text(encoding="utf-8")

    assert "Elo/Glicko 50/50" in report
    assert "TEAM VISION** | — | **61.32%**" in report
    assert "**3.7500 / 14**" in report
    assert "**5.4122 / 14**" in report
    assert "**1367.525**" in report
    assert "**2464.237**" in report
    assert "17.7257%" in report
    assert "14.3741%" in report
    assert "10.9236%" in report
    assert "7.3762%" in report
    assert "21.2766%" in report
    assert "42.5532%" in report
    assert "16.6667%" in report
    assert "不能证明这四天内客户端或 GC 没有漂移" in report
    assert "初始 15 格与首次 offer 的联合分布" in report

    positive_operation_ids = (*range(9, 18), *range(23, 34))
    for operation_id in positive_operation_ids:
        assert re.search(rf"^\| {operation_id} \|", report, flags=re.MULTILINE)


def test_main_release_uses_valve_crossed_lower_round_two_topology() -> None:
    report = (BUNDLE / "reports/ti2026-main-event-publication-2026-08-17.md").read_text(encoding="utf-8")
    svg = (BUNDLE / "assets/ti2026-main-event-double-elimination-bracket-2026-08-17.svg").read_text(
        encoding="utf-8"
    )

    assert "Nigma Galaxy vs BoomBoys" in report
    assert "Iron Wing vs Team Yandex" in report
    assert 'data-node="lower_r2_a" data-left-team-id="10136357" data-right-team-id="8255888"' in svg
    assert 'data-node="lower_r2_b" data-left-team-id="10150413" data-right-team-id="9823272"' in svg


def test_main_release_bundle_local_markdown_links_resolve() -> None:
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for document in BUNDLE.rglob("*.md"):
        text = document.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            target = target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", maxsplit=1)[0]
            if path_part:
                assert (document.parent / path_part).resolve().exists(), (document, target)


def test_main_release_manifest_matches_every_payload_file() -> None:
    lines = (BUNDLE / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    entries = {
        relative_path: expected_hash
        for expected_hash, relative_path in (line.split("  ", maxsplit=1) for line in lines if line)
    }
    assert set(entries) == REQUIRED_FILES - {"MANIFEST.sha256"}

    for relative_path, expected_hash in entries.items():
        actual_hash = hashlib.sha256((BUNDLE / relative_path).read_bytes()).hexdigest()
        assert actual_hash == expected_hash


def test_main_release_zip_matches_the_verified_directory() -> None:
    with ZipFile(ARCHIVE) as archive:
        files = {name for name in archive.namelist() if not name.endswith("/")}
        assert files == REQUIRED_FILES
        for relative_path in files:
            assert (
                hashlib.sha256(archive.read(relative_path)).digest()
                == hashlib.sha256((BUNDLE / relative_path).read_bytes()).digest()
            )
