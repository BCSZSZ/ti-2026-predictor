from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from ti_predictor.fantasy.current_advisor import load_current_advisor_roll_rules
from ti_predictor.fantasy.live_ocr import (
    CapturedFrame,
    LiveRollMonitor,
    OCRToken,
    RollScreenObservation,
    RollScreenReader,
    ScreenCaptureError,
    StableFrameGate,
    _select_dxcam_output,
    load_live_ocr_profile,
    observation_widget_updates,
    parse_roll_screen_tokens,
)


class FakeImage:
    def __init__(self, value: int, size: tuple[int, int] = (2560, 1440)) -> None:
        self.value = value
        self.size = size
        self.width, self.height = size

    def convert(self, _mode: str) -> FakeImage:
        return self

    def resize(self, size: tuple[int, int], **_kwargs) -> FakeImage:
        return FakeImage(self.value, size)

    def crop(self, box: tuple[int, int, int, int]) -> FakeImage:
        return FakeImage(self.value, (box[2] - box[0], box[3] - box[1]))

    def save(self, path, **_kwargs) -> None:
        path.write_bytes(self.tobytes())

    def tobytes(self) -> bytes:
        return bytes([self.value]) * (self.width * self.height)


def _token(text: str, confidence: float, x: float, y: float, *, width: float = 0.1) -> OCRToken:
    return OCRToken(
        text=text,
        confidence=confidence,
        box=(x - width / 2, y - 0.015, x + width / 2, y + 0.015),
    )


def _complete_tokens(*, weak_field: str | None = None) -> tuple[OCRToken, ...]:
    tokens: list[OCRToken] = []
    roles = {
        "core": (0.2, ("Kills", "Stuns", "GPM")),
        "mid": (0.5, ("Deaths", "Obs Wards Planted", "First Blood")),
        "support": (0.8, ("Camps Stacked", "Tormentor Kills", "Smokes Used")),
    }
    role_labels = {"core": "Core", "mid": "Mid", "support": "Support"}
    qualities = ("Tier I", "Tier II", "Tier III")
    traits = ("Friendly", "Vampiric", "Unique")
    for role, (x, stats) in roles.items():
        tokens.append(_token(role_labels[role], 0.99, x, 0.08))
        for index, (stat, quality, trait) in enumerate(zip(stats, qualities, traits, strict=True)):
            y = 0.2 + index * 0.16
            tokens.append(_token(stat, 0.98, x, y, width=0.12))
            quality_id = f"{role}.{index}.quality"
            tokens.append(
                _token(quality, 0.5 if weak_field == quality_id else 0.98, x - 0.04, y + 0.04)
            )
            tokens.append(_token(trait, 0.98, x + 0.04, y + 0.07))
    tokens.extend(
        (
            _token("Reroll Quality for Red Emblems", 0.98, 0.34, 0.74, width=0.2),
            _token("Randomly increase one Quality", 0.98, 0.5, 0.74, width=0.18),
            _token("Reroll Stat for Green Emblems", 0.98, 0.66, 0.74, width=0.2),
            _token("Roll Tokens: 37", 0.99, 0.5, 0.88, width=0.12),
        )
    )
    return tuple(tokens)


def _complete_schinese_tokens() -> tuple[OCRToken, ...]:
    tokens: list[OCRToken] = []
    roles = {
        "core": (0.2, ("击杀数", "眩晕时间", "GPM")),
        "mid": (0.5, ("死亡数", "放置侦察守卫数", "第一滴血")),
        "support": (0.8, ("野怪堆叠次数", "痛苦魔方消灭次数", "开雾次数")),
    }
    role_labels = {"core": "核心", "mid": "中单", "support": "辅助"}
    qualities = ("第1阶", "第2阶", "第3阶")
    traits = ("友好", "吸血鬼", "唯一")
    for role, (x, stats) in roles.items():
        tokens.append(_token(role_labels[role], 0.99, x, 0.08))
        for index, (stat, quality, trait) in enumerate(zip(stats, qualities, traits, strict=True)):
            y = 0.2 + index * 0.16
            tokens.append(_token(stat, 0.98, x, y, width=0.12))
            tokens.append(_token(quality, 0.98, x - 0.04, y + 0.04))
            tokens.append(_token(trait, 0.98, x + 0.04, y + 0.07))
    tokens.extend(
        (
            _token("重新生成红色徽标的品质", 0.98, 0.34, 0.74, width=0.2),
            _token("随机提升一项品质", 0.98, 0.5, 0.74, width=0.18),
            _token("重新生成绿色徽标的统计数据", 0.98, 0.66, 0.74, width=0.2),
            _token("重选代币：37", 0.99, 0.5, 0.88, width=0.12),
        )
    )
    return tuple(tokens)


