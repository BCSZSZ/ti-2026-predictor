from __future__ import annotations

import traceback
from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest

from ti_predictor.ingest.opendota import (
    OpenDotaClient,
    OpenDotaDailyBudgetExhausted,
    OpenDotaMonthlyBudgetExhausted,
    OpenDotaRequestError,
    OpenDotaRequestLoopDetected,
    OpenDotaRunBudgetExhausted,
    OpenDotaUsageLedgerError,
    _sample_match_ids_with_current_provenance,
    extract_fantasy_stats,
    sync_fantasy_player_history,
    sync_opendota,
)


def _detail() -> dict:
    player = {
        "account_id": 152962063,
        "player_slot": 0,
        "kills": 10,
        "assists": 5,
        "deaths": 2,
        "last_hits": 300,
        "denies": 12,
        "gold_per_min": 650,
        "towers_killed": 2,
        "obs_placed": 1,
        "camps_stacked": 3,
        "rune_pickups": 6,
        "roshans_killed": 1,
        "teamfight_participation": 0.01,
        "firstblood_claimed": 0,
        "stuns": 3.5,
        "courier_kills": 0,
        "item_uses": {"smoke_of_deceit": 1},
        "ability_uses": {},
        "killed": {},
    }
    return {
        "match_id": 123,
        "leagueid": 18324,
        "series_id": 44,
        "series_type": 1,
        "start_time": 1756684800,
        "radiant_team_id": 2163,
        "dire_team_id": 7119388,
        "radiant_win": True,
        "radiant_score": 20,
        "dire_score": 8,
        "duration": 2100,
        "players": [player],
    }


def test_stat_extraction_keeps_unavailable_values_null() -> None:
    stats = extract_fantasy_stats(_detail()["players"][0], team_total_kills=20)
    assert stats["creep_score"] == 312
    assert stats["teamfight_participation"] == pytest.approx(0.75)
    assert stats["madstone_collected"] is None
    assert stats["smokes_used"] is None
    assert stats["watchers_taken"] is None
    assert stats["lotuses_gained"] is None
    assert stats["tormentor_kills"] is None


def test_teamfight_participation_uses_owner_formula_and_handles_zero_team_kills() -> None:
    player = {"kills": 3, "assists": 9, "teamfight_participation": 0.01}
    assert extract_fantasy_stats(player, team_total_kills=20)["teamfight_participation"] == pytest.approx(0.6)
    assert extract_fantasy_stats(player, team_total_kills=0)["teamfight_participation"] is None
    assert extract_fantasy_stats(player)["teamfight_participation"] is None


def test_cached_samples_are_stale_when_stat_provenance_changes() -> None:
    samples = pd.DataFrame(
        {
            "match_id": [1, 1, 2],
            "kills_provenance": ["exact", "exact", "exact"],
            "teamfight_participation_provenance": ["exact", "derived", "derived"],
        }
    )

    current = _sample_match_ids_with_current_provenance(
        samples,
        {"kills": "exact", "teamfight_participation": "derived"},
    )

    assert current == {2}


def test_native_unavailable_null_is_current_but_proxy_is_stale() -> None:
    samples = pd.DataFrame(
        {
            "match_id": [1, 2, 3],
            "smokes_used": [None, 1.0, None],
            "smokes_used_provenance": ["unavailable", "proxy", "proxy"],
        }
    )

    current = _sample_match_ids_with_current_provenance(samples, {"smokes_used": "exact"})

    assert current == {1}


def test_client_uses_mock_transport_without_live_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/leagues/18324/matches")
        return httpx.Response(200, json=[{"match_id": 123}])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(client=http_client, min_interval_seconds=0)
    payload, _ = client.league_matches(18324)
    assert payload == [{"match_id": 123}]
    http_client.close()


def test_client_waits_for_minute_window_after_rate_limit() -> None:
    requests = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(
                429,
                headers={
                    "X-Rate-Limit-Remaining-Minute": "0",
                    "X-Rate-Limit-Remaining-Day": "2000",
                },
            )
        return httpx.Response(200, json=[{"match_id": 123}])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(
        client=http_client,
        min_interval_seconds=0,
        rate_limit_pause_seconds=61,
        sleeper=sleeps.append,
    )

    payload, _ = client.pro_matches()

    assert payload == [{"match_id": 123}]
    assert sleeps == [61]
    assert requests == 2
    http_client.close()


