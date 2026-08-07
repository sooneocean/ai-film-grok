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
    except Exception:
        pass
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
