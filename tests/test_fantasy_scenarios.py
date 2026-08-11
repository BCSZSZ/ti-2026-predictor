from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import ti_predictor.fantasy.valuation as valuation_module
from ti_predictor.config import load_tournament_manifest
from ti_predictor.fantasy.roll import BannerState, EmblemState
from ti_predictor.fantasy.scenarios import (
    ROLE_IDS,
    GroupScenarioPolicy,
    SeriesBlock,
    build_common_scenario_set,
    build_series_block_pools,
    load_group_scenario_policy,
)
from ti_predictor.fantasy.valuation import (
    CoachTeamRoleMultipliers,
    RiskConfiguration,
    TeamOutcomeMatrix,
    TerminalValueCache,
    ValidatedCoachScenario,
    build_stat_forecast_package,
    cluster_bootstrap_stat_intervals,
    evaluate_banner_teams,
    lower_tail_cvar,
    match_group_roles,
    match_one_banner,
    score_series_block,
)
from ti_predictor.tournament.group import SLOT_CATEGORIES

CUTOFF = datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC)


def _small_policy(project_paths, *, scenarios: int = 8, replicates: int = 6) -> GroupScenarioPolicy:
    policy = load_group_scenario_policy(project_paths.config / "models" / "fantasy-group-scenarios-v1.json")
    return policy.model_copy(
        update={
            "scenario_count": scenarios,
            "minimum_series_blocks": 2,
            "bootstrap": policy.bootstrap.model_copy(
                update={"replicates": replicates, "scenarios_per_replicate": 4}
            ),
        }
    )


def _stat_value(stat_id: str, *, team_index: int, player_index: int, game_index: int) -> float:
    if stat_id == "deaths":
        return float(1 + (player_index + game_index) % 3)
    if stat_id == "teamfight_participation":
        return 0.4 + 0.02 * ((team_index + player_index + game_index) % 10)
    if stat_id == "gpm":
        return float(420 + 9 * team_index + 3 * player_index + game_index)
    if stat_id == "creep_score":
        return float(180 + 4 * team_index + 2 * player_index + game_index)
    if stat_id == "stuns":
        return float(5 + player_index + game_index)
    return float(1 + ((team_index + player_index + game_index) % 5))


def _synthetic_frames(manifest, rules_payload, *, series_per_team: int = 3):
    match_rows: list[dict] = []
    observation_rows: list[dict] = []
    evidence_rows: list[dict] = []
    match_id = 100_000
    capture = CUTOFF - timedelta(hours=1)
    for team_index, team in enumerate(manifest.teams):
        all_players = [player for role in ROLE_IDS for player in team.players[role]]
        for series_index in range(series_per_team):
            series_id = 10_000 + team_index * 100 + series_index
            for game_index in range(2):
                started = datetime(2026, 6, 1, tzinfo=UTC) + timedelta(
                    days=team_index * 4 + series_index,
                    hours=game_index,
                )
                match_rows.append(
                    {
                        "match_id": match_id,
                        "series_id": series_id,
                        "series_type": 1,
                        "start_time": started,
                        "as_of": capture,
                        "fetched_at": capture,
                    }
                )
                evidence_rows.append({"match_id": match_id, "evidence_weight": 1.0 + series_index})
                for player_index, player in enumerate(all_players):
                    row = {
                        "match_id": match_id,
                        "series_id": series_id,
                        "account_id": player.account_id,
                        "team_id": team.team_id,
                        "start_time": started,
                        "as_of": capture,
                    }
                    for stat_id, rule in rules_payload["fantasy"]["stats"].items():
                        row[stat_id] = _stat_value(
                            stat_id,
                            team_index=team_index,
                            player_index=player_index,
                            game_index=game_index,
                        )
                        row[f"{stat_id}_provenance"] = rule["provenance"]
                    observation_rows.append(row)
                match_id += 1
    return (
        pd.DataFrame(match_rows),
        pd.DataFrame(observation_rows),
        pd.DataFrame(evidence_rows),
    )


