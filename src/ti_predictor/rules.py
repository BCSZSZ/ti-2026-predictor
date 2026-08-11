from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ti_predictor.config import load_rules, load_tournament_manifest, rules_hash
from ti_predictor.hashing import file_manifest, sha256_json
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import AuditIssue, RuleSnapshot, as_utc, utc_now

EXPECTED_GROUP_CAPACITIES = [1, 2, 5, 5, 2, 1]
EXPECTED_GROUP_POINTS = [
    0,
    30,
    60,
    120,
    360,
    720,
    1200,
    1800,
    2520,
    3360,
    4320,
    5400,
    6600,
    7920,
    9360,
    10920,
    12000,
]
EXPECTED_MAIN_POINTS = [
    0,
    120,
    360,
    720,
    1200,
    1800,
    2520,
    3360,
    4320,
    5400,
    6600,
    7920,
    9360,
    10920,
    12000,
]

REQUIRED_SOURCE_SUFFIXES = {
    "scripts/events/international_2026.eventdef",
    "scripts/fantasy_crafting.vdata",
    "scripts/events/fantasy/dpc_fantasy_period_pointscore.eventactions",
    "resource/localization/dota_english.txt",
    "resource/localization/dota_schinese.txt",
}

CLIENT_SCORING_KEYS = {
    "kills": "FANTASY_SCORING_KILLS",
    "deaths": "FANTASY_SCORING_DEATHS",
    "creep_score": "FANTASY_SCORING_CS",
    "gpm": "FANTASY_SCORING_GPM",
    "madstone_collected": "FANTASY_SCORING_MADSTONE",
    "tower_kills": "FANTASY_SCORING_TOWER_KILLS",
    "wards_placed": "FANTASY_SCORING_WARDS_PLANTED",
    "camps_stacked": "FANTASY_SCORING_CAMPS_STACKED",
    "runes_grabbed": "FANTASY_SCORING_RUNES_GRABBED",
    "smokes_used": "FANTASY_SCORING_SMOKES_USED",
    "watchers_taken": "FANTASY_SCORING_WATCHERS_TAKEN",
    "lotuses_gained": "FANTASY_SCORING_LOTUSES_GAINED",
    "roshan_kills": "FANTASY_SCORING_ROSHAN_KILLS",
    "teamfight_participation": "FANTASY_SCORING_TEAMFIGHT_PARTICIPATION",
    "first_blood": "FANTASY_SCORING_FIRST_BLOOD",
    "stuns": "FANTASY_SCORING_STUNS",
    "tormentor_kills": "FANTASY_SCORING_TORMENTOR_KILLS",
    "courier_kills": "FANTASY_SCORING_COURIER_KILLS",
}

GEM_TYPE_COLORS = {
    "FANTASY_GEM_TYPE_RUBY": "red",
    "FANTASY_GEM_TYPE_SAPPHIRE": "blue",
    "FANTASY_GEM_TYPE_EMERALD": "green",
}
FANTASY_ROLE_IDS = {
    "FANTASY_ROLE_CORE": "core",
    "FANTASY_ROLE_MID": "mid",
    "FANTASY_ROLE_SUPPORT": "support",
}


