from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.fantasy.scoring import score_stat
from ti_predictor.models.ratings import TeamStrengthModel
from ti_predictor.schemas import Recommendation, StrategyProfile, TournamentManifest, as_utc


@dataclass(frozen=True)
class EmpiricalEstimate:
    mean: float | None
    std: float | None
    observations: int
    coverage: float


def _weighted_estimate(
    values: pd.Series,
    times: pd.Series,
    as_of,
    *,
    evidence_weights: pd.Series | None = None,
) -> EmpiricalEstimate:
    numeric = pd.to_numeric(values, errors="coerce")
    if evidence_weights is None:
        eligible = pd.Series(True, index=numeric.index, dtype=bool)
        normalized_weights = None
    else:
        normalized_weights = pd.to_numeric(evidence_weights, errors="coerce").fillna(0.0)
        eligible = normalized_weights.gt(0.0)
    coverage = float(numeric.loc[eligible].notna().mean()) if eligible.any() else 0.0
    available = numeric.notna() & eligible
    if not available.any():
        return EmpiricalEstimate(None, None, 0, coverage)
    value_array = numeric.loc[available].to_numpy(dtype=float)
    if normalized_weights is None:
        timestamps = pd.to_datetime(times.loc[available], utc=True)
        age_days = np.maximum(
            0.0,
            (pd.Timestamp(as_of) - timestamps).dt.total_seconds().to_numpy() / 86400,
        )
        weights = np.exp(-np.log(2.0) * age_days / 150.0)
    else:
        weights = normalized_weights.loc[available].to_numpy(dtype=float)
    weight_sum = float(weights.sum())
    mean = float(np.dot(weights, value_array) / weight_sum)
    variance = float(np.dot(weights, (value_array - mean) ** 2) / weight_sum)
    return EmpiricalEstimate(mean, variance**0.5, len(value_array), coverage)


def _matching_provenance_values(
    rows: pd.DataFrame,
    stat_id: str,
    expected_provenance: str,
) -> pd.Series:
    if stat_id not in rows:
        return pd.Series(np.nan, index=rows.index, dtype=float)
    numeric = pd.to_numeric(rows[stat_id], errors="coerce")
    provenance_column = f"{stat_id}_provenance"
    if provenance_column not in rows:
        return pd.Series(np.nan, index=rows.index, dtype=float)
    return numeric.where(rows[provenance_column].eq(expected_provenance))