def _build_foundation(project_paths, rules_payload, *, series_per_team: int = 3):
    manifest = load_tournament_manifest(project_paths.tournament)
    policy = _small_policy(project_paths)
    matches, observations, evidence = _synthetic_frames(
        manifest, rules_payload, series_per_team=series_per_team
    )
    pools = build_series_block_pools(
        observations,
        matches,
        evidence,
        manifest,
        rules_payload,
        policy,
        as_of=CUTOFF,
    )
    outcomes = np.stack([np.roll(SLOT_CATEGORIES, offset) for offset in range(policy.scenario_count)])
    team_ids = np.asarray([team.team_id for team in manifest.teams], dtype=np.int64)
    scenarios = build_common_scenario_set(
        pools,
        group_team_ids=team_ids,
        group_outcomes=outcomes,
        policy=policy,
        data_snapshot_sha256="a" * 64,
        as_of=CUTOFF,
        seed=71,
    )
    return manifest, policy, pools, scenarios, matches, observations, evidence


def _banner(role: str) -> BannerState:
    stats = {
        "core": ("kills", "stuns", "gpm"),
        "mid": ("kills", "wards_placed", "stuns"),
        "support": ("wards_placed", "stuns", "smokes_used"),
    }[role]
    return BannerState(
        role=role,
        emblems=tuple(
            EmblemState(stat_id=stat_id, quality_tier=index + 1, trait_id=trait)
            for index, (stat_id, trait) in enumerate(
                zip(stats, ("benevolent", "vampiric", "unique"), strict=True)
            )
        ),
    )


def test_series_blocks_keep_games_pairs_and_provenance_together(project_paths, rules_payload) -> None:
    manifest, _, pools, _, _, _, _ = _build_foundation(project_paths, rules_payload)

    assert len(pools.pools) == 16 * 3
    assert pools.audit["minimum_complete_series_blocks"] == 3
    core = pools.by_key()[(manifest.teams[0].team_id, "core")]
    assert core.player_ids == tuple(player.account_id for player in manifest.teams[0].players["core"])
    assert all(len(block.match_ids) == 2 for block in core.blocks)
    assert all(block.game_stat_scores.shape == (2, 18) for block in core.blocks)
    assert core.blocks[0].game_stat_scores.flags.writeable is False
    with pytest.raises(ValueError):
        core.blocks[0].game_stat_scores[0, 0] = 0.0


def test_unavailable_mid_pool_is_audited_without_excluding_other_lgd_roles(
    project_paths,
    rules_payload,
) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    policy = _small_policy(project_paths)
    matches, observations, evidence = _synthetic_frames(manifest, rules_payload)
    lgd = next(team for team in manifest.teams if team.team_id == 10150538)
    top_id = lgd.players["mid"][0].account_id
    observations = observations.loc[~observations["account_id"].eq(top_id)].copy()

    pools = build_series_block_pools(
        observations,
        matches,
        evidence,
        manifest,
        rules_payload,
        policy,
        as_of=CUTOFF,
    )
    outcomes = np.stack([np.roll(SLOT_CATEGORIES, offset) for offset in range(policy.scenario_count)])
    team_ids = np.asarray([team.team_id for team in manifest.teams], dtype=np.int64)
    scenarios = build_common_scenario_set(
        pools,
        group_team_ids=team_ids,
        group_outcomes=outcomes,
        policy=policy,
        data_snapshot_sha256="b" * 64,
        as_of=CUTOFF,
        seed=73,
    )

    assert (10150538, "mid") not in pools.by_key()
    assert (10150538, "core") in pools.by_key()
    unavailable = next(
        item
        for item in pools.audit["team_role_availability"]
        if item["target_team_id"] == 10150538 and item["role"] == "mid"
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["complete_series_blocks"] == 0
    assert scenarios.draw_record_for(10150538, "core").target_team_id == 10150538
    with pytest.raises(KeyError, match="no common Scenario draws"):
        scenarios.draw_record_for(10150538, "mid")

    mid_matrix = evaluate_banner_teams(pools, scenarios, _banner("mid"), rules_payload)
    core_matrix = evaluate_banner_teams(pools, scenarios, _banner("core"), rules_payload)
    support_matrix = evaluate_banner_teams(pools, scenarios, _banner("support"), rules_payload)
    assert 10150538 not in mid_matrix.team_ids
    assert 10150538 in core_matrix.team_ids
    matched = match_group_roles(
        {"core": core_matrix, "mid": mid_matrix, "support": support_matrix},
        RiskConfiguration(),
    )
    assert matched.selected_team_ids[1] != 10150538
    stat_forecasts = build_stat_forecast_package(pools, scenarios, rules_payload)
    bootstrap = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        stat_forecasts,
        rules_payload,
        policy,
        seed=74,
        include_team_rankings=True,
    )
    assert bootstrap["team_rankings"]["rows"]
    assert all(
        row["team_id"] != 10150538 for row in bootstrap["team_rankings"]["rows"] if row["role"] == "mid"
    )