def test_client_stops_before_daily_request_reserve() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            headers={"X-Rate-Limit-Remaining-Day": "50"},
            json=[{"match_id": 123}],
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(
        client=http_client,
        min_interval_seconds=0,
        daily_request_reserve=50,
    )

    payload, _ = client.player_matches(152962063, date_days=30)
    assert payload == [{"match_id": 123}]
    with pytest.raises(OpenDotaDailyBudgetExhausted):
        client.player_matches(152962063, date_days=30)
    assert requests == 1
    http_client.close()


def test_client_stops_at_per_run_request_limit() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json={"resource": request.url.path})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(
        client=http_client,
        min_interval_seconds=0,
        run_request_limit=1,
    )

    client.get_json("first")
    with pytest.raises(OpenDotaRunBudgetExhausted):
        client.get_json("second")

    assert requests == 1
    assert client.request_attempts == 1
    http_client.close()


def test_monthly_budget_ceiling_cannot_be_raised_by_configuration() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    with pytest.raises(ValueError, match="cannot exceed"):
        OpenDotaClient(
            api_key="dummy-key",
            client=http_client,
            monthly_request_limit=50_001,
        )
    http_client.close()


def test_client_rejects_key_in_per_request_query() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    client = OpenDotaClient(client=http_client)
    with pytest.raises(ValueError, match="on the client"):
        client.get_json("proMatches", query={"api_key": "must-not-be-passed-here"})
    assert client.request_attempts == 0
    http_client.close()


def test_client_stops_repeated_successful_request_before_second_call() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json=[])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(client=http_client, min_interval_seconds=0)

    client.player_matches(152962063, date_days=30)
    with pytest.raises(OpenDotaRequestLoopDetected):
        client.player_matches(152962063, date_days=30)

    assert requests == 1
    assert client.request_attempts == 1
    http_client.close()


def test_client_retries_transient_errors_with_increasing_backoff() -> None:
    requests = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests < 4:
            return httpx.Response(503, json={"error": "temporary"})
        return httpx.Response(200, json=[])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(
        client=http_client,
        min_interval_seconds=0,
        sleeper=sleeps.append,
    )

    payload, _ = client.pro_matches()

    assert payload == []
    assert requests == 4
    assert client.request_attempts == 4
    assert sleeps == [1.0, 2.0, 4.0]
    http_client.close()


def test_monthly_keyed_request_limit_persists_without_storing_key(tmp_path) -> None:
    requests = 0
    api_key = "test-secret-key-that-must-not-be-written"
    ledger_path = tmp_path / "opendota_api_usage.json"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json=[])

    first_http_client = httpx.Client(transport=httpx.MockTransport(handler))
    first = OpenDotaClient(
        api_key=api_key,
        client=first_http_client,
        min_interval_seconds=0,
        monthly_request_limit=1,
        usage_ledger_path=ledger_path,
    )
    first.pro_matches()
    first_http_client.close()

    second_http_client = httpx.Client(transport=httpx.MockTransport(handler))
    second = OpenDotaClient(
        api_key=api_key,
        client=second_http_client,
        min_interval_seconds=0,
        monthly_request_limit=1,
        usage_ledger_path=ledger_path,
    )
    with pytest.raises(OpenDotaMonthlyBudgetExhausted):
        second.get_json("leagues")

    assert requests == 1
    assert api_key not in ledger_path.read_text(encoding="utf-8")
    assert not ledger_path.with_suffix(".json.lock").exists()
    second_http_client.close()


def test_client_fails_closed_when_paid_usage_ledger_is_corrupt(tmp_path) -> None:
    requests = 0
    ledger_path = tmp_path / "opendota_api_usage.json"
    ledger_path.write_text("not-json", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200, json=[])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenDotaClient(
        api_key="dummy-key",
        client=http_client,
        min_interval_seconds=0,
        usage_ledger_path=ledger_path,
    )

    with pytest.raises(OpenDotaUsageLedgerError):
        client.pro_matches()

    assert requests == 0
    http_client.close()


def test_client_redacts_key_from_http_and_network_errors(tmp_path) -> None:
    api_key = "never-show-this-key"
    ledger_path = tmp_path / "opendota_api_usage.json"

    def unauthorized_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    unauthorized_http_client = httpx.Client(transport=httpx.MockTransport(unauthorized_handler))
    unauthorized = OpenDotaClient(
        api_key=api_key,
        client=unauthorized_http_client,
        min_interval_seconds=0,
        usage_ledger_path=ledger_path,
    )
    with pytest.raises(OpenDotaRequestError) as http_error:
        unauthorized.get_json("matches/123")
    assert api_key not in "".join(traceback.format_exception(http_error.value))
    unauthorized_http_client.close()

    def network_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"could not reach {request.url}", request=request)

    network_http_client = httpx.Client(transport=httpx.MockTransport(network_handler))
    network = OpenDotaClient(
        api_key=api_key,
        client=network_http_client,
        min_interval_seconds=0,
        max_attempts=2,
        sleeper=lambda _: None,
        usage_ledger_path=ledger_path,
    )
    with pytest.raises(OpenDotaRequestError) as network_error:
        network.get_json("matches/456")
    assert api_key not in "".join(traceback.format_exception(network_error.value))
    network_http_client.close()


