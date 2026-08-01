from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GROUP_ORDER = (
    ("four_zero", "4-0"),
    ("four_one", "4-1"),
    ("elimination_winner", "淘汰轮胜者"),
    ("elimination_loser", "淘汰轮败者"),
    ("one_four", "1-4"),
    ("zero_four", "0-4"),
)


def discover_runs(artifacts_dir: Path, kind: str | None = None) -> list[dict[str, Any]]:
    discovered: list[tuple[tuple[str, int, str], dict[str, Any]]] = []
    for path in artifacts_dir.glob("*/run.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            modified_at = path.stat().st_mtime_ns
        except (OSError, json.JSONDecodeError):
            continue
        if kind is not None and payload.get("kind") != kind:
            continue
        payload["_folder"] = str(path.parent)
        sort_key = (
            str(payload.get("created_at", "")),
            modified_at,
            str(payload.get("run_id", "")),
        )
        discovered.append((sort_key, payload))
    discovered.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in discovered]


def filling_checklist(recommendation: dict[str, Any]) -> list[dict[str, Any]]:
    kind = recommendation["recommendation_type"]
    selections = recommendation["selections"]
    if kind == "group":
        slots = selections["slots"]
        return [
            {
                "order": order,
                "section": label,
                "team_id": team["team_id"],
                "selection": team["team"],
            }
            for order, (category, label, team) in enumerate(
                ((category, label, team) for category, label in GROUP_ORDER for team in slots[category]),
                start=1,
            )
        ]
    if kind == "bracket":
        return [
            {
                "order": index,
                "section": node["node"],
                "team_id": node["winner_team_id"],
                "selection": node["winner_team"],
            }
            for index, node in enumerate(selections["nodes"], start=1)
        ]
    if kind == "fantasy":
        result: list[dict[str, Any]] = []
        for index, role in enumerate(("core", "mid", "support"), start=1):
            selected = selections["recommended"].get(role)
            if selected:
                result.append(
                    {
                        "order": index,
                        "section": role,
                        "team_id": selected["team_id"],
                        "selection": selected["team"],
                        "emblems": [item.get("label", "不可用") for item in selected.get("emblems", [])],
                    }
                )
        return result
    raise ValueError(f"unsupported recommendation type: {kind}")
