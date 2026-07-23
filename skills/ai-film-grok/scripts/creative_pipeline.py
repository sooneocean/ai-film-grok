"""Fail-closed contracts for radio cut, animatic and pre-production readiness.

These checks deliberately measure evidence and authored intent only.  They never
invent dialogue, coverage or director decisions on behalf of the filmmaker.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from util import read_json, write_json


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _items(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def build_radio_cut(root: Path | str) -> dict[str, Any]:
    """Validate the authored radio-cut receipt against current story timing."""
    base = Path(root).expanduser().resolve()
    receipt = read_json(base / "receipts" / "radio-cut.json") or {}
    spec_path = base / "film-spec.json"
    spec = read_json(spec_path) or {}
    shots = _items(spec)
    blockers: list[dict[str, str]] = []
    if not spec:
        blockers.append({"code": "FILM_SPEC_MISSING", "message": "film-spec.json is required"})
    if not receipt:
        blockers.append(
            {"code": "RADIO_CUT_MISSING", "message": "record a measured radio cut before I2V"}
        )
    if receipt and receipt.get("spec_sha256") != _sha(spec_path):
        blockers.append(
            {"code": "RADIO_CUT_STALE", "message": "radio cut was recorded for an older film-spec"}
        )
    if receipt and receipt.get("timing_ok") is not True:
        blockers.append(
            {
                "code": "RADIO_TIMING_FAIL",
                "message": "dialogue timing exceeds the available shot duration",
            }
        )
    if receipt and receipt.get("emotion_turns_ok") is not True:
        blockers.append(
            {
                "code": "RADIO_EMOTION_FAIL",
                "message": "radio cut lacks approved emotional-turn evidence",
            }
        )
    if shots and receipt and int(receipt.get("shot_count") or 0) != len(shots):
        blockers.append(
            {
                "code": "RADIO_SHOT_COUNT_STALE",
                "message": "radio cut shot count differs from current spec",
            }
        )
    return {
        "ok": not blockers,
        "kind": "radio-cut-gate",
        "spec_sha256": _sha(spec_path),
        "shot_count": len(shots),
        "human_review_required": True,
        "blockers": blockers,
    }


def build_animatic_gate(root: Path | str) -> dict[str, Any]:
    """Require an authored low-cost animatic before premium I2V generation."""
    base = Path(root).expanduser().resolve()
    receipt = read_json(base / "receipts" / "animatic.json") or {}
    spec_path = base / "film-spec.json"
    blockers: list[dict[str, str]] = []
    if not receipt:
        blockers.append(
            {"code": "ANIMATIC_MISSING", "message": "record an animatic review before I2V"}
        )
    if receipt and receipt.get("spec_sha256") != _sha(spec_path):
        blockers.append(
            {"code": "ANIMATIC_STALE", "message": "animatic is stale after an upstream spec change"}
        )
    for key, code, message in (
        ("coverage_ok", "ANIMATIC_COVERAGE_FAIL", "animatic coverage is incomplete"),
        ("pace_ok", "ANIMATIC_PACE_FAIL", "animatic pace chart is not approved"),
        (
            "performance_ok",
            "ANIMATIC_PERFORMANCE_FAIL",
            "animatic performance transitions are not approved",
        ),
    ):
        if receipt and receipt.get(key) is not True:
            blockers.append({"code": code, "message": message})
    return {
        "ok": not blockers,
        "kind": "animatic-gate",
        "spec_sha256": _sha(spec_path),
        "human_review_required": True,
        "blockers": blockers,
    }


def preproduction_readiness(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Combine premium creative, radio and animatic gates into one receipt."""
    base = Path(root).expanduser().resolve()
    book = read_json(base / "production-book.json") or {}
    premium = str(book.get("quality_target") or "standard") == "premium_vertical"
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "preproduction-readiness",
        "quality_target": book.get("quality_target", "standard"),
        "required": premium,
        "creative": {},
        "radio_cut": build_radio_cut(base) if premium else {"ok": True, "required": False},
        "animatic": build_animatic_gate(base) if premium else {"ok": True, "required": False},
    }
    if premium:
        from creative_quality import validate_premium_vertical

        report["creative"] = validate_premium_vertical(base)
    checks = [report["creative"], report["radio_cut"], report["animatic"]]
    report["ok"] = all(item.get("ok") is True for item in checks if isinstance(item, dict))
    report["blockers"] = [
        blocker
        for item in checks
        if isinstance(item, dict)
        for blocker in item.get("blockers") or item.get("issues") or []
    ]
    if write:
        write_json(base / "receipts" / "preproduction-readiness.json", report)
    return report


def write_authoring_receipt(root: Path | str, kind: str, values: dict[str, Any]) -> dict[str, Any]:
    """Write only explicit human/agent-provided measurements for radio or animatic."""
    if kind not in {"radio-cut", "animatic"}:
        raise ValueError("kind must be radio-cut|animatic")
    base = Path(root).expanduser().resolve()
    path = base / "film-spec.json"
    receipt = {
        "schema_version": 1,
        "kind": kind,
        "spec_sha256": _sha(path),
        **values,
    }
    write_json(base / "receipts" / f"{kind}.json", receipt)
    return receipt
