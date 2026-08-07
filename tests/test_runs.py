from __future__ import annotations

import pytest

from ti_predictor.runs import ArtifactWriter


def test_artifact_writer_writes_text_immutably(project_paths) -> None:
    writer = ArtifactWriter("fantasy-text-fixture", project_paths)

    path = writer.write_text("report.md", "hello")

    assert path.read_text(encoding="utf-8") == "hello\n"
    assert writer.write_text("report.md", "hello") == path
    with pytest.raises(RuntimeError, match="immutable artifact differs"):
        writer.write_text("report.md", "changed")
