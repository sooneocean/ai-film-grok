#!/usr/bin/env python3
"""Production hard gates: pilot user-approval + VO loop-risk (shared by queue / final).

S3 (2026-07-16 Kei): bulk media-queue add requires user pilot approval.
Without approval, at most PILOT_MAX_SHOTS_WITHOUT_APPROVAL distinct shot_ids may queue
(the pilot window). Agent self-approve is rejected.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from film_spec import (
    DEFAULT_DURATION_SEC,
    LOOP_RISK_VO_SEC,
    VO_PACING_SLACK_SEC,
    FilmSpecError,
    estimate_nar_vo_sec,
    validate_film_spec,
)
from util import read_json

PILOT_MAX_SHOTS_WITHOUT_APPROVAL = 3
PILOT_APPROVAL_NAME = "pilot-approval.json"


class ProductionGateError(RuntimeError):
    """Raised when a production gate blocks the operation."""


def pilot_approval_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / PILOT_APPROVAL_NAME


def load_pilot_approval(root: Path) -> dict[str, Any]:
    return read_json(pilot_approval_path(root) or {})


def pilot_is_user_approved(data: dict[str, Any] | None) -> bool:
    """True only when user (not agent) approved pilot."""
    if not isinstance(data, dict) or data.get("approved") is not True:
        return False
    by = str(data.get("approved_by") or "").strip().lower()
    # Agent self-approve is never enough
    if by in {"agent", "bot", "system", "auto", "grok", "grok-agent"}:
        return False
    if by in {"user", "human", "owner"}:
        return True
    notes = str(data.get("notes") or "")
    if "pilot 过" in notes or "pilot过" in notes:
        return True
    return bool("user approved pilot" in notes.lower() or "pilot passed by user" in notes.lower())


def assert_provider_pilot_current(root: Path) -> dict[str, Any]:
    """Prevent a provider fallback from silently reusing an old hero pilot."""
    routing = read_json(Path(root).expanduser().resolve() / "receipts" / "i2v-routing.json") or {}
    if routing.get("requires_hero_repilot") is not True:
        return {"ok": True, "checked": False}
    approval = load_pilot_approval(root)
    pilot_route = approval.get("i2v_routing") if isinstance(approval, dict) else None
    selected = str(routing.get("selected_provider") or "")
    if (
        not isinstance(pilot_route, dict)
        or str(pilot_route.get("selected_provider") or "") != selected
    ):
        raise ProductionGateError(
            "provider fallback changed the hero route; obtain a new user-approved pilot "
            f"for provider={selected!r} before bulk media"
        )
    return {"ok": True, "checked": True, "provider": selected}


def assert_pilot_user_approved(
    root: Path,
    *,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """Strict check: user pilot must already be on disk (used by final / status helpers)."""
    if force:
        return {"skipped": True, "reason": "force"}
    if env_skip and os.environ.get("AIFILM_SKIP_PILOT_GATE", "").strip() in {"1", "true", "yes"}:
        return {"skipped": True, "reason": "env"}
    data = load_pilot_approval(root)
    if pilot_is_user_approved(data):
        _assert_pilot_quality_evidence(root, data)
        return {"ok": True, "pilot": data}
    path = pilot_approval_path(root)
    if not path.is_file():
        raise ProductionGateError(
            "pilot gate: missing receipts/pilot-approval.json with "
            '{"approved": true, "approved_by": "user", ...}. '
            f"Generate ≤{PILOT_MAX_SHOTS_WITHOUT_APPROVAL} pilot shots, get user approval, "
            "then queue bulk work. Emergency: --allow-without-pilot or AIFILM_SKIP_PILOT_GATE=1"
        )
    raise ProductionGateError(
        "pilot gate: pilot-approval.json exists but is not user-approved "
        f"(need approved=true and approved_by=user). got approved={data.get('approved')!r} "
        f"approved_by={data.get('approved_by')!r}. "
        "Do not self-approve. Wait for user phrase like 'pilot 过'."
    )


def _assert_pilot_quality_evidence(root: Path, approval: dict[str, Any]) -> None:
    """New evidence-contract projects cannot bulk from stale pilot approvals."""
    manifest = read_json(Path(root).expanduser().resolve() / "manifest.json") or {}
    if int(manifest.get("quality_evidence_contract_version") or 0) < 1:
        return
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    pilot_shots = approval.get("shots") if isinstance(approval.get("shots"), list) else []
    if not pilot_shots:
        raise ProductionGateError("pilot approval lacks reviewed pilot shot ids")
    try:
        from quality_evidence import quality_evidence_is_current
    except ImportError as exc:
        raise ProductionGateError("quality evidence verifier is unavailable") from exc
    stale: list[str] = []
    for shot_id in pilot_shots:
        record = clips.get(str(shot_id))
        if not isinstance(record, dict):
            stale.append(str(shot_id))
            continue
        clip = Path(str(record.get("path") or ""))
        if not quality_evidence_is_current(record.get("quality_evidence"), clip=clip):
            stale.append(str(shot_id))
    if stale:
        raise ProductionGateError(
            "pilot approval is missing current shot-quality evidence for: "
            + ", ".join(sorted(stale))
        )


def assert_pilot_allows_add(
    root: Path,
    *,
    shot_id: str,
    existing_shot_ids: set[str],
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """S3 gate for media-queue add.

    - User-approved pilot → allow any shot.
    - Else allow at most PILOT_MAX_SHOTS_WITHOUT_APPROVAL distinct shot_ids (pilot window).
    - force / AIFILM_SKIP_PILOT_GATE=1 → skip (tests / emergency).
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if env_skip and os.environ.get("AIFILM_SKIP_PILOT_GATE", "").strip() in {"1", "true", "yes"}:
        return {"skipped": True, "reason": "env"}
    pilot = load_pilot_approval(root)
    if pilot_is_user_approved(pilot):
        assert_provider_pilot_current(root)
        return {"ok": True, "pilot": pilot}
    known = set(existing_shot_ids) | {shot_id}
    if len(known) <= PILOT_MAX_SHOTS_WITHOUT_APPROVAL:
        return {
            "ok": True,
            "pilot_window": True,
            "distinct_shots": sorted(known),
            "max_without_approval": PILOT_MAX_SHOTS_WITHOUT_APPROVAL,
        }
    path = pilot_approval_path(root)
    root_s = str(Path(root).expanduser().resolve())
    raise ProductionGateError(
        f"pilot gate: cannot add shot_id={shot_id!r} — already have {len(existing_shot_ids)} "
        f"distinct shot(s) queued without user pilot approval "
        f"(max {PILOT_MAX_SHOTS_WITHOUT_APPROVAL}). Write {path} with "
        f'{{"approved": true, "approved_by": "user", "shots": ["shot01",...], "notes": "..."}} '
        f"after the user confirms pilot stills, then retry add. Agent must not self-approve. "
        f'Next: aifilm pilot report --root "{root_s}" → '
        f'pilot score … → pilot approve --user-phrase "pilot 过". '
        f"Emergency: --allow-without-pilot or AIFILM_SKIP_PILOT_GATE=1"
    )