class FantasyRecommender:
    def __init__(
        self,
        observations: pd.DataFrame,
        manifest: TournamentManifest,
        rules: dict[str, Any],
        strength_model: TeamStrengthModel,
        *,
        as_of,
    ) -> None:
        self.as_of = as_utc(as_of)
        self.manifest = manifest
        self.rules = rules
        self.strength_model = strength_model
        self.observations = observations.copy()
        if not self.observations.empty:
            self.observations["start_time"] = pd.to_datetime(self.observations["start_time"], utc=True)
            self.observations = self.observations.loc[
                (self.observations["start_time"] <= pd.Timestamp(self.as_of))
                & self.observations["start_time"].dt.year.eq(self.as_of.year)
            ].copy()
            if "evidence_weight" in self.observations:
                self.observations["evidence_weight"] = pd.to_numeric(
                    self.observations["evidence_weight"], errors="coerce"
                ).fillna(0.0)
                self.observations = self.observations.loc[self.observations["evidence_weight"].gt(0.0)].copy()
        self.player_roles = {
            player.account_id: role
            for team in manifest.teams
            for role, players in team.players.items()
            for player in players
        }
        self.player_names = {
            player.account_id: player.name
            for team in manifest.teams
            for players in team.players.values()
            for player in players
        }
        self.team_names = {team.team_id: team.name for team in manifest.teams}
        self._player_estimate_cache: dict[tuple[int, str], EmpiricalEstimate] = {}
        self._global_prior_cache: dict[tuple[str, str], tuple[float, float]] = {}

    def coverage(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for stat_id, stat_rule in self.rules["fantasy"]["stats"].items():
            values = _matching_provenance_values(
                self.observations,
                stat_id,
                stat_rule["provenance"],
            )
            coverage = float(values.notna().mean()) if len(values) else 0.0
            rows.append(
                {
                    "stat_id": stat_id,
                    "label": stat_rule["label"],
                    "color": stat_rule["color"],
                    "provenance": stat_rule["provenance"],
                    "coverage": round(coverage, 6),
                    "default_eligible": stat_rule["provenance"] in {"exact", "derived"} and coverage >= 0.50,
                }
            )
        return rows

    def _player_stat_estimate(self, account_id: int, stat_id: str) -> EmpiricalEstimate:
        cache_key = (account_id, stat_id)
        if cache_key in self._player_estimate_cache:
            return self._player_estimate_cache[cache_key]
        if self.observations.empty or stat_id not in self.observations:
            result = EmpiricalEstimate(None, None, 0, 0.0)
            self._player_estimate_cache[cache_key] = result
            return result
        rows = self.observations.loc[self.observations["account_id"] == account_id]
        if rows.empty:
            result = EmpiricalEstimate(None, None, 0, 0.0)
            self._player_estimate_cache[cache_key] = result
            return result
        rule = self.rules["fantasy"]["stats"][stat_id]
        values = _matching_provenance_values(rows, stat_id, rule["provenance"])
        scored = values.map(lambda value: score_stat(value, rule))
        result = _weighted_estimate(
            scored,
            rows["start_time"],
            self.as_of,
            evidence_weights=rows.get("evidence_weight"),
        )
        self._player_estimate_cache[cache_key] = result
        return result

    def _global_prior(self, role: str, stat_id: str) -> tuple[float, float]:
        cache_key = (role, stat_id)
        if cache_key in self._global_prior_cache:
            return self._global_prior_cache[cache_key]
        account_ids = [account_id for account_id, value in self.player_roles.items() if value == role]
        estimates = [self._player_stat_estimate(account_id, stat_id) for account_id in account_ids]
        means = [estimate.mean for estimate in estimates if estimate.mean is not None]
        stds = [estimate.std for estimate in estimates if estimate.std is not None]
        result = (float(np.mean(means)) if means else 0.0, float(np.mean(stds)) if stds else 0.0)
        self._global_prior_cache[cache_key] = result
        return result

    def _team_stat(self, team, role: str, stat_id: str) -> dict[str, Any]:
        players = team.players[role]
        prior_mean, prior_std = self._global_prior(role, stat_id)
        means: list[float] = []
        variances: list[float] = []
        coverage: list[float] = []
        observations = 0
        player_details = []
        for player in players:
            estimate = self._player_stat_estimate(player.account_id, stat_id)
            shrinkage = estimate.observations / (estimate.observations + 8.0)
            mean = (
                prior_mean
                if estimate.mean is None
                else shrinkage * estimate.mean + (1.0 - shrinkage) * prior_mean
            )
            std = (
                prior_std
                if estimate.std is None
                else shrinkage * estimate.std + (1.0 - shrinkage) * prior_std
            )
            means.append(mean)
            variances.append(std**2)
            coverage.append(estimate.coverage)
            observations += estimate.observations
            player_details.append(
                {
                    "account_id": player.account_id,
                    "player": player.name,
                    "observations": estimate.observations,
                }
            )
        duo_divisor = len(players)
        per_game_mean = float(np.mean(means))
        per_game_std = float(np.sqrt(sum(variances)) / duo_divisor)
        # Two best games in the selected series; 2.08 mildly reflects BO3 upside.
        series_mean = per_game_mean * 2.08
        series_std = per_game_std * np.sqrt(2.0)
        rating = self.strength_model.strength_rating(team.team_id)
        availability = float(np.clip(0.82 + (rating - 1500.0) / 1000.0, 0.55, 1.20))
        return {
            "team_id": team.team_id,
            "team": team.name,
            "role": role,
            "stat_id": stat_id,
            "mean": series_mean * availability,
            "std": series_std,
            "coverage": float(np.mean(coverage)) if coverage else 0.0,
            "observations": observations,
            "min_player_observations": min((item["observations"] for item in player_details), default=0),
            "players": player_details,
        }

    @staticmethod
    def _profile_value(row: dict[str, Any], profile: StrategyProfile) -> float:
        if profile == StrategyProfile.EXPECTED_POINTS:
            return float(row["mean"])
        if profile == StrategyProfile.TOP_10:
            return float(row["mean"] + 0.85 * row["std"])
        return float(row["mean"] + 1.65 * row["std"])

    def _eligible_stats(self, color: str) -> list[str]:
        return [
            stat_id
            for stat_id, rule in self.rules["fantasy"]["stats"].items()
            if rule["color"] == color and rule["provenance"] in {"exact", "derived"}
        ]

    def _role_rankings(self, role: str, profile: StrategyProfile, banner_slots: int) -> list[dict[str, Any]]:
        colors = self.rules["fantasy"]["role_banners"][role][:banner_slots]
        rankings: list[dict[str, Any]] = []
        for team in self.manifest.teams:
            emblems: list[dict[str, Any]] = []
            used_stats: set[str] = set()
            total_expected = 0.0
            total_objective = 0.0
            for slot_index, color in enumerate(colors, start=1):
                candidates = [self._team_stat(team, role, stat_id) for stat_id in self._eligible_stats(color)]
                candidates = [
                    row for row in candidates if row["coverage"] >= 0.5 and row["stat_id"] not in used_stats
                ]
                candidates.sort(key=lambda row: -self._profile_value(row, profile))
                if not candidates:
                    emblems.append(
                        {"slot": slot_index, "color": color, "status": "unavailable", "candidates": []}
                    )
                    continue
                best = candidates[0]
                used_stats.add(best["stat_id"])
                total_expected += float(best["mean"])
                total_objective += self._profile_value(best, profile)
                emblems.append(
                    {
                        "slot": slot_index,
                        "color": color,
                        "stat_id": best["stat_id"],
                        "label": self.rules["fantasy"]["stats"][best["stat_id"]]["label"],
                        "mean": round(float(best["mean"]), 4),
                        "std": round(float(best["std"]), 4),
                        "coverage": round(float(best["coverage"]), 4),
                        "observations": int(best["observations"]),
                        "min_player_observations": int(best["min_player_observations"]),
                        "quality_marginal": {
                            str(item["tier"]): round(
                                float(best["mean"]) * float(item["bonus_percent"]) / 100.0, 4
                            )
                            for item in self.rules["fantasy"]["qualities"]
                        },
                        "candidates": [
                            {
                                "stat_id": candidate["stat_id"],
                                "label": self.rules["fantasy"]["stats"][candidate["stat_id"]]["label"],
                                "objective": round(self._profile_value(candidate, profile), 4),
                                "coverage": round(float(candidate["coverage"]), 4),
                            }
                            for candidate in candidates[:3]
                        ],
                    }
                )
            rankings.append(
                {
                    "team_id": team.team_id,
                    "team": team.name,
                    "role": role,
                    "players": [
                        {"account_id": player.account_id, "player": player.name}
                        for player in team.players[role]
                    ],
                    "expected_raw_points": round(total_expected, 4),
                    "objective": round(total_objective, 4),
                    "emblems": emblems,
                }
            )
        rankings.sort(key=lambda row: (-row["objective"], -row["expected_raw_points"], row["team_id"]))
        if profile == StrategyProfile.TOP_100 and rankings:
            expected_best = max(row["expected_raw_points"] for row in rankings)
            eligible = [row for row in rankings if row["expected_raw_points"] >= expected_best * 0.85]
            ineligible = [row for row in rankings if row not in eligible]
            rankings = eligible + ineligible
        return rankings

    def stat_priority_guide(self, *, period: str) -> dict[str, Any]:
        periods = {item["id"]: item for item in self.rules["fantasy"]["periods"]}
        if period not in periods:
            raise ValueError(f"unknown Fantasy period: {period}")
        banner_slots = int(periods[period]["banner_slots"])
        profile_z = {"stable": -0.85, "expected": 0.0, "upside": 1.65}
        team_by_id = {team.team_id: team for team in self.manifest.teams}
        role_guides: dict[str, Any] = {}

        for role in ("core", "mid", "support"):
            expected_rankings = self._role_rankings(
                role,
                StrategyProfile.EXPECTED_POINTS,
                banner_slots,
            )
            cohort_size = max(1, ceil(len(expected_rankings) * 0.25))
            cohort = expected_rankings[:cohort_size]
            cohort_teams = [team_by_id[int(item["team_id"])] for item in cohort]
            colors = list(dict.fromkeys(self.rules["fantasy"]["role_banners"][role][:banner_slots]))
            color_guides: dict[str, Any] = {}

            for color in colors:
                summaries: list[dict[str, Any]] = []
                for stat_id, rule in self.rules["fantasy"]["stats"].items():
                    if rule["color"] != color:
                        continue
                    team_rows = [self._team_stat(team, role, stat_id) for team in cohort_teams]
                    provenance = str(rule["provenance"])
                    minimum_coverage = 0.5 if provenance in {"exact", "derived"} else 0.0
                    usable = [
                        row
                        for row in team_rows
                        if (
                            float(row["coverage"]) >= minimum_coverage
                            if minimum_coverage > 0.0
                            else float(row["coverage"]) > 0.0
                        )
                    ]
                    values: dict[str, float | None] = {}
                    for name, z_value in profile_z.items():
                        values[name] = (
                            float(
                                np.mean(
                                    [
                                        max(
                                            0.0,
                                            float(row["mean"]) + z_value * float(row["std"]),
                                        )
                                        for row in usable
                                    ]
                                )
                            )
                            if usable
                            else None
                        )
                    average_coverage = (
                        float(np.mean([float(row["coverage"]) for row in team_rows])) if team_rows else 0.0
                    )
                    summaries.append(
                        {
                            "stat_id": stat_id,
                            "label": rule["label"],
                            "provenance": provenance,
                            "coverage": round(average_coverage, 6),
                            "cohort_teams_with_data": len(usable),
                            "cohort_team_count": len(cohort_teams),
                            "default_eligible": (
                                provenance in {"exact", "derived"}
                                and len(usable) == len(cohort_teams)
                                and average_coverage >= 0.5
                            ),
                            "values": {
                                name: None if value is None else round(value, 4)
                                for name, value in values.items()
                            },
                        }
                    )

                ranked_profiles: dict[str, list[dict[str, Any]]] = {}
                for name in profile_z:
                    eligible = [
                        row
                        for row in summaries
                        if row["default_eligible"] and row["values"][name] is not None
                    ]
                    eligible.sort(key=lambda row: (-float(row["values"][name]), str(row["stat_id"])))
                    best_value = float(eligible[0]["values"][name]) if eligible else 0.0
                    ranked_profiles[name] = [
                        {
                            "rank": index,
                            "stat_id": row["stat_id"],
                            "label": row["label"],
                            "score": row["values"][name],
                            "relative_to_best": round(
                                float(row["values"][name]) / best_value,
                                4,
                            )
                            if best_value > 0.0
                            else None,
                            "coverage": row["coverage"],
                            "provenance": row["provenance"],
                        }
                        for index, row in enumerate(eligible, start=1)
                    ]

                sensitivity = [
                    row
                    for row in summaries
                    if not row["default_eligible"] and row["values"]["expected"] is not None
                ]
                sensitivity.sort(key=lambda row: (-float(row["values"]["expected"]), str(row["stat_id"])))
                color_guides[color] = {
                    "profiles": ranked_profiles,
                    "sensitivity_only": sensitivity,
                }

            role_guides[role] = {
                "cohort": [
                    {
                        "team_id": int(item["team_id"]),
                        "team": item["team"],
                        "players": item["players"],
                    }
                    for item in cohort
                ],
                "colors": color_guides,
            }

        return {
            "period": period,
            "as_of": self.as_of.isoformat().replace("+00:00", "Z"),
            "cohort_rule": "top_25_percent_teams_by_expected_role_banner_score",
            "profiles": {
                "stable": "mean_minus_0.85_standard_deviations_clipped_at_zero",
                "expected": "weighted_mean",
                "upside": "mean_plus_1.65_standard_deviations",
            },
            "default_evidence": "exact_or_derived_with_at_least_50_percent_coverage_for_every_cohort_team",
            "proxy_policy": "report_separately_as_sensitivity_only",
            "roles": role_guides,
        }

    def recommend(self, *, period: str, profile: StrategyProfile) -> Recommendation:
        periods = {item["id"]: item for item in self.rules["fantasy"]["periods"]}
        if period not in periods:
            raise ValueError(f"unknown Fantasy period: {period}")
        banner_slots = int(periods[period]["banner_slots"])
        rankings = {
            role: self._role_rankings(role, profile, banner_slots) for role in ("core", "mid", "support")
        }
        no_data = self.observations.empty
        selected_unavailable = any(
            not rankings[role]
            or any(emblem.get("status") == "unavailable" for emblem in rankings[role][0]["emblems"])
            for role in rankings
        )
        selected_low_sample = any(
            rankings[role]
            and any(
                emblem.get("min_player_observations", 0) < 8
                for emblem in rankings[role][0]["emblems"]
                if emblem.get("status") != "unavailable"
            )
            for role in rankings
        )
        warnings = [
            "默认推荐只使用 exact/derived 且覆盖率至少 50% 的统计；proxy 字段仅显示在覆盖审计中。",
            "当前为通用战旗推荐，尚未读取个人徽标库存与重选选项。",
            "本通用入口未加载客户端英雄分类；Title 请使用独立的 title-evidence 入口。",
        ]
        if profile != StrategyProfile.EXPECTED_POINTS:
            warnings.append("总体 Fantasy 分位表尚未由服务器确认，尾部目标为低置信代理。")
        if selected_low_sample:
            warnings.append("至少一项首选徽标有当前定位选手少于 8 局样本，推荐不可发布。")
        status = "blocked" if no_data or selected_unavailable or selected_low_sample else "warning"
        confidence = (
            "unavailable" if no_data else ("low" if profile != StrategyProfile.EXPECTED_POINTS else "medium")
        )
        top_selection = {role: rankings[role][0] if rankings[role] else None for role in rankings}
        objective = (
            sum(float(value["objective"]) for value in top_selection.values() if value is not None)
            if not no_data
            else None
        )
        return Recommendation(
            recommendation_type="fantasy",
            profile=profile,
            as_of=self.as_of,
            generated_at=self.as_of,
            status=status,
            objective_value=round(objective, 4) if objective is not None else None,
            confidence=confidence,
            selections={
                "period": period,
                "banner_slots": banner_slots,
                "recommended": top_selection,
                "role_rankings": {role: rows[:8] for role, rows in rankings.items()},
                "title": {
                    "status": "standalone_evidence_required",
                    "command": "ti fantasy title-evidence",
                    "reason": "Title 统一由客户端英雄分类与原始比赛详情入口计算。",
                },
                "coverage": self.coverage(),
            },
            warnings=warnings,
        )
