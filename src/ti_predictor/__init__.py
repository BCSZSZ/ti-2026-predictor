"""TI 2026 in-game Predictions and Fantasy decision support."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ti-predictor")
except PackageNotFoundError:  # pragma: no cover - editable source tree
    __version__ = "0.1.0"

__all__ = ["__version__"]