def _flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    scenes = spec.get("scenes") or []
    if isinstance(scenes, list):
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            for shot in scene.get("shots") or []:
                if isinstance(shot, dict):
                    out.append(shot)
    # Top-level shots (short-form film-spec may only use this list)
    top = spec.get("shots") or []
    if isinstance(top, list) and top:
        seen = {str(s.get("id") or "") for s in out}
        for shot in top:
            if not isinstance(shot, dict):
                continue
            sid = str(shot.get("id") or "")
            if sid and sid in seen:
                continue
            out.append(shot)
    return out


def _measured_map_for_root(root: Path | None) -> dict[str, float]:
    if root is None:
        return {}
    try:
        from tts_rehearsal import measured_vo_by_shot

        return measured_vo_by_shot(Path(root))
    except Exception:
        return {}


def _shot_would_stream_loop(
    *,
    plate_sec: float,
    vo_sec: float,
    dramatic_function: str | None,
) -> bool:
    """True only if edit_policy.plan_stretch would still use stream_loop.

    P0 · 2026-07-23: short I2V plates clamp/forbid_loop instead of replaying —
    VO slightly over 5.5s is no longer a hard gate when loops=0.
    """
    try:
        from edit_policy import plan_stretch

        # Target ≈ VO + tiny pad (render_final adds vo_pad); plate is I2V source.
        target = max(float(vo_sec), 0.05)
        src = max(float(plate_sec), 0.05)
        plan = plan_stretch(
            src,
            target,
            dramatic_function=dramatic_function,
        )
        return int(plan.get("loops") or 0) > 0
    except Exception:
        # Fall back to legacy threshold if policy import fails
        return float(vo_sec) > LOOP_RISK_VO_SEC and float(plate_sec) <= 6.5


