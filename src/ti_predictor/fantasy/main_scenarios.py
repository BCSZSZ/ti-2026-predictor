"""Deterministic eight-Team Scenario draws for the independent Main period."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from ti_predictor.fantasy.scenarios import (
    ROLE_IDS,
    CommonScenarioSet,
    PoolBuildResult,
    ScenarioDraws,
)
from ti_predictor.hashing import sha256_bytes, sha256_json
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import as_utc
from ti_predictor.tournament.bracket import BracketEngine


def _readonly(values: Any, *, dtype: str | np.dtype) -> np.ndarray:
    result = np.ascontiguousarray(values, dtype=dtype)
    result.setflags(write=False)
    return result


def _array_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values)
    header = f"{canonical.dtype.str}:{','.join(str(value) for value in canonical.shape)}".encode()
    return sha256_bytes(header + b"\0" + canonical.tobytes(order="C"))


def _stream_seed(seed: int, team_id: int, role: str) -> int:
    digest = hashlib.sha256(f"main:{seed}:{team_id}:{role}:predictive-series".encode()).digest()
    return int.from_bytes(digest[:8], "little", signed=False)


@dataclass(frozen=True)
class MainScenarioSet:
    """Main bracket Series counts plus coherent historical-Series draws."""

    policy_id: str
    data_snapshot_sha256: str
    model_sha256: str
    as_of: str
    seed: int
    team_ids: tuple[int, ...]
    scenario_ids: np.ndarray = field(repr=False, compare=False)
    series_counts: np.ndarray = field(repr=False, compare=False)
    draws: tuple[ScenarioDraws, ...] = field(repr=False, compare=False)
    eligibility_mode: Literal["projected", "actual"] = "actual"
    seeding_method: Literal[
        "projected_group_category_then_strength",
        "actual_manifest_order",
    ] = "actual_manifest_order"
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        scenario_ids = _readonly(self.scenario_ids, dtype="<i8")
        series_counts = _readonly(self.series_counts, dtype="<i1")
        draws = tuple(self.draws)
        object.__setattr__(self, "scenario_ids", scenario_ids)
        object.__setattr__(self, "series_counts", series_counts)
        object.__setattr__(self, "draws", draws)
        if self.eligibility_mode not in {"projected", "actual"}:
            raise ValueError("unknown Main eligibility mode")
        expected_candidates = 16 if self.eligibility_mode == "projected" else 8
        if len(self.team_ids) != expected_candidates or len(set(self.team_ids)) != expected_candidates:
            raise ValueError(
                f"{self.eligibility_mode.title()} Main scenarios require "
                f"{expected_candidates} unique stable Team IDs"
            )
        expected_seeding = (
            "projected_group_category_then_strength"
            if self.eligibility_mode == "projected"
            else "actual_manifest_order"
        )
        if self.seeding_method != expected_seeding:
            raise ValueError("Main eligibility mode and seeding method are inconsistent")
        if not np.array_equal(scenario_ids, np.arange(len(scenario_ids), dtype=np.int64)):
            raise ValueError("Main Scenario IDs must be contiguous and zero-based")
        if series_counts.shape != (len(scenario_ids), len(self.team_ids)):
            raise ValueError("Main Series counts must align with Scenario and Team IDs")
        if not len(scenario_ids) or np.any(series_counts < 0) or np.any(series_counts > 6):
            raise ValueError("Main Series counts must be complete values between zero and six")
        active = series_counts > 0
        if not np.all(active.sum(axis=1) == 8):
            raise ValueError("every Main Scenario must contain exactly eight advancing Teams")
        if np.any(series_counts[active] < 2):
            raise ValueError("every Main entrant must play at least two Series")
        if self.eligibility_mode == "actual" and not np.all(active):
            raise ValueError("actual Main scenarios require all eight candidates to enter")
        keys = [(draw.target_team_id, draw.role) for draw in draws]
        if len(keys) != len(set(keys)):
            raise ValueError("Main Scenario draws contain duplicate Team/role identities")
        declared = set(keys)
        expected = [
            (team_id, role) for team_id in self.team_ids for role in ROLE_IDS if (team_id, role) in declared
        ]
        if keys != expected:
            raise ValueError("Main Scenario draws must follow canonical Team/role order")
        if any(not any(key[1] == role for key in keys) for role in ROLE_IDS):
            raise ValueError("Main scenarios require at least one eligible Team for every role")
        max_series = int(series_counts.max())
        if any(draw.block_indexes.shape != (len(scenario_ids), max_series) for draw in draws):
            raise ValueError("Main block draws must align with all Scenario IDs and Series slots")
        for label, value in (
            ("data snapshot", self.data_snapshot_sha256),
            ("Team strength model", self.model_sha256),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"Main scenarios require a lowercase {label} SHA-256")
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "period": "main",
                    "policy_id": self.policy_id,
                    "data_snapshot_sha256": self.data_snapshot_sha256,
                    "model_sha256": self.model_sha256,
                    "as_of": self.as_of,
                    "seed": self.seed,
                    "eligibility_mode": self.eligibility_mode,
                    "seeding_method": self.seeding_method,
                    "team_ids": self.team_ids,
                    "scenario_ids_sha256": _array_sha256(scenario_ids),
                    "series_counts_sha256": _array_sha256(series_counts),
                    "draws": [draw.semantic_hash for draw in draws],
                }
            ),
        )

    def draw_record_for(self, team_id: int, role: str) -> ScenarioDraws:
        for draw in self.draws:
            if draw.target_team_id == team_id and draw.role == role:
                return draw
        raise KeyError(f"no Main Scenario draws for Team {team_id}, role {role}")

    def draws_for(self, team_id: int, role: str) -> np.ndarray:
        return self.draw_record_for(team_id, role).block_indexes


def build_main_scenario_set(
    pool_result: PoolBuildResult,
    *,
    team_ids: tuple[int, ...],
    series_counts: np.ndarray,
    policy_id: str,
    data_snapshot_sha256: str,
    model_sha256: str,
    as_of,
    seed: int,
    eligibility_mode: Literal["projected", "actual"] = "actual",
    seeding_method: Literal[
        "projected_group_category_then_strength",
        "actual_manifest_order",
    ] = "actual_manifest_order",
) -> MainScenarioSet:
    """Build Main draws from an externally verified coherent bracket matrix."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("Main scenarios require an explicit as_of")
    counts = np.asarray(series_counts, dtype=np.int8)
    scenario_count = counts.shape[0] if counts.ndim == 2 else 0
    if counts.shape != (scenario_count, len(team_ids)):
        raise ValueError("Main bracket Series matrix must align with the candidate Team IDs")
    max_series = int(counts.max()) if counts.size else 0
    pool_by_key = pool_result.by_key()
    draws: list[ScenarioDraws] = []
    for team_index, team_id in enumerate(team_ids):
        for role in ROLE_IDS:
            pool = pool_by_key.get((team_id, role))
            if pool is None:
                continue
            rng = np.random.default_rng(_stream_seed(seed, team_id, role))
            indexes = rng.choice(
                len(pool.blocks),
                size=(scenario_count, max_series),
                replace=True,
                p=pool.weights,
            ).astype(np.int32)
            unused = np.arange(max_series)[None, :] >= counts[:, team_index, None]
            indexes[unused] = -1
            draws.append(
                ScenarioDraws(
                    target_team_id=team_id,
                    role=role,
                    pool_sha256=pool.semantic_hash,
                    block_indexes=indexes,
                )
            )
    return MainScenarioSet(
        policy_id=policy_id,
        data_snapshot_sha256=data_snapshot_sha256,
        model_sha256=model_sha256,
        as_of=cutoff.isoformat().replace("+00:00", "Z"),
        seed=seed,
        team_ids=tuple(int(team_id) for team_id in team_ids),
        scenario_ids=np.arange(scenario_count, dtype=np.int64),
        series_counts=counts,
        draws=tuple(draws),
        eligibility_mode=eligibility_mode,
        seeding_method=seeding_method,
    )


