from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import Recommendation, StrategyProfile, TournamentManifest, as_utc

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
                }
                for index in team_indexes
            ]

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
                "slots": selections,
                "score_distribution": {
                    "mean": round(float(best_scores.mean()), 3),
                    "p10": float(np.quantile(best_scores, 0.1)),
                    "p50": float(np.quantile(best_scores, 0.5)),
                    "p90": float(np.quantile(best_scores, 0.9)),
                },
            },
            warnings=warnings,
        )


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
            }
        )
    return sorted(rows, key=lambda row: -row["max_category_probability_spread"])