def _current_client_layout_tokens() -> tuple[OCRToken, ...]:
    """Tokens shaped like the current 16:9 client, including multiline Stat labels."""

    tokens = [
        # The full Dota page also contains SUPPORT in the left navigation. It
        # must not replace the three aligned banner headings.
        _token("Support", 0.99, 0.08, 0.40),
        _token("Core", 0.98, 0.20, 0.08),
        _token("Mid", 0.98, 0.50, 0.08),
        _token("Support", 0.98, 0.80, 0.08),
    ]
    cards = {
        "core": (
            0.20,
            (
                (("Tower Kills",), "Tier II", "Unique"),
                (("Teamfight",), "Tier IV", "Vampiric"),
                (("Deaths",), "Tier V", "Benevolent"),
            ),
        ),
        "mid": (
            0.50,
            (
                (("Kills",), "Tier I", "Fractal"),
                (("Camps Stacked",), "Tier V", "Unique"),
                (("Stuns",), "Tier II", "Benevolent"),
            ),
        ),
        "support": (
            0.80,
            (
                (("Watchers", "Taken"), "Tier II", "Unique"),
                (("Tormentor", "Kills"), "Tier III", "Friendly"),
                (("Smokes Used",), "Tier II", "Fractal"),
            ),
        ),
    }
    for _role, (x, rows) in cards.items():
        for index, (stat_lines, quality, trait) in enumerate(rows):
            stat_y = 0.20 + index * 0.12
            if len(stat_lines) == 1:
                tokens.append(_token(stat_lines[0], 0.98, x, stat_y, width=0.12))
            else:
                tokens.append(_token(stat_lines[0], 0.98, x, stat_y - 0.008, width=0.12))
                tokens.append(_token(stat_lines[1], 0.98, x, stat_y + 0.008, width=0.12))
            tokens.append(_token(quality, 0.98, x, stat_y + 0.035))
            tokens.append(_token(trait, 0.98, x, stat_y + 0.065))
    tokens.extend(
        (
            _token("Reroll Trait for Red Emblems", 0.98, 0.34, 0.74, width=0.2),
            _token("Reroll Quality for One random Red Emblem", 0.98, 0.50, 0.74, width=0.24),
            _token("Reroll Trait for One random Blue Emblem", 0.98, 0.66, 0.74, width=0.24),
            _token("Roll Tokens: 33", 0.99, 0.50, 0.88, width=0.12),
        )
    )
    return tuple(tokens)


def _parse(tokens: tuple[OCRToken, ...], *, captured_at: datetime | None = None):
    return parse_roll_screen_tokens(
        tokens,
        captured_at=captured_at or datetime(2026, 8, 9, 6, 0, tzinfo=UTC),
        image_sha256="a" * 64,
        viewport=(2560, 1440),
        profile=load_live_ocr_profile(),
        rules=load_current_advisor_roll_rules(),
    )


def test_stable_frame_gate_accepts_only_stable_meaningful_changes() -> None:
    gate = StableFrameGate(
        signature_width=4,
        signature_height=2,
        stable_frame_count=2,
        stable_mean_difference=2.0,
        meaningful_mean_difference=1.0,
    )
    assert gate.observe(FakeImage(10)) == "unstable"
    assert gate.observe(FakeImage(10)) == "accepted"
    assert gate.observe(FakeImage(10)) == "duplicate"
    assert gate.observe(FakeImage(30)) == "unstable"
    assert gate.observe(FakeImage(30)) == "accepted"


def test_dxcam_output_is_selected_by_exact_dota_monitor_handle() -> None:
    class Output:
        def __init__(self, handle: int) -> None:
            self.hmonitor = handle

    factory = type("Factory", (), {"outputs": [[Output(101), Output(202)], [Output(303)]]})()

    device_index, output_index, output = _select_dxcam_output(factory, 202)

    assert (device_index, output_index, output.hmonitor) == (0, 1, 202)


def test_complete_structured_tokens_build_a_valid_group_roll_state() -> None:
    observation = _parse(_complete_tokens())

    assert observation.status == "confirmed"
    assert observation.missing_field_ids == ()
    assert observation.state is not None
    assert observation.state.remaining_rolls == 37
    assert observation.state.offer.operation_ids == (9, 23, 17)
    assert [emblem.stat_id for emblem in observation.state.banners[0].emblems] == [
        "kills",
        "stuns",
        "gpm",
    ]
    assert [emblem.quality_tier for emblem in observation.state.banners[1].emblems] == [1, 2, 3]
    assert [emblem.trait_id for emblem in observation.state.banners[2].emblems] == [
        "friendly",
        "vampiric",
        "unique",
    ]


