"""CLI adapter for story normalization."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from story_plan import normalize_story
from util import write_json


class PlanNormalizeError(RuntimeError):
    """User-facing normalization error."""


def run(args: Namespace, root: Path | None = None) -> tuple[dict[str, Any], int]:
    """Normalize inline/file story input and optionally persist its receipt."""
    file_value = getattr(args, "file", None)
    text_value = getattr(args, "text", None)
    if file_value:
        source = Path(str(file_value)).expanduser().resolve()
        if not source.is_file():
            raise PlanNormalizeError(f"plan source file not found: {source}")
        raw = source.read_text(encoding="utf-8")
        source_path = str(source)
    elif text_value is not None and str(text_value).strip():
        raw = str(text_value)
        source_path = ""
    else:
        raise PlanNormalizeError("plan requires --text or --file")

    normalized = normalize_story(
        raw,
        title_hint=getattr(args, "title", None),
        source_path=source_path,
    )
    if root is None:
        return {"ok": True, "action": "normalize", "story": normalized}, 0

    root.mkdir(parents=True, exist_ok=True)
    receipts = root / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    output = receipts / "story-normalize.json"
    write_json(output, normalized)
    return {
        "ok": True,
        "action": "normalize",
        "path": str(output),
        "story": normalized,
    }, 0
