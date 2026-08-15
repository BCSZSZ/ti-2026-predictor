from __future__ import annotations

import json
from pathlib import Path

import pytest

from ti_predictor.fantasy.current_advisor import (
    CurrentAdvisorError,
    _preferred_action,
    _resolve_current_advisor_rule_snapshot,
    classify_recommendation,
    load_current_advisor_policy,
    load_current_advisor_team_options,
    rank_title_for_lineup,
)
from ti_predictor.hashing import sha256_file, sha256_json


def _write_rule_snapshot(
    root: Path,
    *,
    snapshot_id: str,
    as_of: str,
    created_at: str,
    steam_build: str,
    semantic_sha256: str,
) -> Path:
    path = root / "data" / "raw" / "rules" / snapshot_id / "rule_snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "event_id": "international_2026",
                "as_of": as_of,
                "created_at": created_at,
                "source": "dota_client",
                "steam_build": steam_build,
                "source_files": [],
                "canonical_rules_sha256": "c" * 64,
                "snapshot_sha256": semantic_sha256,
                "status": "warning",
                "issues": [],
                "observed": {"fantasy_roll": {}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_v2_policy_freezes_current_screen_boundaries(project_paths) -> None:
    policy = load_current_advisor_policy(
        project_paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )

    assert policy.period == "group"
    assert policy.analysis.primary_model in policy.analysis.models
    assert policy.responsive_scenarios.count == 256
    assert policy.boundaries.future_offer_generation is False
    assert policy.boundaries.dota_client_control is False
    assert policy.boundaries.period_stack == "group"


def test_current_advisor_accepts_a_newer_metadata_only_rule_snapshot(project_paths) -> None:
    frozen_path = _write_rule_snapshot(
        project_paths.root,
        snapshot_id="20260810T134439Z-aaaaaaaaaaaa",
        as_of="2026-08-10T13:44:36Z",
        created_at="2026-08-10T13:44:39Z",
        steam_build="6893:10895878",
        semantic_sha256="a" * 64,
    )
    _write_rule_snapshot(
        project_paths.root,
        snapshot_id="20260811T025356Z-aaaaaaaaaaaa",
        as_of="2026-08-11T02:53:54Z",
        created_at="2026-08-11T02:53:56Z",
        steam_build="6894:10897748",
        semantic_sha256="a" * 64,
    )
    policy = load_current_advisor_policy(
        project_paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )
    policy = policy.model_copy(
        update={"source": policy.source.model_copy(update={"rule_snapshot_sha256": sha256_file(frozen_path)})}
    )

    snapshot, snapshot_path = _resolve_current_advisor_rule_snapshot(policy, paths=project_paths)

    assert snapshot.snapshot_id == "20260810T134439Z-aaaaaaaaaaaa"
    assert snapshot_path == frozen_path


def test_current_advisor_rejects_a_newer_semantically_changed_rule_snapshot(project_paths) -> None:
    frozen_path = _write_rule_snapshot(
        project_paths.root,
        snapshot_id="20260810T134439Z-aaaaaaaaaaaa",
        as_of="2026-08-10T13:44:36Z",
        created_at="2026-08-10T13:44:39Z",
        steam_build="6893:10895878",
        semantic_sha256="a" * 64,
    )
    _write_rule_snapshot(
        project_paths.root,
        snapshot_id="20260811T025356Z-bbbbbbbbbbbb",
        as_of="2026-08-11T02:53:54Z",
        created_at="2026-08-11T02:53:56Z",
        steam_build="6894:10897748",
        semantic_sha256="b" * 64,
    )
    policy = load_current_advisor_policy(
        project_paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )
    policy = policy.model_copy(
        update={"source": policy.source.model_copy(update={"rule_snapshot_sha256": sha256_file(frozen_path)})}
    )

    with pytest.raises(CurrentAdvisorError, match="semantics drifted"):
        _resolve_current_advisor_rule_snapshot(policy, paths=project_paths)


def test_current_advisor_team_options_exclude_only_unavailable_role(project_paths) -> None:
    policy = load_current_advisor_policy(
        project_paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json"
    )
    artifact = project_paths.artifacts / "fantasy-test"
    artifact.mkdir(parents=True)
    payload = {
        "artifact_type": "group_fantasy_stat_evidence",
        "scenario_set": {
            "unavailable_team_roles": [
                {"target_team_id": 10150538, "role": "mid"},
            ]
        },
    }
    payload["evidence_package_sha256"] = sha256_json(payload)
    (artifact / "group-fantasy-evidence.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    source = policy.model_copy(
        update={
            "source": policy.source.model_copy(
                update={"p3_evidence_sha256": payload["evidence_package_sha256"]}
            )
        }
    )
    (project_paths.config / "models" / "fantasy-group-current-screen-advisor-v2.json").write_text(
        source.model_dump_json(indent=2),
        encoding="utf-8",
    )

    options = load_current_advisor_team_options(paths=project_paths)

    assert 10150538 not in dict(options["mid"])
    assert 10150538 in dict(options["core"])
    assert 10150538 in dict(options["support"])


def test_title_ranking_uses_selected_role_pools_and_excludes_unverified_suffixes() -> None:
    pools = []
    for role, team_id, cerulean, golden, clutch, loser in (
        ("core", 1, 1.0, 4.0, 2.0, 6.0),
        ("mid", 2, 5.0, 1.0, 4.0, 1.0),
        ("support", 3, 2.0, 3.0, 3.0, 2.0),
    ):
        pools.append(
            {
                "role": role,
                "team_id": team_id,
                "prefix_trigger_rates": {"cerulean": cerulean / 10, "golden": golden / 10},
                "prefix_paper_bonus_percent": {"cerulean": cerulean, "golden": golden},
                "suffix_trigger_rates": {
                    "clutch": clutch / 10,
                    "loser": loser / 10,
                    "early_first_blood": 1.0,
                },
                "suffix_paper_bonus_percent": {
                    "clutch": clutch,
                    "loser": loser,
                    "early_first_blood": 99.0,
                },
            }
        )
    evidence = {
        "analysis": {
            "pools": pools,
            "prefixes": [
                {"id": "cerulean", "name": "Cerulean", "label": "蓝色英雄", "bonus_percent": 11},
                {"id": "golden", "name": "Golden", "label": "黄色英雄", "bonus_percent": 8},
            ],
            "suffixes": [
                {"id": "clutch", "name": "the Clutch", "label": "决胜局", "bonus_percent": 16},
                {"id": "loser", "name": "the Underdog", "label": "本局落败", "bonus_percent": 6},
                {
                    "id": "early_first_blood",
                    "name": "the Flayed Twins Acolyte",
                    "label": "号角前一血",
                    "bonus_percent": 9,
                },
            ],
        }
    }

    result = rank_title_for_lineup(
        evidence,
        selected_team_ids=(1, 2, 3),
        role_base_means={"core": 6.0, "mid": 3.0, "support": 1.0},
        excluded_suffix_ids=("early_first_blood",),
        top_k=3,
    )

    assert result["recommended_prefix"]["id"] == "golden"
    assert result["recommended_suffix"]["id"] == "loser"
    assert all(row["id"] != "early_first_blood" for row in result["suffixes"])
    assert result["role_weights"] == {"core": 0.6, "mid": 0.3, "support": 0.1}
    assert result["estimated_pair_bonus_percent"] == 7.1


def test_recommendation_classification_has_clear_conditional_and_refresh_gates() -> None:
    clear = classify_recommendation(
        selected_action_id="core:23",
        selected_row={"mean_delta": 10.0, "cvar10_delta": 3.0, "support_lower": 0.0},
        preferred_action_ids=("core:23", "core:23", "core:23"),
    )
    conditional = classify_recommendation(
        selected_action_id="mid:24",
        selected_row={"mean_delta": 8.0, "cvar10_delta": -2.0, "support_lower": -5.0},
        preferred_action_ids=("mid:24", "refresh", "mid:24"),
    )
    refresh = classify_recommendation(
        selected_action_id="refresh",
        selected_row={"mean_delta": 0.0, "cvar10_delta": 0.0, "support_lower": 0.0},
        preferred_action_ids=("refresh", "refresh", "refresh"),
    )

    assert clear["grade"] == "clear"
    assert conditional["grade"] == "conditional"
    assert conditional["model_agreement"] is False
    assert refresh["grade"] == "refresh"
    assert "未来" in refresh["reason"]


def test_action_selection_rejects_a_downside_trade_that_has_no_average_gain() -> None:
    selected = _preferred_action(
        (
            {"action_id": "refresh", "mean": 100.0, "cvar10": 50.0},
            {"action_id": "core:23", "mean": 99.5, "cvar10": 80.0},
        ),
        mean_retention_epsilon=0.01,
    )

    assert selected == "refresh"
