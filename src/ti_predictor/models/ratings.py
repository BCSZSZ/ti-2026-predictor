from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import log, pi, sqrt
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss

from ti_predictor.models.evidence import (
    build_evidence_set,
    prepare_completed_games,
)
from ti_predictor.models.policy import TeamStrengthPolicy
from ti_predictor.schemas import AuditIssue, as_utc

GLICKO_Q = log(10.0) / 400.0
UNWEIGHTED_BASELINE_HALF_LIFE_DAYS = 120.0


def _deduplicate_issues(issues: list[AuditIssue]) -> list[AuditIssue]:
    result: list[AuditIssue] = []
    seen: set[tuple[str, str, str, str]] = set()
    for issue in issues:
        key = (
            issue.code,
            issue.severity,
            issue.message,
            json.dumps(issue.context, sort_keys=True, default=str),
        )
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def elo_probability(rating_a: float, rating_b: float, scale: float = 400.0) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / scale))


def _ece(y_true: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    result = 0.0
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        mask = (probabilities >= lower) & (probabilities <= upper if upper == 1.0 else probabilities < upper)
        if not mask.any():
            continue
        result += float(mask.mean()) * abs(float(y_true[mask].mean()) - float(probabilities[mask].mean()))
    return result


def _metrics(y_true: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    return {
        "log_loss": float(log_loss(y_true, clipped, labels=[0, 1])),
        "brier": float(brier_score_loss(y_true, clipped)),
        "calibration_error": _ece(y_true, clipped),
        "accuracy": float(((clipped >= 0.5) == y_true).mean()),
    }


def probability_metrics(y_true: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return _metrics(np.asarray(y_true, dtype=float), np.asarray(probability, dtype=float))


@dataclass
class ModelReport:
    model_name: str
    training_matches: int
    validation_matches: int
    metrics: dict[str, dict[str, float]]
    calibration_matches: int = 0
    policy_id: str | None = None
    target_patch_family: str | None = None
    previous_patch_family: str | None = None
    evidence_audit: dict[str, Any] = field(default_factory=dict)
    rolling_validation: dict[str, Any] = field(default_factory=dict)
    issues: list[AuditIssue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "policy_id": self.policy_id,
            "target_patch_family": self.target_patch_family,
            "previous_patch_family": self.previous_patch_family,
            "training_matches": self.training_matches,
            "calibration_matches": self.calibration_matches,
            "validation_matches": self.validation_matches,
            "metrics": self.metrics,
            "evidence_audit": self.evidence_audit,
            "rolling_validation": self.rolling_validation,
            "issues": [issue.model_dump(mode="json") for issue in self.issues],
        }


def _serialize_calibrator(calibrator: IsotonicRegression | None) -> dict[str, Any] | None:
    if calibrator is None or not hasattr(calibrator, "X_thresholds_"):
        return None
    return {
        "x_thresholds": [float(value) for value in calibrator.X_thresholds_],
        "y_thresholds": [float(value) for value in calibrator.y_thresholds_],
        "out_of_bounds": calibrator.out_of_bounds,
        "y_min": calibrator.y_min,
        "y_max": calibrator.y_max,
    }


def _glicko_g(deviation: float) -> float:
    return 1.0 / sqrt(1.0 + 3.0 * GLICKO_Q**2 * deviation**2 / pi**2)


def glicko_probability(
    rating_a: float,
    deviation_a: float,
    rating_b: float,
    deviation_b: float,
) -> float:
    expectation_a = 1.0 / (1.0 + 10.0 ** (-_glicko_g(deviation_b) * (rating_a - rating_b) / 400.0))
    expectation_b = 1.0 / (1.0 + 10.0 ** (-_glicko_g(deviation_a) * (rating_b - rating_a) / 400.0))
    return (expectation_a + (1.0 - expectation_b)) / 2.0


class TeamStrengthModel:
    def __init__(
        self,
        ratings: dict[int, float],
        *,
        model_name: str = "manual_elo",
        default_rating: float = 1500.0,
        scale: float = 400.0,
        elo_weight: float = 0.5,
        glicko_weight: float = 0.5,
        calibrator: IsotonicRegression | None = None,
        calibration_candidate: IsotonicRegression | None = None,
        calibration_bounds: tuple[float, float] = (0.03, 0.97),
        matches_played: dict[int, int] | None = None,
        target_patch_matches: dict[int, int] | None = None,
        effective_weight: dict[int, float] | None = None,
        glicko_ratings: dict[int, float] | None = None,
        glicko_deviations: dict[int, float] | None = None,
        policy_id: str | None = None,
        target_patch_family: str | None = None,
        previous_patch_family: str | None = None,
    ) -> None:
        self.ratings = {int(team_id): float(value) for team_id, value in ratings.items()}
        self.model_name = model_name
        self.default_rating = float(default_rating)
        self.scale = float(scale)
        self.elo_weight = float(elo_weight)
        self.glicko_weight = float(glicko_weight)
        self.calibrator = calibrator
        self.calibration_candidate = calibration_candidate
        self.calibration_bounds = calibration_bounds
        self.matches_played = {int(key): int(value) for key, value in (matches_played or {}).items()}
        self.target_patch_matches = {
            int(key): int(value) for key, value in (target_patch_matches or {}).items()
        }
        self.effective_weight = {int(key): float(value) for key, value in (effective_weight or {}).items()}
        self.glicko_ratings = {int(key): float(value) for key, value in (glicko_ratings or {}).items()}
        self.glicko_deviations = {int(key): float(value) for key, value in (glicko_deviations or {}).items()}
        self.policy_id = policy_id
        self.target_patch_family = target_patch_family
        self.previous_patch_family = previous_patch_family

    def rating(self, team_id: int) -> float:
        return self.ratings.get(int(team_id), self.default_rating)

    def strength_rating(self, team_id: int) -> float:
        elo = self.rating(team_id)
        glicko = self.glicko_ratings.get(int(team_id))
        if glicko is None:
            return elo
        return self.elo_weight * elo + self.glicko_weight * glicko

    def component_probabilities(self, team_a: int, team_b: int) -> tuple[float, float]:
        elo = elo_probability(self.rating(team_a), self.rating(team_b), self.scale)
        if team_a not in self.glicko_ratings or team_b not in self.glicko_ratings:
            return elo, elo
        glicko = glicko_probability(
            self.glicko_ratings[team_a],
            self.glicko_deviations.get(team_a, 350.0),
            self.glicko_ratings[team_b],
            self.glicko_deviations.get(team_b, 350.0),
        )
        return elo, glicko

    def raw_probability(self, team_a: int, team_b: int) -> float:
        elo, glicko = self.component_probabilities(team_a, team_b)
        return self.elo_weight * elo + self.glicko_weight * glicko

    def candidate_calibrated_probability(self, team_a: int, team_b: int) -> float:
        raw = self.raw_probability(team_a, team_b)
        if self.calibration_candidate is None:
            return raw
        calibrated = float(self.calibration_candidate.predict([raw])[0])
        return float(np.clip(calibrated, *self.calibration_bounds))

    def predict(self, team_a: int, team_b: int) -> float:
        raw = self.raw_probability(team_a, team_b)
        if self.calibrator is None:
            return raw
        calibrated = float(self.calibrator.predict([raw])[0])
        return float(np.clip(calibrated, *self.calibration_bounds))

    def ranked(self, team_ids: list[int]) -> list[tuple[int, float]]:
        return sorted(
            ((team_id, self.strength_rating(team_id)) for team_id in team_ids),
            key=lambda item: -item[1],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.model_name,
            "policy_id": self.policy_id,
            "target_patch_family": self.target_patch_family,
            "previous_patch_family": self.previous_patch_family,
            "default_rating": self.default_rating,
            "scale": self.scale,
            "ensemble_weights": {"elo": self.elo_weight, "glicko": self.glicko_weight},
            "calibration_accepted": self.calibrator is not None,
            "calibrator": _serialize_calibrator(self.calibrator),
            "calibration_candidate": _serialize_calibrator(self.calibration_candidate),
            "ratings": {str(key): value for key, value in sorted(self.ratings.items())},
            "glicko_ratings": {str(key): value for key, value in sorted(self.glicko_ratings.items())},
            "glicko_deviations": {str(key): value for key, value in sorted(self.glicko_deviations.items())},
            "matches_played": {str(key): value for key, value in sorted(self.matches_played.items())},
            "target_patch_matches": {
                str(key): value for key, value in sorted(self.target_patch_matches.items())
            },
            "effective_weight": {str(key): value for key, value in sorted(self.effective_weight.items())},
        }


@dataclass
class _EloState:
    ratings: dict[int, float] = field(default_factory=dict)
    matches_played: dict[int, int] = field(default_factory=dict)
    target_patch_matches: dict[int, int] = field(default_factory=dict)
    effective_weight: dict[int, float] = field(default_factory=dict)


@dataclass
class _BaselineEloState:
    ratings: dict[int, float] = field(default_factory=dict)
    last_seen: dict[int, datetime] = field(default_factory=dict)
    matches_played: dict[int, int] = field(default_factory=dict)


@dataclass
class _GlickoState:
    ratings: dict[int, float] = field(default_factory=dict)
    deviations: dict[int, float] = field(default_factory=dict)
    last_seen: dict[int, datetime] = field(default_factory=dict)


def _weighted_sequential_elo(
    matches: pd.DataFrame,
    *,
    initial: float,
    k_factor: float,
    scale: float,
    target_patch_family: str,
) -> _EloState:
    state = _EloState()
    for row in matches.itertuples(index=False):
        radiant_id = int(row.radiant_team_id)
        dire_id = int(row.dire_team_id)
        radiant_rating = state.ratings.get(radiant_id, initial)
        dire_rating = state.ratings.get(dire_id, initial)
        prediction = elo_probability(radiant_rating, dire_rating, scale)
        outcome = float(bool(row.radiant_win))
        weight = float(row.evidence_weight)
        delta = k_factor * weight * (outcome - prediction)
        state.ratings[radiant_id] = radiant_rating + delta
        state.ratings[dire_id] = dire_rating - delta
        for team_id in (radiant_id, dire_id):
            state.matches_played[team_id] = state.matches_played.get(team_id, 0) + 1
            state.effective_weight[team_id] = state.effective_weight.get(team_id, 0.0) + weight
            if row.patch_family == target_patch_family:
                state.target_patch_matches[team_id] = state.target_patch_matches.get(team_id, 0) + 1
    return state


def _baseline_decayed_rating(
    state: _BaselineEloState,
    team_id: int,
    at: datetime,
    *,
    initial: float,
) -> float:
    current = state.ratings.get(team_id, initial)
    previous = state.last_seen.get(team_id)
    if previous is None:
        return current
    idle_days = max(0.0, (at - previous).total_seconds() / 86400.0)
    retention = 0.5 ** (idle_days / UNWEIGHTED_BASELINE_HALF_LIFE_DAYS)
    return initial + (current - initial) * retention


def _baseline_sequential_elo(
    matches: pd.DataFrame,
    *,
    initial: float,
    k_factor: float,
    scale: float,
) -> _BaselineEloState:
    """Reproduce the superseded model only for the preregistered benchmark."""
    state = _BaselineEloState()
    for row in matches.itertuples(index=False):
        at = row.start_time.to_pydatetime().astimezone(UTC)
        radiant_id = int(row.radiant_team_id)
        dire_id = int(row.dire_team_id)
        radiant_rating = _baseline_decayed_rating(state, radiant_id, at, initial=initial)
        dire_rating = _baseline_decayed_rating(state, dire_id, at, initial=initial)
        prediction = elo_probability(radiant_rating, dire_rating, scale)
        outcome = float(bool(row.radiant_win))
        delta = k_factor * (outcome - prediction)
        state.ratings[radiant_id] = radiant_rating + delta
        state.ratings[dire_id] = dire_rating - delta
        state.last_seen[radiant_id] = at
        state.last_seen[dire_id] = at
        state.matches_played[radiant_id] = state.matches_played.get(radiant_id, 0) + 1
        state.matches_played[dire_id] = state.matches_played.get(dire_id, 0) + 1
    return state


def _inflated_deviation_value(
    deviation: float,
    previous: datetime | None,
    at: datetime,
    *,
    initial_deviation: float,
    increase_per_30_days: float,
) -> float:
    if previous is None:
        return deviation
    idle_days = max(0.0, (at - previous).total_seconds() / 86400.0)
    return min(
        initial_deviation,
        sqrt(deviation**2 + increase_per_30_days**2 * idle_days / 30.0),
    )


def _glicko_update(
    rating: float,
    deviation: float,
    opponent_rating: float,
    opponent_deviation: float,
    outcome: float,
    *,
    weight: float,
) -> tuple[float, float]:
    if weight <= 0.0:
        return rating, deviation
    g_value = _glicko_g(opponent_deviation)
    expectation = 1.0 / (1.0 + 10.0 ** (-g_value * (rating - opponent_rating) / 400.0))
    information = weight * GLICKO_Q**2 * g_value**2 * expectation * (1.0 - expectation)
    precision = 1.0 / deviation**2 + information
    score = weight * g_value * (outcome - expectation)
    return rating + GLICKO_Q / precision * score, sqrt(1.0 / precision)


def _sequential_glicko(
    matches: pd.DataFrame,
    *,
    initial: float,
    initial_deviation: float,
    increase_per_30_days: float,
    weighted: bool,
) -> _GlickoState:
    state = _GlickoState()
    for row in matches.itertuples(index=False):
        at = row.start_time.to_pydatetime().astimezone(UTC)
        radiant_id = int(row.radiant_team_id)
        dire_id = int(row.dire_team_id)
        radiant_rating = state.ratings.get(radiant_id, initial)
        dire_rating = state.ratings.get(dire_id, initial)
        radiant_deviation = _inflated_deviation_value(
            state.deviations.get(radiant_id, initial_deviation),
            state.last_seen.get(radiant_id),
            at,
            initial_deviation=initial_deviation,
            increase_per_30_days=increase_per_30_days,
        )
        dire_deviation = _inflated_deviation_value(
            state.deviations.get(dire_id, initial_deviation),
            state.last_seen.get(dire_id),
            at,
            initial_deviation=initial_deviation,
            increase_per_30_days=increase_per_30_days,
        )
        outcome = float(bool(row.radiant_win))
        weight = float(row.evidence_weight) if weighted else 1.0
        state.ratings[radiant_id], state.deviations[radiant_id] = _glicko_update(
            radiant_rating,
            radiant_deviation,
            dire_rating,
            dire_deviation,
            outcome,
            weight=weight,
        )
        state.ratings[dire_id], state.deviations[dire_id] = _glicko_update(
            dire_rating,
            dire_deviation,
            radiant_rating,
            radiant_deviation,
            1.0 - outcome,
            weight=weight,
        )
        state.last_seen[radiant_id] = at
        state.last_seen[dire_id] = at
    return state


def _model_from_weighted_matches(
    matches: pd.DataFrame,
    *,
    policy: TeamStrengthPolicy,
    target_patch_family: str,
    previous_patch_family: str | None,
    calibrator: IsotonicRegression | None = None,
    calibration_candidate: IsotonicRegression | None = None,
) -> TeamStrengthModel:
    elo_state = _weighted_sequential_elo(
        matches,
        initial=policy.elo.initial_rating,
        k_factor=policy.elo.k_factor,
        scale=policy.elo.scale,
        target_patch_family=target_patch_family,
    )
    glicko_state = _sequential_glicko(
        matches,
        initial=policy.glicko.initial_rating,
        initial_deviation=policy.glicko.initial_deviation,
        increase_per_30_days=policy.glicko.deviation_increase_per_30_days,
        weighted=True,
    )
    name = "patch_tier_time_weighted_elo_glicko"
    if calibrator is not None:
        name += "_isotonic"
    return TeamStrengthModel(
        elo_state.ratings,
        model_name=name,
        default_rating=policy.elo.initial_rating,
        scale=policy.elo.scale,
        elo_weight=policy.ensemble.elo_weight,
        glicko_weight=policy.ensemble.glicko_weight,
        calibrator=calibrator,
        calibration_candidate=calibration_candidate,
        calibration_bounds=(
            policy.calibration.probability_floor,
            policy.calibration.probability_ceiling,
        ),
        matches_played=elo_state.matches_played,
        target_patch_matches=elo_state.target_patch_matches,
        effective_weight=elo_state.effective_weight,
        glicko_ratings=glicko_state.ratings,
        glicko_deviations=glicko_state.deviations,
        policy_id=policy.policy_id,
        target_patch_family=target_patch_family,
        previous_patch_family=previous_patch_family,
    )


def fit_unweighted_baseline(
    matches: pd.DataFrame,
    *,
    as_of: datetime,
    policy: TeamStrengthPolicy,
) -> TeamStrengthModel:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    frame, _, _ = prepare_completed_games(matches, as_of=cutoff)
    elo_state = _baseline_sequential_elo(
        frame,
        initial=policy.elo.initial_rating,
        k_factor=policy.elo.k_factor,
        scale=policy.elo.scale,
    )
    glicko_state = _sequential_glicko(
        frame,
        initial=policy.glicko.initial_rating,
        initial_deviation=policy.glicko.initial_deviation,
        increase_per_30_days=policy.glicko.deviation_increase_per_30_days,
        weighted=False,
    )
    return TeamStrengthModel(
        elo_state.ratings,
        model_name="unweighted_time_decay_elo_glicko_baseline",
        default_rating=policy.elo.initial_rating,
        scale=policy.elo.scale,
        elo_weight=policy.ensemble.elo_weight,
        glicko_weight=policy.ensemble.glicko_weight,
        matches_played=elo_state.matches_played,
        glicko_ratings=glicko_state.ratings,
        glicko_deviations=glicko_state.deviations,
    )


def _predict_components(
    model: TeamStrengthModel,
    matches: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    elo: list[float] = []
    glicko: list[float] = []
    ensemble: list[float] = []
    for row in matches.itertuples(index=False):
        elo_probability_value, glicko_probability_value = model.component_probabilities(
            int(row.radiant_team_id), int(row.dire_team_id)
        )
        elo.append(elo_probability_value)
        glicko.append(glicko_probability_value)
        ensemble.append(
            model.elo_weight * elo_probability_value + model.glicko_weight * glicko_probability_value
        )
    return np.asarray(elo), np.asarray(glicko), np.asarray(ensemble)


def _rolling_calibration(
    matches: pd.DataFrame,
    patches: pd.DataFrame,
    *,
    as_of: datetime,
    target_patch_family: str,
    policy: TeamStrengthPolicy,
    target_team_ids: Collection[int] | None,
) -> tuple[
    IsotonicRegression | None,
    IsotonicRegression | None,
    dict[str, Any],
    dict[str, dict[str, float]],
    list[AuditIssue],
]:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    prepared, _, structural_issues = prepare_completed_games(matches, as_of=cutoff)
    calibration_evidence = build_evidence_set(
        prepared,
        patches,
        as_of=cutoff,
        policy=policy,
        target_patch_family=target_patch_family,
        target_team_ids=target_team_ids,
    )
    candidates = calibration_evidence.matches.loc[
        calibration_evidence.matches["patch_family"].eq(target_patch_family)
    ].sort_values(["start_time", "match_id"], kind="stable")
    count = len(candidates)
    initial_end = int(count * policy.calibration.rolling_initial_fraction)
    remaining = count - initial_end
    fold_width = remaining / policy.calibration.rolling_folds if remaining > 0 else 0.0
    calibration_issues: list[AuditIssue] = []
    for issue in calibration_evidence.issues:
        if issue.code == "model-target-team-no-evidence":
            calibration_issues.append(
                issue.model_copy(
                    update={
                        "code": "model-calibration-target-team-no-evidence",
                        "message": (
                            "At least one target team has no positive-weight Game in the "
                            "pre-holdout calibration period"
                        ),
                        "context": {**issue.context, "phase": "rolling_calibration"},
                    }
                )
            )
        else:
            calibration_issues.append(issue)
    issues = [*structural_issues, *calibration_issues]
    minimum = policy.calibration.minimum_games_per_window
    if initial_end < minimum or fold_width < minimum:
        issues.append(
            AuditIssue(
                code="model-calibration-insufficient",
                severity="warning",
                message="Pre-holdout rolling windows are too small for isotonic calibration",
                context={
                    "same_patch_games": count,
                    "initial_training_games": initial_end,
                    "nominal_fold_games": fold_width,
                },
            )
        )
        return None, None, {"folds": [], "same_patch_games": count}, {}, issues

    fold_payloads: list[dict[str, Any]] = []
    fold_elo: list[np.ndarray] = []
    fold_glicko: list[np.ndarray] = []
    fold_ensemble: list[np.ndarray] = []
    fold_outcomes: list[np.ndarray] = []
    for fold_index in range(policy.calibration.rolling_folds):
        start = initial_end + int(round(fold_index * fold_width))
        end = initial_end + int(round((fold_index + 1) * fold_width))
        if fold_index == policy.calibration.rolling_folds - 1:
            end = count
        validation = candidates.iloc[start:end].copy()
        if len(validation) < minimum:
            continue
        fold_start = validation["start_time"].min().to_pydatetime().astimezone(UTC)
        training = prepared.loc[prepared["start_time"] < pd.Timestamp(fold_start)]
        evidence = build_evidence_set(
            training,
            patches,
            as_of=fold_start - timedelta(microseconds=1),
            policy=policy,
            target_patch_family=target_patch_family,
            target_team_ids=target_team_ids,
        )
        fold_model = _model_from_weighted_matches(
            evidence.matches,
            policy=policy,
            target_patch_family=evidence.target_patch_family,
            previous_patch_family=evidence.previous_patch_family,
        )
        elo, glicko, ensemble = _predict_components(fold_model, validation)
        outcomes = validation["radiant_win"].to_numpy(dtype=float)
        fold_elo.append(elo)
        fold_glicko.append(glicko)
        fold_ensemble.append(ensemble)
        fold_outcomes.append(outcomes)
        fold_payloads.append(
            {
                "fold": fold_index + 1,
                "as_of": (fold_start - timedelta(microseconds=1)).isoformat().replace("+00:00", "Z"),
                "training_positive_weight_games": len(evidence.matches),
                "training_selected_match_ids_sha256": evidence.audit["selected_match_ids_sha256"],
                "validation_games": len(validation),
            }
        )

    if len(fold_outcomes) != policy.calibration.rolling_folds:
        issues.append(
            AuditIssue(
                code="model-calibration-incomplete-folds",
                severity="warning",
                message="Not all preregistered rolling folds could be evaluated",
                context={"completed_folds": len(fold_outcomes)},
            )
        )
        return None, None, {"folds": fold_payloads, "same_patch_games": count}, {}, issues

    calibration_raw = np.concatenate(fold_ensemble[:-1])
    calibration_outcomes = np.concatenate(fold_outcomes[:-1])
    validation_raw = fold_ensemble[-1]
    validation_outcomes = fold_outcomes[-1]
    if len(np.unique(calibration_outcomes)) != 2 or len(np.unique(validation_outcomes)) != 2:
        issues.append(
            AuditIssue(
                code="model-calibration-single-class",
                severity="warning",
                message="Rolling calibration or validation contains only one outcome class",
            )
        )
        return None, None, {"folds": fold_payloads, "same_patch_games": count}, {}, issues

    evaluation_calibrator = IsotonicRegression(
        out_of_bounds="clip",
        y_min=policy.calibration.probability_floor,
        y_max=policy.calibration.probability_ceiling,
    )
    evaluation_calibrator.fit(calibration_raw, calibration_outcomes)
    validation_calibrated = evaluation_calibrator.predict(validation_raw)
    metrics = {
        "weighted_elo": _metrics(validation_outcomes, fold_elo[-1]),
        "weighted_glicko": _metrics(validation_outcomes, fold_glicko[-1]),
        "weighted_ensemble": _metrics(validation_outcomes, validation_raw),
        "calibrated_candidate": _metrics(validation_outcomes, validation_calibrated),
        "fifty_percent": _metrics(validation_outcomes, np.full(len(validation_outcomes), 0.5, dtype=float)),
    }
    accepted = (
        metrics["calibrated_candidate"]["log_loss"] <= metrics["weighted_ensemble"]["log_loss"]
        and metrics["calibrated_candidate"]["calibration_error"]
        <= metrics["weighted_ensemble"]["calibration_error"]
    )
    all_raw = np.concatenate(fold_ensemble)
    all_outcomes = np.concatenate(fold_outcomes)
    candidate = IsotonicRegression(
        out_of_bounds="clip",
        y_min=policy.calibration.probability_floor,
        y_max=policy.calibration.probability_ceiling,
    )
    candidate.fit(all_raw, all_outcomes)
    deployed = candidate if accepted else None
    if not accepted:
        issues.append(
            AuditIssue(
                code="model-calibration-rejected",
                severity="warning",
                message="Pre-holdout rolling validation rejected isotonic calibration",
                context={
                    "calibrated_log_loss": metrics["calibrated_candidate"]["log_loss"],
                    "ensemble_log_loss": metrics["weighted_ensemble"]["log_loss"],
                    "calibrated_ece": metrics["calibrated_candidate"]["calibration_error"],
                    "ensemble_ece": metrics["weighted_ensemble"]["calibration_error"],
                },
            )
        )
    rolling = {
        "target_patch_family": target_patch_family,
        "evidence_scope_mode": policy.evidence_scope.mode,
        "selected_match_ids_sha256": calibration_evidence.audit["selected_match_ids_sha256"],
        "cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "same_patch_games": count,
        "initial_fraction": policy.calibration.rolling_initial_fraction,
        "folds": fold_payloads,
        "calibration_games": int(sum(len(values) for values in fold_outcomes[:-1])),
        "validation_games": int(len(fold_outcomes[-1])),
        "calibration_accepted": accepted,
    }
    return deployed, candidate, rolling, metrics, issues


def fit_team_strengths(
    matches: pd.DataFrame,
    patches: pd.DataFrame,
    *,
    as_of: datetime,
    policy: TeamStrengthPolicy,
    target_patch_family: str | None = None,
    target_team_ids: Collection[int] | None = None,
    calibration_as_of: datetime | None = None,
    calibration_target_patch_family: str | None = None,
) -> tuple[TeamStrengthModel, ModelReport]:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    issues: list[AuditIssue] = []
    try:
        evidence = build_evidence_set(
            matches,
            patches,
            as_of=cutoff,
            policy=policy,
            target_patch_family=target_patch_family,
            target_team_ids=target_team_ids,
        )
    except ValueError as error:
        issue = AuditIssue(
            code="model-evidence-policy-error",
            severity="blocking",
            message=str(error),
        )
        empty = TeamStrengthModel(
            {},
            model_name="patch_tier_time_weighted_elo_glicko",
            default_rating=policy.elo.initial_rating,
            scale=policy.elo.scale,
            policy_id=policy.policy_id,
        )
        return empty, ModelReport(
            model_name=empty.model_name,
            policy_id=policy.policy_id,
            training_matches=0,
            validation_matches=0,
            metrics={},
            issues=[issue],
        )
    issues.extend(evidence.issues)

    calibrator: IsotonicRegression | None = None
    calibration_candidate: IsotonicRegression | None = None
    rolling: dict[str, Any] = {}
    report_metrics: dict[str, dict[str, float]] = {}
    if calibration_as_of is not None and calibration_target_patch_family is not None:
        (
            calibrator,
            calibration_candidate,
            rolling,
            report_metrics,
            calibration_issues,
        ) = _rolling_calibration(
            matches,
            patches,
            as_of=calibration_as_of,
            target_patch_family=calibration_target_patch_family,
            policy=policy,
            target_team_ids=target_team_ids,
        )
        issues.extend(calibration_issues)
    else:
        issues.append(
            AuditIssue(
                code="model-calibration-not-requested",
                severity="warning",
                message="No frozen pre-holdout rolling calibration cutoff was supplied",
            )
        )

    model = _model_from_weighted_matches(
        evidence.matches,
        policy=policy,
        target_patch_family=evidence.target_patch_family,
        previous_patch_family=evidence.previous_patch_family,
        calibrator=calibrator,
        calibration_candidate=calibration_candidate,
    )
    return model, ModelReport(
        model_name=model.model_name,
        policy_id=policy.policy_id,
        target_patch_family=evidence.target_patch_family,
        previous_patch_family=evidence.previous_patch_family,
        training_matches=len(evidence.matches),
        calibration_matches=int(rolling.get("calibration_games", 0)),
        validation_matches=int(rolling.get("validation_games", 0)),
        metrics=report_metrics,
        evidence_audit=evidence.audit,
        rolling_validation=rolling,
        issues=_deduplicate_issues(issues),
    )
