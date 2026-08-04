"""Closeout one-shot — plate/final → review → post-audit → optional export.

Wave A1 · workflow optimize: stop hand-rolling 6 commands after a plate exists.
Does **not** auto-approve review-final (human scorecard required).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/closeout.json")


def _export_name(root: Path) -> str:
    """Desktop folder name without placeholders (advance-safe)."""
    try:
        from next_actions import _export_desktop_name

        return _export_desktop_name(root)
    except Exception:
        return "GrokFilm"


class CloseoutError(RuntimeError):
    """Hard stop with a single next action for agents."""

    def __init__(
        self,
        message: str,
        *,
        next_cmd: str | None = None,
        required_proof: str | None = None,
        code: str = "CLOSEOUT_BLOCKED",
    ) -> None:
        super().__init__(message)
        self.next_cmd = next_cmd
        self.required_proof = required_proof
        self.code = code


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _gates(root: Path) -> dict[str, Any]:
    man = read_json(root / "manifest.json") or {}
    raw = man.get("gates") if isinstance(man.get("gates"), dict) else {}
    return dict(raw)


def _final_record(root: Path) -> dict[str, Any] | None:
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else None
    if rec and rec.get("path"):
        p = Path(str(rec["path"]))
        if not p.is_absolute():
            p = root / p
        if p.is_file():
            return rec
    # plate fallbacks often used before register-final
    for rel in (
        "out/film_final.mp4",
        "out/final.mp4",
        "out/plate.mp4",
        "out/final-plate.mp4",
    ):
        if (root / rel).is_file():
            return {"path": str(root / rel), "source": "filesystem"}
    return None


def _post_audit_current(root: Path) -> dict[str, Any]:
    try:
        from post_audit import audit_freshness

        return audit_freshness(root)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def closeout_status(root: Path | str) -> dict[str, Any]:
    """Read-only ladder: heat → plate → final_complete → post-audit → export."""
    base = _root(root)
    gates = _gates(base)
    final_rec = _final_record(base)
    heat: dict[str, Any] = {}
    try:
        from heat_check import heat_agent_status

        heat = heat_agent_status(base) or {}
    except Exception as exc:  # noqa: BLE001
        heat = {"active": False, "error": str(exc)[:160]}

    post = _post_audit_current(base)
    steps = [
        {
            "id": "heat",
            "ok": not (
                heat.get("active")
                and (heat.get("hard_fail") or heat.get("needs_boost") is True)
                and heat.get("blocks_final", heat.get("hard_fail"))
            ),
            "detail": heat.get("why") or heat.get("error") or "heat ok or inactive",
            "next_cmd": heat.get("next_cmd"),
        },
        {
            "id": "plate_or_final",
            "ok": final_rec is not None,
            "detail": (final_rec or {}).get("path") or "no final/plate mp4",
            "next_cmd": (
                None
                if final_rec
                else f'aifilm final --root "{base}" --lipsync off --music-mood rnb --tts-backend edge'
            ),
        },
        {
            "id": "final_complete",
            "ok": bool(gates.get("final_complete")),
            "detail": "review-final scorecard approved"
            if gates.get("final_complete")
            else "needs human review-final",
            "next_cmd": (
                None
                if gates.get("final_complete")
                # Draft if missing; apply path needs user phrase (shown in human_next)
                else (f'aifilm agent-review-final --root "{base}"')
            ),
            "required_proof": None
            if gates.get("final_complete")
            else (
                "agent-review-final → --apply --reviewer … --user-phrase 可以 "
                "(never forge phrase; technical gates still apply)"
            ),
        },
        {
            "id": "post_audit",
            "ok": bool(post.get("ok") or post.get("current")),
            "detail": post.get("error") or ("current" if post.get("ok") else "stale or missing"),
            "next_cmd": (
                None
                if (post.get("ok") or post.get("current"))
                else f'aifilm post-audit --root "{base}"'
            ),
        },
        {
            "id": "desktop_exported",
            "ok": bool(gates.get("desktop_exported")),
            "detail": "export-desktop done"
            if gates.get("desktop_exported")
            else "optional export remaining",
            "next_cmd": (
                None
                if gates.get("desktop_exported")
                else f'aifilm export-desktop --root "{base}" --name "{_export_name(base)}"'
            ),
        },
    ]
    # Soft heat: if active hard_fail for final, mark heat not ok more clearly
    if heat.get("active") and heat.get("hard_fail"):
        steps[0]["ok"] = False
        steps[0]["detail"] = heat.get("why") or "heat hard_fail"
        steps[0]["next_cmd"] = heat.get("next_cmd") or f'aifilm heat boost --root "{base}" --apply'
        steps[0]["required_proof"] = "heat_agent_status.hard_fail cleared"

    # P2 film-core audit (advisory — does not block delivery_ready alone)
    core_audit: dict[str, Any] = {}
    try:
        from workflow_pack import film_core_closeout_audit

        core_audit = film_core_closeout_audit(base, write=True)
        steps.append(
            {
                "id": "film_core",
                "ok": bool(core_audit.get("ok")),
                "detail": (
                    "motion core DF/want/dialogue aligned"
                    if core_audit.get("ok")
                    else f"issues={len(core_audit.get('issues') or [])}"
                ),
                "next_cmd": core_audit.get("next_cmd"),
                "advisory": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        core_audit = {"ok": True, "skipped": True, "error": str(exc)[:160]}

    blocked = next(
        (s for s in steps if not s["ok"] and s["id"] not in {"desktop_exported", "film_core"}),
        None,
    )
    delivery_ready = all(s["ok"] for s in steps if s["id"] not in {"desktop_exported", "film_core"})
    export_cmd = f'aifilm export-desktop --root "{base}" --name "{_export_name(base)}"'
    return {
        "kind": "closeout-status",
        "schema_version": 1,
        "root": str(base),
        "at": utc_now(),
        "ok": blocked is None and delivery_ready,
        "delivery_ready": delivery_ready,
        "film_core": core_audit,
        "gates": {
            "final_complete": bool(gates.get("final_complete")),
            "desktop_exported": bool(gates.get("desktop_exported")),
            "clips_complete": bool(gates.get("clips_complete")),
        },
        "final": final_rec,
        "heat": {
            "active": heat.get("active"),
            "hard_fail": heat.get("hard_fail"),
            "needs_boost": heat.get("needs_boost"),
            "why": heat.get("why"),
        },
        "steps": steps,
        "blocked_by": blocked["id"] if blocked else None,
        "next_cmd": (blocked or {}).get("next_cmd"),
        "required_proof": (blocked or {}).get("required_proof"),
        "next_action": {
            "id": f"closeout-{(blocked or {}).get('id') or 'done'}",
            "cmd": (blocked or {}).get("next_cmd")
            or (
                export_cmd
                if not gates.get("desktop_exported")
                else f'aifilm status --root "{base}"'
            ),
            "why": (blocked or {}).get("detail") or "closeout ladder clear",
        },
    }


def closeout_run(
    root: Path | str,
    *,
    execute: bool = True,
    export: bool = False,
    export_name: str | None = None,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """Run automatable closeout steps; stop at first human/hard gate.

    ``execute=False`` is status-only (same as closeout_status).
    ``execute=True`` runs post-audit when review is already complete.
    Never auto-approves review-final.
    """
    base = _root(root)
    status = closeout_status(base)
    ran: list[dict[str, Any]] = []

    if not execute:
        status["mode"] = "status"
        if write_receipt:
            path = base / RECEIPT_REL
            write_json(path, {**status, "receipt_path": str(path)})
            status["receipt_path"] = str(path)
        return status

    status["mode"] = "run"
    # Heat hard fail → stop
    heat_step = next(s for s in status["steps"] if s["id"] == "heat")
    if not heat_step["ok"]:
        payload = {
            **status,
            "ok": False,
            "stopped_at": "heat",
            "ran": ran,
            "next_cmd": heat_step.get("next_cmd"),
            "required_proof": heat_step.get("required_proof"),
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    if not status["final"]:
        payload = {
            **status,
            "ok": False,
            "stopped_at": "plate_or_final",
            "ran": ran,
            "next_cmd": next(s for s in status["steps"] if s["id"] == "plate_or_final").get(
                "next_cmd"
            ),
            "required_proof": "out/*.mp4 plate or registered final_film",
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    if not status["gates"].get("final_complete"):
        rev = next(s for s in status["steps"] if s["id"] == "final_complete")
        payload = {
            **status,
            "ok": False,
            "stopped_at": "final_complete",
            "ran": ran,
            "next_cmd": rev.get("next_cmd"),
            "required_proof": rev.get("required_proof"),
            "note": "closeout does not auto-approve review-final",
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    # post-audit
    post_step = next(s for s in status["steps"] if s["id"] == "post_audit")
    if not post_step["ok"]:
        try:
            from post_audit import audit

            report = audit(base, write=True)
            ran.append(
                {
                    "id": "post_audit",
                    "ok": bool(report.get("delivery_ready") or report.get("ok")),
                    "delivery_ready": report.get("delivery_ready"),
                }
            )
            if not (report.get("delivery_ready") or report.get("ok")):
                payload = {
                    **status,
                    "ok": False,
                    "stopped_at": "post_audit",
                    "ran": ran,
                    "post_audit": report,
                    "next_cmd": f'aifilm post-audit --root "{base}"',
                    "required_proof": "receipts/post-audit.json delivery_ready",
                }
                if write_receipt:
                    write_json(base / RECEIPT_REL, payload)
                return payload
        except Exception as exc:  # noqa: BLE001
            payload = {
                **status,
                "ok": False,
                "stopped_at": "post_audit",
                "ran": ran,
                "error": str(exc)[:300],
                "next_cmd": f'aifilm post-audit --root "{base}"',
            }
            if write_receipt:
                write_json(base / RECEIPT_REL, payload)
            return payload

    # optional export — only when requested; still needs a name
    if export:
        name = (export_name or "").strip()
        if not name:
            payload = {
                **closeout_status(base),
                "mode": "run",
                "ok": False,
                "stopped_at": "export_desktop",
                "ran": ran,
                "next_cmd": f'aifilm export-desktop --root "{base}" --name "{_export_name(base)}"',
                "required_proof": "export name (derived from film title when available)",
            }
            if write_receipt:
                write_json(base / RECEIPT_REL, payload)
            return payload
        # export is side-effect heavy; leave to CLI cmd_export_desktop via next_cmd
        # when agent passes --export, still emit explicit next for aifilm_grok to run
        payload = {
            **closeout_status(base),
            "mode": "run",
            "ok": True,
            "ran": ran,
            "export_requested": True,
            "export_name": name,
            "next_cmd": f'aifilm export-desktop --root "{base}" --name "{name}"',
            "note": "post-audit ok; run export-desktop with provided name",
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    fresh = closeout_status(base)
    payload = {
        **fresh,
        "mode": "run",
        "ok": fresh.get("delivery_ready"),
        "ran": ran,
        "next_cmd": fresh.get("next_cmd"),
    }
    if write_receipt:
        path = base / RECEIPT_REL
        write_json(path, {**payload, "receipt_path": str(path)})
        payload["receipt_path"] = str(path)
    return payload
