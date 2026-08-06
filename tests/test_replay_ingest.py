from __future__ import annotations

import bz2
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import pytest
import zstandard as zstd

from ti_predictor.hashing import sha256_file
from ti_predictor.ingest.replay import (
    NATIVE_FANTASY_FIELDS,
    NATIVE_PARSER_VERSION,
    ReplayCapture,
    ReplayParser,
    ReplayProcessingError,
    _decompress_replay,
    _download_replay,
    _latest_raw_match_capture,
    _latest_replay_capture,
    _replay_coordinates,
    build_watcher_support,
    enrich_native_replay_coordinates,
    enrich_replay_status_audit,
    overlay_native_fantasy_stats,
    sync_replay_fantasy_history,
    validate_parser_payload,
)
from ti_predictor.paths import PATHS
from ti_predictor.storage import DataStore

SLOTS = [*range(5), *range(128, 133)]


def _parser_payload(
    replay_hash: str,
    *,
    watcher_nonzero: bool = True,
    parser_jar_sha256: str = "fake-parser",
) -> dict:
    players = []
    for index, slot in enumerate(SLOTS):
        values = {
            "madstone_collected": index,
            "smokes_used": 0,
            "watchers_taken": 1 if watcher_nonzero and index == 0 else 0,
            "lotuses_gained": index % 3,
            "tormentor_kills": 0,
        }
        players.append(
            {
                "playerSlot": slot,
                "team": "dire" if slot >= 128 else "radiant",
                "teamSlot": slot - 128 if slot >= 128 else slot,
                "entityPresent": True,
                "stats": {
                    stat_id: {"schemaPresent": True, "observed": True, "value": value}
                    for stat_id, value in values.items()
                },
            }
        )
    return {
        "parserVersion": NATIVE_PARSER_VERSION,
        "parserJarSha256": parser_jar_sha256,
        "replaySha256": replay_hash,
        "engine": "DOTA_S2",
        "buildNumber": 10695,
        "gameVersion": 6699,
        "lastTick": 12345,
        "schemaFingerprint": "schema-v1",
        "durationMs": 12,
        "players": players,
    }


class FakeParser:
    version = NATIVE_PARSER_VERSION

    def __init__(
        self,
        *,
        watcher_nonzero: bool = True,
        artifact_sha256: str = "fake-parser",
    ) -> None:
        self.calls = 0
        self.watcher_nonzero = watcher_nonzero
        self.artifact_sha256 = artifact_sha256

    def parse(self, replay_path: Path, *, expected_sha256: str) -> dict:
        self.calls += 1
        assert replay_path.read_bytes() == b"fixed replay fixture"
        return _parser_payload(
            expected_sha256,
            watcher_nonzero=self.watcher_nonzero,
            parser_jar_sha256=self.artifact_sha256,
        )


