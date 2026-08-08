from __future__ import annotations

import hashlib
import re
from collections import defaultdict, deque
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ti_predictor.hashing import sha256_json
from ti_predictor.models.policy import TeamStrengthPolicy
from ti_predictor.schemas import AuditIssue, as_utc

_PATCH_FAMILY = re.compile(r"^(\d+)\.(\d+)(?:[a-z]+)?$", re.IGNORECASE)
_EXACT_PATCH = re.compile(r"^(\d+)\.(\d+)([a-z]+)?$", re.IGNORECASE)
_UNKNOWN = "<unknown>"


@dataclass
class EvidenceSet:
    matches: pd.DataFrame
    target_patch_family: str
    previous_patch_family: str | None
    audit: dict[str, Any]
    issues: list[AuditIssue]


def normalize_patch_family(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    match = _PATCH_FAMILY.fullmatch(str(value).strip())
    if match is None:
        return None
    return f"{int(match.group(1))}.{int(match.group(2))}"


def normalize_exact_patch(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    match = _EXACT_PATCH.fullmatch(str(value).strip())
    if match is None:
        return None
    suffix = (match.group(3) or "").lower()
    return f"{int(match.group(1))}.{int(match.group(2))}{suffix}"


def ordered_patch_families(patches: pd.DataFrame, *, as_of: datetime) -> list[str]:
    required = {"name", "date"}
    missing = required - set(patches.columns)
    if missing:
        raise ValueError(f"patch timeline is missing required columns: {sorted(missing)}")
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    frame = patches.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce", format="mixed")
    frame["patch_family"] = frame["name"].map(normalize_patch_family)
    frame = frame.loc[
        frame["date"].notna() & (frame["date"] <= pd.Timestamp(cutoff)) & frame["patch_family"].notna()
    ].sort_values(["date", "patch_family"], kind="stable")
    result: list[str] = []
    for family in frame["patch_family"].astype(str):
        if not result or family != result[-1]:
            result.append(family)
    if not result:
        raise ValueError("patch timeline has no gameplay patch available at as_of")
    return result


def patch_window(
    patches: pd.DataFrame,
    *,
    as_of: datetime,
    target_patch_family: str | None = None,
) -> tuple[str, str | None, list[str]]:
    families = ordered_patch_families(patches, as_of=as_of)
    target = normalize_patch_family(target_patch_family) if target_patch_family else families[-1]
    if target is None or target not in families:
        raise ValueError(f"target patch family {target_patch_family!r} is unavailable at as_of")
    target_index = families.index(target)
    previous = families[target_index - 1] if target_index else None
    return target, previous, families


def prepare_completed_games(
    matches: pd.DataFrame,
    *,
    as_of: datetime,
) -> tuple[pd.DataFrame, dict[str, int], list[AuditIssue]]:
    required = {"match_id", "start_time", "radiant_team_id", "dire_team_id", "radiant_win"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"match data is missing required columns: {sorted(missing)}")
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    frame = matches.copy()
    frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
    invalid_start = frame["start_time"].isna()
    future = frame["start_time"] >= pd.Timestamp(cutoff)
    missing_identity_or_result = (
        frame["radiant_team_id"].isna() | frame["dire_team_id"].isna() | frame["radiant_win"].isna()
    )
    same_team = (
        frame["radiant_team_id"].notna()
        & frame["dire_team_id"].notna()
        & frame["radiant_team_id"].eq(frame["dire_team_id"])
    )
    duplicate = frame["match_id"].duplicated(keep=False)
    usable = ~(invalid_start | future | missing_identity_or_result | same_team | duplicate)
    prepared = frame.loc[usable].copy()
    prepared["radiant_team_id"] = prepared["radiant_team_id"].astype(int)
    prepared["dire_team_id"] = prepared["dire_team_id"].astype(int)
    prepared["radiant_win"] = prepared["radiant_win"].astype(bool)
    prepared = prepared.sort_values(["start_time", "match_id"], kind="stable").reset_index(drop=True)
    audit = {
        "input_games": int(len(frame)),
        "completed_as_of_games": int(len(prepared)),
        "invalid_start_time_games": int(invalid_start.sum()),
        "future_games": int(future.fillna(False).sum()),
        "missing_identity_or_result_games": int(missing_identity_or_result.sum()),
        "same_team_games": int(same_team.sum()),
        "duplicate_match_id_games": int(duplicate.sum()),
    }
    issues: list[AuditIssue] = []
    if duplicate.any():
        issues.append(
            AuditIssue(
                code="model-duplicate-match-id",
                severity="blocking",
                message="Duplicate match IDs were excluded to prevent repeated rating updates",
                context={"games": int(duplicate.sum())},
            )
        )
    return prepared, audit, issues


def _breakdown(frame: pd.DataFrame, column: str) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    labels = frame[column].fillna(_UNKNOWN).astype(str)
    for label in sorted(labels.unique()):
        group = frame.loc[labels.eq(label)]
        result[label] = {
            "games": int(len(group)),
            "included_games": int(group["evidence_weight"].gt(0.0).sum()),
            "effective_weight": float(group["evidence_weight"].sum()),
        }
    return result


def _stable_id_hash(values: Collection[int]) -> str:
    payload = ",".join(str(value) for value in sorted({int(value) for value in values}))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _target_connected_component(
    matches: pd.DataFrame,
    *,
    target_team_ids: Collection[int],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    targets = {int(value) for value in target_team_ids}
    if not targets:
        raise ValueError("target_team_ids are required for target_connected_component evidence")
    if any(value <= 0 for value in targets):
        raise ValueError("target_team_ids must contain only positive stable IDs")

    adjacency: dict[int, set[int]] = defaultdict(set)
    nodes: set[int] = set()
    for row in matches[["radiant_team_id", "dire_team_id"]].itertuples(index=False):
        radiant_id = int(row.radiant_team_id)
        dire_id = int(row.dire_team_id)
        adjacency[radiant_id].add(dire_id)
        adjacency[dire_id].add(radiant_id)
        nodes.update((radiant_id, dire_id))

    connected = targets & nodes
    queue = deque(sorted(connected))
    while queue:
        team_id = queue.popleft()
        for opponent_id in sorted(adjacency[team_id]):
            if opponent_id not in connected:
                connected.add(opponent_id)
                queue.append(opponent_id)

    mask = matches["radiant_team_id"].isin(connected) & matches["dire_team_id"].isin(connected)
    selected = matches.loc[mask].copy().reset_index(drop=True)
    missing_targets = sorted(targets - nodes)
    audit = {
        "target_team_ids": sorted(targets),
        "target_team_ids_sha256": _stable_id_hash(targets),
        "target_team_ids_present": sorted(targets & nodes),
        "target_team_ids_missing": missing_targets,
        "connected_team_count": len(connected),
        "connected_team_ids_sha256": _stable_id_hash(connected),
        "excluded_disconnected_games": int(len(matches) - len(selected)),
        "selected_match_ids_sha256": _stable_id_hash([int(value) for value in selected["match_id"]]),
    }
    return selected, audit


def build_evidence_set(
    matches: pd.DataFrame,
    patches: pd.DataFrame,
    *,
    as_of: datetime,
    policy: TeamStrengthPolicy,
    target_patch_family: str | None = None,
    target_team_ids: Collection[int] | None = None,
) -> EvidenceSet:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    frame, structural_audit, issues = prepare_completed_games(matches, as_of=cutoff)
    for column in ("patch_name", "league_tier"):
        if column not in frame:
            frame[column] = None
    target, previous, sequence = patch_window(
        patches,
        as_of=cutoff,
        target_patch_family=target_patch_family,
    )
    target_index = sequence.index(target)
    known_earlier = set(sequence[:target_index])
    known_later = set(sequence[target_index + 1 :])
    frame["patch_family"] = frame["patch_name"].map(normalize_patch_family)
    frame["exact_patch_name"] = frame["patch_name"].map(normalize_exact_patch)
    frame["normalized_league_tier"] = frame["league_tier"].map(
        lambda value: None if value is None or pd.isna(value) else str(value).strip().lower()
    )

    def patch_weight(family: object) -> float:
        if family == target:
            return policy.patch_weights.target
        if previous is not None and family == previous:
            return policy.patch_weights.immediate_prior
        if family in known_earlier:
            return policy.patch_weights.earlier
        return 0.0

    frame["patch_family_weight"] = frame["patch_family"].map(patch_weight).astype(float)
    frame["current_exact_patch"] = False
    frame["exact_patch_multiplier"] = 1.0
    exact_patch_conflict = pd.Series(False, index=frame.index, dtype=bool)
    exact_policy = policy.current_exact_patch_weight
    exact_policy_active = False
    if exact_policy is not None:
        exact_patch_name = normalize_exact_patch(exact_policy.patch_name)
        exact_patch_family = normalize_patch_family(exact_policy.patch_name)
        exact_patch_start = pd.Timestamp(exact_policy.active_from)
        exact_policy_active = bool(
            exact_patch_name is not None
            and exact_patch_family == target
            and exact_patch_start <= pd.Timestamp(cutoff)
        )
        if exact_policy_active:
            compatible_name = frame["exact_patch_name"].isin({target, exact_patch_name})
            current_exact_patch = (
                frame["patch_family"].eq(target) & frame["start_time"].ge(exact_patch_start) & compatible_name
            )
            frame.loc[current_exact_patch, "current_exact_patch"] = True
            frame.loc[current_exact_patch, "exact_patch_multiplier"] = exact_policy.multiplier
            exact_patch_conflict = frame["patch_family"].eq(target) & (
                (
                    frame["start_time"].ge(exact_patch_start)
                    & frame["exact_patch_name"].notna()
                    & ~compatible_name
                )
                | (frame["start_time"].lt(exact_patch_start) & frame["exact_patch_name"].eq(exact_patch_name))
            )
    frame["patch_weight"] = (frame["patch_family_weight"] * frame["exact_patch_multiplier"]).astype(float)
    frame["tier_weight"] = frame["normalized_league_tier"].map(policy.tier_weights).fillna(0.0).astype(float)
    age_days = (pd.Timestamp(cutoff) - frame["start_time"]).dt.total_seconds() / 86400.0
    frame["age_days"] = age_days.astype(float)
    frame["time_weight"] = np.power(2.0, -frame["age_days"] / policy.time_half_life_days)
    frame["evidence_weight"] = (frame["patch_weight"] * frame["tier_weight"] * frame["time_weight"]).astype(
        float
    )

    unknown_patch = frame["patch_family"].isna()
    unrecognized_patch = frame["patch_family"].notna() & ~frame["patch_family"].isin(sequence)
    later_patch = frame["patch_family"].isin(known_later)
    unknown_tier = frame["normalized_league_tier"].isna() | frame["normalized_league_tier"].eq("unknown")
    unsupported_tier = frame["normalized_league_tier"].notna() & ~frame["normalized_league_tier"].isin(
        policy.tier_weights
    )

    issue_specs = (
        (
            unknown_patch,
            "model-evidence-unknown-patch",
            "Games with an unknown or invalid Patch were excluded from rating evidence",
        ),
        (
            unrecognized_patch,
            "model-evidence-unrecognized-patch",
            "Games whose normalized Patch is absent from the as_of patch timeline were excluded",
        ),
        (
            later_patch,
            "model-evidence-later-patch",
            "Games later than the selected target Patch were excluded",
        ),
        (
            unknown_tier,
            "model-evidence-unknown-tier",
            "Games with an unknown League tier were excluded from rating evidence",
        ),
        (
            unsupported_tier & ~unknown_tier,
            "model-evidence-unsupported-tier",
            "Games outside OpenDota premium/professional tiers were excluded from rating evidence",
        ),
    )
    for mask, code, message in issue_specs:
        if mask.any():
            issues.append(
                AuditIssue(
                    code=code,
                    severity="warning",
                    message=message,
                    context={"games": int(mask.sum())},
                )
            )

    if exact_patch_conflict.any():
        issues.append(
            AuditIssue(
                code="model-evidence-exact-patch-conflict",
                severity="warning",
                message=(
                    "Games whose explicit exact Patch conflicts with the configured current-Patch "
                    "UTC boundary kept their ordinary family weight"
                ),
                context={"games": int(exact_patch_conflict.sum())},
            )
        )

    eligible = frame.loc[frame["evidence_weight"] > 0.0].copy().reset_index(drop=True)
    scope_audit: dict[str, Any] = {
        "evidence_scope_mode": policy.evidence_scope.mode,
        "pre_scope_positive_weight_games": int(len(eligible)),
        "pre_scope_total_effective_weight": float(eligible["evidence_weight"].sum()),
    }
    if policy.evidence_scope.mode == "target_connected_component":
        included, connected_audit = _target_connected_component(
            eligible,
            target_team_ids=target_team_ids or (),
        )
        scope_audit.update(connected_audit)
        missing_targets = connected_audit["target_team_ids_missing"]
        if missing_targets:
            issues.append(
                AuditIssue(
                    code="model-target-team-no-evidence",
                    severity="warning",
                    message="At least one target team has no positive-weight Game at as_of",
                    context={"target_team_ids": missing_targets},
                )
            )
    else:
        included = eligible
        team_ids = {
            int(value) for column in ("radiant_team_id", "dire_team_id") for value in included[column]
        }
        scope_audit.update(
            {
                "target_team_ids": [],
                "target_team_ids_present": [],
                "target_team_ids_missing": [],
                "connected_team_count": len(team_ids),
                "connected_team_ids_sha256": _stable_id_hash(team_ids),
                "excluded_disconnected_games": 0,
                "selected_match_ids_sha256": _stable_id_hash([int(value) for value in included["match_id"]]),
            }
        )
    if included.empty:
        issues.append(
            AuditIssue(
                code="model-no-weighted-matches",
                severity="blocking",
                message="No positive-weight Games are available for the selected target Patch at as_of",
                context={"target_patch_family": target, "previous_patch_family": previous},
            )
        )
    audit: dict[str, Any] = {
        "weight_formula_version": "major_exact_tier_time_v3",
        "weight_policy_sha256": sha256_json(policy.model_dump(mode="json")),
        "policy_id": policy.policy_id,
        "as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "target_patch_family": target,
        "previous_patch_family": previous,
        **structural_audit,
        **scope_audit,
        "positive_weight_games": int(len(included)),
        "zero_weight_games": int(len(frame) - len(eligible)),
        "total_effective_weight": float(included["evidence_weight"].sum()),
        "unknown_patch_games": int(unknown_patch.sum()),
        "unrecognized_patch_games": int(unrecognized_patch.sum()),
        "later_patch_games": int(later_patch.sum()),
        "unknown_tier_games": int(unknown_tier.sum()),
        "unsupported_tier_games": int((unsupported_tier & ~unknown_tier).sum()),
        "current_exact_patch_weight": (
            None if exact_policy is None else exact_policy.model_dump(mode="json")
        ),
        "current_exact_patch_weight_active": exact_policy_active,
        "current_exact_patch_games": int(included["current_exact_patch"].sum()),
        "current_exact_patch_effective_weight": float(
            included.loc[included["current_exact_patch"], "evidence_weight"].sum()
        ),
        "by_patch_family": _breakdown(frame, "patch_family"),
        "by_exact_patch_multiplier": _breakdown(frame, "exact_patch_multiplier"),
        "by_league_tier": _breakdown(frame, "normalized_league_tier"),
        "selected_by_patch_family": _breakdown(included, "patch_family"),
        "selected_by_exact_patch_multiplier": _breakdown(included, "exact_patch_multiplier"),
        "selected_by_league_tier": _breakdown(included, "normalized_league_tier"),
    }
    return EvidenceSet(
        matches=included,
        target_patch_family=target,
        previous_patch_family=previous,
        audit=audit,
        issues=issues,
    )
