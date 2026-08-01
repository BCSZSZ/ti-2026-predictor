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
    role_scoring = fantasy.get("role_scoring", {})
    if role_scoring.get("series") != "sum_top_two_games":
        block("fantasy-series-aggregation", "Fantasy series score must use the top two games")
    if role_scoring.get("period") != "maximum_series":
        block("fantasy-period-aggregation", "Fantasy period score must use the best series")

    for stat_id, stat in stats.items():
        if stat.get("provenance") not in {"exact", "derived", "proxy", "unavailable"}:
            block("fantasy-provenance", "invalid Fantasy provenance label", stat=stat_id)

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
            observed["event_team_ids"] = sorted(
                {int(value) for value in re.findall(r"m_unTeamID\s*=\s*(\d+)", event_text)}
            )
            observed["event_account_ids"] = sorted(
                {int(value) for value in re.findall(r"m_unAccountID\s*=\s*(\d+)", event_text)}
            )
            observed["event_roster_pairs"] = sorted(
                [
                    [int(account), int(team)]
                    for account, team in re.findall(
                        r"m_unAccountID\s*=\s*(\d+).*?m_unTeamID\s*=\s*(\d+)",
                        event_text,
                        flags=re.DOTALL,
                    )
                ]
            )

    localization_path = source_root / "resource/localization/dota_schinese.txt"
    if localization_path.exists():
        text = localization_path.read_text(encoding="utf-8", errors="replace")
        observed["late_first_blood_localized_10"] = bool(
            re.search(r"(?:10|１０)\s*分钟", text, flags=re.IGNORECASE)
        )
    return observed


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


def np_cumsum(values: list[int]) -> list[int]:
    total = 0
    result = []
    for value in values:
        total += value
        result.append(total)
    return result


def compare_observed(observed: dict[str, Any], rules: dict[str, Any]) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
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
    observed_scoring = observed.get("fantasy_scoring", {})
    for stat_id, client_key in CLIENT_SCORING_KEYS.items():
        rule = rules["fantasy"]["stats"][stat_id]
        expected = round(float(rule["factor"]) * 100)
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


def rule_snapshot_issues(as_of: datetime, paths: ProjectPaths = PATHS) -> list[AuditIssue]:
    current = latest_rule_snapshot(paths)
    if current is None:
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
    if snapshot.created_at > as_utc(as_of):
        issues.append(
            AuditIssue(
                code="rule-snapshot-after-as-of",
                severity="blocking",
                message="Latest rule snapshot was captured after the forecast as_of",
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