def validate_rules(rules: dict[str, Any]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []

    def block(code: str, message: str, **context: Any) -> None:
        issues.append(AuditIssue(code=code, severity="blocking", message=message, context=context))

    group = rules.get("prediction", {}).get("group", {})
    capacities = [slot.get("count") for slot in group.get("slots", [])]
    if capacities != EXPECTED_GROUP_CAPACITIES:
        block("group-capacities", "group slot capacities differ from the golden fixture", got=capacities)
    if sum(value for value in capacities if isinstance(value, int)) != 16:
        block("group-slot-total", "group prediction slots must total 16", got=capacities)
    if group.get("cumulative_points") != EXPECTED_GROUP_POINTS:
        block("group-points", "group cumulative point table differs from the golden fixture")

    main = rules.get("prediction", {}).get("main", {})
    if main.get("nodes") != 14:
        block("main-nodes", "main event must contain fourteen prediction nodes")
    if main.get("cumulative_points") != EXPECTED_MAIN_POINTS:
        block("main-points", "main cumulative point table differs from the golden fixture")

    fantasy = rules.get("fantasy", {})
    stats = fantasy.get("stats", {})
    if len(stats) != 18:
        block("fantasy-stat-count", "Fantasy must contain exactly eighteen statistics", got=len(stats))
    periods = {period.get("id"): period for period in fantasy.get("periods", [])}
    expected_periods = {"group": (3, 40), "main": (5, 30)}
    for period_id, (slots, rolls) in expected_periods.items():
        period = periods.get(period_id, {})
        if (period.get("banner_slots"), period.get("new_rolls")) != (slots, rolls):
            block(
                f"fantasy-period-{period_id}",
                f"Fantasy {period_id} slots or rerolls differ from the golden fixture",
                got=period,
            )
    roll = fantasy.get("roll", {})
    offer = roll.get("offer", {})
    if offer != {
        "count": 3,
        "unique": True,
        "shared_across_banners": True,
        "apply_replaces_all": True,
        "refresh_replaces_all": True,
    }:
        block("fantasy-roll-offer", "Fantasy Roll offer contract differs from the accepted Group rule")
    if roll.get("token_cost") != {"apply": 1, "refresh": 1}:
        block("fantasy-roll-token-cost", "Fantasy apply and refresh must each consume one token")
    if roll.get("application_scope") != "selected_banner_only":
        block("fantasy-roll-application-scope", "a Roll option must affect only the selected Banner")
    if roll.get("supported_periods") != ["group"]:
        block("fantasy-roll-period", "P2 must support Group execution only")
    contract = roll.get("client_contract", {})
    positive_ids = contract.get("positive_operation_ids", [])
    zero_ids = contract.get("zero_weight_template_ids", [])
    if (
        len(positive_ids) != 20
        or len(set(positive_ids)) != 20
        or len(zero_ids) != 8
        or len(set(zero_ids)) != 8
        or set(positive_ids) & set(zero_ids)
        or contract.get("positive_weight_sum") != 168
    ):
        block("fantasy-roll-client-contract", "Fantasy Roll client operation contract is malformed")
    models = roll.get("transition_models", [])
    expected_models = {
        "client-weight-primary-v1": 1.0,
        "flattened-weights-v1": 0.5,
        "sharpened-weights-v1": 2.0,
    }
    if {item.get("id"): item.get("exposed_weight_power") for item in models} != expected_models:
        block("fantasy-roll-models", "Fantasy Roll transition models differ from the preregistration")
    assumptions = roll.get("outcome_assumptions", {})
    required_assumptions = {
        "reroll_may_repeat_current": True,
        "multi_target_draws": "independent",
        "one_color_target": "all_matching_slots_in_support",
        "increase_one_quality": "each_slot_increment_clamped",
        "increase_two_decrease_one": "each_decreased_slot_other_two_increment_clamped",
        "quality_bounds": [1, 5],
        "unweighted_model_choices": "uniform",
    }
    if assumptions != required_assumptions:
        block("fantasy-roll-assumptions", "Fantasy Roll outcome assumptions are incomplete")
    role_scoring = fantasy.get("role_scoring", {})
    if role_scoring.get("series") != "sum_top_two_games":
        block("fantasy-series-aggregation", "Fantasy series score must use the top two games")
    if role_scoring.get("period") != "maximum_series":
        block("fantasy-period-aggregation", "Fantasy period score must use the best series")

    for stat_id, stat in stats.items():
        if stat.get("provenance") not in {"exact", "derived", "proxy", "unavailable"}:
            block("fantasy-provenance", "invalid Fantasy provenance label", stat=stat_id)
    traits = fantasy.get("traits", [])
    if [item.get("shape_id") for item in traits] != [1, 2, 3, 4, 5]:
        block("fantasy-trait-shapes", "Fantasy Traits must map to the five client Shape IDs")

    for conflict in rules.get("conflicts", []):
        issues.append(
            AuditIssue(
                code=conflict["id"],
                severity="warning",
                message=f"Known client ambiguity: {conflict['policy']}",
                context=conflict,
            )
        )
    return issues


def status_from_issues(issues: list[AuditIssue]) -> str:
    if any(issue.severity == "blocking" for issue in issues):
        return "blocked"
    if any(issue.severity == "warning" for issue in issues):
        return "warning"
    return "publishable"


def _deduplicate_issues(issues: list[AuditIssue]) -> list[AuditIssue]:
    severity_rank = {"info": 0, "warning": 1, "blocking": 2}
    result: dict[str, AuditIssue] = {}
    for issue in issues:
        if issue.code == "late-first-blood-threshold":
            issue = issue.model_copy(update={"code": "late_first_blood_threshold"})
        current = result.get(issue.code)
        if current is None or severity_rank[issue.severity] > severity_rank[current.severity]:
            result[issue.code] = issue
    return list(result.values())


def _steam_build(dota_path: Path) -> str | None:
    steam_inf = dota_path / "steam.inf"
    if not steam_inf.exists():
        return None
    fields: dict[str, str] = {}
    for line in steam_inf.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    version = fields.get("ClientVersion") or fields.get("ServerVersion")
    revision = fields.get("SourceRevision")
    return f"{version}:{revision}" if version and revision else version


def find_dota_path(explicit: Path | None = None) -> Path:
    candidates = [
        explicit,
        Path(os.environ["DOTA_PATH"]) if os.getenv("DOTA_PATH") else None,
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota"),
        Path(r"C:\Program Files\Steam\steamapps\common\dota 2 beta\game\dota"),
    ]
    for candidate in candidates:
        if candidate and (candidate / "pak01_dir.vpk").is_file():
            return candidate.resolve()
    raise FileNotFoundError("Dota client not found; pass --dota-path or set DOTA_PATH")


def find_vrf_cli(explicit: Path | None = None) -> Path:
    candidates = [
        explicit,
        Path(os.environ["VRF_CLI"]) if os.getenv("VRF_CLI") else None,
        Path.home() / "AppData/Local/Temp/codex-ti-vrf-19.2/Source2Viewer-CLI.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    discovered = shutil.which("Source2Viewer-CLI") or shutil.which("Decompiler")
    if discovered:
        return Path(discovered).resolve()
    raise FileNotFoundError("ValveResourceFormat CLI not found; pass --vrf-cli or set VRF_CLI")


def _copy_source_tree(source_dir: Path, output: Path) -> list[Path]:
    copied: list[Path] = []
    normalized_required = {item.lower() for item in REQUIRED_SOURCE_SUFFIXES}
    for source in source_dir.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_dir).as_posix()
        if relative.lower() not in normalized_required:
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)
    return copied


