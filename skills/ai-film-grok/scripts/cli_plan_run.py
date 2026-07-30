"""Story idea → draft Drama Graph planning route."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from intake import validate_intake
from story_plan import run_plan
from story_reception import ReceptionError, load_story_reception


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
    production_mode = str(getattr(args, "production_mode", "shortform") or "shortform")
    target_duration = float(getattr(args, "target_duration", 45) or 45)
    if production_mode == "longform" and not 480 <= target_duration <= 900:
        raise PlanRunError("longform target duration must be within 480..900 seconds")
    received_file = getattr(args, "received_file", None)
    if bool(getattr(args, "received", False)):
        if received_file:
            raise PlanRunError("--received and --received-file are mutually exclusive")
        received_file = root / "receipts" / "story-reception.json"
        if not Path(received_file).is_file():
            raise PlanRunError(
                "canonical story reception is missing; run plan receive or pass --received-file"
            )
    if received_file:
        try:
            reception = load_story_reception(Path(str(received_file)))
        except ReceptionError as exc:
            raise PlanRunError(str(exc)) from exc
        from narrative_control import control_status

        if "story" in set(control_status(root).get("locked_scopes") or []):
            raise PlanRunError("story is locked; unlock story before applying a revised reception")
        source = reception["source"]
        return _run_raw(
            args,
            root,
            str(reception["treatment"]["planning_text"]),
            {},
            source_path=str(Path(str(received_file)).expanduser().resolve()),
            source_evidence_refs=[str(source["source_ref"])],
            reception=reception,
        )
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
    reception: dict[str, Any] | None = None,
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
        reception=reception,
        story_mode=str(getattr(args, "story_mode", "narrative") or "narrative"),
        production_mode=str(getattr(args, "production_mode", "shortform") or "shortform"),
    )
    return report, 0 if report.get("ok") else 1
