from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from ti_predictor.config import load_rules
from ti_predictor.fantasy.main_multi_forecast import (
    GAME_TEMPLATE_SENTINEL,
    MAIN_FORECAST_ARTIFACT_TYPE,
    MAIN_FORECAST_MODELS,
    MainMultiForecastError,
    load_main_multi_forecast_context,
    materialize_main_multi_forecast,
    solve_parallel_main_forecasts,
)
from ti_predictor.fantasy.main_multi_forecast_builder import _prediction_semantic_hash
from ti_predictor.fantasy.roll import BannerState, EmblemState
from ti_predictor.hashing import sha256_file, sha256_json


def _banners() -> tuple[BannerState, ...]:
    rules = load_rules()["fantasy"]
    stats_by_color: dict[str, list[str]] = {}
    for stat_id, rule in rules["stats"].items():
        stats_by_color.setdefault(str(rule["color"]), []).append(str(stat_id))
    return tuple(
        BannerState(
            role,
            tuple(
                EmblemState(sorted(stats_by_color[color])[0], 3, "friendly")
                for color in rules["role_banners"][role]
            ),
        )
        for role in ("core", "mid", "support")
    )


def _write_artifact(root: Path) -> dict:
    root.mkdir(parents=True)
    stat_ids = tuple(load_rules()["fantasy"]["stats"])
    scores = np.zeros((6, 5, len(stat_ids)), dtype=np.float32)
    for index, value in enumerate((10.0, 8.0, 7.0, 12.0, 11.0, 10.0)):
        scores[index] = value
    np.savez_compressed(root / "templates.npz", scores=scores)
    participants = np.tile(np.asarray([[[0, 1]]], dtype=np.int16), (1, 14, 1))
    np.savez_compressed(
        root / "outer-paths.npz",
        participants=participants,
        probabilities=np.asarray([1.0]),
    )
    model_ids = {
        MAIN_FORECAST_MODELS[0]: (0, 1),
        MAIN_FORECAST_MODELS[1]: (2, 3),
        MAIN_FORECAST_MODELS[2]: (4, 5),
    }
    for model_id, (left, right) in model_ids.items():
        game_ids = np.full((1, 1, 14, 2, 5), GAME_TEMPLATE_SENTINEL, dtype=np.uint16)
        game_ids[..., 0, :2] = left
        game_ids[..., 1, :2] = right
        np.savez_compressed(
            root / f"draws-{model_id}-7.npz",
            game_template_ids=game_ids,
        )
    checked = [
        "templates.npz",
        "outer-paths.npz",
        *(f"draws-{model_id}-7.npz" for model_id in MAIN_FORECAST_MODELS),
    ]
    checksums = {name: sha256_file(root / name) for name in checked}
    (root / "checksums.json").write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "artifact_type": MAIN_FORECAST_ARTIFACT_TYPE,
        "status": "ready",
        "web_integration": True,
        "as_of": "2026-08-16T15:31:30Z",
        "team_ids": [10, 20, 30, 40, 50, 60, 70, 80],
        "stat_ids": list(stat_ids),
        "seeds": [7],
        "cvar_alpha": 0.1,
        "weighted_scenario_count": 1,
        "models": [{"model_id": model_id} for model_id in MAIN_FORECAST_MODELS],
        "limitations": ["fixture"],
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def test_three_models_remain_separate_and_expose_role_disagreement(tmp_path: Path) -> None:
    root = tmp_path / "artifact"
    _write_artifact(root)
    context = load_main_multi_forecast_context(artifact_root=root)

    result = solve_parallel_main_forecasts(
        context,
        _banners(),
        team_names={10: "Left", 20: "Right"},
        title_evidence=None,
    )

    assert [row["model_id"] for row in result["models"]] == list(MAIN_FORECAST_MODELS)
    assert [row["selected_team_ids"] for row in result["models"]] == [
        [10, 10, 10],
        [20, 20, 20],
        [10, 10, 10],
    ]
    assert result["agreement"] == {
        "by_role": {"core": False, "mid": False, "support": False},
        "all_roles": False,
        "policy": "display-disagreement-no-majority-vote",
    }


def test_pointer_materialization_verifies_archive_before_loading(tmp_path: Path) -> None:
    source = tmp_path / "source"
    manifest = _write_artifact(source)
    pointer_dir = tmp_path / "deploy" / "runtime"
    release_dir = pointer_dir / "releases"
    release_dir.mkdir(parents=True)
    archive = release_dir / "fixture.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(source.iterdir()):
            bundle.write(path, path.name)
    pointer = {
        "schema_version": 1,
        "status": "ready",
        "as_of": manifest["as_of"],
        "artifact_manifest_sha256": manifest["manifest_sha256"],
        "archive": {
            "file": "releases/fixture.zip",
            "bytes": archive.stat().st_size,
            "sha256": sha256_file(archive),
            "download_url": "https://example.invalid/fixture.zip",
        },
    }
    pointer_path = pointer_dir / "main-forecast-current.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    extracted = materialize_main_multi_forecast(
        pointer_path,
        cache_root=tmp_path / "cache",
        allow_download=False,
    )

    assert extracted.joinpath("manifest.json").is_file()

    pointer["archive"]["sha256"] = "0" * 64
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(MainMultiForecastError, match="SHA-256"):
        materialize_main_multi_forecast(
            pointer_path,
            cache_root=tmp_path / "other-cache",
            allow_download=False,
        )


def test_rejected_calibration_candidate_is_audit_only_for_prediction_identity() -> None:
    class Model:
        def __init__(self, candidate, *, accepted: bool = False) -> None:
            self.payload = {
                "ratings": {"10": 1500.0},
                "calibration_accepted": accepted,
                "calibration_candidate": candidate,
            }

        def as_dict(self):
            return self.payload

    assert _prediction_semantic_hash(Model(None)) == _prediction_semantic_hash(
        Model({"x_thresholds": [0.2, 0.8]})
    )
    assert _prediction_semantic_hash(Model(None, accepted=True)) != _prediction_semantic_hash(
        Model({"x_thresholds": [0.2, 0.8]}, accepted=True)
    )
