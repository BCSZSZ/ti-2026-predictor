from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from ti_predictor.models.policy import SwissSimulationPolicy
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import (
    Recommendation,
    StrategyProfile,
    SwissFormat,
    TournamentManifest,
    as_utc,
)
from ti_predictor.tournament.swiss import (
    SeriesProbabilityMode,
    SwissEngine,
    adjust_strength_probability,
    bo3_probability,
    inverse_bo3_probability,
)

CATEGORY_IDS = (
    "four_zero",
    "four_one",
    "elimination_winner",
    "elimination_loser",
    "one_four",
    "zero_four",
)
CATEGORY_CAPACITIES = np.asarray([1, 2, 5, 5, 2, 1], dtype=int)
SLOT_CATEGORIES = np.repeat(np.arange(len(CATEGORY_IDS)), CATEGORY_CAPACITIES)


@dataclass
class GroupSimulation:
    team_ids: np.ndarray
    outcomes: np.ndarray
    probabilities: np.ndarray
    scenario: str
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.outcomes.ndim != 2 or self.outcomes.shape[1] != len(self.team_ids):
            raise ValueError("invalid group simulation shape")
        for category, expected in enumerate(CATEGORY_CAPACITIES):
            counts = (self.outcomes == category).sum(axis=1)
            if not np.all(counts == expected):
                raise ValueError(f"category {CATEGORY_IDS[category]} violates capacity {expected}")


