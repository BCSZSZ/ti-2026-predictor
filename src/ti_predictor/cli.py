from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal

import typer

from ti_predictor import __version__
from ti_predictor.audit import audit_run
from ti_predictor.backtesting import run_ti2025_backtest
from ti_predictor.config import load_rules, load_tournament_manifest
from ti_predictor.fantasy.advisor_reporting import generate_group_advisor_evidence
from ti_predictor.fantasy.cross_audit_reporting import generate_group_cross_audit_evidence
from ti_predictor.fantasy.current_advisor import prepare_current_advisor_context
from ti_predictor.fantasy.main_evidence import (
    build_main_evidence_snapshot,
    validate_actual_main_evidence_refresh,
)
from ti_predictor.fantasy.main_multi_forecast_builder import (
    build_main_multi_forecast_release,
    load_main_multi_forecast_build_config,
)
from ti_predictor.fantasy.main_publication import generate_main_publication_evidence
from ti_predictor.fantasy.main_scenarios import (
    build_main_scenario_set_from_model,
    build_projected_main_scenario_set_from_group,
)
from ti_predictor.fantasy.main_solver_release import (
    MAIN_SOLVER_RELEASE_ID,
    load_main_solver_policy,
    load_main_solver_release_context,
    main_solver_readiness,
    write_main_solver_release_bundle,
)
from ti_predictor.fantasy.main_title_runtime import build_main_title_runtime_evidence
from ti_predictor.fantasy.playbook_reporting import generate_group_playbook_evidence
from ti_predictor.fantasy.solver_release import (
    SOLVER_RELEASE_ID,
    load_solver_release_context,
    write_solver_release_bundle,
)
from ti_predictor.fantasy.solver_reporting import generate_group_solver_evidence
from ti_predictor.fantasy.title_reporting import generate_group_title_evidence
from ti_predictor.forecasting import (
    generate_bracket,
    generate_fantasy,
    generate_group,
    generate_group_fantasy_evidence,
    load_strength_model_as_of,
)
from ti_predictor.hashing import sha256_json
from ti_predictor.ingest.main_actual import (
    freeze_main_actual_snapshot,
    load_main_actual_workspace,
    prepare_main_actual_workspace,
)
from ti_predictor.ingest.opendota import (
    DEFAULT_OPENDOTA_RUN_REQUEST_LIMIT,
    OpenDotaSafetyStop,
    sync_fantasy_player_history,
    sync_opendota,
)
from ti_predictor.ingest.replay import ReplayParser, sync_replay_fantasy_history
from ti_predictor.ocr import inspect_screenshot
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.rules import create_rule_snapshot, parse_as_of, validate_snapshot


def _configure_windows_utf8() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_configure_windows_utf8()

app = typer.Typer(
    name="ti",
    help="TI 2026 游戏内预测与梦幻挑战本地决策台。",
    no_args_is_help=False,
    invoke_without_command=True,
)
rules_app = typer.Typer(help="从 Dota 客户端快照并校验活动规则。", no_args_is_help=True)
data_app = typer.Typer(help="同步、缓存和规范化数据。", no_args_is_help=True)
forecast_app = typer.Typer(help="生成小组或主赛事预测。", no_args_is_help=True)
fantasy_app = typer.Typer(help="生成 Fantasy 推荐。", no_args_is_help=True)
ocr_app = typer.Typer(help="识别用户提供的 Fantasy 截图。", no_args_is_help=True)
consumer_app = typer.Typer(help="运行不依赖原始数据的玩家应用。", no_args_is_help=True)
dev_app = typer.Typer(help="运行需要本地构建数据的维护者工具。", no_args_is_help=True)
app.add_typer(rules_app, name="rules")
app.add_typer(data_app, name="data")
app.add_typer(forecast_app, name="forecast")
app.add_typer(fantasy_app, name="fantasy")
app.add_typer(ocr_app, name="ocr")
app.add_typer(consumer_app, name="app")
app.add_typer(dev_app, name="dev")


