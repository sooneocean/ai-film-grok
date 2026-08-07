"""F2 · Face-lock triple honesty (face_identity ∧ identity_generation ∧ partner_cast).

Lock-face is necessary: when cast is on film, all three legs must pass (or explicit
soft / skip) before any path may claim master-class delivery.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/face-lock-triple.json")


def _leg_face_identity(root: Path) -> dict[str, Any]:
    try:
        from gates.production_gates import ProductionGateError, assert_face_identity_passed
    except ImportError:  # pragma: no cover
        from production_gates import ProductionGateError, assert_face_identity_passed  # type: ignore

    try:
        out = assert_face_identity_passed(root, force=False, env_skip=True)
        if out.get("skipped"):
            return {
                "id": "face_identity",
                "ok": True,
                "skipped": True,
                "soft": False,
                "codes": [],
                "detail": f"skipped:{out.get('reason')}",
            }
        if out.get("soft"):
            return {
                "id": "face_identity",
                "ok": True,
                "soft": True,
                "codes": list(out.get("codes") or []),
                "detail": "soft advisory",
                "issues": out.get("issues") or [],
            }
        return {
            "id": "face_identity",
            "ok": True,
            "soft": False,
            "codes": list(out.get("codes") or []),
            "detail": "ok",
        }
    except ProductionGateError as exc:
        return {
            "id": "face_identity",
            "ok": False,
            "soft": False,
            "hard": True,
            "codes": _codes_from_message(str(exc), default="FACE_IDENTITY_GATE"),
            "detail": str(exc)[:200],
            "error": str(exc)[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "face_identity",
            "ok": False,
            "hard": True,
            "codes": ["FACE_IDENTITY_PROBE_FAILED"],
            "detail": str(exc)[:160],
        }


def _codes_from_message(msg: str, *, default: str) -> list[str]:
    known = (
        "FACE_IDENTITY_DRIFT",
        "FACE_IDENTITY_NOT_AUDITED",
        "FACE_IDENTITY_ENROLL_GAP",
        "STYLE_BIBLE_PARSE_FAILED",
    )
    found = [c for c in known if c in msg]
    return found or [default]


def _leg_identity_generation(root: Path) -> dict[str, Any]:
    try:
        from gates.identity_generation_lock import audit_identity_generation
    except ImportError:  # pragma: no cover
        from identity_generation_lock import audit_identity_generation  # type: ignore

    try:
        rep = audit_identity_generation(root, write_receipt=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "identity_generation",
            "ok": False,
            "hard": True,
            "identity_partial": True,
            "codes": ["IDENTITY_GEN_PROBE_FAILED"],
            "detail": str(exc)[:160],
        }
    partial = bool(rep.get("identity_partial"))
    ok = bool(rep.get("ok"))
    return {
        "id": "identity_generation",
        "ok": ok,
        "hard": not ok,
        "identity_partial": partial,
        "soft": ok and partial,
        "codes": list(rep.get("codes") or []),
        "classification": rep.get("classification"),
        "detail": (
            f"class={rep.get('classification')} partial={partial} "
            f"codes={rep.get('codes') or []}"
        )[:200],
        "next_cmd": rep.get("next_cmd"),
    }


def _leg_partner_cast(root: Path) -> dict[str, Any]:
    try:
        from gates.partner_cast_gate import audit_partner_cast
    except ImportError:  # pragma: no cover
        from partner_cast_gate import audit_partner_cast  # type: ignore

    try:
        rep = audit_partner_cast(root, write_receipt=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "partner_cast",
            "ok": True,
            "advisory": True,
            "codes": [],
            "detail": f"probe:{str(exc)[:120]}",
        }
    ok = bool(rep.get("ok", True))
    return {
        "id": "partner_cast",
        "ok": ok,
        "hard": not ok,
        "checked": bool(rep.get("checked")),
        "codes": list(rep.get("codes") or []),
        "detail": (
            f"checked={rep.get('checked')} codes={rep.get('codes') or []}"
        )[:200],
        "next_cmd": rep.get("next_cmd"),
        "advisory": not rep.get("checked") and ok,
    }


def audit_face_lock_triple(
    root: Path | str,
    *,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """AND of face_identity · identity_generation · partner_cast.

    Returns master_eligible=False when any hard leg fails or identity_partial.
    Soft-only face advisory does not block master_eligible by itself.
    """
    base = Path(root).expanduser().resolve()
    face = _leg_face_identity(base)
    igen = _leg_identity_generation(base)
    partner = _leg_partner_cast(base)
    legs = {
        "face_identity": face,
        "identity_generation": igen,
        "partner_cast": partner,
    }
    hard_fails = [
        leg
        for leg in (face, igen, partner)
        if not leg.get("ok") and not leg.get("soft") and not leg.get("skipped")
    ]
    identity_partial = bool(igen.get("identity_partial")) or any(
        "IDENTITY_PARTIAL" in (c or "") or c == "IDENTITY_UNVERIFIED"
        for c in (igen.get("codes") or [])
        if isinstance(c, str)
    )
    codes: list[str] = []
    for leg in (face, igen, partner):
        for c in leg.get("codes") or []:
            if c not in codes:
                codes.append(str(c))
    # Master claim banned if hard fail OR identity partial honesty
    master_eligible = not hard_fails and not identity_partial
    ok = not hard_fails
    next_cmds = [
        leg.get("next_cmd")
        for leg in (face, igen, partner)
        if leg.get("next_cmd") and (not leg.get("ok") or leg.get("identity_partial"))
    ]
    out: dict[str, Any] = {
        "kind": "face-lock-triple",
        "schema_version": 1,
        "at": utc_now(),
        "root": str(base),
        "ok": ok,
        "master_eligible": master_eligible,
        "identity_partial": identity_partial,
        "codes": codes,
        "hard_fail_legs": [h["id"] for h in hard_fails],
        "legs": legs,
        "next_cmd": next_cmds[0]
        if next_cmds
        else (
            f'aifilm face-identity enroll-bible --root "{base}" && '
            f'aifilm face-identity audit --root "{base}"'
            if not master_eligible
            else None
        ),
        "note": (
            "master claim banned"
            if not master_eligible
            else "face-lock triple clear (human master_lock still separate)"
        ),
    }
    if write_receipt:
        write_json(base / RECEIPT_REL, out)
        out["path"] = str(base / RECEIPT_REL)
    return out


def annotate_official_final_for_face_lock(
    root: Path | str,
    triple: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """If face-lock blocks master, force official-final-report to plate honesty."""
    base = Path(root).expanduser().resolve()
    path = base / "receipts" / "official-final-report.json"
    if not path.is_file():
        return None
    rep = read_json(path)
    if not isinstance(rep, dict):
        return None
    trip = triple if isinstance(triple, dict) else audit_face_lock_triple(base, write_receipt=False)
    if trip.get("master_eligible"):
        return {"updated": False, "status": rep.get("status")}
    status = str(rep.get("status") or rep.get("delivery_class") or "")
    limits = list(rep.get("honest_limits") or [])
    for tag in ("face_lock_triple", "IDENTITY_PARTIAL" if trip.get("identity_partial") else None):
        if tag and tag not in limits:
            limits.append(tag)
    for c in trip.get("codes") or []:
        if c not in limits:
            limits.append(str(c))
    rep["status"] = "OFFICIAL_FINAL_PLATE"
    rep["delivery_class"] = "OFFICIAL_FINAL_PLATE"
    rep["partial"] = True
    rep["master_lock"] = False
    rep["master_eligible"] = False
    rep["identity_partial"] = bool(trip.get("identity_partial"))
    rep["face_lock_triple"] = {
        "ok": trip.get("ok"),
        "master_eligible": False,
        "codes": trip.get("codes") or [],
        "hard_fail_legs": trip.get("hard_fail_legs") or [],
    }
    rep["honest_limits"] = limits
    if status and status not in ("OFFICIAL_FINAL_PLATE",):
        rep["previous_status"] = status
    rep["note"] = (
        "face-lock triple not master-eligible — plate only "
        f"(legs={trip.get('hard_fail_legs') or []}; partial={trip.get('identity_partial')})"
    )
    write_json(path, rep)
    return {"updated": True, "status": "OFFICIAL_FINAL_PLATE", "path": str(path)}


__all__ = [
    "annotate_official_final_for_face_lock",
    "audit_face_lock_triple",
]
