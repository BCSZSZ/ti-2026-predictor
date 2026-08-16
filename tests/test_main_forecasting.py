from __future__ import annotations

import pandas as pd

from ti_predictor import forecasting
from ti_predictor.models.ratings import ModelReport, TeamStrengthModel
from ti_predictor.paths import ProjectPaths


def test_actual_main_strength_loader_uses_pointer_selected_snapshot(
    project_paths: ProjectPaths,
    monkeypatch,
) -> None:
    snapshot_path = project_paths.data / "processed/snapshots/main-actual-test"
    selected_paths = ProjectPaths(root=project_paths.root, processed_override=snapshot_path)
    selected: list[bool] = []
    reads = []

    def select_main_paths(paths: ProjectPaths, *, require: bool) -> ProjectPaths:
        selected.append(require)
        assert paths == project_paths
        return selected_paths

    def read_processed(path):
        reads.append(path)
        return pd.DataFrame()

    def fit_model(*args, policy, **kwargs):
        model = TeamStrengthModel({}, policy_id=policy.policy_id)
        return model, ModelReport(
            model_name=model.model_name,
            policy_id=policy.policy_id,
            training_matches=0,
            validation_matches=0,
            metrics={},
        )

    monkeypatch.setattr(forecasting, "main_evidence_paths", select_main_paths)
    monkeypatch.setattr(forecasting, "read_parquet_if_exists", read_processed)
    monkeypatch.setattr(forecasting, "fit_team_strengths", fit_model)
    monkeypatch.setattr(
        forecasting,
        "canonicalize_match_team_ids",
        lambda matches, *args, **kwargs: (matches, {}),
    )

    _, report = forecasting._load_strength_model(
        project_paths,
        "2026-08-16T15:31:30Z",
        period="main",
    )

    assert selected == [True]
    assert reads == [
        snapshot_path / "matches.parquet",
        snapshot_path / "patches.parquet",
    ]
    assert report.policy_id == "team-strength-main-stage-weight-v1"