class StaticReplayClient:
    def __init__(self, content: bytes, *, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code
        self.calls = 0

    def get(self, url: str) -> httpx.Response:
        assert url == "https://replay.test/100.dem.bz2"
        self.calls += 1
        return httpx.Response(
            self.status_code,
            content=self.content,
            headers={"content-type": "application/octet-stream"},
        )


def _prepare_sync_inputs(
    project_paths, *, match_id: int = 100, include_extra_player: bool = False
) -> list[int]:
    started_at = datetime(2026, 7, 1, tzinfo=UTC)
    account_ids = [1000 + index for index in range(10)]
    players = []
    for slot, account_id in zip(SLOTS, account_ids, strict=True):
        players.append(
            {
                "player_slot": slot,
                "account_id": account_id,
                "item_uses": {"madstone_bundle": 7, "smoke_of_deceit": 8, "famango": 9},
                "ability_uses": {"ability_lamp_use": 10},
                "killed": {"npc_dota_miniboss": 11},
            }
        )
    if include_extra_player:
        players.append({"player_slot": 99, "account_id": 9999})
    payload = {
        "match_id": match_id,
        "start_time": int(started_at.timestamp()),
        "duration": 1800,
        "radiant_win": True,
        "replay_url": "https://replay.test/100.dem.bz2",
        "replay_salt": 123456,
        "cluster": 321,
        "players": players,
    }
    DataStore(project_paths).write_raw_json(
        source="opendota",
        resource=f"matches/{match_id}",
        payload=payload,
        request={"method": "GET", "url": f"https://api.test/matches/{match_id}"},
        fetched_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    pd.DataFrame(
        {
            "match_id": [match_id] * 10,
            "account_id": account_ids,
            "start_time": [started_at] * 10,
        }
    ).to_parquet(project_paths.processed / "fantasy_player_history_scope.parquet", index=False)
    sample_rows = []
    for account_id in account_ids:
        row = {"match_id": match_id, "account_id": account_id}
        for stat_id in NATIVE_FANTASY_FIELDS:
            row[stat_id] = 999.0
            row[f"{stat_id}_provenance"] = "proxy"
        sample_rows.append(row)
    pd.DataFrame(sample_rows).to_parquet(
        project_paths.processed / "fantasy_performance_samples.parquet", index=False
    )
    return account_ids


def _native_frame(*, watcher_nonzero: bool) -> pd.DataFrame:
    rows = []
    for index, _slot in enumerate(SLOTS):
        row = {
            "match_id": 100,
            "account_id": 1000 + index,
            "entity_present": True,
            "build_number": 10695,
            "game_version": 6699,
            "schema_fingerprint": "schema-v1",
            "decompressed_sha256": "decompressed",
            "compressed_sha256": "compressed",
            "parser_version": NATIVE_PARSER_VERSION,
        }
        for stat_id in NATIVE_FANTASY_FIELDS:
            row[stat_id] = 1 if stat_id == "watchers_taken" and watcher_nonzero and index == 0 else 0
            row[f"{stat_id}_schema_present"] = True
            row[f"{stat_id}_observed"] = True
        rows.append(row)
    return pd.DataFrame(rows)


def test_parser_payload_accepts_observed_zero_and_rejects_getter_default() -> None:
    payload = _parser_payload("abc")
    validate_parser_payload(payload, expected_sha256="abc")
    zero = payload["players"][1]["stats"]["smokes_used"]
    assert zero == {"schemaPresent": True, "observed": True, "value": 0}

    zero["observed"] = False
    with pytest.raises(ReplayProcessingError, match="unobserved smokes_used has a value"):
        validate_parser_payload(payload, expected_sha256="abc")


def test_parser_rejects_jar_change_after_construction(tmp_path: Path) -> None:
    jar_path = tmp_path / "parser.jar"
    replay_path = tmp_path / "replay.dem"
    jar_path.write_bytes(b"first parser artifact")
    replay_path.write_bytes(b"replay")
    parser = ReplayParser(jar_path=jar_path)
    original_hash = parser.artifact_sha256

    jar_path.write_bytes(b"changed parser artifact")

    with pytest.raises(ReplayProcessingError, match="jar changed during this sync"):
        parser.parse(replay_path, expected_sha256="unused")
    assert parser._artifact_sha256 == original_hash


def test_watcher_support_needs_complete_nonzero_fixture() -> None:
    all_zero = _native_frame(watcher_nonzero=False)
    support = build_watcher_support(all_zero)
    assert support.loc[0, "status"] == "build_untrusted"
    assert support.loc[0, "complete_fixture_matches"] == 1
    assert support.loc[0, "nonzero_fixture_matches"] == 0

    credible = _native_frame(watcher_nonzero=True).assign(match_id=101)
    admitted = build_watcher_support(pd.concat([all_zero, credible], ignore_index=True))
    assert admitted.loc[0, "status"] == "admitted"
    assert admitted.loc[0, "nonzero_fixture_matches"] == 1


def test_overlay_never_uses_proxy_and_preserves_exact_zero() -> None:
    samples = pd.DataFrame(
        {
            "match_id": [100, 100],
            "account_id": [1000, 9999],
            "smokes_used": [99.0, 88.0],
            "smokes_used_provenance": ["proxy", "proxy"],
        }
    )

    output = overlay_native_fantasy_stats(samples, native=_native_frame(watcher_nonzero=True))

    exact = output.loc[output["account_id"].eq(1000)].iloc[0]
    missing = output.loc[output["account_id"].eq(9999)].iloc[0]
    assert exact["smokes_used"] == 0
    assert exact["smokes_used_provenance"] == "exact"
    assert exact["watchers_taken"] == 1
    assert missing["smokes_used"] is None
    assert missing["smokes_used_provenance"] == "unavailable"


def test_overlay_rejects_stale_parser_or_missing_replay_hash() -> None:
    samples = pd.DataFrame({"match_id": [100], "account_id": [1000]})
    native = _native_frame(watcher_nonzero=True).loc[lambda frame: frame["account_id"].eq(1000)]

    stale = overlay_native_fantasy_stats(samples, native=native.assign(parser_version="stale"))
    unhashed = overlay_native_fantasy_stats(
        samples,
        native=native.assign(compressed_sha256=None),
    )

    assert stale.loc[0, "madstone_collected"] is None
    assert stale.loc[0, "madstone_collected_provenance"] == "unavailable"
    assert unhashed.loc[0, "smokes_used"] is None
    assert unhashed.loc[0, "smokes_used_provenance"] == "unavailable"

    incomplete = overlay_native_fantasy_stats(
        samples,
        native=pd.DataFrame({"match_id": [100], "account_id": [1000]}),
    )
    assert incomplete.loc[0, "tormentor_kills"] is None
    assert incomplete.loc[0, "tormentor_kills_provenance"] == "unavailable"


def test_download_retries_and_records_attempt_history(project_paths) -> None:
    responses = [503, 200]

    class RetryClient:
        def get(self, url: str) -> httpx.Response:
            status = responses.pop(0)
            return httpx.Response(status, content=b"demo" if status == 200 else b"")

    sleeps: list[float] = []
    capture = _download_replay(
        project_paths,
        match_id=100,
        replay_url="https://replay.test/100.dem.bz2",
        client=RetryClient(),
        refresh=True,
        replay_salt=123456,
        replay_cluster=321,
        sleeper=sleeps.append,
    )

    assert capture.request_attempts == 2
    assert [row["http_status"] for row in capture.retry_history] == [503, 200]
    assert sleeps == [0.25]
    metadata_path = next((project_paths.raw / "valve_replay").rglob("metadata.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["retry_history"] == list(capture.retry_history)
    assert metadata["request"]["replay_salt"] == 123456
    assert metadata["request"]["cluster"] == 321


def test_replay_coordinates_recovers_missing_official_url_values() -> None:
    payload = {
        "match_id": 8696203572,
        "replay_salt": None,
        "cluster": None,
        "replay_url": "http://replay274.valve.net/570/8696203572_1444850494.dem.bz2",
    }

    assert _replay_coordinates(payload) == (1444850494, 274)
    mismatched = payload | {"replay_url": "http://replay274.valve.net/570/8696203573_1444850494.dem.bz2"}
    assert _replay_coordinates(mismatched) == (None, 274)
    non_official = payload | {"replay_url": "https://example.test/570/8696203572_1444850494.dem.bz2"}
    assert _replay_coordinates(non_official) == (None, None)


def test_raw_match_capture_rejects_content_hash_mismatch(project_paths) -> None:
    _prepare_sync_inputs(project_paths)
    body_path = next((project_paths.raw / "opendota" / "matches" / "100").rglob("response.json"))
    body_path.write_text("{}\n", encoding="utf-8")

    assert _latest_raw_match_capture(project_paths, 100) is None


def test_changed_replay_url_does_not_reuse_old_capture(project_paths) -> None:
    requested: list[str] = []

    class RecordingClient:
        def get(self, url: str) -> httpx.Response:
            requested.append(url)
            return httpx.Response(200, content=url.encode())

    first_url = "https://replay.test/100_old.dem.bz2"
    second_url = "https://replay.test/100_new.dem.bz2"
    first = _download_replay(
        project_paths,
        match_id=100,
        replay_url=first_url,
        client=RecordingClient(),
        refresh=False,
    )
    second = _download_replay(
        project_paths,
        match_id=100,
        replay_url=second_url,
        client=RecordingClient(),
        refresh=False,
    )

    assert requested == [first_url, second_url]
    assert first.content_sha256 != second.content_sha256
    assert _latest_replay_capture(project_paths, 100).replay_url == second_url


def test_decompression_uses_content_magic_for_zstd_with_bz2_url(project_paths) -> None:
    body_path = project_paths.raw / "mislabelled.dem"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(zstd.ZstdCompressor().compress(b"zstd replay fixture"))
    capture = ReplayCapture(
        body_path=body_path,
        content_sha256="compressed",
        byte_count=body_path.stat().st_size,
        fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
        replay_url="https://replay.test/mislabelled.dem.bz2",
        request_attempts=1,
        retry_history=(),
    )

    replay_path, _digest, byte_count, compression = _decompress_replay(capture, project_paths)
    try:
        assert replay_path.read_bytes() == b"zstd replay fixture"
        assert byte_count == len(b"zstd replay fixture")
        assert compression == "zstd"
    finally:
        replay_path.unlink(missing_ok=True)


def test_replay_sync_is_resumable_deterministic_and_separates_proxy(project_paths) -> None:
    account_ids = _prepare_sync_inputs(project_paths)
    compressed = bz2.compress(b"fixed replay fixture")
    client = StaticReplayClient(compressed)
    parser = FakeParser()
    cutoff = datetime(2026, 8, 1, tzinfo=UTC)

    first = sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=parser,
        client=client,
        paths=project_paths,
    )

    assert first.status == "publishable"
    assert first.target_matches == 1
    assert first.attempted_matches == 1
    assert first.exact_matches == 1
    assert first.remaining_matches == 0
    assert first.watcher_trusted_cohorts == 1
    assert parser.calls == 1
    assert client.calls == 1
    native = pd.read_parquet(first.native_stats_path)
    statuses = pd.read_parquet(first.replay_status_path)
    diagnostics = pd.read_parquet(first.proxy_diagnostics_path)
    samples = pd.read_parquet(first.fantasy_samples_path)
    assert len(native) == 10
    assert statuses.loc[0, "status"] == "exact"
    assert statuses.loc[0, "replay_salt"] == 123456
    assert statuses.loc[0, "replay_cluster"] == 321
    assert statuses.loc[0, "compressed_bytes"] == len(compressed)
    assert statuses.loc[0, "decompressed_bytes"] == len(b"fixed replay fixture")
    assert statuses.loc[0, "compression"] == "bz2"
    assert diagnostics["smokes_used_proxy"].eq(8.0).all()
    assert samples["smokes_used"].eq(0).all()
    assert samples["smokes_used_provenance"].eq("exact").all()
    assert set(samples["account_id"]) == set(account_ids)

    tracked_paths = (
        first.native_stats_path,
        first.replay_status_path,
        first.proxy_diagnostics_path,
        first.watcher_support_path,
        first.fantasy_samples_path,
    )
    first_hashes = [sha256_file(path) for path in tracked_paths]
    no_network = StaticReplayClient(b"", status_code=500)
    repeated = sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=parser,
        client=no_network,
        paths=project_paths,
    )

    assert repeated.attempted_matches == 0
    assert repeated.reused_matches == 1
    assert repeated.data_sha256 == first.data_sha256
    assert no_network.calls == 0
    assert parser.calls == 1
    assert [sha256_file(path) for path in tracked_paths] == first_hashes


def test_changed_parser_artifact_reparses_verified_local_capture(project_paths) -> None:
    _prepare_sync_inputs(project_paths)
    cutoff = datetime(2026, 8, 1, tzinfo=UTC)
    first_parser = FakeParser()
    sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=first_parser,
        client=StaticReplayClient(bz2.compress(b"fixed replay fixture")),
        paths=project_paths,
    )

    second_parser = FakeParser(artifact_sha256="fake-parser-v2")
    no_network = StaticReplayClient(b"", status_code=500)
    reparsed = sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=second_parser,
        client=no_network,
        paths=project_paths,
    )

    assert reparsed.attempted_matches == 1
    assert reparsed.reused_matches == 0
    assert second_parser.calls == 1
    assert no_network.calls == 0
    status = pd.read_parquet(reparsed.replay_status_path).iloc[0]
    assert status["parser_jar_sha256"] == "fake-parser-v2"


