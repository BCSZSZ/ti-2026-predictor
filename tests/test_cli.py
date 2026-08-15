from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ti_predictor import cli


def test_player_web_is_a_single_current_runtime_entrypoint(monkeypatch) -> None:
    calls: list[tuple[Path, int]] = []
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(
        cli,
        "_run_streamlit",
        lambda entrypoint, *, port: calls.append((entrypoint, port)),
    )

    result = CliRunner().invoke(cli.app, ["web", "--port", "8765"])

    assert result.exit_code == 0
    assert calls == [(cli.PATHS.root / "local_ocr_app.py", 8765)]


def test_player_web_manual_mode_uses_the_public_entrypoint(monkeypatch) -> None:
    calls: list[tuple[Path, int]] = []
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(
        cli,
        "_run_streamlit",
        lambda entrypoint, *, port: calls.append((entrypoint, port)),
    )

    result = CliRunner().invoke(cli.app, ["web", "--manual"])

    assert result.exit_code == 0
    assert calls == [(cli.PATHS.root / "streamlit_app.py", 8501)]


def test_player_runtime_summary_automatically_loads_current_main_release() -> None:
    summary = cli._current_player_runtime_summary()

    assert summary["main_status"] in {"provisional", "ready"}
    assert summary["main_mode"] in {"projected", "actual"}
    assert summary["main_candidate_team_count"] in {8, 16}
    assert summary["main_entrant_team_count"] == 8
