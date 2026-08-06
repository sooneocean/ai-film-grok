#!/usr/bin/env python3
"""P1 / P3 · Agent assist for review-final (never auto-approves).

Builds a full director scorecard draft from L0 machine evidence already on disk,
writes ``receipts/agent-review-final.json`` + an optional hash-bound
``final-review-input.assist.json``, and emits a paste-ready ``review-final``
command for the human. Artistic sign-off remains ``review-final --approve``.

P3 (2026-08-05): merge post machine lane into objective dims —
caption-pixel · post-route · timeline-clock · post-doctor · mix PARTIAL ·
true-video / cinematic-gate — still **never** sets ``final_complete``.
"""

from __future__ import annotations

import contextlib
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from director_review import SCORECARD_DIMENSIONS
from util import read_json, sha256_file, utc_now, write_json

RECEIPT_REL = Path("receipts/agent-review-final.json")
ASSIST_INPUT_REL = Path("receipts/final-review-input.assist.json")
APPLY_RECEIPT_REL = Path("receipts/agent-review-final-apply.json")

# Dimensions with direct machine-readable proxies on the film root.
_OBJECTIVE: frozenset[str] = frozenset(
    {
        "identity",
        "style",
        "motion",
        "escalation",
        "audio",
        "subs",
        "dead_air",
    }
)

# Artistic / narrative dimensions: provisional pass only when every objective L0 is green.
_SUBJECTIVE: frozenset[str] = frozenset(SCORECARD_DIMENSIONS) - _OBJECTIVE


class AgentReviewFinalError(ValueError):
    """Assist package cannot be built from the current film root."""


def _root(path: Path | str) -> Path:
    base = Path(path).expanduser().resolve()
    if not base.is_dir():
        raise AgentReviewFinalError("film root must be an existing directory")
    return base


def _final_record(root: Path) -> dict[str, Any] | None:
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else None
    if isinstance(rec, dict) and rec.get("path"):
        p = Path(str(rec["path"]))
        if not p.is_absolute():
            p = root / p
        if p.is_file():
            out = dict(rec)
            out["_resolved_path"] = str(p)
            if not out.get("sha256"):
                with contextlib.suppress(OSError):
                    out["sha256"] = sha256_file(p)
            return out
    for rel in ("out/film_final.mp4", "out/final.mp4", "out/plate.mp4", "out/final-plate.mp4"):
        p = root / rel
        if p.is_file():
            digest = ""
            with contextlib.suppress(OSError):
                digest = sha256_file(p)
            return {
                "path": str(p),
                "_resolved_path": str(p),
                "sha256": digest,
                "source": "filesystem",
            }
    return None


def _duration_sec(root: Path, final: dict[str, Any] | None) -> float:
    quality = read_json(root / "out" / "quality-report.json") or {}
    for key in ("duration_sec", "duration"):
        val = quality.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
            return float(val)
    if isinstance(final, dict):
        for key in ("duration_sec", "duration"):
            val = final.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
                return float(val)
    spec = read_json(root / "film-spec.json") or {}
    val = spec.get("duration_sec") if isinstance(spec, dict) else None
    if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
        return float(val)
    return 0.0


def _ts(index: int, total: int, duration: float) -> float:
    if duration <= 0:
        return 0.0
    if total <= 1:
        return round(min(duration * 0.5, duration), 3)
    return round(min(duration * 0.98, max(0.0, (index + 0.5) / total * duration)), 3)


def _gate_bool(gates: dict[str, Any], key: str) -> bool | None:
    if key not in gates:
        return None
    return bool(gates.get(key))


def _quality_gate_ok(quality: dict[str, Any], name: str) -> bool | None:
    gates = quality.get("gates") if isinstance(quality.get("gates"), dict) else {}
    gate = gates.get(name)
    if not isinstance(gate, dict):
        return None
    status = str(gate.get("status") or "").lower()
    if status == "pass":
        return True
    if status == "fail":
        return False
    return None