def test_pool_builder_audits_excluded_format_future_capture_and_wrong_provenance(
    project_paths,
    rules_payload,
) -> None:
    manifest = load_tournament_manifest(project_paths.tournament)
    policy = _small_policy(project_paths)
    matches, observations, evidence = _synthetic_frames(manifest, rules_payload, series_per_team=5)
    first_team_series = sorted(matches["series_id"].unique())[:5]
    proxy_series, excluded_format_series, future_capture_series = first_team_series[:3]
    proxy_matches = matches.loc[matches["series_id"].eq(proxy_series), "match_id"]
    core_player = manifest.teams[0].players["core"][0].account_id
    proxy_rows = observations["match_id"].isin(proxy_matches) & observations["account_id"].eq(core_player)
    observations.loc[proxy_rows, "kills_provenance"] = "proxy"
    matches.loc[matches["series_id"].eq(excluded_format_series), "series_type"] = 2
    matches.loc[matches["series_id"].eq(future_capture_series), "as_of"] = CUTOFF + timedelta(seconds=1)

    result = build_series_block_pools(
        observations,
        matches,
        evidence,
        manifest,
        rules_payload,
        policy,
        as_of=CUTOFF,
    )
    first_core = result.by_key()[(manifest.teams[0].team_id, "core")]

    assert len(first_core.blocks) == 2
    assert result.audit["positive_weight_excluded_series_format_games"] == 2
    assert result.audit["games_unavailable_at_as_of"] == 2
    first_core_audit = next(
        row
        for row in result.audit["pools"]
        if row["target_team_id"] == manifest.teams[0].team_id and row["role"] == "core"
    )
    assert first_core_audit["rejected_series"]["missing_or_wrong_provenance"] == 1


def test_common_scenarios_are_paired_deterministic_and_order_independent(
    project_paths,
    rules_payload,
) -> None:
    manifest, policy, pools, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)
    outcomes = scenarios.group_categories.copy()
    team_ids = np.asarray([team.team_id for team in manifest.teams], dtype=np.int64)
    repeated = build_common_scenario_set(
        pools,
        group_team_ids=team_ids,
        group_outcomes=outcomes,
        policy=policy,
        data_snapshot_sha256="a" * 64,
        as_of=CUTOFF,
        seed=71,
    )
    changed = build_common_scenario_set(
        pools,
        group_team_ids=team_ids,
        group_outcomes=outcomes,
        policy=policy,
        data_snapshot_sha256="a" * 64,
        as_of=CUTOFF,
        seed=72,
    )

    assert repeated.semantic_hash == scenarios.semantic_hash
    assert changed.semantic_hash != scenarios.semantic_hash
    assert scenarios.series_counts.min() == 4
    assert scenarios.series_counts.max() == 6
    assert scenarios.scenario_ids.flags.writeable is False
    for team_index, team_id in enumerate(scenarios.team_ids):
        core_draws = scenarios.draws_for(team_id, "core")
        support_draws = scenarios.draws_for(team_id, "support")
        used = np.arange(6)[None, :] < scenarios.series_counts[:, team_index, None]
        assert np.all(core_draws[used] >= 0)
        assert np.all(core_draws[~used] == -1)
        assert core_draws.shape == support_draws.shape

    invalid_outcomes = outcomes.copy()
    invalid_outcomes[0] = 0
    with pytest.raises(ValueError, match="violates capacity"):
        build_common_scenario_set(
            pools,
            group_team_ids=team_ids,
            group_outcomes=invalid_outcomes,
            policy=policy,
            data_snapshot_sha256="a" * 64,
            as_of=CUTOFF,
            seed=71,
        )


