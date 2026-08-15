"""Local-only Dota window observation with isolated Group and Main OCR profiles."""

from __future__ import annotations

import copy
import ctypes
import itertools
import json
import re
import sys
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol

from ti_predictor.fantasy.main_roll import MainRollState, validate_main_state
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
    state: GroupRollState | MainRollState | None = None

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
                "period": self.state.period,
                "slot_count": self.state.slot_count,
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
            json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        return payload


@dataclass(frozen=True)
class CapturedFrame:
    image: Any
    captured_at: datetime
    image_sha256: str
    window_title: str
    capture_source: str = ""
    monitor_device: str = ""

    @property
    def viewport(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.image.size)


@dataclass(frozen=True)
class LiveOCRProfile:
    profile_id: str
    period: Literal["group", "main"]
    slot_count: int
    max_rolls: int
    language_priority: tuple[str, ...]
    source: dict[str, str]
    capture: dict[str, Any]
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
    inherited = raw.pop("extends", None)
    if inherited is not None:
        base_path = path.parent / str(inherited)
        base = json.loads(base_path.read_text(encoding="utf-8"))
        base.update(raw)
        raw = base
    period = str(raw["period"])
    if period not in {"group", "main"}:
        raise ValueError(f"unknown Fantasy OCR period: {period}")
    slot_count = int(raw["slot_count"])
    max_rolls = int(raw["max_rolls"])
    expected = {"group": (3, 40), "main": (5, 30)}[period]
    if (slot_count, max_rolls) != expected:
        raise ValueError(f"{period} OCR profile has an invalid slot or Roll contract")
    return LiveOCRProfile(
        profile_id=str(raw["profile_id"]),
        period=period,  # type: ignore[arg-type]
        slot_count=slot_count,
        max_rolls=max_rolls,
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


@dataclass(frozen=True)
class DotaCaptureTarget:
    hwnd: int
    process_id: int
    executable_path: str
    monitor_handle: int
    monitor_device: str
    monitor_rect: tuple[int, int, int, int]
    window_rect: tuple[int, int, int, int]


def _locate_dota_capture_target(window_title: str) -> DotaCaptureTarget:
    if not live_capture_supported():
        raise ScreenCaptureError("实时窗口识别仅支持本机 Windows；手填顾问仍可使用。")
    from ctypes import wintypes

    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MonitorInfoEx(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", Rect),
            ("rcWork", Rect),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    )
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = int(user32.FindWindowW(None, window_title) or 0)
    if not handle:
        raise ScreenCaptureError(f"没有找到标题为 {window_title!r} 的 Dota 窗口。")
    if user32.IsIconic(handle):
        raise ScreenCaptureError("Dota 2 窗口已最小化；请先恢复窗口。")

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    process_handle = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not process_handle:
        raise ScreenCaptureError(f"无法核对 Dota 窗口进程（PID {process_id.value}）。")
    try:
        path_buffer = ctypes.create_unicode_buffer(32768)
        path_length = wintypes.DWORD(len(path_buffer))
        if not kernel32.QueryFullProcessImageNameW(
            process_handle,
            0,
            path_buffer,
            ctypes.byref(path_length),
        ):
            raise ScreenCaptureError(f"无法读取 Dota 窗口进程路径（PID {process_id.value}）。")
        executable_path = path_buffer.value
    finally:
        kernel32.CloseHandle(process_handle)
    if Path(executable_path).name.casefold() != "dota2.exe":
        raise ScreenCaptureError(
            f"标题为 {window_title!r} 的窗口属于 {Path(executable_path).name}，不是 dota2.exe。"
        )

    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfoEx))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(Rect))
    user32.GetWindowRect.restype = wintypes.BOOL
    monitor_handle = int(user32.MonitorFromWindow(handle, 2) or 0)
    monitor_info = MonitorInfoEx()
    monitor_info.cbSize = ctypes.sizeof(MonitorInfoEx)
    if not monitor_handle or not user32.GetMonitorInfoW(monitor_handle, ctypes.byref(monitor_info)):
        raise ScreenCaptureError("无法确定 Dota 2 所在显示器。")
    window_rect = Rect()
    if not user32.GetWindowRect(handle, ctypes.byref(window_rect)):
        raise ScreenCaptureError("无法读取 Dota 2 窗口范围。")
    return DotaCaptureTarget(
        hwnd=handle,
        process_id=int(process_id.value),
        executable_path=executable_path,
        monitor_handle=monitor_handle,
        monitor_device=str(monitor_info.szDevice),
        monitor_rect=(
            int(monitor_info.rcMonitor.left),
            int(monitor_info.rcMonitor.top),
            int(monitor_info.rcMonitor.right),
            int(monitor_info.rcMonitor.bottom),
        ),
        window_rect=(
            int(window_rect.left),
            int(window_rect.top),
            int(window_rect.right),
            int(window_rect.bottom),
        ),
    )