def test_all_zero_watcher_cohort_keeps_only_watcher_unavailable(project_paths) -> None:
    _prepare_sync_inputs(project_paths)
    result = sync_replay_fantasy_history(
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        year=2026,
        workers=1,
        parser=FakeParser(watcher_nonzero=False),
        client=StaticReplayClient(bz2.compress(b"fixed replay fixture")),
        paths=project_paths,
    )

    assert result.status == "warning"
    assert result.build_untrusted_matches == 1
    status = pd.read_parquet(result.replay_status_path).iloc[0]
    assert "non-zero fixture" in status["error"]
    samples = pd.read_parquet(result.fantasy_samples_path)
    assert samples["madstone_collected_provenance"].eq("exact").all()
    assert samples["watchers_taken"].isna().all()
    assert samples["watchers_taken_provenance"].eq("unavailable").all()


def test_parse_failure_keeps_capture_audit_and_proxy_diagnostics(project_paths) -> None:
    _prepare_sync_inputs(project_paths)

    class FailingParser:
        version = NATIVE_PARSER_VERSION

        def parse(self, replay_path: Path, *, expected_sha256: str) -> dict:
            raise ReplayProcessingError("parse_failed", "fixture parser failure")

    result = sync_replay_fantasy_history(
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        year=2026,
        workers=1,
        parser=FailingParser(),
        client=StaticReplayClient(bz2.compress(b"fixed replay fixture")),
        paths=project_paths,
    )

    status = pd.read_parquet(result.replay_status_path).iloc[0]
    diagnostics = pd.read_parquet(result.proxy_diagnostics_path)
    assert status["status"] == "parse_failed"
    assert status["compressed_sha256"]
    assert status["decompressed_sha256"]
    assert status["request_attempts"] == 1
    assert status["compressed_bytes"] > 0
    assert status["decompressed_bytes"] == len(b"fixed replay fixture")
    assert status["compression"] == "bz2"
    assert status["replay_salt"] == 123456
    assert status["replay_cluster"] == 321
    assert len(diagnostics) == 10


