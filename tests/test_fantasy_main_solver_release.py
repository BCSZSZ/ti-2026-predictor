from __future__ import annotations

import copy
import json

from ti_predictor.fantasy.main_current_advisor import analyze_main_current_screen
from ti_predictor.fantasy.main_roll import MainRollState
from ti_predictor.fantasy.main_scenarios import (
    build_main_scenario_set_from_model,
    build_projected_main_scenario_set_from_group,
)
from ti_predictor.fantasy.main_solver_release import (
    MAIN_SOLVER_RELEASE_ID,
    MAIN_SOLVER_RELEASE_SCHEMA_VERSION,
    load_main_solver_policy,
    load_main_solver_release_context,
    main_solver_readiness,
    main_solver_team_options,
    write_main_solver_release_bundle,
)
from ti_predictor.fantasy.roll import BannerState, EmblemState, RollOffer
from ti_predictor.fantasy.scenarios import PoolBuildResult
from ti_predictor.fantasy.solver_release import load_solver_release_context
from ti_predictor.hashing import sha256_json
from ti_predictor.models.ratings import TeamStrengthModel


def test_projected_main_pointer_is_explicitly_usable_before_the_actual_eight(project_paths) -> None:
    pointer = project_paths.root / "deploy/runtime/main-current.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "release_schema_version": MAIN_SOLVER_RELEASE_SCHEMA_VERSION,
                "release_id": MAIN_SOLVER_RELEASE_ID,
                "period": "main",
                "status": "provisional",
                "eligibility_mode": "projected",
                "candidate_team_count": 16,
                "entrant_team_count": 8,
                "as_of": "2026-08-13T12:00:00Z",
                "lock_at": "2026-08-20T02:00:00Z",
                "file": "releases/main.json.zst",
                "bytes": 1,
                "file_sha256": "a" * 64,
                "release_sha256": "b" * 64,
                "reason": "usable now with projected advancement",
            }
        ),
        encoding="utf-8",
    )

    readiness = main_solver_readiness(project_paths)

    assert readiness.status == "provisional"
    assert readiness.eligibility_mode == "projected"
    assert readiness.candidate_team_count == 16
    assert readiness.entrant_team_count == 8
    assert "usable now" in readiness.reason


def test_projected_main_release_round_trip_keeps_all_sixteen_team_options(project_paths) -> None:
    group = load_solver_release_context()
    policy = load_main_solver_policy(
        project_paths.config / "models/fantasy-main-current-screen-advisor-v1.json"
    )
    team_ids = tuple(group.team_names)
    model = TeamStrengthModel({team_id: 1500.0 + index * 15 for index, team_id in enumerate(team_ids)})
    scenarios = build_projected_main_scenario_set_from_group(
        group.pool_result,
        group_scenarios=group.scenarios,
        model=model,
        scenario_count=policy.scenario_count,
        policy_id=policy.policy_id,
        data_snapshot_sha256="c" * 64,
        as_of="2026-08-13T12:00:00Z",
        seed=policy.seed,
    )

    write_main_solver_release_bundle(
        group,
        scenarios,
        lock_at="2026-08-20T02:00:00Z",
        paths=project_paths,
    )
    loaded = load_main_solver_release_context(group, paths=project_paths)
    readiness = main_solver_readiness(project_paths)

    assert readiness.status == "provisional"
    assert loaded.eligibility_mode == "projected"
    assert loaded.strategy_catalog.default_strategy_id == "main-greedy-immediate-v1"
    assert loaded.strategy_catalog.strategies.g_lite.strategy_id == ("main-greedy-selective-two-step-v1")
    assert tuple(loaded.team_names) == team_ids
    options = main_solver_team_options(loaded)
    assert len(options["core"]) == 16
    assert len(options["mid"]) == 15
    assert len(options["support"]) == 16


def test_main_release_round_trip_is_content_addressed_and_period_isolated(project_paths) -> None:
    group = load_solver_release_context()
    policy = load_main_solver_policy(
        project_paths.config / "models/fantasy-main-current-screen-advisor-v1.json"
    )
    team_ids = tuple(group.team_names)[:8]
    model = TeamStrengthModel({team_id: 1500.0 + index * 15 for index, team_id in enumerate(team_ids)})
    refreshed_audit = copy.deepcopy(group.pool_result.audit)
    refreshed_audit["team_role_availability"] = list(reversed(refreshed_audit["team_role_availability"]))
    refreshed_pool = PoolBuildResult(
        pools=group.pool_result.pools,
        audit=refreshed_audit,
        semantic_hash=sha256_json(
            {
                "pools": [pool.semantic_hash for pool in group.pool_result.pools],
                "team_role_availability": refreshed_audit["team_role_availability"],
            }
        ),
    )
    scenarios = build_main_scenario_set_from_model(
        refreshed_pool,
        team_ids=team_ids,
        model=model,
        scenario_count=policy.scenario_count,
        policy_id=policy.policy_id,
        data_snapshot_sha256="d" * 64,
        as_of="2026-08-16T12:00:00Z",
        seed=policy.seed,
    )

    written = write_main_solver_release_bundle(
        group,
        scenarios,
        lock_at="2026-08-20T02:00:00Z",
        pool_result=refreshed_pool,
        paths=project_paths,
    )
    loaded = load_main_solver_release_context(group, paths=project_paths)

    assert written.pointer_path.is_file()
    assert written.path.with_name(written.path.name + ".sha256").is_file()
    assert written.file_sha256 == json.loads(written.pointer_path.read_text(encoding="utf-8"))["file_sha256"]
    assert loaded.as_of == scenarios.as_of
    assert loaded.scenario_count == policy.scenario_count
    assert loaded.terminal.pool_result.semantic_hash == refreshed_pool.semantic_hash
    assert loaded.terminal.pool_result.semantic_hash != group.pool_result.semantic_hash
    assert tuple(loaded.team_names) == team_ids
    options = main_solver_team_options(loaded)
    assert set(options) == {"core", "mid", "support"}
    assert all(options.values())

    banners = tuple(
        BannerState(
            role,
            tuple(
                EmblemState(
                    loaded.roll_rules.stats_for(color)[0],
                    3,
                    loaded.roll_rules.traits[index],
                )
                for index, color in enumerate(loaded.roll_rules.colors_for(role)[:5])
            ),
        )
        for role in loaded.roll_rules.roles
    )
    result = analyze_main_current_screen(
        loaded,
        MainRollState(banners, RollOffer((14, 12, 31)), 30),
    )
    assert result["period"] == "main"
    assert result["analysis_sha256"]
    assert any("Operation #24" in warning for warning in result["limitations"])