def _extract_vpk(vrf_cli: Path, dota_path: Path, output: Path) -> list[Path]:
    vpk = dota_path / "pak01_dir.vpk"
    # VRF recreates the VPK output folder for each invocation, so all filters must
    # be passed at once. Valve mixes plain text resources with compiled *_c files.
    filters = sorted(
        {candidate for resource in REQUIRED_SOURCE_SUFFIXES for candidate in (resource, f"{resource}_c")}
    )
    command = [
        str(vrf_cli),
        "-i",
        str(vpk),
        "-o",
        str(output),
        "-f",
        ",".join(filters),
        "-d",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    copied = [item for item in output.rglob("*") if item.is_file()]
    if completed.returncode != 0 or not copied:
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"VRF extraction failed: {diagnostic}")
    return copied


def inspect_client_sources(source_root: Path) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    event_path = source_root / "scripts/events/international_2026.eventdef"
    if event_path.exists():
        text = event_path.read_text(encoding="utf-8", errors="replace")
        observed["group_max_grants"] = _value_after_block(text, "predictions_road_to_ti", "max_grants")
        observed["main_max_grants"] = _value_after_block(text, "predictions_main_event", "max_grants")
        observed["fantasy_rolls"] = [int(value) for value in re.findall(r'"rolls"\s+"(\d+)"', text)]
        group_block = _named_block(text, "predictions_road_to_ti")
        main_block = _named_block(text, "predictions_main_event")
        group_grants = [int(value) for value in re.findall(r'"points"\s+"(\d+)"', group_block)]
        main_grants = [int(value) for value in re.findall(r'"points"\s+"(\d+)"', main_block)]
        observed["group_point_grants"] = group_grants
        observed["group_cumulative_points"] = list(np_cumsum(group_grants))
        observed["main_point_grants"] = main_grants
        observed["main_cumulative_points"] = list(np_cumsum(main_grants))
        scoring = _named_block(_named_block(text, "fantasy"), "scoring")
        observed["fantasy_scoring"] = {
            key: int(value) for key, value in re.findall(r'"(FANTASY_SCORING_[A-Z_]+)"\s+"(\d+)"', scoring)
        }
        periods = _named_block(_named_block(text, "fantasy"), "period_definitions")
        observed["fantasy_period_starts"] = [
            int(value) for value in re.findall(r'"start"\s+"(\d+)"', periods)
        ]
        observed["fantasy_allowed_leagues"] = [
            int(value) for value in re.findall(r'"LEAGUE_REGION_UNSET"\s+"(\d+)"', periods)
        ]

    crafting_path = source_root / "scripts/fantasy_crafting.vdata"
    if crafting_path.exists():
        text = crafting_path.read_text(encoding="utf-8", errors="replace")
        observed["fantasy_roll"] = _inspect_fantasy_crafting(text)
        quality_start = text.find("m_vecQualities")
        quality_text = text[quality_start : quality_start + 2500] if quality_start >= 0 else text
        observed["qualities"] = [
            int(value) for value in re.findall(r"m_nBonus\s*=\s*(\d+)", quality_text)[:5]
        ]
        observed["quality_roll_weights"] = [
            int(value) for value in re.findall(r"m_nRollWeight\s*=\s*(\d+)", quality_text)[:5]
        ]
        observed["late_first_blood_internal_6"] = "first_blood_after_6_minutes" in text
        event_start = text.find('m_eEvent = "EVENT_ID_INTERNATIONAL_2026"')
        if event_start >= 0:
            event_text = text[event_start:]
            roster_entries = _event_roster_entries(event_text)
            active_entries = [entry for entry in roster_entries if entry["is_valid"]]
            inactive_entries = [entry for entry in roster_entries if not entry["is_valid"]]
            observed["event_roster_entries"] = roster_entries
            observed["event_team_ids"] = sorted({entry["team_id"] for entry in active_entries})
            observed["event_account_ids"] = sorted(entry["account_id"] for entry in active_entries)
            observed["event_roster_pairs"] = sorted(
                [entry["account_id"], entry["team_id"]] for entry in active_entries
            )
            observed["event_inactive_account_ids"] = sorted(entry["account_id"] for entry in inactive_entries)

    localization_path = source_root / "resource/localization/dota_schinese.txt"
    if localization_path.exists():
        text = localization_path.read_text(encoding="utf-8", errors="replace")
        observed["late_first_blood_localized_10"] = bool(
            re.search(r"(?:10|１０)\s*分钟", text, flags=re.IGNORECASE)
        )
    return observed