def _select_dxcam_output(factory: Any, monitor_handle: int) -> tuple[int, int, Any]:
    for device_index, outputs in enumerate(factory.outputs):
        for output_index, output in enumerate(outputs):
            if int(output.hmonitor) == monitor_handle:
                return device_index, output_index, output
    available = [int(output.hmonitor) for outputs in factory.outputs for output in outputs]
    raise ScreenCaptureError(f"DXcam 没有找到 Dota 所在显示器句柄 {monitor_handle}；可用句柄：{available}。")


def _crop_monitor_frame_to_window(image: Any, target: DotaCaptureTarget) -> Any:
    monitor_left, monitor_top, monitor_right, monitor_bottom = target.monitor_rect
    window_left, window_top, window_right, window_bottom = target.window_rect
    left = max(monitor_left, window_left)
    top = max(monitor_top, window_top)
    right = min(monitor_right, window_right)
    bottom = min(monitor_bottom, window_bottom)
    if right <= left or bottom <= top:
        raise ScreenCaptureError("Dota 2 窗口没有位于检测到的显示器可见范围内。")
    scale_x = image.width / max(1, monitor_right - monitor_left)
    scale_y = image.height / max(1, monitor_bottom - monitor_top)
    box = (
        round((left - monitor_left) * scale_x),
        round((top - monitor_top) * scale_y),
        round((right - monitor_left) * scale_x),
        round((bottom - monitor_top) * scale_y),
    )
    return image.crop(box)


def _capture_is_blank(image: Any) -> bool:
    low, high = image.convert("L").resize((64, 36)).getextrema()
    return int(high) < 16 or int(high) - int(low) < 4


class DotaMonitorCapturer:
    """Capture the physical monitor containing dota2.exe, including DirectX surfaces."""

    def __init__(self, *, backend_order: tuple[str, ...] = ("winrt", "dxgi")) -> None:
        self._backend_order = backend_order
        self._factory: Any | None = None
        self._camera: Any | None = None
        self._camera_key: tuple[int, int, str] | None = None

    @property
    def factory(self) -> Any:
        if self._factory is None:
            try:
                import dxcam
            except ImportError as error:  # pragma: no cover - optional dependency
                raise ScreenCaptureError("缺少 DXcam；请运行 `uv sync --extra ocr`。") from error
            self._factory = dxcam.DXFactory()
        return self._factory

    def _camera_for(self, device_index: int, output_index: int, backend: str) -> Any:
        key = (device_index, output_index, backend)
        if self._camera is not None and self._camera_key == key:
            return self._camera
        if self._camera is not None:
            self._camera.release()
        try:
            self._camera = self.factory.create(
                device_idx=device_index,
                output_idx=output_index,
                output_color="RGB",
                backend=backend,
                processor_backend="numpy",
            )
        except (OSError, RuntimeError, ValueError) as error:
            self._camera = None
            self._camera_key = None
            raise ScreenCaptureError(f"{backend} 捕获器初始化失败：{error}") from error
        self._camera_key = key
        return self._camera

    def __call__(self, *, window_title: str = "Dota 2") -> CapturedFrame:
        try:
            from PIL import Image
        except ImportError as error:  # pragma: no cover - optional dependency
            raise ScreenCaptureError("缺少 Pillow；请运行 `uv sync --extra ocr`。") from error
        target = _locate_dota_capture_target(window_title)
        device_index, output_index, _ = _select_dxcam_output(
            self.factory,
            target.monitor_handle,
        )
        failures: list[str] = []
        for backend in self._backend_order:
            try:
                array = self._camera_for(device_index, output_index, backend).grab(new_frame_only=False)
                if array is None:
                    raise ScreenCaptureError("没有返回画面。")
                image = _crop_monitor_frame_to_window(
                    Image.fromarray(array).convert("RGB"),
                    target,
                )
                if image.width < 800 or image.height < 600:
                    raise ScreenCaptureError(f"窗口尺寸异常：{image.width}×{image.height}。")
                if _capture_is_blank(image):
                    raise ScreenCaptureError("返回了空白画面。")
                identity = (
                    image.width.to_bytes(4, "little") + image.height.to_bytes(4, "little") + image.tobytes()
                )
                return CapturedFrame(
                    image=image,
                    captured_at=_utc_now(),
                    image_sha256=sha256(identity).hexdigest(),
                    window_title=window_title,
                    capture_source=backend,
                    monitor_device=target.monitor_device,
                )
            except (OSError, RuntimeError, ValueError, ScreenCaptureError) as error:
                failures.append(f"{backend}: {error}")
        raise ScreenCaptureError("Dota 显示器捕获失败；" + "；".join(failures))

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
        self._camera = None
        self._camera_key = None


