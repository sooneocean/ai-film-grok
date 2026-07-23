"""Story idea → draft Drama Graph planning route."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from intake import validate_intake
from story_plan import run_plan


class PlanRunError(RuntimeError):
    """A source or planning input error."""


def run_from_intake(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    """Plan a staged intake while preserving its reviewed character IDs."""
    root = Path(root).expanduser().resolve()
    intake = validate_intake(root, write_receipt=True)
    quality = intake.get("quality") or {}
    if not quality.get("ready_for_planning"):
        raise PlanRunError(
            "intake is not ready for planning: "
            + "; ".join(str(item) for item in intake.get("errors") or ["quality gate failed"])
        )
    story = (intake.get("story") or {}).get("evidence") or []
    raw = "\n\n".join(str(item.get("text") or "") for item in story).strip()
    if not raw:
        raise PlanRunError("intake story has no usable text")
    overrides = {
        str(item.get("name") or ""): str(item.get("id") or "")
        for item in intake.get("characters") or []
        if item.get("name") and item.get("id")
    }
    report, code = _run_raw(
        args,
        root,
        raw,
        overrides,
        source_path="intake-manifest.json",
        source_evidence_refs=[str(item.get("source_ref") or item.get("id")) for item in story],
    )
    report["intake"] = {
        "manifest": str(root / "intake-manifest.json"),
        "report": str(root / "receipts" / "intake-report.json"),
        "quality": quality,
    }
    return report, code


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
    return _run_raw(args, root, raw, {}, source_path=str(file_path or ""))


def _run_raw(
    args: Namespace,
    root: Path,
    raw: str,
    character_id_overrides: dict[str, str],
    *,
    source_path: str,
    source_evidence_refs: list[str] | None = None,
) -> tuple[dict[str, Any], int]:
    report = run_plan(
        root,
        raw,
        title=getattr(args, "title", None),
        target_duration=float(getattr(args, "target_duration", 45) or 45),
        apply_film_spec=bool(getattr(args, "apply_film_spec", False))
        and not bool(getattr(args, "no_film_spec", False)),
        force=bool(getattr(args, "force", False)),
        source_path=source_path,
        seed_bible=not bool(getattr(args, "no_bible", False)),
        character_id_overrides=character_id_overrides,
        source_evidence_refs=source_evidence_refs,
    )
    return report, 0 if report.get("ok") else 1