def _event_roster_entries(event_text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in re.finditer(r"\{(?P<body>[^{}]*m_unAccountID\s*=\s*\d+[^{}]*)\}", event_text):
        body = match.group("body")
        account = re.search(r"m_unAccountID\s*=\s*(\d+)", body)
        team = re.search(r"m_unTeamID\s*=\s*(\d+)", body)
        if account is None or team is None:
            continue
        name = re.search(r'm_strPlayerName\s*=\s*"([^"]*)"', body)
        validity = re.search(r"m_bIsValid\s*=\s*(true|false)", body, flags=re.IGNORECASE)
        entries.append(
            {
                "account_id": int(account.group(1)),
                "team_id": int(team.group(1)),
                "player_name": name.group(1) if name else "",
                "is_valid": validity is None or validity.group(1).lower() == "true",
            }
        )
    return sorted(entries, key=lambda entry: entry["account_id"])


def _value_after_block(text: str, block: str, key: str) -> int | None:
    start = text.find(f'"{block}"')
    if start < 0:
        return None
    match = re.search(rf'"{re.escape(key)}"\s+"(\d+)"', text[start : start + 1500])
    return int(match.group(1)) if match else None


def _named_block(text: str, name: str) -> str:
    start = text.find(f'"{name}"')
    if start < 0:
        return ""
    opening = text.find("{", start)
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening : index + 1]
    return ""


def _balanced_value(text: str, opening: int, opening_char: str, closing_char: str) -> str:
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
        elif char == opening_char:
            depth += 1
        elif char == closing_char:
            depth -= 1
            if depth == 0:
                return text[opening : index + 1]
    return ""


def _assignment_list(text: str, key: str, *, start: int = 0) -> str:
    match = re.search(rf"\b{re.escape(key)}\s*=", text[start:])
    if match is None:
        return ""
    assignment = start + match.end()
    opening = text.find("[", assignment)
    if opening < 0:
        return ""
    return _balanced_value(text, opening, "[", "]")


def _top_level_objects(list_text: str) -> list[str]:
    objects: list[str] = []
    index = 0
    while index < len(list_text):
        opening = list_text.find("{", index)
        if opening < 0:
            break
        block = _balanced_value(list_text, opening, "{", "}")
        if not block:
            break
        objects.append(block)
        index = opening + len(block)
    return objects


