"""Best-effort, secret-free Telegram notifications for project autopilot."""

from __future__ import annotations

import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


def notify_telegram(message: str, *, opener=urlopen) -> dict[str, object]:
    """Send a bounded status line only when explicit local configuration exists."""
    token = os.environ.get("AIFILM_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("AIFILM_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"attempted": False, "ok": False, "reason": "not_configured"}
    text = " ".join(str(message).split())[:900]
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            ok = 200 <= int(getattr(response, "status", 200)) < 300
        return {"attempted": True, "ok": ok, "reason": "sent" if ok else "http_error"}
    except (OSError, URLError, ValueError):
        return {"attempted": True, "ok": False, "reason": "delivery_failed"}


def notify_review_ready(root: str, *, shot_id: str, provider: str, model: str) -> dict[str, object]:
    """Send a one-time loopback review invite; Telegram never receives the API session token."""
    try:
        from review_ui import ReviewUIError, create_invite

        invite = create_invite(root)
    except (OSError, ValueError, ReviewUIError):
        return {"attempted": False, "ok": False, "reason": "review_ui_unavailable"}
    report = notify_telegram(
        f"云端候选可审核：镜头 {shot_id} · {provider}/{model}。一次性审核链接：{invite['url']}"
    )
    return {key: value for key, value in report.items() if key != "url"}