def _collect_l0(root: Path, *, final: dict[str, Any] | None, duration: float) -> dict[str, Any]:
    """Map scorecard dimensions → L0 pass/fail + evidence note (no network, no approve)."""
    man = read_json(root / "manifest.json") or {}
    gates = man.get("gates") if isinstance(man.get("gates"), dict) else {}
    quality = read_json(root / "out" / "quality-report.json") or {}
    if not isinstance(quality, dict):
        quality = {}
    heat: dict[str, Any] = {}
    try:
        from heat_check import heat_agent_status

        heat = heat_agent_status(root) or {}
    except Exception as exc:  # noqa: BLE001
        heat = {"active": False, "error": str(exc)[:160]}
    editorial = read_json(root / "receipts" / "final-editorial-review.json") or {}
    face = read_json(root / "receipts" / "face-identity.json") or {}
    srt = root / "out" / "final.srt"
    motion_gate = read_json(root / "receipts" / "i2v-final-gate.json") or {}
    if not isinstance(motion_gate, dict):
        motion_gate = read_json(root / "receipts" / "i2v-motion-gate.json") or {}

    dims: dict[str, dict[str, Any]] = {}

    # identity
    clips_ok = _gate_bool(gates, "clips_complete")
    face_ok = None
    if isinstance(face, dict) and face:
        face_ok = face.get("ok") is True or face.get("hard_fail") is not True
    identity_pass = True
    identity_notes: list[str] = []
    if clips_ok is False:
        identity_pass = False
        identity_notes.append("clips_complete=false")
    if face_ok is False:
        identity_pass = False
        identity_notes.append("face-identity not ok")
    if clips_ok is None and not final:
        identity_pass = False
        identity_notes.append("no final/plate media")
    if not identity_notes:
        identity_notes.append("clips/face L0 clear or not required")
    dims["identity"] = {
        "pass": identity_pass,
        "source": "l0",
        "note": "; ".join(identity_notes),
        "fail_code": None if identity_pass else "IDENTITY_DRIFT",
    }

    # style
    style_ok = _gate_bool(gates, "style_locked")
    style_pass = style_ok is not False  # missing style lock → soft pass for draft only
    dims["style"] = {
        "pass": style_pass,
        "source": "l0",
        "note": "style_locked" if style_ok else "style_locked missing/false — provisional",
        "fail_code": None if style_pass else "CONTINUITY_CHAIN_BROKEN",
    }

    # motion
    motion_q = _quality_gate_ok(quality, "motion")
    motion_gate_ok = None
    if isinstance(motion_gate, dict) and motion_gate:
        motion_gate_ok = motion_gate.get("ok") is True
    motion_pass = True
    motion_notes: list[str] = []
    if motion_q is False or motion_gate_ok is False:
        motion_pass = False
        motion_notes.append("motion gate/quality fail")
    elif motion_q is True or motion_gate_ok is True:
        motion_notes.append("motion quality/gate ok")
    else:
        # Delivery Truth: max/premium must not provisional-pass missing gate
        try:
            from util import read_json as _rj_motion

            _sp = _rj_motion(root / "film-spec.json") or {}
            _strict_motion = (
                str(_sp.get("heat_scale") or "").strip().lower() == "max"
                or _sp.get("premium_vertical") is True
                or _sp.get("dramatic_meaning_strict") is True
            )
        except Exception:  # noqa: BLE001
            _strict_motion = False
        if _strict_motion:
            motion_pass = False
            motion_notes.append("no motion receipt — fail for max/premium")
        else:
            motion_notes.append("no motion receipt — provisional pass")
    if quality.get("hard_fail") is True and motion_q is not True:
        # hard_fail elsewhere shouldn't auto-fail motion unless motion gate failed
        pass
    dims["motion"] = {
        "pass": motion_pass,
        "source": "l0",
        "note": "; ".join(motion_notes),
        "fail_code": None if motion_pass else "MOTION_LOW",
    }

    # escalation / heat
    heat_active = bool(heat.get("active"))
    heat_hard = bool(heat.get("hard_fail"))
    esc_pass = not (heat_active and heat_hard)
    dims["escalation"] = {
        "pass": esc_pass,
        "source": "l0",
        "note": (f"heat active hard_fail={heat_hard}" if heat_active else "heat inactive or clear"),
        "fail_code": None if esc_pass else "INVENTORY_INCOMPLETE",
    }

    # --- P3 machine lane (post) · advisory into objective dims ---
    machine_lane: dict[str, Any] = {
        "caption_pixel": None,
        "post_route": None,
        "timeline_clock": None,
        "post_doctor": None,
        "mix_partial": None,
        "true_video": None,
        "cinematic_gate": None,
    }

    # caption pixel ink
    try:
        from caption_pixel_check import caption_pixel_status

        cap = caption_pixel_status(root)
        machine_lane["caption_pixel"] = {
            "ok": cap.get("ok"),
            "missing_ink": cap.get("missing_ink"),
            "stale": cap.get("stale"),
            "skipped": cap.get("skipped"),
            "detail": cap.get("detail"),
        }
    except Exception as exc:  # noqa: BLE001
        machine_lane["caption_pixel"] = {"ok": None, "error": str(exc)[:160]}

    # post-route / double-burn risk
    route = read_json(root / "receipts" / "post-route.json") or {}
    if isinstance(route, dict) and route.get("caption_path"):
        machine_lane["post_route"] = {
            "caption_path": route.get("caption_path"),
            "plate_subs": route.get("plate_subs"),
        }
        try:
            from post_route import PostRouteError, assert_no_double_caption_layers

            delivery = read_json(root / "out" / "final-delivery.json") or {}
            subs_meta = (
                delivery.get("subtitles") if isinstance(delivery.get("subtitles"), dict) else {}
            )
            assert_no_double_caption_layers(
                caption_path=str(route.get("caption_path")),
                plate_subs=str(route.get("plate_subs") or ""),
                caption_owner=str(subs_meta.get("caption_owner") or ""),
            )
            machine_lane["post_route"]["double_burn_ok"] = True
        except Exception as exc:  # noqa: BLE001 — PostRouteError or import
            machine_lane["post_route"]["double_burn_ok"] = False
            machine_lane["post_route"]["error"] = str(exc)[:200]

    # timeline single clock
    try:
        from timeline_clock import audit_timeline_clock

        clock = audit_timeline_clock(root, write=False)
        machine_lane["timeline_clock"] = {
            "ok": clock.get("ok"),
            "dual_clock": clock.get("dual_clock"),
            "skipped": clock.get("skipped"),
            "error": clock.get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        machine_lane["timeline_clock"] = {"ok": None, "error": str(exc)[:160]}

    # post-doctor hard codes
    try:
        from post_doctor import run_post_doctor

        doctor = run_post_doctor(root, write=False)
        hard_codes = [
            str(i.get("code"))
            for i in (doctor.get("hard") or [])
            if isinstance(i, dict) and i.get("code")
        ]
        machine_lane["post_doctor"] = {
            "ok": doctor.get("ok"),
            "hard_codes": hard_codes,
        }
    except Exception as exc:  # noqa: BLE001
        machine_lane["post_doctor"] = {"ok": None, "error": str(exc)[:160]}

    # mix PARTIAL honesty
    mix = read_json(root / "receipts" / "final-mix-partial.json") or {}
    if isinstance(mix, dict) and mix.get("kind") == "final-mix-partial" and mix.get("partial"):
        machine_lane["mix_partial"] = {
            "partial": True,
            "reason_code": mix.get("reason_code") or mix.get("reason"),
            "affected_tracks": mix.get("affected_tracks"),
        }

    # true-video + cinematic-gate (motion-adjacent)
    tv = read_json(root / "receipts" / "true-video-policy.json") or {}
    if isinstance(tv, dict) and tv:
        machine_lane["true_video"] = {"ok": tv.get("ok")}
    cin = read_json(root / "receipts" / "cinematic-gate.json") or {}
    if isinstance(cin, dict) and cin:
        machine_lane["cinematic_gate"] = {"ok": cin.get("ok")}

    # motion: fold true-video / cinematic hard fails
    if machine_lane.get("true_video") and machine_lane["true_video"].get("ok") is False:
        motion_pass = False
        motion_notes.append("true_video_policy not ok")
    if machine_lane.get("cinematic_gate") and machine_lane["cinematic_gate"].get("ok") is False:
        motion_pass = False
        motion_notes.append("cinematic-gate not ok")
    dims["motion"] = {
        "pass": motion_pass,
        "source": "l0",
        "note": "; ".join(motion_notes),
        "fail_code": None if motion_pass else "MOTION_LOW",
    }

    # audio
    audio_q = _quality_gate_ok(quality, "audio")
    audio_pass = audio_q is not False
    audio_notes: list[str] = []
    if audio_q is True:
        audio_notes.append("quality audio pass")
    elif audio_q is False:
        audio_notes.append("quality audio fail")
    else:
        audio_notes.append("no audio quality gate — provisional")
    if machine_lane.get("mix_partial"):
        # PARTIAL is honesty, not auto-fail: note for human, keep pass unless quality red
        audio_notes.append(
            f"mix PARTIAL {machine_lane['mix_partial'].get('reason_code')} "
            f"tracks={machine_lane['mix_partial'].get('affected_tracks')}"
        )
    dims["audio"] = {
        "pass": audio_pass,
        "source": "l0",
        "note": "; ".join(audio_notes),
        "fail_code": None if audio_pass else "AUDIO_MISSING",
    }

    # subs · quality + caption pixel + double-burn + doctor hard caption codes
    subs_q = _quality_gate_ok(quality, "subtitles") or _quality_gate_ok(quality, "subs")
    srt_ok = srt.is_file() and srt.stat().st_size > 0
    subs_pass = True
    subs_notes: list[str] = [f"srt={'yes' if srt_ok else 'no'}", f"quality_subs={subs_q}"]
    if subs_q is False:
        subs_pass = False
        subs_notes.append("quality subtitles fail")
    cap_lane = machine_lane.get("caption_pixel") or {}
    # Only fail when a real pixel receipt is present and red (or explicit missing_ink).
    # Missing receipt stays provisional so assist still drafts before caption-pixel-check.
    if cap_lane.get("skipped"):
        subs_notes.append("caption_pixel skipped")
    elif cap_lane.get("missing_ink") is True:
        subs_pass = False
        subs_notes.append(f"caption_pixel missing_ink: {cap_lane.get('detail') or 'no ink'}")
    elif cap_lane.get("ok") is False and not str(cap_lane.get("detail") or "").startswith(
        "missing receipt"
    ):
        # stale / red with evidence — hard
        if cap_lane.get("stale") or cap_lane.get("present") is True:
            subs_pass = False
            subs_notes.append(f"caption_pixel red: {cap_lane.get('detail') or 'pixel red'}")
        else:
            subs_notes.append(
                f"caption_pixel not green yet (provisional): {cap_lane.get('detail')}"
            )
    elif cap_lane.get("ok") is True:
        subs_notes.append("caption_pixel ok")
    if (machine_lane.get("post_route") or {}).get("double_burn_ok") is False:
        subs_pass = False
        subs_notes.append("post-route double-burn risk")
    doctor_hard = set((machine_lane.get("post_doctor") or {}).get("hard_codes") or [])
    # Doctor hard caption codes only when not pure "missing receipt" provisional
    for code in ("DOUBLE_BURN_RISK", "SRT_OVERLAP", "SRT_BAD_CUE"):
        if code in doctor_hard:
            subs_pass = False
            subs_notes.append(f"post-doctor {code}")
    if "CAPTION_PIXEL_RED" in doctor_hard and cap_lane.get("missing_ink") is True:
        subs_pass = False
        subs_notes.append("post-doctor CAPTION_PIXEL_RED")
    dims["subs"] = {
        "pass": subs_pass,
        "source": "l0+post",
        "note": "; ".join(subs_notes),
        "fail_code": None if subs_pass else "SUBTITLE_DOUBLE_BURN",
    }

    # dead_air · freeze/black + dual timeline clock (subtitle cut risk)
    freeze = _quality_gate_ok(quality, "freeze") or _quality_gate_ok(quality, "freezes")
    black = _quality_gate_ok(quality, "black_frames") or _quality_gate_ok(quality, "black")
    dead_pass = freeze is not False and black is not False and quality.get("hard_fail") is not True
    dead_notes = [f"freeze={freeze}", f"black={black}", f"hard_fail={quality.get('hard_fail')}"]
    clock_lane = machine_lane.get("timeline_clock") or {}
    if clock_lane.get("dual_clock") is True:
        dead_pass = False
        dead_notes.append("DUAL_TIMELINE_CLOCK — rewrite film_timeline authority")
    if "DUAL_TIMELINE_CLOCK" in doctor_hard:
        dead_pass = False
        dead_notes.append("post-doctor DUAL_TIMELINE_CLOCK")
    dims["dead_air"] = {
        "pass": dead_pass,
        "source": "l0+post",
        "note": "; ".join(dead_notes),
        "fail_code": None if dead_pass else "DECODE_FAILED",
    }

    objective_all = all(dims[d]["pass"] for d in _OBJECTIVE if d in dims)

    # subjective dims
    for dim in SCORECARD_DIMENSIONS:
        if dim in dims:
            continue
        if dim == "rhythm" and isinstance(editorial, dict) and editorial:
            ed_ok = editorial.get("ok") is True
            dims[dim] = {
                "pass": ed_ok if editorial.get("ok") is not None else objective_all,
                "source": "l0+editorial" if editorial.get("ok") is not None else "assist",
                "note": (
                    "editorial review ok"
                    if ed_ok
                    else (
                        "editorial review failed"
                        if editorial.get("ok") is False
                        else "no editorial — provisional on L0"
                    )
                ),
                "fail_code": None
                if (ed_ok or (editorial.get("ok") is None and objective_all))
                else "DURATION_INVALID",
            }
            continue
        # provisional pass only when objective L0 all green
        dims[dim] = {
            "pass": objective_all,
            "source": "assist_provisional",
            "note": (
                "L0 objective green — provisional artistic pass; human must confirm full watch"
                if objective_all
                else "blocked: objective L0 not green — artistic dims fail-closed"
            ),
            "fail_code": None if objective_all else "INVENTORY_INCOMPLETE",
        }

    # timestamps + grades
    ordered = list(SCORECARD_DIMENSIONS)
    for i, dim in enumerate(ordered):
        row = dims[dim]
        row["timestamp_sec"] = _ts(i, len(ordered), duration)
        row["grade"] = 4 if row["pass"] and row.get("source") == "l0" else (3 if row["pass"] else 1)
        row["evidence_note"] = (f"[{row.get('source')}] {row.get('note')}")[:480]

    return {
        "objective_all_pass": objective_all,
        "dimensions": dims,
        "machine_lane": machine_lane,
        "heat": {
            "active": heat.get("active"),
            "hard_fail": heat.get("hard_fail"),
            "why": heat.get("why"),
        },
        "quality_hard_fail": quality.get("hard_fail"),
        "gates": {
            "clips_complete": gates.get("clips_complete"),
            "style_locked": gates.get("style_locked"),
            "final_complete": gates.get("final_complete"),
        },
    }


def _build_scorecard(l0: dict[str, Any]) -> dict[str, str]:
    dims = l0.get("dimensions") or {}
    return {
        dim: ("pass" if (dims.get(dim) or {}).get("pass") else "fail")
        for dim in SCORECARD_DIMENSIONS
    }


def _build_evidence(l0: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dims = l0.get("dimensions") or {}
    out: dict[str, dict[str, Any]] = {}
    for dim in SCORECARD_DIMENSIONS:
        row = dims.get(dim) or {}
        out[dim] = {
            "timestamp_sec": float(row.get("timestamp_sec") or 0.0),
            "note": str(row.get("evidence_note") or row.get("note") or "assist"),
        }
    return out


def _build_grades(l0: dict[str, Any]) -> dict[str, int]:
    dims = l0.get("dimensions") or {}
    return {dim: int((dims.get(dim) or {}).get("grade") or 1) for dim in SCORECARD_DIMENSIONS}


def _build_fail_reasons(l0: dict[str, Any]) -> dict[str, list[str]]:
    dims = l0.get("dimensions") or {}
    out: dict[str, list[str]] = {}
    for dim in SCORECARD_DIMENSIONS:
        row = dims.get(dim) or {}
        if row.get("pass"):
            continue
        code = str(row.get("fail_code") or "INVENTORY_INCOMPLETE")
        out[dim] = [code]
    return out


def _review_final_cmd(
    root: Path,
    *,
    scorecard: dict[str, str],
    grades: dict[str, int],
    evidence: dict[str, dict[str, Any]],
    fail_reasons: dict[str, list[str]],
    reviewer: str,
    notes: str,
    assist_path: Path | None,
) -> str:
    if assist_path is not None and reviewer and not reviewer.startswith("<"):
        # Prefer review-file path when assist input is fully bound.
        return (
            f"aifilm review-final --root {shlex.quote(str(root))} "
            f"--review-file {shlex.quote(str(assist_path))}"
        )
    parts = [
        "aifilm",
        "review-final",
        "--root",
        str(root),
        "--approve",
        "--watched-full",
        "--reviewer",
        reviewer or "YOU",
        "--notes",
        notes or "已完整观看；确认 agent assist 草案",
    ]
    for dim in SCORECARD_DIMENSIONS:
        flag = dim.replace("_", "-")
        parts.extend([f"--score-{flag}", scorecard[dim]])
        parts.extend([f"--grade-{flag}", str(grades[dim])])
    for dim in SCORECARD_DIMENSIONS:
        item = evidence[dim]
        parts.extend(
            [
                "--screening-evidence",
                f"{dim}@{item['timestamp_sec']}:{item['note']}",
            ]
        )
    for dim, reasons in fail_reasons.items():
        for reason in reasons:
            parts.extend(["--fail-reason", f"{dim}:{reason}"])
    return " ".join(shlex.quote(p) for p in parts)


def build_agent_review_final(
    root: Path | str,
    *,
    reviewer: str | None = None,
    notes: str | None = None,
    human_minutes: float | None = None,
    write: bool = True,
    write_assist_input: bool = True,
) -> dict[str, Any]:
    """Build assist package. Never sets gates.final_complete and never approves."""
    base = _root(root)
    final = _final_record(base)
    if not final:
        raise AgentReviewFinalError(
            "no final/plate media under out/ or manifest.outputs.final_film"
        )
    duration = _duration_sec(base, final)
    l0 = _collect_l0(base, final=final, duration=duration)
    scorecard = _build_scorecard(l0)
    grades = _build_grades(l0)
    evidence = _build_evidence(l0)
    fail_reasons = _build_fail_reasons(l0)
    all_pass = all(v == "pass" for v in scorecard.values())
    rev = (reviewer or "").strip()
    note_text = (notes or "").strip() or (
        "Agent assist draft from L0 receipts — human confirms full-film watch"
    )
    minutes = (
        human_minutes if human_minutes is not None else max(1.0, round(duration / 60.0, 2) or 1.0)
    )
    if not (0 < float(minutes) <= 1440):
        minutes = 1.0

    man = read_json(base / "manifest.json") or {}
    contract = int(man.get("review_contract_version") or 3)
    final_sha = str(final.get("sha256") or "").strip()

    assist_input: dict[str, Any] | None = None
    assist_path: Path | None = None
    # Only write a valid final-review-input when human identity is supplied.
    # Without reviewer the package is evidence-only (still useful for paste cmd).
    if write_assist_input and rev and final_sha:
        assist_input = {
            "schema_version": 1,
            "kind": "final-review-input",
            "approve": True,
            "reviewer": rev,
            "notes": note_text,
            "watched_full": True,
            "final_output_sha256": final_sha,
            "human_minutes": float(minutes),
            "scorecard": scorecard,
            "grades": grades,
            "screening_evidence": evidence,
            "fail_reasons": fail_reasons,
            "reshoot_shots": [],
            "assist": {
                "mode": "agent_assist",
                "never_auto_approved": True,
                "objective_all_pass": l0.get("objective_all_pass"),
                "provisional_subjective": True,
            },
        }
        assist_path = base / ASSIST_INPUT_REL

    cmd = _review_final_cmd(
        base,
        scorecard=scorecard,
        grades=grades,
        evidence=evidence,
        fail_reasons=fail_reasons,
        reviewer=rev or "YOU",
        notes=note_text,
        assist_path=assist_path if assist_input else None,
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "agent-review-final",
        "mode": "assist",
        "at": utc_now(),
        "root": str(base),
        "ok": True,
        "auto_approved": False,
        "never_auto_approves_review_final": True,
        "all_pass_suggested": all_pass,
        "ready_for_human_confirm": bool(all_pass and final_sha),
        "objective_all_pass": bool(l0.get("objective_all_pass")),
        "final": {
            "path": final.get("_resolved_path") or final.get("path"),
            "sha256": final_sha,
            "source": final.get("source"),
            "duration_sec": duration,
        },
        "review_contract_version": contract,
        "l0": l0,
        "machine_lane": (l0.get("machine_lane") if isinstance(l0, dict) else None),
        "scorecard": scorecard,
        "grades": grades,
        "screening_evidence": evidence,
        "fail_reasons": fail_reasons,
        "reviewer_bound": bool(rev),
        "p3_post_lane": True,
        "next_cmd": cmd,
        "human_next": (
            f'aifilm agent-review-final --root "{base}" --apply '
            f'--reviewer <你> --user-phrase "可以" --notes "已完整观看"'
            if all_pass
            else "L0 有红项：先按 fail_reasons 修片，再重跑 agent-review-final"
        ),
        "apply_cmd": (
            f'aifilm agent-review-final --root "{base}" --apply '
            f'--reviewer REVIEWER --user-phrase "可以" --notes "已完整观看"'
            if all_pass
            else None
        ),
        "receipt_path": str(base / RECEIPT_REL),
        "assist_input_path": str(assist_path) if assist_path else None,
    }

    if write:
        write_json(base / RECEIPT_REL, report)
        if assist_input is not None and assist_path is not None:
            write_json(assist_path, assist_input)
            report["assist_input_written"] = True
        else:
            report["assist_input_written"] = False

    return report


def agent_review_stale(root: Path | str) -> bool:
    """True when assist receipt is missing or final sha drifted."""
    base = _root(root)
    rec = read_json(base / RECEIPT_REL) or {}
    if not isinstance(rec, dict) or rec.get("kind") != "agent-review-final":
        return True
    final = _final_record(base)
    if not final:
        return True
    return str((rec.get("final") or {}).get("sha256") or "") != str(final.get("sha256") or "")


def apply_agent_review_final(
    root: Path | str,
    *,
    reviewer: str,
    user_phrase: str,
    notes: str | None = None,
    human_minutes: float | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """One-shot: rebuild assist + run review-final when user phrase is real approval.

    Still fail-closed on technical gates inside review-final. Never forges a
    phrase; never applies without ``user_phrase_is_approval``.
    """
    from pilot_review import user_phrase_is_approval

    base = _root(root)
    rev = (reviewer or "").strip()
    phrase = (user_phrase or "").strip()
    if not rev:
        raise AgentReviewFinalError("--apply requires --reviewer (human name)")
    if not phrase or not user_phrase_is_approval(phrase):
        raise AgentReviewFinalError(
            "--apply requires a verbatim user approval phrase "
            '(e.g. "可以" / "ok" / "做完" / "一路做完"); agent must not invent one'
        )

    note_text = (notes or "").strip() or f"已完整观看；用户原话确认：{phrase}"
    draft = build_agent_review_final(
        base,
        reviewer=rev,
        notes=note_text,
        human_minutes=human_minutes,
        write=True,
        write_assist_input=True,
    )
    if not draft.get("all_pass_suggested"):
        raise AgentReviewFinalError(
            "assist scorecard is not all-pass; fix L0 fail_reasons before --apply"
        )
    if not draft.get("objective_all_pass"):
        raise AgentReviewFinalError("objective L0 not green; refuse --apply")
    assist_path = draft.get("assist_input_path")
    if not assist_path or not Path(str(assist_path)).is_file():
        raise AgentReviewFinalError("assist input JSON missing after rebuild")

    argv = [
        str(Path(sys.executable).resolve()),
            str((Path(__file__).resolve().parents[1] / "aifilm_grok.py").resolve()),
        "review-final",
        "--root",
        str(base),
        "--review-file",
        str(assist_path),
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "agent-review-final-apply",
        "at": utc_now(),
        "root": str(base),
        "reviewer": rev,
        "user_phrase": phrase,
        "assist_input_path": str(assist_path),
        "draft_receipt": draft.get("receipt_path"),
        "all_pass_suggested": True,
        "objective_all_pass": True,
        "dry_run": dry_run,
        "auto_forged": False,
        "argv": argv[2:],
    }
    if dry_run:
        payload["ok"] = True
        payload["applied"] = False
        payload["note"] = "dry-run only; review-final not executed"
        write_json(base / APPLY_RECEIPT_REL, payload)
        return payload

    process = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    payload["returncode"] = process.returncode
    payload["stdout_tail"] = (process.stdout or "")[-3000:]
    payload["stderr_tail"] = (process.stderr or "")[-3000:]
    payload["ok"] = process.returncode == 0
    payload["applied"] = process.returncode == 0
    if process.returncode == 0:
        payload["note"] = "review-final accepted assist package; final_complete depends on gates"
    else:
        payload["error"] = (
            "review-final rejected assist (technical/editorial gates still apply). "
            "Inspect stderr_tail; fix then re-run --apply."
        )
    write_json(base / APPLY_RECEIPT_REL, payload)
    # refresh main assist receipt with apply pointer
    main = read_json(base / RECEIPT_REL) or {}
    if isinstance(main, dict):
        main["apply_receipt"] = str(base / APPLY_RECEIPT_REL)
        main["last_apply_ok"] = payload["ok"]
        main["last_apply_at"] = payload["at"]
        write_json(base / RECEIPT_REL, main)
    return payload
