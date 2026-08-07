"""Take compare + director review for localhost console."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from util import exclusive_file_lock, utc_now, write_json
from web_core import WebConsoleError, WebConsoleForbidden

VALID_STATUSES = frozenset(
    {"generated", "candidate", "selected", "approved", "rejected", "archived", "active"}
)


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise WebConsoleError("film root must be an existing directory")
    return value


def _rel_media(base: Path, path: Any) -> str | None:
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        p = Path(path)
        candidate = (base / path).resolve() if not p.is_absolute() else p.resolve()
        if not candidate.is_file() or candidate.is_symlink():
            return None
        if base not in candidate.parents and candidate != base:
            return None
        return str(candidate.relative_to(base)).replace("\\", "/")
    except (OSError, ValueError):
        return None


def _enrich_candidates(base: Path, manifest: dict[str, Any], shot_id: str) -> dict[str, Any]:
    from take_registry import compare_takes

    cmp = compare_takes(manifest, shot_id)
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    history = (manifest.get("take_history") or {}).get(shot_id) or []
    by_id: dict[str, dict[str, Any]] = {}
    cur = clips.get(shot_id)
    if isinstance(cur, dict) and cur.get("take_id"):
        by_id[str(cur["take_id"])] = cur
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and item.get("take_id"):
                by_id[str(item["take_id"])] = item
    rows = []
    for row in cmp.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("take_id") or "")
        src = by_id.get(tid) or {}
        path = _rel_media(base, src.get("path") or src.get("archived_path"))
        mean = None
        qg = src.get("quality_gate") if isinstance(src.get("quality_gate"), dict) else {}
        if isinstance(qg.get("mean_volume"), (int, float)):
            mean = float(qg["mean_volume"])
        elif isinstance(src.get("mean_volume"), (int, float)):
            mean = float(src["mean_volume"])
        rows.append(
            {
                **row,
                "path": path,
                "media": path,
                "mean_volume": mean,
                "provider": src.get("provider") or src.get("i2v_provider"),
            }
        )
    return {
        "kind": "takes-compare",
        "shot_id": shot_id,
        "candidate_count": len(rows),
        "candidates": rows,
        "anti_hijack_hint": "禁止只比 mean/音量/white0 自动选片；请目视构图与主体，再 Select。",
    }


def list_take_shots(root: Path | str) -> dict[str, Any]:
    base = _root(root)
    from core.film_io import load_manifest

    manifest = load_manifest(base)
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    history = manifest.get("take_history") if isinstance(manifest.get("take_history"), dict) else {}
    shot_ids = sorted({*clips.keys(), *history.keys()}, key=str)
    items = []
    multi = 0
    for sid in shot_ids:
        cmp = _enrich_candidates(base, manifest, str(sid))
        n = int(cmp.get("candidate_count") or 0)
        if n == 0:
            continue
        if n >= 2:
            multi += 1
        active = next(
            (c for c in cmp["candidates"] if c.get("active")),
            cmp["candidates"][0] if cmp["candidates"] else None,
        )
        items.append(
            {
                "shot_id": str(sid),
                "candidate_count": n,
                "active_take_id": (active or {}).get("take_id"),
                "active_path": (active or {}).get("path"),
                "needs_pick": n >= 2
                and not any(
                    str(c.get("director_status") or "").lower() in {"selected", "approved"}
                    for c in cmp["candidates"]
                ),
            }
        )
    return {
        "kind": "takes-index",
        "shots": items,
        "shot_count": len(items),
        "multi_take_count": multi,
        "anti_hijack_hint": "禁止只比 mean/音量自动全选；多 take 须人眼选片。",
    }


def get_takes(root: Path | str, shot_id: str) -> dict[str, Any]:
    base = _root(root)
    sid = str(shot_id or "").strip()
    if not sid:
        raise WebConsoleError("shot_id is required")
    from core.film_io import load_manifest

    return _enrich_candidates(base, load_manifest(base), sid)


def review_take(
    root: Path | str,
    *,
    shot_id: str,
    take_id: str | None = None,
    director_status: str | None = None,
    performance: int | None = None,
    continuity: int | None = None,
    camera: int | None = None,
    artifacts: int | None = None,
    note: str | None = None,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    base = _root(root)
    sid = str(shot_id or "").strip()
    if not sid:
        raise WebConsoleError("shot_id is required")
    status = str(director_status).strip().lower() if director_status is not None else None
    if status is not None and status not in VALID_STATUSES:
        raise WebConsoleError(f"director_status must be one of {sorted(VALID_STATUSES)}")
    try:
        from gate_panel import collect_gates

        if collect_gates(base).get("blocking"):
            raise WebConsoleForbidden("hard gates blocking — cannot review takes")
    except WebConsoleForbidden:
        raise
    except Exception:
        pass
    from core.film_io import load_manifest, save_manifest
    from take_registry import set_take_review

    with exclusive_file_lock(base / "manifest.json"):
        manifest = load_manifest(base)
        if expected_revision is not None:
            try:
                from approval_ledger import read_approval_ledger
                from web_core import WebConsoleConflict

                rev = int(read_approval_ledger(base).get("revision") or 0)
                if rev != int(expected_revision):
                    raise WebConsoleConflict("approval ledger revision is stale")
            except WebConsoleError:
                raise
            except Exception:
                pass
        try:
            result = set_take_review(
                manifest,
                sid,
                take_id=take_id,
                performance=performance,
                continuity=continuity,
                camera=camera,
                artifacts=artifacts,
                director_status=status,
            )
        except ValueError as exc:
            raise WebConsoleError(str(exc)) from exc
        save_manifest(base, manifest)
    audit = {
        "schema_version": 1,
        "kind": "director-take-review",
        "shot_id": sid,
        "take_id": result.get("take_id"),
        "director_status": result.get("director_status"),
        "note": (note or "")[:500] or None,
        "at": utc_now(),
        "source": "web-console",
    }
    audit_dir = base / "receipts" / "take-reviews"
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_json(audit_dir / f"{sid}-{result.get('take_id') or 'na'}.json", audit)
    try:
        from pipeline_events import append_event

        append_event(
            base,
            stage=f"take:{sid}",
            phase="completed" if status in {"selected", "approved", "active"} else "human_time",
            shot_id=sid,
            note=status or "review",
            actor="director-center",
        )
    except Exception:
        pass
    return {"ok": True, "result": result, "compare": get_takes(base, sid), "audit": audit}