def test_complete_banner_is_combined_before_top_two_and_accepts_validated_coach() -> None:
    block = SeriesBlock(
        target_team_id=1,
        role="mid",
        player_ids=(11,),
        historical_team_id=7,
        series_id=101,
        match_ids=(1, 2, 3),
        start_times=("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"),
        evidence_weight=1.0,
        stat_ids=("a", "b", "c"),
        game_stat_scores=np.asarray([[100, 0, 0], [0, 100, 0], [60, 60, 0]], dtype=float),
    )

    combined = score_series_block(
        block,
        stat_indexes=(0, 1),
        emblem_score_multipliers=(1.0, 1.0),
    )
    separately_optimized = 160.0 + 160.0
    coached = score_series_block(
        block,
        stat_indexes=(0, 1),
        emblem_score_multipliers=(1.0, 1.0),
        coach_game_multipliers=np.asarray([1.0, 2.0, 1.0]),
    )

    assert combined == 220.0
    assert combined != separately_optimized
    assert coached == 320.0


def test_banner_and_group_matching_retain_whole_team_vectors(project_paths, rules_payload) -> None:
    _, _, pools, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)
    risk = RiskConfiguration(mean_retention_epsilon=0.0, cvar_alpha=0.1)
    cache = TerminalValueCache()
    matrices = {role: cache.banner(pools, scenarios, _banner(role), rules_payload) for role in ROLE_IDS}
    assert cache.banner(pools, scenarios, _banner("core"), rules_payload) is matrices["core"]

    core_match = cache.matched_banner(matrices["core"], risk)
    core_index = matrices["core"].team_ids.index(core_match.selected_team_ids[0])
    assert np.array_equal(core_match.outcomes, matrices["core"].outcomes[core_index])

    group_match = cache.matched_group(matrices, risk)
    expected = np.zeros(len(scenarios.scenario_ids))
    for role, team_id in zip(ROLE_IDS, group_match.selected_team_ids, strict=True):
        team_index = matrices[role].team_ids.index(team_id)
        expected += matrices[role].outcomes[team_index]
    assert np.array_equal(group_match.outcomes, expected)
    assert group_match.summary["mean"] == pytest.approx(group_match.maximum_mean)

    changed = evaluate_banner_teams(
        pools,
        scenarios,
        BannerState(
            role="core",
            emblems=(
                EmblemState("deaths", 1, "unique"),
                EmblemState("courier_kills", 1, "unique"),
                EmblemState("tower_kills", 1, "unique"),
            ),
        ),
        rules_payload,
    )
    assert changed.semantic_hash != matrices["core"].semantic_hash
    assert match_one_banner(changed, risk).scenario_sha256 == scenarios.semantic_hash
    invalid_trait = BannerState(
        role="core",
        emblems=(
            EmblemState("kills", 1, "not-a-trait"),
            EmblemState("stuns", 1, "unique"),
            EmblemState("gpm", 1, "unique"),
        ),
    )
    with pytest.raises(ValueError, match="unknown Fantasy Trait"):
        evaluate_banner_teams(pools, scenarios, invalid_trait, rules_payload)


