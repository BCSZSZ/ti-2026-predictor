"""Projected-derived eight-Team panels for isolated Main Roll research.

An outer row supplies only a projected advancing roster and proxy seed order.  Separate
inner Main paths choose the future Team lineup and evaluate it, preventing both an
across-roster fixed lineup (``max E``) and per-realization hindsight selection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from itertools import product
from typing import Any

import numpy as np

from ti_predictor.fantasy.main_roll_research_contract import ProjectedRosterValidationSpec
from ti_predictor.fantasy.main_roll_research_simulator import (
    MainResearchSimulationError,
    TerminalEvaluation,
)
from ti_predictor.fantasy.main_roll_research_terminal import VectorizedMainResearchTerminal
from ti_predictor.fantasy.main_scenarios import MainScenarioSet, build_main_scenario_set
from ti_predictor.fantasy.roll import BannerState
from ti_predictor.fantasy.scenarios import ROLE_IDS, CommonScenarioSet, PoolBuildResult
from ti_predictor.fantasy.valuation import lower_tail_cvar
from ti_predictor.hashing import sha256_bytes, sha256_json
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.tournament.bracket import BracketEngine

INNER_SELECTION = 0
INNER_EVALUATION = 1


class ProjectedRosterResearchError(ValueError):
    """Projected-derived roster evidence crossed or lost a frozen boundary."""


def _array_sha256(values: np.ndarray) -> str:
    canonical = np.ascontiguousarray(values)
    header = f"{canonical.dtype.str}:{','.join(str(value) for value in canonical.shape)}".encode()
    return sha256_bytes(header + b"\0" + canonical.tobytes(order="C"))


def _seed_from(*values: Any) -> int:
    digest = hashlib.sha256(":".join(str(value) for value in values).encode()).digest()
    return int.from_bytes(digest[:8], "little", signed=False)


@dataclass(frozen=True)
class ProjectedRosterRecord:
    source_group_scenario_id: int
    entrant_team_ids: tuple[int, ...]
    projected_seed_order: tuple[int, ...]
    entrant_group_categories: tuple[int, ...]
    fold_id: int
    empirical_weight: float
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        entrants = tuple(int(value) for value in self.entrant_team_ids)
        seeds = tuple(int(value) for value in self.projected_seed_order)
        categories = tuple(int(value) for value in self.entrant_group_categories)
        object.__setattr__(self, "entrant_team_ids", entrants)
        object.__setattr__(self, "projected_seed_order", seeds)
        object.__setattr__(self, "entrant_group_categories", categories)
        if len(entrants) != 8 or len(set(entrants)) != 8 or set(seeds) != set(entrants):
            raise ProjectedRosterResearchError("a projected-derived roster requires eight Teams")
        if len(categories) != 8 or any(value not in {0, 1, 2} for value in categories):
            raise ProjectedRosterResearchError("projected entrant categories are invalid")
        if self.source_group_scenario_id < 0 or self.fold_id < 0:
            raise ProjectedRosterResearchError("projected roster identifiers must be non-negative")
        if not 0.0 < self.empirical_weight <= 1.0:
            raise ProjectedRosterResearchError("projected roster weight must be positive")
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "scenario_kind": "projected-derived-eight-team-roster",
                    "source_group_scenario_id": self.source_group_scenario_id,
                    "entrant_team_ids": entrants,
                    "projected_seed_order": seeds,
                    "entrant_group_categories": categories,
                    "fold_id": self.fold_id,
                    "empirical_weight": self.empirical_weight,
                }
            ),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "scenario_kind": "projected-derived-eight-team-roster",
            "source_group_scenario_id": self.source_group_scenario_id,
            "entrant_team_ids": list(self.entrant_team_ids),
            "projected_seed_order": list(self.projected_seed_order),
            "entrant_group_categories": list(self.entrant_group_categories),
            "fold_id": self.fold_id,
            "empirical_weight": self.empirical_weight,
            "semantic_hash": self.semantic_hash,
        }


def derive_projected_roster_records(
    group_scenarios: CommonScenarioSet,
    main_scenarios: MainScenarioSet,
    model: TeamStrengthModel,
    specification: ProjectedRosterValidationSpec,
) -> tuple[ProjectedRosterRecord, ...]:
    """Derive all outer rosters without changing the frozen 1/N empirical measure."""

    if main_scenarios.eligibility_mode != "projected":
        raise ProjectedRosterResearchError("projected-derived validation requires projected Main")
    if group_scenarios.team_ids != main_scenarios.team_ids:
        raise ProjectedRosterResearchError("Group and Main candidate Team identities differ")
    if len(group_scenarios.scenario_ids) != specification.outer_scenario_count:
        raise ProjectedRosterResearchError("frozen Group outer Scenario count changed")
    if not np.array_equal(group_scenarios.scenario_ids, main_scenarios.scenario_ids):
        raise ProjectedRosterResearchError("Group and Main Scenario IDs are not aligned")
    expected_active = group_scenarios.group_categories < 3
    if not np.array_equal(expected_active, main_scenarios.series_counts > 0):
        raise ProjectedRosterResearchError("Main entrants differ from frozen Group advancement")

    team_ids = group_scenarios.team_ids
    identities: list[dict[str, Any]] = []
    for source_id, categories in zip(
        group_scenarios.scenario_ids,
        group_scenarios.group_categories,
        strict=True,
    ):
        entrant_indexes = np.flatnonzero(categories < 3)
        entrants = tuple(team_ids[int(index)] for index in entrant_indexes)
        seeds = tuple(
            team_ids[int(index)]
            for index in sorted(
                entrant_indexes.tolist(),
                key=lambda index: (
                    int(categories[index]),
                    -float(model.strength_rating(team_ids[index])),
                    int(team_ids[index]),
                ),
            )
        )
        identities.append(
            {
                "source_group_scenario_id": int(source_id),
                "entrant_team_ids": entrants,
                "projected_seed_order": seeds,
                "entrant_group_categories": tuple(
                    int(categories[team_ids.index(team_id)]) for team_id in seeds
                ),
            }
        )

    ranked = sorted(
        range(len(identities)),
        key=lambda index: sha256_json(
            {
                "fold_salt": specification.fold_salt,
                **identities[index],
            }
        ),
    )
    fold_by_index = {
        original_index: rank % specification.fold_count for rank, original_index in enumerate(ranked)
    }
    weight = 1.0 / len(identities)
    return tuple(
        ProjectedRosterRecord(
            **identity,
            fold_id=fold_by_index[index],
            empirical_weight=weight,
        )
        for index, identity in enumerate(identities)
    )


@dataclass(frozen=True)
class ProjectedRosterPanel:
    source_group_scenario_sha256: str
    source_main_scenario_sha256: str
    source_pool_sha256: str
    source_model_sha256: str
    records: tuple[ProjectedRosterRecord, ...]
    scenarios: MainScenarioSet
    outer_scenario_ids: np.ndarray = field(repr=False, compare=False)
    fold_ids: np.ndarray = field(repr=False, compare=False)
    inner_phases: np.ndarray = field(repr=False, compare=False)
    inner_replicate_ids: np.ndarray = field(repr=False, compare=False)
    inner_scenarios_per_phase: int
    semantic_hash: str = field(init=False)

    def __post_init__(self) -> None:
        records = tuple(self.records)
        outer = np.ascontiguousarray(self.outer_scenario_ids, dtype="<i8")
        folds = np.ascontiguousarray(self.fold_ids, dtype="<i2")
        phases = np.ascontiguousarray(self.inner_phases, dtype="<i1")
        replicates = np.ascontiguousarray(self.inner_replicate_ids, dtype="<i2")
        for values in (outer, folds, phases, replicates):
            values.setflags(write=False)
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "outer_scenario_ids", outer)
        object.__setattr__(self, "fold_ids", folds)
        object.__setattr__(self, "inner_phases", phases)
        object.__setattr__(self, "inner_replicate_ids", replicates)
        expected = len(self.scenarios.scenario_ids)
        if not records or any(len(values) != expected for values in (outer, folds, phases, replicates)):
            raise ProjectedRosterResearchError("projected roster panel arrays do not align")
        if set(np.unique(phases).tolist()) != {INNER_SELECTION, INNER_EVALUATION}:
            raise ProjectedRosterResearchError("projected roster panel requires two independent phases")
        for record in records:
            mask = outer == record.source_group_scenario_id
            if int(mask.sum()) != 2 * self.inner_scenarios_per_phase:
                raise ProjectedRosterResearchError("each outer roster has an incomplete inner panel")
            for phase in (INNER_SELECTION, INNER_EVALUATION):
                selected = mask & (phases == phase)
                if set(replicates[selected].tolist()) != set(range(self.inner_scenarios_per_phase)):
                    raise ProjectedRosterResearchError("inner replicate IDs are incomplete")
        object.__setattr__(
            self,
            "semantic_hash",
            sha256_json(
                {
                    "scenario_kind": "projected-derived-eight-team-roster-panel",
                    "source_group_scenario_sha256": self.source_group_scenario_sha256,
                    "source_main_scenario_sha256": self.source_main_scenario_sha256,
                    "source_pool_sha256": self.source_pool_sha256,
                    "source_model_sha256": self.source_model_sha256,
                    "records": [record.semantic_hash for record in records],
                    "inner_scenarios_per_phase": self.inner_scenarios_per_phase,
                    "scenarios_sha256": self.scenarios.semantic_hash,
                    "outer_ids_sha256": _array_sha256(outer),
                    "fold_ids_sha256": _array_sha256(folds),
                    "inner_phases_sha256": _array_sha256(phases),
                    "inner_replicates_sha256": _array_sha256(replicates),
                }
            ),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "scenario_kind": "projected-derived-eight-team-roster-panel",
            "eligibility_mode": "projected",
            "source_group_scenario_sha256": self.source_group_scenario_sha256,
            "source_main_scenario_sha256": self.source_main_scenario_sha256,
            "source_pool_sha256": self.source_pool_sha256,
            "source_model_sha256": self.source_model_sha256,
            "outer_weighting": "empirical-row-equal",
            "outer_record_count": len(self.records),
            "inner_scenarios_per_phase": self.inner_scenarios_per_phase,
            "inner_total_scenario_count": len(self.scenarios.scenario_ids),
            "selection_phase": "independent-inner-selection",
            "evaluation_phase": "independent-inner-evaluation",
            "fold_ids": sorted(set(int(value) for value in self.fold_ids)),
            "records": [record.payload() for record in self.records],
            "inner_main_scenario_sha256": self.scenarios.semantic_hash,
            "panel_sha256": self.semantic_hash,
        }


def build_projected_roster_panel(
    pool_result: PoolBuildResult,
    group_scenarios: CommonScenarioSet,
    main_scenarios: MainScenarioSet,
    model: TeamStrengthModel,
    specification: ProjectedRosterValidationSpec,
    *,
    selected_fold_ids: tuple[int, ...],
    inner_scenarios_per_phase: int | None = None,
) -> ProjectedRosterPanel:
    records = derive_projected_roster_records(
        group_scenarios,
        main_scenarios,
        model,
        specification,
    )
    selected_folds = set(int(value) for value in selected_fold_ids)
    if not selected_folds or not selected_folds.issubset(set(range(specification.fold_count))):
        raise ProjectedRosterResearchError("projected roster panel selected unknown folds")
    selected_records = tuple(record for record in records if record.fold_id in selected_folds)
    count = inner_scenarios_per_phase or specification.inner_scenarios_per_phase
    if count not in specification.convergence_inner_scenario_counts:
        raise ProjectedRosterResearchError("inner Scenario count is outside the frozen convergence set")

    team_index = {team_id: index for index, team_id in enumerate(main_scenarios.team_ids)}
    series_rows: list[np.ndarray] = []
    outer_ids: list[int] = []
    fold_ids: list[int] = []
    phases: list[int] = []
    replicates: list[int] = []
    for record in selected_records:
        engine = BracketEngine(record.projected_seed_order, model)
        for phase in (INNER_SELECTION, INNER_EVALUATION):
            for replicate in range(count):
                rng = np.random.default_rng(
                    _seed_from(
                        specification.inner_seed,
                        record.source_group_scenario_id,
                        phase,
                        replicate,
                        "projected-derived-inner-main",
                    )
                )
                path = engine.sample(rng)
                row = np.zeros(len(main_scenarios.team_ids), dtype=np.int8)
                for left, right in path.participants:
                    row[team_index[left]] += 1
                    row[team_index[right]] += 1
                series_rows.append(row)
                outer_ids.append(record.source_group_scenario_id)
                fold_ids.append(record.fold_id)
                phases.append(phase)
                replicates.append(replicate)

    data_snapshot_sha256 = sha256_json(
        {
            "scenario_kind": "projected-derived-eight-team-roster-panel",
            "source_group_scenario_sha256": group_scenarios.semantic_hash,
            "source_main_scenario_sha256": main_scenarios.semantic_hash,
            "source_pool_sha256": pool_result.semantic_hash,
            "source_model_sha256": main_scenarios.model_sha256,
            "selected_folds": sorted(selected_folds),
            "inner_scenarios_per_phase": count,
            "inner_seed": specification.inner_seed,
        }
    )
    scenarios = build_main_scenario_set(
        pool_result,
        team_ids=main_scenarios.team_ids,
        series_counts=np.stack(series_rows),
        policy_id="ti2026-main-roll-projected-derived-roster-panel-v1",
        data_snapshot_sha256=data_snapshot_sha256,
        model_sha256=main_scenarios.model_sha256,
        as_of=main_scenarios.as_of,
        seed=specification.inner_seed,
        eligibility_mode="projected",
        seeding_method="projected_group_category_then_strength",
    )
    return ProjectedRosterPanel(
        source_group_scenario_sha256=group_scenarios.semantic_hash,
        source_main_scenario_sha256=main_scenarios.semantic_hash,
        source_pool_sha256=pool_result.semantic_hash,
        source_model_sha256=main_scenarios.model_sha256,
        records=selected_records,
        scenarios=scenarios,
        outer_scenario_ids=np.asarray(outer_ids),
        fold_ids=np.asarray(fold_ids),
        inner_phases=np.asarray(phases),
        inner_replicate_ids=np.asarray(replicates),
        inner_scenarios_per_phase=count,
    )


class ProjectedRosterConditionalTerminal:
    """Evaluate ``E[max Team | projected roster]`` on independent inner outcomes."""

    def __init__(
        self,
        terminal: VectorizedMainResearchTerminal,
        panel: ProjectedRosterPanel,
        *,
        cvar_alpha: float,
    ) -> None:
        if terminal.scenario_set is not panel.scenarios:
            raise ProjectedRosterResearchError("conditional terminal and panel Scenarios differ")
        if not 0.0 < cvar_alpha <= 1.0:
            raise ProjectedRosterResearchError("conditional terminal CVaR alpha is invalid")
        self.terminal = terminal
        self.panel = panel
        self.cvar_alpha = cvar_alpha
        self._cache: dict[tuple[BannerState, ...], TerminalEvaluation] = {}
        selection_columns: list[np.ndarray] = []
        evaluation_columns: list[np.ndarray] = []
        for record in panel.records:
            outer = panel.outer_scenario_ids == record.source_group_scenario_id
            selected = np.flatnonzero(outer & (panel.inner_phases == INNER_SELECTION))
            evaluated = np.flatnonzero(outer & (panel.inner_phases == INNER_EVALUATION))
            if (
                len(selected) != panel.inner_scenarios_per_phase
                or len(evaluated) != panel.inner_scenarios_per_phase
            ):
                raise ProjectedRosterResearchError(
                    "projected roster inner phases do not match the frozen replicate count"
                )
            selection_columns.append(selected)
            evaluation_columns.append(evaluated)
        self._selection_columns = np.stack(selection_columns)
        self._evaluation_columns = np.stack(evaluation_columns)
        self._selection_columns.setflags(write=False)
        self._evaluation_columns.setflags(write=False)
        self._entrant_ids = np.asarray(
            [record.entrant_team_ids for record in panel.records],
            dtype=np.int64,
        )
        entrant_counts = {len(record.entrant_team_ids) for record in panel.records}
        if len(entrant_counts) != 1:
            raise ProjectedRosterResearchError("projected roster records must have one fixed entrant count")
        entrant_count = entrant_counts.pop()
        self._lineup_offsets = np.asarray(
            tuple(product(range(entrant_count), repeat=len(ROLE_IDS))),
            dtype=np.int64,
        )
        self._candidate_index_cache: dict[tuple[str, tuple[int, ...]], np.ndarray] = {}
        self._entrant_ids.setflags(write=False)
        self._lineup_offsets.setflags(write=False)

    def clear_evaluation_cache(self) -> None:
        """Release per-state values while retaining the immutable roster index."""

        self._cache.clear()
        self.terminal.clear_evaluation_cache()

    def _select_lineup(
        self,
        matrices: dict[str, Any],
        record: ProjectedRosterRecord,
        selection_columns: np.ndarray,
    ) -> tuple[int, int, int]:
        candidate_indexes: list[list[int]] = []
        for role in ROLE_IDS:
            matrix = matrices[role]
            indexes = [
                matrix.team_ids.index(team_id)
                for team_id in record.entrant_team_ids
                if team_id in matrix.team_ids
            ]
            if not indexes:
                raise MainResearchSimulationError(
                    f"projected roster has no available Fantasy Team for {role}"
                )
            means = matrix.outcomes[np.ix_(indexes, selection_columns)].mean(axis=1)
            maximum = float(means.max())
            candidate_indexes.append([indexes[offset] for offset in np.flatnonzero(means >= maximum - 1e-12)])
        best: tuple[tuple[float, tuple[int, int, int]], tuple[int, int, int]] | None = None
        for indexes in product(*candidate_indexes):
            outcomes = sum(
                (
                    matrices[role].outcomes[index, selection_columns]
                    for role, index in zip(ROLE_IDS, indexes, strict=True)
                ),
                start=np.zeros(len(selection_columns), dtype=float),
            )
            team_ids = tuple(
                int(matrices[role].team_ids[index]) for role, index in zip(ROLE_IDS, indexes, strict=True)
            )
            key = (-lower_tail_cvar(outcomes, self.cvar_alpha), team_ids)
            if best is None or key < best[0]:
                best = (key, team_ids)  # type: ignore[assignment]
        if best is None:
            raise MainResearchSimulationError("no roster-conditional Team lineup is available")
        return best[1]

    def _candidate_indexes(self, role: str, matrix: Any) -> np.ndarray:
        key = (role, tuple(int(team_id) for team_id in matrix.team_ids))
        if key in self._candidate_index_cache:
            return self._candidate_index_cache[key]
        team_index = {team_id: index for index, team_id in enumerate(key[1])}
        indexes = np.asarray(
            [[team_index.get(int(team_id), -1) for team_id in record] for record in self._entrant_ids],
            dtype=np.int64,
        )
        if np.any(~(indexes >= 0).any(axis=1)):
            raise MainResearchSimulationError(f"projected roster has no available Fantasy Team for {role}")
        indexes.setflags(write=False)
        self._candidate_index_cache[key] = indexes
        return indexes

    @staticmethod
    def _lower_tail_cvar_rows(values: np.ndarray, alpha: float) -> np.ndarray:
        outcome_count = values.shape[-1]
        mass = alpha * outcome_count
        whole = int(np.floor(mass))
        fraction = mass - whole
        if whole == outcome_count:
            return values.mean(axis=-1)
        boundary_index = whole if fraction > 0.0 else whole - 1
        partitioned = np.partition(values, boundary_index, axis=-1)
        total = partitioned[..., :whole].sum(axis=-1)
        if fraction > 0.0:
            total += fraction * partitioned[..., whole]
        return total / mass

    def _select_lineups(self, matrices: dict[str, Any]) -> tuple[tuple[int, int, int], ...]:
        """Batch unique winners and exact CVaR/Team-ID tie resolution."""

        record_count = len(self.panel.records)
        lineups = np.zeros((record_count, len(ROLE_IDS)), dtype=np.int64)
        candidate_indexes: dict[str, np.ndarray] = {}
        winner_masks: dict[str, np.ndarray] = {}
        tied = np.zeros(record_count, dtype=bool)
        for role in ROLE_IDS:
            indexes = self._candidate_indexes(role, matrices[role])
            candidate_indexes[role] = indexes
            available = indexes >= 0
            safe_indexes = np.maximum(indexes, 0)
            means = (
                matrices[role]
                .outcomes[
                    safe_indexes[:, :, None],
                    self._selection_columns[:, None, :],
                ]
                .mean(axis=2)
            )
            means[~available] = -np.inf
            maxima = means.max(axis=1, keepdims=True)
            winners = means >= maxima - 1e-12
            winner_masks[role] = winners
            tied |= winners.sum(axis=1) != 1
            offsets = np.argmax(winners, axis=1)
            lineups[:, ROLE_IDS.index(role)] = self._entrant_ids[np.arange(record_count), offsets]

        tied_rows = np.flatnonzero(tied)
        if len(tied_rows):
            combination_count = len(self._lineup_offsets)
            valid = np.ones((len(tied_rows), combination_count), dtype=bool)
            values = np.zeros(
                (
                    len(tied_rows),
                    combination_count,
                    self.panel.inner_scenarios_per_phase,
                ),
                dtype=float,
            )
            team_ids = np.empty(
                (len(tied_rows), combination_count, len(ROLE_IDS)),
                dtype=np.int64,
            )
            for role_offset, role in enumerate(ROLE_IDS):
                offsets = self._lineup_offsets[:, role_offset]
                valid &= winner_masks[role][tied_rows][:, offsets]
                indexes = np.maximum(candidate_indexes[role][tied_rows][:, offsets], 0)
                values += matrices[role].outcomes[
                    indexes[:, :, None],
                    self._selection_columns[tied_rows][:, None, :],
                ]
                team_ids[:, :, role_offset] = self._entrant_ids[tied_rows][:, offsets]
            cvars = self._lower_tail_cvar_rows(values, self.cvar_alpha)
            cvars[~valid] = -np.inf
            for local_row, row in enumerate(tied_rows):
                maximum = float(cvars[local_row].max())
                candidates = np.flatnonzero(cvars[local_row] == maximum)
                selected = min(
                    candidates,
                    key=lambda index: tuple(int(value) for value in team_ids[local_row, index]),
                )
                lineups[row] = team_ids[local_row, selected]
        return tuple(tuple(int(team_id) for team_id in row) for row in lineups)

    def evaluate(self, banners: tuple[BannerState, ...]) -> TerminalEvaluation:
        banners = tuple(banners)
        if banners in self._cache:
            return self._cache[banners]
        banner_by_role = {banner.role: banner for banner in banners}
        if tuple(banner_by_role) != ROLE_IDS:
            raise MainResearchSimulationError("conditional terminal Banners are out of role order")
        matrices = {role: self.terminal.banner(banner_by_role[role]) for role in ROLE_IDS}
        lineups = self._select_lineups(matrices)
        roster_outcomes = np.zeros(self._evaluation_columns.shape, dtype=float)
        for role_offset, role in enumerate(ROLE_IDS):
            team_index = {int(team_id): index for index, team_id in enumerate(matrices[role].team_ids)}
            selected_indexes = np.asarray(
                [team_index[lineup[role_offset]] for lineup in lineups],
                dtype=np.int64,
            )
            roster_outcomes += matrices[role].outcomes[
                selected_indexes[:, None],
                self._evaluation_columns,
            ]
        replicate_count = self.panel.inner_scenarios_per_phase
        cohort_ids = tuple(
            int(value)
            for value in np.repeat(
                [record.fold_id for record in self.panel.records],
                replicate_count,
            )
        )
        roster_ids = tuple(
            int(value)
            for value in np.repeat(
                [record.source_group_scenario_id for record in self.panel.records],
                replicate_count,
            )
        )
        selection_plan = [
            {
                "source_group_scenario_id": record.source_group_scenario_id,
                "selected_team_ids": lineup,
            }
            for record, lineup in zip(self.panel.records, lineups, strict=True)
        ]
        result = TerminalEvaluation(
            outcomes=roster_outcomes.reshape(-1),
            selected_team_ids=(),
            selection_mode="projected-roster-conditional",
            selection_plan_sha256=sha256_json(selection_plan),
            cohort_ids=cohort_ids,
            roster_ids=roster_ids,
        )
        self._cache[banners] = result
        return result


__all__ = [
    "INNER_EVALUATION",
    "INNER_SELECTION",
    "ProjectedRosterConditionalTerminal",
    "ProjectedRosterPanel",
    "ProjectedRosterRecord",
    "ProjectedRosterResearchError",
    "build_projected_roster_panel",
    "derive_projected_roster_records",
]