def _echo(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_for_status(status: str) -> None:
    if status == "blocked":
        raise typer.Exit(code=2)


def _stop_for_opendota_safety(error: OpenDotaSafetyStop) -> None:
    _echo({"status": "stopped", "reason": str(error)})
    raise typer.Exit(code=2)


@app.callback()
def root(
    version: Annotated[bool, typer.Option("--version", help="显示版本后退出。")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@rules_app.command("snapshot")
def rules_snapshot(
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="规则可用截止时间，ISO-8601 且必须带时区。")
    ] = None,
    dota_path: Annotated[Path | None, typer.Option("--dota-path", exists=True, file_okay=False)] = None,
    vrf_cli: Annotated[Path | None, typer.Option("--vrf-cli", exists=True, dir_okay=False)] = None,
    source_dir: Annotated[
        Path | None,
        typer.Option(
            "--source-dir",
            exists=True,
            file_okay=False,
            help="使用已由 VRF 解包的目录；主要用于复核和测试。",
        ),
    ] = None,
) -> None:
    snapshot, path = create_rule_snapshot(
        as_of=parse_as_of(as_of),
        dota_path=dota_path,
        vrf_cli=vrf_cli,
        source_dir=source_dir,
    )
    _echo({"path": str(path), **snapshot.model_dump(mode="json")})
    _exit_for_status(snapshot.status)


@rules_app.command("validate")
def rules_validate(
    snapshot: Annotated[Path | None, typer.Option("--snapshot", exists=True, dir_okay=False)] = None,
) -> None:
    status, issues = validate_snapshot(snapshot)
    _echo({"status": status, "issues": [item.model_dump(mode="json") for item in issues]})
    _exit_for_status(status)


@data_app.command("sync")
def data_sync(
    as_of: Annotated[str, typer.Option("--as-of", help="只纳入该时点前已公开的比赛。")],
    year: Annotated[
        int | None,
        typer.Option(
            "--year",
            min=2013,
            help="同步该 UTC 日历年的完整 OpenDota 职业比赛目录；默认使用 as-of 所在年份。",
        ),
    ] = None,
    pro_catalog: Annotated[
        bool,
        typer.Option(
            "--pro-catalog/--no-pro-catalog",
            help="是否分页同步 OpenDota /proMatches 职业比赛目录。",
        ),
    ] = True,
    league: Annotated[
        list[int] | None, typer.Option("--league", help="可重复指定；默认使用配置中的历史与当前联赛。")
    ] = None,
    details: Annotated[
        bool, typer.Option("--details/--no-details", help="是否下载逐场详情用于 Fantasy。")
    ] = True,
    team_history: Annotated[
        bool,
        typer.Option(
            "--team-history/--no-team-history",
            help="是否同步当前 16 队最近比赛摘要用于队伍强度；默认开启。",
        ),
    ] = True,
    team_detail_limit: Annotated[
        int,
        typer.Option(
            "--team-detail-limit",
            min=0,
            help="为每支当前参赛队下载最近 N 场详情用于 Fantasy；0 表示仅摘要。",
        ),
    ] = 20,
    max_matches: Annotated[
        int | None,
        typer.Option("--max-matches", min=1, help="只下载最近 N 场联赛逐场详情，适合烟雾测试。"),
    ] = None,
    request_limit: Annotated[
        int,
        typer.Option(
            "--request-limit",
            min=1,
            help="本次进程最多发出的 OpenDota 请求尝试数；重试也计数。",
        ),
    ] = DEFAULT_OPENDOTA_RUN_REQUEST_LIMIT,
    refresh_details: Annotated[
        bool,
        typer.Option(
            "--refresh-details",
            help="重新抓取已有逐场详情；默认按 match_id 断点续传。",
        ),
    ] = False,
) -> None:
    cutoff = parse_as_of(as_of)
    try:
        result = sync_opendota(
            as_of=cutoff,
            league_ids=league,
            pro_year=(year or cutoff.year) if pro_catalog else None,
            include_details=details,
            include_team_history=team_history,
            team_history_detail_limit=team_detail_limit,
            max_matches=max_matches,
            request_limit=request_limit,
            refresh_details=refresh_details,
        )
    except OpenDotaSafetyStop as error:
        _stop_for_opendota_safety(error)
    _echo(
        {
            "status": result.status,
            "pro_year": result.pro_year,
            "leagues": result.requested_leagues,
            "match_catalog_rows": result.match_count,
            "professional_matches": result.pro_match_count,
            "fantasy_performance_samples": result.fantasy_sample_count,
            "detailed_matches": result.detailed_match_count,
            "request_attempts": result.request_attempts,
            "monthly_keyed_request_attempts": result.monthly_keyed_request_attempts,
            "data_sha256": result.data_sha256,
            "paths": {
                "matches": str(result.matches_path),
                "fantasy_performance_samples": str(result.fantasy_samples_path),
                "rosters": str(result.roster_path),
                "leagues": str(result.leagues_path) if result.leagues_path else None,
                "patches": str(result.patches_path) if result.patches_path else None,
            },
            "issues": [item.model_dump(mode="json") for item in result.issues],
        }
    )
    _exit_for_status(result.status)


@data_app.command("fantasy-history")
def data_fantasy_history(
    as_of: Annotated[str, typer.Option("--as-of", help="只纳入该时点前已完成的比赛。")],
    year: Annotated[
        int | None,
        typer.Option("--year", min=2013, help="目标 UTC 日历年；默认使用 as-of 所在年份。"),
    ] = None,
    tier: Annotated[
        list[str] | None,
        typer.Option("--tier", help="可重复指定，仅接受 premium/professional。"),
    ] = None,
    history_days: Annotated[
        int | None,
        typer.Option(
            "--history-days",
            min=1,
            help="玩家历史重叠窗口；首次同步默认覆盖目标年，增量时可缩短。",
        ),
    ] = None,
    max_matches: Annotated[
        int | None,
        typer.Option("--max-matches", min=1, help="本次最多新请求多少场详情，适合烟雾测试。"),
    ] = None,
    checkpoint_every: Annotated[
        int,
        typer.Option("--checkpoint-every", min=1, help="每多少个访问目标检查点落盘。"),
    ] = 25,
    daily_reserve: Annotated[
        int,
        typer.Option("--daily-reserve", min=0, help="停止前保留的 OpenDota 当日请求额度。"),
    ] = 50,
    request_limit: Annotated[
        int,
        typer.Option(
            "--request-limit",
            min=1,
            help="本次进程最多发出的 OpenDota 请求尝试数；重试也计数。",
        ),
    ] = DEFAULT_OPENDOTA_RUN_REQUEST_LIMIT,
    refresh_details: Annotated[
        bool,
        typer.Option("--refresh-details", help="重新请求已经完整解析的详情。"),
    ] = False,
) -> None:
    cutoff = parse_as_of(as_of)

    def progress(payload: dict) -> None:
        typer.echo(json.dumps(payload, ensure_ascii=False, default=str), err=True)

    try:
        result = sync_fantasy_player_history(
            as_of=cutoff,
            year=year,
            league_tiers=set(tier) if tier else None,
            history_days=history_days,
            max_matches=max_matches,
            checkpoint_every=checkpoint_every,
            daily_request_reserve=daily_reserve,
            request_limit=request_limit,
            refresh_details=refresh_details,
            progress=progress,
        )
    except OpenDotaSafetyStop as error:
        _stop_for_opendota_safety(error)
    _echo(
        {
            "status": result.status,
            "target_players": result.target_players,
            "target_matches": result.target_matches,
            "target_player_games": result.target_player_games,
            "requested_details": result.requested_details,
            "reused_raw_details": result.reused_raw_details,
            "skipped_parsed_details": result.skipped_parsed_details,
            "parsed_complete": result.parsed_complete,
            "base_complete": result.base_complete,
            "failed_details": result.failed_details,
            "remaining_details": result.remaining_details,
            "rate_limit_remaining_day": result.rate_limit_remaining_day,
            "request_attempts": result.request_attempts,
            "monthly_keyed_request_attempts": result.monthly_keyed_request_attempts,
            "data_sha256": result.data_sha256,
            "paths": {
                "scope": str(result.scope_path),
                "matches": str(result.matches_path),
                "fantasy_performance_samples": str(result.fantasy_samples_path),
                "detail_status": str(result.detail_status_path),
            },
            "issues": [item.model_dump(mode="json") for item in result.issues],
        }
    )
    _exit_for_status(result.status)


@data_app.command("main-actual-materialize")
def data_main_actual_materialize(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="Main actual 数据与模型的显式 UTC 截止时间。"),
    ],
    catalog_audit: Annotated[
        Path,
        typer.Option("--catalog-audit", exists=True, dir_okay=False),
    ] = PATHS.raw / "opendota/audits/20260816T122321Z/manifest.json",
    workspace: Annotated[
        Path,
        typer.Option("--workspace", file_okay=False),
    ] = PATHS.processed / "work/main-actual-20260816T140616Z",
) -> None:
    """Materialize Main actual processed evidence from immutable local raw captures."""

    result = prepare_main_actual_workspace(
        as_of=parse_as_of(as_of),
        catalog_audit_path=catalog_audit,
        workspace_path=workspace,
    )
    _echo(
        {
            "status": "prepared-replay-pending",
            "as_of": result.as_of,
            "workspace": str(result.path),
            "stage_game_count": result.stage_game_count,
            "entrant_team_ids": list(result.entrant_team_ids),
            "replay_target_game_count": len(result.replay_target_match_ids),
            "replay_target_match_ids_sha256": result.replay_target_match_ids_sha256,
            "workspace_manifest": str(result.manifest_path),
        }
    )