def test_invalid_eleven_player_join_fails_before_download(project_paths) -> None:
    _prepare_sync_inputs(project_paths, include_extra_player=True)
    parser = FakeParser()
    client = StaticReplayClient(bz2.compress(b"fixed replay fixture"))

    result = sync_replay_fantasy_history(
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        year=2026,
        workers=1,
        parser=parser,
        client=client,
        paths=project_paths,
    )
    status = pd.read_parquet(result.replay_status_path).iloc[0]

    assert status["status"] == "join_failed"
    assert parser.calls == 0
    assert client.calls == 0


def test_match_finishing_after_as_of_is_not_downloaded(project_paths) -> None:
    _prepare_sync_inputs(project_paths)
    parser = FakeParser()
    client = StaticReplayClient(bz2.compress(b"fixed replay fixture"))

    result = sync_replay_fantasy_history(
        as_of=datetime(2026, 7, 1, 0, 10, tzinfo=UTC),
        year=2026,
        workers=1,
        parser=parser,
        client=client,
        paths=project_paths,
    )
    status = pd.read_parquet(result.replay_status_path).iloc[0]

    assert status["status"] == "missing"
    assert "not completed by as_of" in status["error"]
    assert parser.calls == 0
    assert client.calls == 0


def test_mismatched_source_or_official_replay_identity_is_not_downloaded(project_paths) -> None:
    cutoff = datetime(2026, 8, 1, tzinfo=UTC)
    client = StaticReplayClient(bz2.compress(b"fixed replay fixture"))
    _prepare_sync_inputs(project_paths)
    payload, _, _ = _latest_raw_match_capture(project_paths, 100)

    payload["match_id"] = 101
    DataStore(project_paths).write_raw_json(
        source="opendota",
        resource="matches/100",
        payload=payload,
        request={"method": "GET", "url": "https://api.test/matches/100"},
        fetched_at=datetime(2026, 7, 3, tzinfo=UTC),
    )
    source_result = sync_replay_fantasy_history(
        as_of=cutoff,
        match_ids=[100],
        parser=FakeParser(),
        client=client,
        paths=project_paths,
    )
    source_status = pd.read_parquet(source_result.replay_status_path).iloc[0]
    assert source_status["status"] == "join_failed"
    assert "capture identity 101" in source_status["error"]
    assert client.calls == 0

    payload["match_id"] = 100
    payload["replay_url"] = "http://replay321.valve.net/570/101_123456.dem.bz2"
    DataStore(project_paths).write_raw_json(
        source="opendota",
        resource="matches/100",
        payload=payload,
        request={"method": "GET", "url": "https://api.test/matches/100"},
        fetched_at=datetime(2026, 7, 4, tzinfo=UTC),
    )
    replay_result = sync_replay_fantasy_history(
        as_of=cutoff,
        match_ids=[100],
        parser=FakeParser(),
        client=client,
        paths=project_paths,
    )
    replay_status = pd.read_parquet(replay_result.replay_status_path).iloc[0]
    assert replay_status["status"] == "join_failed"
    assert "replay URL identity 101" in replay_status["error"]
    assert client.calls == 0


