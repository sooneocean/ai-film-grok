"""I4.2 · iron-status — list machine iron gates + escape env (CTO A1 / iron plan).

Read-only. Does not change film state.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import utc_now

# (id, label, escape_env, notes)
_IRON_GATES: list[tuple[str, str, str, str]] = [
    ("anti_hijack", "multi-seed composition anti-hijack", "AIFILM_SKIP_ANTI_HIJACK", "select-shortlist / pk"),
    ("variety_preflight", "meat pose/CU/L4 field variety", "AIFILM_SKIP_VARIETY_PREFLIGHT", "bulk / h3 register"),
    ("variety_pixel", "field≠pixel bind", "AIFILM_SKIP_VARIETY_PIXEL", "ship-prep / gate-auto"),
    ("plate_boring", "meat mean≪20 → plate only", "AIFILM_SKIP_PLATE_BORING", "delivery_class / closeout"),
    ("anatomy_safe", "human anatomy attestation", "AIFILM_SKIP_ANATOMY_SAFETY", "H3 + media-queue"),
    ("generation_request", "material fidelity request", "AIFILM_SKIP_GENERATION_REQUEST", "restricted I2V"),
    ("endframe_wardrobe", "endframe no-redress heuristic", "AIFILM_SKIP_ENDFRAME_WARDROBE", "register-clip"),
    ("scale_promote", "scale_fallback promote_ban", "AIFILM_SKIP_SCALE_PROMOTE_GATE", "register still/clip"),
    ("speaker_frame", "on_camera speaker=picture", "speaker_frame_strict:false", "preflight / write-spec"),
    ("gate_auto", "machine lane", "AIFILM_SKIP_GATE_AUTO", "closeout / export"),
    ("true_video", "still not hero", "AIFILM_SKIP_TRUE_VIDEO_POLICY", "register / final"),
    ("i2v_motion", "mean floors 18/20", "AIFILM_SKIP_I2V_MOTION_GATE", "export-desktop"),
    ("heat_queue", "adult max queue hard", "AIFILM_SKIP_HEAT_QUEUE_GATE", "media-queue add"),
    ("heat_final", "adult max final hard", "AIFILM_SKIP_HEAT_FINAL_GATE", "final / export"),
    ("mix_acrossover", "legacy multiband mix", "AIFILM_ALLOW_ACROSSOVER_MIX", "default=broadband"),
    (
        "gpu_no_hog",
        "multi-agent 5090 no-hog / dual-film lease",
        "AIFILM_I_OWN_THE_GPU",
        "until-empty needs --i-own-the-gpu; foreign LEASE_HELD blocks; unowned run-next max 5",
    ),
    (
        "composition_fill",
        "I2V first-frame subject fill ≥~75%",
        "AIFILM_SKIP_COMPOSITION_FILL",
        "register-still / H3 / generation_ready",
    ),
    (
        "identity_generation",
        "one cast generation / no archive mix / verified honesty",
        "AIFILM_SKIP_IDENTITY_GEN",
        "closeout / ship-prep; IDENTITY_PARTIAL if unverified",
    ),
    (
        "partner_cast",
        "on-camera cast_master+face_lock; style.locked not heroine-only",
        "AIFILM_SKIP_PARTNER_CAST",
        "preflight / style lock",
    ),
    (
        "face_lock_triple",
        "face_identity ∧ identity_gen ∧ partner; master_eligible honesty",
        "AIFILM_SKIP_FACE_IDENTITY_GATE",
        "closeout / ship-prep; plate if not master_eligible",
    ),
    (
        "still_face_lock_bind",
        "still binds current face-lock enroll; ban archive still for H3",
        "AIFILM_SKIP_STILL_FACE_LOCK",
        "generation_ready / generation_request",
    ),
    (
        "plate_transition_align",
        "plate xfade styles match transition_ops.picture",
        "AIFILM_SKIP_TRANSITION_POLICY_GATE",
        "render_final concat",
    ),
    (
        "transition_frame_audit",
        "final+delivery requires non-stale transition-frame-audit",
        "AIFILM_SKIP_TRANSITION_FRAME_AUDIT",
        "closeout / ship-prep",
    ),
    (
        "still_provenance",
        "ban midframe composite / poison archive still as I2V source",
        "AIFILM_SKIP_STILL_PROVENANCE",
        "register-still / H3",
    ),
    (
        "skip_audit",
        "AIFILM_SKIP_* runtime ledger → receipts/skip-usage.json",
        "AIFILM_SKIP_REASON",
        "closeout verify_skip_usage; IRON skip needs reason",
    ),
]


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def iron_floors() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from edit_policy import DEFAULT_SEX_DURATION_FLOOR

        out["sex_duration_floor"] = DEFAULT_SEX_DURATION_FLOOR
    except Exception as exc:
        out["sex_duration_floor_error"] = str(exc)[:80]
    try:
        from i2v_motion_gate import MEAN_MEAT_FLOOR, MEAN_NORMAL_FLOOR

        out["mean_normal"] = MEAN_NORMAL_FLOOR
        out["mean_meat"] = MEAN_MEAT_FLOOR
    except Exception as exc:
        out["mean_error"] = str(exc)[:80]
    try:
        from final.delivery_class import PLATE_BORING_MEAT_FLOOR

        out["plate_boring_meat_floor"] = PLATE_BORING_MEAT_FLOOR
    except Exception as exc:
        # A1 · surface import/probe fail (never leave floor missing silently)
        out["plate_boring_meat_floor_error"] = str(exc)[:80]
    return out


def iron_status_report(root: Path | str | None = None) -> dict[str, Any]:
    """Snapshot of iron gates: which escapes are currently armed."""
    gates: list[dict[str, Any]] = []
    armed_escapes: list[str] = []
    for gid, label, escape, notes in _IRON_GATES:
        if escape.endswith(":false"):
            # film-spec flag; only report name
            skipped = False
            env_set = False
        else:
            env_set = _env_on(escape) if escape.startswith("AIFILM_") else False
            skipped = env_set
            if env_set:
                armed_escapes.append(escape)
        gates.append(
            {
                "id": gid,
                "label": label,
                "escape": escape,
                "escape_armed": skipped,
                "notes": notes,
            }
        )
    film: dict[str, Any] = {}
    if root is not None:
        base = Path(root).expanduser().resolve()
        film["root"] = str(base)
        try:
            from util import read_json

            spec = read_json(base / "film-spec.json") or {}
            if isinstance(spec, dict):
                film["heat_scale"] = spec.get("heat_scale")
                film["vo_mode"] = spec.get("vo_mode")
                film["genre"] = spec.get("genre")
                film["speaker_frame_strict"] = spec.get("speaker_frame_strict")
                film["adult_max_iron"] = spec.get("adult_max_iron")
            for rel in (
                "receipts/scale-fallback.json",
                "receipts/plate-boring-mean.json",
                "receipts/gate-auto.json",
                "receipts/official-final-report.json",
            ):
                p = base / rel
                if p.is_file():
                    data = read_json(p) or {}
                    film[rel] = {
                        "ok": data.get("ok") if "ok" in data else None,
                        "status": data.get("status"),
                        "partial": data.get("partial"),
                        "promote_ban": data.get("promote_ban"),
                        "boring": data.get("boring"),
                    }
        except Exception as exc:
            film["error"] = str(exc)[:160]

    return {
        "schema_version": 1,
        "kind": "iron-status",
        "at": utc_now(),
        "floors": iron_floors(),
        "gates": gates,
        "escape_armed": armed_escapes,
        "escape_count": len(armed_escapes),
        "film": film or None,
        "note": (
            "escape_armed>0 means IRON gates are skipped — not production default"
            if armed_escapes
            else "no AIFILM_SKIP_* iron escapes armed in this process env"
        ),
        "next_cmd": 'aifilm iron-status --root "$ROOT"  # optional film receipts',
    }
