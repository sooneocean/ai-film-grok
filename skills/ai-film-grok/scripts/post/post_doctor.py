#!/usr/bin/env python3
"""One-page post health check (P1-C · 2026-08-05).

Red/green: caption_path · double-burn · SRT non-overlap · five_track plan ·
timeline single clock · mix PARTIAL honesty.

Does not spend money. Safe before/after final.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/post-doctor.json")


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    fix: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if fix:
        row["fix"] = fix
    return row


def _srt_nonoverlap(srt: Path) -> list[dict[str, Any]]:
    try:
        from subtitle_dialogue_alignment import _cues

        cues = _cues(srt)
    except Exception as exc:  # noqa: BLE001
        return [_issue("hard", "SRT_PARSE_FAILED", str(exc)[:160])]
    issues: list[dict[str, Any]] = []
    prev_end = -1.0
    for i, (start, end) in enumerate(cues):
        if end <= start:
            issues.append(_issue("hard", "SRT_BAD_CUE", f"cue[{i}] end<=start ({start}->{end})"))
        if start < prev_end - 1e-3:
            issues.append(
                _issue(
                    "hard",
                    "SRT_OVERLAP",
                    f"cue[{i}] starts before previous ends ({start} < {prev_end})",
                    fix="sub_lead=0 + non-overlap clamp in render_final",
                )
            )
        prev_end = end
    return issues


def run_post_doctor(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []

    route = read_json(base / "receipts" / "post-route.json") or {}
    stages = read_json(base / "receipts" / "final-stages.json") or {}
    delivery = read_json(base / "out" / "final-delivery.json") or {}
    caption_path = route.get("caption_path")
    plate_subs = route.get("plate_subs")
    if isinstance(stages.get("stages"), dict):
        plate_subs = plate_subs or (stages["stages"].get("plate") or {}).get("subs")
    subs = delivery.get("subtitles") if isinstance(delivery.get("subtitles"), dict) else {}
    owner = subs.get("caption_owner")
    if caption_path:
        soft.append(
            _issue(
                "soft",
                "CAPTION_PATH",
                f"caption_path={caption_path} plate_subs={plate_subs} owner={owner}",
            )
        )
        if caption_path == "master_hf" and str(plate_subs or "").lower() == "burn":
            hard.append(
                _issue(
                    "hard",
                    "DOUBLE_BURN_RISK",
                    "master_hf with plate subs=burn (designed captions would stack)",
                    fix="aifilm final --caption-path master_hf  # forces plate subs=off",
                )
            )
        if (
            caption_path == "ship_hardburn"
            and str(plate_subs or "").lower() == "burn"
            and owner in {"hyperframes", "remotion", "hyperframes_export_only"}
        ):
            hard.append(
                _issue(
                    "hard",
                    "DOUBLE_BURN_RISK",
                    f"ship_hardburn plate burn + designed caption_owner={owner}",
                    fix="designed layer title/grade only; caption_owner should be ffmpeg_plate",
                )
            )
    else:
        soft.append(
            _issue(
                "soft",
                "CAPTION_PATH_UNSET",
                "no receipts/post-route.json yet — set on next final",
                fix="aifilm final --caption-path master_hf|ship_hardburn",
            )
        )

    srt = next(
        (p for p in (base / "out" / "final.srt", base / "final.srt") if p.is_file()),
        None,
    )
    if srt:
        hard.extend(_srt_nonoverlap(srt))
    else:
        soft.append(_issue("soft", "SRT_MISSING", "no final.srt yet"))

    ft = read_json(base / "receipts" / "five-track-plan.json") or {}
    if ft.get("kind") == "five-track-plan":
        if ft.get("ok") is False:
            soft.append(
                _issue(
                    "soft",
                    "FIVE_TRACK_RED",
                    f"five-track plan red: {ft.get('codes')}",
                    fix=str(ft.get("next_cmd") or "aifilm five-track plan --root …"),
                )
            )
        else:
            soft.append(_issue("soft", "FIVE_TRACK_OK", "five-track plan ok or soft-only"))
    else:
        soft.append(
            _issue(
                "soft",
                "FIVE_TRACK_UNSET",
                "no five-track-plan receipt",
                fix='aifilm five-track plan --root "<film>"',
            )
        )

    try:
        from timeline_clock import audit_timeline_clock

        clock = audit_timeline_clock(base, write=True)
        if clock.get("dual_clock"):
            hard.append(
                _issue(
                    "hard",
                    "DUAL_TIMELINE_CLOCK",
                    clock.get("error") or "timeline.json ≠ film_timeline",
                    fix=clock.get("next_cmd") or f'aifilm timeline-clock rewrite --root "{base}"',
                )
            )
        elif clock.get("skipped"):
            soft.append(_issue("soft", "TIMELINE_CLOCK_SKIP", "no starts to compare yet"))
        else:
            soft.append(_issue("soft", "TIMELINE_CLOCK_OK", "single on-picture clock"))
    except Exception as exc:  # noqa: BLE001
        soft.append(_issue("soft", "TIMELINE_CLOCK_ERROR", str(exc)[:160]))

    mix = read_json(base / "receipts" / "final-mix-partial.json") or {}
    if mix.get("kind") == "final-mix-partial" and mix.get("partial"):
        soft.append(
            _issue(
                "soft",
                "MIX_PARTIAL",
                (
                    f"sidechain→{mix.get('to')}: reason={mix.get('reason_code') or mix.get('reason')} "
                    f"tracks={mix.get('affected_tracks')}"
                ),
                fix="re-final if full sidechain required; delivery remains PARTIAL",
            )
        )

    final = next(
        (p for p in (base / "out" / "film_final.mp4", base / "out" / "final.mp4") if p.is_file()),
        None,
    )
    if final:
        try:
            from caption_pixel_check import caption_pixel_status

            cap = caption_pixel_status(base)
            if not cap.get("ok") and not cap.get("skipped"):
                hard.append(
                    _issue(
                        "hard",
                        "CAPTION_PIXEL_RED",
                        cap.get("detail") or "caption pixel red",
                        fix=cap.get("next_cmd") or f'aifilm caption-pixel-check --root "{base}"',
                    )
                )
            else:
                soft.append(_issue("soft", "CAPTION_PIXEL_OK", "pixel ink ok or skipped"))
        except Exception as exc:  # noqa: BLE001
            soft.append(_issue("soft", "CAPTION_PIXEL_ERROR", str(exc)[:160]))

    report = {
        "schema_version": 1,
        "kind": "post-doctor",
        "at": utc_now(),
        "root": str(base),
        "ok": not hard,
        "hard_ok": not hard,
        "soft_ok": True,
        "hard": hard,
        "soft": soft,
        "summary": {
            "hard_n": len(hard),
            "soft_n": len(soft),
            "codes": [i.get("code") for i in hard + soft],
        },
        "next_cmd": (
            None if not hard else (hard[0].get("fix") or f'aifilm post-doctor --root "{base}"')
        ),
    }
    if write:
        path = base / RECEIPT_REL
        write_json(path, report)
        report["path"] = str(path)
    return report