def capture_dota_window(*, window_title: str = "Dota 2") -> CapturedFrame:
    capturer = DotaMonitorCapturer()
    try:
        return capturer(window_title=window_title)
    finally:
        capturer.close()


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


def _multiline_token_candidates(tokens: tuple[OCRToken, ...]) -> tuple[OCRToken, ...]:
    """Add two-line OCR labels without replacing the original evidence tokens."""

    combined: list[OCRToken] = []
    for pair in itertools.combinations(tokens, 2):
        first, second = sorted(pair, key=lambda token: token.center_y)
        vertical_gap = second.center_y - first.center_y
        if vertical_gap <= 0 or vertical_gap > 0.026:
            continue
        if abs(first.center_x - second.center_x) > 0.045:
            continue
        horizontal_overlap = min(first.box[2], second.box[2]) - max(first.box[0], second.box[0])
        narrowest_width = min(first.box[2] - first.box[0], second.box[2] - second.box[0])
        if horizontal_overlap < max(0.0, narrowest_width * 0.25):
            continue
        combined.append(_combined_token([first, second]))
    return (*tokens, *combined)


def _deduplicate_vertical_matches(
    matches: list[tuple[OCRToken, Any, float]],
    *,
    minimum_separation: float = 0.035,
) -> list[tuple[OCRToken, Any, float]]:
    """Keep the most specific label when OCR returns both a line and its joined label."""

    ranked = sorted(
        matches,
        key=lambda item: (
            item[0].confidence * item[2],
            len(_normalize(item[0].text)),
        ),
        reverse=True,
    )
    chosen: list[tuple[OCRToken, Any, float]] = []
    for item in ranked:
        if any(abs(item[0].center_y - other[0].center_y) < minimum_separation for other in chosen):
            continue
        chosen.append(item)
    return sorted(chosen, key=lambda item: item[0].center_y)


def _role_anchors(tokens: tuple[OCRToken, ...], profile: LiveOCRProfile) -> dict[str, tuple[OCRToken, float]]:
    threshold = float(profile.recognition["target_anchor_confidence"])
    candidates: dict[str, list[tuple[OCRToken, float]]] = {role: [] for role in profile.roles}
    for token, role, similarity in _matched_tokens(tokens, profile.roles, minimum_similarity=0.72):
        confidence = token.confidence * similarity
        if confidence >= threshold:
            candidates[role].append((token, confidence))

    role_order = ("core", "mid", "support")
    if all(candidates.get(role) for role in role_order):
        aligned: list[tuple[float, tuple[tuple[OCRToken, float], ...]]] = []
        for triplet in itertools.product(*(candidates[role] for role in role_order)):
            xs = [item[0].center_x for item in triplet]
            ys = [item[0].center_y for item in triplet]
            if not (xs[0] + 0.08 < xs[1] and xs[1] + 0.08 < xs[2]):
                continue
            y_spread = max(ys) - min(ys)
            if y_spread > 0.08:
                continue
            score = sum(item[1] for item in triplet) - y_spread * 4.0
            aligned.append((score, triplet))
        if aligned:
            _, best = max(aligned, key=lambda item: item[0])
            return dict(zip(role_order, best, strict=True))

    anchors: dict[str, tuple[OCRToken, float]] = {}
    for role, items in candidates.items():
        if items:
            anchors[role] = max(items, key=lambda item: item[1])
    return anchors


