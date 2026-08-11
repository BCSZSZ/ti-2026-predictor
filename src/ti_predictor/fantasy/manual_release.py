"""Compatibility names for the former manual-only release API.

New code must import :mod:`ti_predictor.fantasy.solver_release`; the runtime
bundle is shared by both manual and OCR consumers.
"""

from ti_predictor.fantasy.solver_release import (
    SolverReleaseWriteResult,
    default_manual_release_path,
    load_manual_release_context,
    manual_release_team_options,
    write_manual_release_bundle,
)

ManualReleaseWriteResult = SolverReleaseWriteResult

__all__ = [
    "ManualReleaseWriteResult",
    "default_manual_release_path",
    "load_manual_release_context",
    "manual_release_team_options",
    "write_manual_release_bundle",
]