def _scalar_value(text: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*(?:\"([^\"]+)\"|(-?\d+))", text)
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _client_target_flags(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _client_mutation_targets_supported(operation: str | None, targets: list[str]) -> bool:
    target_set = set(targets)
    if len(target_set) != len(targets):
        return False
    if operation in {
        "k_eFantasyMutationOperation_IncreaseOneQuality",
        "k_eFantasyMutationOperation_IncreaseTwoQualitiesDecreaseOne",
    }:
        return target_set == {"k_eFantasyMutationTarget_All"}
    color_flags = {
        "k_eFantasyMutationTarget_Rubies",
        "k_eFantasyMutationTarget_Sapphires",
        "k_eFantasyMutationTarget_Emeralds",
    }
    selector_flags = {
        "k_eFantasyMutationTarget_AllColor",
        "k_eFantasyMutationTarget_OneColor",
        "k_eFantasyMutationTarget_FirstColor",
        "k_eFantasyMutationTarget_LastColor",
    }
    return (
        len(target_set) == 2 and len(target_set & color_flags) == 1 and len(target_set & selector_flags) == 1
    )


def _inspect_fantasy_crafting(text: str) -> dict[str, Any]:
    gems: list[dict[str, Any]] = []
    scoring_to_stat = {client_key: stat_id for stat_id, client_key in CLIENT_SCORING_KEYS.items()}
    for index, block in enumerate(_top_level_objects(_assignment_list(text, "m_vecGems"))):
        client_type = _scalar_value(block, "m_eType")
        if client_type is None and index == 0:
            client_type = "FANTASY_GEM_TYPE_RUBY"
        stats_text = _assignment_list(block, "m_eStats")
        client_stats = re.findall(r'"(FANTASY_SCORING_[A-Z_]+)"', stats_text)
        gems.append(
            {
                "client_type": client_type,
                "color": GEM_TYPE_COLORS.get(str(client_type)),
                "stat_ids": [scoring_to_stat.get(value, value) for value in client_stats],
            }
        )

    traits: list[dict[str, Any]] = []
    for block in _top_level_objects(_assignment_list(text, "m_vecShapes")):
        shape_id = _scalar_value(block, "m_unShapeID")
        traits.append(
            {
                "shape_id": int(shape_id) if shape_id is not None else None,
                "client_behavior": _scalar_value(block, "m_eShapeBehavior"),
                "name_key": _scalar_value(block, "m_sLocName"),
            }
        )

    qualities: list[dict[str, Any]] = []
    for block in _top_level_objects(_assignment_list(text, "m_vecQualities")):
        quality_id = _scalar_value(block, "m_unQualityID")
        bonus = _scalar_value(block, "m_nBonus")
        weight = _scalar_value(block, "m_nRollWeight")
        qualities.append(
            {
                "tier": int(quality_id) if quality_id is not None else None,
                "bonus_percent": int(bonus) if bonus is not None else None,
                "roll_weight": int(weight) if weight is not None else None,
            }
        )

    banners: list[dict[str, Any]] = []
    for block in _top_level_objects(_assignment_list(text, "m_vecTablets")):
        role = FANTASY_ROLE_IDS.get(str(_scalar_value(block, "m_eRole")))
        slots: list[dict[str, Any]] = []
        for slot_block in _top_level_objects(_assignment_list(block, "m_vecGemSlots")):
            slot = _scalar_value(slot_block, "m_unGemSlot")
            required_level = _scalar_value(slot_block, "m_nRequiredTabletLevel")
            client_type = _scalar_value(slot_block, "m_eGemType")
            slots.append(
                {
                    "slot": int(slot) if slot is not None else None,
                    "color": GEM_TYPE_COLORS.get(str(client_type)),
                    "required_tablet_level": int(required_level) if required_level is not None else 1,
                }
            )
        banners.append({"role": role, "slots": slots})

    tablets_start = text.find("m_vecTablets")
    operations_list = _assignment_list(text, "m_vecOperations", start=max(0, tablets_start))
    operation_wrappers = _top_level_objects(operations_list)
    wrapper = operation_wrappers[0] if operation_wrappers else ""
    offer_size = _scalar_value(wrapper, "m_unOperationCount")
    operation_list = _assignment_list(wrapper, "m_vecOperations")
    operations: list[dict[str, Any]] = []
    for block in _top_level_objects(operation_list):
        operation_id = _scalar_value(block, "m_unOperationID")
        roll_weight = _scalar_value(block, "m_nRollWeight")
        mutations_list = _assignment_list(block, "m_vecOperations")
        prefix = block[: block.find("m_vecOperations")] if mutations_list else block
        mutations: list[dict[str, Any]] = []
        for mutation in _top_level_objects(mutations_list):
            raw_target = _scalar_value(mutation, "m_eTarget")
            mutations.append(
                {
                    "operation": _scalar_value(mutation, "m_eOperation"),
                    "targets": _client_target_flags(raw_target) if raw_target else [],
                }
            )
        operations.append(
            {
                "operation_id": int(operation_id) if operation_id is not None else None,
                "roll_weight": int(roll_weight) if roll_weight is not None else None,
                "operation_target": _scalar_value(prefix, "m_eTarget"),
                "description_key": _scalar_value(block, "m_sLocDescription"),
                "mutations": mutations,
            }
        )

    return {
        "offer_size": int(offer_size) if offer_size is not None else None,
        "gems": gems,
        "traits": traits,
        "qualities": qualities,
        "banners": banners,
        "operations": operations,
    }


def np_cumsum(values: list[int]) -> list[int]:
    total = 0
    result = []
    for value in values:
        total += value
        result.append(total)
    return result


def compare_observed(observed: dict[str, Any], rules: dict[str, Any]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []

    def client_block(code: str, message: str, **context: Any) -> None:
        issues.append(AuditIssue(code=code, severity="blocking", message=message, context=context))

    checks = {
        "group_max_grants": 16,
        "main_max_grants": 14,
        "group_cumulative_points": EXPECTED_GROUP_POINTS[1:],
        "main_cumulative_points": EXPECTED_MAIN_POINTS[1:],
        "qualities": [10, 30, 60, 100, 150],
        "quality_roll_weights": [10, 20, 10, 5, 2],
        "fantasy_period_starts": [1786543200, 1787191200],
        "fantasy_allowed_leagues": [19719, 19719],
    }
    for key, expected in checks.items():
        value = observed.get(key)
        if value is None:
            issues.append(
                AuditIssue(
                    code=f"client-{key}-missing",
                    severity="blocking",
                    message=f"Client snapshot did not expose {key}",
                )
            )
        elif value != expected:
            issues.append(
                AuditIssue(
                    code=f"client-{key}-mismatch",
                    severity="blocking",
                    message=f"Client value for {key} differs from the golden fixture",
                    context={"expected": expected, "observed": value},
                )
            )
    fantasy = rules["fantasy"]
    roll_contract = fantasy["roll"]["client_contract"]
    fantasy_roll = observed.get("fantasy_roll")
    if not isinstance(fantasy_roll, dict):
        client_block("client-fantasy-roll-missing", "Client snapshot did not expose Fantasy Roll rules")
    else:
        if fantasy_roll.get("offer_size") != fantasy["roll"]["offer"]["count"]:
            client_block(
                "client-fantasy-roll-offer-size",
                "Client Roll offer count differs from the canonical contract",
                observed=fantasy_roll.get("offer_size"),
            )
        expected_qualities = [
            {
                "tier": int(item["tier"]),
                "bonus_percent": int(item["bonus_percent"]),
                "roll_weight": int(item["roll_weight"]),
            }
            for item in fantasy["qualities"]
        ]
        if fantasy_roll.get("qualities") != expected_qualities:
            client_block(
                "client-fantasy-roll-qualities",
                "Client Quality definitions differ from canonical rules",
            )
        expected_gems = []
        for color, client_type in (
            ("red", "FANTASY_GEM_TYPE_RUBY"),
            ("blue", "FANTASY_GEM_TYPE_SAPPHIRE"),
            ("green", "FANTASY_GEM_TYPE_EMERALD"),
        ):
            expected_gems.append(
                {
                    "client_type": client_type,
                    "color": color,
                    "stat_ids": [
                        stat_id
                        for stat_id, definition in fantasy["stats"].items()
                        if definition["color"] == color
                    ],
                }
            )
        if fantasy_roll.get("gems") != expected_gems:
            client_block(
                "client-fantasy-roll-gems",
                "Client legal Stats by Gem color differ from canonical rules",
            )
        expected_traits = [
            {
                "shape_id": int(item["shape_id"]),
                "client_behavior": item["client_behavior"],
                "name_key": {
                    "fractal": "#DOTA_FantasyCraft_Trait_UniqueQualities",
                    "benevolent": "#DOTA_FantasyCraft_Trait_AdjBonus",
                    "vampiric": "#DOTA_FantasyCraft_Trait_Steal",
                    "unique": "#DOTA_FantasyCraft_Trait_Unique",
                    "friendly": "#DOTA_FantasyCraft_Trait_Multiples",
                }[item["id"]],
            }
            for item in fantasy["traits"]
        ]
        if fantasy_roll.get("traits") != expected_traits:
            client_block(
                "client-fantasy-roll-traits",
                "Client Trait Shapes differ from canonical rules",
            )
        required_levels = [1, 1, 1, 2, 3]
        expected_banners = [
            {
                "role": role,
                "slots": [
                    {"slot": index, "color": color, "required_tablet_level": required_levels[index - 1]}
                    for index, color in enumerate(colors, start=1)
                ],
            }
            for role, colors in fantasy["role_banners"].items()
        ]
        if fantasy_roll.get("banners") != expected_banners:
            client_block(
                "client-fantasy-roll-banners",
                "Client War Banner slot colors differ from canonical rules",
            )

        operations = fantasy_roll.get("operations")
        if not isinstance(operations, list):
            client_block(
                "client-fantasy-roll-operations",
                "Client snapshot did not expose a Roll operation list",
            )
        else:
            ids = [item.get("operation_id") for item in operations]
            if len(ids) != len(set(ids)):
                client_block("client-fantasy-roll-duplicate-id", "Client Roll operation IDs repeat")
            positive = [
                item
                for item in operations
                if isinstance(item.get("roll_weight"), int) and item["roll_weight"] > 0
            ]
            zero = [item for item in operations if item.get("roll_weight") == 0]
            if [item["operation_id"] for item in positive] != roll_contract["positive_operation_ids"]:
                client_block(
                    "client-fantasy-roll-positive-ids",
                    "Client positive Roll operation IDs differ from the frozen contract",
                )
            if [item["operation_id"] for item in zero] != roll_contract["zero_weight_template_ids"]:
                client_block(
                    "client-fantasy-roll-zero-ids",
                    "Client zero-weight Roll templates differ from the frozen contract",
                )
            if sum(item["roll_weight"] for item in positive) != roll_contract["positive_weight_sum"]:
                client_block(
                    "client-fantasy-roll-weight-sum",
                    "Client positive Roll weights differ from the frozen contract",
                )
            supported_mutations = {
                "k_eFantasyMutationOperation_RollQuality",
                "k_eFantasyMutationOperation_RollShape",
                "k_eFantasyMutationOperation_RollStat",
                "k_eFantasyMutationOperation_IncreaseOneQuality",
                "k_eFantasyMutationOperation_IncreaseTwoQualitiesDecreaseOne",
            }
            supported_targets = {
                "k_eFantasyMutationTarget_All",
                "k_eFantasyMutationTarget_Rubies",
                "k_eFantasyMutationTarget_Sapphires",
                "k_eFantasyMutationTarget_Emeralds",
                "k_eFantasyMutationTarget_AllColor",
                "k_eFantasyMutationTarget_OneColor",
                "k_eFantasyMutationTarget_FirstColor",
                "k_eFantasyMutationTarget_LastColor",
            }
            for operation in positive:
                mutations = operation.get("mutations")
                if (
                    not isinstance(mutations, list)
                    or len(mutations) != 1
                    or mutations[0].get("operation") not in supported_mutations
                    or not set(mutations[0].get("targets", [])) <= supported_targets
                    or not _client_mutation_targets_supported(
                        mutations[0].get("operation"), mutations[0].get("targets", [])
                    )
                    or not operation.get("description_key")
                ):
                    client_block(
                        "client-fantasy-roll-unsupported-operation",
                        "A positive client Roll operation is malformed or unsupported",
                        operation=operation,
                    )
    observed_scoring = observed.get("fantasy_scoring", {})
    for stat_id, client_key in CLIENT_SCORING_KEYS.items():
        rule = rules["fantasy"]["stats"][stat_id]
        expected = round(float(rule["factor"]))
        value = observed_scoring.get(client_key)
        if value != expected:
            issues.append(
                AuditIssue(
                    code=f"client-scoring-{stat_id}",
                    severity="blocking",
                    message=f"Client Fantasy coefficient differs for {stat_id}",
                    context={"expected": expected, "observed": value, "client_key": client_key},
                )
            )
    rolls = observed.get("fantasy_rolls", [])
    if not {30, 40}.issubset(set(rolls)):
        issues.append(
            AuditIssue(
                code="client-fantasy-rolls",
                severity="blocking",
                message="Client snapshot does not contain both 40 and 30 Fantasy reroll grants",
                context={"observed": rolls},
            )
        )
    if observed.get("late_first_blood_internal_6") and observed.get("late_first_blood_localized_10"):
        issues.append(
            AuditIssue(
                code="late_first_blood_threshold",
                severity="warning",
                message="Client internal and localized late-first-blood thresholds conflict",
            )
        )
    return issues


def create_rule_snapshot(
    *,
    as_of: datetime,
    dota_path: Path | None = None,
    vrf_cli: Path | None = None,
    source_dir: Path | None = None,
    paths: ProjectPaths = PATHS,
) -> tuple[RuleSnapshot, Path]:
    cutoff = as_utc(as_of)
    rules = load_rules(paths.rules)
    tournament = load_tournament_manifest(paths.tournament)
    canonical_hash = rules_hash(paths.rules)
    created = utc_now()

    with tempfile.TemporaryDirectory(prefix="ti-rules-") as temp_name:
        temp = Path(temp_name)
        if source_dir:
            copied = _copy_source_tree(source_dir.resolve(), temp)
            build = _steam_build(find_dota_path(dota_path)) if dota_path else None
        else:
            client = find_dota_path(dota_path)
            copied = _extract_vpk(find_vrf_cli(vrf_cli), client, temp)
            build = _steam_build(client)

        issues = validate_rules(rules)
        observed = inspect_client_sources(temp)
        issues.extend(compare_observed(observed, rules))
        if observed.get("event_team_ids") is not None:
            expected_team_ids = sorted(team.team_id for team in tournament.teams)
            expected_account_ids = sorted(
                player.account_id
                for team in tournament.teams
                for players in team.players.values()
                for player in players
            )
            expected_pairs = sorted(
                [player.account_id, team.team_id]
                for team in tournament.teams
                for players in team.players.values()
                for player in players
            )
            for key, expected in (
                ("event_team_ids", expected_team_ids),
                ("event_account_ids", expected_account_ids),
                ("event_roster_pairs", expected_pairs),
            ):
                if observed.get(key) != expected:
                    issues.append(
                        AuditIssue(
                            code=f"client-{key}-mismatch",
                            severity="blocking",
                            message=f"Client {key} differs from config/ti2026.yaml",
                        )
                    )
        found = {path.relative_to(temp).as_posix().lower() for path in copied}
        for required in sorted(REQUIRED_SOURCE_SUFFIXES):
            if required.lower() not in found:
                issues.append(
                    AuditIssue(
                        code="client-source-missing",
                        severity="blocking",
                        message=f"Required client source is absent: {required}",
                    )
                )

        manifest = file_manifest(temp)
        snapshot_hash = sha256_json(
            {"files": manifest, "observed": observed, "canonical_rules_sha256": canonical_hash}
        )
        snapshot_id = f"{created.strftime('%Y%m%dT%H%M%SZ')}-{snapshot_hash[:12]}"
        output = paths.raw / "rules" / snapshot_id
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temp, output)

        issues = _deduplicate_issues(issues)
        snapshot = RuleSnapshot(
            snapshot_id=snapshot_id,
            event_id=rules["event"]["event_id"],
            as_of=cutoff,
            created_at=created,
            source="dota_client",
            steam_build=build,
            source_files=manifest,
            canonical_rules_sha256=canonical_hash,
            snapshot_sha256=snapshot_hash,
            status=status_from_issues(issues),
            issues=issues,
            observed=observed,
        )
    snapshot_path = output / "rule_snapshot.json"
    snapshot_path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return snapshot, snapshot_path


def validate_snapshot(path: Path | None = None, paths: ProjectPaths = PATHS) -> tuple[str, list[AuditIssue]]:
    rules = load_rules(paths.rules)
    issues = validate_rules(rules)
    if path is None:
        latest = latest_rule_snapshot(paths)
        if latest is None:
            issues.append(
                AuditIssue(
                    code="rule-snapshot-missing",
                    severity="blocking",
                    message="No Dota client rule snapshot is available",
                )
            )
        else:
            path = latest[1]
    if path:
        snapshot = RuleSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        if snapshot.canonical_rules_sha256 != rules_hash(paths.rules):
            issues.append(
                AuditIssue(
                    code="snapshot-rule-hash",
                    severity="blocking",
                    message="Rule snapshot was created against a different canonical rules file",
                )
            )
        issues.extend(snapshot.issues)
        issues = _deduplicate_issues(issues)
    return status_from_issues(issues), issues


def latest_rule_snapshot(paths: ProjectPaths = PATHS) -> tuple[RuleSnapshot, Path] | None:
    candidates = sorted((paths.raw / "rules").glob("*/rule_snapshot.json"), reverse=True)
    for snapshot_path in candidates:
        try:
            snapshot = RuleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
            return snapshot, snapshot_path
        except (OSError, ValueError):
            continue
    return None


def rule_snapshot_at(
    as_of: datetime,
    paths: ProjectPaths = PATHS,
) -> tuple[RuleSnapshot, Path] | None:
    """Return the newest snapshot that was both observed and captured by the UTC cutoff."""

    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("rule snapshot resolution requires an explicit UTC as_of")
    available: list[tuple[RuleSnapshot, Path]] = []
    for snapshot_path in (paths.raw / "rules").glob("*/rule_snapshot.json"):
        try:
            snapshot = RuleSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if snapshot.as_of <= cutoff and snapshot.created_at <= cutoff:
            available.append((snapshot, snapshot_path))
    if not available:
        return None
    return max(available, key=lambda item: (item[0].created_at, item[0].snapshot_id))


def rule_snapshot_issues(as_of: datetime, paths: ProjectPaths = PATHS) -> list[AuditIssue]:
    current = rule_snapshot_at(as_of, paths)
    if current is None:
        latest = latest_rule_snapshot(paths)
        if latest is not None:
            return [
                AuditIssue(
                    code="rule-snapshot-after-as-of",
                    severity="blocking",
                    message="No rule snapshot had been captured by the forecast as_of",
                )
            ]
        return [
            AuditIssue(
                code="rule-snapshot-missing",
                severity="blocking",
                message="No Dota client rule snapshot is available for this forecast",
            )
        ]
    snapshot, _ = current
    issues: list[AuditIssue] = []
    if snapshot.status == "blocked":
        issues.append(
            AuditIssue(
                code="rule-snapshot-blocked",
                severity="blocking",
                message=f"Latest Dota client rule snapshot {snapshot.snapshot_id} is blocked",
            )
        )
    if snapshot.canonical_rules_sha256 != rules_hash(paths.rules):
        issues.append(
            AuditIssue(
                code="rule-snapshot-canonical-drift",
                severity="blocking",
                message="Latest client snapshot targets a different canonical rules hash",
            )
        )
    return issues


def parse_as_of(value: str | None) -> datetime:
    return as_utc(value) if value else datetime.now(UTC)