def test_complete_simplified_chinese_tokens_build_the_same_valid_state() -> None:
    observation = _parse(_complete_schinese_tokens())

    assert observation.status == "confirmed"
    assert observation.missing_field_ids == ()
    assert observation.state is not None
    assert observation.state.remaining_rolls == 37
    assert observation.state.offer.operation_ids == (9, 23, 17)
    assert [emblem.stat_id for emblem in observation.state.banners[0].emblems] == [
        "kills",
        "stuns",
        "gpm",
    ]


def test_current_client_multiline_layout_builds_the_exact_visible_state() -> None:
    observation = _parse(_current_client_layout_tokens())

    assert observation.status == "confirmed"
    assert observation.missing_field_ids == ()
    assert observation.state is not None
    assert observation.state.remaining_rolls == 33
    assert observation.state.offer.operation_ids == (10, 25, 28)
    assert [
        [(emblem.stat_id, emblem.quality_tier, emblem.trait_id) for emblem in banner.emblems]
        for banner in observation.state.banners
    ] == [
        [
            ("tower_kills", 2, "unique"),
            ("teamfight_participation", 4, "vampiric"),
            ("deaths", 5, "benevolent"),
        ],
        [
            ("kills", 1, "fractal"),
            ("camps_stacked", 5, "unique"),
            ("stuns", 2, "benevolent"),
        ],
        [
            ("watchers_taken", 2, "unique"),
            ("tormentor_kills", 3, "friendly"),
            ("smokes_used", 2, "fractal"),
        ],
    ]


def test_reader_locates_and_upscales_fantasy_region_before_detailed_ocr() -> None:
    class SequencedEngine:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple[int, int], int]] = []

        def extract(self, image: FakeImage, *, maximum_width: int) -> tuple[OCRToken, ...]:
            self.calls.append((image.size, maximum_width))
            if len(self.calls) == 1:
                return (
                    _token("Support", 0.99, 0.08, 0.40),
                    _token("Core", 0.98, 0.29, 0.27),
                    _token("Mid", 0.98, 0.54, 0.27),
                    _token("Support", 0.98, 0.79, 0.27),
                )
            return _current_client_layout_tokens()

    engine = SequencedEngine()
    frame = CapturedFrame(
        image=FakeImage(10, (2048, 1152)),
        captured_at=datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
        image_sha256="a" * 64,
        window_title="Dota 2",
    )
    observation = RollScreenReader(
        profile=load_live_ocr_profile(),
        rules=load_current_advisor_roll_rules(),
        token_engine=engine,
    ).inspect(frame)

    assert observation.status == "confirmed"
    assert engine.calls[0] == ((2048, 1152), 1280)
    assert engine.calls[1][0][0] == 2560
    assert engine.calls[1][1] == 2560
    core_stat = next(field for field in observation.fields if field.field_id == "banner.core.0.stat")
    assert core_stat.evidence_box is not None
    assert 0.28 < core_stat.evidence_box[0] < 0.31


def test_low_confidence_field_allows_partial_autofill_but_blocks_auto_calculation() -> None:
    observation = _parse(_complete_tokens(weak_field="mid.1.quality"))

    assert observation.status == "incomplete"
    assert observation.state is None
    assert "banner.mid.1.quality" in observation.missing_field_ids
    updates = observation_widget_updates(
        observation.to_payload(),
        load_current_advisor_roll_rules(),
    )
    assert "current_advisor_mid_1_quality" not in updates
    assert updates["current_advisor_mid_1_stat"] == "wards_placed"
    assert updates["current_advisor_remaining"] == 37


def test_non_roll_screen_never_yields_advisor_fields() -> None:
    observation = _parse(
        (
            _token("Stat", 0.99, 0.1, 0.1),
            _token("Current", 0.99, 0.2, 0.1),
            _token("Earth Spirit", 0.99, 0.5, 0.5),
        )
    )

    assert observation.status == "not_target"
    assert observation.fields == ()
    assert observation.state is None


def test_observation_semantic_hash_ignores_capture_time_and_image_identity() -> None:
    first = _parse(_complete_tokens())
    second = parse_roll_screen_tokens(
        _complete_tokens(),
        captured_at=first.captured_at + timedelta(seconds=30),
        image_sha256="b" * 64,
        viewport=(2560, 1440),
        profile=load_live_ocr_profile(),
        rules=load_current_advisor_roll_rules(),
    )

    assert first.to_payload()["observation_sha256"] == second.to_payload()["observation_sha256"]


