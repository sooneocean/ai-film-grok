"""Server-Sent Events frames for director-center live feed (Phase E).

Loopback console only. Frames:
  event: live
  data: {"live": <director-center-live>, "events": <tail>}

Keepalive comments every interval when snapshot is unchanged.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def _snapshot(root: Path | str) -> dict[str, Any]:
    from console_projection import project_director_live, project_events_tail

    live = project_director_live(root, include_token=False)
    events = project_events_tail(root, limit=20)
    return {
        "kind": "director-center-sse",
        "live": live,
        "events": events.get("events") or [],
        "review_mode": live.get("review_mode"),
        "inbox_count": live.get("inbox_count"),
        "revision": live.get("revision"),
    }


def _sig(snap: dict[str, Any]) -> str:
    live = snap.get("live") if isinstance(snap.get("live"), dict) else {}
    q = live.get("queue") if isinstance(live.get("queue"), dict) else {}
    inbox = live.get("human_inbox") if isinstance(live.get("human_inbox"), list) else []
    return json.dumps(
        {
            "r": live.get("revision"),
            "i": live.get("inbox_count"),
            "rm": live.get("review_mode"),
            "run": q.get("running"),
            "pend": q.get("pending"),
            "takes": q.get("takes_count"),
            "ids": [x.get("id") for x in inbox[:12] if isinstance(x, dict)],
            "ev": [e.get("event_id") for e in (snap.get("events") or [])[-5:] if isinstance(e, dict)],
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def format_sse(event: str, data: dict[str, Any] | str) -> bytes:
    if isinstance(data, dict):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        body = str(data)
    # SSE forbids bare newlines in data without multi-line encoding
    body = body.replace("\n", "")
    return f"event: {event}\ndata: {body}\n\n".encode()


def format_keepalive() -> bytes:
    return b": keepalive\n\n"


def iter_director_sse(
    root: Path | str,
    *,
    interval_sec: float = 1.5,
    max_events: int | None = None,
    include_unchanged: bool = False,
) -> Iterator[bytes]:
    """Yield SSE bytes. ``max_events`` limits *data* frames (not keepalives) for tests."""
    base = Path(root).expanduser().resolve()
    interval_sec = max(0.3, min(float(interval_sec), 30.0))
    last = ""
    sent = 0
    # Hello frame so clients know stream is live immediately
    hello = {
        "kind": "director-center-sse-hello",
        "ok": True,
        "interval_sec": interval_sec,
    }
    yield format_sse("hello", hello)
    while True:
        try:
            snap = _snapshot(base)
        except Exception as exc:  # noqa: BLE001
            yield format_sse("error", {"error": str(exc)[:300]})
            time.sleep(interval_sec)
            continue
        sig = _sig(snap)
        if sig != last or include_unchanged:
            yield format_sse("live", snap)
            last = sig
            sent += 1
            if max_events is not None and sent >= max_events:
                yield format_sse("bye", {"ok": True, "frames": sent})
                return
        else:
            yield format_keepalive()
        time.sleep(interval_sec)
