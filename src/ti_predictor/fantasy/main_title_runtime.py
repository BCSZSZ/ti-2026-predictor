"""Portable, hash-verified Main Title evidence for consumer runtimes."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ti_predictor.fantasy.scenarios import ROLE_IDS, PoolBuildResult
from ti_predictor.fantasy.title import build_title_analysis, parse_title_hero_categories
from ti_predictor.fantasy.title_reporting import _load_match_features, _raw_capture_index
from ti_predictor.forecasting import _available_by_as_of
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.ingest.main_actual import main_evidence_paths
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import as_utc
from ti_predictor.storage import read_parquet_if_exists

MAIN_TITLE_RUNTIME_ARTIFACT_TYPE = "ti2026_main_title_runtime_evidence"
MAIN_TITLE_RUNTIME_SCHEMA_VERSION = 1


def subset_actual_main_pools(
    pool_result: PoolBuildResult,
    *,
    team_ids: tuple[int, ...],
) -> PoolBuildResult:
    """Select the actual Main Team×role pools in stable seed order."""

    expected = [(team_id, role) for team_id in team_ids for role in ROLE_IDS]
    pool_by_key = pool_result.by_key()
    if any(key not in pool_by_key for key in expected):
        raise ValueError("Main Title evidence requires every actual Team/role pool in seed order")
    selected = tuple(pool_by_key[key] for key in expected)
    semantic_hash = sha256_json(
        {
            "period": "main",
            "eligibility_mode": "actual",
            "parent_pool_set_sha256": pool_result.semantic_hash,
            "team_ids": team_ids,
            "pools": [pool.semantic_hash for pool in selected],
        }
    )
    selected_team_ids = set(team_ids)
    audit = {
        **pool_result.audit,
        "period": "main",
        "eligibility_mode": "actual",
        "team_ids": list(team_ids),
        "team_count": len(team_ids),
        "pool_count": len(selected),
        "parent_pool_set_sha256": pool_result.semantic_hash,
        "pool_set_sha256": semantic_hash,
        "pools": [
            row
            for row in pool_result.audit.get("pools", [])
            if int(row.get("target_team_id", -1)) in selected_team_ids
        ],
        "team_role_availability": [
            row
            for row in pool_result.audit.get("team_role_availability", [])
            if int(row.get("target_team_id", -1)) in selected_team_ids
        ],
        "unavailable_team_role_count": 0,
    }
    return PoolBuildResult(pools=selected, audit=audit, semantic_hash=semantic_hash)


def build_main_title_runtime_evidence(
    *,
    as_of: Any,
    pool_result: PoolBuildResult,
    team_ids: tuple[int, ...],
    team_names: Mapping[int, str],
    canonical_rules: Mapping[str, Any],
    scenario_sha256: str,
    hero_source_path: Path,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    """Build the small Title payload embedded in an actual Main solver release."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Main Title runtime evidence requires an explicit UTC as_of")
    if len(team_ids) != 8 or set(team_names) != set(team_ids):
        raise ValueError("Main Title runtime evidence requires the actual eight stable Team IDs")
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    actual_pool = subset_actual_main_pools(pool_result, team_ids=team_ids)

    hero_source = hero_source_path.resolve()
    if not hero_source.is_file():
        raise FileNotFoundError(f"Valve npc_heroes.txt is unavailable: {hero_source}")
    hero_content = hero_source.read_bytes()
    hero_categories = parse_title_hero_categories(hero_content.decode("utf-8", errors="replace"))

    evidence_paths = main_evidence_paths(paths, require=True)
    observations = _available_by_as_of(
        read_parquet_if_exists(evidence_paths.processed / "fantasy_performance_samples.parquet"),
        cutoff,
    )
    matches = _available_by_as_of(
        read_parquet_if_exists(evidence_paths.processed / "matches.parquet"), cutoff
    )
    needed_match_ids = {
        match_id for pool in actual_pool.pools for block in pool.blocks for match_id in block.match_ids
    }
    source_rows = observations.loc[
        observations["match_id"].isin(needed_match_ids), ["match_id", "source_sha256"]
    ].dropna()
    source_counts = source_rows.groupby("match_id")["source_sha256"].nunique()
    if source_counts.empty or source_counts.ne(1).any():
        raise ValueError("each Main Title match must map to one immutable raw source SHA-256")
    source_by_match = {
        int(row.match_id): str(row.source_sha256)
        for row in source_rows.drop_duplicates("match_id").itertuples(index=False)
    }
    if set(source_by_match) != needed_match_ids:
        missing = sorted(needed_match_ids - set(source_by_match))
        raise ValueError(f"Main Title matches lack raw source identities: {missing[:10]}")
    captures = _raw_capture_index(paths, set(source_by_match.values()), as_of=cutoff)
    match_features, raw_audit = _load_match_features(source_by_match, captures)
    series_types = {
        int(row.match_id): int(row.series_type)
        for row in matches.loc[matches["match_id"].isin(needed_match_ids), ["match_id", "series_type"]]
        .dropna()
        .itertuples(index=False)
    }
    title_analysis = build_title_analysis(
        actual_pool,
        match_features,
        series_types,
        hero_categories,
        dict(canonical_rules),
        team_names=dict(team_names),
    )
    bo3_values = [
        float(row["bo3_reaches_game3"])
        for row in title_analysis["pools"]
        if row["bo3_reaches_game3"] is not None
    ]
    if not bo3_values:
        raise ValueError("Main Title Clutch proxy has no complete historical BO3 evidence")

    hero_counts = {
        item["id"]: sum(item["id"] in categories for categories in hero_categories.values())
        for item in canonical_rules["fantasy"]["coach"]["prefixes"]
    }
    hero_metadata_path = hero_source.parents[2] / "metadata.json"
    hero_metadata = (
        json.loads(hero_metadata_path.read_text(encoding="utf-8")) if hero_metadata_path.is_file() else {}
    )
    evidence: dict[str, Any] = {
        "artifact_type": MAIN_TITLE_RUNTIME_ARTIFACT_TYPE,
        "schema_version": MAIN_TITLE_RUNTIME_SCHEMA_VERSION,
        "as_of": cutoff_text,
        "eligibility_mode": "actual",
        "team_ids": list(team_ids),
        "parent_pool_set_sha256": pool_result.semantic_hash,
        "actual_pool_set_sha256": actual_pool.semantic_hash,
        "scenario_sha256": scenario_sha256,
        "hero_source": {
            "resource": "scripts/npc/npc_heroes.txt",
            "sha256": sha256_file(hero_source),
            "bytes": len(hero_content),
            "client_build": hero_metadata.get("client_build"),
            "mapped_heroes": len(hero_categories),
            "category_hero_counts": hero_counts,
        },
        "raw_detail_audit": raw_audit,
        "diagnostics": {"mean_bo3_reaches_game3": sum(bo3_values) / len(bo3_values)},
        "analysis": title_analysis,
        "warnings": [
            "Main Title Clutch uses a historical BO3 proxy and does not separately model "
            "the possible BO5 grand final.",
            "Title paper bonuses are not jointly optimized with the five-slot terminal solver.",
        ],
    }
    evidence["evidence_sha256"] = sha256_json(evidence)
    return evidence