def test_confirmed_observation_maps_to_all_advisor_widget_keys() -> None:
    observation = _parse(_complete_tokens())
    updates = observation_widget_updates(
        observation.to_payload(),
        load_current_advisor_roll_rules(),
    )

    assert len(updates) == 31
    assert updates["current_advisor_core_0_stat"] == "kills"
    assert updates["current_advisor_offer_1"] == 23
    assert updates["current_advisor_remaining"] == 37


def test_ocr_profile_covers_every_current_positive_weight_offer() -> None:
    profile = load_live_ocr_profile()
    rules = load_current_advisor_roll_rules()

    assert profile.language_priority == ("en", "zh-Hans")
    assert set(profile.operations) == {
        operation.operation_id for operation in rules.offered_operations
    }


def test_stop_prevents_a_slow_recognition_from_overwriting_idle_state() -> None:
    profile = load_live_ocr_profile()
    profile.capture["stable_frame_count"] = 1
    profile.capture["poll_seconds"] = 0.01
    entered = threading.Event()
    release = threading.Event()
    request_closed = threading.Event()

    class BlockingReader:
        def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
            entered.set()
            assert release.wait(timeout=2)
            return RollScreenObservation(
                status="not_target",
                captured_at=frame.captured_at,
                image_sha256=frame.image_sha256,
                viewport=frame.viewport,
                profile_id=profile.profile_id,
            )

    class Capturer:
        def __call__(self, **_kwargs) -> CapturedFrame:
            return CapturedFrame(
                image=FakeImage(10),
                captured_at=datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
                image_sha256="a" * 64,
                window_title="Dota 2",
            )

        def close(self) -> None:
            request_closed.set()

    monitor = LiveRollMonitor(
        profile=profile,
        rules=load_current_advisor_roll_rules(),
        capturer=Capturer(),
        reader=BlockingReader(),  # type: ignore[arg-type]
    )
    try:
        monitor.start_once()
        assert entered.wait(timeout=2)
        monitor.stop(join_timeout=0.01)
        stopped_generation = monitor.snapshot().generation
        release.set()
        assert request_closed.wait(timeout=2)

        snapshot = monitor.snapshot()
        assert snapshot.stage == "idle"
        assert snapshot.generation == stopped_generation
    finally:
        monitor.shutdown()


def test_one_shot_waits_through_minimized_and_non_target_then_stops_after_result(tmp_path) -> None:
    profile = load_live_ocr_profile()
    profile.capture["stable_frame_count"] = 1
    profile.capture["poll_seconds"] = 0.01
    recognized = threading.Event()

    class SequencedCapturer:
        def __init__(self) -> None:
            self.calls = 0
            self.closed = False

        def __call__(self, **_kwargs) -> CapturedFrame:
            self.calls += 1
            if self.calls == 1:
                raise ScreenCaptureError("Dota 2 窗口已最小化；请先恢复窗口。")
            value = 10 if self.calls <= 3 else 30
            return CapturedFrame(
                image=FakeImage(value),
                captured_at=datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
                image_sha256="a" * 64,
                window_title="Dota 2",
            )

        def close(self) -> None:
            self.closed = True

    class ConfirmedReader:
        def __init__(self) -> None:
            self.calls = 0

        def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
            self.calls += 1
            if self.calls == 1:
                return RollScreenObservation(
                    status="not_target",
                    captured_at=frame.captured_at,
                    image_sha256=frame.image_sha256,
                    viewport=frame.viewport,
                    profile_id=profile.profile_id,
                )
            recognized.set()
            return _parse(_complete_tokens(), captured_at=frame.captured_at)

    capturer = SequencedCapturer()
    reader = ConfirmedReader()
    monitor = LiveRollMonitor(
        profile=profile,
        rules=load_current_advisor_roll_rules(),
        capturer=capturer,
        reader=reader,  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )

    try:
        monitor.start_once()
        assert recognized.wait(timeout=2)
        assert _wait_until(lambda: capturer.closed)

        snapshot = monitor.snapshot()
        assert snapshot.stage == "confirmed"
        assert snapshot.running is False
        assert snapshot.observation is not None
        assert snapshot.observation["status"] == "confirmed"
        assert capturer.calls == 4
        assert reader.calls == 2
    finally:
        monitor.shutdown()


