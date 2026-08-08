from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from ti_predictor.config import load_tournament_manifest
from ti_predictor.paths import PATHS
from ti_predictor.prize_reporting import render_team_prize_markdown, validate_prize_ledger


def _fixture() -> dict:
    return {
        "artifact_type": "ti2026_team_prize_ytd_ledger",
        "schema_version": 1,
        "as_of": "2026-08-08T12:00:00Z",
        "calendar_year": 2026,
        "currency": "USD",
        "amount_semantics": "published_gross_team_award",
        "teams": [
            {"team_id": 1, "display_name": "Alpha"},
            {"team_id": 2, "display_name": "Beta"},
        ],
        "sources": [
            {
                "source_id": "event-a",
                "url": "https://example.com/event-a",
                "observed_at": "2026-08-08T11:00:00Z",
            }
        ],
        "awards": [
            {
                "award_id": "alpha-event-a",
                "team_id": 1,
                "event_id": "event-a",
                "event_name": "Event A",
                "event_end_date": "2026-08-01",
                "tier": "Tier 1",
                "placement": "冠军",
                "award_scope": "team",
                "status": "confirmed",
                "amount_usd": "125.50",
                "components_usd": {"prize_money": "100.00", "club_reward": "25.50"},
                "source_ids": ["event-a"],
            },
            {
                "award_id": "beta-event-a",
                "team_id": 2,
                "event_id": "event-a",
                "event_name": "Event A",
                "event_end_date": "2026-08-01",
                "tier": "Tier 1",
                "placement": "亚军",
                "award_scope": "team",
                "status": "confirmed",
                "amount_usd": "50.00",
                "source_ids": ["event-a"],
            },
        ],
        "declared_team_totals_usd": {"1": "125.50", "2": "50.00"},
        "declared_total_usd": "175.50",
    }


def test_prize_ledger_recomputes_totals_and_player_report_omits_ids_and_sources() -> None:
    payload = _fixture()

    totals = validate_prize_ledger(payload, expected_team_ids={1, 2})
    report = render_team_prize_markdown(payload)

    assert [row.display_name for row in totals] == ["Alpha", "Beta"]
    assert [str(row.total_usd) for row in totals] == ["125.50", "50.00"]
    assert "**$125.50**" in report
    assert "https://example.com" not in report
    assert "team_id" not in report


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row: row.update(amount_usd="126.00"), "components do not sum"),
        (lambda row: row.update(award_scope="personal"), "confirmed team award"),
        (lambda row: row.update(event_end_date="2026-08-09"), "outside the governed"),
        (lambda row: row.update(source_ids=["missing"]), "unknown source"),
    ],
)
def test_prize_ledger_rejects_semantic_or_temporal_drift(mutation, message: str) -> None:
    payload = copy.deepcopy(_fixture())
    mutation(payload["awards"][0])

    with pytest.raises(ValueError, match=message):
        validate_prize_ledger(payload)


def test_committed_ti2026_prize_report_matches_governed_ledger() -> None:
    ledger_path = PATHS.config / "publication" / "ti2026-team-prize-ytd-2026-08-08.json"
    if not ledger_path.is_file():
        pytest.skip("production prize ledger is added by the publication phase")
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    manifest = load_tournament_manifest(PATHS.tournament)
    expected_ids = {team.team_id for team in manifest.teams}

    totals = validate_prize_ledger(payload, expected_team_ids=expected_ids)
    rendered = render_team_prize_markdown(payload)
    report_path = PATHS.root / "docs/reports/ti2026-team-prize-ytd-2026-08-08.md"
    bundle_path = (
        PATHS.root
        / "docs/publication/ti2026-release-bundle-2026-08-08/reports/ti2026-team-prize-ytd-2026-08-08.md"
    )

    assert len(totals) == 16
    assert [(row.display_name, row.award_count, row.total_usd) for row in totals] == [
        ("TEAM VISION", 8, Decimal("1365000")),
        ("Team Yandex", 8, Decimal("1177500")),
        ("Team Liquid", 10, Decimal("1002500")),
        ("BoomBoys", 9, Decimal("985500")),
        ("Aurora Gaming", 9, Decimal("777000")),
        ("Team Falcons", 9, Decimal("540000")),
        ("Team Spirit", 9, Decimal("501250")),
        ("Xtreme Gaming", 11, Decimal("461250")),
        ("Vici Gaming", 8, Decimal("347000")),
        ("LGD Gaming", 3, Decimal("237500")),
        ("OG", 7, Decimal("185000")),
        ("Team Resilience", 3, Decimal("166000")),
        ("Nigma Galaxy", 7, Decimal("165000")),
        ("GamerLegion", 8, Decimal("143250")),
        ("Iron Wing", 6, Decimal("108500")),
        ("HULIGANI", 7, Decimal("42018.51")),
    ]
    assert payload["declared_total_usd"] == "8204268.51"
    assert any(
        award["team_id"] == 7119388 and award["event_id"] == "dreamleague-28"
        for award in payload["awards"]
    )
    assert any(
        award["team_id"] == 9964962 and award["event_id"] == "pgl-wallachia-8"
        for award in payload["awards"]
    )
    assert not any(
        award["team_id"] == 10150538 and award["event_id"] == "games-of-future-2026"
        for award in payload["awards"]
    )
    assert report_path.read_text(encoding="utf-8") == rendered
    assert bundle_path.read_text(encoding="utf-8") == rendered
