"""Assembly gate — only approved/selected takes enter rough cut (Film Production OS W6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

CODE_DRAFT_TAKE = "ASSEMBLY_DRAFT_TAKE"
CODE_NO_ACTIVE = "ASSEMBLY_NO_ACTIVE_TAKE"
CODE_REJECTED = "ASSEMBLY_REJECTED_TAKE"


def _manifest(root: Path) -> dict[str, Any]:
    for name in ("manifest.json", "media-manifest.json"):
        data = read_json(root / name)
        if isinstance(data, dict) and data:
            return data
    # common film layout
    data = read_json(root / "receipts" / "manifest.json")
    return data if isinstance(data, dict) else {}


def check_assembly_takes(
    manifest: dict[str, Any],
    *,
    shot_ids: list[str] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    ids = list(shot_ids) if shot_ids else sorted(str(k) for k in clips.keys())
    issues: list[dict[str, Any]] = []
    allowed: list[str] = []
    blocked: list[str] = []

    for sid in ids:
        rec = clips.get(sid)
        if not isinstance(rec, dict):
            issues.append(
                {
                    "code": CODE_NO_ACTIVE,
                    "severity": "error" if strict else "warning",
                    "message": f"{sid}: no clip record",
                    "shot_ids": [sid],
                }
            )
            blocked.append(sid)
            continue
        state = str(rec.get("state") or "").lower()
        director = str(rec.get("director_status") or rec.get("review_status") or "").lower()
        active = rec.get("active") is True or state in {"active", "selected", "approved"}
        if state in {"rejected", "archived"} or director in {"rejected"}:
            issues.append(
                {
                    "code": CODE_REJECTED,
                    "severity": "error" if strict else "warning",
                    "message": f"{sid}: take state={state!r} not assemblable",
                    "shot_ids": [sid],
                }
            )
            blocked.append(sid)
            continue
        if state in {"draft", "generated", "candidate", "stale"} and director not in {
            "selected",
            "approved",
        }:
            # draft/candidate without director selection
            if not (active and state == "active"):
                issues.append(
                    {
                        "code": CODE_DRAFT_TAKE,
                        "severity": "error" if strict else "warning",
                        "message": (
                            f"{sid}: take state={state!r} — need selected/approved/active "
                            "before rough cut"
                        ),
                        "shot_ids": [sid],
                    }
                )
                blocked.append(sid)
                continue
        if active or state in {"selected", "approved"} or director in {"selected", "approved"}:
            allowed.append(sid)
        else:
            issues.append(
                {
                    "code": CODE_DRAFT_TAKE,
                    "severity": "error" if strict else "warning",
                    "message": f"{sid}: not approved for assembly",
                    "shot_ids": [sid],
                }
            )
            blocked.append(sid)

    errors = [i for i in issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "kind": "assembly-gate",
        "strict": strict,
        "allowed_shot_ids": allowed,
        "blocked_shot_ids": blocked,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
        "rough_cut_allowed": not errors,
    }


def assembly_gate_at_root(
    root: Path | str,
    *,
    strict: bool = True,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    # Prefer core film_io manifest if available
    try:
        from core.film_io import load_manifest

        man = load_manifest(root_p)
    except Exception:  # noqa: BLE001
        man = _manifest(root_p)
    if not isinstance(man, dict):
        man = {}
    report = check_assembly_takes(man, strict=strict)
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "assembly-gate.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
