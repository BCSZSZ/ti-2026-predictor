from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from ti_predictor import __version__
from ti_predictor.audit import audit_run
from ti_predictor.backtesting import run_ti2025_backtest
from ti_predictor.forecasting import generate_bracket, generate_fantasy, generate_group
from ti_predictor.ingest.opendota import sync_opendota
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
app.add_typer(rules_app, name="rules")
app.add_typer(data_app, name="data")
app.add_typer(forecast_app, name="forecast")
app.add_typer(fantasy_app, name="fantasy")
app.add_typer(ocr_app, name="ocr")


def _echo(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_for_status(status: str) -> None:
    if status == "blocked":
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
    refresh_details: Annotated[
        bool,
        typer.Option(
            "--refresh-details",
            help="重新抓取已有逐场详情；默认按 match_id 断点续传。",
        ),
    ] = False,
) -> None:
    cutoff = parse_as_of(as_of)
    result = sync_opendota(
        as_of=cutoff,
        league_ids=league,
        pro_year=(year or cutoff.year) if pro_catalog else None,
        include_details=details,
        include_team_history=team_history,
        team_history_detail_limit=team_detail_limit,
        max_matches=max_matches,
        refresh_details=refresh_details,
    )
    _echo(
        {
            "status": result.status,
            "pro_year": result.pro_year,
            "leagues": result.requested_leagues,
            "match_catalog_rows": result.match_count,
            "professional_matches": result.pro_match_count,
            "fantasy_performance_samples": result.fantasy_sample_count,
            "detailed_matches": result.detailed_match_count,
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


@forecast_app.command("group")
def forecast_group(
    as_of: Annotated[str, typer.Option("--as-of")],
    profile: Annotated[str, typer.Option("--profile")] = "all",
    samples: Annotated[int, typer.Option("--samples", min=1000)] = 20000,
    seed: Annotated[int, typer.Option("--seed", min=0)] = 20260813,
) -> None:
    result = generate_group(as_of=parse_as_of(as_of), profile=profile, samples=samples, seed=seed)
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
    league_id: Annotated[int, typer.Option("--league-id")] = 18324,
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


@app.command("audit")
def audit(run_id: str) -> None:
    report = audit_run(run_id)
    _echo(report)
    _exit_for_status(report["status"])


@ocr_app.command("inspect")
def ocr_inspect(image: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    _echo(inspect_screenshot(image))


@app.command("web")
def web(
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
