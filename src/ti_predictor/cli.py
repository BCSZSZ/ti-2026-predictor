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
from ti_predictor.fantasy.advisor_reporting import generate_group_advisor_evidence
from ti_predictor.fantasy.cross_audit_reporting import generate_group_cross_audit_evidence
from ti_predictor.fantasy.current_advisor import prepare_current_advisor_context
from ti_predictor.fantasy.playbook_reporting import generate_group_playbook_evidence
from ti_predictor.fantasy.solver_release import (
    SOLVER_RELEASE_ID,
    default_solver_release_path,
    write_solver_release_bundle,
)
from ti_predictor.fantasy.solver_reporting import generate_group_solver_evidence
from ti_predictor.fantasy.title_reporting import generate_group_title_evidence
from ti_predictor.forecasting import (
    generate_bracket,
    generate_fantasy,
    generate_group,
    generate_group_fantasy_evidence,
)
from ti_predictor.ingest.opendota import (
    DEFAULT_OPENDOTA_RUN_REQUEST_LIMIT,
    OpenDotaSafetyStop,
    sync_fantasy_player_history,
    sync_opendota,
)
from ti_predictor.ingest.replay import ReplayParser, sync_replay_fantasy_history
from ti_predictor.ocr import inspect_screenshot
from ti_predictor.paths import PATHS
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
) -> None:
    cutoff = parse_as_of(as_of)

    def progress(payload: dict) -> None:
        if (
            payload.get("status") != "exact"
            or int(payload.get("processed", 0)) % progress_every == 0
            or payload.get("processed") == payload.get("scheduled")
        ):
            typer.echo(json.dumps(payload, ensure_ascii=False, default=str), err=True)

    result = sync_replay_fantasy_history(
        as_of=cutoff,
        year=year,
        match_ids=match_id,
        workers=workers,
        max_matches=max_matches,
        checkpoint_every=checkpoint_every,
        refresh=refresh,
        parser=ReplayParser(jar_path=parser_jar),
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


@fantasy_app.command("manual-release", hidden=True)
def fantasy_manual_release_compatibility(
    as_of: Annotated[str, typer.Option("--as-of")],
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Compatibility alias for the former manual-only release name."""

    _write_current_solver_release(as_of=as_of, output=output)


@app.command("audit")
def audit(run_id: str) -> None:
    report = audit_run(run_id)
    _echo(report)
    _exit_for_status(report["status"])


@ocr_app.command("inspect")
def ocr_inspect(image: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    _echo(inspect_screenshot(image))


def _run_streamlit(entrypoint: Path, *, port: int) -> None:
    default_solver_release_path()
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