def test_sync_writes_raw_parquet_and_duckdb(project_paths) -> None:
    detail = _detail()
    fetched = datetime(2026, 8, 1, tzinfo=UTC)
    detail_calls = 0

    class FakeClient:
        def league_matches(self, league_id):
            return [detail], fetched

        def match(self, match_id):
            nonlocal detail_calls
            assert match_id == 123
            detail_calls += 1
            return detail, fetched

    result = sync_opendota(
        as_of=datetime(2026, 8, 12, tzinfo=UTC),
        league_ids=[18324],
        include_team_history=False,
        max_matches=1,
        client=FakeClient(),
        paths=project_paths,
    )
    assert result.match_count == 1
    assert result.fantasy_sample_count == 1
    assert result.fantasy_samples_path.name == "fantasy_performance_samples.parquet"
    assert result.matches_path.is_file()
    assert project_paths.database.is_file()
    samples = pd.read_parquet(result.fantasy_samples_path)
    assert samples.loc[0, "teamfight_participation"] == pytest.approx(0.75)
    assert samples.loc[0, "teamfight_participation_provenance"] == "derived"
    assert samples.loc[0, "assists"] == 5
    assert samples.loc[0, "team_total_kills"] == 20
    assert len(list((project_paths.raw / "opendota").rglob("metadata.json"))) == 2
    repeated = sync_opendota(
        as_of=datetime(2026, 8, 12, tzinfo=UTC),
        league_ids=[18324],
        include_team_history=False,
        max_matches=1,
        client=FakeClient(),
        paths=project_paths,
    )
    assert detail_calls == 1
    assert repeated.detailed_match_count == 0


def test_current_team_history_details_are_eligible_for_fantasy(project_paths) -> None:
    fetched = datetime(2026, 8, 1, tzinfo=UTC)
    team_match = {
        "match_id": 456,
        "leagueid": 99,
        "start_time": 1756684800,
        "duration": 2100,
        "radiant": True,
        "opposing_team_id": 7119388,
        "radiant_win": True,
    }
    detail = {**_detail(), "match_id": 456, "leagueid": 99}
    detail_calls: list[int] = []

    class FakeClient:
        def league_matches(self, league_id):
            return [], fetched

        def team_matches(self, team_id):
            return ([team_match] if team_id == 2163 else []), fetched

        def match(self, match_id):
            detail_calls.append(match_id)
            return detail, fetched

    result = sync_opendota(
        as_of=datetime(2026, 8, 12, tzinfo=UTC),
        league_ids=[19719],
        include_team_history=True,
        team_history_detail_limit=1,
        client=FakeClient(),
        paths=project_paths,
    )

    assert detail_calls == [456]
    assert result.detailed_match_count == 1
    assert result.fantasy_sample_count == 1


def test_sync_builds_complete_year_catalog_with_patch_and_league_tier(project_paths) -> None:
    fetched = datetime(2026, 8, 1, tzinfo=UTC)
    current = {
        "match_id": 500,
        "leagueid": 99,
        "league_name": "Premium Cup",
        "start_time": int(datetime(2026, 6, 1, tzinfo=UTC).timestamp()),
        "duration": 2100,
        "radiant_team_id": 1,
        "radiant_name": "Radiant",
        "dire_team_id": 2,
        "dire_name": "Dire",
        "radiant_win": True,
    }
    older = {
        **current,
        "match_id": 300,
        "start_time": int(datetime(2025, 12, 31, tzinfo=UTC).timestamp()),
    }
    cursors: list[int | None] = []

    class FakeClient:
        base_url = "https://example.test/api"

        def leagues(self):
            return [{"leagueid": 99, "name": "Premium Cup", "tier": "premium"}], fetched

        def patches(self):
            return [
                {"id": 59, "name": "7.40", "date": "2025-12-16T00:50:40Z"},
                {"id": 60, "name": "7.41", "date": "2026-03-24T00:50:59Z"},
            ], fetched

        def pro_matches(self, cursor):
            cursors.append(cursor)
            return ([current] if cursor is None else [older]), fetched

        def league_matches(self, league_id):
            return [], fetched

    result = sync_opendota(
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        league_ids=[19719],
        pro_year=2026,
        include_details=False,
        include_team_history=False,
        client=FakeClient(),
        paths=project_paths,
    )

    assert cursors == [None, 500]
    assert result.pro_match_count == 1
    matches = pd.read_parquet(result.matches_path)
    assert matches.loc[0, "patch_name"] == "7.41"
    assert matches.loc[0, "league_tier"] == "premium"
    assert bool(matches.loc[0, "is_pro_match"])
    assert matches.loc[0, "radiant_team_name"] == "Radiant"


