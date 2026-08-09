from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from ti_predictor.fantasy.current_advisor import load_current_advisor_roll_rules
from ti_predictor.fantasy.live_ocr import (
    CapturedFrame,
    LiveRollMonitor,
    OCRToken,
    RollScreenObservation,
    StableFrameGate,
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

    def resize(self, size: tuple[int, int]) -> FakeImage:
        return FakeImage(self.value, size)

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

    assert set(profile.operations) == {
        operation.operation_id for operation in rules.offered_operations
    }


def test_stop_prevents_a_slow_recognition_from_overwriting_idle_state() -> None:
    profile = load_live_ocr_profile()
    profile.capture["stable_frame_count"] = 1
    profile.capture["poll_seconds"] = 0.01
    entered = threading.Event()
    release = threading.Event()

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
        reader=BlockingReader(),  # type: ignore[arg-type]
    )
    monitor.start()
    assert entered.wait(timeout=2)
    monitor.stop(join_timeout=0.01)
    stopped_generation = monitor.snapshot().generation

    # start() must remain a no-op while the previous worker is still alive.
    monitor.start()
    assert monitor.snapshot().stage == "idle"
    release.set()
    assert monitor._thread is not None  # noqa: SLF001 - lifecycle regression test
    monitor._thread.join(timeout=2)  # noqa: SLF001 - lifecycle regression test

    snapshot = monitor.snapshot()
    assert snapshot.stage == "idle"
    assert snapshot.generation == stopped_generation