@data_app.command("main-actual-freeze")
def data_main_actual_freeze(
    workspace: Annotated[
        Path,
        typer.Option("--workspace", exists=True, file_okay=False),
    ] = PATHS.processed / "work/main-actual-20260816T140616Z",
) -> None:
    """Freeze an exact-replay Main workspace and select it for Main evidence builds."""

    result = freeze_main_actual_snapshot(load_main_actual_workspace(workspace))
    _echo(
        {
            "status": "ready",
            "snapshot": str(result.path),
            "pointer": str(result.pointer_path),
            "manifest": str(result.manifest_path),
            "manifest_sha256": result.manifest_sha256,
            "semantic_hash": result.semantic_hash,
            "replay_target_game_count": result.replay_target_game_count,
        }
    )


@data_app.command("replay-fantasy")
def data_replay_fantasy(
    as_of: Annotated[str, typer.Option("--as-of", help="只纳入该时点前已完成的比赛。")],
    year: Annotated[
        int | None,
        typer.Option("--year", min=2013, help="目标 UTC 日历年；默认使用 as-of 所在年份。"),
    ] = None,
    match_id: Annotated[
        list[int] | None,
        typer.Option("--match-id", min=1, help="可重复指定，用于缓存 fixture 或定向复核。"),
    ] = None,
    workers: Annotated[int, typer.Option("--workers", min=1, max=8, help="并发 replay 下载/解析数。")] = 4,
    max_matches: Annotated[
        int | None,
        typer.Option("--max-matches", min=1, help="本次最多处理多少个尚未完成的 replay。"),
    ] = None,
    checkpoint_every: Annotated[
        int,
        typer.Option("--checkpoint-every", min=1, help="每多少场完成后原子落盘；默认逐场。"),
    ] = 1,
    progress_every: Annotated[
        int,
        typer.Option("--progress-every", min=1, help="每多少场输出一次进度；失败始终输出。"),
    ] = 10,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="重新下载并解析已完成的 match；默认安全断点续传。"),
    ] = False,
    parser_jar: Annotated[
        Path | None,
        typer.Option("--parser-jar", exists=True, dir_okay=False, help="覆盖默认 Clarity parser JAR。"),
    ] = None,
    processed_dir: Annotated[
        Path | None,
        typer.Option(
            "--processed-dir",
            exists=True,
            file_okay=False,
            help="将 replay 结果写入隔离 processed 工作区；默认使用 data/processed。",
        ),
    ] = None,
) -> None:
    cutoff = parse_as_of(as_of)

    def progress(payload: dict) -> None:
        if (
            payload.get("status") != "exact"
            or int(payload.get("processed", 0)) % progress_every == 0
            or payload.get("processed") == payload.get("scheduled")
        ):
            typer.echo(json.dumps(payload, ensure_ascii=False, default=str), err=True)

    selected_paths = (
        PATHS
        if processed_dir is None
        else ProjectPaths(root=PATHS.root, processed_override=processed_dir.resolve())
    )
    result = sync_replay_fantasy_history(
        as_of=cutoff,
        year=year,
        match_ids=match_id,
        workers=workers,
        max_matches=max_matches,
        checkpoint_every=checkpoint_every,
        refresh=refresh,
        parser=ReplayParser(jar_path=parser_jar),
        paths=selected_paths,
        progress=progress,
    )
    _echo(
        {
            "status": result.status,
            "target_matches": result.target_matches,
            "attempted_matches": result.attempted_matches,
            "reused_matches": result.reused_matches,
            "remaining_matches": result.remaining_matches,
            "exact_matches": result.exact_matches,
            "build_untrusted_matches": result.build_untrusted_matches,
            "failed_matches": result.failed_matches,
            "watcher_trusted_cohorts": result.watcher_trusted_cohorts,
            "data_sha256": result.data_sha256,
            "paths": {
                "native_stats": str(result.native_stats_path),
                "replay_status": str(result.replay_status_path),
                "proxy_diagnostics": str(result.proxy_diagnostics_path),
                "watcher_support": str(result.watcher_support_path),
                "fantasy_performance_samples": str(result.fantasy_samples_path),
            },
            "issues": [item.model_dump(mode="json") for item in result.issues],
        }
    )
    _exit_for_status(result.status)


