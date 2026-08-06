from __future__ import annotations

import bz2
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
import pandas as pd
import zstandard as zstd

from ti_predictor.hashing import canonical_json, sha256_bytes, sha256_file
from ti_predictor.paths import PATHS, ProjectPaths
from ti_predictor.schemas import AuditIssue, as_utc, utc_now
from ti_predictor.storage import DataStore, read_parquet_if_exists, timestamp_slug

NATIVE_FANTASY_FIELDS: dict[str, str] = {
    "madstone_collected": "m_iNeutralTokensFound",
    "smokes_used": "m_iSmokesUsed",
    "watchers_taken": "m_iWatchersTaken",
    "lotuses_gained": "m_iLotusesTaken",
    "tormentor_kills": "m_iTormentorKills",
}
NATIVE_PARSER_VERSION = "p1-native-v1"
FINAL_REPLAY_STATUSES = frozenset({"exact", "build_untrusted"})
ALL_REPLAY_STATUSES = frozenset(
    {
        "exact",
        "missing",
        "download_failed",
        "decompress_failed",
        "parse_failed",
        "join_failed",
        "build_untrusted",
    }
)
NATIVE_TABLE_COLUMNS = (
    "match_id",
    "account_id",
    "player_slot",
    "team",
    "team_slot",
    "entity_present",
    "parser_version",
    "parser_jar_sha256",
    "engine",
    "build_number",
    "game_version",
    "last_tick",
    "schema_fingerprint",
    "compressed_sha256",
    "compressed_bytes",
    "decompressed_sha256",
    "decompressed_bytes",
    "compression",
    "opendota_source_sha256",
    "replay_salt",
    "replay_cluster",
    "fetched_at",
    "as_of",
    *(
        column
        for stat_id in NATIVE_FANTASY_FIELDS
        for column in (stat_id, f"{stat_id}_schema_present", f"{stat_id}_observed")
    ),
    "watcher_cohort_trusted",
)
REPLAY_STATUS_COLUMNS = (
    "match_id",
    "status",
    "parser_version",
    "parser_jar_sha256",
    "engine",
    "build_number",
    "game_version",
    "schema_fingerprint",
    "compressed_sha256",
    "decompressed_sha256",
    "opendota_source_sha256",
    "replay_url",
    "replay_salt",
    "replay_cluster",
    "request_attempts",
    "retry_history_json",
    "compressed_bytes",
    "decompressed_bytes",
    "compression",
    "fetched_at",
    "as_of",
    "error",
)
PROXY_DIAGNOSTIC_COLUMNS = (
    "match_id",
    "account_id",
    "player_slot",
    *(f"{stat_id}_proxy" for stat_id in NATIVE_FANTASY_FIELDS),
    "as_of",
)
REPLAY_PATH_PATTERN = re.compile(
    r"/(?P<match_id>[1-9]\d*)_(?P<salt>[1-9]\d*)\.dem(?:\.(?:bz2|zst))?/?$",
    re.IGNORECASE,
)
REPLAY_HOST_PATTERN = re.compile(r"^replay(?P<cluster>[1-9]\d*)\.valve\.net$", re.IGNORECASE)


class ReplayParserProtocol(Protocol):
    @property
    def version(self) -> str: ...

    def parse(self, replay_path: Path, *, expected_sha256: str) -> dict[str, Any]: ...


class ReplayProcessingError(RuntimeError):
    def __init__(
        self,
        status: str,
        message: str,
        *,
        request_attempts: int | None = None,
        retry_history: list[dict[str, Any]] | None = None,
    ) -> None:
        if status not in ALL_REPLAY_STATUSES - FINAL_REPLAY_STATUSES:
            raise ValueError(f"invalid replay error status: {status}")
        self.status = status
        self.request_attempts = request_attempts
        self.retry_history = retry_history or []
        super().__init__(message)


@dataclass(frozen=True)
class ReplayCapture:
    body_path: Path
    content_sha256: str
    byte_count: int
    fetched_at: datetime
    replay_url: str
    request_attempts: int
    retry_history: tuple[dict[str, Any], ...]


