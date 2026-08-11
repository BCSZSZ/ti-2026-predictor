from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from ti_predictor.schemas import SwissFormat

SWISS_CATEGORY_IDS = (
    "four_zero",
    "four_one",
    "elimination_winner",
    "elimination_loser",
    "one_four",
    "zero_four",
)
SWISS_CATEGORY_CAPACITIES = (1, 2, 5, 5, 2, 1)
_CATEGORY_INDEX = {category: index for index, category in enumerate(SWISS_CATEGORY_IDS)}

Pair = tuple[int, int]
Record = tuple[int, int]
EliminationChoiceStrategy = Literal["model_optimal", "adversarial", "seeded_random"]
PairingTieBreak = Literal["canonical", "seeded_random"]
SeriesProbabilityMode = Literal["independent_games", "direct_series"]


def canonical_pair(team_a: int, team_b: int) -> Pair:
    return (team_a, team_b) if team_a < team_b else (team_b, team_a)


def bo3_probability(game_probability: float) -> float:
    probability = float(game_probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("Game probability must be between zero and one")
    return 3.0 * probability**2 - 2.0 * probability**3


def inverse_bo3_probability(series_probability: float) -> float:
    probability = float(series_probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("Series probability must be between zero and one")
    low = 0.0
    high = 1.0
    for _ in range(64):
        midpoint = (low + high) / 2.0
        if bo3_probability(midpoint) < probability:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def adjust_strength_probability(
    probability_a: float,
    *,
    multiplier_a: float = 1.0,
    multiplier_b: float = 1.0,
) -> float:
    probability = float(probability_a)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between zero and one")
    if multiplier_a <= 0.0 or multiplier_b <= 0.0:
        raise ValueError("strength multipliers must be positive")
    numerator = multiplier_a * probability
    denominator = numerator + multiplier_b * (1.0 - probability)
    return numerator / denominator


@dataclass
class TeamStanding:
    series_wins: int = 0
    series_losses: int = 0
    game_wins: int = 0
    game_losses: int = 0
    total_duration_seconds: int = 0
    opponents: list[int] = field(default_factory=list)

    @property
    def record(self) -> Record:
        return self.series_wins, self.series_losses

    @property
    def games_played(self) -> int:
        return self.game_wins + self.game_losses

    @property
    def game_win_rate(self) -> float:
        return self.game_wins / self.games_played if self.games_played else 0.0

    @property
    def average_duration_seconds(self) -> float:
        return self.total_duration_seconds / self.games_played if self.games_played else float("inf")


@dataclass(frozen=True)
class SwissSeriesResult:
    phase: Literal["swiss", "elimination"]
    round_number: int
    team_a_id: int
    team_b_id: int
    team_a_record_before: Record
    team_b_record_before: Record
    team_a_game_wins: int
    team_b_game_wins: int
    winner_team_id: int
    loser_team_id: int
    game_durations_seconds: tuple[int, ...]

    @property
    def pair(self) -> Pair:
        return canonical_pair(self.team_a_id, self.team_b_id)


@dataclass(frozen=True)
class SwissTournamentResult:
    team_ids: tuple[int, ...]
    category_by_team: dict[int, int]
    standings: dict[int, TeamStanding]
    series: tuple[SwissSeriesResult, ...]
    elimination_choices: tuple[Pair, ...]

    @property
    def outcomes(self) -> np.ndarray:
        return np.asarray([self.category_by_team[team_id] for team_id in self.team_ids], dtype=np.int8)

    def validate(self, swiss_format: SwissFormat) -> None:
        counts = np.bincount(self.outcomes, minlength=len(SWISS_CATEGORY_IDS))
        if tuple(int(value) for value in counts) != SWISS_CATEGORY_CAPACITIES:
            raise ValueError(f"Swiss category capacities are invalid: {counts.tolist()}")
        swiss_series = [item for item in self.series if item.phase == "swiss"]
        if len(swiss_series) != 39:
            raise ValueError(f"Swiss stage must contain thirty-nine Series, got {len(swiss_series)}")
        expected_round_one = {
            canonical_pair(item.team_a_id, item.team_b_id) for item in swiss_format.first_round
        }
        actual_round_one = {item.pair for item in swiss_series if item.round_number == 1}
        if actual_round_one != expected_round_one:
            raise ValueError("simulated Round 1 differs from the fixed Valve schedule")
        if len(self.elimination_choices) != 5:
            raise ValueError("Elimination Round must contain five opponent choices")


def rank_teams(
    team_ids: Iterable[int],
    standings: dict[int, TeamStanding],
    coin_toss: dict[int, float],
) -> list[int]:
    def opponent_game_win_rate(team_id: int) -> float:
        opponents = standings[team_id].opponents
        if not opponents:
            return 0.0
        game_win_rates = [standings[opponent].game_win_rate for opponent in opponents]
        return float(np.add.reduce(game_win_rates) / len(opponents))

    def key(team_id: int) -> tuple[float, ...]:
        standing = standings[team_id]
        opponent_match_wins = sum(standings[opponent].series_wins for opponent in standing.opponents)
        return (
            -standing.series_wins,
            standing.series_losses,
            -opponent_match_wins,
            -standing.game_win_rate,
            -opponent_game_win_rate(team_id),
            standing.average_duration_seconds,
            coin_toss[team_id],
        )

    return sorted((int(team_id) for team_id in team_ids), key=key)


def select_pairings(
    team_ids: Iterable[int],
    *,
    round_number: int,
    rank_positions: dict[int, int],
    prior_pairs: set[Pair],
    initial_groups: dict[int, str],
    maximize_rank_distance: bool,
    rng: np.random.Generator,
    tie_break: PairingTieBreak = "seeded_random",
) -> tuple[Pair, ...]:
    pool = tuple(sorted(int(team_id) for team_id in team_ids))
    if len(pool) % 2:
        raise ValueError("Swiss record pool must contain an even number of teams")

    def allowed(team_a: int, team_b: int) -> bool:
        if round_number in (2, 3):
            return initial_groups[team_a] == initial_groups[team_b]
        if round_number == 4:
            return initial_groups[team_a] != initial_groups[team_b]
        return True

    candidates: list[tuple[Pair, ...]] = []

    def enumerate_matchings(remaining: tuple[int, ...], selected: tuple[Pair, ...]) -> None:
        if not remaining:
            candidates.append(tuple(sorted(selected)))
            return
        left = remaining[0]
        for index, right in enumerate(remaining[1:], start=1):
            if not allowed(left, right):
                continue
            next_remaining = remaining[1:index] + remaining[index + 1 :]
            enumerate_matchings(next_remaining, (*selected, canonical_pair(left, right)))

    enumerate_matchings(pool, ())
    if not candidates:
        raise ValueError(f"no legal Swiss pairing for round {round_number}: {pool}")

    def objective(pairing: tuple[Pair, ...]) -> tuple[int, ...]:
        repeats = sum(pair in prior_pairs for pair in pairing)
        distances = sorted(
            (abs(rank_positions[left] - rank_positions[right]) for left, right in pairing),
            reverse=True,
        )
        if maximize_rank_distance:
            return repeats, *(-distance for distance in distances), -sum(distances)
        return repeats, *distances, sum(distances)

    scored = [(objective(pairing), pairing) for pairing in candidates]
    best_value = min(value for value, _ in scored)
    best = sorted(pairing for value, pairing in scored if value == best_value)
    if tie_break == "canonical" or len(best) == 1:
        return best[0]
    return best[int(rng.integers(len(best)))]


class SwissEngine:
    def __init__(
        self,
        swiss_format: SwissFormat,
        game_probability: Callable[[int, int], float],
        *,
        elimination_choice_strategy: EliminationChoiceStrategy = "model_optimal",
        pairing_tie_break: PairingTieBreak = "seeded_random",
        series_probability_mode: SeriesProbabilityMode = "independent_games",
        duration_mean_seconds: float = 2400.0,
        duration_standard_deviation_seconds: float = 420.0,
        duration_minimum_seconds: int = 900,
        duration_maximum_seconds: int = 5400,
    ) -> None:
        self.format = swiss_format
        self.game_probability = game_probability
        self.elimination_choice_strategy = elimination_choice_strategy
        self.pairing_tie_break = pairing_tie_break
        self.series_probability_mode = series_probability_mode
        self.duration_mean_seconds = float(duration_mean_seconds)
        self.duration_standard_deviation_seconds = float(duration_standard_deviation_seconds)
        self.duration_minimum_seconds = int(duration_minimum_seconds)
        self.duration_maximum_seconds = int(duration_maximum_seconds)
        if self.duration_mean_seconds <= 0.0 or self.duration_standard_deviation_seconds <= 0.0:
            raise ValueError("duration proxy mean and standard deviation must be positive")
        if self.duration_maximum_seconds <= self.duration_minimum_seconds:
            raise ValueError("duration proxy bounds are reversed")
        self.team_ids = tuple(
            team_id for series in swiss_format.first_round for team_id in (series.team_a_id, series.team_b_id)
        )
        self.initial_groups = {
            team_id: series.initial_group
            for series in swiss_format.first_round
            for team_id in (series.team_a_id, series.team_b_id)
        }
        self._probability_cache: dict[Pair, float] = {}
        self._scoreline_probability_cache: dict[Pair, float] = {}

    def _probability(self, team_a: int, team_b: int) -> float:
        key = (int(team_a), int(team_b))
        cached = self._probability_cache.get(key)
        if cached is not None:
            return cached
        probability = float(self.game_probability(*key))
        if not 0.0 < probability < 1.0:
            raise ValueError(f"invalid Game probability for {team_a} vs {team_b}: {probability}")
        self._probability_cache[key] = probability
        return probability

    def _scoreline_probability(self, team_a: int, team_b: int) -> float:
        key = (int(team_a), int(team_b))
        cached = self._scoreline_probability_cache.get(key)
        if cached is not None:
            return cached
        probability = self._probability(*key)
        if self.series_probability_mode == "direct_series":
            probability = inverse_bo3_probability(probability)
        self._scoreline_probability_cache[key] = probability
        return probability

    def _play_series(
        self,
        team_a: int,
        team_b: int,
        *,
        phase: Literal["swiss", "elimination"],
        round_number: int,
        standings: dict[int, TeamStanding],
        rng: np.random.Generator,
        update_standings: bool,
    ) -> SwissSeriesResult:
        record_a = standings[team_a].record
        record_b = standings[team_b].record
        wins_a = 0
        wins_b = 0
        scoreline_game_probability = self._scoreline_probability(team_a, team_b)
        while wins_a < 2 and wins_b < 2:
            if rng.random() < scoreline_game_probability:
                wins_a += 1
            else:
                wins_b += 1
        durations: list[int] = []
        for _ in range(wins_a + wins_b):
            rounded_duration = np.rint(
                rng.normal(
                    self.duration_mean_seconds,
                    self.duration_standard_deviation_seconds,
                )
            )
            duration = int(
                min(
                    max(rounded_duration, self.duration_minimum_seconds),
                    self.duration_maximum_seconds,
                )
            )
            durations.append(duration)
        winner, loser = (team_a, team_b) if wins_a == 2 else (team_b, team_a)
        if update_standings:
            standings[winner].series_wins += 1
            standings[loser].series_losses += 1
            standings[team_a].game_wins += wins_a
            standings[team_a].game_losses += wins_b
            standings[team_b].game_wins += wins_b
            standings[team_b].game_losses += wins_a
            total_duration = sum(durations)
            standings[team_a].total_duration_seconds += total_duration
            standings[team_b].total_duration_seconds += total_duration
            standings[team_a].opponents.append(team_b)
            standings[team_b].opponents.append(team_a)
        return SwissSeriesResult(
            phase=phase,
            round_number=round_number,
            team_a_id=team_a,
            team_b_id=team_b,
            team_a_record_before=record_a,
            team_b_record_before=record_b,
            team_a_game_wins=wins_a,
            team_b_game_wins=wins_b,
            winner_team_id=winner,
            loser_team_id=loser,
            game_durations_seconds=tuple(durations),
        )

    def _choose_elimination_opponent(
        self,
        chooser: int,
        available: list[int],
        *,
        rank_positions: dict[int, int],
        rng: np.random.Generator,
    ) -> int:
        if self.elimination_choice_strategy == "seeded_random":
            return available[int(rng.integers(len(available)))]
        scored = [
            (self._probability(chooser, opponent), rank_positions[opponent], opponent)
            for opponent in available
        ]
        if self.elimination_choice_strategy == "model_optimal":
            return max(scored)[2]
        return min(scored)[2]

    def _simulate(self, rng: np.random.Generator) -> SwissTournamentResult:
        standings = {team_id: TeamStanding() for team_id in self.team_ids}
        coin_toss = {team_id: float(rng.random()) for team_id in self.team_ids}
        prior_pairs: set[Pair] = set()
        results: list[SwissSeriesResult] = []

        for scheduled in self.format.first_round:
            result = self._play_series(
                scheduled.team_a_id,
                scheduled.team_b_id,
                phase="swiss",
                round_number=1,
                standings=standings,
                rng=rng,
                update_standings=True,
            )
            results.append(result)
            prior_pairs.add(result.pair)

        for round_number in range(2, self.format.rounds + 1):
            active = [
                team_id
                for team_id in self.team_ids
                if standings[team_id].series_wins < self.format.win_loss_limit
                and standings[team_id].series_losses < self.format.win_loss_limit
            ]
            ranking = rank_teams(self.team_ids, standings, coin_toss)
            rank_positions = {team_id: index for index, team_id in enumerate(ranking)}
            pools: dict[Record, list[int]] = {}
            for team_id in active:
                pools.setdefault(standings[team_id].record, []).append(team_id)
            round_pairings: list[Pair] = []
            for record in sorted(pools, key=lambda item: (-item[0], item[1])):
                round_pairings.extend(
                    select_pairings(
                        pools[record],
                        round_number=round_number,
                        rank_positions=rank_positions,
                        prior_pairs=prior_pairs,
                        initial_groups=self.initial_groups,
                        maximize_rank_distance=round_number == 5 and record[1] == 3,
                        rng=rng,
                        tie_break=self.pairing_tie_break,
                    )
                )
            for team_a, team_b in round_pairings:
                result = self._play_series(
                    team_a,
                    team_b,
                    phase="swiss",
                    round_number=round_number,
                    standings=standings,
                    rng=rng,
                    update_standings=True,
                )
                results.append(result)
                prior_pairs.add(result.pair)

        ranking = rank_teams(self.team_ids, standings, coin_toss)
        rank_positions = {team_id: index for index, team_id in enumerate(ranking)}
        four_zero = [team_id for team_id in ranking if standings[team_id].record == (4, 0)]
        four_one = [team_id for team_id in ranking if standings[team_id].record == (4, 1)]
        three_two = [team_id for team_id in ranking if standings[team_id].record == (3, 2)]
        two_three = [team_id for team_id in ranking if standings[team_id].record == (2, 3)]
        one_four = [team_id for team_id in ranking if standings[team_id].record == (1, 4)]
        zero_four = [team_id for team_id in ranking if standings[team_id].record == (0, 4)]
        record_counts = tuple(map(len, (four_zero, four_one, three_two, two_three, one_four, zero_four)))
        if record_counts != SWISS_CATEGORY_CAPACITIES:
            raise RuntimeError(f"Swiss terminal record capacities are invalid: {record_counts}")

        available = list(two_three)
        choices: list[Pair] = []
        elimination_winners: list[int] = []
        elimination_losers: list[int] = []
        for chooser in three_two:
            opponent = self._choose_elimination_opponent(
                chooser,
                available,
                rank_positions=rank_positions,
                rng=rng,
            )
            available.remove(opponent)
            choices.append((chooser, opponent))
            result = self._play_series(
                chooser,
                opponent,
                phase="elimination",
                round_number=6,
                standings=standings,
                rng=rng,
                update_standings=False,
            )
            results.append(result)
            elimination_winners.append(result.winner_team_id)
            elimination_losers.append(result.loser_team_id)

        categories: dict[int, int] = {}
        for category, teams in (
            ("four_zero", four_zero),
            ("four_one", four_one),
            ("elimination_winner", elimination_winners),
            ("elimination_loser", elimination_losers),
            ("one_four", one_four),
            ("zero_four", zero_four),
        ):
            categories.update({team_id: _CATEGORY_INDEX[category] for team_id in teams})
        tournament = SwissTournamentResult(
            team_ids=self.team_ids,
            category_by_team=categories,
            standings=standings,
            series=tuple(results),
            elimination_choices=tuple(choices),
        )
        tournament.validate(self.format)
        return tournament

    def simulate(self, *, seed: int) -> SwissTournamentResult:
        return self._simulate(np.random.default_rng(seed))

    def simulate_many(self, *, samples: int, seed: int) -> np.ndarray:
        if samples <= 0:
            raise ValueError("samples must be positive")
        rng = np.random.default_rng(seed)
        outcomes = np.empty((samples, len(self.team_ids)), dtype=np.int8)
        for sample in range(samples):
            outcomes[sample] = self._simulate(rng).outcomes
        return outcomes