@forecast_app.command("group")
def forecast_group(
    as_of: Annotated[str, typer.Option("--as-of")],
    profile: Annotated[str, typer.Option("--profile")] = "all",
    samples: Annotated[int, typer.Option("--samples", min=1000)] = 20000,
    sensitivity_samples: Annotated[
        int | None,
        typer.Option(
            "--sensitivity-samples",
            min=1000,
            help="每个非主情景的样本数；缺省时与 --samples 相同。",
        ),
    ] = None,
    seed: Annotated[int, typer.Option("--seed", min=0)] = 20260813,
) -> None:
    result = generate_group(
        as_of=parse_as_of(as_of),
        profile=profile,
        samples=samples,
        sensitivity_samples=sensitivity_samples,
        seed=seed,
    )
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "profiles": [item.profile.value for item in result.recommendations],
        }
    )
    _exit_for_status(result.run.status)


@forecast_app.command("bracket")
def forecast_bracket(
    as_of: Annotated[str, typer.Option("--as-of")],
    profile: Annotated[str, typer.Option("--profile")] = "all",
    teams: Annotated[
        str | None,
        typer.Option("--teams", help="八个种子 team ID，按顺序用逗号分隔；缺省时仅作阻断占位推演。"),
    ] = None,
    seed: Annotated[int, typer.Option("--seed", min=0)] = 20260820,
) -> None:
    team_ids = [int(value.strip()) for value in teams.split(",")] if teams else None
    if team_ids is not None and len(team_ids) != 8:
        raise typer.BadParameter("--teams 必须恰好包含八个 team ID")
    result = generate_bracket(as_of=parse_as_of(as_of), profile=profile, team_ids=team_ids, seed=seed)
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "profiles": [item.profile.value for item in result.recommendations],
        }
    )
    _exit_for_status(result.run.status)


