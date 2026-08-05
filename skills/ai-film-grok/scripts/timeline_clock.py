#!/usr/bin/env python3
"""Single on-picture clock for post (P1-A · 2026-08-05).

Problem (closeout IRON): hand-plate 6s grid vs old VO clock (7.6/11/…) causes
``SUBTITLE_CROSSES_HARD_CUT`` and review-final false fails.

Truth: ``film_timeline.shot_starts`` on the final MP4 clock is authoritative after
plate/final. ``timeline.json`` must match or be rewritten.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/timeline-clock.json")
DEFAULT_EPS = 0.08  # 80ms


class TimelineClockError(ValueError):
    pass


def _as_float_list(raw: Any) -> list[float] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[float] = []
    for x in raw:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            return None
    return out


def _rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def load_film_timeline(root: Path | str) -> dict[str, Any]:
    """Best-effort film_timeline with shot_starts (final/SRT clock)."""
    base = Path(root).expanduser().resolve()
    candidates: list[Path] = [
        base / "receipts" / "film_timeline.json",
        base / "out" / "_final_work" / "film_timeline.json",
        base / "compose" / "hyperframes" / "composition-data.json",
        base / "compose" / "composition-package.json",
        base / "out" / "final-delivery.json",
        base / "out" / "final-report.json",
        base / "receipts" / "final-report.json",
    ]
    for path in candidates:
        data = read_json(path) or {}
        if not isinstance(data, dict):
            continue
        if data.get("shot_starts"):
            starts = _as_float_list(data.get("shot_starts"))
            if starts:
                return {
                    "source": _rel(base, path),
                    "shot_starts": starts,
                    "output_duration": data.get("output_duration") or data.get("duration_sec"),
                    "title_duration": data.get("title_duration") or data.get("title_dur"),
                    "raw": data,
                }
        nested = data.get("film_timeline")
        if isinstance(nested, dict) and nested.get("shot_starts"):
            starts = _as_float_list(nested.get("shot_starts"))
            if starts:
                return {
                    "source": _rel(base, path),
                    "shot_starts": starts,
                    "output_duration": nested.get("output_duration"),
                    "title_duration": nested.get("title_duration"),
                    "raw": nested,
                }
        tr = data.get("transition") if isinstance(data.get("transition"), dict) else {}
        ftl = tr.get("film_timeline") if isinstance(tr.get("film_timeline"), dict) else {}
        if ftl.get("shot_starts"):
            starts = _as_float_list(ftl.get("shot_starts"))
            if starts:
                return {
                    "source": _rel(base, path),
                    "shot_starts": starts,
                    "output_duration": ftl.get("output_duration"),
                    "title_duration": ftl.get("title_duration"),
                    "raw": ftl,
                }
    return {}


def load_timeline_json_starts(root: Path | str) -> dict[str, Any]:
    """Extract cumulative starts from timeline.json (editorial / VO-era clock)."""
    base = Path(root).expanduser().resolve()
    path = base / "timeline.json"
    data = read_json(path) or {}
    if not isinstance(data, dict):
        return {"present": False, "shot_starts": [], "path": str(path)}
    starts = _as_float_list(data.get("shot_starts"))
    if starts:
        return {
            "present": True,
            "shot_starts": starts,
            "path": str(path),
            "source_field": "shot_starts",
            "shots": data.get("shots") if isinstance(data.get("shots"), list) else [],
        }
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    if not shots:
        return {"present": bool(data), "shot_starts": [], "path": str(path)}
    cursor = 0.0
    built: list[float] = []
    for item in shots:
        if not isinstance(item, dict):
            continue
        if item.get("start_sec") is not None:
            try:
                built.append(float(item["start_sec"]))
                continue
            except (TypeError, ValueError):
                pass
        built.append(round(cursor, 6))
        with suppress(TypeError, ValueError):
            cursor += float(item.get("duration_sec") or item.get("duration") or 0.0)
    return {
        "present": True,
        "shot_starts": built,
        "path": str(path),
        "source_field": "derived_from_shots",
        "shots": shots,
    }


def compare_starts(
    a: list[float],
    b: list[float],
    *,
    eps: float = DEFAULT_EPS,
) -> dict[str, Any]:
    if not a or not b:
        return {
            "ok": False,
            "reason": "empty_starts",
            "max_delta": None,
            "mismatches": [],
        }
    n = min(len(a), len(b))
    mismatches: list[dict[str, Any]] = []
    max_delta = 0.0
    for i in range(n):
        d = abs(float(a[i]) - float(b[i]))
        max_delta = max(max_delta, d)
        if d > eps:
            mismatches.append(
                {
                    "index": i,
                    "film_start": round(float(a[i]), 4),
                    "timeline_start": round(float(b[i]), 4),
                    "delta": round(d, 4),
                }
            )
    length_mismatch = len(a) != len(b)
    ok = not mismatches and not length_mismatch
    return {
        "ok": ok,
        "max_delta": round(max_delta, 4),
        "mismatches": mismatches,
        "length_mismatch": length_mismatch,
        "film_n": len(a),
        "timeline_n": len(b),
        "eps": eps,
    }


def audit_timeline_clock(
    root: Path | str,
    *,
    eps: float = DEFAULT_EPS,
    write: bool = True,
) -> dict[str, Any]:
    """Compare film_timeline vs timeline.json; dual clock → hard for post."""
    base = Path(root).expanduser().resolve()
    film = load_film_timeline(base)
    tl = load_timeline_json_starts(base)
    film_starts = list(film.get("shot_starts") or [])
    tl_starts = list(tl.get("shot_starts") or [])

    if not film_starts and not tl_starts:
        report: dict[str, Any] = {
            "schema_version": 1,
            "kind": "timeline-clock",
            "at": utc_now(),
            "ok": True,
            "skipped": True,
            "reason": "no film_timeline or timeline.json starts yet",
            "dual_clock": False,
        }
    elif film_starts and not tl_starts:
        report = {
            "schema_version": 1,
            "kind": "timeline-clock",
            "at": utc_now(),
            "ok": True,
            "dual_clock": False,
            "film": {"source": film.get("source"), "n": len(film_starts), "starts": film_starts},
            "timeline": tl,
            "note": "film_timeline only — write timeline.json from film when hand-editing cues",
        }
    elif tl_starts and not film_starts:
        report = {
            "schema_version": 1,
            "kind": "timeline-clock",
            "at": utc_now(),
            "ok": True,
            "dual_clock": False,
            "advisory": True,
            "film": {},
            "timeline": {"n": len(tl_starts), "starts": tl_starts, "path": tl.get("path")},
            "note": "timeline.json only (pre-final). After final, film_timeline is authority.",
        }
    else:
        cmp = compare_starts(film_starts, tl_starts, eps=eps)
        dual = not cmp["ok"]
        report = {
            "schema_version": 1,
            "kind": "timeline-clock",
            "at": utc_now(),
            "ok": not dual,
            "dual_clock": dual,
            "film": {
                "source": film.get("source"),
                "n": len(film_starts),
                "starts": film_starts,
                "output_duration": film.get("output_duration"),
            },
            "timeline": {
                "path": tl.get("path"),
                "source_field": tl.get("source_field"),
                "n": len(tl_starts),
                "starts": tl_starts,
            },
            "compare": cmp,
            "next_cmd": (None if not dual else f'aifilm timeline-clock rewrite --root "{base}"'),
            "error": (
                None
                if not dual
                else (
                    "DUAL_TIMELINE_CLOCK: timeline.json shot_starts ≠ film_timeline "
                    f"(max_delta={cmp.get('max_delta')}s). Subtitles must use on-picture slots."
                )
            ),
        }

    if write:
        path = base / RECEIPT_REL
        write_json(path, report)
        report["path"] = str(path)
    return report


def rewrite_timeline_from_film(root: Path | str, *, eps: float = DEFAULT_EPS) -> dict[str, Any]:
    """Rewrite timeline.json shot_starts / shot start_sec from film_timeline authority."""
    base = Path(root).expanduser().resolve()
    film = load_film_timeline(base)
    starts = list(film.get("shot_starts") or [])
    if not starts:
        raise TimelineClockError(
            "no film_timeline.shot_starts — run final first or place receipts/film_timeline.json"
        )
    path = base / "timeline.json"
    data = read_json(path) or {}
    if not isinstance(data, dict):
        data = {}
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    new_shots: list[dict[str, Any]] = []
    for i, start in enumerate(starts):
        prev = shots[i] if i < len(shots) and isinstance(shots[i], dict) else {}
        row = dict(prev) if prev else {"id": f"shot{i + 1:02d}"}
        row["start_sec"] = round(float(start), 4)
        if i + 1 < len(starts):
            row["duration_sec"] = round(float(starts[i + 1]) - float(start), 4)
        elif film.get("output_duration") is not None:
            with suppress(TypeError, ValueError):
                row["duration_sec"] = round(float(film["output_duration"]) - float(start), 4)
        new_shots.append(row)
    data["shot_starts"] = [round(float(x), 4) for x in starts]
    data["shots"] = new_shots
    data["timeline_clock"] = {
        "authority": "film_timeline",
        "source": film.get("source"),
        "rewritten_at": utc_now(),
        "eps": eps,
    }
    write_json(path, data)
    write_json(
        base / "receipts" / "film_timeline.json",
        {
            "schema_version": 1,
            "kind": "film-timeline",
            "at": utc_now(),
            "shot_starts": starts,
            "output_duration": film.get("output_duration"),
            "title_duration": film.get("title_duration"),
            "source": film.get("source"),
        },
    )
    audit = audit_timeline_clock(base, eps=eps, write=True)
    return {
        "ok": bool(audit.get("ok")),
        "rewritten": str(path),
        "shot_starts": starts,
        "n": len(starts),
        "audit": audit,
    }


def persist_film_timeline(root: Path | str, film_tl: dict[str, Any]) -> Path:
    """Write receipts/film_timeline.json from render_final film_tl dict."""
    base = Path(root).expanduser().resolve()
    path = base / "receipts" / "film_timeline.json"
    starts = _as_float_list(film_tl.get("shot_starts")) or []
    payload = {
        "schema_version": 1,
        "kind": "film-timeline",
        "at": utc_now(),
        "shot_starts": starts,
        "output_duration": film_tl.get("output_duration"),
        "title_duration": film_tl.get("title_duration") or film_tl.get("title_dur"),
        "use_ts": film_tl.get("use_ts"),
        "enabled": film_tl.get("enabled"),
        "join_intents": film_tl.get("full_join_intents") or film_tl.get("join_intents"),
        "source": "render_final",
    }
    write_json(path, payload)
    tl_path = base / "timeline.json"
    if tl_path.is_file() and starts:
        with suppress(TimelineClockError):
            rewrite_timeline_from_film(base)
    return path