def validate_main_title_runtime_evidence(
    payload: Mapping[str, Any],
    *,
    as_of: str,
    pool_result: PoolBuildResult,
    team_ids: tuple[int, ...],
    scenario_sha256: str,
) -> dict[str, Any]:
    """Validate a portable Title payload against its containing Main release."""

    evidence = dict(payload)
    claimed = evidence.pop("evidence_sha256", None)
    if not isinstance(claimed, str) or claimed != sha256_json(evidence):
        raise ValueError("Main Title runtime evidence hash is invalid")
    evidence["evidence_sha256"] = claimed
    expected_actual_pool = subset_actual_main_pools(pool_result, team_ids=team_ids)
    expected = {
        "artifact_type": MAIN_TITLE_RUNTIME_ARTIFACT_TYPE,
        "schema_version": MAIN_TITLE_RUNTIME_SCHEMA_VERSION,
        "as_of": as_of,
        "eligibility_mode": "actual",
        "team_ids": list(team_ids),
        "parent_pool_set_sha256": pool_result.semantic_hash,
        "actual_pool_set_sha256": expected_actual_pool.semantic_hash,
        "scenario_sha256": scenario_sha256,
    }
    if any(evidence.get(key) != value for key, value in expected.items()):
        raise ValueError("Main Title runtime evidence does not match the Main release")
    analysis = evidence.get("analysis")
    if not isinstance(analysis, Mapping):
        raise ValueError("Main Title runtime evidence has no analysis")
    pools = analysis.get("pools")
    if not isinstance(pools, Sequence):
        raise ValueError("Main Title runtime evidence has no Team×role pools")
    pool_keys = {
        (int(row["team_id"]), str(row["role"]))
        for row in pools
        if isinstance(row, Mapping) and "team_id" in row and "role" in row
    }
    expected_pool_keys = {(team_id, role) for team_id in team_ids for role in ROLE_IDS}
    if pool_keys != expected_pool_keys:
        raise ValueError("Main Title runtime evidence Team×role pools are incomplete")
    if not isinstance(analysis.get("prefixes"), Sequence) or not isinstance(
        analysis.get("suffixes"), Sequence
    ):
        raise ValueError("Main Title runtime evidence rankings are incomplete")
    warnings = evidence.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise ValueError("Main Title runtime evidence warnings are invalid")
    return evidence


__all__ = [
    "MAIN_TITLE_RUNTIME_ARTIFACT_TYPE",
    "MAIN_TITLE_RUNTIME_SCHEMA_VERSION",
    "build_main_title_runtime_evidence",
    "subset_actual_main_pools",
    "validate_main_title_runtime_evidence",
]