def test_one_shot_stops_after_an_incomplete_target_observation(tmp_path) -> None:
    profile = load_live_ocr_profile()
    profile.capture["stable_frame_count"] = 1
    profile.capture["poll_seconds"] = 0.01
    recognized = threading.Event()

    class IncompleteReader:
        def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
            recognized.set()
            return _parse(
                _complete_tokens(weak_field="mid.1.quality"),
                captured_at=frame.captured_at,
            )

    def capture(**_kwargs) -> CapturedFrame:
        return CapturedFrame(
            image=FakeImage(10),
            captured_at=datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
            image_sha256="a" * 64,
            window_title="Dota 2",
        )

    monitor = LiveRollMonitor(
        profile=profile,
        rules=load_current_advisor_roll_rules(),
        capturer=capture,
        reader=IncompleteReader(),  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )

    try:
        monitor.start_once()
        assert recognized.wait(timeout=2)
        assert _wait_until(lambda: not monitor.snapshot().running)

        snapshot = monitor.snapshot()
        assert snapshot.stage == "incomplete"
        assert snapshot.running is False
        assert snapshot.observation is not None
        assert "banner.mid.1.quality" in snapshot.observation["missing_field_ids"]
    finally:
        monitor.shutdown()


def _wait_until(predicate, *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def test_sequential_one_shot_requests_reuse_one_worker_thread(tmp_path) -> None:
    profile = load_live_ocr_profile()
    profile.capture["stable_frame_count"] = 1
    profile.capture["poll_seconds"] = 0.01

    class ThreadTrackingCapturer:
        def __init__(self) -> None:
            self.calls = 0
            self.capture_threads: list[threading.Thread] = []
            self.close_threads: list[threading.Thread] = []

        def __call__(self, **_kwargs) -> CapturedFrame:
            self.calls += 1
            self.capture_threads.append(threading.current_thread())
            return CapturedFrame(
                image=FakeImage(10 + self.calls),
                captured_at=datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
                image_sha256=f"{self.calls:064x}",
                window_title="Dota 2",
            )

        def close(self) -> None:
            self.close_threads.append(threading.current_thread())

    class ConfirmedReader:
        def __init__(self) -> None:
            self.calls = 0

        def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
            self.calls += 1
            return _parse(_complete_tokens(), captured_at=frame.captured_at)

    capturer = ThreadTrackingCapturer()
    reader = ConfirmedReader()
    monitor = LiveRollMonitor(
        profile=profile,
        rules=load_current_advisor_roll_rules(),
        capturer=capturer,
        reader=reader,  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )

    try:
        monitor.start_once()
        assert _wait_until(lambda: len(capturer.close_threads) == 1)
        monitor.start_once()
        assert _wait_until(lambda: len(capturer.close_threads) == 2)

        worker_threads = capturer.capture_threads + capturer.close_threads
        assert len({id(thread) for thread in worker_threads}) == 1
        assert reader.calls == 2
        assert monitor._thread is not None  # noqa: SLF001 - lifecycle regression test
        assert monitor._thread.is_alive()  # noqa: SLF001 - lifecycle regression test
    finally:
        monitor.shutdown()


def test_cancelled_slow_request_can_rearm_on_the_same_worker(tmp_path) -> None:
    profile = load_live_ocr_profile()
    profile.capture["stable_frame_count"] = 1
    profile.capture["poll_seconds"] = 0.01
    first_entered = threading.Event()
    release_first = threading.Event()
    second_read = threading.Event()
    capture_threads: list[threading.Thread] = []

    class BlockingThenConfirmedReader:
        def __init__(self) -> None:
            self.calls = 0

        def inspect(self, frame: CapturedFrame) -> RollScreenObservation:
            self.calls += 1
            if self.calls == 1:
                first_entered.set()
                assert release_first.wait(timeout=2)
            else:
                second_read.set()
            return _parse(_complete_tokens(), captured_at=frame.captured_at)

    def capture(**_kwargs) -> CapturedFrame:
        capture_threads.append(threading.current_thread())
        value = 10 + len(capture_threads)
        return CapturedFrame(
            image=FakeImage(value),
            captured_at=datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
            image_sha256=f"{value:064x}",
            window_title="Dota 2",
        )

    monitor = LiveRollMonitor(
        profile=profile,
        rules=load_current_advisor_roll_rules(),
        capturer=capture,
        reader=BlockingThenConfirmedReader(),  # type: ignore[arg-type]
        cache_dir=tmp_path,
    )

    try:
        monitor.start_once()
        assert first_entered.wait(timeout=2)
        monitor.stop(join_timeout=0.01)
        monitor.start_once()
        release_first.set()

        assert second_read.wait(timeout=2)
        assert _wait_until(
            lambda: monitor.snapshot().stage == "confirmed"
            and not monitor.snapshot().running
        )
        assert len({id(thread) for thread in capture_threads}) == 1
    finally:
        monitor.shutdown()