def test_status_audit_migration_uses_native_and_immutable_raw_coordinates(project_paths) -> None:
    _prepare_sync_inputs(project_paths)
    legacy = pd.DataFrame({"match_id": [100], "status": ["exact"]})
    native = pd.DataFrame(
        {
            "match_id": [100],
            "compressed_sha256": ["compressed"],
            "decompressed_sha256": ["decompressed"],
            "compressed_bytes": [123],
            "decompressed_bytes": [456],
            "compression": ["bz2"],
        }
    )

    migrated = enrich_replay_status_audit(legacy, native, paths=project_paths).iloc[0]

    assert migrated["compressed_sha256"] == "compressed"
    assert migrated["decompressed_sha256"] == "decompressed"
    assert migrated["compressed_bytes"] == 123
    assert migrated["decompressed_bytes"] == 456
    assert migrated["compression"] == "bz2"
    assert migrated["replay_salt"] == 123456
    assert migrated["replay_cluster"] == 321

    native_coordinates = enrich_native_replay_coordinates(
        native,
        pd.DataFrame({"match_id": [100], "replay_salt": [123456], "replay_cluster": [321]}),
    )
    assert native_coordinates.loc[0, "replay_salt"] == 123456
    assert native_coordinates.loc[0, "replay_cluster"] == 321


