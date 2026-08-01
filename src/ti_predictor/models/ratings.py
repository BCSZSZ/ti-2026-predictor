from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import log, pi, sqrt
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss

from ti_predictor.schemas import AuditIssue, as_utc


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


@dataclass
class ModelReport:
    model_name: str
    training_matches: int
    validation_matches: int
    metrics: dict[str, dict[str, float]]
    calibration_matches: int = 0
    issues: list[AuditIssue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "training_matches": self.training_matches,
            "calibration_matches": self.calibration_matches,
            "validation_matches": self.validation_matches,
            "metrics": self.metrics,
            "issues": [issue.model_dump(mode="json") for issue in self.issues],
        }


GLICKO_Q = log(10.0) / 400.0


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
        default_rating: float = 1500.0,
        scale: float = 400.0,
        calibrator: IsotonicRegression | None = None,
        calibration_bounds: tuple[float, float] = (0.03, 0.97),
        matches_played: dict[int, int] | None = None,
        glicko_ratings: dict[int, float] | None = None,
        glicko_deviations: dict[int, float] | None = None,
    ) -> None:
        self.ratings = {int(team_id): float(value) for team_id, value in ratings.items()}
        self.default_rating = float(default_rating)
        self.scale = float(scale)
        self.calibrator = calibrator
        self.calibration_bounds = calibration_bounds
        self.matches_played = {int(key): int(value) for key, value in (matches_played or {}).items()}
        self.glicko_ratings = {int(key): float(value) for key, value in (glicko_ratings or {}).items()}
        self.glicko_deviations = {int(key): float(value) for key, value in (glicko_deviations or {}).items()}

    def rating(self, team_id: int) -> float:
        return self.ratings.get(int(team_id), self.default_rating)

    def strength_rating(self, team_id: int) -> float:
        elo = self.rating(team_id)
        glicko = self.glicko_ratings.get(int(team_id))
        return (elo + glicko) / 2.0 if glicko is not None else elo

    def raw_probability(self, team_a: int, team_b: int) -> float:
        elo = elo_probability(self.rating(team_a), self.rating(team_b), self.scale)
        if team_a not in self.glicko_ratings or team_b not in self.glicko_ratings:
            return elo
        glicko = glicko_probability(
            self.glicko_ratings[team_a],
            self.glicko_deviations.get(team_a, 350.0),
            self.glicko_ratings[team_b],
            self.glicko_deviations.get(team_b, 350.0),
        )
        return (elo + glicko) / 2.0

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
            "type": ("time_decay_elo_glicko_isotonic" if self.calibrator else "time_decay_elo_glicko"),
            "default_rating": self.default_rating,
            "scale": self.scale,
            "ratings": {str(key): value for key, value in sorted(self.ratings.items())},
            "glicko_ratings": {str(key): value for key, value in sorted(self.glicko_ratings.items())},
            "glicko_deviations": {str(key): value for key, value in sorted(self.glicko_deviations.items())},
            "matches_played": {str(key): value for key, value in sorted(self.matches_played.items())},
        }


@dataclass
class _EloState:
    ratings: dict[int, float]
    last_seen: dict[int, datetime]
    matches_played: dict[int, int]


@dataclass
class _GlickoState:
    ratings: dict[int, float]
    deviations: dict[int, float]
    last_seen: dict[int, datetime]


def _decayed_rating(
    state: _EloState,
    team_id: int,
    at: datetime,
    *,
    initial: float,
    half_life_days: float,
) -> float:
    current = state.ratings.get(team_id, initial)
    previous = state.last_seen.get(team_id)
    if previous is None or half_life_days <= 0:
        return current
    idle_days = max(0.0, (at - previous).total_seconds() / 86400.0)
    retention = 0.5 ** (idle_days / half_life_days)
    return initial + (current - initial) * retention


def _inflated_deviation(
    state: _GlickoState,
    team_id: int,
    at: datetime,
    *,
    initial_deviation: float,
) -> float:
    deviation = state.deviations.get(team_id, initial_deviation)
    previous = state.last_seen.get(team_id)
    if previous is None:
        return deviation
    idle_days = max(0.0, (at - previous).total_seconds() / 86400.0)
    return min(initial_deviation, sqrt(deviation**2 + 35.0**2 * idle_days / 30.0))


