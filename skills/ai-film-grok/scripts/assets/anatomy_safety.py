"""Human-attested anatomy safety gates for adult-max / restricted media.

The gate deliberately does not claim that text or a hash can recognise anatomy.
It records the required full-frame human inspection and fails closed when that
inspection is missing or has found a poisoned frame.

I2.1 (2026-08-07): restricted still → I2V / H3 must have anatomy_safe=true;
poisoned stills always block. Escape: AIFILM_SKIP_ANATOMY_SAFETY=1.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json


class AnatomySafetyError(ValueError):
    pass


_RESTRICTED_WARDROBE = frozenset({"undressed", "bare", "partial", "nude", "naked"})
_RESTRICTED_HEAT = frozenset({"act", "climax", "foreplay"})


def _env_skip(root: Path | str | None = None) -> bool:
    """Honesty-rail: prefer central skip_flag so escapes land in skip-usage ledger."""
    try:
        from core.skip_audit import skip_flag

        return skip_flag(
            "AIFILM_SKIP_ANATOMY_SAFETY",
            origin="env",
            film_root=root,
            call_site="anatomy_safety._env_skip",
        )
    except Exception:  # noqa: BLE001
        return os.environ.get("AIFILM_SKIP_ANATOMY_SAFETY", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _load_spec(root: Path) -> dict[str, Any]:
    spec = read_json(Path(root).expanduser().resolve() / "film-spec.json") or {}
    return spec if isinstance(spec, dict) else {}


def requires_anatomy_safety(root: Path) -> bool:
    """Return whether this film's adult contract requires attestation by default.

    True when heat_scale=max (adult_max_iron not false) **or** genre=adult
    (same iron exit). Escape env forces False.
    """
    if _env_skip(root):
        return False
    spec = _load_spec(root)
    if spec.get("adult_max_iron") is False:
        return False
    heat = str(spec.get("heat_scale") or "").strip().lower()
    if heat == "max":
        return True
    genre = str(spec.get("genre") or "").strip().lower()
    if genre in {"adult", "erotic", "nsfw", "ecchi"}:
        return True
    return False


def shot_is_restricted(shot: dict[str, Any] | None) -> bool:
    """True for meat / undressed frames that must never I2V without human anatomy pass."""
    if not isinstance(shot, dict):
        return False
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    wardrobe = str(
        shot.get("wardrobe_state") or dsl.get("wardrobe_state") or ""
    ).strip().lower()
    heat = str(shot.get("heat_phase") or dsl.get("heat_phase") or "").strip().lower()
    if wardrobe in _RESTRICTED_WARDROBE:
        return True
    if heat in _RESTRICTED_HEAT:
        return True
    return False


def find_shot(spec: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    sid = str(shot_id)
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and str(sh.get("id") or "") == sid:
                return sh
    if isinstance(spec.get("shots"), list):
        for sh in spec["shots"]:
            if isinstance(sh, dict) and str(sh.get("id") or "") == sid:
                return sh
    return None


def shot_requires_anatomy_safety(
    root: Path,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
) -> bool:
    """Film-level adult max **or** this shot is restricted meat/undress."""
    if _env_skip(root):
        return False
    if requires_anatomy_safety(root):
        return True
    spec = _load_spec(root)
    sh = shot if isinstance(shot, dict) else find_shot(spec, shot_id)
    # restricted only when adult iron not explicitly off
    if spec.get("adult_max_iron") is False:
        return False
    return shot_is_restricted(sh)


def require_anatomy_safe(
    *,
    root: Path,
    anatomy_safe: bool,
    kind: str,
    shot_id: str,
    still_path: str | Path | None = None,
    reviewer: str | None = None,
    agent_session: str | None = None,
    review_note: str | None = None,
) -> None:
    """Require an explicit human attestation before approving adult-max media.

    When anatomy_safe=True, write provenance to receipts/attestation-ledger.json
    (honesty-rail R2). Missing reviewer/session → pending_human_review, never fake source.
    """
    if _env_skip(root):
        return
    # film-level or this shot restricted
    if not shot_requires_anatomy_safety(root, shot_id) or anatomy_safe:
        if anatomy_safe:
            try:
                from core.attestation_audit import write_attestation

                write_attestation(
                    root,
                    kind=f"anatomy_{kind}",
                    shot_id=str(shot_id),
                    still_path=still_path,
                    reviewer=reviewer,
                    agent_session=agent_session,
                    anatomy_safe=True,
                    note=review_note,
                    source="require_anatomy_safe",
                )
            except Exception:  # noqa: BLE001
                pass
        return
    raise AnatomySafetyError(
        f"adult-max/restricted approved {kind} for {shot_id} requires --anatomy-safe after "
        "full-frame human inspection (no futa/wrong anatomy, milk spray, or neon-genital artifact); "
        "escape AIFILM_SKIP_ANATOMY_SAFETY=1"
    )


def anatomy_safety_report(
    manifest: dict[str, Any], *, required_shot_ids: list[str], kind: str
) -> dict[str, Any]:
    """Return missing/poisoned approval attestations for a manifest media collection."""
    records = manifest.get(kind) if isinstance(manifest.get(kind), dict) else {}
    missing: list[str] = []
    poisoned: list[str] = []
    for shot_id in required_shot_ids:
        record = records.get(shot_id)
        if not isinstance(record, dict) or record.get("status") != "approved":
            continue
        safe = record.get("anatomy_safe")
        if safe is True:
            continue
        if safe is False:
            poisoned.append(str(shot_id))
        else:
            missing.append(str(shot_id))
    ok = not missing and not poisoned
    return {
        "ok": ok,
        "kind": kind,
        "missing_attestation_shots": sorted(missing),
        "poisoned_shots": sorted(poisoned),
        # alias for older bulk-preflight consumers
        "missing_shots": sorted(missing),
        "judgment_source": "human_full_frame_inspection",
        "reason": (
            "all approved media has anatomy_safe=true"
            if ok
            else "poisoned media must not enter I2V/register/final; missing attestation fails closed"
        ),
    }


def assert_still_anatomy_for_i2v(
    root: Path | str,
    shot_id: str,
    *,
    input_paths: list[Path | str] | None = None,
) -> dict[str, Any]:
    """I2.1 · fail-closed before I2V/H3 when attestation missing or still poisoned.

    - anatomy_safe is False → always hard block (poison), even outside adult max.
    - film/shot requires safety → must be approved still with anatomy_safe=true.
    - optional input_paths: first path sha must match approved still when required.
    """
    base = Path(root).expanduser().resolve()
    sid = str(shot_id)
    if _env_skip(base):
        return {
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_ANATOMY_SAFETY=1",
            "shot_id": sid,
        }
    man = read_json(base / "manifest.json") or {}
    stills = man.get("stills") if isinstance(man, dict) else {}
    still = stills.get(sid) if isinstance(stills, dict) else None
    required = shot_requires_anatomy_safety(base, sid)

    # Explicit poison always blocks (no silent I2V of known-bad still)
    if isinstance(still, dict) and still.get("anatomy_safe") is False:
        raise AnatomySafetyError(
            f"I2V blocked for {sid}: still marked anatomy_safe=false (poison); "
            "repair/archive and re-register with --anatomy-safe"
        )

    if not required:
        return {
            "ok": True,
            "required": False,
            "shot_id": sid,
            "note": "anatomy attestation not required for this film/shot",
        }

    if not isinstance(still, dict) or still.get("status") != "approved":
        raise AnatomySafetyError(
            f"I2V blocked for {sid}: restricted/adult-max requires approved keyframe "
            "with human anatomy inspection"
        )
    if still.get("anatomy_safe") is not True:
        raise AnatomySafetyError(
            f"I2V blocked for {sid}: keyframe lacks anatomy_safe=true; "
            "register-still --status approved --anatomy-safe after full-frame inspection"
        )

    if input_paths:
        try:
            from runtime_policy import sha256
        except ImportError:  # pragma: no cover
            sha256 = None  # type: ignore
        approved_sha = str(still.get("sha256") or "").strip()
        if sha256 is not None and approved_sha:
            first = Path(input_paths[0]).expanduser().resolve()
            if first.is_file() and sha256(first) != approved_sha:
                raise AnatomySafetyError(
                    f"I2V blocked for {sid}: first input does not match the approved "
                    "anatomy-safe keyframe bytes for this shot"
                )

    # R2: surface provenance status (pending if register lacked reviewer/session)
    provenance: dict[str, Any] | None = None
    try:
        from core.attestation_audit import find_attestation, provenance_fields

        entry = find_attestation(base, kind="anatomy_still", shot_id=sid)
        if entry is None:
            entry = find_attestation(base, kind="anatomy_clip", shot_id=sid)
        if entry is not None:
            provenance = {
                **provenance_fields(entry),
                "pending_human_review": bool(entry.get("pending_human_review")),
                "provenance_complete": bool(entry.get("provenance_complete")),
            }
        else:
            provenance = {
                "pending_human_review": True,
                "provenance_complete": False,
                "note": "anatomy_safe=true without attestation ledger row",
            }
    except Exception:  # noqa: BLE001
        provenance = None

    out: dict[str, Any] = {
        "ok": True,
        "required": True,
        "shot_id": sid,
        "anatomy_safe": True,
        "still_status": still.get("status"),
    }
    if provenance is not None:
        out["attestation"] = provenance
    return out


__all__ = [
    "AnatomySafetyError",
    "anatomy_safety_report",
    "assert_still_anatomy_for_i2v",
    "find_shot",
    "require_anatomy_safe",
    "requires_anatomy_safety",
    "shot_is_restricted",
    "shot_requires_anatomy_safety",
]
