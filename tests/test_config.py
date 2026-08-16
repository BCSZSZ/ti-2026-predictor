from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ti_predictor.config import (
    load_swiss_format,
    load_swiss_simulation_policy,
    load_team_strength_policy,
    load_tournament_manifest,
    roster_intervals,
)
from ti_predictor.identity import RosterIndex


def test_lgd_mid_replacement_uses_half_open_roster_intervals(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    cutoff = datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC)
    index = RosterIndex(roster_intervals(manifest, as_of=cutoff))
    boundary = datetime(2026, 8, 10, 6, 10, 26, tzinfo=UTC)

    before = index.resolve(1026694469, boundary - timedelta(seconds=1))
    after = index.resolve(94054712, boundary)

    assert manifest.schema_version == 3
    assert before is not None
    assert before.team_id == 10150538
    assert before.role == "mid"
    assert index.resolve(1026694469, boundary) is None
    assert after is not None
    assert after.team_id == 10150538
    assert after.role == "mid"
    assert index.resolve(94054712, boundary - timedelta(seconds=1)) is None


def test_schema_v2_manifest_rejects_as_of_before_roster_snapshot(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)

    with pytest.raises(ValueError, match="roster snapshot was not available"):
        roster_intervals(manifest, as_of=datetime(2026, 8, 10, 13, 44, 35, tzinfo=UTC))


def test_manifest_records_verified_registration_identity_bridges(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)

    bridges = {bridge.raw_team_id: bridge for bridge in manifest.team_identity_bridges}
    assert {raw_team_id: bridge.canonical_team_id for raw_team_id, bridge in bridges.items()} == {
        9303383: 10149530,
        9316703: 5017210,
        9824702: 9572001,
        10182299: 10149530,
        10182357: 10150413,
        10207984: 5017210,
        10208009: 10149530,
        10208068: 10150538,
        10208071: 8261500,
    }
    assert all(
        bridge.valid_to == datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC) for bridge in bridges.values()
    )
    assert all(bridge.provenance == "derived" for bridge in bridges.values())
    assert set(bridges[9824702].verified_account_ids) == {
        73401082,
        106573901,
        164199202,
        195108598,
        1044002267,
    }
    teams = {team.team_id: team for team in manifest.teams}
    assert teams[10150413].registration_identity is not None
    assert teams[10150413].registration_identity.valid_from == datetime(2026, 6, 1, tzinfo=UTC)
    assert teams[5017210].registration_identity is not None
    assert teams[5017210].registration_identity.valid_from == datetime(2026, 4, 8, 9, 8, 1, tzinfo=UTC)


def test_main_policy_and_official_broadcast_seed_order_are_period_isolated(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    group_policy = load_team_strength_policy(manifest, config_root=project_paths.config)
    main_policy = load_team_strength_policy(
        manifest,
        config_root=project_paths.config,
        period="main",
    )

    assert group_policy.current_event_stage_scope is None
    assert main_policy.current_event_stage_scope is not None
    assert len(main_policy.current_event_stage_scope.match_ids) == 109
    assert main_policy.team_strength_current_event_stage_multiplier == 1.5
    assert main_policy.fantasy_current_event_stage_multiplier == 1.5
    seeds = manifest.main_event_seeds
    assert [(seeds[0], seeds[7]), (seeds[3], seeds[4]), (seeds[1], seeds[6]), (seeds[2], seeds[5])] == [
        (10150413, 7119388),
        (9572001, 8255888),
        (2163, 9823272),
        (10136357, 9247354),
    ]


def test_swiss_format_has_official_round_one_pairs_and_stable_ids(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    swiss = load_swiss_format(
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        manifest=manifest,
        path=project_paths.swiss,
    )

    pairs = [(series.team_a_id, series.team_b_id) for series in swiss.first_round]
    assert pairs[0] == (9247354, 10150538)
    assert pairs[-1] == (9823272, 10149530)
    assert {series.initial_group for series in swiss.first_round[:4]} == {"A"}
    assert {series.initial_group for series in swiss.first_round[4:]} == {"B"}


def test_swiss_format_rejects_future_snapshot(project_paths) -> None:
    with pytest.raises(ValueError, match="Swiss format was not available"):
        load_swiss_format(
            as_of=datetime(2026, 8, 10, 13, 45, 11, tzinfo=UTC),
            path=project_paths.swiss,
        )


def test_swiss_policy_versions_lgd_scenarios(project_paths) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    policy = load_swiss_simulation_policy(
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        manifest=manifest,
        path=project_paths.swiss_policy,
    )

    assert policy.primary_scenario == "roster_shock_0_60"
    assert policy.roster_shock.target_team_id == 10150538
    assert {scenario.roster_strength_multiplier for scenario in policy.scenarios} == {
        1.0,
        0.9,
        0.75,
        0.6,
    }