@dataclass
class MatchReplayResult:
    status_row: dict[str, Any]
    native_rows: list[dict[str, Any]] = field(default_factory=list)
    proxy_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReplayFantasySyncResult:
    native_stats_path: Path
    replay_status_path: Path
    proxy_diagnostics_path: Path
    watcher_support_path: Path
    fantasy_samples_path: Path
    target_matches: int
    attempted_matches: int
    reused_matches: int
    remaining_matches: int
    exact_matches: int
    build_untrusted_matches: int
    failed_matches: int
    watcher_trusted_cohorts: int
    data_sha256: str
    issues: list[AuditIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(issue.severity == "blocking" for issue in self.issues):
            return "blocked"
        if (
            self.failed_matches
            or self.build_untrusted_matches
            or any(issue.severity == "warning" for issue in self.issues)
        ):
            return "warning"
        return "publishable"


class ReplayParser:
    def __init__(
        self,
        *,
        jar_path: Path | None = None,
        java_command: str = "java",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.jar_path = (
            jar_path or PATHS.root / "src" / "ti_replay_parser" / "target" / "ti-replay-parser.jar"
        ).resolve()
        self.java_command = java_command
        self.timeout_seconds = timeout_seconds
        self._artifact_sha256 = sha256_file(self.jar_path) if self.jar_path.is_file() else None
        self._artifact_signature = self._jar_signature() if self.jar_path.is_file() else None

    @property
    def version(self) -> str:
        return NATIVE_PARSER_VERSION

    @property
    def artifact_sha256(self) -> str | None:
        if self.jar_path.is_file():
            return self._verify_artifact()
        return self._artifact_sha256

    def _jar_signature(self) -> tuple[int, int]:
        metadata = self.jar_path.stat()
        return metadata.st_size, metadata.st_mtime_ns

    def _verify_artifact(self) -> str:
        try:
            signature = self._jar_signature()
        except OSError as error:
            raise ReplayProcessingError(
                "parse_failed", f"replay parser jar is unavailable: {self.jar_path}"
            ) from error
        current_hash = self._artifact_sha256
        if current_hash is None or signature != self._artifact_signature:
            observed_hash = sha256_file(self.jar_path)
            if current_hash is not None and observed_hash != current_hash:
                raise ReplayProcessingError(
                    "parse_failed",
                    "replay parser jar changed during this sync; restart with one immutable artifact",
                )
            self._artifact_sha256 = observed_hash
            self._artifact_signature = signature
            current_hash = observed_hash
        return current_hash

    def parse(self, replay_path: Path, *, expected_sha256: str) -> dict[str, Any]:
        if not self.jar_path.is_file():
            raise ReplayProcessingError(
                "parse_failed",
                f"replay parser jar is missing: {self.jar_path}; build src/ti_replay_parser first",
            )
        artifact_sha256 = self._verify_artifact()
        try:
            completed = subprocess.run(
                [
                    self.java_command,
                    "--enable-native-access=ALL-UNNAMED",
                    "-jar",
                    str(self.jar_path),
                    str(replay_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReplayProcessingError("parse_failed", f"parser process failed: {error}") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "no stderr"
            raise ReplayProcessingError("parse_failed", f"parser exited {completed.returncode}: {detail}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ReplayProcessingError("parse_failed", "parser returned invalid JSON") from error
        self._verify_artifact()
        validate_parser_payload(payload, expected_sha256=expected_sha256)
        payload["parserJarSha256"] = artifact_sha256
        return payload


def validate_parser_payload(payload: Any, *, expected_sha256: str) -> None:
    if not isinstance(payload, dict):
        raise ReplayProcessingError("parse_failed", "parser output is not an object")
    if payload.get("parserVersion") != NATIVE_PARSER_VERSION:
        raise ReplayProcessingError(
            "parse_failed", f"unexpected parser version: {payload.get('parserVersion')!r}"
        )
    if str(payload.get("replaySha256", "")).lower() != expected_sha256.lower():
        raise ReplayProcessingError("parse_failed", "parser replay hash does not match decompressed file")
    if not payload.get("schemaFingerprint"):
        raise ReplayProcessingError("parse_failed", "parser omitted schema fingerprint")
    if not isinstance(payload.get("engine"), str) or not payload["engine"]:
        raise ReplayProcessingError("parse_failed", "parser omitted replay engine")
    for key in ("buildNumber", "gameVersion", "lastTick", "durationMs"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ReplayProcessingError("parse_failed", f"parser returned invalid {key}")
    players = payload.get("players")
    if not isinstance(players, list) or len(players) != 10:
        raise ReplayProcessingError("parse_failed", "parser did not return ten player slots")
    slots = {row.get("playerSlot") for row in players if isinstance(row, dict)}
    expected_slots = {*range(5), *range(128, 133)}
    if slots != expected_slots:
        raise ReplayProcessingError("parse_failed", f"unexpected parser player slots: {sorted(slots)}")
    for row in players:
        if not isinstance(row, dict):
            raise ReplayProcessingError("parse_failed", "parser returned a non-object player row")
        slot = row.get("playerSlot")
        expected_team = "dire" if slot is not None and int(slot) >= 128 else "radiant"
        expected_team_slot = int(slot) - 128 if expected_team == "dire" else int(slot)
        if (
            row.get("team") != expected_team
            or row.get("teamSlot") != expected_team_slot
            or not isinstance(row.get("entityPresent"), bool)
        ):
            raise ReplayProcessingError("parse_failed", f"invalid parser identity for slot {slot}")
        stats = row.get("stats") if isinstance(row, dict) else None
        if not isinstance(stats, dict) or set(stats) != set(NATIVE_FANTASY_FIELDS):
            raise ReplayProcessingError("parse_failed", "parser returned an incomplete native stat set")
        for stat_id, observation in stats.items():
            if not isinstance(observation, dict):
                raise ReplayProcessingError("parse_failed", f"invalid observation for {stat_id}")
            if not isinstance(observation.get("schemaPresent"), bool) or not isinstance(
                observation.get("observed"), bool
            ):
                raise ReplayProcessingError("parse_failed", f"missing presence flags for {stat_id}")
            value = observation.get("value")
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ReplayProcessingError("parse_failed", f"invalid native value for {stat_id}")
            if observation["observed"] and not observation["schemaPresent"]:
                raise ReplayProcessingError("parse_failed", f"observed absent schema field {stat_id}")
            if observation["observed"] and value is None:
                raise ReplayProcessingError("parse_failed", f"observed {stat_id} has no integer value")
            if not observation["observed"] and value is not None:
                raise ReplayProcessingError("parse_failed", f"unobserved {stat_id} has a value")


def _latest_raw_match_capture(
    paths: ProjectPaths, match_id: int
) -> tuple[dict[str, Any], datetime, str] | None:
    root = paths.raw / "opendota" / "matches" / str(match_id)
    if not root.is_dir():
        return None
    for body_path in sorted(root.glob("*/response.json"), reverse=True):
        metadata_path = body_path.with_name("metadata.json")
        try:
            content = body_path.read_bytes().rstrip(b"\n")
            payload = json.loads(content)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            fetched_at = as_utc(metadata["fetched_at"])
            source_hash = str(metadata["content_sha256"])
            byte_count = int(metadata["bytes"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and fetched_at is not None
            and len(content) == byte_count
            and sha256_bytes(content) == source_hash
        ):
            return payload, fetched_at, source_hash
    return None


def _replay_url(payload: Mapping[str, Any]) -> str | None:
    direct = payload.get("replay_url")
    if isinstance(direct, str) and direct.startswith(("http://", "https://")):
        return direct
    match_id = payload.get("match_id")
    salt = payload.get("replay_salt")
    cluster = payload.get("cluster")
    if match_id and salt and cluster:
        return f"http://replay{int(cluster)}.valve.net/570/{int(match_id)}_{int(salt)}.dem.bz2"
    return None


def _replay_coordinates(
    payload: Mapping[str, Any], replay_url: str | None = None
) -> tuple[int | None, int | None]:
    def positive_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    match_id = positive_int(payload.get("match_id"))
    salt = positive_int(payload.get("replay_salt"))
    cluster = positive_int(payload.get("cluster"))
    candidate = replay_url or _replay_url(payload)
    if not candidate:
        return salt, cluster
    parsed_url = urlsplit(candidate)
    path_match = REPLAY_PATH_PATTERN.search(parsed_url.path)
    host_match = REPLAY_HOST_PATTERN.fullmatch(parsed_url.hostname or "")
    if (
        salt is None
        and host_match is not None
        and path_match is not None
        and match_id is not None
        and int(path_match.group("match_id")) == match_id
    ):
        salt = int(path_match.group("salt"))
    if cluster is None and host_match is not None:
        cluster = int(host_match.group("cluster"))
    return salt, cluster


def _official_replay_match_id(replay_url: str) -> int | None:
    parsed_url = urlsplit(replay_url)
    if REPLAY_HOST_PATTERN.fullmatch(parsed_url.hostname or "") is None:
        return None
    path_match = REPLAY_PATH_PATTERN.search(parsed_url.path)
    if path_match is None:
        raise ReplayProcessingError("join_failed", "official replay URL has an invalid path")
    return int(path_match.group("match_id"))


def _completed_by(payload: Mapping[str, Any], cutoff: datetime) -> bool:
    try:
        start = float(payload["start_time"])
        duration = float(payload["duration"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        datetime.fromtimestamp(start + duration, tz=UTC) <= cutoff and payload.get("radiant_win") is not None
    )


def _latest_replay_capture(paths: ProjectPaths, match_id: int) -> ReplayCapture | None:
    root = paths.raw / "valve_replay" / "matches" / str(match_id)
    if not root.is_dir():
        return None
    for metadata_path in sorted(root.glob("*/metadata.json"), reverse=True):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            body_path = metadata_path.with_name(str(metadata["file_name"]))
            expected_hash = str(metadata["content_sha256"])
            fetched_at = as_utc(metadata["fetched_at"])
            replay_url = str(metadata["request"]["url"])
            byte_count = int(metadata["bytes"])
            request_attempts = int(metadata.get("request_attempts", 1))
            retry_history = tuple(metadata.get("retry_history") or [])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if fetched_at is None or not body_path.is_file() or body_path.stat().st_size != byte_count:
            continue
        if sha256_file(body_path) != expected_hash:
            continue
        return ReplayCapture(
            body_path=body_path,
            content_sha256=expected_hash,
            byte_count=byte_count,
            fetched_at=fetched_at,
            replay_url=replay_url,
            request_attempts=request_attempts,
            retry_history=retry_history,
        )
    return None


def _persist_replay_capture(
    paths: ProjectPaths,
    *,
    match_id: int,
    replay_url: str,
    content: bytes,
    fetched_at: datetime,
    response_status: int,
    content_type: str | None,
    request_attempts: int,
    retry_history: list[dict[str, Any]],
    replay_salt: int | None = None,
    replay_cluster: int | None = None,
) -> ReplayCapture:
    content_hash = sha256_bytes(content)
    fetched_utc = as_utc(fetched_at)
    if fetched_utc is None:
        raise ValueError("fetched_at is required")
    capture_slug = f"{timestamp_slug(fetched_utc)}{fetched_utc.microsecond:06d}"
    folder = paths.raw / "valve_replay" / "matches" / str(match_id) / f"{capture_slug}-{content_hash[:12]}"
    if content.startswith(b"BZh"):
        file_name = "response.dem.bz2"
    elif content.startswith(b"\x28\xb5\x2f\xfd"):
        file_name = "response.dem.zst"
    else:
        file_name = "response.dem"
    body_path = folder / file_name
    metadata_path = folder / "metadata.json"
    if folder.exists():
        try:
            persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
            persisted_fetched_at = as_utc(persisted["fetched_at"])
            persisted_url = str(persisted["request"]["url"])
            persisted_attempts = int(persisted.get("request_attempts", 1))
            persisted_history = tuple(persisted.get("retry_history") or [])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            persisted_fetched_at = None
            persisted_url = ""
            persisted_attempts = 0
            persisted_history = ()
        if (
            body_path.is_file()
            and sha256_file(body_path) == content_hash
            and persisted_fetched_at is not None
            and persisted_url == replay_url
        ):
            return ReplayCapture(
                body_path=body_path,
                content_sha256=content_hash,
                byte_count=len(content),
                fetched_at=persisted_fetched_at,
                replay_url=persisted_url,
                request_attempts=persisted_attempts,
                retry_history=persisted_history,
            )
        raise FileExistsError(f"immutable replay capture collision: {folder}")
    folder.mkdir(parents=True, exist_ok=False)
    body_path.write_bytes(content)
    metadata = {
        "source": "valve_replay",
        "resource": f"matches/{match_id}",
        "request": {
            "method": "GET",
            "url": replay_url,
            "match_id": match_id,
            "replay_salt": replay_salt,
            "cluster": replay_cluster,
        },
        "response_status": response_status,
        "content_type": content_type,
        "fetched_at": fetched_utc.isoformat().replace("+00:00", "Z"),
        "content_sha256": content_hash,
        "bytes": len(content),
        "file_name": file_name,
        "request_attempts": request_attempts,
        "retry_history": retry_history,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ReplayCapture(
        body_path=body_path,
        content_sha256=content_hash,
        byte_count=len(content),
        fetched_at=fetched_utc,
        replay_url=replay_url,
        request_attempts=request_attempts,
        retry_history=tuple(retry_history),
    )


def _download_replay(
    paths: ProjectPaths,
    *,
    match_id: int,
    replay_url: str,
    client: Any,
    refresh: bool,
    replay_salt: int | None = None,
    replay_cluster: int | None = None,
    max_attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> ReplayCapture:
    if not refresh:
        existing = _latest_replay_capture(paths, match_id)
        if existing is not None and existing.replay_url == replay_url:
            return existing
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    history: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        attempted_at = utc_now()
        try:
            response = client.get(replay_url)
        except Exception as error:
            history.append(
                {
                    "attempt": attempt,
                    "attempted_at": attempted_at.isoformat().replace("+00:00", "Z"),
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            if attempt == max_attempts:
                raise ReplayProcessingError(
                    "download_failed",
                    f"replay request failed after {attempt} attempts: {error}",
                    request_attempts=attempt,
                    retry_history=history,
                ) from error
            sleeper(0.25 * (2 ** (attempt - 1)))
            continue

        status_code = int(response.status_code)
        history.append(
            {
                "attempt": attempt,
                "attempted_at": attempted_at.isoformat().replace("+00:00", "Z"),
                "http_status": status_code,
            }
        )
        if status_code in {404, 410}:
            raise ReplayProcessingError(
                "missing",
                f"replay returned HTTP {status_code}",
                request_attempts=attempt,
                retry_history=history,
            )
        if status_code != 200:
            if status_code in {429, 500, 502, 503, 504} and attempt < max_attempts:
                sleeper(0.25 * (2 ** (attempt - 1)))
                continue
            raise ReplayProcessingError(
                "download_failed",
                f"replay returned HTTP {status_code}",
                request_attempts=attempt,
                retry_history=history,
            )
        content = bytes(response.content)
        if not content:
            raise ReplayProcessingError(
                "download_failed",
                "replay response was empty",
                request_attempts=attempt,
                retry_history=history,
            )
        return _persist_replay_capture(
            paths,
            match_id=match_id,
            replay_url=replay_url,
            content=content,
            fetched_at=utc_now(),
            response_status=status_code,
            content_type=response.headers.get("content-type"),
            request_attempts=attempt,
            retry_history=history,
            replay_salt=replay_salt,
            replay_cluster=replay_cluster,
        )
    raise AssertionError("bounded replay download loop did not return")


def _decompress_replay(capture: ReplayCapture, paths: ProjectPaths) -> tuple[Path, str, int, str]:
    paths.cache.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix="fantasy-replay-", suffix=".dem", dir=paths.cache, delete=False
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        with capture.body_path.open("rb") as header:
            magic = header.read(4)
        if magic[:3] == b"BZh":
            source = bz2.open(capture.body_path, "rb")
            compression = "bz2"
        elif magic == b"\x28\xb5\x2f\xfd":
            compressed = capture.body_path.open("rb")
            source = zstd.ZstdDecompressor().stream_reader(compressed)
            compression = "zstd"
        else:
            source = capture.body_path.open("rb")
            compression = "none"
        with source, temporary_path.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        byte_count = temporary_path.stat().st_size
        if byte_count == 0:
            raise ReplayProcessingError("decompress_failed", "decompressed replay was empty")
        return temporary_path, sha256_file(temporary_path), byte_count, compression
    except ReplayProcessingError:
        temporary_path.unlink(missing_ok=True)
        raise
    except (OSError, EOFError, zstd.ZstdError) as error:
        temporary_path.unlink(missing_ok=True)
        raise ReplayProcessingError("decompress_failed", f"replay decompression failed: {error}") from error


def _slot_accounts(payload: Mapping[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    for player in payload.get("players") or []:
        if not isinstance(player, dict):
            continue
        try:
            slot = int(player["player_slot"])
            account_id = int(player["account_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if slot in result or account_id <= 0:
            continue
        result[slot] = account_id
    return result


def extract_proxy_diagnostics(payload: Mapping[str, Any], *, as_of: datetime) -> list[dict[str, Any]]:
    def mapping_value(player: Mapping[str, Any], mapping: str, keys: tuple[str, ...]) -> float | None:
        values = player.get(mapping)
        if not isinstance(values, dict):
            return None
        found = [
            values[key]
            for key in keys
            if key in values and not isinstance(values[key], bool) and isinstance(values[key], (int, float))
        ]
        return float(sum(found)) if found else None

    rows: list[dict[str, Any]] = []
    for player in payload.get("players") or []:
        if not isinstance(player, dict) or not player.get("account_id"):
            continue
        rows.append(
            {
                "match_id": int(payload["match_id"]),
                "account_id": int(player["account_id"]),
                "player_slot": int(player.get("player_slot", 0)),
                "madstone_collected_proxy": mapping_value(
                    player, "item_uses", ("madstone_bundle", "item_madstone_bundle")
                ),
                "smokes_used_proxy": mapping_value(
                    player, "item_uses", ("smoke_of_deceit", "item_smoke_of_deceit")
                ),
                "watchers_taken_proxy": mapping_value(player, "ability_uses", ("ability_lamp_use",)),
                "lotuses_gained_proxy": mapping_value(
                    player,
                    "item_uses",
                    (
                        "famango",
                        "great_famango",
                        "greater_famango",
                        "item_famango",
                        "item_great_famango",
                        "item_greater_famango",
                    ),
                ),
                "tormentor_kills_proxy": mapping_value(player, "killed", ("npc_dota_miniboss",)),
                "as_of": as_of,
            }
        )
    return rows


def _process_match(
    match_id: int,
    *,
    as_of: datetime,
    paths: ProjectPaths,
    parser: ReplayParserProtocol,
    client: Any,
    refresh: bool,
) -> MatchReplayResult:
    fetched_at = utc_now()
    source_hash: str | None = None
    replay_url: str | None = None
    replay_salt: int | None = None
    replay_cluster: int | None = None
    proxy_rows: list[dict[str, Any]] = []
    capture: ReplayCapture | None = None
    replay_sha256: str | None = None
    decompressed_bytes: int | None = None
    compression: str | None = None
    try:
        raw_capture = _latest_raw_match_capture(paths, match_id)
        if raw_capture is None:
            raise ReplayProcessingError("missing", "OpenDota match capture is missing")
        payload, _, source_hash = raw_capture
        try:
            source_match_id = int(payload["match_id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ReplayProcessingError("join_failed", "match capture has no valid match ID") from error
        if source_match_id != match_id:
            raise ReplayProcessingError(
                "join_failed",
                f"match capture identity {source_match_id} does not match requested {match_id}",
            )
        if not _completed_by(payload, as_of):
            raise ReplayProcessingError("missing", "match was not completed by as_of")
        proxy_rows = extract_proxy_diagnostics(payload, as_of=as_of)
        if not isinstance(payload.get("players"), list) or len(payload["players"]) != 10:
            raise ReplayProcessingError("join_failed", "match does not contain exactly ten players")
        accounts = _slot_accounts(payload)
        expected_slots = {*range(5), *range(128, 133)}
        if set(accounts) != expected_slots or len(set(accounts.values())) != 10:
            raise ReplayProcessingError("join_failed", "match does not have ten stable slot identities")
        replay_url = _replay_url(payload)
        if replay_url is None:
            raise ReplayProcessingError("missing", "match has no replay URL or replay salt")
        official_match_id = _official_replay_match_id(replay_url)
        if official_match_id is not None and official_match_id != match_id:
            raise ReplayProcessingError(
                "join_failed",
                f"official replay URL identity {official_match_id} does not match requested {match_id}",
            )
        replay_salt, replay_cluster = _replay_coordinates(payload, replay_url)
        capture = _download_replay(
            paths,
            match_id=match_id,
            replay_url=replay_url,
            client=client,
            refresh=refresh,
            replay_salt=replay_salt,
            replay_cluster=replay_cluster,
        )
        replay_path, replay_sha256, decompressed_bytes, compression = _decompress_replay(capture, paths)
        try:
            parser_payload = parser.parse(replay_path, expected_sha256=replay_sha256)
        finally:
            replay_path.unlink(missing_ok=True)
        DataStore(paths).write_raw_json(
            source="replay_parser",
            resource=f"matches/{match_id}",
            payload=parser_payload,
            request={
                "match_id": match_id,
                "replay_url": replay_url,
                "replay_salt": replay_salt,
                "replay_cluster": replay_cluster,
                "compressed_sha256": capture.content_sha256,
                "decompressed_sha256": replay_sha256,
                "parser_version": parser.version,
                "as_of": as_of.isoformat(),
            },
        )
        native_rows: list[dict[str, Any]] = []
        complete = True
        for parser_row in parser_payload["players"]:
            slot = int(parser_row["playerSlot"])
            account_id = accounts.get(slot)
            if account_id is None:
                raise ReplayProcessingError("join_failed", f"parser slot {slot} has no account identity")
            row: dict[str, Any] = {
                "match_id": match_id,
                "account_id": account_id,
                "player_slot": slot,
                "team": parser_row["team"],
                "team_slot": int(parser_row["teamSlot"]),
                "entity_present": bool(parser_row["entityPresent"]),
                "parser_version": parser_payload["parserVersion"],
                "parser_jar_sha256": parser_payload.get("parserJarSha256"),
                "engine": parser_payload.get("engine"),
                "build_number": parser_payload.get("buildNumber"),
                "game_version": parser_payload.get("gameVersion"),
                "last_tick": parser_payload.get("lastTick"),
                "schema_fingerprint": parser_payload["schemaFingerprint"],
                "compressed_sha256": capture.content_sha256,
                "compressed_bytes": capture.byte_count,
                "decompressed_sha256": replay_sha256,
                "decompressed_bytes": decompressed_bytes,
                "compression": compression,
                "opendota_source_sha256": source_hash,
                "replay_salt": replay_salt,
                "replay_cluster": replay_cluster,
                "fetched_at": capture.fetched_at,
                "as_of": as_of,
            }
            for stat_id in NATIVE_FANTASY_FIELDS:
                observation = parser_row["stats"][stat_id]
                row[stat_id] = observation["value"]
                row[f"{stat_id}_schema_present"] = bool(observation["schemaPresent"])
                row[f"{stat_id}_observed"] = bool(observation["observed"])
                if not (
                    parser_row["entityPresent"]
                    and observation["schemaPresent"]
                    and observation["observed"]
                    and observation["value"] is not None
                ):
                    complete = False
            native_rows.append(row)
        if len(native_rows) != 10:
            raise ReplayProcessingError("parse_failed", "parser result did not join to ten players")
        status = "exact" if complete else "parse_failed"
        status_row = _status_row(
            match_id,
            status=status,
            as_of=as_of,
            fetched_at=capture.fetched_at,
            source_hash=source_hash,
            replay_url=replay_url,
            replay_salt=replay_salt,
            replay_cluster=replay_cluster,
            error=None if complete else "one or more native fields were not observed",
            parser_payload=parser_payload,
            compressed_sha256=capture.content_sha256,
            decompressed_sha256=replay_sha256,
            compressed_bytes=capture.byte_count,
            decompressed_bytes=decompressed_bytes,
            compression=compression,
            request_attempts=capture.request_attempts,
            retry_history=list(capture.retry_history),
        )
        return MatchReplayResult(status_row, native_rows, proxy_rows)
    except ReplayProcessingError as error:
        return MatchReplayResult(
            _status_row(
                match_id,
                status=error.status,
                as_of=as_of,
                fetched_at=capture.fetched_at if capture is not None else fetched_at,
                source_hash=source_hash,
                replay_url=replay_url,
                replay_salt=replay_salt,
                replay_cluster=replay_cluster,
                error=str(error),
                compressed_sha256=capture.content_sha256 if capture is not None else None,
                decompressed_sha256=replay_sha256,
                compressed_bytes=capture.byte_count if capture is not None else None,
                decompressed_bytes=decompressed_bytes,
                compression=compression,
                request_attempts=(
                    capture.request_attempts if capture is not None else error.request_attempts
                ),
                retry_history=(list(capture.retry_history) if capture is not None else error.retry_history),
            ),
            proxy_rows=proxy_rows,
        )
    except Exception as error:  # defensive phase boundary: report and continue the backfill
        return MatchReplayResult(
            _status_row(
                match_id,
                status="parse_failed",
                as_of=as_of,
                fetched_at=capture.fetched_at if capture is not None else fetched_at,
                source_hash=source_hash,
                replay_url=replay_url,
                replay_salt=replay_salt,
                replay_cluster=replay_cluster,
                error=f"unexpected {type(error).__name__}: {error}",
                compressed_sha256=capture.content_sha256 if capture is not None else None,
                decompressed_sha256=replay_sha256,
                compressed_bytes=capture.byte_count if capture is not None else None,
                decompressed_bytes=decompressed_bytes,
                compression=compression,
                request_attempts=capture.request_attempts if capture is not None else None,
                retry_history=list(capture.retry_history) if capture is not None else None,
            ),
            proxy_rows=proxy_rows,
        )


def _status_row(
    match_id: int,
    *,
    status: str,
    as_of: datetime,
    fetched_at: datetime,
    source_hash: str | None,
    replay_url: str | None,
    replay_salt: int | None,
    replay_cluster: int | None,
    error: str | None,
    parser_payload: Mapping[str, Any] | None = None,
    compressed_sha256: str | None = None,
    decompressed_sha256: str | None = None,
    compressed_bytes: int | None = None,
    decompressed_bytes: int | None = None,
    compression: str | None = None,
    request_attempts: int | None = None,
    retry_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if status not in ALL_REPLAY_STATUSES:
        raise ValueError(f"invalid replay status: {status}")
    parser_payload = parser_payload or {}
    return {
        "match_id": match_id,
        "status": status,
        "parser_version": parser_payload.get("parserVersion"),
        "parser_jar_sha256": parser_payload.get("parserJarSha256"),
        "engine": parser_payload.get("engine"),
        "build_number": parser_payload.get("buildNumber"),
        "game_version": parser_payload.get("gameVersion"),
        "schema_fingerprint": parser_payload.get("schemaFingerprint"),
        "compressed_sha256": compressed_sha256,
        "decompressed_sha256": decompressed_sha256,
        "opendota_source_sha256": source_hash,
        "replay_url": replay_url,
        "replay_salt": replay_salt,
        "replay_cluster": replay_cluster,
        "request_attempts": request_attempts,
        "retry_history_json": canonical_json(retry_history or []).decode("utf-8"),
        "compressed_bytes": compressed_bytes,
        "decompressed_bytes": decompressed_bytes,
        "compression": compression,
        "fetched_at": fetched_at,
        "as_of": as_of,
        "error": error,
    }


def _merge_frames(existing: pd.DataFrame, incoming: list[dict[str, Any]], keys: list[str]) -> pd.DataFrame:
    new = pd.DataFrame(incoming)
    if new.empty:
        combined = existing.copy()
    elif existing.empty:
        combined = new
    else:
        incoming_columns = list(new.columns)
        combined = pd.concat([existing, new.dropna(axis=1, how="all")], ignore_index=True)
        for column in incoming_columns:
            if column not in combined:
                combined[column] = None
    if not combined.empty:
        combined = combined.drop_duplicates(subset=keys, keep="last").sort_values(keys).reset_index(drop=True)
    return combined


def _write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def enrich_replay_status_audit(
    statuses: pd.DataFrame,
    native: pd.DataFrame,
    *,
    paths: ProjectPaths,
) -> pd.DataFrame:
    """Migrate older status rows to the complete P1 audit contract without replay re-parsing."""

    columns = list(dict.fromkeys([*statuses.columns, *REPLAY_STATUS_COLUMNS]))
    output = statuses.reindex(columns=columns).copy()
    if output.empty:
        return output

    native_columns = (
        "compressed_sha256",
        "decompressed_sha256",
        "compressed_bytes",
        "decompressed_bytes",
        "compression",
        "replay_salt",
        "replay_cluster",
    )
    available_native = [column for column in native_columns if column in native]
    if not native.empty and available_native:
        audit = native[["match_id", *available_native]].drop_duplicates("match_id", keep="last")
        audit = audit.rename(columns={column: f"{column}_audit" for column in available_native})
        output = output.merge(audit, on="match_id", how="left")
        for column in available_native:
            audit_column = f"{column}_audit"
            output[column] = output[column].where(output[column].notna(), output[audit_column])
        output = output.drop(columns=[f"{column}_audit" for column in available_native])

    coordinate_missing = output["replay_salt"].isna() | output["replay_cluster"].isna()
    for index, match_id in output.loc[coordinate_missing, "match_id"].items():
        if pd.isna(match_id):
            continue
        raw = _latest_raw_match_capture(paths, int(match_id))
        payload = raw[0] if raw is not None else {"match_id": int(match_id)}
        replay_url = output.at[index, "replay_url"]
        salt, cluster = _replay_coordinates(
            payload,
            str(replay_url) if replay_url is not None and not pd.isna(replay_url) else None,
        )
        if output.at[index, "replay_salt"] is None or pd.isna(output.at[index, "replay_salt"]):
            output.at[index, "replay_salt"] = salt
        if output.at[index, "replay_cluster"] is None or pd.isna(output.at[index, "replay_cluster"]):
            output.at[index, "replay_cluster"] = cluster

    return output.sort_values("match_id").reset_index(drop=True)


def enrich_native_replay_coordinates(
    native: pd.DataFrame,
    statuses: pd.DataFrame,
) -> pd.DataFrame:
    """Fill legacy native-row replay coordinates from the keyed status audit."""

    columns = list(dict.fromkeys([*native.columns, *NATIVE_TABLE_COLUMNS]))
    output = native.reindex(columns=columns).copy()
    if output.empty or statuses.empty:
        return output
    coordinate_columns = [column for column in ("replay_salt", "replay_cluster") if column in statuses]
    if not coordinate_columns:
        return output
    audit = statuses[["match_id", *coordinate_columns]].drop_duplicates("match_id", keep="last")
    audit = audit.rename(columns={column: f"{column}_audit" for column in coordinate_columns})
    output = output.merge(audit, on="match_id", how="left")
    for column in coordinate_columns:
        audit_column = f"{column}_audit"
        output[column] = output[column].where(output[column].notna(), output[audit_column])
    output = output.drop(columns=[f"{column}_audit" for column in coordinate_columns])
    return output.sort_values(["match_id", "account_id"]).reset_index(drop=True)


WATCHER_SUPPORT_COLUMNS = (
    "build_number",
    "game_version",
    "schema_fingerprint",
    "match_count",
    "player_row_count",
    "complete_fixture_matches",
    "nonzero_fixture_matches",
    "watcher_nonzero_rows",
    "status",
)


def build_watcher_support(native: pd.DataFrame) -> pd.DataFrame:
    required = {
        "match_id",
        "build_number",
        "game_version",
        "schema_fingerprint",
        "parser_version",
        "entity_present",
        "watchers_taken",
        "watchers_taken_schema_present",
        "watchers_taken_observed",
    }
    if native.empty or not required <= set(native.columns):
        return pd.DataFrame(columns=WATCHER_SUPPORT_COLUMNS)
    native = native.loc[native["parser_version"].eq(NATIVE_PARSER_VERSION)].copy()
    if native.empty:
        return pd.DataFrame(columns=WATCHER_SUPPORT_COLUMNS)
    rows: list[dict[str, Any]] = []
    keys = ["build_number", "game_version", "schema_fingerprint"]
    for key, group in native.dropna(subset=keys).groupby(keys, sort=True):
        complete_fixtures = 0
        nonzero_fixtures = 0
        for _, match in group.groupby("match_id", sort=True):
            complete = (
                len(match) == 10
                and match["entity_present"].astype("boolean").fillna(False).all()
                and match["watchers_taken_schema_present"].astype("boolean").fillna(False).all()
                and match["watchers_taken_observed"].astype("boolean").fillna(False).all()
                and pd.to_numeric(match["watchers_taken"], errors="coerce").notna().all()
            )
            if complete:
                complete_fixtures += 1
                if pd.to_numeric(match["watchers_taken"], errors="coerce").gt(0).any():
                    nonzero_fixtures += 1
        nonzero_rows = int(pd.to_numeric(group["watchers_taken"], errors="coerce").fillna(0).gt(0).sum())
        rows.append(
            {
                "build_number": int(key[0]),
                "game_version": int(key[1]),
                "schema_fingerprint": str(key[2]),
                "match_count": int(group["match_id"].nunique()),
                "player_row_count": len(group),
                "complete_fixture_matches": complete_fixtures,
                "nonzero_fixture_matches": nonzero_fixtures,
                "watcher_nonzero_rows": nonzero_rows,
                "status": "admitted" if nonzero_fixtures else "build_untrusted",
            }
        )
    return pd.DataFrame(rows, columns=WATCHER_SUPPORT_COLUMNS).sort_values(keys).reset_index(drop=True)


def watcher_trusted_cohorts(native: pd.DataFrame) -> set[tuple[int, int, str]]:
    support = build_watcher_support(native)
    if support.empty:
        return set()
    return {
        (int(row["build_number"]), int(row["game_version"]), str(row["schema_fingerprint"]))
        for row in support.loc[support["status"].eq("admitted")].to_dict(orient="records")
    }


def overlay_native_fantasy_stats(
    samples: pd.DataFrame,
    *,
    native: pd.DataFrame | None = None,
    paths: ProjectPaths = PATHS,
) -> pd.DataFrame:
    if samples.empty:
        return samples.copy()
    output = samples.copy()
    for stat_id in NATIVE_FANTASY_FIELDS:
        output[stat_id] = None
        output[f"{stat_id}_provenance"] = "unavailable"
    for column in (
        "native_replay_sha256",
        "native_stats_source_sha256",
        "native_parser_version",
        "native_schema_fingerprint",
        "native_build_number",
        "native_game_version",
    ):
        output[column] = None

    native_frame = (
        native.copy()
        if native is not None
        else read_parquet_if_exists(paths.processed / "fantasy_native_stats.parquet")
    )
    if native_frame.empty:
        return output.sort_values(["match_id", "account_id"]).reset_index(drop=True)
    required_native_columns = {
        "match_id",
        "account_id",
        "entity_present",
        "decompressed_sha256",
        "compressed_sha256",
        "parser_version",
        "schema_fingerprint",
        "build_number",
        "game_version",
        *(
            column
            for stat_id in NATIVE_FANTASY_FIELDS
            for column in (stat_id, f"{stat_id}_observed", f"{stat_id}_schema_present")
        ),
    }
    if not required_native_columns <= set(native_frame.columns):
        return output.sort_values(["match_id", "account_id"]).reset_index(drop=True)
    trusted = watcher_trusted_cohorts(native_frame)
    native_frame["_watcher_trusted"] = [
        (int(build), int(game), str(schema)) in trusted
        if pd.notna(build) and pd.notna(game) and pd.notna(schema)
        else False
        for build, game, schema in zip(
            native_frame["build_number"],
            native_frame["game_version"],
            native_frame["schema_fingerprint"],
            strict=True,
        )
    ]
    columns = ["match_id", "account_id", "entity_present", "_watcher_trusted"]
    columns.extend(
        [
            "decompressed_sha256",
            "compressed_sha256",
            "parser_version",
            "schema_fingerprint",
            "build_number",
            "game_version",
        ]
    )
    for stat_id in NATIVE_FANTASY_FIELDS:
        columns.extend((stat_id, f"{stat_id}_observed", f"{stat_id}_schema_present"))
    overlay = native_frame[columns].drop_duplicates(["match_id", "account_id"], keep="last")
    merged = output.merge(overlay, on=["match_id", "account_id"], how="left", suffixes=("", "_native"))
    native_valid = (
        merged["entity_present"].astype("boolean").fillna(False).astype(bool)
        & merged["parser_version"].eq(NATIVE_PARSER_VERSION)
        & merged["compressed_sha256"].notna()
        & merged["decompressed_sha256"].notna()
    )
    for stat_id in NATIVE_FANTASY_FIELDS:
        native_value = f"{stat_id}_native"
        observed = merged[f"{stat_id}_observed"].astype("boolean").fillna(False).astype(bool)
        schema_present = merged[f"{stat_id}_schema_present"].astype("boolean").fillna(False).astype(bool)
        exact = native_valid & observed & schema_present & merged[native_value].notna()
        if stat_id == "watchers_taken":
            exact &= merged["_watcher_trusted"].astype("boolean").fillna(False).astype(bool)
        merged.loc[exact, stat_id] = merged.loc[exact, native_value]
        merged.loc[exact, f"{stat_id}_provenance"] = "exact"
    merged["native_replay_sha256"] = merged["decompressed_sha256"]
    merged["native_stats_source_sha256"] = merged["compressed_sha256"]
    merged["native_parser_version"] = merged["parser_version"]
    merged["native_schema_fingerprint"] = merged["schema_fingerprint"]
    merged["native_build_number"] = merged["build_number"]
    merged["native_game_version"] = merged["game_version"]
    drop_columns = [column for column in merged.columns if column.endswith("_native")]
    drop_columns.extend(
        [
            "_watcher_trusted",
            "entity_present",
            "decompressed_sha256",
            "compressed_sha256",
            "parser_version",
            "schema_fingerprint",
            "build_number",
            "game_version",
        ]
    )
    for stat_id in NATIVE_FANTASY_FIELDS:
        drop_columns.extend((f"{stat_id}_observed", f"{stat_id}_schema_present"))
    merged = merged.drop(columns=list(dict.fromkeys(drop_columns)), errors="ignore")
    return merged.sort_values(["match_id", "account_id"]).reset_index(drop=True)


def _content_hash(frame: pd.DataFrame) -> str:
    preferred_keys = (
        "match_id",
        "account_id",
        "player_slot",
        "build_number",
        "game_version",
        "schema_fingerprint",
        "status",
    )
    keys = [column for column in preferred_keys if column in frame]
    records = (
        frame.sort_values(keys, kind="mergesort", na_position="last").to_dict(orient="records")
        if not frame.empty
        else []
    )
    return sha256_bytes(canonical_json(records))


def sync_replay_fantasy_history(
    *,
    as_of: datetime,
    year: int | None = None,
    workers: int = 4,
    max_matches: int | None = None,
    match_ids: list[int] | None = None,
    checkpoint_every: int = 1,
    refresh: bool = False,
    parser: ReplayParserProtocol | None = None,
    client: Any | None = None,
    paths: ProjectPaths = PATHS,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> ReplayFantasySyncResult:
    cutoff = as_utc(as_of)
    if cutoff is None:
        raise ValueError("as_of is required")
    selected_year = year or cutoff.year
    if workers < 1:
        raise ValueError("workers must be positive")
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every must be positive")
    if max_matches is not None and max_matches < 1:
        raise ValueError("max_matches must be positive")
    scope_path = paths.processed / "fantasy_player_history_scope.parquet"
    scope = read_parquet_if_exists(scope_path)
    if scope.empty or not {"match_id", "start_time"} <= set(scope.columns):
        raise ValueError("Fantasy player history scope is missing; run data fantasy-history first")
    starts = pd.to_datetime(scope["start_time"], utc=True)
    selected = scope.loc[(starts.dt.year == selected_year) & (starts <= cutoff)]
    scoped_match_ids = sorted(int(value) for value in selected["match_id"].dropna().unique())
    if match_ids is not None:
        requested_ids = {int(value) for value in match_ids}
        outside_scope = requested_ids - set(scoped_match_ids)
        if outside_scope:
            raise ValueError(f"requested match IDs are outside the selected scope: {sorted(outside_scope)}")
        target_ids = sorted(requested_ids)
    else:
        target_ids = scoped_match_ids
    native_path = paths.processed / "fantasy_native_stats.parquet"
    status_path = paths.processed / "fantasy_replay_status.parquet"
    diagnostics_path = paths.processed / "fantasy_proxy_diagnostics.parquet"
    watcher_support_path = paths.processed / "fantasy_watcher_support.parquet"
    samples_path = paths.processed / "fantasy_performance_samples.parquet"
    native = read_parquet_if_exists(native_path)
    statuses = read_parquet_if_exists(status_path)
    diagnostics = read_parquet_if_exists(diagnostics_path)
    samples = read_parquet_if_exists(samples_path)
    if not len(native.columns):
        native = pd.DataFrame(columns=NATIVE_TABLE_COLUMNS)
    if not len(statuses.columns):
        statuses = pd.DataFrame(columns=REPLAY_STATUS_COLUMNS)
    if not len(diagnostics.columns):
        diagnostics = pd.DataFrame(columns=PROXY_DIAGNOSTIC_COLUMNS)
    enriched_statuses = enrich_replay_status_audit(statuses, native, paths=paths)
    status_audit_changed = not statuses.equals(enriched_statuses)
    statuses = enriched_statuses
    enriched_native = enrich_native_replay_coordinates(native, statuses)
    native_audit_changed = not native.equals(enriched_native)
    native = enriched_native
    parser_impl = parser or ReplayParser(
        jar_path=paths.root / "src" / "ti_replay_parser" / "target" / "ti-replay-parser.jar"
    )

    native_complete_ids: set[int] = set()
    if not native.empty and {"match_id", "account_id"} <= set(native.columns):
        native_counts = native.groupby("match_id")["account_id"].nunique()
        native_complete_ids = {int(value) for value in native_counts.loc[native_counts.eq(10)].index}
    reusable: set[int] = set()
    if not refresh and not statuses.empty and {"match_id", "status", "parser_version"} <= set(statuses):
        reusable_status = statuses["status"].isin(FINAL_REPLAY_STATUSES)
        reusable_version = statuses["parser_version"].eq(parser_impl.version)
        parser_artifact_sha256 = getattr(parser_impl, "artifact_sha256", None)
        reusable_artifact = (
            statuses["parser_jar_sha256"].eq(parser_artifact_sha256)
            if parser_artifact_sha256 is not None and "parser_jar_sha256" in statuses
            else pd.Series(True, index=statuses.index)
        )
        reusable = {
            int(value)
            for value in statuses.loc[reusable_status & reusable_version & reusable_artifact, "match_id"]
            .dropna()
            .unique()
            if int(value) in native_complete_ids
        }
    pending = [match_id for match_id in target_ids if match_id not in reusable]
    if max_matches is not None:
        pending = pending[:max_matches]
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(120.0, connect=20.0),
        headers={"User-Agent": "ti-predictor/0.1 native-fantasy-replay"},
    )
    attempted = 0
    new_native: list[dict[str, Any]] = []
    new_statuses: list[dict[str, Any]] = []
    new_diagnostics: list[dict[str, Any]] = []

    watcher_support = build_watcher_support(native)

    def checkpoint() -> None:
        nonlocal native, statuses, diagnostics, samples, watcher_support
        nonlocal new_native, new_statuses, new_diagnostics
        nonlocal native_audit_changed, status_audit_changed
        native = _merge_frames(native, new_native, ["match_id", "account_id"])
        statuses = _merge_frames(statuses, new_statuses, ["match_id"])
        diagnostics = _merge_frames(diagnostics, new_diagnostics, ["match_id", "account_id"])
        new_native = []
        new_statuses = []
        new_diagnostics = []
        if not native.empty:
            watcher_support = build_watcher_support(native)
            trusted = {
                (
                    int(row["build_number"]),
                    int(row["game_version"]),
                    str(row["schema_fingerprint"]),
                )
                for row in watcher_support.loc[watcher_support["status"].eq("admitted")].to_dict(
                    orient="records"
                )
            }
            trusted_rows = [
                (
                    int(row["build_number"]),
                    int(row["game_version"]),
                    str(row["schema_fingerprint"]),
                )
                in trusted
                if pd.notna(row.get("build_number"))
                and pd.notna(row.get("game_version"))
                and pd.notna(row.get("schema_fingerprint"))
                else False
                for row in native.to_dict(orient="records")
            ]
            native["watcher_cohort_trusted"] = trusted_rows
            if not statuses.empty:
                trusted_matches = set(
                    int(value) for value in native.loc[native["watcher_cohort_trusted"], "match_id"].unique()
                )
                parsed_matches = set(int(value) for value in native["match_id"].unique())
                eligible = statuses["status"].isin(FINAL_REPLAY_STATUSES) & statuses["match_id"].isin(
                    parsed_matches
                )
                statuses.loc[eligible, "status"] = "build_untrusted"
                statuses.loc[eligible, "error"] = "Watcher cohort has no complete ten-player non-zero fixture"
                trusted_status = eligible & statuses["match_id"].isin(trusted_matches)
                statuses.loc[trusted_status, "status"] = "exact"
                statuses.loc[trusted_status, "error"] = None
        samples = overlay_native_fantasy_stats(samples, native=native, paths=paths)
        _write_parquet_atomic(native, native_path)
        _write_parquet_atomic(statuses, status_path)
        _write_parquet_atomic(diagnostics, diagnostics_path)
        _write_parquet_atomic(watcher_support, watcher_support_path)
        _write_parquet_atomic(samples, samples_path)
        native_audit_changed = False
        status_audit_changed = False

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_match,
                    match_id,
                    as_of=cutoff,
                    paths=paths,
                    parser=parser_impl,
                    client=http_client,
                    refresh=refresh,
                ): match_id
                for match_id in pending
            }
            for future in as_completed(futures):
                result = future.result()
                attempted += 1
                new_statuses.append(result.status_row)
                new_native.extend(result.native_rows)
                new_diagnostics.extend(result.proxy_rows)
                if attempted % checkpoint_every == 0:
                    checkpoint()
                if progress is not None:
                    progress(
                        {
                            "phase": "replay_fantasy",
                            "processed": attempted,
                            "scheduled": len(pending),
                            "match_id": futures[future],
                            "status": result.status_row["status"],
                        }
                    )
    finally:
        if owns_client:
            http_client.close()
    if new_native or new_statuses or new_diagnostics:
        checkpoint()
    if status_audit_changed:
        _write_parquet_atomic(statuses, status_path)
    if native_audit_changed:
        _write_parquet_atomic(native, native_path)

    for frame, path in (
        (native, native_path),
        (statuses, status_path),
        (diagnostics, diagnostics_path),
        (watcher_support, watcher_support_path),
        (samples, samples_path),
    ):
        if not path.is_file():
            _write_parquet_atomic(frame, path)
    scoped_status = statuses.loc[statuses["match_id"].isin(target_ids)] if not statuses.empty else statuses
    counts = scoped_status["status"].value_counts().to_dict() if not scoped_status.empty else {}
    failures = sum(int(counts.get(status, 0)) for status in ALL_REPLAY_STATUSES - FINAL_REPLAY_STATUSES)
    trusted_count = len(watcher_trusted_cohorts(native))
    accounted_ids = (
        {int(value) for value in scoped_status["match_id"].dropna().unique()}
        if not scoped_status.empty
        else set()
    )
    remaining = len(set(target_ids) - accounted_ids)
    issues: list[AuditIssue] = []
    if failures:
        issues.append(
            AuditIssue(
                severity="warning",
                code="fantasy-replay-incomplete",
                message=f"{failures} scoped replays are not exact; inspect fantasy_replay_status.parquet",
            )
        )
    if counts.get("build_untrusted", 0):
        issues.append(
            AuditIssue(
                severity="warning",
                code="fantasy-watcher-build-untrusted",
                message=f"{counts['build_untrusted']} matches have an untrusted Watcher cohort",
            )
        )
    if remaining:
        issues.append(
            AuditIssue(
                severity="warning",
                code="fantasy-replay-not-attempted",
                message=f"{remaining} scoped replays do not yet have a replay status",
            )
        )
    DataStore(paths).refresh_duckdb(
        {
            "fantasy_native_stats": native_path,
            "fantasy_replay_status": status_path,
            "fantasy_proxy_diagnostics": diagnostics_path,
            "fantasy_watcher_support": watcher_support_path,
            "fantasy_performance_samples": samples_path,
        }
    )
    # Hash the persisted snapshot, not checkpoint-local frames whose pandas dtypes can differ from
    # the Parquet round trip after a migration or mixed historical/new batch.
    data_material = {
        "native": _content_hash(read_parquet_if_exists(native_path)),
        "status": _content_hash(read_parquet_if_exists(status_path)),
        "diagnostics": _content_hash(read_parquet_if_exists(diagnostics_path)),
        "watcher_support": _content_hash(read_parquet_if_exists(watcher_support_path)),
        "samples": _content_hash(read_parquet_if_exists(samples_path)),
    }
    return ReplayFantasySyncResult(
        native_stats_path=native_path,
        replay_status_path=status_path,
        proxy_diagnostics_path=diagnostics_path,
        watcher_support_path=watcher_support_path,
        fantasy_samples_path=samples_path,
        target_matches=len(target_ids),
        attempted_matches=attempted,
        reused_matches=len(set(target_ids) & reusable),
        remaining_matches=remaining,
        exact_matches=int(counts.get("exact", 0)),
        build_untrusted_matches=int(counts.get("build_untrusted", 0)),
        failed_matches=failures,
        watcher_trusted_cohorts=trusted_count,
        data_sha256=sha256_bytes(canonical_json(data_material)),
        issues=issues,
    )