@forecast_app.command("backtest")
def forecast_backtest(
    as_of: Annotated[str, typer.Option("--as-of")],
    league_id: Annotated[
        int | None,
        typer.Option("--league-id", help="默认使用当前队伍强度策略中锁定的 TI 2025 联赛。"),
    ] = None,
) -> None:
    result = run_ti2025_backtest(as_of=parse_as_of(as_of), league_id=league_id)
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            **result.report,
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("recommend")
def fantasy_recommend(
    as_of: Annotated[str, typer.Option("--as-of")],
    period: Annotated[str, typer.Option("--period", help="group 或 main")] = "group",
    profile: Annotated[str, typer.Option("--profile")] = "all",
    seed: Annotated[int, typer.Option("--seed", min=0)] = 20260813,
) -> None:
    if period not in {"group", "main"}:
        raise typer.BadParameter("--period 只能是 group 或 main")
    result = generate_fantasy(as_of=parse_as_of(as_of), period=period, profile=profile, seed=seed)
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "profiles": [item.profile.value for item in result.recommendations],
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("group-evidence")
def fantasy_group_evidence(
    as_of: Annotated[str, typer.Option("--as-of", help="P3 证据可用截止时间，必须带时区。")],
    seed: Annotated[int, typer.Option("--seed", min=0)] = 20260813,
    bootstrap: Annotated[
        bool,
        typer.Option(
            "--bootstrap/--no-bootstrap",
            help="执行冻结的完整 Series 分组重采样；正式 P3/P4 证据必须开启。",
        ),
    ] = True,
    team_rank_bootstrap: Annotated[
        bool,
        typer.Option(
            "--team-rank-bootstrap/--no-team-rank-bootstrap",
            help="额外计算每个位置/Stat 的队伍 P(rank=1)、P(top3) 并生成 Top 3 Markdown。",
        ),
    ] = False,
) -> None:
    result = generate_group_fantasy_evidence(
        as_of=parse_as_of(as_of),
        seed=seed,
        include_bootstrap=bootstrap,
        include_team_rank_bootstrap=team_rank_bootstrap,
    )
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "evidence_package_sha256": result.evidence["evidence_package_sha256"],
            "scenario_sha256": result.evidence["scenario_set"]["scenario_sha256"],
            "team_rank_report_path": (
                None if result.team_rank_report_path is None else str(result.team_rank_report_path)
            ),
            "runtime_seconds": result.runtime_seconds,
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("title-evidence")
def fantasy_title_evidence(
    as_of: Annotated[str, typer.Option("--as-of", help="Title 证据可用截止时间，必须带时区。")],
    hero_source: Annotated[
        Path,
        typer.Option(
            "--hero-source",
            exists=True,
            dir_okay=False,
            help="由当前 Dota 客户端解包的 scripts/npc/npc_heroes.txt。",
        ),
    ],
    client_build: Annotated[
        str | None,
        typer.Option("--client-build", help="与 hero-source 对应的 ClientVersion:SourceRevision。"),
    ] = None,
    seed: Annotated[int, typer.Option("--seed", min=0)] = 20260808,
) -> None:
    result = generate_group_title_evidence(
        as_of=parse_as_of(as_of),
        hero_source_path=hero_source,
        client_build=client_build,
        seed=seed,
    )
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "report_path": str(result.report_path),
            "evidence_sha256": result.evidence["evidence_sha256"],
            "default_title": result.evidence["analysis"]["recommendation"],
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("main-publication-evidence")
def fantasy_main_publication_evidence(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="必须等于当前 actual Main 求解包的显式 UTC 截止时间。"),
    ],
    hero_source: Annotated[
        Path,
        typer.Option(
            "--hero-source",
            exists=True,
            dir_okay=False,
            help="已归档的 Valve scripts/npc/npc_heroes.txt。",
        ),
    ],
) -> None:
    result = generate_main_publication_evidence(
        as_of=parse_as_of(as_of),
        hero_source_path=hero_source,
    )
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "stat_report_path": str(result.stat_report_path),
            "title_report_path": str(result.title_report_path),
            "evidence_sha256": result.evidence["evidence_sha256"],
            "default_title": result.evidence["title_analysis"]["recommendation"],
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("group-playbook-evidence")
def fantasy_group_playbook_evidence(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="P4 冻结人工手册验证截止时间，必须带时区。"),
    ],
    playbook_version: Annotated[
        Literal["v1", "v2"],
        typer.Option("--playbook-version", help="选择冻结的人工手册与验证策略版本。"),
    ] = "v1",
) -> None:
    result = generate_group_playbook_evidence(
        as_of=parse_as_of(as_of),
        playbook_version=playbook_version,
    )
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "evidence_sha256": result.evidence["evidence_sha256"],
            "gate": result.evidence["gate"],
            "runtime_seconds": result.runtime_seconds,
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("group-solver-evidence")
def fantasy_group_solver_evidence(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="P5 限枝参考求解器证据截止时间，必须带时区。"),
    ],
) -> None:
    result = generate_group_solver_evidence(as_of=parse_as_of(as_of))
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "evidence_sha256": result.evidence["evidence_sha256"],
            "gate": result.evidence["gate"],
            "runtime_seconds": result.runtime_seconds,
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("group-cross-audit")
def fantasy_group_cross_audit(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="P6 只读手册交叉审计截止时间，必须带时区。"),
    ],
    cross_audit_version: Annotated[
        Literal["v1", "v2"],
        typer.Option("--cross-audit-version", help="选择冻结的只读交叉审计版本。"),
    ] = "v1",
) -> None:
    result = generate_group_cross_audit_evidence(
        as_of=parse_as_of(as_of),
        cross_audit_version=cross_audit_version,
    )
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "evidence_sha256": result.evidence["evidence_sha256"],
            "gate": result.evidence["gate"],
            "runtime_seconds": result.runtime_seconds,
        }
    )
    _exit_for_status(result.run.status)