def _prepare(matches: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    required = {"start_time", "radiant_team_id", "dire_team_id", "radiant_win"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"match data is missing required columns: {sorted(missing)}")
    frame = matches.copy()
    frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True)
    frame = frame.loc[
        frame["start_time"].notna()
        & (frame["start_time"] <= pd.Timestamp(as_of))
        & frame["radiant_team_id"].notna()
        & frame["dire_team_id"].notna()
        & frame["radiant_win"].notna()
    ].copy()
    frame["radiant_team_id"] = frame["radiant_team_id"].astype(int)
    frame["dire_team_id"] = frame["dire_team_id"].astype(int)
    frame["radiant_win"] = frame["radiant_win"].astype(bool)
    return frame.sort_values(["start_time", "match_id"], kind="stable").reset_index(drop=True)


def _sequential_elo(
    matches: pd.DataFrame,
    *,
    initial: float,
    k_factor: float,
    half_life_days: float,
    scale: float,
) -> tuple[_EloState, np.ndarray, np.ndarray]:
    state = _EloState(ratings={}, last_seen={}, matches_played={})
    predictions: list[float] = []
    outcomes: list[float] = []
    for row in matches.itertuples(index=False):
        at = row.start_time.to_pydatetime().astimezone(UTC)
        radiant_id = int(row.radiant_team_id)
        dire_id = int(row.dire_team_id)
        radiant_rating = _decayed_rating(
            state, radiant_id, at, initial=initial, half_life_days=half_life_days
        )
        dire_rating = _decayed_rating(state, dire_id, at, initial=initial, half_life_days=half_life_days)
        prediction = elo_probability(radiant_rating, dire_rating, scale)
        outcome = float(bool(row.radiant_win))
        delta = k_factor * (outcome - prediction)
        state.ratings[radiant_id] = radiant_rating + delta
        state.ratings[dire_id] = dire_rating - delta
        state.last_seen[radiant_id] = at
        state.last_seen[dire_id] = at
        state.matches_played[radiant_id] = state.matches_played.get(radiant_id, 0) + 1
        state.matches_played[dire_id] = state.matches_played.get(dire_id, 0) + 1
        predictions.append(prediction)
        outcomes.append(outcome)
    return state, np.asarray(predictions), np.asarray(outcomes)


def _glicko_update(
    rating: float,
    deviation: float,
    opponent_rating: float,
    opponent_deviation: float,
    outcome: float,
) -> tuple[float, float]:
    g_value = _glicko_g(opponent_deviation)
    expectation = 1.0 / (1.0 + 10.0 ** (-g_value * (rating - opponent_rating) / 400.0))
    variance = 1.0 / (GLICKO_Q**2 * g_value**2 * expectation * (1.0 - expectation))
    precision = 1.0 / deviation**2 + 1.0 / variance
    return (
        rating + GLICKO_Q / precision * g_value * (outcome - expectation),
        sqrt(1.0 / precision),
    )


def _sequential_glicko(
    matches: pd.DataFrame,
    *,
    initial: float,
    initial_deviation: float = 350.0,
) -> tuple[_GlickoState, np.ndarray]:
    state = _GlickoState(ratings={}, deviations={}, last_seen={})
    predictions: list[float] = []
    for row in matches.itertuples(index=False):
        at = row.start_time.to_pydatetime().astimezone(UTC)
        radiant_id = int(row.radiant_team_id)
        dire_id = int(row.dire_team_id)
        radiant_rating = state.ratings.get(radiant_id, initial)
        dire_rating = state.ratings.get(dire_id, initial)
        radiant_deviation = _inflated_deviation(state, radiant_id, at, initial_deviation=initial_deviation)
        dire_deviation = _inflated_deviation(state, dire_id, at, initial_deviation=initial_deviation)
        predictions.append(
            glicko_probability(
                radiant_rating,
                radiant_deviation,
                dire_rating,
                dire_deviation,
            )
        )
        outcome = float(bool(row.radiant_win))
        state.ratings[radiant_id], state.deviations[radiant_id] = _glicko_update(
            radiant_rating,
            radiant_deviation,
            dire_rating,
            dire_deviation,
            outcome,
        )
        state.ratings[dire_id], state.deviations[dire_id] = _glicko_update(
            dire_rating,
            dire_deviation,
            radiant_rating,
            radiant_deviation,
            1.0 - outcome,
        )
        state.last_seen[radiant_id] = at
        state.last_seen[dire_id] = at
    return state, np.asarray(predictions)


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