def build_main_scenario_set_from_model(
    pool_result: PoolBuildResult,
    *,
    team_ids: tuple[int, ...],
    model: TeamStrengthModel,
    scenario_count: int,
    policy_id: str,
    data_snapshot_sha256: str,
    as_of,
    seed: int,
) -> MainScenarioSet:
    """Sample coherent bracket paths, then build full-Series Fantasy draws."""

    if scenario_count < 1:
        raise ValueError("Main scenario_count must be positive")
    rng = np.random.default_rng(seed)
    engine = BracketEngine(team_ids, model)
    team_index = {team_id: index for index, team_id in enumerate(team_ids)}
    counts = np.zeros((scenario_count, len(team_ids)), dtype=np.int8)
    for scenario_index in range(scenario_count):
        path = engine.sample(rng)
        for left, right in path.participants:
            counts[scenario_index, team_index[left]] += 1
            counts[scenario_index, team_index[right]] += 1
    model_sha256 = sha256_json(model.as_dict())
    return build_main_scenario_set(
        pool_result,
        team_ids=team_ids,
        series_counts=counts,
        policy_id=policy_id,
        data_snapshot_sha256=data_snapshot_sha256,
        model_sha256=model_sha256,
        as_of=as_of,
        seed=seed,
    )


def build_projected_main_scenario_set_from_group(
    pool_result: PoolBuildResult,
    *,
    group_scenarios: CommonScenarioSet,
    model: TeamStrengthModel,
    scenario_count: int,
    policy_id: str,
    data_snapshot_sha256: str,
    as_of,
    seed: int,
) -> MainScenarioSet:
    """Project Main now from all 16 candidates while keeping eight entrants per Scenario."""

    if scenario_count < 1:
        raise ValueError("Main scenario_count must be positive")
    team_ids = tuple(int(team_id) for team_id in group_scenarios.team_ids)
    if len(team_ids) != 16 or len(set(team_ids)) != 16:
        raise ValueError("projected Main scenarios require the 16 Group candidate Teams")
    source_count = len(group_scenarios.scenario_ids)
    if source_count < 1:
        raise ValueError("projected Main scenarios require Group advancement Scenarios")
    rng = np.random.default_rng(seed)
    if scenario_count == source_count:
        selected_group_rows = np.arange(source_count, dtype=np.int64)
    else:
        selected_group_rows = rng.choice(source_count, size=scenario_count, replace=True)
    team_index = {team_id: index for index, team_id in enumerate(team_ids)}
    counts = np.zeros((scenario_count, len(team_ids)), dtype=np.int8)
    for scenario_index, group_row in enumerate(selected_group_rows):
        categories = group_scenarios.group_categories[int(group_row)]
        entrant_indexes = np.flatnonzero(categories < 3)
        if len(entrant_indexes) != 8:
            raise ValueError("each Group Scenario must identify exactly eight Main entrants")
        seeded_ids = tuple(
            team_ids[int(index)]
            for index in sorted(
                entrant_indexes.tolist(),
                key=lambda index: (
                    int(categories[index]),
                    -float(model.strength_rating(team_ids[index])),
                    team_ids[index],
                ),
            )
        )
        path = BracketEngine(seeded_ids, model).sample(rng)
        for left, right in path.participants:
            counts[scenario_index, team_index[left]] += 1
            counts[scenario_index, team_index[right]] += 1
    return build_main_scenario_set(
        pool_result,
        team_ids=team_ids,
        series_counts=counts,
        policy_id=policy_id,
        data_snapshot_sha256=data_snapshot_sha256,
        model_sha256=sha256_json(model.as_dict()),
        as_of=as_of,
        seed=seed,
        eligibility_mode="projected",
        seeding_method="projected_group_category_then_strength",
    )


__all__ = [
    "MainScenarioSet",
    "build_main_scenario_set",
    "build_main_scenario_set_from_model",
    "build_projected_main_scenario_set_from_group",
]
