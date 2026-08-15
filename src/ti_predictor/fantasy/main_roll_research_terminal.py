"""Vectorized terminal arithmetic for the isolated Main Roll research path.

The production Web evaluator remains unchanged.  This module reproduces its five-slot
Banner arithmetic over a frozen Main Scenario set while pre-packing historical Series
blocks so large offline experiments do not repeatedly execute the same Python loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ti_predictor.fantasy.main_scenarios import MainScenarioSet
from ti_predictor.fantasy.roll import BannerState
from ti_predictor.fantasy.scenarios import PoolBuildResult, SeriesBlockPool
from ti_predictor.fantasy.valuation import TeamOutcomeMatrix, _banner_score_inputs


class MainResearchTerminalArithmeticError(ValueError):
    """The frozen research tensor does not match its Series pools or Scenarios."""


@dataclass(frozen=True)
class _PackedPool:
    pool: SeriesBlockPool
    game_stat_scores: np.ndarray
    valid_games: np.ndarray

    @classmethod
    def from_pool(cls, pool: SeriesBlockPool) -> _PackedPool:
        if not pool.blocks:
            raise MainResearchTerminalArithmeticError("research terminal requires non-empty pools")
        stat_count = len(pool.stat_ids)
        maximum_games = max(len(block.match_ids) for block in pool.blocks)
        values = np.zeros((len(pool.blocks), maximum_games, stat_count), dtype=float)
        valid = np.zeros((len(pool.blocks), maximum_games), dtype=bool)
        for block_index, block in enumerate(pool.blocks):
            scores = np.asarray(block.game_stat_scores, dtype=float)
            expected = (len(block.match_ids), stat_count)
            if scores.shape != expected or not np.isfinite(scores).all():
                raise MainResearchTerminalArithmeticError(
                    f"Series block {block.block_id} does not align with its Stat schema"
                )
            values[block_index, : len(block.match_ids)] = scores
            valid[block_index, : len(block.match_ids)] = True
        values.setflags(write=False)
        valid.setflags(write=False)
        return cls(pool, values, valid)

    def block_values(
        self,
        stat_ids: tuple[str, ...],
        multipliers: tuple[float, ...],
    ) -> np.ndarray:
        index = {stat_id: offset for offset, stat_id in enumerate(self.pool.stat_ids)}
        try:
            selected = tuple(index[stat_id] for stat_id in stat_ids)
        except KeyError as error:
            raise MainResearchTerminalArithmeticError(
                f"Series pool lacks Main Stat {error.args[0]}"
            ) from error
        weights = np.asarray(multipliers, dtype=float)
        game_values = self.game_stat_scores[:, :, selected] @ weights
        game_values = np.where(self.valid_games, game_values, -np.inf)
        ordered = np.sort(game_values, axis=1, kind="stable")
        top_two = ordered[:, -2:]
        top_two = np.where(np.isfinite(top_two), top_two, 0.0)
        return top_two.sum(axis=1)


class VectorizedMainResearchTerminal:
    """Research-only drop-in implementation of ``MainBannerTerminal``."""

    def __init__(
        self,
        pool_result: PoolBuildResult,
        scenario_set: MainScenarioSet,
        canonical_rules: dict[str, Any],
    ) -> None:
        expected_candidates = 16 if scenario_set.eligibility_mode == "projected" else 8
        if len(scenario_set.team_ids) != expected_candidates:
            raise MainResearchTerminalArithmeticError(
                "research terminal candidate count does not match Main eligibility"
            )
        self.pool_result = pool_result
        self.scenario_set = scenario_set
        self.canonical_rules = canonical_rules
        self.eligibility_mode = scenario_set.eligibility_mode
        self._packed = {
            (pool.target_team_id, pool.role): _PackedPool.from_pool(pool) for pool in pool_result.pools
        }
        if len(self._packed) != len(pool_result.pools):
            raise MainResearchTerminalArithmeticError("research pools contain duplicate Team roles")
        self._cache: dict[BannerState, TeamOutcomeMatrix] = {}

    def clear_evaluation_cache(self) -> None:
        """Release dynamic Banner matrices between isolated research shards."""

        self._cache.clear()

    def banner(self, banner: BannerState) -> TeamOutcomeMatrix:
        if banner in self._cache:
            return self._cache[banner]
        stat_ids, multipliers = _banner_score_inputs(
            banner,
            self.canonical_rules,
            slot_count=5,
            period_label="Main",
        )
        rows: list[np.ndarray] = []
        team_ids = tuple(
            team_id for team_id in self.scenario_set.team_ids if (team_id, banner.role) in self._packed
        )
        if not team_ids:
            raise MainResearchTerminalArithmeticError(
                f"no research Main Team is available for role {banner.role}"
            )
        for team_id in team_ids:
            packed = self._packed[(team_id, banner.role)]
            block_values = packed.block_values(stat_ids, multipliers)
            draws = self.scenario_set.draws_for(team_id, banner.role)
            sampled = np.zeros(draws.shape, dtype=float)
            used = draws >= 0
            sampled[used] = block_values[draws[used]]
            rows.append(sampled.max(axis=1))
        result = TeamOutcomeMatrix(
            kind="banner",
            item_id=(
                banner.role
                + "|"
                + ";".join(f"{item.stat_id}:T{item.quality_tier}:{item.trait_id}" for item in banner.emblems)
                + "|coach-unavailable-excluded"
            ),
            role=banner.role,
            scenario_sha256=self.scenario_set.semantic_hash,
            team_ids=team_ids,
            outcomes=np.stack(rows),
        )
        self._cache[banner] = result
        return result


__all__ = [
    "MainResearchTerminalArithmeticError",
    "VectorizedMainResearchTerminal",
]