class GroupSimulator:
    """Joint capacity-preserving projection while Valve pairing details remain incomplete."""

    def __init__(self, model: TeamStrengthModel, manifest: TournamentManifest) -> None:
        if len(manifest.teams) != 16:
            raise ValueError("TI group forecast requires exactly sixteen teams")
        self.model = model
        self.manifest = manifest
        self.team_ids = np.asarray([team.team_id for team in manifest.teams], dtype=np.int64)
        self.team_names = {team.team_id: team.name for team in manifest.teams}

    def simulate(
        self,
        *,
        samples: int = 20000,
        seed: int = 20260813,
        scenario: str = "balanced_pairing",
    ) -> GroupSimulation:
        if samples <= 0:
            raise ValueError("samples must be positive")
        settings = {
            "strength_seeded": (0.0, 245.0),
            "balanced_pairing": (0.18, 310.0),
            "high_variance": (0.08, 410.0),
        }
        if scenario not in settings:
            raise ValueError(f"unknown group pairing scenario: {scenario}")
        compression, noise_scale = settings[scenario]
        ratings = np.asarray([self.model.strength_rating(int(team_id)) for team_id in self.team_ids])
        ratings = ratings.mean() + (ratings - ratings.mean()) * (1.0 - compression)
        rng = np.random.default_rng(seed)
        # A Gumbel random-utility draw creates one joint ordering per tournament.
        utilities = ratings[None, :] + rng.gumbel(0.0, noise_scale, size=(samples, len(ratings)))
        order = np.argsort(-utilities, axis=1, kind="stable")
        outcomes = np.empty_like(order, dtype=np.int8)
        outcomes[np.arange(samples)[:, None], order] = SLOT_CATEGORIES[None, :]
        probabilities = np.stack([(outcomes == index).mean(axis=0) for index in range(6)], axis=1)
        result = GroupSimulation(
            team_ids=self.team_ids.copy(),
            outcomes=outcomes,
            probabilities=probabilities,
            scenario=scenario,
            seed=seed,
        )
        result.validate()
        return result

    @staticmethod
    def _initial_assignment(probabilities: np.ndarray) -> np.ndarray:
        costs = -probabilities[:, SLOT_CATEGORIES]
        rows, slots = linear_sum_assignment(costs)
        assignment = np.empty(probabilities.shape[0], dtype=np.int8)
        assignment[rows] = SLOT_CATEGORIES[slots]
        return assignment

    @staticmethod
    def _score_distribution(
        outcomes: np.ndarray,
        assignment: np.ndarray,
        cumulative_points: np.ndarray,
    ) -> np.ndarray:
        correct = (outcomes == assignment[None, :]).sum(axis=1)
        return cumulative_points[correct]

    def recommend(
        self,
        simulation: GroupSimulation,
        *,
        profile: StrategyProfile,
        cumulative_points: list[int],
        as_of,
        search_steps: int = 1800,
    ) -> Recommendation:
        points = np.asarray(cumulative_points, dtype=float)
        rng = np.random.default_rng(simulation.seed + list(StrategyProfile).index(profile) * 10007)
        initial = self._initial_assignment(simulation.probabilities)
        baseline_scores = self._score_distribution(simulation.outcomes, initial, points)
        expected_floor = float(baseline_scores.mean()) * 0.85
        top10_threshold = float(np.quantile(baseline_scores, 0.90, method="higher"))
        top100_threshold = float(np.quantile(baseline_scores, 0.995, method="higher"))

        def objective(assignment: np.ndarray) -> tuple[float, float, np.ndarray]:
            scores = self._score_distribution(simulation.outcomes, assignment, points)
            expected = float(scores.mean())
            if profile == StrategyProfile.EXPECTED_POINTS:
                value = expected
            elif profile == StrategyProfile.TOP_10:
                value = float((scores >= top10_threshold).mean()) * 10000.0 + expected / 10000.0
            else:
                if expected < expected_floor:
                    value = -1e12 + expected
                else:
                    tail = scores[scores >= top100_threshold]
                    cvar = float(tail.mean()) if len(tail) else 0.0
                    value = cvar + float((scores >= top100_threshold).mean()) * 1000.0
            return value, expected, scores

        best = initial.copy()
        best_value, best_expected, best_scores = objective(best)
        current = best.copy()
        current_value = best_value
        for step in range(search_steps):
            candidate = current.copy()
            left, right = rng.choice(len(candidate), size=2, replace=False)
            candidate[left], candidate[right] = candidate[right], candidate[left]
            value, expected, scores = objective(candidate)
            temperature = max(0.001, 1.0 - step / search_steps)
            accept = value >= current_value or rng.random() < np.exp(
                np.clip((value - current_value) / max(1.0, abs(current_value)) / temperature, -30, 0)
            )
            if accept:
                current, current_value = candidate, value
            if value > best_value:
                best, best_value, best_expected, best_scores = candidate, value, expected, scores

        selections: dict[str, list[dict[str, Any]]] = {}
        for category_index, category_id in enumerate(CATEGORY_IDS):
            team_indexes = np.flatnonzero(best == category_index)
            selections[category_id] = [
                {
                    "team_id": int(simulation.team_ids[index]),
                    "team": self.team_names[int(simulation.team_ids[index])],
                    "category_probability": round(float(simulation.probabilities[index, category_index]), 6),
                    "category_probability_percent": round(
                        float(simulation.probabilities[index, category_index]) * 100.0,
                        2,
                    ),
                }
                for index in team_indexes
            ]

        correct_counts = (simulation.outcomes == best[None, :]).sum(axis=1)
        expected_correct_count = float(correct_counts.mean())
        marginal_expected_count = float(
            sum(
                simulation.probabilities[team_index, int(category_index)]
                for team_index, category_index in enumerate(best)
            )
        )
        if not np.isclose(expected_correct_count, marginal_expected_count, atol=1e-12):
            raise AssertionError("joint and marginal expected correct counts disagree")
        values, frequencies = np.unique(correct_counts, return_counts=True)
        correct_distribution = [
            {
                "correct_count": int(value),
                "probability": round(float(frequency / len(correct_counts)), 6),
                "probability_percent": round(float(frequency / len(correct_counts)) * 100.0, 2),
            }
            for value, frequency in zip(values, frequencies, strict=True)
        ]
        standard_error = (
            float(correct_counts.std(ddof=1) / np.sqrt(len(correct_counts)))
            if len(correct_counts) > 1
            else 0.0
        )
        confidence_interval = (
            max(0.0, expected_correct_count - 1.96 * standard_error),
            min(float(len(best)), expected_correct_count + 1.96 * standard_error),
        )

        if simulation.metadata.get("engine") == "official_swiss_v1":
            warnings = [
                "首轮使用 Valve 官方对阵；初始 A/B 组由官方 .A/.B 节点与组内规则派生。",
                "多个合法后续配对及淘汰轮选对手仍由已声明情景处理，不代表赛事方唯一决定。",
                "深层平均时长/掷币 tiebreak 使用对称时长与固定种子代理，属于显式情景不确定性。",
            ]
            if simulation.metadata.get("scoreline_probability_proxy") == (
                "inverse_bo3_from_direct_series_probability"
            ):
                warnings.append("BO3 留出集选择直接系列概率；局分与 Game 胜率使用其逆 BO3 单局代理。")
        else:
            warnings = [
                "Valve 尚未完整公布瑞士轮配对细则；当前使用保持 1/2/5/5/2/1 容量的联合排名情景。",
            ]
        confidence = "medium"
        if profile != StrategyProfile.EXPECTED_POINTS:
            warnings.append("前 10%/前 100 阈值缺少服务器总体分布，当前为低置信代理目标。")
            confidence = "low"
        return Recommendation(
            recommendation_type="group",
            profile=profile,
            as_of=as_utc(as_of),
            generated_at=as_utc(as_of),
            status="warning",
            objective_value=round(best_expected, 3),
            confidence=confidence,
            selections={
                "scenario": simulation.scenario,
                "sample_count": len(simulation.outcomes),
                "slots": selections,
                "expected_correct": {
                    "count": round(expected_correct_count, 4),
                    "total": len(best),
                    "rate": round(expected_correct_count / len(best), 6),
                    "rate_percent": round(expected_correct_count / len(best) * 100.0, 2),
                    "p10": float(np.quantile(correct_counts, 0.1)),
                    "p50": float(np.quantile(correct_counts, 0.5)),
                    "p90": float(np.quantile(correct_counts, 0.9)),
                    "distribution": correct_distribution,
                    "monte_carlo_standard_error": round(standard_error, 6),
                    "monte_carlo_confidence_interval_95": [round(value, 4) for value in confidence_interval],
                },
                "score_distribution": {
                    "mean": round(float(best_scores.mean()), 3),
                    "p10": float(np.quantile(best_scores, 0.1)),
                    "p50": float(np.quantile(best_scores, 0.5)),
                    "p90": float(np.quantile(best_scores, 0.9)),
                },
            },
            warnings=warnings,
        )


