from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import product

import numpy as np

from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import Recommendation, StrategyProfile, as_utc

BRACKET_NODE_IDS = (
    "upper_r1_a",
    "upper_r1_b",
    "upper_r1_c",
    "upper_r1_d",
    "lower_r1_a",
    "lower_r1_b",
    "upper_semifinal_a",
    "upper_semifinal_b",
    "lower_r2_a",
    "lower_r2_b",
    "lower_r3",
    "upper_final",
    "lower_final",
    "grand_final",
)


@dataclass(frozen=True)
class BracketPath:
    bits: tuple[int, ...]
    participants: tuple[tuple[int, int], ...]
    winners: tuple[int, ...]
    losers: tuple[int, ...]
    probability: float

    @property
    def champion(self) -> int:
        return self.winners[-1]


class BracketEngine:
    def __init__(self, team_ids: Iterable[int], model: TeamStrengthModel) -> None:
        self.team_ids = tuple(int(value) for value in team_ids)
        if len(self.team_ids) != 8 or len(set(self.team_ids)) != 8:
            raise ValueError("Main Event bracket requires eight unique seeded teams")
        self.model = model

    def _resolve_with(
        self,
        choose: Callable[[int, int, float], int],
    ) -> BracketPath:
        choices: list[int] = []
        participants: list[tuple[int, int]] = []
        winners: list[int] = []
        losers: list[int] = []
        probability = 1.0

        def play(left: int, right: int) -> tuple[int, int]:
            nonlocal probability
            participants.append((left, right))
            p_left = self.model.predict(left, right)
            choice = int(choose(left, right, p_left))
            if choice not in (0, 1):
                raise ValueError("a bracket choice must be zero or one")
            choices.append(choice)
            if choice == 0:
                probability *= p_left
                winner, loser = left, right
            else:
                probability *= 1.0 - p_left
                winner, loser = right, left
            winners.append(winner)
            losers.append(loser)
            return winner, loser

        # Upper R1 uses seeds 1v8, 4v5, 2v7, 3v6.
        w0, l0 = play(self.team_ids[0], self.team_ids[7])
        w1, l1 = play(self.team_ids[3], self.team_ids[4])
        w2, l2 = play(self.team_ids[1], self.team_ids[6])
        w3, l3 = play(self.team_ids[2], self.team_ids[5])
        w4, _ = play(l0, l1)
        w5, _ = play(l2, l3)
        w6, l6 = play(w0, w1)
        w7, l7 = play(w2, w3)
        w8, _ = play(w4, l6)
        w9, _ = play(w5, l7)
        w10, _ = play(w8, w9)
        w11, l11 = play(w6, w7)
        w12, _ = play(w10, l11)
        play(w11, w12)
        return BracketPath(
            bits=tuple(choices),
            participants=tuple(participants),
            winners=tuple(winners),
            losers=tuple(losers),
            probability=probability,
        )

    def resolve(self, bits: Iterable[int]) -> BracketPath:
        choices = tuple(int(value) for value in bits)
        if len(choices) != 14 or any(value not in (0, 1) for value in choices):
            raise ValueError("a bracket grid is exactly fourteen binary choices")
        iterator = iter(choices)
        return self._resolve_with(lambda _left, _right, _probability: next(iterator))

    def sample(self, rng: np.random.Generator) -> BracketPath:
        """Draw one coherent bracket path from the model's conditional probabilities."""

        return self._resolve_with(lambda _left, _right, probability: int(rng.random() >= probability))

    def enumerate(self) -> list[BracketPath]:
        paths = [self.resolve(bits) for bits in product((0, 1), repeat=14)]
        probability_sum = sum(path.probability for path in paths)
        if not np.isclose(probability_sum, 1.0, atol=1e-9):
            raise RuntimeError(f"bracket path probabilities sum to {probability_sum}, not one")
        return paths

    @staticmethod
    def _scores(
        candidate: BracketPath,
        actual_winners: np.ndarray,
        points: np.ndarray,
    ) -> np.ndarray:
        correct = (actual_winners == np.asarray(candidate.winners)[None, :]).sum(axis=1)
        return points[correct]

    def recommend(
        self,
        *,
        profile: StrategyProfile,
        cumulative_points: list[int],
        as_of,
        team_names: dict[int, str] | None = None,
        projected_entrants: bool = False,
    ) -> Recommendation:
        paths = self.enumerate()
        probabilities = np.asarray([path.probability for path in paths])
        actual_winners = np.asarray([path.winners for path in paths], dtype=np.int64)
        points = np.asarray(cumulative_points, dtype=float)
        # Every coherent grid is enumerated. Exact nonlinear scoring is then applied to
        # a broad deterministic shortlist selected by node marginals and path probability.
        marginal: list[dict[int, float]] = []
        for node in range(14):
            values: dict[int, float] = {}
            for winner, probability in zip(actual_winners[:, node], probabilities, strict=True):
                values[int(winner)] = values.get(int(winner), 0.0) + float(probability)
            marginal.append(values)
        linear_scores = np.asarray(
            [
                sum(marginal[node].get(winner, 0.0) for node, winner in enumerate(path.winners))
                for path in paths
            ]
        )
        shortlist_indexes = set(np.argsort(-linear_scores)[:768].tolist())
        shortlist_indexes.update(np.argsort(-probabilities)[:768].tolist())
        expected_reference = paths[int(np.argmax(linear_scores))]
        reference_scores = self._scores(expected_reference, actual_winners, points)
        top10_threshold = float(np.quantile(reference_scores, 0.90, method="higher"))
        top100_threshold = float(np.quantile(reference_scores, 0.995, method="higher"))
        reference_expected = float(np.dot(reference_scores, probabilities))

        best_path = expected_reference
        best_value = -float("inf")
        best_expected = 0.0
        best_scores = reference_scores
        for index in sorted(shortlist_indexes):
            candidate = paths[index]
            scores = self._scores(candidate, actual_winners, points)
            expected = float(np.dot(scores, probabilities))
            if profile == StrategyProfile.EXPECTED_POINTS:
                value = expected
            elif profile == StrategyProfile.TOP_10:
                value = float(probabilities[scores >= top10_threshold].sum())
            else:
                if expected < reference_expected * 0.85:
                    continue
                tail_mask = scores >= top100_threshold
                value = float(np.dot(scores[tail_mask], probabilities[tail_mask]))
            if value > best_value:
                best_path, best_value, best_expected, best_scores = candidate, value, expected, scores

        names = team_names or {team_id: str(team_id) for team_id in self.team_ids}
        nodes = []
        for node_id, participants, winner in zip(
            BRACKET_NODE_IDS, best_path.participants, best_path.winners, strict=True
        ):
            nodes.append(
                {
                    "node": node_id,
                    "left_team_id": participants[0],
                    "left_team": names.get(participants[0], str(participants[0])),
                    "right_team_id": participants[1],
                    "right_team": names.get(participants[1], str(participants[1])),
                    "winner_team_id": winner,
                    "winner_team": names.get(winner, str(winner)),
                }
            )
        warnings: list[str] = []
        status = "publishable"
        confidence = "medium"
        if projected_entrants:
            status = "blocked"
            confidence = "low"
            warnings.append("主赛事实际八队与种子尚未导入；当前网格仅为占位推演，不可发布。")
        if profile != StrategyProfile.EXPECTED_POINTS:
            confidence = "low"
            warnings.append("前 10%/前 100 阈值缺少服务器总体分布，当前为低置信代理目标。")
        return Recommendation(
            recommendation_type="bracket",
            profile=profile,
            as_of=as_utc(as_of),
            generated_at=as_utc(as_of),
            status=status,
            objective_value=round(best_expected, 3),
            confidence=confidence,
            selections={
                "nodes": nodes,
                "champion": {
                    "team_id": best_path.champion,
                    "team": names.get(best_path.champion, str(best_path.champion)),
                },
                "score_distribution": {
                    "mean": round(best_expected, 3),
                    "p50": float(_weighted_quantile(best_scores, probabilities, 0.5)),
                    "p90": float(_weighted_quantile(best_scores, probabilities, 0.9)),
                },
                "enumerated_grids": 16384,
            },
            warnings=warnings,
        )


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    index = int(np.searchsorted(cumulative, quantile, side="left"))
    return float(sorted_values[min(index, len(sorted_values) - 1)])