def _is_target_screen(
    tokens: tuple[OCRToken, ...], profile: LiveOCRProfile
) -> tuple[bool, dict[str, tuple[OCRToken, float]]]:
    roles = _role_anchors(tokens, profile)
    anchor_hit = any(
        token.confidence >= float(profile.recognition["target_anchor_confidence"])
        and max((_similarity(token.text, alias) for alias in profile.target_anchors), default=0.0) >= 0.68
        for token in tokens
    )
    stat_count = len(
        _matched_tokens(_multiline_token_candidates(tokens), profile.stats, minimum_similarity=0.7)
    )
    return len(roles) == 3 and (anchor_hit or stat_count >= 6), roles


def _nearest_role_at_x(
    x: float,
    roles: dict[str, tuple[OCRToken, float]],
    maximum_distance: float,
) -> str | None:
    if not roles:
        return None
    role, item = min(roles.items(), key=lambda pair: abs(pair[1][0].center_x - x))
    return role if abs(item[0].center_x - x) <= maximum_distance else None


def _nearest_role(
    token: OCRToken,
    roles: dict[str, tuple[OCRToken, float]],
    maximum_distance: float,
) -> str | None:
    return _nearest_role_at_x(token.center_x, roles, maximum_distance)


def _row_boundaries(stat_tokens: list[tuple[OCRToken, str, float]]) -> list[tuple[float, float]]:
    centers = [item[0].center_y for item in stat_tokens]
    bounds = []
    for index, center in enumerate(centers):
        low = max(0.0, center - 0.025)
        high = 1.0 if index == len(centers) - 1 else max(low, centers[index + 1] - 0.005)
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
        if low <= item[0].center_y < high and _nearest_role(item[0], roles, maximum_distance) == role
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


