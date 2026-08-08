"""Validation and player-facing rendering for the TI 2026 team prize ledger."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ti_predictor.schemas import as_utc


@dataclass(frozen=True)
class TeamPrizeTotal:
    team_id: int
    display_name: str
    award_count: int
    total_usd: Decimal


def _money(value: Any, *, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a decimal USD amount") from error
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount


def _iso_date(value: Any, *, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error


def _source_index(payload: dict[str, Any], *, as_of: datetime) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("sources", []):
        source_id = str(row.get("source_id", "")).strip()
        if not source_id or source_id in result:
            raise ValueError(f"source_id must be non-empty and unique: {source_id!r}")
        url = str(row.get("url", ""))
        if not url.startswith("https://"):
            raise ValueError(f"source {source_id} must use an https URL")
        observed_at = as_utc(row.get("observed_at"))
        if observed_at is None or observed_at > as_of:
            raise ValueError(f"source {source_id} was not available by ledger as_of")
        result[source_id] = row
    if not result:
        raise ValueError("prize ledger requires at least one source")
    return result


def validate_prize_ledger(
    payload: dict[str, Any],
    *,
    expected_team_ids: Iterable[int] | None = None,
) -> list[TeamPrizeTotal]:
    """Validate the governed ledger and return totals in publication order."""

    if payload.get("artifact_type") != "ti2026_team_prize_ytd_ledger":
        raise ValueError("unexpected prize ledger artifact_type")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported prize ledger schema_version")
    as_of = as_utc(payload.get("as_of"))
    if as_of is None:
        raise ValueError("prize ledger requires an explicit UTC as_of")
    year = int(payload.get("calendar_year", 0))
    if year != as_of.year:
        raise ValueError("calendar_year must match as_of year")
    if payload.get("currency") != "USD":
        raise ValueError("prize ledger currency must be USD")
    if payload.get("amount_semantics") != "published_gross_team_award":
        raise ValueError("prize ledger must use published gross team awards")

    sources = _source_index(payload, as_of=as_of)
    identities: dict[int, dict[str, Any]] = {}
    for row in payload.get("teams", []):
        team_id = int(row.get("team_id", 0))
        display_name = str(row.get("display_name", "")).strip()
        if team_id <= 0 or not display_name or team_id in identities:
            raise ValueError(f"team identity must have a unique positive ID and name: {team_id}")
        identities[team_id] = row
    if expected_team_ids is not None and set(identities) != {int(value) for value in expected_team_ids}:
        raise ValueError("prize ledger team IDs differ from the declared TI field")

    seen_award_ids: set[str] = set()
    seen_team_events: set[tuple[int, str]] = set()
    amounts: dict[int, list[Decimal]] = defaultdict(list)
    for row in payload.get("awards", []):
        award_id = str(row.get("award_id", "")).strip()
        if not award_id or award_id in seen_award_ids:
            raise ValueError(f"award_id must be non-empty and unique: {award_id!r}")
        seen_award_ids.add(award_id)
        team_id = int(row.get("team_id", 0))
        if team_id not in identities:
            raise ValueError(f"award {award_id} references an unknown team_id")
        event_id = str(row.get("event_id", "")).strip()
        event_name = str(row.get("event_name", "")).strip()
        placement = str(row.get("placement", "")).strip()
        if not event_id or not event_name or not placement:
            raise ValueError(f"award {award_id} lacks event or placement identity")
        team_event = (team_id, event_id)
        if team_event in seen_team_events:
            raise ValueError(f"team {team_id} has duplicate award rows for {event_id}")
        seen_team_events.add(team_event)
        event_end = _iso_date(row.get("event_end_date"), field=f"award {award_id} event_end_date")
        if event_end.year != year or event_end > as_of.date():
            raise ValueError(f"award {award_id} is outside the governed year/as_of")
        if row.get("status") != "confirmed" or row.get("award_scope") != "team":
            raise ValueError(f"award {award_id} is not a confirmed team award")
        amount = _money(row.get("amount_usd"), field=f"award {award_id} amount_usd")
        if amount <= 0:
            raise ValueError(f"award {award_id} amount_usd must be positive")
        components = row.get("components_usd")
        if components is not None:
            if not isinstance(components, dict) or not components:
                raise ValueError(f"award {award_id} components_usd must be a non-empty object")
            component_total = sum(
                (
                    _money(value, field=f"award {award_id} component {key}")
                    for key, value in components.items()
                ),
                start=Decimal("0"),
            )
            if component_total != amount:
                raise ValueError(f"award {award_id} components do not sum to amount_usd")
        source_ids = row.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ValueError(f"award {award_id} requires source_ids")
        if any(str(source_id) not in sources for source_id in source_ids):
            raise ValueError(f"award {award_id} references an unknown source")
        amounts[team_id].append(amount)
    if not seen_award_ids:
        raise ValueError("prize ledger contains no confirmed awards")

    declared = payload.get("declared_team_totals_usd")
    if not isinstance(declared, dict):
        raise ValueError("prize ledger requires declared_team_totals_usd")
    totals: list[TeamPrizeTotal] = []
    for team_id, identity in identities.items():
        total = sum(amounts.get(team_id, []), start=Decimal("0"))
        declared_total = _money(declared.get(str(team_id)), field=f"declared total for team {team_id}")
        if total != declared_total:
            raise ValueError(f"declared total for team {team_id} does not match award rows")
        totals.append(
            TeamPrizeTotal(
                team_id=team_id,
                display_name=str(identity["display_name"]),
                award_count=len(amounts.get(team_id, [])),
                total_usd=total,
            )
        )
    declared_all = _money(payload.get("declared_total_usd"), field="declared_total_usd")
    if sum((row.total_usd for row in totals), start=Decimal("0")) != declared_all:
        raise ValueError("declared_total_usd does not match team totals")
    return sorted(totals, key=lambda row: (-row.total_usd, row.display_name.casefold()))


def load_prize_ledger(
    path: Path,
    *,
    expected_team_ids: Iterable[int] | None = None,
) -> tuple[dict[str, Any], list[TeamPrizeTotal]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prize ledger root must be an object")
    return payload, validate_prize_ledger(payload, expected_team_ids=expected_team_ids)


def format_usd(amount: Decimal) -> str:
    if amount == amount.to_integral_value():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _display_placement(value: str) -> str:
    exact = {
        "1st": "冠军",
        "2nd": "亚军",
        "3rd": "季军",
        "4th": "第 4 名",
        "5th": "第 5 名",
        "6th": "第 6 名",
        "7th": "第 7 名",
        "8th": "第 8 名",
        "9th": "第 9 名",
        "10th": "第 10 名",
        "11th": "第 11 名",
    }
    if value in exact:
        return exact[value]
    if "-" not in value:
        return value
    start, end = value.split("-", maxsplit=1)
    ordinal = {"st": "", "nd": "", "rd": "", "th": ""}
    for suffix in ordinal:
        start = start.removesuffix(suffix)
        end = end.removesuffix(suffix)
    if start.isdigit() and end.isdigit():
        return f"第 {start}–{end} 名"
    return value


def _display_tier(value: str) -> str:
    if value == "Qualifier (Tier 2 destination)":
        return "资格赛（通往 Tier 2）"
    return value


def render_team_prize_markdown(payload: dict[str, Any]) -> str:
    """Render the source-free player edition after validating the ledger."""

    totals = validate_prize_ledger(payload)
    grand_total = sum((row.total_usd for row in totals), start=Decimal("0"))
    identities = {int(row["team_id"]): row for row in payload["teams"]}
    awards_by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for award in payload["awards"]:
        awards_by_team[int(award["team_id"])].append(award)
    lines = [
        "# TI 2026 参赛战队：2026 年已获奖金累计",
        "",
        f"统计截止：`{payload['as_of']}`。金额为美元；只统计当年已经完赛并能公开确认的战队奖金。",
        "",
        f"当前 16 支参赛队合计 **{format_usd(grand_total)}**。这是逐队结果的合计，不是赛事总奖池。",
        "",
        "## 先看排名",
        "",
        "| 奖金排名 | 战队 | 2026 累计 | 有奖金的赛事 | 最大一笔 |",
        "| ---: | --- | ---: | ---: | --- |",
    ]
    for rank, total in enumerate(totals, start=1):
        awards = awards_by_team[total.team_id]
        largest = max(awards, key=lambda row: _money(row["amount_usd"], field="amount_usd"))
        largest_amount = format_usd(_money(largest["amount_usd"], field="amount_usd"))
        lines.append(
            f"| {rank} | **{total.display_name}** | **{format_usd(total.total_usd)}** | "
            f"{total.award_count} | {largest['event_name']}（{largest_amount}） |"
        )
    lines.extend(
        [
            "",
            "这里的累计是赛事公开分配给战队名次的毛额。赛事如果同时列出选手奖金和俱乐部奖励，",
            "两部分都会计入；它不是扣税后的到账金额，也不表示奖金已经完成付款。",
            "",
            "## 逐队明细",
            "",
        ]
    )
    rank_by_team = {row.team_id: rank for rank, row in enumerate(totals, start=1)}
    total_by_team = {row.team_id: row for row in totals}
    for team_id in sorted(identities, key=lambda value: rank_by_team[value]):
        total = total_by_team[team_id]
        lines.extend(
            [
                f"### {rank_by_team[team_id]}. {total.display_name} — {format_usd(total.total_usd)}",
                "",
                "| 完赛日期 | 赛事 | 档位 | 最终名次 | 获得奖金 |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        awards = sorted(
            awards_by_team[team_id],
            key=lambda row: (row["event_end_date"], row["event_name"]),
            reverse=True,
        )
        for award in awards:
            lines.append(
                f"| {award['event_end_date']} | {award['event_name']} | "
                f"{_display_tier(str(award['tier']))} | "
                f"{_display_placement(str(award['placement']))} | "
                f"{format_usd(_money(award['amount_usd'], field='amount_usd'))} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 口径说明",
            "",
            "- 统计主体是当前战队/组织身份；同一战队的正式更名会衔接，但不会把选手或阵容在"
            "旧俱乐部的奖金转过来。",
            "- 个人 MVP 等个人奖不计入；没有确认金额的赛事保持未知，也不会用 0 或估算值补齐。",
            "- 非美元赛事沿用赛事资料在完赛时给出的美元折算，因此少量金额会带小数。",
            "- 奖金只帮助理解战队今年的成绩和赛事规模，没有进入现有实力模型，也不会单独决定排名。",
        ]
    )
    return "\n".join(lines) + "\n"
