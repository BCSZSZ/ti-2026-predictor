"""Local-only Dota window observation and structured Group Roll OCR."""

from __future__ import annotations

import copy
import ctypes
import json
import re
import sys
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol

from ti_predictor.fantasy.roll import (
    BannerState,
    EmblemState,
    GroupRollState,
    RollOffer,
    RollRuleSet,
    validate_group_state,
)
from ti_predictor.hashing import sha256_bytes
from ti_predictor.paths import PATHS

Box = tuple[float, float, float, float]
ObservationStatus = Literal["not_target", "incomplete", "confirmed", "error"]
FieldStatus = Literal["confirmed", "low_confidence", "missing", "conflict"]


class ScreenCaptureError(RuntimeError):
    """The local Dota window could not be observed safely."""


@dataclass(frozen=True)
class OCRToken:
    text: str
    confidence: float
    box: Box

    @property
    def center_x(self) -> float:
        return (self.box[0] + self.box[2]) / 2.0

    @property
    def center_y(self) -> float:
        return (self.box[1] + self.box[3]) / 2.0


@dataclass(frozen=True)
class RollFieldReading:
    field_id: str
    value: str | int | None
    confidence: float
    status: FieldStatus
    evidence_text: str = ""
    evidence_box: Box | None = None
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value": self.value,
            "confidence": round(float(self.confidence), 6),
            "status": self.status,
            "evidence_text": self.evidence_text,
            "evidence_box": list(self.evidence_box) if self.evidence_box is not None else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RollScreenObservation:
    status: ObservationStatus
    captured_at: datetime
    image_sha256: str
    viewport: tuple[int, int]
    profile_id: str
    fields: tuple[RollFieldReading, ...] = ()
    warnings: tuple[str, ...] = ()
    state: GroupRollState | None = None

    @property
    def missing_field_ids(self) -> tuple[str, ...]:
        return tuple(field.field_id for field in self.fields if field.status != "confirmed")

    def to_payload(self) -> dict[str, Any]:
        state_payload = None
        if self.state is not None:
            state_payload = {
                "banners": [
                    {
                        "role": banner.role,
                        "emblems": [
                            {
                                "stat_id": emblem.stat_id,
                                "quality": emblem.quality_tier,
                                "trait": emblem.trait_id,
                            }
                            for emblem in banner.emblems
                        ],
                    }
                    for banner in self.state.banners
                ],
                "offer": list(self.state.offer.operation_ids),
                "remaining_rolls": self.state.remaining_rolls,
            }
        payload = {
            "status": self.status,
            "captured_at": self.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "image_sha256": self.image_sha256,
            "viewport": list(self.viewport),
            "profile_id": self.profile_id,
            "fields": [field.to_payload() for field in self.fields],
            "missing_field_ids": list(self.missing_field_ids),
            "warnings": list(self.warnings),
            "state": state_payload,
        }
        semantic = dict(payload)
        semantic.pop("captured_at")
        semantic.pop("image_sha256")
        payload["observation_sha256"] = sha256_bytes(
            json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        return payload


@dataclass(frozen=True)
class CapturedFrame:
    image: Any
    captured_at: datetime
    image_sha256: str
    window_title: str

    @property
    def viewport(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.image.size)


@dataclass(frozen=True)
class LiveOCRProfile:
    profile_id: str
    language_priority: tuple[str, ...]
    source: dict[str, str]
    capture: dict[str, float | int | str]
    recognition: dict[str, float | int]
    roles: dict[str, tuple[str, ...]]
    stats: dict[str, tuple[str, ...]]
    qualities: dict[int, tuple[str, ...]]
    traits: dict[str, tuple[str, ...]]
    target_anchors: tuple[str, ...]
    operations: dict[int, tuple[str, ...]]


def load_live_ocr_profile(
    path: Path = PATHS.config / "ocr" / "fantasy-group-roll-screen-v1.json",
) -> LiveOCRProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return LiveOCRProfile(
        profile_id=str(raw["profile_id"]),
        language_priority=tuple(str(value) for value in raw["language_priority"]),
        source={str(key): str(value) for key, value in raw["source"].items()},
        capture=dict(raw["capture"]),
        recognition=dict(raw["recognition"]),
        roles={key: tuple(values) for key, values in raw["roles"].items()},
        stats={key: tuple(values) for key, values in raw["stats"].items()},
        qualities={int(key): tuple(values) for key, values in raw["qualities"].items()},
        traits={key: tuple(values) for key, values in raw["traits"].items()},
        target_anchors=tuple(raw["target_anchors"]),
        operations={int(key): tuple(values) for key, values in raw["operations"].items()},
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def live_capture_supported() -> bool:
    """Return whether this process can use the Windows-only Dota window capture path."""

    return sys.platform == "win32"


def capture_dota_window(*, window_title: str = "Dota 2") -> CapturedFrame:
    if not live_capture_supported():
        raise ScreenCaptureError("实时窗口识别仅支持本机 Windows；手填顾问仍可使用。")
    try:
        from PIL import ImageGrab
    except ImportError as error:  # pragma: no cover - optional dependency
        raise ScreenCaptureError("缺少 Pillow；请运行 `uv sync --extra ocr`。") from error
    handle = int(ctypes.windll.user32.FindWindowW(None, window_title))
    if handle == 0:
        raise ScreenCaptureError(f"没有找到标题为 {window_title!r} 的 Dota 窗口。")
    try:
        image = ImageGrab.grab(window=handle).convert("RGB")
    except OSError as error:
        raise ScreenCaptureError(f"Dota 窗口捕获失败：{error}") from error
    if image.width < 800 or image.height < 600:
        raise ScreenCaptureError(f"Dota 窗口尺寸异常：{image.width}×{image.height}。")
    identity = (
        image.width.to_bytes(4, "little")
        + image.height.to_bytes(4, "little")
        + image.tobytes()
    )
    return CapturedFrame(
        image=image,
        captured_at=_utc_now(),
        image_sha256=sha256(identity).hexdigest(),
        window_title=window_title,
    )


def _signature(image: Any, *, width: int, height: int) -> bytes:
    return image.convert("L").resize((width, height)).tobytes()


def _mean_difference(left: bytes, right: bytes) -> float:
    if len(left) != len(right):
        return float("inf")
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / max(1, len(left))


@dataclass
class StableFrameGate:
    signature_width: int = 160
    signature_height: int = 90
    stable_frame_count: int = 2
    stable_mean_difference: float = 4.0
    meaningful_mean_difference: float = 1.25
    _candidate: bytes | None = field(default=None, init=False, repr=False)
    _candidate_count: int = field(default=0, init=False, repr=False)
    _accepted: bytes | None = field(default=None, init=False, repr=False)

    def reset(self) -> None:
        self._candidate = None
        self._candidate_count = 0
        self._accepted = None

    def observe(self, image: Any) -> Literal["unstable", "duplicate", "accepted"]:
        current = _signature(
            image,
            width=self.signature_width,
            height=self.signature_height,
        )
        if self._candidate is None:
            self._candidate = current
            self._candidate_count = 1
            return "unstable"
        if _mean_difference(self._candidate, current) <= self.stable_mean_difference:
            self._candidate_count += 1
        else:
            self._candidate_count = 1
        self._candidate = current
        if self._candidate_count < self.stable_frame_count:
            return "unstable"
        if (
            self._accepted is not None
            and _mean_difference(self._accepted, current) < self.meaningful_mean_difference
        ):
            return "duplicate"
        self._accepted = current
        return "accepted"


class TokenEngine(Protocol):
    def extract(self, image: Any, *, maximum_width: int) -> tuple[OCRToken, ...]: ...


class RapidOCRTokenEngine:
    def __init__(self) -> None:
        try:
            from rapidocr import RapidOCR
        except ImportError as error:  # pragma: no cover - optional dependency
            raise RuntimeError("OCR 依赖未安装；请运行 `uv sync --extra ocr`。") from error
        self._engine = RapidOCR()

    def extract(self, image: Any, *, maximum_width: int) -> tuple[OCRToken, ...]:
        try:
            import numpy as np
        except ImportError as error:  # pragma: no cover - core dependency in this project
            raise RuntimeError("OCR 需要 NumPy。") from error
        if image.width > maximum_width:
            ratio = maximum_width / image.width
            image = image.resize((maximum_width, max(1, round(image.height * ratio))))
        output = self._engine(np.asarray(image))
        texts = list(getattr(output, "txts", []) or [])
        scores = list(getattr(output, "scores", []) or [])
        boxes = getattr(output, "boxes", None)
        if boxes is None:
            return ()
        tokens: list[OCRToken] = []
        for text, score, points in zip(texts, scores, boxes, strict=True):
            xs = [float(point[0]) / image.width for point in points]
            ys = [float(point[1]) / image.height for point in points]
            tokens.append(
                OCRToken(
                    text=str(text).strip(),
                    confidence=float(score),
                    box=(min(xs), min(ys), max(xs), max(ys)),
                )
            )
        return tuple(token for token in tokens if token.text)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def _similarity(text: str, alias: str) -> float:
    left = _normalize(text)
    right = _normalize(alias)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    if left in right or right in left:
        ratio = max(ratio, min(len(left), len(right)) / max(len(left), len(right)))
    return ratio


def _best_match(
    text: str,
    vocabulary: dict[Any, tuple[str, ...]],
) -> tuple[Any | None, float]:
    best_value = None
    best_score = 0.0
    for value, aliases in vocabulary.items():
        score = max((_similarity(text, alias) for alias in aliases), default=0.0)
        if score > best_score:
            best_value = value
            best_score = score
    return best_value, best_score


def _reading(
    field_id: str,
    value: str | int | None,
    token: OCRToken | None,
    match_score: float,
    threshold: float,
    *,
    reason: str = "",
) -> RollFieldReading:
    if token is None or value is None:
        return RollFieldReading(field_id, None, 0.0, "missing", reason=reason or "没有读到字段")
    confidence = max(0.0, min(1.0, token.confidence * match_score))
    status: FieldStatus = "confirmed" if confidence >= threshold else "low_confidence"
    return RollFieldReading(
        field_id=field_id,
        value=value,
        confidence=confidence,
        status=status,
        evidence_text=token.text,
        evidence_box=token.box,
        reason=reason if status != "confirmed" else "",
    )


def _matched_tokens(
    tokens: tuple[OCRToken, ...],
    vocabulary: dict[Any, tuple[str, ...]],
    *,
    minimum_similarity: float = 0.62,
) -> list[tuple[OCRToken, Any, float]]:
    matches = []
    for token in tokens:
        value, score = _best_match(token.text, vocabulary)
        if value is not None and score >= minimum_similarity:
            matches.append((token, value, score))
    return matches


def _role_anchors(
    tokens: tuple[OCRToken, ...], profile: LiveOCRProfile
) -> dict[str, tuple[OCRToken, float]]:
    threshold = float(profile.recognition["target_anchor_confidence"])
    anchors: dict[str, tuple[OCRToken, float]] = {}
    for token, role, similarity in _matched_tokens(tokens, profile.roles, minimum_similarity=0.72):
        confidence = token.confidence * similarity
        current = anchors.get(role)
        if confidence >= threshold and (current is None or confidence > current[1]):
            anchors[role] = (token, confidence)
    return anchors


def _is_target_screen(
    tokens: tuple[OCRToken, ...], profile: LiveOCRProfile
) -> tuple[bool, dict[str, tuple[OCRToken, float]]]:
    roles = _role_anchors(tokens, profile)
    anchor_hit = any(
        token.confidence >= float(profile.recognition["target_anchor_confidence"])
        and max((_similarity(token.text, alias) for alias in profile.target_anchors), default=0.0)
        >= 0.68
        for token in tokens
    )
    stat_count = len(_matched_tokens(tokens, profile.stats, minimum_similarity=0.7))
    return len(roles) == 3 and (anchor_hit or stat_count >= 6), roles


def _nearest_role(
    token: OCRToken,
    roles: dict[str, tuple[OCRToken, float]],
    maximum_distance: float,
) -> str | None:
    if not roles:
        return None
    role, item = min(roles.items(), key=lambda pair: abs(pair[1][0].center_x - token.center_x))
    return role if abs(item[0].center_x - token.center_x) <= maximum_distance else None


def _row_boundaries(stat_tokens: list[tuple[OCRToken, str, float]]) -> list[tuple[float, float]]:
    centers = [item[0].center_y for item in stat_tokens]
    bounds = []
    for index, center in enumerate(centers):
        low = 0.0 if index == 0 else (centers[index - 1] + center) / 2.0
        high = 1.0 if index == len(centers) - 1 else (center + centers[index + 1]) / 2.0
        bounds.append((low, high))
    return bounds


def _best_in_row(
    matches: list[tuple[OCRToken, Any, float]],
    *,
    role: str,
    roles: dict[str, tuple[OCRToken, float]],
    maximum_distance: float,
    low: float,
    high: float,
) -> tuple[OCRToken, Any, float] | None:
    candidates = [
        item
        for item in matches
        if low <= item[0].center_y < high
        and _nearest_role(item[0], roles, maximum_distance) == role
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0].confidence * item[2])


def _combined_token(tokens: list[OCRToken]) -> OCRToken:
    ordered = sorted(tokens, key=lambda token: (token.center_y, token.center_x))
    return OCRToken(
        text=" ".join(token.text for token in ordered),
        confidence=min(token.confidence for token in ordered),
        box=(
            min(token.box[0] for token in ordered),
            min(token.box[1] for token in ordered),
            max(token.box[2] for token in ordered),
            max(token.box[3] for token in ordered),
        ),
    )


def _operation_candidates(tokens: tuple[OCRToken, ...], *, region_top: float) -> list[OCRToken]:
    bottom = [token for token in tokens if token.center_y >= region_top]
    relevant = [
        token
        for token in bottom
        if any(
            keyword in _normalize(token.text)
            for keyword in (
                "reroll",
                "random",
                "increase",
                "quality",
                "trait",
                "stat",
                "重新",
                "随机",
                "提升",
                "品质",
                "特性",
                "统计",
            )
        )
    ]
    if not relevant:
        return []
    groups: list[list[OCRToken]] = []
    for token in sorted(relevant, key=lambda item: item.center_x):
        attached = False
        for group in groups:
            group_box = _combined_token(group).box
            center_x = (group_box[0] + group_box[2]) / 2.0
            center_y = (group_box[1] + group_box[3]) / 2.0
            if abs(center_x - token.center_x) <= 0.11 and abs(center_y - token.center_y) <= 0.1:
                group.append(token)
                attached = True
                break
        if not attached:
            groups.append([token])
    candidates = [_combined_token(group) for group in groups]
    candidates.extend(relevant)
    unique: dict[tuple[str, Box], OCRToken] = {}
    for candidate in candidates:
        unique[(_normalize(candidate.text), candidate.box)] = candidate
    return sorted(unique.values(), key=lambda item: item.center_x)


def _parse_offers(
    tokens: tuple[OCRToken, ...], profile: LiveOCRProfile
) -> list[RollFieldReading]:
    threshold = float(profile.recognition["operation_confidence"])
    candidates = _operation_candidates(
        tokens,
        region_top=float(profile.recognition["operation_region_top"]),
    )
    choices: list[tuple[float, OCRToken, int]] = []
    for token in candidates:
        operation_id, similarity = _best_match(token.text, profile.operations)
        if operation_id is not None:
            choices.append((token.confidence * similarity, token, int(operation_id)))
    chosen: list[tuple[float, OCRToken, int]] = []
    for choice in sorted(choices, key=lambda item: item[0], reverse=True):
        _, token, operation_id = choice
        if operation_id in {item[2] for item in chosen}:
            continue
        if any(abs(token.center_x - item[1].center_x) < 0.045 for item in chosen):
            continue
        chosen.append(choice)
        if len(chosen) == 3:
            break
    chosen.sort(key=lambda item: item[1].center_x)
    readings = []
    for index in range(3):
        if index >= len(chosen):
            readings.append(_reading(f"offer.{index}", None, None, 0.0, threshold))
            continue
        confidence, token, operation_id = chosen[index]
        status: FieldStatus = "confirmed" if confidence >= threshold else "low_confidence"
        readings.append(
            RollFieldReading(
                field_id=f"offer.{index}",
                value=operation_id,
                confidence=confidence,
                status=status,
                evidence_text=token.text,
                evidence_box=token.box,
                reason="Roll 选项文字置信度不足" if status != "confirmed" else "",
            )
        )
    if len({reading.value for reading in readings if reading.value is not None}) != 3:
        readings = [
            RollFieldReading(
                field_id=reading.field_id,
                value=reading.value,
                confidence=reading.confidence,
                status="conflict" if reading.value is not None else reading.status,
                evidence_text=reading.evidence_text,
                evidence_box=reading.evidence_box,
                reason="三个 Roll 选项没有被识别为互不相同",
            )
            for reading in readings
        ]
    return readings


def _parse_remaining(
    tokens: tuple[OCRToken, ...], profile: LiveOCRProfile
) -> RollFieldReading:
    threshold = float(profile.recognition["field_confidence"])
    patterns = (
        re.compile(r"roll\s*tokens?\s*[:：]?\s*(\d{1,2})", re.IGNORECASE),
        re.compile(r"重选代币\s*[:：]?\s*(\d{1,2})\s*枚?"),
    )
    candidates: list[OCRToken] = list(tokens)
    ordered = sorted(tokens, key=lambda token: (token.center_y, token.center_x))
    for left in ordered:
        neighbors = [
            right
            for right in ordered
            if right is not left
            and abs(right.center_y - left.center_y) <= 0.025
            and 0.0 <= right.center_x - left.center_x <= 0.16
        ]
        for right in neighbors[:2]:
            candidates.append(_combined_token([left, right]))
    best: tuple[float, OCRToken, int] | None = None
    for token in candidates:
        for pattern in patterns:
            match = pattern.search(unicodedata.normalize("NFKC", token.text))
            if match:
                value = int(match.group(1))
                if 0 <= value <= 40 and (best is None or token.confidence > best[0]):
                    best = (token.confidence, token, value)
    if best is None:
        return _reading("remaining_rolls", None, None, 0.0, threshold)
    confidence, token, value = best
    status: FieldStatus = "confirmed" if confidence >= threshold else "low_confidence"
    return RollFieldReading(
        "remaining_rolls",
        value,
        confidence,
        status,
        token.text,
        token.box,
        "剩余次数置信度不足" if status != "confirmed" else "",
    )


def parse_roll_screen_tokens(
    tokens: tuple[OCRToken, ...],
    *,
    captured_at: datetime,
    image_sha256: str,
    viewport: tuple[int, int],
    profile: LiveOCRProfile,
    rules: RollRuleSet,
) -> RollScreenObservation:
    target, roles = _is_target_screen(tokens, profile)
    if not target:
        return RollScreenObservation(
            status="not_target",
            captured_at=captured_at,
            image_sha256=image_sha256,
            viewport=viewport,
            profile_id=profile.profile_id,
            warnings=("当前不是完整的 Group Roll 页面；没有更新顾问表单。",),
        )

    threshold = float(profile.recognition["field_confidence"])
    maximum_distance = float(profile.recognition["role_maximum_x_distance"])
    stat_matches = _matched_tokens(tokens, profile.stats, minimum_similarity=0.66)
    quality_matches = _matched_tokens(tokens, profile.qualities, minimum_similarity=0.7)
    trait_matches = _matched_tokens(tokens, profile.traits, minimum_similarity=0.7)
    readings: list[RollFieldReading] = []
    role_stat_values: dict[str, list[str | None]] = {}

    for role in rules.group_roles:
        role_stats = [
            item
            for item in stat_matches
            if _nearest_role(item[0], roles, maximum_distance) == role
        ]
        role_stats.sort(key=lambda item: item[0].center_y)
        role_stats = role_stats[:3]
        while len(role_stats) < 3:
            role_stats.append((None, None, 0.0))  # type: ignore[arg-type]
        valid_stats = [item for item in role_stats if item[0] is not None]
        bounds = _row_boundaries(valid_stats)
        if len(bounds) != 3:
            bounds = [(0.0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1.0)]
        role_stat_values[role] = []
        colors = rules.colors_for(role)[:3]
        for index, (stat_item, (low, high), color) in enumerate(
            zip(role_stats, bounds, colors, strict=True)
        ):
            stat_token, stat_id, stat_similarity = stat_item
            stat_reading = _reading(
                f"banner.{role}.{index}.stat",
                stat_id,
                stat_token,
                stat_similarity,
                threshold,
            )
            if stat_id is not None and stat_id not in rules.stats_for(color):
                stat_reading = RollFieldReading(
                    field_id=stat_reading.field_id,
                    value=stat_reading.value,
                    confidence=stat_reading.confidence,
                    status="conflict",
                    evidence_text=stat_reading.evidence_text,
                    evidence_box=stat_reading.evidence_box,
                    reason=f"{role} 第 {index + 1} 格颜色与 Stat 冲突",
                )
            readings.append(stat_reading)
            role_stat_values[role].append(str(stat_id) if stat_id is not None else None)

            quality_item = _best_in_row(
                quality_matches,
                role=role,
                roles=roles,
                maximum_distance=maximum_distance,
                low=low,
                high=high,
            )
            quality_token, quality, quality_similarity = (
                quality_item if quality_item is not None else (None, None, 0.0)
            )
            readings.append(
                _reading(
                    f"banner.{role}.{index}.quality",
                    quality,
                    quality_token,
                    quality_similarity,
                    threshold,
                )
            )

            trait_item = _best_in_row(
                trait_matches,
                role=role,
                roles=roles,
                maximum_distance=maximum_distance,
                low=low,
                high=high,
            )
            trait_token, trait, trait_similarity = (
                trait_item if trait_item is not None else (None, None, 0.0)
            )
            readings.append(
                _reading(
                    f"banner.{role}.{index}.trait",
                    trait,
                    trait_token,
                    trait_similarity,
                    threshold,
                )
            )

    for role, values in role_stat_values.items():
        non_null = [value for value in values if value is not None]
        duplicates = {value for value in non_null if non_null.count(value) > 1}
        if duplicates:
            readings = [
                RollFieldReading(
                    field_id=reading.field_id,
                    value=reading.value,
                    confidence=reading.confidence,
                    status="conflict",
                    evidence_text=reading.evidence_text,
                    evidence_box=reading.evidence_box,
                    reason="同一战旗出现重复 Stat，识别结果不合法",
                )
                if reading.field_id.startswith(f"banner.{role}.")
                and reading.field_id.endswith(".stat")
                and reading.value in duplicates
                else reading
                for reading in readings
            ]

    readings.extend(_parse_offers(tokens, profile))
    readings.append(_parse_remaining(tokens, profile))
    confirmed = all(reading.status == "confirmed" for reading in readings)
    state = _state_from_readings(readings, rules) if confirmed else None
    return RollScreenObservation(
        status="confirmed" if state is not None else "incomplete",
        captured_at=captured_at,
        image_sha256=image_sha256,
        viewport=viewport,
        profile_id=profile.profile_id,
        fields=tuple(readings),
        warnings=(
            ()
            if state is not None
            else ("有字段缺失、冲突或置信度不足；已识别字段可录入，但不会自动计算。",)
        ),
        state=state,
    )


def _state_from_readings(
    readings: list[RollFieldReading], rules: RollRuleSet
) -> GroupRollState | None:
    values = {reading.field_id: reading.value for reading in readings}
    try:
        banners = []
        for role in rules.group_roles:
            emblems = []
            for index in range(3):
                emblems.append(
                    EmblemState(
                        stat_id=str(values[f"banner.{role}.{index}.stat"]),
                        quality_tier=int(values[f"banner.{role}.{index}.quality"]),
                        trait_id=str(values[f"banner.{role}.{index}.trait"]),
                    )
                )
            banners.append(BannerState(role=role, emblems=tuple(emblems)))
        state = GroupRollState(
            banners=tuple(banners),
            offer=RollOffer(tuple(int(values[f"offer.{index}"]) for index in range(3))),
            remaining_rolls=int(values["remaining_rolls"]),
        )
        validate_group_state(state, rules)
        return state
    except (KeyError, TypeError, ValueError):
        return None


class RollScreenReader:
    def __init__(
        self,
        *,
        profile: LiveOCRProfile,
        rules: RollRuleSet,
        token_engine: TokenEngine | None = None,
    ) -> None:
        self.profile = profile
        self.rules = rules
        self._token_engine = token_engine

    @property
    def token_engine(self) -> TokenEngine:
        if self._token_engine is None:
            self._token_engine = RapidOCRTokenEngine()
        return self._token_engine

    def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
        tokens = self.token_engine.extract(
            frame.image,
            maximum_width=int(self.profile.recognition["maximum_ocr_width"]),
        )
        return parse_roll_screen_tokens(
            tokens,
            captured_at=frame.captured_at,
            image_sha256=frame.image_sha256,
            viewport=frame.viewport,
            profile=self.profile,
            rules=self.rules,
        )


@dataclass(frozen=True)
class MonitorSnapshot:
    running: bool
    stage: Literal["idle", "capturing", "recognizing", "not_target", "incomplete", "confirmed", "error"]
    message: str
    generation: int
    observation: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "stage": self.stage,
            "message": self.message,
            "generation": self.generation,
            "observation": copy.deepcopy(self.observation),
        }


