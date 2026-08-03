#!/usr/bin/env python3
"""P1 · Agent assist for review-final (never auto-approves).

Builds a full director scorecard draft from L0 machine evidence already on disk,
writes ``receipts/agent-review-final.json`` + an optional hash-bound
``final-review-input.assist.json``, and emits a paste-ready ``review-final``
command for the human. Artistic sign-off remains ``review-final --approve``.
"""

from __future__ import annotations

import contextlib
import shlex
from pathlib import Path
from typing import Any

from director_review import SCORECARD_DIMENSIONS
from util import read_json, sha256_file, utc_now, write_json

RECEIPT_REL = Path("receipts/agent-review-final.json")
ASSIST_INPUT_REL = Path("receipts/final-review-input.assist.json")

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
        "note": (
            f"heat active hard_fail={heat_hard}"
            if heat_active
            else "heat inactive or clear"
        ),
        "fail_code": None if esc_pass else "INVENTORY_INCOMPLETE",
    }

    # audio
    audio_q = _quality_gate_ok(quality, "audio")
    audio_pass = audio_q is not False
    dims["audio"] = {
        "pass": audio_pass,
        "source": "l0",
        "note": (
            "quality audio pass"
            if audio_q is True
            else ("quality audio fail" if audio_q is False else "no audio quality gate — provisional")
        ),
        "fail_code": None if audio_pass else "AUDIO_MISSING",
    }

    # subs
    subs_q = _quality_gate_ok(quality, "subtitles") or _quality_gate_ok(quality, "subs")
    srt_ok = srt.is_file() and srt.stat().st_size > 0
    subs_pass = True
    if subs_q is False:
        subs_pass = False
    elif not srt_ok and subs_q is not True:
        # missing SRT is a soft fail for assist (many plates use burned-only)
        subs_pass = True
    dims["subs"] = {
        "pass": subs_pass,
        "source": "l0",
        "note": (
            f"srt={'yes' if srt_ok else 'no'}; quality_subs={subs_q}"
        ),
        "fail_code": None if subs_pass else "SUBTITLE_DOUBLE_BURN",
    }

    # dead_air
    freeze = _quality_gate_ok(quality, "freeze") or _quality_gate_ok(quality, "freezes")
    black = _quality_gate_ok(quality, "black_frames") or _quality_gate_ok(quality, "black")
    dead_pass = freeze is not False and black is not False and quality.get("hard_fail") is not True
    dims["dead_air"] = {
        "pass": dead_pass,
        "source": "l0",
        "note": f"freeze={freeze} black={black} hard_fail={quality.get('hard_fail')}",
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
                "fail_code": None if (ed_ok or (editorial.get("ok") is None and objective_all)) else "DURATION_INVALID",
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
        row["evidence_note"] = (
            f"[{row.get('source')}] {row.get('note')}"
        )[:480]

    return {
        "objective_all_pass": objective_all,
        "dimensions": dims,
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
    return {
        dim: int((dims.get(dim) or {}).get("grade") or 1)
        for dim in SCORECARD_DIMENSIONS
    }


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
    minutes = human_minutes if human_minutes is not None else max(1.0, round(duration / 60.0, 2) or 1.0)
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
        "scorecard": scorecard,
        "grades": grades,
        "screening_evidence": evidence,
        "fail_reasons": fail_reasons,
        "reviewer_bound": bool(rev),
        "next_cmd": cmd,
        "human_next": (
            "完整观看成片后执行 next_cmd（或 review-final --review-file assist）；"
            "本命令绝不自动 --approve"
            if all_pass
            else "L0 有红项：先按 fail_reasons 修片，再重跑 agent-review-final"
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