def test_resumed_sync_persists_status_audit_migration_without_reparse(project_paths) -> None:
    _prepare_sync_inputs(project_paths)
    parser = FakeParser()
    cutoff = datetime(2026, 8, 1, tzinfo=UTC)
    first = sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=parser,
        client=StaticReplayClient(bz2.compress(b"fixed replay fixture")),
        paths=project_paths,
    )
    status = pd.read_parquet(first.replay_status_path).drop(
        columns=[
            "replay_salt",
            "replay_cluster",
            "compressed_bytes",
            "decompressed_bytes",
            "compression",
        ]
    )
    status.to_parquet(first.replay_status_path, index=False)
    native = pd.read_parquet(first.native_stats_path).drop(columns=["replay_salt", "replay_cluster"])
    native.to_parquet(first.native_stats_path, index=False)

    resumed = sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=parser,
        client=StaticReplayClient(b"", status_code=500),
        paths=project_paths,
    )
    persisted = pd.read_parquet(resumed.replay_status_path).iloc[0]
    persisted_native = pd.read_parquet(resumed.native_stats_path)

    assert resumed.attempted_matches == 0
    assert parser.calls == 1
    assert persisted["replay_salt"] == 123456
    assert persisted["replay_cluster"] == 321
    assert persisted["compressed_bytes"] > 0
    assert persisted["decompressed_bytes"] == len(b"fixed replay fixture")
    assert persisted["compression"] == "bz2"
    assert persisted_native["replay_salt"].eq(123456).all()
    assert persisted_native["replay_cluster"].eq(321).all()

    stable = sync_replay_fantasy_history(
        as_of=cutoff,
        year=2026,
        workers=1,
        parser=parser,
        client=StaticReplayClient(b"", status_code=500),
        paths=project_paths,
    )
    assert stable.attempted_matches == 0
    assert stable.data_sha256 == resumed.data_sha256