class SwissGroupSimulator(GroupSimulator):
    def __init__(
        self,
        model: TeamStrengthModel,
        manifest: TournamentManifest,
        *,
        swiss_format: SwissFormat,
        policy: SwissSimulationPolicy,
        as_of: datetime,
        series_probability_mode: SeriesProbabilityMode,
    ) -> None:
        super().__init__(model, manifest)
        cutoff = as_utc(as_of)
        if cutoff is None:
            raise ValueError("Swiss Group simulation requires an explicit UTC as_of")
        self.swiss_format = swiss_format
        self.policy = policy
        self.as_of = cutoff
        if series_probability_mode not in ("direct_series", "independent_games"):
            raise ValueError(f"unknown Series probability mode: {series_probability_mode}")
        self.series_probability_mode = series_probability_mode
        self._scenarios = {scenario.scenario_id: scenario for scenario in policy.scenarios}

    def roster_strength_multiplier(self, team_id: int, *, scenario: str) -> float:
        if scenario not in self._scenarios:
            raise ValueError(f"unknown Swiss scenario: {scenario}")
        active = self.as_of >= self.policy.roster_shock.effective_from
        if active and int(team_id) == self.policy.roster_shock.target_team_id:
            return float(self._scenarios[scenario].roster_strength_multiplier)
        return 1.0

    def adjusted_game_probability(self, team_a: int, team_b: int, *, scenario: str) -> float:
        return adjust_strength_probability(
            self.model.predict(team_a, team_b),
            multiplier_a=self.roster_strength_multiplier(team_a, scenario=scenario),
            multiplier_b=self.roster_strength_multiplier(team_b, scenario=scenario),
        )

    def series_win_probability(self, team_a: int, team_b: int, *, scenario: str) -> float:
        probability = self.adjusted_game_probability(team_a, team_b, scenario=scenario)
        if self.series_probability_mode == "independent_games":
            return bo3_probability(probability)
        return probability

    def scoreline_game_probability(self, team_a: int, team_b: int, *, scenario: str) -> float:
        probability = self.adjusted_game_probability(team_a, team_b, scenario=scenario)
        if self.series_probability_mode == "direct_series":
            return inverse_bo3_probability(probability)
        return probability

    def simulate(
        self,
        *,
        samples: int = 20000,
        seed: int = 20260813,
        scenario: str | None = None,
    ) -> GroupSimulation:
        selected_id = scenario or self.policy.primary_scenario
        if selected_id not in self._scenarios:
            raise ValueError(f"unknown Swiss scenario: {selected_id}")
        selected = self._scenarios[selected_id]
        duration = self.policy.duration_proxy
        engine = SwissEngine(
            self.swiss_format,
            lambda team_a, team_b: self.adjusted_game_probability(
                team_a,
                team_b,
                scenario=selected_id,
            ),
            elimination_choice_strategy=selected.elimination_choice_strategy,
            pairing_tie_break=self.policy.pairing_tie_break,
            series_probability_mode=self.series_probability_mode,
            duration_mean_seconds=duration.mean_seconds,
            duration_standard_deviation_seconds=duration.standard_deviation_seconds,
            duration_minimum_seconds=duration.minimum_seconds,
            duration_maximum_seconds=duration.maximum_seconds,
        )
        engine_outcomes = engine.simulate_many(samples=samples, seed=seed)
        engine_indexes = {team_id: index for index, team_id in enumerate(engine.team_ids)}
        outcomes = np.column_stack(
            [engine_outcomes[:, engine_indexes[int(team_id)]] for team_id in self.team_ids]
        ).astype(np.int8, copy=False)
        probabilities = np.stack(
            [(outcomes == index).mean(axis=0) for index in range(len(CATEGORY_IDS))],
            axis=1,
        )
        active = self.as_of >= self.policy.roster_shock.effective_from
        result = GroupSimulation(
            team_ids=self.team_ids.copy(),
            outcomes=outcomes,
            probabilities=probabilities,
            scenario=selected_id,
            seed=seed,
            metadata={
                "engine": "official_swiss_v1",
                "format_version": self.swiss_format.format_version,
                "format_as_of": self.swiss_format.as_of.isoformat(),
                "initial_group_provenance": self.swiss_format.initial_group_provenance,
                "model_probability_semantics": "game_trained_probability",
                "series_probability_mode": self.series_probability_mode,
                "scoreline_probability_proxy": (
                    "inverse_bo3_from_direct_series_probability"
                    if self.series_probability_mode == "direct_series"
                    else "independent_games_from_model_probability"
                ),
                "pairing_tie_break": self.policy.pairing_tie_break,
                "elimination_choice_strategy": selected.elimination_choice_strategy,
                "roster_shock": {
                    "target_team_id": self.policy.roster_shock.target_team_id,
                    "transform": self.policy.roster_shock.transform,
                    "transform_space": "deployed_model_probability_odds_before_series_mode",
                    "multiplier": selected.roster_strength_multiplier if active else 1.0,
                    "applied": active,
                    "provenance": self.policy.roster_shock.provenance,
                },
            },
        )
        result.validate()
        return result


