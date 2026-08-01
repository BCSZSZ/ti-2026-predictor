from __future__ import annotations

import re
from pathlib import Path
from typing import Any

QUALITY_PATTERN = re.compile(r"(?:品质|quality)?\s*([1-5一二三四五])", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")


def parse_ocr_lines(lines: list[str]) -> dict[str, Any]:
    quality_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
    parsed: list[dict[str, Any]] = []
    for line in lines:
        quality_match = QUALITY_PATTERN.search(line)
        percent_match = PERCENT_PATTERN.search(line)
        quality = None
        if quality_match:
            token = quality_match.group(1)
            quality = quality_map.get(token, int(token) if token.isdigit() else None)
        parsed.append(
            {
                "text": line,
                "quality_tier": quality,
                "percent": float(percent_match.group(1)) if percent_match else None,
                "requires_confirmation": True,
            }
        )
    return {"status": "draft", "lines": parsed, "requires_user_confirmation": True}


def inspect_screenshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        from rapidocr import RapidOCR
    except ImportError as error:  # pragma: no cover - optional dependency
        raise RuntimeError("OCR dependencies are not installed; run `uv sync --extra ocr`") from error
    engine = RapidOCR()
    output = engine(str(path))
    if hasattr(output, "txts"):
        texts = [str(value) for value in output.txts]
        scores = [float(value) for value in getattr(output, "scores", [])]
    else:  # compatibility with RapidOCR 2.x tuple output
        result = output[0] if isinstance(output, tuple) else output
        texts = [str(item[1]) for item in result or []]
        scores = [float(item[2]) for item in result or []]
    parsed = parse_ocr_lines(texts)
    parsed["image"] = str(path.resolve())
    parsed["confidence"] = scores
    return parsed