def loop_risk_shots_from_spec(
    spec: dict[str, Any],
    *,
    measured_by_shot: dict[str, float] | None = None,
    root: Path | None = None,
) -> list[str]:
    """Return shot ids whose VO would still force stream_loop after edit policy.

    When measured_by_shot (or root rehearsal receipt) is present, prefer measured
    seconds over estimate_nar_vo_sec / cached _vo_budget.
    """
    measured = dict(measured_by_shot or {})
    if not measured and root is not None:
        measured = _measured_map_for_root(root)

    risk: list[str] = []
    for shot in _flatten_shots(spec):
        sid = str(shot.get("id") or "?")
        nar = str(shot.get("nar") or shot.get("narration") or "")
        if measured:
            try:
                from tts_rehearsal import effective_vo_sec

                vo, _src = effective_vo_sec(
                    sid,
                    nar,
                    est_vo_sec=shot.get("est_vo_sec"),
                    measured_by_shot=measured,
                )
            except Exception:
                vo = float(shot.get("est_vo_sec") or estimate_nar_vo_sec(nar))
        else:
            try:
                vo = float(shot.get("est_vo_sec") or estimate_nar_vo_sec(nar))
            except (TypeError, ValueError):
                vo = estimate_nar_vo_sec(nar)
        try:
            dur = float(shot.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            dur = float(DEFAULT_DURATION_SEC)
        beat = str(shot.get("dramatic_function") or shot.get("beat") or shot.get("function") or "")
        # P0 · 2026-07-23: only flag when plan_stretch still uses stream_loop.
        # Shortform clamp forbids loop on ≤7.5s plates — VO slightly >5.5s is OK.
        if _shot_would_stream_loop(plate_sec=dur, vo_sec=vo, dramatic_function=beat or None) or (
            vo > LOOP_RISK_VO_SEC and dur <= 6.5
        ):
            risk.append(sid)
    # Do not trust stale _vo_budget.loop_risk_shots (pre shortform clamp policy)
    return risk


def measured_over_plate_shots(
    spec: dict[str, Any],
    measured_by_shot: dict[str, float],
    *,
    slack_sec: float | None = None,
) -> list[str]:
    """Shot ids where measured VO exceeds duration_sec + vo_pacing slack."""
    slack = VO_PACING_SLACK_SEC if slack_sec is None else float(slack_sec)
    over: list[str] = []
    for shot in _flatten_shots(spec):
        sid = str(shot.get("id") or "").strip()
        if not sid or sid not in measured_by_shot:
            continue
        try:
            plate = float(shot.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            plate = float(DEFAULT_DURATION_SEC)
        try:
            m = float(measured_by_shot[sid])
        except (TypeError, ValueError):
            continue
        if m > plate + slack:
            over.append(sid)
    return over


def assert_tts_rehearsal_timing(
    root: Path,
    *,
    strict: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Gate final/preflight on measured VO when rehearsal receipt is present/required.

    - Receipt present → measured preferred; over-plate shots hard-fail.
    - strict=True (or film-spec tts_rehearsal_required / env) → missing receipt hard-fails.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    env_strict = os.environ.get("AIFILM_STRICT_TTS_REHEARSAL", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    spec_strict = bool(spec.get("tts_rehearsal_required") is True) if spec else False
    strict = bool(strict or env_strict or spec_strict)

    try:
        from tts_rehearsal import TTSRehearsalError, bind_receipt_to_spec_timing
    except ImportError as exc:
        if strict:
            raise ProductionGateError(
                f"tts rehearsal timing: tts_rehearsal unavailable: {exc}"
            ) from exc
        return {"present": False, "ok": True, "skipped": True, "reason": "module_missing"}

    try:
        report = bind_receipt_to_spec_timing(root, strict=strict, raise_on_fail=False)
    except TTSRehearsalError as exc:
        raise ProductionGateError(str(exc)) from exc

    if strict and not report.get("present"):
        raise ProductionGateError(
            "tts rehearsal timing (strict): missing receipts/tts-rehearsal.json — "
            'run aifilm tts-rehearse --root "<root>" before final/bulk '
            "(or drop tts_rehearsal_required / --strict-tts-rehearsal)."
        )
    over = list(report.get("over_plate_shots") or [])
    if over:
        raise ProductionGateError(
            "tts rehearsal timing: measured VO exceeds plate on "
            f"{over} (vo_pacing with measured_duration_sec, slack "
            f"{VO_PACING_SLACK_SEC}s). Shorten nar, raise duration_sec, split shots, "
            "or re-run tts-rehearse after edits. "
            "--allow-loop-risk does NOT skip measured over-plate; fix VO budget."
        )
    return report


def assert_no_loop_risk(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
    strict_tts_rehearsal: bool = False,
) -> list[str]:
    """Block final when loop_risk_shots non-empty (defense in depth after write-spec vo_pacing).

    When root has receipts/tts-rehearsal.json, prefers measured_duration_sec over
    estimate_nar_vo_sec for risk detection. Measured over-plate hard-fails even when
    force/allow_loop_risk is set (separate vo_pacing truth).
    """
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
        if not data:
            if force:
                return []
            raise ProductionGateError(f"loop-risk gate: film-spec missing at {path}")
        try:
            validate_film_spec(data, assign_missing_ids=False)
        except FilmSpecError as exc:
            if force:
                return []
            raise ProductionGateError(f"loop-risk gate: film-spec invalid: {exc}") from exc
    if data is None and root is None:
        raise ProductionGateError("assert_no_loop_risk requires root or spec")

    # Measured over-plate always enforced when root given (receipt present → use it)
    if root is not None:
        assert_tts_rehearsal_timing(
            Path(root),
            strict=strict_tts_rehearsal,
            force=False,
        )

    if force:
        return []
    if env_skip and os.environ.get("AIFILM_SKIP_LOOP_RISK_GATE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return []
    if data is None:
        return []

    measured = _measured_map_for_root(Path(root) if root is not None else None)
    risk = loop_risk_shots_from_spec(
        data, measured_by_shot=measured or None, root=Path(root) if root else None
    )
    if risk:
        src = "measured" if measured else "est_vo"
        raise ProductionGateError(
            "loop-risk gate: these shots have VO too long for a 6s plate "
            f"({src} > {LOOP_RISK_VO_SEC}s) and would stream_loop (boring replay): {risk}. "
            "Split into more shots with shorter nar (≤28 chars recommended), then write-spec. "
            "If tts-rehearsal receipt exists, measured_duration_sec is used. "
            "Emergency only: --allow-loop-risk or AIFILM_SKIP_LOOP_RISK_GATE=1"
        )
    return risk
