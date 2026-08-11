from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from ti_predictor.config import load_tournament_manifest
from ti_predictor.identity import canonicalize_match_team_ids
from ti_predictor.schemas import TeamIdentityBridge, TeamRegistrationIdentity


def _bridge() -> TeamIdentityBridge:
    return TeamIdentityBridge(
        bridge_id="brand-registration-to-canonical",
        raw_team_id=20,
        canonical_team_id=10,
        valid_from="2026-05-01T00:00:00Z",
        valid_to="2026-06-01T00:00:00Z",
        evidence_as_of="2026-06-15T00:00:00Z",
        verified_account_ids=(1, 2, 3, 4, 5),
        reason="restricted-sponsor-display-name",
        source="frozen-test-fixture",
        provenance="derived",
    )


def _matches() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "match_id": 1,
                "start_time": "2026-04-30T23:59:59Z",
                "radiant_team_id": 20,
                "dire_team_id": 30,
            },
            {
                "match_id": 2,
                "start_time": "2026-05-01T00:00:00Z",
                "radiant_team_id": 30,
                "dire_team_id": 20,
            },
            {
                "match_id": 3,
                "start_time": "2026-06-01T00:00:00Z",
                "radiant_team_id": 20,
                "dire_team_id": 30,
            },
        ]
    )


def test_canonicalize_match_team_ids_uses_evidence_and_half_open_validity() -> None:
    normalized, audit = canonicalize_match_team_ids(
        _matches(),
        [_bridge()],
        as_of=datetime(2026, 6, 15, tzinfo=UTC),
    )

    assert normalized["radiant_raw_team_id"].tolist() == [20, 30, 20]
    assert normalized["dire_raw_team_id"].tolist() == [30, 20, 30]
    assert normalized["radiant_team_id"].tolist() == [20, 30, 20]
    assert normalized["dire_team_id"].tolist() == [30, 10, 30]
    assert normalized.loc[1, "dire_team_identity_bridge_id"] == "brand-registration-to-canonical"
    assert audit["mapped_games"] == 1
    assert audit["bridges"][0]["mapped_games"] == 1


def test_canonicalize_match_team_ids_does_not_use_future_identity_evidence() -> None:
    normalized, audit = canonicalize_match_team_ids(
        _matches(),
        [_bridge()],
        as_of=datetime(2026, 6, 14, 23, 59, 59, tzinfo=UTC),
    )

    assert normalized["radiant_team_id"].tolist() == [20, 30, 20]
    assert normalized["dire_team_id"].tolist() == [30, 20, 30]
    assert audit["available_bridge_count"] == 0
    assert audit["mapped_games"] == 0


def test_registration_identity_does_not_use_future_epoch_evidence() -> None:
    identity = TeamRegistrationIdentity(
        valid_from="2026-05-01T00:00:00Z",
        evidence_as_of="2026-06-15T00:00:00Z",
        source="frozen-test-fixture",
        provenance="derived",
    )

    normalized, audit = canonicalize_match_team_ids(
        _matches(),
        [],
        as_of=datetime(2026, 6, 14, 23, 59, 59, tzinfo=UTC),
        registration_identities={20: identity},
    )

    assert normalized["radiant_team_id"].tolist() == [20, 30, 20]
    assert normalized["dire_team_id"].tolist() == [30, 20, 30]
    assert audit["available_registration_identity_count"] == 0
    assert audit["registration_identity_excluded_games"] == 0


def test_ti2026_identity_bridges_merge_verified_splits_without_inheriting_transfers(
    project_paths,
) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    cases = [
        # Long-lived organization ID replaced by the TI-compliant display identity.
        (101, "2026-03-16T08:17:12Z", 9303383, 10149530),
        # One-game and tournament-local registrations for the same exact team.
        (102, "2026-04-08T09:08:01Z", 9316703, 5017210),
        (103, "2026-05-26T08:01:27Z", 9824702, 9572001),
        (104, "2026-07-07T12:18:00Z", 10182299, 10149530),
        (105, "2026-07-07T18:16:19Z", 10182357, 10150413),
        (106, "2026-07-31T09:33:01Z", 10207984, 5017210),
        (107, "2026-07-31T12:27:48Z", 10208009, 10149530),
        (108, "2026-07-31T17:31:28Z", 10208071, 8261500),
        (109, "2026-07-31T17:31:28Z", 10208068, 10150538),
        # Exact or partial roster continuity alone must not transfer identity ownership.
        (110, "2026-05-18T11:58:58Z", 8291895, 8291895),
        (111, "2026-04-24T09:29:24Z", 9303484, 9303484),
    ]
    matches = pd.DataFrame(
        [
            {
                "match_id": match_id,
                "start_time": start_time,
                "radiant_team_id": raw_team_id,
                "dire_team_id": 99999999,
            }
            for match_id, start_time, raw_team_id, _ in cases
        ]
    )

    normalized, audit = canonicalize_match_team_ids(
        matches,
        manifest.team_identity_bridges,
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        registration_identities={
            team.team_id: team.registration_identity
            for team in manifest.teams
            if team.registration_identity is not None
        },
    )

    assert normalized["radiant_team_id"].tolist() == [expected for *_, expected in cases]
    assert normalized["radiant_raw_team_id"].tolist() == [raw for _, _, raw, _ in cases]
    assert audit["mapped_games"] == 9


def test_registration_identity_epoch_excludes_reused_current_id_without_touching_raw_evidence(
    project_paths,
) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    matches = pd.DataFrame(
        [
            {
                "match_id": 201,
                "start_time": "2026-05-30T14:25:01Z",
                "radiant_team_id": 10150413,
                "dire_team_id": 30,
            },
            {
                "match_id": 202,
                "start_time": "2026-06-01T00:00:00Z",
                "radiant_team_id": 10150413,
                "dire_team_id": 30,
            },
            {
                "match_id": 203,
                "start_time": "2018-04-10T10:55:51Z",
                "radiant_team_id": 5017210,
                "dire_team_id": 30,
            },
        ]
    )

    normalized, audit = canonicalize_match_team_ids(
        matches,
        manifest.team_identity_bridges,
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        registration_identities={
            team.team_id: team.registration_identity
            for team in manifest.teams
            if team.registration_identity is not None
        },
    )

    assert pd.isna(normalized.loc[0, "radiant_team_id"])
    assert normalized.loc[1, "radiant_team_id"] == 10150413
    assert pd.isna(normalized.loc[2, "radiant_team_id"])
    assert normalized["radiant_raw_team_id"].tolist() == [10150413, 10150413, 5017210]
    assert normalized["radiant_registration_identity_excluded"].tolist() == [True, False, True]
    assert audit["registration_identity_excluded_games"] == 2