@fantasy_app.command("group-advisor-evidence")
def fantasy_group_advisor_evidence(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="P7 本地 Group Roll 顾问证据截止时间，必须带时区。"),
    ],
) -> None:
    result = generate_group_advisor_evidence(as_of=parse_as_of(as_of))
    _echo(
        {
            "run_id": result.run.run_id,
            "status": result.run.status,
            "run_path": str(result.run_path),
            "evidence_path": str(result.evidence_path),
            "evidence_sha256": result.evidence["evidence_sha256"],
            "functional_gate": result.evidence["functional_gate"],
            "runtime_seconds": result.runtime_seconds,
        }
    )
    _exit_for_status(result.run.status)


def _write_current_solver_release(*, as_of: str, output: Path | None) -> None:
    cutoff = parse_as_of(as_of)
    context = prepare_current_advisor_context(as_of=cutoff)
    result = write_solver_release_bundle(
        context,
        output_path=output,
    )
    _echo(
        {
            "release_id": SOLVER_RELEASE_ID,
            "as_of": context.policy.as_of,
            "path": str(result.path),
            "pointer_path": str(result.pointer_path) if result.pointer_path else None,
            "bytes": result.bytes,
            "file_sha256": result.file_sha256,
            "release_sha256": result.release_sha256,
        }
    )


@fantasy_app.command("solver-release")
def fantasy_solver_release(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="冻结求解发布包的数据截止时间，必须带时区。"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="默认写入 deploy/runtime/releases 并更新 current.json。"),
    ] = None,
) -> None:
    _write_current_solver_release(as_of=as_of, output=output)