def test_frozen_six_match_fixture_is_complete() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "replay_native_expected_2026.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["parser_version"] == NATIVE_PARSER_VERSION
    assert len(fixture["matches"]) == 6
    assert all(len(match["players"]) == 10 for match in fixture["matches"])
    assert all(len(match["compressed_sha256"]) == 64 for match in fixture["matches"])
    assert all(len(match["decompressed_sha256"]) == 64 for match in fixture["matches"])
    assert all(len(match["schema_fingerprint"]) == 64 for match in fixture["matches"])
    assert all([row[0] for row in match["players"]] == SLOTS for match in fixture["matches"])
    aggregates = {
        match["match_id"]: [sum(row[index] for row in match["players"]) for index in range(1, 6)]
        for match in fixture["matches"]
    }
    assert aggregates[8680265600] == [104, 5, 12, 10, 0]
    assert aggregates[8924770688] == [360, 12, 29, 26, 8]


def test_optional_cached_six_replay_parser_integration() -> None:
    if os.getenv("TI_REPLAY_INTEGRATION") != "1":
        pytest.skip("set TI_REPLAY_INTEGRATION=1 to run the cached six-replay integration")
    expected_path = Path(__file__).parent / "fixtures" / "replay_native_expected_2026.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    parser = ReplayParser(
        jar_path=Path(os.environ["TI_REPLAY_PARSER_JAR"]) if os.getenv("TI_REPLAY_PARSER_JAR") else None
    )

    for match in expected["matches"]:
        capture = _latest_replay_capture(PATHS, match["match_id"])
        if capture is None:
            pytest.fail(f"missing immutable cached replay fixture: {match['match_id']}")
        assert capture.content_sha256 == match["compressed_sha256"]
        replay_path, replay_hash, _byte_count, _compression = _decompress_replay(capture, PATHS)
        try:
            assert replay_hash == match["decompressed_sha256"]
            payload = parser.parse(replay_path, expected_sha256=replay_hash)
        finally:
            replay_path.unlink(missing_ok=True)
        assert payload["buildNumber"] == match["build_number"]
        assert payload["gameVersion"] == match["game_version"]
        assert payload["schemaFingerprint"] == match["schema_fingerprint"]
        actual = []
        for player in payload["players"]:
            actual.append(
                [
                    player["playerSlot"],
                    *[player["stats"][stat_id]["value"] for stat_id in expected["stat_order"]],
                ]
            )
        assert actual == match["players"]