def test_fantasy_history_uses_player_ids_and_professional_catalog(project_paths) -> None:
    project_paths.ensure_runtime_dirs()
    fetched = datetime(2026, 8, 1, tzinfo=UTC)
    start_time = int(datetime(2026, 7, 1, tzinfo=UTC).timestamp())
    source_hash = "1" * 64
    catalog_row = {
        "match_id": 123,
        "league_id": 99,
        "series_id": 44,
        "series_type": 1,
        "start_time": datetime(2026, 7, 1, tzinfo=UTC),
        "radiant_team_id": 2163,
        "radiant_team_name": "Team Liquid",
        "dire_team_id": 7119388,
        "dire_team_name": "Team Spirit",
        "radiant_win": True,
        "duration": 2100,
        "patch": 60,
        "patch_name": "7.41",
        "radiant_score": 30,
        "dire_score": 20,
        "data_source": "opendota",
        "is_pro_match": True,
        "source_sha256": source_hash,
        "league_source_sha256": "2" * 64,
        "patch_source_sha256": "3" * 64,
        "fetched_at": fetched,
        "as_of": fetched,
        "league_name": "Professional Cup",
        "league_tier": "professional",
    }
    pd.DataFrame([catalog_row]).to_parquet(project_paths.processed / "matches.parquet", index=False)
    pd.DataFrame(
        [
            {
                "leagueid": 99,
                "name": "Professional Cup",
                "tier": "professional",
                "source_sha256": "2" * 64,
            }
        ]
    ).to_parquet(project_paths.processed / "leagues.parquet", index=False)
    pd.DataFrame(
        [
            {
                "id": 60,
                "name": "7.41",
                "date": "2026-03-24T00:50:59Z",
                "source_sha256": "3" * 64,
            }
        ]
    ).to_parquet(project_paths.processed / "patches.parquet", index=False)

    player_template = _detail()["players"][0]
    detail_players = []
    account_ids = [152962063, 97590558, 201358612, 77490514, 16497807]
    account_ids.extend([900000001, 900000002, 900000003, 900000004, 900000005])
    for index, account_id in enumerate(account_ids):
        detail_players.append(
            {
                **player_template,
                "account_id": account_id,
                "player_slot": index if index < 5 else 128 + index - 5,
            }
        )
    detail = {
        **_detail(),
        "match_id": 123,
        "leagueid": 99,
        "start_time": start_time,
        "players": detail_players,
        "version": 22,
        "od_data": {"has_parsed": True},
    }
    player_calls: list[int] = []
    detail_calls: list[int] = []

    class FakeClient:
        base_url = "https://example.test/api"
        rate_limit_remaining_day = 2000

        def player_matches(self, account_id, *, date_days, significant=0):
            player_calls.append(account_id)
            assert date_days >= 1
            assert significant == 0
            if account_id == 152962063:
                return [{"match_id": 123, "start_time": start_time}], fetched
            return [], fetched

        def match(self, match_id):
            detail_calls.append(match_id)
            return detail, fetched

    result = sync_fantasy_player_history(
        as_of=datetime(2026, 8, 10, 13, 45, 12, tzinfo=UTC),
        year=2026,
        client=FakeClient(),
        paths=project_paths,
        checkpoint_every=1,
    )

    assert len(player_calls) == 80
    assert detail_calls == [123]
    assert result.target_players == 80
    assert result.target_matches == 1
    assert result.target_player_games == 1
    assert result.parsed_complete == 1
    assert result.remaining_details == 0
    scope = pd.read_parquet(result.scope_path)
    assert scope.loc[0, "account_id"] == 152962063
    assert scope.loc[0, "match_id"] == 123
    statuses = pd.read_parquet(result.detail_status_path)
    assert statuses.loc[0, "status"] == "parsed_complete"