def scenario_sensitivity(
    simulations: list[GroupSimulation], team_names: dict[int, str]
) -> list[dict[str, Any]]:
    if not simulations:
        return []
    stack = np.stack([item.probabilities for item in simulations])
    spread = stack.max(axis=0) - stack.min(axis=0)
    rows: list[dict[str, Any]] = []
    for team_index, team_id in enumerate(simulations[0].team_ids):
        rows.append(
            {
                "team_id": int(team_id),
                "team": team_names[int(team_id)],
                "max_category_probability_spread": round(float(spread[team_index].max()), 6),
                "max_category_probability_spread_percent": round(
                    float(spread[team_index].max()) * 100.0,
                    2,
                ),
            }
        )
    return sorted(rows, key=lambda row: -row["max_category_probability_spread"])


def scenario_probability_tables(
    simulations: list[GroupSimulation], team_names: dict[int, str]
) -> list[dict[str, Any]]:
    return [
        {
            "scenario": simulation.scenario,
            "sample_count": len(simulation.outcomes),
            "seed": simulation.seed,
            "elimination_choice_strategy": simulation.metadata.get("elimination_choice_strategy"),
            "teams": [
                {
                    "team_id": int(team_id),
                    "team": team_names[int(team_id)],
                    **{
                        category: round(
                            float(simulation.probabilities[team_index, category_index]),
                            6,
                        )
                        for category_index, category in enumerate(CATEGORY_IDS)
                    },
                    "percentages": {
                        category: round(
                            float(simulation.probabilities[team_index, category_index]) * 100.0,
                            2,
                        )
                        for category_index, category in enumerate(CATEGORY_IDS)
                    },
                }
                for team_index, team_id in enumerate(simulation.team_ids)
            ],
        }
        for simulation in simulations
    ]