class LiveRollMonitor:
    def __init__(
        self,
        *,
        profile: LiveOCRProfile,
        rules: RollRuleSet,
        capturer: Callable[..., CapturedFrame] = capture_dota_window,
        reader: RollScreenReader | None = None,
        cache_dir: Path = PATHS.cache / "ocr" / "live-roll",
    ) -> None:
        self.profile = profile
        self.rules = rules
        self._capturer = capturer
        self._reader = reader or RollScreenReader(profile=profile, rules=rules)
        self._cache_dir = cache_dir
        self._gate = StableFrameGate(
            signature_width=int(profile.capture["signature_width"]),
            signature_height=int(profile.capture["signature_height"]),
            stable_frame_count=int(profile.capture["stable_frame_count"]),
            stable_mean_difference=float(profile.capture["stable_mean_difference"]),
            meaningful_mean_difference=float(profile.capture["meaningful_mean_difference"]),
        )
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = MonitorSnapshot(False, "idle", "实时识别尚未启动。", 0)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._gate.reset()
            generation = self._snapshot.generation + 1
            self._snapshot = MonitorSnapshot(True, "capturing", "正在等待稳定的 Dota 画面…", generation)
            self._thread = threading.Thread(
                target=self._run,
                name="ti-live-roll-ocr",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)
        with self._lock:
            generation = self._snapshot.generation + 1
            self._snapshot = MonitorSnapshot(False, "idle", "实时识别已停止；手填仍可使用。", generation)
            # A recognition pass can outlive the short UI join timeout. Keep its
            # handle until it actually exits so start() cannot clear the shared
            # stop event and launch a second worker beside it.
            if thread is None or not thread.is_alive():
                self._thread = None

    def snapshot(self) -> MonitorSnapshot:
        with self._lock:
            return MonitorSnapshot(**self._snapshot.to_payload())

    def _publish(
        self,
        stage: Literal["capturing", "recognizing", "not_target", "incomplete", "confirmed", "error"],
        message: str,
        *,
        observation: dict[str, Any] | None = None,
        advance: bool = True,
    ) -> None:
        with self._lock:
            # stop() owns the final idle snapshot. A slow OCR pass that began
            # before the user disabled monitoring must never publish over it.
            if self._stop.is_set():
                return
            generation = self._snapshot.generation + (1 if advance else 0)
            self._snapshot = MonitorSnapshot(
                running=not self._stop.is_set(),
                stage=stage,
                message=message,
                generation=generation,
                observation=copy.deepcopy(observation),
            )

    def _persist_latest(self, frame: CapturedFrame, observation: RollScreenObservation) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        image_tmp = self._cache_dir / "latest-screen.tmp.png"
        image_path = self._cache_dir / "latest-screen.png"
        json_tmp = self._cache_dir / "latest-observation.tmp.json"
        json_path = self._cache_dir / "latest-observation.json"
        frame.image.save(image_tmp, format="PNG")
        image_tmp.replace(image_path)
        json_tmp.write_text(
            json.dumps(observation.to_payload(), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        json_tmp.replace(json_path)

    def _run(self) -> None:
        poll_seconds = float(self.profile.capture["poll_seconds"])
        title = str(self.profile.capture["window_title"])
        try:
            while not self._stop.is_set():
                try:
                    frame = self._capturer(window_title=title)
                    decision = self._gate.observe(frame.image)
                    if decision == "accepted":
                        self._publish("recognizing", "检测到稳定的新画面，正在识别…")
                        observation = self._reader.inspect(frame)
                        payload = observation.to_payload()
                        if observation.status != "not_target":
                            self._persist_latest(frame, observation)
                        messages = {
                            "not_target": "当前不是完整的 Group Roll 页面；继续监视。",
                            "incomplete": "识别到 Roll 页面，但仍有字段需要人工确认。",
                            "confirmed": "完整新画面已确认，准备自动录入并重新计算。",
                            "error": "识别器返回错误状态。",
                        }
                        self._publish(
                            observation.status,
                            messages[observation.status],
                            observation=payload,
                        )
                    elif decision == "unstable":
                        self._publish(
                            "capturing",
                            "画面仍在变化，等待稳定后再识别…",
                            advance=False,
                        )
                except (OSError, RuntimeError, ValueError, ScreenCaptureError) as error:
                    self._publish("error", str(error))
                self._stop.wait(poll_seconds)
        finally:
            if not self._stop.is_set():
                self._publish("error", "实时识别线程意外结束。")


def observation_widget_updates(observation: dict[str, Any], rules: RollRuleSet) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    positive_operations = {item.operation_id for item in rules.offered_operations}
    for reading in observation.get("fields", []):
        if reading.get("status") != "confirmed":
            continue
        field_id = str(reading.get("field_id", ""))
        value = reading.get("value")
        banner_match = re.fullmatch(r"banner\.(core|mid|support)\.(\d)\.(stat|quality|trait)", field_id)
        if banner_match:
            role, index_text, attribute = banner_match.groups()
            index = int(index_text)
            if index >= 3:
                continue
            if attribute == "stat" and value not in rules.stats_for(rules.colors_for(role)[index]):
                continue
            if attribute == "quality" and value not in {1, 2, 3, 4, 5}:
                continue
            if attribute == "trait" and value not in rules.traits:
                continue
            updates[f"current_advisor_{role}_{index}_{attribute}"] = value
            continue
        offer_match = re.fullmatch(r"offer\.(\d)", field_id)
        if offer_match and int(offer_match.group(1)) < 3 and value in positive_operations:
            updates[f"current_advisor_offer_{offer_match.group(1)}"] = value
        elif field_id == "remaining_rolls" and isinstance(value, int) and 0 <= value <= 40:
            updates["current_advisor_remaining"] = value
    return updates
