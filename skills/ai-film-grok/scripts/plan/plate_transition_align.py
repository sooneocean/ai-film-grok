"""T4 · Align plate xfade join styles with transition_ops.picture.

When film-spec has transition_ops, the plate concat styles must match each op's
picture.style (soft/xfade) or hard_cut (no silent fade fallback).
"""

from __future__ import annotations

from typing import Any


def align_story_styles_to_transition_ops(
    ops: list[Any],
    story_styles: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return (aligned_styles, issues). Length preserved to len(story_styles).

    For each story seam i:
      - ops[i].picture.base == hard_cut → style kept as placeholder (not used by concat hard)
      - ops[i].picture.base == xfade → plate style must equal picture.style
      - missing style on xfade → issue PLATE_TRANSITION_STYLE_MISSING
      - mismatch → rewrite to ops style + issue PLATE_TRANSITION_STYLE_MISMATCH (informational)
    """
    issues: list[dict[str, Any]] = []
    n = len(story_styles)
    out = list(story_styles)
    if not isinstance(ops, list) or not ops:
        return out, issues

    for i in range(min(n, len(ops))):
        op = ops[i]
        if not isinstance(op, dict):
            issues.append(
                {
                    "code": "PLATE_TRANSITION_OP_INVALID",
                    "join_index": i,
                    "message": f"transition_ops[{i}] is not an object",
                }
            )
            continue
        pic = op.get("picture") if isinstance(op.get("picture"), dict) else {}
        base = str(pic.get("base") or "").strip().lower()
        op_style = str(pic.get("style") or "").strip().lower() or None
        plate_style = str(out[i] or "").strip().lower() or None

        if base in {"hard_cut", "hard", "concat"}:
            # hard joins ignore xfade style; no mismatch for soft plate leftover
            continue
        if base in {"xfade", "soft", "hold"} or base == "":
            if not op_style or op_style in {"none", "hard"}:
                issues.append(
                    {
                        "code": "PLATE_TRANSITION_STYLE_MISSING",
                        "join_index": i,
                        "message": (
                            f"join {i}: transition_ops soft/xfade lacks picture.style"
                        ),
                        "plate_style": plate_style,
                    }
                )
                continue
            if plate_style and plate_style != op_style and plate_style not in {"hard", "none"}:
                issues.append(
                    {
                        "code": "PLATE_TRANSITION_STYLE_MISMATCH",
                        "join_index": i,
                        "message": (
                            f"join {i}: plate style={plate_style!r} != "
                            f"transition_ops.picture.style={op_style!r} — aligning to ops"
                        ),
                        "plate_style": plate_style,
                        "ops_style": op_style,
                    }
                )
            out[i] = op_style
    return out, issues


def plate_transition_ops_alignment_report(
    *,
    transition_ops: object,
    story_styles: list[str] | None,
    story_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Pure report for tests / preflight (does not rewrite)."""
    styles = list(story_styles or [])
    if not isinstance(transition_ops, list) or not transition_ops:
        return {
            "ok": True,
            "checked": False,
            "codes": [],
            "issues": [],
            "aligned_styles": styles,
        }
    aligned, issues = align_story_styles_to_transition_ops(transition_ops, styles or [""] * len(transition_ops))
    # Mismatch codes are auto-fixed on plate path — only MISSING / INVALID are hard
    hard_codes = {
        i["code"]
        for i in issues
        if i.get("code") in {"PLATE_TRANSITION_STYLE_MISSING", "PLATE_TRANSITION_OP_INVALID"}
    }
    # Also hard if continue op is xfade in ops (should be hard_cut) — optional
    for i, op in enumerate(transition_ops):
        if not isinstance(op, dict):
            continue
        cont = str(op.get("continuity_class") or "").lower()
        pic = op.get("picture") if isinstance(op.get("picture"), dict) else {}
        base = str(pic.get("base") or "").lower()
        if cont == "continue" and base not in {"hard_cut", "hard", "concat", ""}:
            issues.append(
                {
                    "code": "PLATE_TRANSITION_CONTINUE_NOT_HARD",
                    "join_index": i,
                    "message": f"join {i}: continue seam ops.base={base!r} must be hard_cut",
                }
            )
            hard_codes.add("PLATE_TRANSITION_CONTINUE_NOT_HARD")

    return {
        "ok": len(hard_codes) == 0,
        "checked": True,
        "codes": sorted(hard_codes | {i["code"] for i in issues if i.get("code")}),
        "hard_codes": sorted(hard_codes),
        "issues": issues,
        "aligned_styles": aligned,
        "ops_count": len(transition_ops),
        "style_count": len(styles),
    }


__all__ = [
    "align_story_styles_to_transition_ops",
    "plate_transition_ops_alignment_report",
]