def _operation_candidates(
    tokens: tuple[OCRToken, ...],
    *,
    region_top: float,
    excluded_labels: tuple[str, ...] = (),
) -> list[OCRToken]:
    bottom = _multiline_token_candidates(tuple(token for token in tokens if token.center_y >= region_top))
    relevant = [
        token
        for token in bottom
        if max((_similarity(token.text, label) for label in excluded_labels), default=0.0) < 0.75
        and any(
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


def _parse_offers(tokens: tuple[OCRToken, ...], profile: LiveOCRProfile) -> list[RollFieldReading]:
    threshold = float(profile.recognition["operation_confidence"])
    candidates = _operation_candidates(
        tokens,
        region_top=float(profile.recognition["operation_region_top"]),
        excluded_labels=profile.target_anchors,
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


def _parse_remaining(tokens: tuple[OCRToken, ...], profile: LiveOCRProfile) -> RollFieldReading:
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
                if 0 <= value <= profile.max_rolls and (best is None or token.confidence > best[0]):
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
            warnings=(f"当前不是完整的 {profile.period.title()} Roll 页面；没有更新顾问表单。",),
        )

    threshold = float(profile.recognition["field_confidence"])
    maximum_distance = float(profile.recognition["role_maximum_x_distance"])
    stat_matches = _matched_tokens(
        _multiline_token_candidates(tokens),
        profile.stats,
        minimum_similarity=0.66,
    )
    quality_matches = _matched_tokens(tokens, profile.qualities, minimum_similarity=0.7)
    trait_matches = _matched_tokens(tokens, profile.traits, minimum_similarity=0.7)
    readings: list[RollFieldReading] = []
    role_stat_values: dict[str, list[str | None]] = {}

    matched_by_role = {
        role: _deduplicate_vertical_matches(
            [
                item
                for item in stat_matches
                if _nearest_role_at_x(item[0].box[0], roles, maximum_distance) == role
            ]
        )
        for role in rules.roles
    }
    if any(len(matches) > profile.slot_count for matches in matched_by_role.values()):
        return RollScreenObservation(
            status="incomplete",
            captured_at=captured_at,
            image_sha256=image_sha256,
            viewport=viewport,
            profile_id=profile.profile_id,
            warnings=(
                f"画面槽位数超过 {profile.period.title()} 的 {profile.slot_count} 槽契约；"
                "拒绝截断并请切换正确的阶段 Tab。",
            ),
        )

    for role in rules.roles:
        role_stats = [item for item in matched_by_role[role]]
        role_stats = role_stats[: profile.slot_count]
        while len(role_stats) < profile.slot_count:
            role_stats.append((None, None, 0.0))  # type: ignore[arg-type]
        valid_stats = [item for item in role_stats if item[0] is not None]
        bounds = _row_boundaries(valid_stats)
        if len(bounds) != profile.slot_count:
            bounds = [
                (index / profile.slot_count, (index + 1) / profile.slot_count)
                for index in range(profile.slot_count)
            ]
        role_stat_values[role] = []
        colors = rules.colors_for(role)[: profile.slot_count]
        for index, (stat_item, (low, high), color) in enumerate(zip(role_stats, bounds, colors, strict=True)):
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
            trait_token, trait, trait_similarity = trait_item if trait_item is not None else (None, None, 0.0)
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
    state = _state_from_readings(readings, rules, profile) if confirmed else None
    return RollScreenObservation(
        status="confirmed" if state is not None else "incomplete",
        captured_at=captured_at,
        image_sha256=image_sha256,
        viewport=viewport,
        profile_id=profile.profile_id,
        fields=tuple(readings),
        warnings=(
            () if state is not None else ("有字段缺失、冲突或置信度不足；已识别字段可录入，但不会自动计算。",)
        ),
        state=state,
    )


def _state_from_readings(
    readings: list[RollFieldReading],
    rules: RollRuleSet,
    profile: LiveOCRProfile,
) -> GroupRollState | MainRollState | None:
    values = {reading.field_id: reading.value for reading in readings}
    try:
        banners = []
        for role in rules.roles:
            emblems = []
            for index in range(profile.slot_count):
                emblems.append(
                    EmblemState(
                        stat_id=str(values[f"banner.{role}.{index}.stat"]),
                        quality_tier=int(values[f"banner.{role}.{index}.quality"]),
                        trait_id=str(values[f"banner.{role}.{index}.trait"]),
                    )
                )
            banners.append(BannerState(role=role, emblems=tuple(emblems)))
        state: GroupRollState | MainRollState
        common = {
            "banners": tuple(banners),
            "offer": RollOffer(tuple(int(values[f"offer.{index}"]) for index in range(3))),
            "remaining_rolls": int(values["remaining_rolls"]),
        }
        if profile.period == "group":
            state = GroupRollState(**common)
            validate_group_state(state, rules)
        else:
            state = MainRollState(**common)
            validate_main_state(state, rules)
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

    def _recognition_region(
        self,
        image: Any,
        roles: dict[str, tuple[OCRToken, float]],
    ) -> tuple[Any, tuple[int, int, int, int]]:
        left = max(
            0.0,
            min(item[0].center_x for item in roles.values())
            - float(self.profile.recognition["fantasy_region_left_margin"]),
        )
        right = min(
            1.0,
            max(item[0].center_x for item in roles.values())
            + float(self.profile.recognition["fantasy_region_right_margin"]),
        )
        top = max(
            0.0,
            min(item[0].center_y for item in roles.values())
            - float(self.profile.recognition["fantasy_region_top_margin"]),
        )
        bottom = float(self.profile.recognition["fantasy_region_bottom"])
        if right - left < 0.55 or bottom - top < 0.45:
            return image, (0, 0, image.width, image.height)
        box = (
            round(left * image.width),
            round(top * image.height),
            round(right * image.width),
            round(bottom * image.height),
        )
        return image.crop(box), box

    @staticmethod
    def _upscale_for_detail(image: Any, *, target_width: int) -> Any:
        if image.width >= target_width:
            return image
        ratio = target_width / image.width
        size = (target_width, max(1, round(image.height * ratio)))
        try:
            from PIL import Image

            return image.resize(size, resample=Image.Resampling.LANCZOS)
        except (ImportError, TypeError):
            return image.resize(size)

    @staticmethod
    def _to_full_frame_observation(
        observation: RollScreenObservation,
        *,
        region_box: tuple[int, int, int, int],
        viewport: tuple[int, int],
    ) -> RollScreenObservation:
        left, top, right, bottom = region_box
        full_width, full_height = viewport
        region_width = right - left
        region_height = bottom - top
        fields = tuple(
            replace(
                reading,
                evidence_box=(
                    (left + reading.evidence_box[0] * region_width) / full_width,
                    (top + reading.evidence_box[1] * region_height) / full_height,
                    (left + reading.evidence_box[2] * region_width) / full_width,
                    (top + reading.evidence_box[3] * region_height) / full_height,
                )
                if reading.evidence_box is not None
                else None,
            )
            for reading in observation.fields
        )
        return replace(observation, fields=fields)

    def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
        locator_tokens = self.token_engine.extract(
            frame.image,
            maximum_width=int(self.profile.recognition["locator_ocr_width"]),
        )
        roles = _role_anchors(locator_tokens, self.profile)
        region_box: tuple[int, int, int, int] | None = None
        if len(roles) == 3:
            recognition_image, region_box = self._recognition_region(frame.image, roles)
            recognition_image = self._upscale_for_detail(
                recognition_image,
                target_width=int(self.profile.recognition["maximum_ocr_width"]),
            )
            tokens = self.token_engine.extract(
                recognition_image,
                maximum_width=int(self.profile.recognition["maximum_ocr_width"]),
            )
        else:
            tokens = locator_tokens
        observation = parse_roll_screen_tokens(
            tokens,
            captured_at=frame.captured_at,
            image_sha256=frame.image_sha256,
            viewport=frame.viewport,
            profile=self.profile,
            rules=self.rules,
        )
        if region_box is not None:
            return self._to_full_frame_observation(
                observation,
                region_box=region_box,
                viewport=frame.viewport,
            )
        return observation


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
        capturer: Callable[..., CapturedFrame] | None = None,
        reader: RollScreenReader | None = None,
        cache_dir: Path = PATHS.cache / "ocr" / "live-roll",
    ) -> None:
        self.profile = profile
        self.rules = rules
        backend_order = tuple(str(item) for item in profile.capture.get("capture_backends", ()))
        self._capturer = capturer or DotaMonitorCapturer(backend_order=backend_order or ("winrt", "dxgi"))
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
        self._condition = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._active = False
        self._shutdown_requested = False
        self._request_id = 0
        self._snapshot = MonitorSnapshot(False, "idle", "尚未开始本次识别。", 0)

    def start_once(self) -> None:
        with self._condition:
            if self._shutdown_requested:
                return
            if self._active:
                return
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run,
                    name="ti-live-roll-ocr",
                    daemon=True,
                )
                self._thread.start()
            elif not self._thread.is_alive():
                generation = self._snapshot.generation + 1
                self._snapshot = MonitorSnapshot(
                    False,
                    "error",
                    "识别线程已经退出；请重启本地顾问。",
                    generation,
                )
                return
            self._gate.reset()
            self._request_id += 1
            self._active = True
            generation = self._snapshot.generation + 1
            self._snapshot = MonitorSnapshot(
                True,
                "capturing",
                f"一次识别已就绪；请切回 Dota 并停在完整的 {self.profile.period.title()} Roll 页面。",
                generation,
            )
            self._condition.notify_all()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        del join_timeout  # Kept for compatibility with the previous public method.
        with self._condition:
            self._request_id += 1
            self._active = False
            generation = self._snapshot.generation + 1
            self._snapshot = MonitorSnapshot(False, "idle", "本次识别已取消；手填仍可使用。", generation)
            self._condition.notify_all()

    def shutdown(self, *, join_timeout: float = 2.0) -> None:
        with self._condition:
            self._request_id += 1
            self._active = False
            self._shutdown_requested = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)

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
        running: bool | None = None,
        request_id: int,
    ) -> bool:
        with self._condition:
            # A canceled or superseded request must never publish over the
            # current UI state after a slow capture or OCR pass returns.
            if self._shutdown_requested or not self._active or request_id != self._request_id:
                return False
            next_running = self._active if running is None else running
            self._active = next_running
            generation = self._snapshot.generation + (1 if advance else 0)
            self._snapshot = MonitorSnapshot(
                running=next_running,
                stage=stage,
                message=message,
                generation=generation,
                observation=copy.deepcopy(observation),
            )
            if not next_running:
                self._condition.notify_all()
            return True

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

    def _request_is_active(self, request_id: int) -> bool:
        with self._lock:
            return not self._shutdown_requested and self._active and request_id == self._request_id

    def _wait_for_poll(self, request_id: int, poll_seconds: float) -> bool:
        with self._condition:
            self._condition.wait_for(
                lambda: self._shutdown_requested or not self._active or request_id != self._request_id,
                timeout=poll_seconds,
            )
            return not self._shutdown_requested and self._active and request_id == self._request_id

    def _close_capturer(self) -> None:
        close = getattr(self._capturer, "close", None)
        if callable(close):
            close()

    def _serve_request(self, request_id: int) -> None:
        poll_seconds = float(self.profile.capture["poll_seconds"])
        title = str(self.profile.capture["window_title"])
        while self._request_is_active(request_id):
            try:
                frame = self._capturer(window_title=title)
                decision = self._gate.observe(frame.image)
                if decision == "accepted":
                    self._publish(
                        "recognizing",
                        "检测到稳定的新画面，正在识别…",
                        request_id=request_id,
                    )
                    observation = self._reader.inspect(frame)
                    payload = observation.to_payload()
                    if observation.status != "not_target":
                        self._persist_latest(frame, observation)
                    messages = {
                        "not_target": (
                            f"已经看到 Dota，但还不是完整的 {self.profile.period.title()} Roll 页面；"
                            "继续等待。"
                        ),
                        "incomplete": "识别到 Roll 页面，但仍有字段需要人工确认。",
                        "confirmed": "完整画面已确认，准备自动录入并重新计算。",
                        "error": "识别器返回错误状态。",
                    }
                    if observation.status == "not_target":
                        self._publish(
                            "capturing",
                            messages["not_target"],
                            advance=False,
                            request_id=request_id,
                        )
                    else:
                        self._publish(
                            observation.status,
                            messages[observation.status],
                            observation=payload,
                            running=False,
                            request_id=request_id,
                        )
                        return
                elif decision == "unstable":
                    self._publish(
                        "capturing",
                        "画面仍在变化，等待稳定后再识别…",
                        advance=False,
                        request_id=request_id,
                    )
            except ScreenCaptureError as error:
                self._publish(
                    "capturing",
                    f"等待 Dota 画面：{error}",
                    advance=False,
                    request_id=request_id,
                )
            except (OSError, RuntimeError, ValueError) as error:
                self._publish("error", str(error), request_id=request_id)
            if not self._wait_for_poll(request_id, poll_seconds):
                return

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._shutdown_requested or self._active)
                    if self._shutdown_requested:
                        return
                    request_id = self._request_id
                try:
                    self._serve_request(request_id)
                except Exception as error:  # noqa: BLE001 - keep the persistent worker alive
                    self._publish(
                        "error",
                        f"识别线程错误：{error}",
                        running=False,
                        request_id=request_id,
                    )
                finally:
                    # WinRT capture resources are both created and released on
                    # this one persistent owner thread. Between requests the
                    # worker sleeps and performs no screen capture.
                    self._close_capturer()
        finally:
            self._close_capturer()