def test_banner_valuation_accepts_only_aligned_validated_coach_candidates(
    project_paths,
    rules_payload,
) -> None:
    _, _, pools, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)
    uncoached = evaluate_banner_teams(pools, scenarios, _banner("core"), rules_payload)
    entries = tuple(
        CoachTeamRoleMultipliers(
            target_team_id=team_id,
            role="core",
            values=np.full((len(scenarios.scenario_ids), 6, 3), 2.0),
        )
        for team_id in scenarios.team_ids
    )
    coach = ValidatedCoachScenario(
        candidate_id="fixture-double",
        scenario_sha256=scenarios.semantic_hash,
        entries=entries,
        evidence_sha256="c" * 64,
    )
    coached = evaluate_banner_teams(
        pools,
        scenarios,
        _banner("core"),
        rules_payload,
        coach=coach,
    )

    assert coached.outcomes == pytest.approx(uncoached.outcomes * 2.0)
    mismatched = ValidatedCoachScenario(
        candidate_id="wrong-scenarios",
        scenario_sha256="d" * 64,
        entries=entries,
        evidence_sha256="c" * 64,
    )
    with pytest.raises(ValueError, match="not aligned"):
        evaluate_banner_teams(
            pools,
            scenarios,
            _banner("core"),
            rules_payload,
            coach=mismatched,
        )


def test_group_cvar_is_joint_not_sum_of_role_cvars() -> None:
    scenario_hash = "b" * 64
    matrices = {
        "core": TeamOutcomeMatrix(
            "banner", "core", "core", scenario_hash, (1,), np.asarray([[0, 100, 100, 100]])
        ),
        "mid": TeamOutcomeMatrix(
            "banner", "mid", "mid", scenario_hash, (1,), np.asarray([[100, 0, 100, 100]])
        ),
        "support": TeamOutcomeMatrix(
            "banner", "support", "support", scenario_hash, (1,), np.asarray([[100, 100, 0, 100]])
        ),
    }
    risk = RiskConfiguration(cvar_alpha=0.25)

    result = match_group_roles(matrices, risk)
    separate_sum = sum(lower_tail_cvar(matrix.outcomes[0], 0.25) for matrix in matrices.values())

    assert separate_sum == 0.0
    assert result.summary["cvar"] == 200.0
    assert lower_tail_cvar(np.asarray([0.0, 10.0, 20.0]), 0.5) == pytest.approx(10.0 / 3.0)


def test_group_matching_skips_combinations_that_cannot_reach_mean_floor(monkeypatch) -> None:
    scenario_hash = "f" * 64
    team_ids = tuple(range(1, 17))
    outcomes = np.zeros((16, 4), dtype=float)
    outcomes[0] = 100.0
    matrices = {
        role: TeamOutcomeMatrix(
            "banner",
            role,
            role,
            scenario_hash,
            team_ids,
            outcomes,
        )
        for role in ROLE_IDS
    }
    combinations_visited = 0

    def counting_product(*args, **kwargs):
        nonlocal combinations_visited
        for indexes in itertools.product(*args, **kwargs):
            combinations_visited += 1
            yield indexes

    monkeypatch.setattr(valuation_module, "product", counting_product)

    result = match_group_roles(
        matrices,
        RiskConfiguration(mean_retention_epsilon=0.0, cvar_alpha=0.1),
    )

    assert result.selected_team_ids == (1, 1, 1)
    assert combinations_visited == 1


@pytest.mark.parametrize("epsilon", [0.0, 0.01, 0.02, 0.05])
def test_group_candidate_pruning_matches_full_enumeration(monkeypatch, epsilon: float) -> None:
    team_ids = tuple(range(1, 17))
    for seed in range(3):
        generator = np.random.default_rng(seed)
        matrices = {
            role: TeamOutcomeMatrix(
                "banner",
                role,
                role,
                "e" * 64,
                team_ids,
                generator.normal(loc=100.0, scale=15.0, size=(16, 13)),
            )
            for role in ROLE_IDS
        }
        risk = RiskConfiguration(mean_retention_epsilon=epsilon, cvar_alpha=0.1)

        pruned = match_group_roles(matrices, risk)
        with monkeypatch.context() as full_enumeration:
            full_enumeration.setattr(
                valuation_module,
                "product",
                lambda *args: itertools.product(range(16), repeat=len(ROLE_IDS)),
            )
            reference = match_group_roles(matrices, risk)

        assert pruned.selected_team_ids == reference.selected_team_ids
        assert np.array_equal(pruned.outcomes, reference.outcomes)
        assert pruned.maximum_mean == reference.maximum_mean
        assert pruned.summary == reference.summary
        assert pruned.semantic_hash == reference.semantic_hash


