"""One fail-closed status surface for the local audio automation chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime_policy import verify_runtime_lock
from scene_sound import reconcile as reconcile_scene_sound
from util import read_json, utc_now


def build_verification_report(root: Path) -> dict[str, Any]:
    """Collect only checks whose inputs exist; never render, queue, or mutate a film."""
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    timeline_enabled = bool(spec.get("audio_timeline_v1", False))
    checks: list[dict[str, Any]] = []

    skill_dir = Path(__file__).resolve().parents[1]
    runtime = verify_runtime_lock(skill_dir, skill_dir / "runtime-lock.json")
    checks.append({"name": "runtime_lock", "required": True, "ok": bool(runtime.get("ok"))})

    if timeline_enabled:
        scene_sound = reconcile_scene_sound(root, write=False)
        checks.append(
            {
                "name": "scene_sound",
                "required": True,
                "ok": scene_sound.get("status") != "blocked",
                "status": scene_sound.get("status"),
                "blocking_shot_ids": scene_sound.get("blocking_shot_ids") or [],
            }
        )
        delivery = read_json(root / "audio" / "audio-delivery-report.json")
        checks.append(
            {
                "name": "audio_delivery",
                "required": True,
                "ok": bool(
                    isinstance(delivery, dict) and delivery.get("ok") and not delivery.get("stale")
                ),
                "status": "missing"
                if not isinstance(delivery, dict)
                else "ok"
                if delivery.get("ok")
                else "blocked",
                "stale": bool((delivery or {}).get("stale"))
                if isinstance(delivery, dict)
                else False,
            }
        )

    book_path = root / "production-book.json"
    if book_path.is_file():
        from director_cli import check as director_check

        director = director_check(root)
        checks.append(
            {
                "name": "production_book",
                "required": True,
                "ok": bool(director.get("ok")),
                "error_count": len(director.get("errors") or []),
            }
        )

    blocking = [item["name"] for item in checks if item["required"] and not item["ok"]]
    return {
        "schema_version": 1,
        "kind": "aifilm-automation-verify",
        "checked_at": utc_now(),
        "root": str(root),
        "ok": not blocking,
        "blocking_checks": blocking,
        "checks": checks,
    }
