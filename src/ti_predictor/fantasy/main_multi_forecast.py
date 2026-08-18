"""Published Main terminal Fantasy Forecast comparison.

This module is the production consumer for one immutable evidence archive.  It
keeps historical-template v1, conditional-generator B1, and the Series-capped
hybrid separate; callers must not average or majority-vote their results.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from ti_predictor.config import load_rules
from ti_predictor.fantasy.current_advisor import rank_title_for_lineup
from ti_predictor.fantasy.roll import BannerState
from ti_predictor.fantasy.scenarios import ROLE_IDS
from ti_predictor.fantasy.valuation import _banner_score_inputs
from ti_predictor.hashing import sha256_file, sha256_json
from ti_predictor.paths import PATHS, ProjectPaths

MAIN_FORECAST_POINTER = PATHS.root / "deploy" / "runtime" / "main-forecast-current.json"
MAIN_FORECAST_ARTIFACT_TYPE = "ti2026-main-parallel-fantasy-forecast"
MAIN_FORECAST_MODELS = (
    "historical-template-v1",
    "player-role-conditional-b1",
    "series-capped-hybrid-v1-b1",
)
MODEL_LABELS = {
    "historical-template-v1": "V1 · 历史 Series 模板",
    "player-role-conditional-b1": "B1 · 选手—定位条件生成",
    "series-capped-hybrid-v1-b1": "混合 · V1 单 Series 10% 上限 + B1",
}
MODEL_EXPLANATIONS = {
    "historical-template-v1": "保留历史同队五人同局结构，但可能较多复用少数相似 Series。",
    "player-role-conditional-b1": "按选手、位置、近期、胜负、对手和赛制条件合成未来表现。",
    "series-capped-hybrid-v1-b1": "每个历史来源 Series 最终概率不超过 10%，截断部分交给 B1。",
}
SERIES_NODE_COUNT = 14
SERIES_SIDE_COUNT = 2
MAX_SERIES_GAMES = 5
GAME_TEMPLATE_SENTINEL = np.iinfo(np.uint16).max
ROLE_PLAYER_OFFSETS: Mapping[str, tuple[int, ...]] = {
    "core": (0, 1),
    "mid": (2,),
    "support": (3, 4),
}


class MainMultiForecastError(ValueError):
    """A published terminal Forecast pointer, archive, or state is invalid."""


@dataclass(frozen=True)
class MainMultiForecastContext:
    root: Path
    manifest: Mapping[str, Any]

    @property
    def as_of(self) -> str:
        return str(self.manifest["as_of"])

    @property
    def team_ids(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.manifest["team_ids"])

    @property
    def stat_ids(self) -> tuple[str, ...]:
        return tuple(str(value) for value in self.manifest["stat_ids"])

    @property
    def seeds(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.manifest["seeds"])

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(str(row["model_id"]) for row in self.manifest["models"])


def _validate_pointer(pointer: Mapping[str, Any]) -> None:
    if pointer.get("schema_version") != 1 or pointer.get("status") != "ready":
        raise MainMultiForecastError("Main three-model Forecast pointer is not ready")
    archive = pointer.get("archive")
    if not isinstance(archive, Mapping):
        raise MainMultiForecastError("Main three-model Forecast pointer has no archive")
    expected = str(archive.get("sha256", ""))
    if len(expected) != 64 or int(archive.get("bytes", 0)) <= 0:
        raise MainMultiForecastError("Main three-model Forecast archive identity is invalid")


def _verify_archive(path: Path, archive: Mapping[str, Any]) -> None:
    if not path.is_file():
        raise MainMultiForecastError(f"Main three-model Forecast archive is missing: {path}")
    if path.stat().st_size != int(archive["bytes"]):
        raise MainMultiForecastError("Main three-model Forecast archive byte count differs")
    if sha256_file(path) != str(archive["sha256"]):
        raise MainMultiForecastError("Main three-model Forecast archive SHA-256 differs")


def _safe_extract(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as bundle:
        for item in bundle.infolist():
            candidate = (destination / item.filename).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as error:
                raise MainMultiForecastError("Forecast archive contains an unsafe path") from error
        bundle.extractall(destination)


def _download_archive(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def materialize_main_multi_forecast(
    pointer_path: Path = MAIN_FORECAST_POINTER,
    *,
    cache_root: Path | None = None,
    allow_download: bool = True,
) -> Path:
    """Verify, optionally download, and extract the immutable Forecast archive."""

    pointer_file = pointer_path.resolve()
    pointer = json.loads(pointer_file.read_text(encoding="utf-8"))
    _validate_pointer(pointer)
    archive = pointer["archive"]
    relative = Path(str(archive["file"]))
    bundled = (pointer_file.parent / relative).resolve()
    cache = (cache_root or (PATHS.data / "cache" / "main-forecast")).resolve()
    cached_archive = cache / "archives" / f"{archive['sha256']}.zip"
    if bundled.is_file():
        archive_path = bundled
    elif cached_archive.is_file():
        archive_path = cached_archive
    else:
        if not allow_download:
            raise MainMultiForecastError("Main three-model Forecast archive is not bundled")
        url = str(archive.get("download_url", ""))
        if not url.startswith("https://"):
            raise MainMultiForecastError("Main three-model Forecast pointer has no HTTPS download URL")
        _download_archive(url, cached_archive)
        archive_path = cached_archive
    _verify_archive(archive_path, archive)
    extracted = cache / "extracted" / str(archive["sha256"])
    manifest_path = extracted / "manifest.json"
    if not manifest_path.is_file():
        extracted.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="main-forecast-", dir=extracted.parent) as temporary:
            temporary_root = Path(temporary)
            _safe_extract(archive_path, temporary_root)
            _validate_artifact(temporary_root)
            try:
                temporary_root.replace(extracted)
            except FileExistsError:
                pass
    manifest = _validate_artifact(extracted)
    if manifest["manifest_sha256"] != pointer.get("artifact_manifest_sha256"):
        raise MainMultiForecastError("Forecast pointer and artifact manifest differ")
    return extracted


def _validate_artifact(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    checksums_path = root / "checksums.json"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise MainMultiForecastError("Main three-model Forecast artifact is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = manifest.pop("manifest_sha256", None)
    if claimed != sha256_json(manifest):
        raise MainMultiForecastError("Main three-model Forecast manifest hash is invalid")
    manifest["manifest_sha256"] = claimed
    if (
        manifest.get("schema_version") != 1
        or manifest.get("artifact_type") != MAIN_FORECAST_ARTIFACT_TYPE
        or manifest.get("status") != "ready"
        or manifest.get("web_integration") is not True
        or tuple(row.get("model_id") for row in manifest.get("models", ()))
        != MAIN_FORECAST_MODELS
    ):
        raise MainMultiForecastError("Main three-model Forecast manifest contract is invalid")
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    for name, expected in checksums.items():
        candidate = root / str(name)
        if not candidate.is_file() or sha256_file(candidate) != str(expected):
            raise MainMultiForecastError(f"Main Forecast artifact checksum failed: {name}")
    return manifest


def load_main_multi_forecast_context(
    *,
    artifact_root: Path | None = None,
    pointer_path: Path = MAIN_FORECAST_POINTER,
    cache_root: Path | None = None,
    allow_download: bool = True,
) -> MainMultiForecastContext:
    root = (
        artifact_root.resolve()
        if artifact_root is not None
        else materialize_main_multi_forecast(
            pointer_path,
            cache_root=cache_root,
            allow_download=allow_download,
        )
    )
    return MainMultiForecastContext(root, _validate_artifact(root))


def weighted_lower_tail_cvar(values: np.ndarray, weights: np.ndarray, alpha: float) -> float:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    mass = np.asarray(weights, dtype=float).reshape(-1)
    if numeric.shape != mass.shape or not len(numeric) or not 0.0 < alpha <= 1.0:
        raise MainMultiForecastError("weighted CVaR input does not align")
    if not np.isfinite(numeric).all() or not np.isfinite(mass).all() or np.any(mass < 0.0):
        raise MainMultiForecastError("weighted CVaR input is not finite nonnegative evidence")
    mass = mass / mass.sum()
    order = np.argsort(numeric, kind="stable")
    remaining = float(alpha)
    total = 0.0
    for value, weight in zip(numeric[order], mass[order], strict=True):
        used = min(remaining, float(weight))
        total += used * float(value)
        remaining -= used
        if remaining <= 1e-15:
            break
    return total / alpha


def _template_role_values(
    scores: np.ndarray,
    stat_ids: tuple[str, ...],
    banner: BannerState,
    rules: dict[str, Any],
) -> np.ndarray:
    selected_stats, multipliers = _banner_score_inputs(
        banner,
        rules,
        slot_count=5,
        period_label="Main",
    )
    index = {stat_id: offset for offset, stat_id in enumerate(stat_ids)}
    selected = np.asarray([index[stat_id] for stat_id in selected_stats], dtype=np.int32)
    player_values = scores[:, :, selected] @ np.asarray(multipliers, dtype=np.float32)
    return player_values[:, ROLE_PLAYER_OFFSETS[banner.role]].mean(axis=1, dtype=np.float32)


def _period_outcomes(
    game_template_ids: np.ndarray,
    participants: np.ndarray,
    template_values: np.ndarray,
    team_count: int,
) -> np.ndarray:
    valid = game_template_ids != GAME_TEMPLATE_SENTINEL
    safe_ids = np.where(valid, game_template_ids, 0).astype(np.int64)
    game_values = np.where(valid, template_values[safe_ids], 0.0)
    top_two = np.partition(game_values, -2, axis=-1)[..., -2:].sum(axis=-1)
    inner, path_count = top_two.shape[:2]
    period = np.zeros((team_count, inner, path_count), dtype=np.float32)
    for node in range(SERIES_NODE_COUNT):
        for side in range(SERIES_SIDE_COUNT):
            team_by_path = participants[:, node, side]
            values = top_two[:, :, node, side]
            for team_index in range(team_count):
                mask = team_by_path == team_index
                if np.any(mask):
                    target = period[team_index]
                    target[:, mask] = np.maximum(target[:, mask], values[:, mask])
    return period.reshape(team_count, inner * path_count)


def _validate_banners(banners: Sequence[BannerState]) -> tuple[BannerState, ...]:
    frozen = tuple(banners)
    if tuple(item.role for item in frozen) != ROLE_IDS or any(len(item.emblems) != 5 for item in frozen):
        raise MainMultiForecastError("parallel Forecast requires core/mid/support five-slot Banners")
    return frozen


def _solve_model(
    context: MainMultiForecastContext,
    model_id: str,
    *,
    participants: np.ndarray,
    path_probabilities: np.ndarray,
    role_template_values: Mapping[str, np.ndarray],
    team_names: Mapping[int, str],
    title_evidence: Mapping[str, Any] | None,
    title_excluded_suffix_ids: Sequence[str],
    title_top_k: int,
) -> dict[str, Any]:
    role_by_seed: dict[str, list[np.ndarray]] = {role: [] for role in ROLE_IDS}
    weights_by_seed: list[np.ndarray] = []
    for seed in context.seeds:
        with np.load(context.root / f"draws-{model_id}-{seed}.npz", allow_pickle=False) as payload:
            game_ids = np.asarray(payload["game_template_ids"], dtype=np.uint16)
        inner = game_ids.shape[0]
        weights_by_seed.append(np.tile(path_probabilities / inner, inner))
        for role in ROLE_IDS:
            role_by_seed[role].append(
                _period_outcomes(
                    game_ids,
                    participants,
                    role_template_values[role],
                    len(context.team_ids),
                )
            )
    weights = np.concatenate(weights_by_seed) / len(context.seeds)
    role_outcomes = {role: np.concatenate(role_by_seed[role], axis=1) for role in ROLE_IDS}
    rankings: dict[str, list[dict[str, Any]]] = {}
    selected_indexes: dict[str, int] = {}
    role_base_means: dict[str, float] = {}
    for role in ROLE_IDS:
        outcomes = role_outcomes[role]
        means = outcomes @ weights
        rows = [
            {
                "team_id": team_id,
                "team_name": team_names.get(team_id, str(team_id)),
                "mean": float(means[index]),
                "cvar10": weighted_lower_tail_cvar(
                    outcomes[index],
                    weights,
                    float(context.manifest["cvar_alpha"]),
                ),
            }
            for index, team_id in enumerate(context.team_ids)
        ]
        rows.sort(key=lambda row: (-row["mean"], -row["cvar10"], row["team_id"]))
        rankings[role] = rows
        selected_indexes[role] = context.team_ids.index(int(rows[0]["team_id"]))
        role_base_means[role] = float(rows[0]["mean"])
    selected_team_ids = tuple(
        context.team_ids[selected_indexes[role]] for role in ROLE_IDS
    )
    total = sum(
        (role_outcomes[role][selected_indexes[role]] for role in ROLE_IDS),
        start=np.zeros_like(weights),
    )
    title = (
        rank_title_for_lineup(
            title_evidence,
            selected_team_ids=selected_team_ids,
            role_base_means=role_base_means,
            excluded_suffix_ids=title_excluded_suffix_ids,
            top_k=title_top_k,
        )
        if title_evidence is not None
        else None
    )
    return {
        "model_id": model_id,
        "model_label": MODEL_LABELS[model_id],
        "model_explanation": MODEL_EXPLANATIONS[model_id],
        "selected_team_ids": list(selected_team_ids),
        "selected_teams": [team_names.get(team_id, str(team_id)) for team_id in selected_team_ids],
        "role_base_means": role_base_means,
        "summary": {
            "mean": float(np.dot(total, weights)),
            "cvar10": weighted_lower_tail_cvar(
                total,
                weights,
                float(context.manifest["cvar_alpha"]),
            ),
        },
        "role_rankings": rankings,
        "title": title,
    }


def solve_parallel_main_forecasts(
    context: MainMultiForecastContext,
    banners: Sequence[BannerState],
    *,
    team_names: Mapping[int, str],
    title_evidence: Mapping[str, Any] | None,
    title_excluded_suffix_ids: Sequence[str] = (),
    title_top_k: int = 3,
    paths: ProjectPaths = PATHS,
) -> dict[str, Any]:
    """Return three independent terminal Forecasts for one confirmed Banner state."""

    frozen = _validate_banners(banners)
    with np.load(context.root / "templates.npz", allow_pickle=False) as payload:
        scores = np.asarray(payload["scores"], dtype=np.float32)
    with np.load(context.root / "outer-paths.npz", allow_pickle=False) as payload:
        participants = np.asarray(payload["participants"], dtype=np.int16)
        path_probabilities = np.asarray(payload["probabilities"], dtype=float)
    if len(scores) >= GAME_TEMPLATE_SENTINEL:
        raise MainMultiForecastError("Forecast template bank exceeds uint16 identity space")
    rules = load_rules(paths.rules)
    role_template_values = {
        banner.role: _template_role_values(scores, context.stat_ids, banner, rules)
        for banner in frozen
    }
    models = [
        _solve_model(
            context,
            model_id,
            participants=participants,
            path_probabilities=path_probabilities,
            role_template_values=role_template_values,
            team_names=team_names,
            title_evidence=title_evidence,
            title_excluded_suffix_ids=title_excluded_suffix_ids,
            title_top_k=title_top_k,
        )
        for model_id in context.models
    ]
    agreement = {
        role: len({tuple(row["selected_team_ids"])[index] for row in models}) == 1
        for index, role in enumerate(ROLE_IDS)
    }
    payload = {
        "schema_version": 1,
        "analysis_type": "main_parallel_terminal_fantasy_forecast",
        "status": "published-model-comparison",
        "as_of": context.as_of,
        "evidence_manifest_sha256": context.manifest["manifest_sha256"],
        "scenario_count_per_model": int(context.manifest["weighted_scenario_count"]),
        "models": models,
        "agreement": {
            "by_role": agreement,
            "all_roles": all(agreement.values()),
            "policy": "display-disagreement-no-majority-vote",
        },
        "limitations": list(context.manifest.get("limitations", ())),
    }
    payload["analysis_sha256"] = sha256_json(payload)
    return payload


__all__ = [
    "MAIN_FORECAST_MODELS",
    "MAIN_FORECAST_POINTER",
    "MODEL_EXPLANATIONS",
    "MODEL_LABELS",
    "MainMultiForecastContext",
    "MainMultiForecastError",
    "load_main_multi_forecast_context",
    "materialize_main_multi_forecast",
    "solve_parallel_main_forecasts",
    "weighted_lower_tail_cvar",
]