def observation_widget_updates(
    observation: dict[str, Any],
    rules: RollRuleSet,
    *,
    period: Literal["group", "main"] = "group",
    key_prefix: str = "current_advisor",
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    state_payload = observation.get("state")
    if isinstance(state_payload, dict) and state_payload.get("period", period) != period:
        return updates
    slot_count, max_rolls = {"group": (3, 40), "main": (5, 30)}[period]
    positive_operations = {item.operation_id for item in rules.offered_operations}
    fields = observation.get("fields", [])
    unsafe_banner_roles = {
        match.group(1)
        for reading in fields
        if reading.get("status") != "confirmed"
        and (
            match := re.fullmatch(
                r"banner\.(core|mid|support)\.\d\.stat",
                str(reading.get("field_id", "")),
            )
        )
    }
    for reading in fields:
        if reading.get("status") != "confirmed":
            continue
        field_id = str(reading.get("field_id", ""))
        value = reading.get("value")
        banner_match = re.fullmatch(r"banner\.(core|mid|support)\.(\d)\.(stat|quality|trait)", field_id)
        if banner_match:
            role, index_text, attribute = banner_match.groups()
            if role in unsafe_banner_roles:
                continue
            index = int(index_text)
            if index >= slot_count:
                continue
            if attribute == "stat" and value not in rules.stats_for(rules.colors_for(role)[index]):
                continue
            if attribute == "quality" and value not in {1, 2, 3, 4, 5}:
                continue
            if attribute == "trait" and value not in rules.traits:
                continue
            updates[f"{key_prefix}_{role}_{index}_{attribute}"] = value
            continue
        offer_match = re.fullmatch(r"offer\.(\d)", field_id)
        if offer_match and int(offer_match.group(1)) < 3 and value in positive_operations:
            updates[f"{key_prefix}_offer_{offer_match.group(1)}"] = value
        elif field_id == "remaining_rolls" and isinstance(value, int) and 0 <= value <= max_rolls:
            updates[f"{key_prefix}_remaining"] = value
    return updates