def fit_team_strengths(
    matches: pd.DataFrame,
    *,
    as_of: datetime,
    initial: float = 1500.0,
    k_factor: float = 28.0,
    half_life_days: float = 120.0,
    scale: float = 400.0,
) -> tuple[TeamStrengthModel, ModelReport]:
    cutoff = as_utc(as_of)
    frame = _prepare(matches, cutoff)
    issues: list[AuditIssue] = []
    if frame.empty:
        issues.append(
            AuditIssue(
                code="model-no-matches",
                severity="blocking",
                message="No completed matches are available at as_of; all ratings remain at 1500",
            )
        )
        return TeamStrengthModel({}, default_rating=initial, scale=scale), ModelReport(
            model_name="time_decay_elo_glicko",
            training_matches=0,
            validation_matches=0,
            metrics={},
            issues=issues,
        )

    elo_state, elo_predictions, outcomes = _sequential_elo(
        frame,
        initial=initial,
        k_factor=k_factor,
        half_life_days=half_life_days,
        scale=scale,
    )
    glicko_state, glicko_predictions = _sequential_glicko(frame, initial=initial)
    ensemble_predictions = (elo_predictions + glicko_predictions) / 2.0

    train_end = max(1, int(len(frame) * 0.70))
    calibration_end = min(len(frame), max(train_end + 1, int(len(frame) * 0.85)))
    calibration_count = calibration_end - train_end
    validation_count = len(frame) - calibration_end
    calibration_slice = slice(train_end, calibration_end)
    validation_slice = slice(calibration_end, len(frame))
    calibrator: IsotonicRegression | None = None
    report_metrics: dict[str, dict[str, float]] = {}

    enough_temporal_data = (
        calibration_count >= 20
        and validation_count >= 20
        and len(np.unique(outcomes[calibration_slice])) == 2
        and len(np.unique(outcomes[validation_slice])) == 2
    )
    if enough_temporal_data:
        evaluation_calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.03, y_max=0.97)
        evaluation_calibrator.fit(ensemble_predictions[calibration_slice], outcomes[calibration_slice])
        validation_outcomes = outcomes[validation_slice]
        calibrated = evaluation_calibrator.predict(ensemble_predictions[validation_slice])
        report_metrics["elo"] = _metrics(validation_outcomes, elo_predictions[validation_slice])
        report_metrics["glicko"] = _metrics(validation_outcomes, glicko_predictions[validation_slice])
        report_metrics["elo_glicko_ensemble"] = _metrics(
            validation_outcomes, ensemble_predictions[validation_slice]
        )
        report_metrics["calibrated"] = _metrics(validation_outcomes, calibrated)
        report_metrics["fifty_percent"] = _metrics(
            validation_outcomes, np.full(validation_count, 0.5, dtype=float)
        )
        calibrated_metrics = report_metrics["calibrated"]
        ensemble_metrics = report_metrics["elo_glicko_ensemble"]
        if (
            calibrated_metrics["log_loss"] <= ensemble_metrics["log_loss"]
            and calibrated_metrics["calibration_error"] <= ensemble_metrics["calibration_error"]
        ):
            # Fit the deployment curve only after the honest evaluation accepts it.
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.03, y_max=0.97)
            calibrator.fit(ensemble_predictions[train_end:], outcomes[train_end:])
        else:
            issues.append(
                AuditIssue(
                    code="model-calibration-rejected",
                    severity="warning",
                    message=(
                        "Temporal holdout rejected isotonic calibration; deploy the raw Elo/Glicko ensemble"
                    ),
                    context={
                        "calibrated_log_loss": calibrated_metrics["log_loss"],
                        "ensemble_log_loss": ensemble_metrics["log_loss"],
                        "calibrated_ece": calibrated_metrics["calibration_error"],
                        "ensemble_ece": ensemble_metrics["calibration_error"],
                    },
                )
            )
    else:
        issues.append(
            AuditIssue(
                code="model-calibration-insufficient",
                severity="warning",
                message="Temporal calibration/validation windows are too small; calibration was not fitted",
                context={
                    "calibration_matches": calibration_count,
                    "validation_matches": validation_count,
                },
            )
        )
        if len(outcomes) >= 2 and len(np.unique(outcomes)) == 2:
            report_metrics["elo_in_sample"] = _metrics(outcomes, elo_predictions)
            report_metrics["glicko_in_sample"] = _metrics(outcomes, glicko_predictions)
            report_metrics["fifty_percent_in_sample"] = _metrics(
                outcomes, np.full(len(outcomes), 0.5, dtype=float)
            )

    model = TeamStrengthModel(
        elo_state.ratings,
        default_rating=initial,
        scale=scale,
        calibrator=calibrator,
        matches_played=elo_state.matches_played,
        glicko_ratings=glicko_state.ratings,
        glicko_deviations=glicko_state.deviations,
    )
    return model, ModelReport(
        model_name=("time_decay_elo_glicko_isotonic" if calibrator else "time_decay_elo_glicko"),
        training_matches=train_end,
        calibration_matches=calibration_count,
        validation_matches=validation_count,
        metrics=report_metrics,
        issues=issues,
    )
