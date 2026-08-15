from __future__ import annotations

from pathlib import Path


def test_web_and_runtime_entrypoints_do_not_import_research_stack() -> None:
    root = Path(__file__).resolve().parents[1]
    production_entrypoints = (
        root / "src/ti_predictor/web_app.py",
        root / "src/ti_predictor/fantasy/main_advisor_ui.py",
        root / "src/ti_predictor/cli.py",
        root / "streamlit_app.py",
        root / "local_ocr_app.py",
    )

    for path in production_entrypoints:
        assert "main_roll_research" not in path.read_text(encoding="utf-8")


def test_research_configuration_is_outside_runtime_pointer_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    research_configs = (
        root / "config/research/fantasy-main-roll-simulator-v1.json",
        root / "config/research/fantasy-main-starting-state-coverage-v1.json",
        root / "config/research/fantasy-main-roll-bounded-challengers-v1.json",
        root / "config/research/fantasy-main-roll-bounded-challengers-v2.json",
    )
    runtime = root / "deploy/runtime"

    assert all(path.is_file() for path in research_configs)
    assert all(not path.resolve().is_relative_to(runtime.resolve()) for path in research_configs)
    assert not any("research" in path.name for path in runtime.iterdir())
