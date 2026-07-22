"""Story idea → draft Drama Graph planning route."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from story_plan import run_plan


class PlanRunError(RuntimeError):
    """A source or planning input error."""


def run(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    file_path = getattr(args, "file", None)
    if file_path:
        source = Path(str(file_path)).expanduser().resolve()
        if not source.is_file():
            raise PlanRunError(f"plan source file not found: {source}")
        raw = source.read_text(encoding="utf-8")
    else:
        text = getattr(args, "text", None)
        if text is None or not str(text).strip():
            raise PlanRunError("plan requires --text or --file")
        raw = str(text)
    report = run_plan(
        root,
        raw,
        title=getattr(args, "title", None),
        target_duration=float(getattr(args, "target_duration", 45) or 45),
        apply_film_spec=bool(getattr(args, "apply_film_spec", False))
        and not bool(getattr(args, "no_film_spec", False)),
        force=bool(getattr(args, "force", False)),
        source_path=str(file_path or ""),
        seed_bible=not bool(getattr(args, "no_bible", False)),
    )
    return report, 0 if report.get("ok") else 1