@fantasy_app.command("main-solver-release")
def fantasy_main_solver_release(
    as_of: Annotated[
        str,
        typer.Option("--as-of", help="Main 模型与数据的显式 UTC 截止时间，必须带时区。"),
    ],
    mode: Annotated[
        Literal["auto", "projected", "actual"],
        typer.Option(
            "--mode",
            help="auto 在无正式种子时发布 16 队预测模式，有正式八队后发布实际模式。",
        ),
    ] = "auto",
    hero_source: Annotated[
        Path | None,
        typer.Option(
            "--hero-source",
            exists=True,
            dir_okay=False,
            help="actual 模式嵌入动态 Title 推荐所需的 Valve npc_heroes.txt。",
        ),
    ] = None,
) -> None:
    """Build a usable projected Main runtime now, then replace it with actual eight Teams."""

    cutoff = parse_as_of(as_of)
    manifest = load_tournament_manifest(PATHS.tournament)
    if cutoff > manifest.main_lock_at:
        raise typer.BadParameter("Main 发布截止时间不得晚于游戏内 Main roster lock")
    policy = load_main_solver_policy()
    group_context = load_solver_release_context()
    selected_mode = (
        ("actual" if len(manifest.main_event_seeds) == 8 else "projected") if mode == "auto" else mode
    )
    release_pool = group_context.pool_result
    evidence_warnings: tuple[str, ...] = ()
    eligibility_evidence: dict[str, object]
    title_evidence: dict[str, object] | None = None
    if selected_mode == "projected":
        model, report = load_strength_model_as_of(as_of=cutoff)
        blocking = [issue.message for issue in report.issues if issue.severity == "blocking"]
        if blocking:
            raise typer.BadParameter("Main Team-strength model is blocked: " + "; ".join(blocking))
        data_snapshot_sha256 = sha256_json(
            {
                "period": "main",
                "eligibility_mode": "projected",
                "as_of": cutoff.isoformat().replace("+00:00", "Z"),
                "group_pool_set_sha256": group_context.pool_result.semantic_hash,
                "group_scenario_sha256": group_context.scenarios.semantic_hash,
                "group_scenario_as_of": group_context.scenarios.as_of,
                "model_sha256": sha256_json(model.as_dict()),
                "policy_sha256": sha256_json(policy.model_dump(mode="json")),
            }
        )
        scenarios = build_projected_main_scenario_set_from_group(
            release_pool,
            group_scenarios=group_context.scenarios,
            model=model,
            scenario_count=policy.scenario_count,
            policy_id=policy.policy_id,
            data_snapshot_sha256=data_snapshot_sha256,
            as_of=cutoff,
            seed=policy.seed,
        )
        evidence_warnings = tuple(
            sorted(issue.message for issue in report.issues if issue.severity == "warning")
        )
        eligibility_evidence = {
            "source_group_scenario_sha256": group_context.scenarios.semantic_hash,
            "source_group_as_of": group_context.scenarios.as_of,
        }
    else:
        if hero_source is None:
            raise typer.BadParameter("actual 模式要求 --hero-source，以便把 Main Title 推荐嵌入 Web 发布包")
        if len(manifest.main_event_seeds) != policy.entrant_team_count:
            raise typer.BadParameter(
                "actual 模式要求 config/ti2026.yaml 提供按正式种子排序的 8 个 main_event_seeds"
            )
        if sha256_json(load_rules(PATHS.rules)) != sha256_json(group_context.canonical_rules):
            raise typer.BadParameter("Main 当前规则与已发布的共享客户端规则不一致")
        evidence = build_main_evidence_snapshot(as_of=cutoff)
        try:
            validate_actual_main_evidence_refresh(
                evidence,
                entrant_team_ids=tuple(manifest.main_event_seeds),
                newer_than=group_context.policy.as_of,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        release_pool = evidence.pool_result
        if release_pool.semantic_hash == group_context.pool_result.semantic_hash:
            raise typer.BadParameter(
                "实际八队发布前必须先同步赛后比赛并重跑 Fantasy replay；当前 Main 样本池仍与 Group 冻结包相同"
            )
        scenarios = build_main_scenario_set_from_model(
            release_pool,
            team_ids=tuple(manifest.main_event_seeds),
            model=evidence.model,
            scenario_count=policy.scenario_count,
            policy_id=policy.policy_id,
            data_snapshot_sha256=evidence.data_snapshot_sha256,
            as_of=cutoff,
            seed=policy.seed,
        )
        evidence_warnings = evidence.warnings
        eligibility_evidence = {
            "current_event_fantasy_game_count": evidence.current_event_fantasy_game_count,
            "current_event_fantasy_team_ids": list(evidence.current_event_fantasy_team_ids),
            "latest_current_event_fantasy_start_at": (evidence.latest_current_event_fantasy_start_at),
            "refreshed_after_group_as_of": group_context.policy.as_of,
        }
        title_evidence = build_main_title_runtime_evidence(
            as_of=cutoff,
            pool_result=release_pool,
            team_ids=scenarios.team_ids,
            team_names={team_id: group_context.team_names[team_id] for team_id in scenarios.team_ids},
            canonical_rules=group_context.canonical_rules,
            scenario_sha256=scenarios.semantic_hash,
            hero_source_path=hero_source,
        )
    result = write_main_solver_release_bundle(
        group_context,
        scenarios,
        lock_at=manifest.main_lock_at.isoformat().replace("+00:00", "Z"),
        pool_result=release_pool,
        additional_warnings=evidence_warnings,
        eligibility_evidence=eligibility_evidence,
        title_evidence=title_evidence,
    )
    _echo(
        {
            "release_id": MAIN_SOLVER_RELEASE_ID,
            "period": "main",
            "status": "provisional" if scenarios.eligibility_mode == "projected" else "ready",
            "eligibility_mode": scenarios.eligibility_mode,
            "as_of": scenarios.as_of,
            "team_ids": list(scenarios.team_ids),
            "scenario_count": len(scenarios.scenario_ids),
            "data_snapshot_sha256": scenarios.data_snapshot_sha256,
            "model_sha256": scenarios.model_sha256,
            "path": str(result.path),
            "pointer_path": str(result.pointer_path),
            "bytes": result.bytes,
            "file_sha256": result.file_sha256,
            "release_sha256": result.release_sha256,
            "title_evidence_sha256": (
                title_evidence["evidence_sha256"] if title_evidence is not None else None
            ),
        }
    )


@fantasy_app.command("manual-release", hidden=True)
def fantasy_manual_release_compatibility(
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Compatibility alias for the former manual-only release name."""

    _write_current_solver_release(as_of=as_of, output=output)


@fantasy_app.command("main-parallel-forecast-release")
def fantasy_main_parallel_forecast_release(
    source_v1: Annotated[
        Path,
        typer.Option(
            "--source-v1",
            exists=True,
            file_okay=False,
            help="已冻结并通过校验的完整 Main V1 条件真值目录。",
        ),
    ],
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            help="三模型正式发布契约。",
        ),
    ] = PATHS.config / "models" / "fantasy-main-parallel-forecast-v1.json",
    output: Annotated[
        Path,
        typer.Option("--output", file_okay=False, help="内容寻址目录与 ZIP 的输出父目录。"),
    ] = PATHS.artifacts / "releases" / "main-parallel-forecast",
) -> None:
    """Build the immutable V1/B1/hybrid terminal Forecast evidence archive."""

    payload = build_main_multi_forecast_release(
        load_main_multi_forecast_build_config(config),
        source_v1_root=source_v1,
        output_root=output,
    )
    _echo(payload)


@app.command("audit")
def audit(run_id: str) -> None:
    report = audit_run(run_id)
    _echo(report)
    _exit_for_status(report["status"])


@ocr_app.command("inspect")
def ocr_inspect(image: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    _echo(inspect_screenshot(image))


def _current_player_runtime_summary() -> dict[str, object]:
    """Validate and describe the pointer-selected releases used by the player service."""

    group_context = load_solver_release_context()
    main_context = load_main_solver_release_context(group_context)
    readiness = main_solver_readiness()
    return {
        "group_as_of": group_context.policy.as_of,
        "main_as_of": main_context.as_of,
        "main_status": readiness.status,
        "main_mode": readiness.eligibility_mode,
        "main_candidate_team_count": readiness.candidate_team_count,
        "main_entrant_team_count": readiness.entrant_team_count,
    }


def _run_streamlit(entrypoint: Path, *, port: int) -> None:
    summary = _current_player_runtime_summary()
    _echo(
        {
            "status": "starting",
            "url": f"http://127.0.0.1:{port}",
            "runtime_selection": "current-pointer",
            **summary,
        }
    )
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(entrypoint),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    raise typer.Exit(code=subprocess.run(command, check=False).returncode)


def _player_entrypoint(*, manual: bool) -> Path:
    if manual or sys.platform != "win32":
        return PATHS.root / "streamlit_app.py"
    return PATHS.root / "local_ocr_app.py"


@app.command("web")
def player_web(
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8501,
    manual: Annotated[
        bool,
        typer.Option(
            "--manual",
            help="只启用手动录入；Windows 默认同时启用本地只读 OCR。",
        ),
    ] = False,
) -> None:
    """启动 Fantasy 玩家服务并自动加载当前可用的 Group/Main 发布包。"""

    _run_streamlit(_player_entrypoint(manual=manual), port=port)


@consumer_app.command("local-ocr")
def local_ocr_app(
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8501,
) -> None:
    if sys.platform != "win32":
        raise typer.BadParameter("本地画面识别仅支持 Windows；其他系统可运行 ti app manual")
    _run_streamlit(PATHS.root / "local_ocr_app.py", port=port)


@consumer_app.command("manual")
def manual_app(
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8501,
) -> None:
    _run_streamlit(PATHS.root / "streamlit_app.py", port=port)


@dev_app.command("web")
def developer_web(
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8501,
) -> None:
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(PATHS.root / "src/ti_predictor/web_app.py"),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    raise typer.Exit(code=subprocess.run(command, check=False).returncode)


if __name__ == "__main__":  # pragma: no cover
    app()