def test_stat_forecasts_and_cluster_bootstrap_have_stable_hashes(project_paths, rules_payload) -> None:
    _, policy, pools, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)
    forecasts = build_stat_forecast_package(pools, scenarios, rules_payload)
    first = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        forecasts,
        rules_payload,
        policy,
        seed=901,
    )
    repeated = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        forecasts,
        rules_payload,
        policy,
        seed=901,
    )

    assert len(forecasts["rows"]) == 42
    assert {
        "madstone_collected",
        "smokes_used",
        "watchers_taken",
        "lotuses_gained",
        "tormentor_kills",
    }.issubset({row["stat_id"] for row in forecasts["rows"]})
    assert len(first["rows"]) == 42
    assert first["bootstrap_sha256"] == repeated["bootstrap_sha256"]
    assert all(0.0 <= row["interval_lower"] <= row["interval_upper"] <= 1.0 for row in first["rows"])
    assert all(row["point_relative_to_best"] <= 1.0 for row in first["rows"])


def test_team_rank_bootstrap_is_optional_complete_and_deterministic(
    project_paths,
    rules_payload,
) -> None:
    _, policy, pools, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)
    forecasts = build_stat_forecast_package(pools, scenarios, rules_payload)
    legacy = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        forecasts,
        rules_payload,
        policy,
        seed=901,
    )
    explicit_legacy = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        forecasts,
        rules_payload,
        policy,
        seed=901,
        include_team_rankings=False,
    )
    extended = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        forecasts,
        rules_payload,
        policy,
        seed=901,
        include_team_rankings=True,
    )
    repeated = cluster_bootstrap_stat_intervals(
        pools,
        scenarios,
        forecasts,
        rules_payload,
        policy,
        seed=901,
        include_team_rankings=True,
    )

    assert legacy == explicit_legacy
    assert "team_rankings" not in legacy
    assert extended["bootstrap_sha256"] == repeated["bootstrap_sha256"]
    rankings = extended["team_rankings"]
    assert rankings["top_k"] == 3
    assert rankings["point_order"] == "descending_mean_then_team_id"
    assert rankings["bootstrap_order"] == "descending_mean_then_team_id"
    assert (
        rankings["probability_interpretation"]
        == "series_resampling_frequency_not_calibrated_future_probability"
    )
    assert len(rankings["rows"]) == 42 * len(scenarios.team_ids)

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rankings["rows"]:
        grouped.setdefault((row["role"], row["stat_id"]), []).append(row)
        assert 0.0 <= row["rank1_probability"] <= 1.0
        assert 0.0 <= row["top3_probability"] <= 1.0
        assert row["gap_to_point_best_fraction"] >= 0.0
    assert len(grouped) == 42
    for rows in grouped.values():
        assert sorted(row["point_rank"] for row in rows) == list(range(1, len(scenarios.team_ids) + 1))
        assert sum(row["rank1_probability"] for row in rows) == pytest.approx(1.0)
        assert sum(row["top3_probability"] for row in rows) == pytest.approx(3.0)


def test_policy_rejects_missing_category_or_unapproved_provenance(project_paths) -> None:
    path = project_paths.config / "models" / "fantasy-group-scenarios-v1.json"
    payload = pd.read_json(path, typ="series").to_dict()
    payload["group_category_series_counts"] = {"four_zero": 4}
    with pytest.raises(ValueError, match="category Series-count"):
        GroupScenarioPolicy.model_validate(payload)

    payload = pd.read_json(path, typ="series").to_dict()
    payload["allowed_provenance"] = ["exact"]
    with pytest.raises(ValueError, match="exact and derived"):
        GroupScenarioPolicy.model_validate(payload)
