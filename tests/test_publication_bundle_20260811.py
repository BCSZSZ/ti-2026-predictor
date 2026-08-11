from __future__ import annotations

import hashlib
import re
from zipfile import ZipFile

from ti_predictor.paths import PATHS

BUNDLE = PATHS.root / "docs/publication/ti2026-release-bundle-2026-08-11"
ARCHIVE = PATHS.root / "docs/publication/ti2026-release-bundle-2026-08-11.zip"
REQUIRED_FILES = {
    "MANIFEST.sha256",
    "README.md",
    "WEIGHTING.md",
    "playbooks/group-roll/group-roll-publication-manual-v4.md",
    "playbooks/group-roll/stat-team-top3-publication-v4.md",
    "reports/ti2026-fantasy-title-recommendation-2026-08-10.md",
    "reports/ti2026-group-current-patch-series-evidence-2026-08-08.md",
    "reports/ti2026-group-event-tier-prize-2026-08-08.md",
    "reports/ti2026-group-forecast-publication-2026-08-10.md",
    "reports/ti2026-methodology-and-evidence-authority-report-2026-08-10.md",
    "reports/ti2026-methodology-quick-reference-2026-08-10.md",
    "reports/ti2026-swiss-round1-roster-update-2026-08-10.md",
    "reports/ti2026-team-prize-ytd-2026-08-08.md",
    "research/ti2026-player-history-scope.md",
    "research/ti2026-swiss-round1-lgd-roster-2026-08-10.md",
    "research/ti2026-team-display-alias-audit-2026-08-11.md",
    "research/ti2026-yandex-liquid-vision-rating-audit-2026-08-11.md",
}


def _bundle_files() -> set[str]:
    return {path.relative_to(BUNDLE).as_posix() for path in BUNDLE.rglob("*") if path.is_file()}


def test_current_release_bundle_is_complete_and_linked_from_root() -> None:
    assert _bundle_files() == REQUIRED_FILES

    root_readme = (PATHS.root / "README.md").read_text(encoding="utf-8")
    assert "docs/publication/ti2026-release-bundle-2026-08-11/README.md" in root_readme

    release_readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
    assert "## 16 队身份的处理" in release_readme
    assert "## LGD 的处理" in release_readme
    assert "5.1561 / 16" in release_readme
    assert "32.23%" in release_readme
    assert "35.28% / 31.31% / 24.05% / 17.35%" in release_readme
    assert "75.65% / 24.35%" in release_readme
    assert "9 条 identity bridge" in release_readme
    assert "203 场不同比赛" in release_readme
    assert "10150413" in release_readme
    assert "47 / 48" in release_readme

    forecast = (BUNDLE / "reports/ti2026-group-forecast-publication-2026-08-10.md").read_text(
        encoding="utf-8"
    )
    assert "0.536381 × 0.60 = 0.321829" in forecast
    assert "5.15608 ÷ 16 = 0.322255 ≈ 32.23%" in forecast
    assert "16 队身份怎样归一" in forecast

    identity_audit = (BUNDLE / "research/ti2026-team-display-alias-audit-2026-08-11.md").read_text(
        encoding="utf-8"
    )
    assert "应用的 9 条 identity bridge" in identity_audit
    assert "Registration identity windows" in identity_audit
    assert "8291895 Tundra Esports" in identity_audit

    stat_report = (BUNDLE / "playbooks/group-roll/stat-team-top3-publication-v4.md").read_text(
        encoding="utf-8"
    )
    assert "数据截止：`2026-08-10T13:45:12Z`" in stat_report
    assert "排名稳定性检查：400 次完整系列赛重采样" in stat_report


def test_release_bundle_local_markdown_links_resolve() -> None:
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


def test_release_manifest_matches_every_payload_file() -> None:
    lines = (BUNDLE / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    entries = {
        relative_path: expected_hash
        for expected_hash, relative_path in (line.split("  ", maxsplit=1) for line in lines if line)
    }
    assert set(entries) == REQUIRED_FILES - {"MANIFEST.sha256"}

    for relative_path, expected_hash in entries.items():
        actual_hash = hashlib.sha256((BUNDLE / relative_path).read_bytes()).hexdigest()
        assert actual_hash == expected_hash


def test_release_zip_matches_the_verified_directory() -> None:
    with ZipFile(ARCHIVE) as archive:
        files = {name for name in archive.namelist() if not name.endswith("/")}
        assert files == REQUIRED_FILES
        for relative_path in files:
            assert (
                hashlib.sha256(archive.read(relative_path)).digest()
                == hashlib.sha256((BUNDLE / relative_path).read_bytes()).digest()
            )


def test_lgd_mid_is_unavailable_but_other_lgd_roles_remain() -> None:
    stat_report = (BUNDLE / "playbooks/group-roll/stat-team-top3-publication-v4.md").read_text(
        encoding="utf-8"
    )
    mid_section = stat_report.split("## 中单 · 红色", maxsplit=1)[1].split("## 辅助位 · 蓝色", maxsplit=1)[0]
    assert "LGD Gaming" not in mid_section
    assert (
        "LGD Gaming"
        in stat_report.split("## 核心位 · 红色", maxsplit=1)[1].split("## 中单 · 红色", maxsplit=1)[0]
    )
    assert "LGD Gaming" in stat_report.split("## 辅助位 · 蓝色", maxsplit=1)[1]
