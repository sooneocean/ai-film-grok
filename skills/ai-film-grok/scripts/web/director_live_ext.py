"""Director-live projections (kept separate so they are hard to silently drop)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json


def _clip_text(value: Any, *, max_len: int = 480) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def session_meta(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    path = base / "receipts" / "review-ui-session.json"
    empty: dict[str, Any] = {
        "active": False,
        "port": None,
        "pid": None,
        "url": None,
        "token": None,
        "root": str(base),
    }
    raw = read_json(path)
    if not isinstance(raw, dict) or raw.get("root") != str(base):
        return empty
    port, token = raw.get("port"), raw.get("token")
    if not isinstance(port, int) or not isinstance(token, str) or not token:
        return empty
    pid = raw.get("pid")
    alive = True
    if isinstance(pid, int) and pid > 0:
        try:
            import os

            os.kill(pid, 0)
        except OSError:
            alive = False
    if not alive:
        return empty
    return {
        "active": True,
        "port": port,
        "pid": pid if isinstance(pid, int) else None,
        "url": f"http://127.0.0.1:{port}/console?token={token}",
        "token": token,
        "root": str(base),
    }


def project_events_tail(
    root: Path | str, *, since: str | None = None, limit: int = 40
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    limit = max(1, min(int(limit or 40), 200))
    out: dict[str, Any] = {
        "kind": "pipeline-events-tail",
        "available": False,
        "events": [],
        "invalid_count": 0,
        "since": since,
    }
    try:
        from pipeline_events import load_events

        events, invalid = load_events(base)
    except Exception:
        return out
    if since:
        events = [
            e for e in events if str(e.get("occurred_at") or e.get("at") or "") > str(since)
        ]
    slim = []
    for e in events[-limit:]:
        if not isinstance(e, dict):
            continue
        err = e.get("error")
        slim.append(
            {
                "event_id": e.get("event_id"),
                "stage": e.get("stage"),
                "phase": e.get("phase"),
                "shot_id": e.get("shot_id"),
                "at": e.get("occurred_at") or e.get("at"),
                "note": _clip_text(e.get("note"), max_len=200),
                "error_code": (err or {}).get("code")
                if isinstance(err, dict)
                else e.get("error_code"),
            }
        )
    out["available"] = True
    out["events"] = slim
    out["invalid_count"] = len(invalid)
    return out


def project_human_inbox(root: Path | str) -> list[dict[str, Any]]:
    base = Path(root).expanduser().resolve()
    inbox: list[dict[str, Any]] = []
    try:
        from review_control import review_queue

        items = review_queue(base).get("items") or []
    except Exception:
        items = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            state = str(item.get("state") or "")
            if state not in {"pending_review", "stale"}:
                continue
            media = item.get("media") if isinstance(item.get("media"), list) else []
            cands = (
                item.get("cloud_candidates")
                if isinstance(item.get("cloud_candidates"), list)
                else []
            )
            inbox.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "state": state,
                    "kind": "stage",
                    "media": media[:8],
                    "candidates": len(cands),
                    "approval_id": item.get("approval_id"),
                }
            )
    sample_every = 5
    try:
        from review_control import load_settings

        ap = load_settings(base).get("autopilot") or {}
        sample_every = max(1, int(ap.get("sample_every") or 5))
    except Exception:
        pass
    try:
        from web.takes_api import list_take_shots

        needs = [s for s in (list_take_shots(base).get("shots") or []) if s.get("needs_pick")]
        picked: list[dict[str, Any]] = []
        for i, shot in enumerate(needs):
            if i < 3 or i % sample_every == 0:
                picked.append(shot)
            if len(picked) >= 12:
                break
        for shot in picked:
            inbox.append(
                {
                    "id": f"take:{shot.get('shot_id')}",
                    "title": f"选 Take · {shot.get('shot_id')}",
                    "state": "pending_review",
                    "kind": "take_pick",
                    "shot_id": shot.get("shot_id"),
                    "media": [shot.get("active_path")] if shot.get("active_path") else [],
                    "candidates": shot.get("candidate_count") or 0,
                    "approval_id": None,
                }
            )
    except Exception:
        pass
    return inbox[:40]


def project_director_live(root: Path | str, *, include_token: bool = False) -> dict[str, Any]:
    from web.projection import project_dispatch_for_console, project_queue_snapshot

    base = Path(root).expanduser().resolve()
    dispatch = project_dispatch_for_console(base)
    queue = project_queue_snapshot(base)
    inbox = project_human_inbox(base)
    activity = project_events_tail(base, limit=24)
    session = session_meta(base)
    session_public: dict[str, Any] = {
        "active": session.get("active") is True,
        "port": session.get("port"),
        "pid": session.get("pid"),
        "url": session.get("url")
        if include_token
        else (f"http://127.0.0.1:{session['port']}/console" if session.get("active") else None),
    }
    if include_token and session.get("token"):
        session_public["token"] = session["token"]
        session_public["url"] = session.get("url")
    job_counts = queue.get("job_counts") if isinstance(queue.get("job_counts"), dict) else {}
    pending = int(job_counts.get("pending") or job_counts.get("queued") or 0)
    running = int(queue.get("running") or job_counts.get("running") or 0)
    failed = int(job_counts.get("failed") or job_counts.get("error") or 0)
    reviewable = sum(1 for i in inbox if i.get("state") == "pending_review")
    gates_blocking, hard_fail = False, []
    try:
        from gate_panel import collect_gates

        g = collect_gates(base)
        gates_blocking = bool(g.get("blocking"))
        hard_fail = list(g.get("hard_fail") or [])[:12]
    except Exception:
        pass
    ledger_revision = 0
    try:
        from approval_ledger import read_approval_ledger

        ledger = read_approval_ledger(base)
        if isinstance(ledger, dict):
            ledger_revision = int(ledger.get("revision") or 0)
    except Exception:
        pass
    multi_take = 0
    try:
        from web.takes_api import list_take_shots

        multi_take = int(list_take_shots(base).get("multi_take_count") or 0)
    except Exception:
        pass
    return {
        "kind": "director-center-live",
        "available": True,
        "revision": ledger_revision,
        "dispatch": {
            "available": dispatch.get("available"),
            "stage_public": dispatch.get("stage_public"),
            "craft_stage": dispatch.get("craft_stage"),
            "pipeline_stage": dispatch.get("pipeline_stage"),
            "next_id": dispatch.get("next_id"),
            "next_cmd": dispatch.get("next_cmd"),
            "next_why": dispatch.get("next_why"),
            "approval_class": dispatch.get("approval_class"),
            "console_url": dispatch.get("console_url"),
            "copy_cmd": dispatch.get("copy_cmd"),
            "blocked_by": dispatch.get("blocked_by") or [],
        },
        "queue": {
            "available": queue.get("available"),
            "pending": pending,
            "running": running,
            "reviewable": reviewable,
            "failed": failed,
            "takes_count": queue.get("takes_count"),
            "multi_take_shots": multi_take,
            "job_counts": job_counts,
            "unknown": queue.get("unknown"),
        },
        "human_inbox": inbox,
        "inbox_count": len(inbox),
        "activity": activity.get("events") or [],
        "gates": {"blocking": gates_blocking, "hard_fail": hard_fail},
        "session": session_public,
    }


def attach_console_url_to_dispatch(root: Path | str, packet: dict[str, Any]) -> dict[str, Any]:
    out = dict(packet)
    meta = session_meta(root)
    if meta.get("active") and meta.get("url"):
        out["console_url"] = meta["url"]
        out["console_port"] = meta.get("port")
    else:
        out["console_url"] = None
        out["console_port"] = None
        base = Path(root).expanduser().resolve()
        out["console_hint"] = f'aifilm director-center open --root "{base}"'
    return out
