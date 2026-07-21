#!/usr/bin/env python3
"""Shot inventory consistency — fail closed on partial sets (cn/codex sediment).

film-spec shot ids must match registered approved clips (and VO stems when required).
Prevents indexing past missing segments into a silent partial final.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


class InventoryError(RuntimeError):
    pass


def _as_id_list(values: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        sid = str(v).strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def check_shot_inventory(
    shot_ids: Iterable[Any],
    approved_clip_ids: Iterable[Any],
    *,
    vo_stem_ids: Iterable[Any] | None = None,
    require_vo: bool = False,
) -> dict[str, Any]:
    """Compare film-spec shots vs approved clips (and optional VO stems).

    Rules:
    - Empty shot list → not ok (no inventory to protect) with code NO_SHOTS
    - Partial clips (some approved, not all / extras) → not ok INVENTORY_MISMATCH
    - Zero approved when shots exist → ok=False with code CLIPS_INCOMPLETE (early stage;
      preflight maps severity)
    - require_vo: VO stem set must equal shot set
    """
    shots = _as_id_list(shot_ids)
    clips = _as_id_list(approved_clip_ids)
    vo = _as_id_list(vo_stem_ids) if vo_stem_ids is not None else None

    shot_set = set(shots)
    clip_set = set(clips)
    missing_clips = [s for s in shots if s not in clip_set]
    extra_clips = [c for c in clips if c not in shot_set]

    codes: list[str] = []
    issues: list[dict[str, Any]] = []

    if not shots:
        codes.append("NO_SHOTS")
        issues.append(
            {
                "code": "NO_SHOTS",
                "message": "film-spec has no shot ids — cannot validate inventory",
            }
        )
        return {
            "ok": False,
            "complete": False,
            "partial": False,
            "shot_count": 0,
            "approved_clip_count": len(clips),
            "missing_clips": [],
            "extra_clips": clips,
            "missing_vo": [],
            "extra_vo": [],
            "codes": codes,
            "issues": issues,
            "require_vo": require_vo,
        }

    complete = not missing_clips and not extra_clips
    partial = bool(clips) and not complete

    if missing_clips or extra_clips:
        codes.append("INVENTORY_MISMATCH")
        issues.append(
            {
                "code": "INVENTORY_MISMATCH",
                "message": (
                    f"shot set ≠ approved clips: missing={missing_clips} extra={extra_clips}"
                ),
                "missing_clips": missing_clips,
                "extra_clips": extra_clips,
            }
        )
    if missing_clips and not clips:
        codes.append("CLIPS_INCOMPLETE")
        issues.append(
            {
                "code": "CLIPS_INCOMPLETE",
                "message": f"no approved clips yet; expected {len(shots)} shots",
                "missing_clips": missing_clips,
            }
        )
    elif missing_clips:
        codes.append("CLIPS_INCOMPLETE")

    missing_vo: list[str] = []
    extra_vo: list[str] = []
    if require_vo or vo is not None:
        vo_list = vo if vo is not None else []
        vo_set = set(vo_list)
        missing_vo = [s for s in shots if s not in vo_set]
        extra_vo = [v for v in vo_list if v not in shot_set]
        if require_vo and (missing_vo or extra_vo):
            codes.append("VO_INVENTORY_MISMATCH")
            issues.append(
                {
                    "code": "VO_INVENTORY_MISMATCH",
                    "message": (
                        f"shot set ≠ VO stems: missing={missing_vo} extra={extra_vo}"
                    ),
                    "missing_vo": missing_vo,
                    "extra_vo": extra_vo,
                }
            )

    # ok only when fully complete (and VO if required)
    ok = complete and (not require_vo or (not missing_vo and not extra_vo))
    # de-dupe codes preserving order
    seen_c: set[str] = set()
    uniq_codes: list[str] = []
    for c in codes:
        if c not in seen_c:
            seen_c.add(c)
            uniq_codes.append(c)

    return {
        "ok": ok,
        "complete": complete and (not require_vo or not missing_vo),
        "partial": partial,
        "shot_count": len(shots),
        "approved_clip_count": len(clips),
        "missing_clips": missing_clips,
        "extra_clips": extra_clips,
        "missing_vo": missing_vo,
        "extra_vo": extra_vo,
        "codes": uniq_codes,
        "issues": issues,
        "require_vo": require_vo,
        "shot_ids": shots,
        "approved_clip_ids": clips,
    }


def discover_vo_stem_ids(root: Path) -> list[str]:
    """Find per-shot VO stems under common final work / audio dirs."""
    root = Path(root).expanduser().resolve()
    candidates: list[Path] = [
        root / "out" / "_final_work" / "vo",
        root / "audio" / "vo",
        root / "audio" / "stems",
        root / "receipts" / "tts-rehearsal-audio",
    ]
    found: set[str] = set()
    for d in candidates:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if not p.is_file():
                continue
            name = p.name
            # shot01.wav / shot01.mp3 / shot01_vo.wav
            stem = p.stem
            if stem.endswith("_vo"):
                stem = stem[: -len("_vo")]
            if stem.startswith("shot") or stem.startswith("s"):
                found.add(stem)
    return sorted(found)


def assert_inventory_for_final(
    shot_ids: Iterable[Any],
    approved_clip_ids: Iterable[Any],
    *,
    vo_stem_ids: Iterable[Any] | None = None,
    require_vo: bool = False,
) -> dict[str, Any]:
    """Hard fail when inventory is incomplete or mismatched (final/assemble gate)."""
    report = check_shot_inventory(
        shot_ids,
        approved_clip_ids,
        vo_stem_ids=vo_stem_ids,
        require_vo=require_vo,
    )
    if not report["ok"]:
        raise InventoryError(
            "shot inventory not complete for final/assemble: "
            + ",".join(report.get("codes") or ["INVENTORY"])
            + f" missing_clips={report.get('missing_clips')} "
            + f"extra_clips={report.get('extra_clips')}"
            + (
                f" missing_vo={report.get('missing_vo')}"
                if require_vo
                else ""
            )
        )
    return report
