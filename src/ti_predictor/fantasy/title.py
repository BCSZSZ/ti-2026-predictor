"""Client-backed Fantasy Title parsing and descriptive evidence calculations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ti_predictor.fantasy.scenarios import ROLE_IDS, PoolBuildResult

PREFIX_ADJECTIVES: dict[str, tuple[str, ...]] = {
    "crimson": ("Red",),
    "cerulean": ("Blue",),
    "emerald": ("Green",),
    "royal": ("Purple",),
    "golden": ("Yellow", "Brown"),
    "elemental": ("Aquatic", "Fiery", "Icy"),
    "otherworldly": ("Undead", "Demon", "Spirit"),
    "heroic": ("Cape", "Mask", "Masked"),
}

CONFLICTED_SUFFIXES = {"early_first_blood", "late_first_blood"}
UNAVAILABLE_SUFFIXES = {"fountain"}
_HERO_HEADER = re.compile(r'"(npc_dota_hero_[^"]+)"\s*\{')


@dataclass(frozen=True)
class PlayerTitleFeatures:
    account_id: int
    hero_id: int
    won: bool | None


@dataclass(frozen=True)
class MatchTitleFeatures:
    match_id: int
    duration_seconds: int | None
    first_blood_time_seconds: int | None
    any_player_died_to_tormentor: bool | None
    players: tuple[PlayerTitleFeatures, ...]

    def player(self, account_id: int) -> PlayerTitleFeatures | None:
        return next((item for item in self.players if item.account_id == account_id), None)


def _balanced_braces(text: str, opening: int) -> str:
    if opening < 0 or opening >= len(text) or text[opening] != "{":
        return ""
    depth = 0
    quoted = False
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[opening : index + 1]
    return ""


def parse_title_hero_categories(text: str) -> dict[int, tuple[str, ...]]:
    """Read stable hero IDs and Title adjectives from Valve's ``npc_heroes.txt``.

    The client file contains repeated ``DOTAHeroes`` chunks, so parsing it into a
    regular dictionary would silently discard earlier chunks. Hero blocks are
    therefore scanned directly and merged by stable ``HeroID``.
    """

    result: dict[int, tuple[str, ...]] = {}
    for header in _HERO_HEADER.finditer(text):
        opening = text.find("{", header.start())
        block = _balanced_braces(text, opening)
        hero_id_match = re.search(r'"HeroID"\s*"(\d+)"', block)
        if hero_id_match is None:
            continue
        adjective_marker = block.find('"Adjectives"')
        adjective_opening = block.find("{", adjective_marker) if adjective_marker >= 0 else -1
        adjectives = _balanced_braces(block, adjective_opening)
        categories = tuple(
            prefix_id
            for prefix_id, keys in PREFIX_ADJECTIVES.items()
            if any(re.search(rf'"{re.escape(key)}"\s*"([1-9]\d*)"', adjectives) for key in keys)
        )
        hero_id = int(hero_id_match.group(1))
        previous = result.get(hero_id)
        if previous is not None and previous != categories:
            raise ValueError(f"client hero {hero_id} has conflicting Title adjective definitions")
        result[hero_id] = categories
    if not result:
        raise ValueError("npc_heroes.txt did not expose any stable HeroID blocks")
    missing_categories = set(PREFIX_ADJECTIVES) - {
        category for categories in result.values() for category in categories
    }
    if missing_categories:
        raise ValueError(f"client hero file is missing Title categories: {sorted(missing_categories)}")
    return dict(sorted(result.items()))


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_match_title_features(
    payload: dict[str, Any], *, expected_match_id: int | None = None
) -> MatchTitleFeatures:
    """Normalize only the raw match fields needed by Fantasy Title evidence."""

    match_id = _optional_int(payload.get("match_id"))
    if match_id is None:
        if expected_match_id is None:
            raise ValueError("raw match payload has no stable match_id")
        match_id = int(expected_match_id)
    if expected_match_id is not None and match_id != int(expected_match_id):
        raise ValueError(f"raw match identity mismatch: expected {expected_match_id}, got {match_id}")

    radiant_win = payload.get("radiant_win")
    players: list[PlayerTitleFeatures] = []
    raw_players = payload.get("players") if isinstance(payload.get("players"), list) else []
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            continue
        account_id = _optional_int(raw_player.get("account_id"))
        hero_id = _optional_int(raw_player.get("hero_id"))
        if account_id is None or account_id <= 0 or hero_id is None or hero_id <= 0:
            continue
        raw_win = raw_player.get("win")
        if raw_win in (0, 1, False, True):
            won = bool(raw_win)
        else:
            player_slot = _optional_int(raw_player.get("player_slot"))
            if isinstance(radiant_win, bool) and player_slot is not None:
                won = radiant_win if player_slot < 128 else not radiant_win
            else:
                won = None
        players.append(PlayerTitleFeatures(account_id=account_id, hero_id=hero_id, won=won))
    players.sort(key=lambda item: item.account_id)
    if len({item.account_id for item in players}) != len(players):
        raise ValueError(f"raw match {match_id} repeats a stable account_id")

    first_blood_times = [
        _optional_int(objective.get("time"))
        for objective in payload.get("objectives", [])
        if isinstance(objective, dict) and objective.get("type") == "CHAT_MESSAGE_FIRSTBLOOD"
    ]
    observed_first_blood = [value for value in first_blood_times if value is not None]
    first_blood_time = min(observed_first_blood) if observed_first_blood else None

    parsed = (
        isinstance(payload.get("od_data"), dict)
        and payload["od_data"].get("has_parsed") is True
        and payload.get("version") is not None
    )
    tormentor_death = None
    if parsed:
        tormentor_death = any(
            _optional_int((player.get("killed_by") or {}).get("npc_dota_miniboss")) not in (None, 0)
            for player in raw_players
            if isinstance(player, dict) and isinstance(player.get("killed_by") or {}, dict)
        )

    return MatchTitleFeatures(
        match_id=match_id,
        duration_seconds=_optional_int(payload.get("duration")),
        first_blood_time_seconds=first_blood_time,
        any_player_died_to_tormentor=tormentor_death,
        players=tuple(players),
    )


def _rank_rows(rows: list[dict[str, Any]], *, value_key: str) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            -(float(row[value_key]) if row.get(value_key) is not None else -1.0),
            str(row["id"]),
        ),
    )
    return [{**row, "rank": index} for index, row in enumerate(ranked, start=1)]


def _condition_value(
    condition_id: str,
    feature: MatchTitleFeatures,
    player_features: list[PlayerTitleFeatures],
) -> bool | None:
    if condition_id == "loser":
        wins = [item.won for item in player_features]
        if not wins or any(value is None for value in wins) or len(set(wins)) != 1:
            return None
        return not bool(wins[0])
    if condition_id == "quick":
        return None if feature.duration_seconds is None else feature.duration_seconds < 25 * 60
    if condition_id == "lucky":
        return None if feature.duration_seconds is None else feature.duration_seconds % 10 == 8
    if condition_id == "early_first_blood":
        value = feature.first_blood_time_seconds
        return None if value is None else value < 0
    if condition_id == "late_first_blood":
        value = feature.first_blood_time_seconds
        return None if value is None else value > 10 * 60
    if condition_id == "tormented":
        return feature.any_player_died_to_tormentor
    return None


def build_title_analysis(
    pool_result: PoolBuildResult,
    match_features: dict[int, MatchTitleFeatures],
    series_types: dict[int, int],
    hero_categories: dict[int, tuple[str, ...]],
    rules: dict[str, Any],
    *,
    team_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Build pool-balanced, map-level Title evidence without changing P3 valuation."""

    names = team_names or {}
    prefix_rules = {item["id"]: item for item in rules["fantasy"]["coach"]["prefixes"]}
    suffix_rules = {item["id"]: item for item in rules["fantasy"]["coach"]["suffixes"]}
    if tuple(prefix_rules) != tuple(PREFIX_ADJECTIVES):
        raise ValueError("canonical Title Prefix order differs from the client adjective mapping")

    pool_rows: list[dict[str, Any]] = []
    for pool in pool_result.pools:
        prefix_total = 0.0
        prefix_available = 0.0
        prefix_triggered = {prefix_id: 0.0 for prefix_id in prefix_rules}
        suffix_total = {suffix_id: 0.0 for suffix_id in suffix_rules}
        suffix_triggered = {suffix_id: 0.0 for suffix_id in suffix_rules}
        player_game_rows = 0
        bo3_weight = 0.0
        bo3_game3_weight = 0.0
        bo3_blocks = 0

        for block in pool.blocks:
            block_series_type = {series_types.get(match_id) for match_id in block.match_ids}
            if len(block_series_type) != 1 or None in block_series_type:
                raise ValueError(f"Series {block.series_id} has missing or mixed series_type")
            series_type = int(next(iter(block_series_type)))
            if series_type == 1:
                bo3_blocks += 1
                bo3_weight += block.evidence_weight
                if len(block.match_ids) == 3:
                    bo3_game3_weight += block.evidence_weight

            for match_id in block.match_ids:
                feature = match_features.get(match_id)
                if feature is None:
                    raise ValueError(f"Title evidence is missing raw match {match_id}")
                selected_players = [feature.player(account_id) for account_id in pool.player_ids]
                if any(item is None for item in selected_players):
                    raise ValueError(f"raw match {match_id} is missing a required stable player ID")
                complete_players = [item for item in selected_players if item is not None]

                game_weight = block.evidence_weight / len(block.match_ids)
                for player in complete_players:
                    player_game_rows += 1
                    player_weight = game_weight / len(complete_players)
                    prefix_total += player_weight
                    categories = hero_categories.get(player.hero_id)
                    if categories is None:
                        continue
                    prefix_available += player_weight
                    for prefix_id in categories:
                        prefix_triggered[prefix_id] += player_weight

                for suffix_id in suffix_rules:
                    value = _condition_value(suffix_id, feature, complete_players)
                    if value is None:
                        continue
                    suffix_total[suffix_id] += game_weight
                    if value:
                        suffix_triggered[suffix_id] += game_weight

        if prefix_available <= 0.0:
            raise ValueError(f"Team {pool.target_team_id} {pool.role} has no mapped hero observations")
        prefix_rates = {
            prefix_id: prefix_triggered[prefix_id] / prefix_available for prefix_id in prefix_rules
        }
        prefix_lifts = {
            prefix_id: prefix_rates[prefix_id] * float(prefix_rules[prefix_id]["bonus_percent"])
            for prefix_id in prefix_rules
        }
        suffix_rates: dict[str, float | None] = {}
        suffix_coverage: dict[str, float] = {}
        for suffix_id in suffix_rules:
            if suffix_id == "clutch":
                reach_game3 = bo3_game3_weight / bo3_weight if bo3_weight > 0.0 else None
                suffix_rates[suffix_id] = (
                    reach_game3 / (2.0 + reach_game3) if reach_game3 is not None else None
                )
                suffix_coverage[suffix_id] = 1.0 if bo3_weight > 0.0 else 0.0
            elif suffix_id == "fountain":
                suffix_rates[suffix_id] = None
                suffix_coverage[suffix_id] = 0.0
            else:
                denominator = suffix_total[suffix_id]
                suffix_rates[suffix_id] = (
                    suffix_triggered[suffix_id] / denominator if denominator > 0.0 else None
                )
                total_game_weight = sum(block.evidence_weight for block in pool.blocks)
                suffix_coverage[suffix_id] = (
                    denominator / total_game_weight if total_game_weight > 0.0 else 0.0
                )
        suffix_lifts = {
            suffix_id: (
                None
                if suffix_rates[suffix_id] is None
                else suffix_rates[suffix_id] * float(suffix_rules[suffix_id]["bonus_percent"])
            )
            for suffix_id in suffix_rules
        }
        best_prefix = max(prefix_lifts, key=prefix_lifts.__getitem__)
        recommendable_suffixes = [
            suffix_id
            for suffix_id, value in suffix_lifts.items()
            if value is not None
            and suffix_id not in CONFLICTED_SUFFIXES
            and suffix_id not in UNAVAILABLE_SUFFIXES
        ]
        best_suffix = max(recommendable_suffixes, key=lambda suffix_id: suffix_lifts[suffix_id])
        pool_rows.append(
            {
                "team_id": int(pool.target_team_id),
                "team": names.get(pool.target_team_id, str(pool.target_team_id)),
                "role": pool.role,
                "player_ids": list(pool.player_ids),
                "complete_series_blocks": len(pool.blocks),
                "player_game_rows": player_game_rows,
                "hero_mapping_coverage": prefix_available / prefix_total if prefix_total > 0.0 else 0.0,
                "prefix_trigger_rates": prefix_rates,
                "prefix_paper_bonus_percent": prefix_lifts,
                "best_prefix": best_prefix,
                "suffix_trigger_rates": suffix_rates,
                "suffix_observation_coverage": suffix_coverage,
                "suffix_paper_bonus_percent": suffix_lifts,
                "best_recommendable_suffix": best_suffix,
                "bo3_complete_series_blocks": bo3_blocks,
                "bo3_reaches_game3": (bo3_game3_weight / bo3_weight if bo3_weight > 0.0 else None),
            }
        )

    def summarize_prefixes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for prefix_id, rule in prefix_rules.items():
            rates = [float(row["prefix_trigger_rates"][prefix_id]) for row in rows]
            lifts = [float(row["prefix_paper_bonus_percent"][prefix_id]) for row in rows]
            result.append(
                {
                    "id": prefix_id,
                    "name": rule["name"],
                    "label": rule["label"],
                    "bonus_percent": float(rule["bonus_percent"]),
                    "trigger_rate": sum(rates) / len(rates),
                    "paper_expected_bonus_percent": sum(lifts) / len(lifts),
                    "best_pool_count": sum(row["best_prefix"] == prefix_id for row in rows),
                    "pool_count": len(rows),
                    "status": "estimated",
                    "provenance": "client_exact_category_plus_weighted_history",
                }
            )
        return _rank_rows(result, value_key="paper_expected_bonus_percent")

    def summarize_suffixes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for suffix_id, rule in suffix_rules.items():
            rates = [
                float(row["suffix_trigger_rates"][suffix_id])
                for row in rows
                if row["suffix_trigger_rates"][suffix_id] is not None
            ]
            lifts = [
                float(row["suffix_paper_bonus_percent"][suffix_id])
                for row in rows
                if row["suffix_paper_bonus_percent"][suffix_id] is not None
            ]
            if suffix_id in CONFLICTED_SUFFIXES:
                status = "conflicted_excluded"
            elif suffix_id in UNAVAILABLE_SUFFIXES or not rates:
                status = "unavailable"
            else:
                status = "estimated"
            result.append(
                {
                    "id": suffix_id,
                    "name": rule["name"],
                    "label": rule["label"],
                    "bonus_percent": float(rule["bonus_percent"]),
                    "trigger_rate": sum(rates) / len(rates) if rates else None,
                    "paper_expected_bonus_percent": sum(lifts) / len(lifts) if lifts else None,
                    "mean_observation_coverage": (
                        sum(float(row["suffix_observation_coverage"][suffix_id]) for row in rows) / len(rows)
                    ),
                    "best_pool_count": sum(row["best_recommendable_suffix"] == suffix_id for row in rows),
                    "pool_count": len(rows),
                    "status": status,
                    "provenance": (
                        "unavailable" if suffix_id == "fountain" else "opendota_parsed_match_detail"
                    ),
                }
            )
        estimated = [row for row in result if row["status"] == "estimated"]
        excluded = [row for row in result if row["status"] != "estimated"]
        return _rank_rows(estimated, value_key="paper_expected_bonus_percent") + [
            {**row, "rank": None} for row in excluded
        ]

    prefix_summary = summarize_prefixes(pool_rows)
    suffix_summary = summarize_suffixes(pool_rows)
    prefix_by_role = {}
    suffix_by_role = {}
    for role in ROLE_IDS:
        role_rows = [row for row in pool_rows if row["role"] == role]
        prefix_by_role[role] = summarize_prefixes(role_rows) if role_rows else []
        suffix_by_role[role] = summarize_suffixes(role_rows) if role_rows else []
    default_prefix = prefix_summary[0]
    default_suffix = next(row for row in suffix_summary if row["status"] == "estimated")
    underdog = next(row for row in suffix_summary if row["id"] == "loser")
    break_even = (
        float(default_suffix["paper_expected_bonus_percent"]) / float(underdog["bonus_percent"])
        if default_suffix["id"] == "clutch"
        else None
    )
    return {
        "method": {
            "aggregation": "equal_team_role_pools_then_weighted_complete_series_blocks",
            "unit": "player_game_for_prefix_and_game_for_suffix",
            "future_series_format_for_clutch": "bo3",
            "paper_bonus_definition": "trigger_rate_times_displayed_bonus_percent",
            "period_selection_effects_included": False,
        },
        "pool_count": len(pool_rows),
        "complete_series_blocks_across_pools": sum(int(row["complete_series_blocks"]) for row in pool_rows),
        "player_game_rows_across_pools": sum(int(row["player_game_rows"]) for row in pool_rows),
        "prefixes": prefix_summary,
        "prefixes_by_role": prefix_by_role,
        "suffixes": suffix_summary,
        "suffixes_by_role": suffix_by_role,
        "pools": pool_rows,
        "recommendation": {
            "default_prefix": default_prefix["id"],
            "default_suffix": default_suffix["id"],
            "prefix_confidence": "medium_low_conditional_on_final_banners",
            "suffix_confidence": "medium",
            "underdog_break_even_loss_rate": break_even,
            "production_p3_coach_status": "still_unavailable_excluded",
        },
    }
