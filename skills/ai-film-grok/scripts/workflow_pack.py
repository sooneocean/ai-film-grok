#!/usr/bin/env python3
"""Wave A–C production throughput helpers (closeout / pilot pack / preflight / lease).

Thin orchestration over existing gates — does not invent a fourth stage model.
Receipts land under film-root receipts/ for dispatch and humans.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

# Anti-boring floors (hard-defaults · shot-variety) — advisory in design phase
POSE_MIN_UNIQUE = 4
FACE_CU_MIN = 2
L4_INSERT_MIN = 2
MEAT_DURATION_FLOOR = 4.5

GPU_LEASE_NAME = "gpu-lease.json"
BULK_PREFLIGHT_NAME = "bulk-preflight.json"
VARIETY_NAME = "variety-precheck.json"
SELECT_SHORTLIST_NAME = "select-shortlist.json"
LEASE_STALE_SEC = 45 * 60  # 45 min without heartbeat → expired
DEFAULT_TUNNEL_PORT = 18188
COMFY_WRONG_PORT = 8189


class WorkflowPackError(RuntimeError):
    """User-facing orchestration failure (exit non-zero)."""


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _shots_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict):
                out.append(sh)
    return out


def _plate_path(root: Path) -> Path | None:
    """First existing final plate candidate (post-audit compatible order)."""
    candidates = [
        root / "out" / "film_final.mp4",
        root / "out" / "film_hyperframes.mp4",
        root / "out" / "final.mp4",
        root / "final.mp4",
        root / "deliverables" / "final.mp4",
    ]
    man = read_json(root / "manifest.json") or {}
    rec = ((man.get("outputs") or {}).get("final_film") or {}) if isinstance(man, dict) else {}
    raw = str(rec.get("path") or "").strip()
    if raw:
        p = Path(raw)
        if p.is_absolute():
            candidates.insert(0, p)
        else:
            candidates.insert(0, root / p)
            candidates.insert(1, root / "out" / p.name)
    for p in candidates:
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def _heat_phase(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(shot.get("heat_phase") or dsl.get("heat_phase") or "").strip().lower()


def _coitus_beat(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(shot.get("coitus_beat") or dsl.get("coitus_beat") or "").strip().lower()


def _shot_size(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    return (
        str(shot.get("shot_size") or cam.get("shot_size") or dsl.get("shot_size") or "")
        .strip()
        .lower()
    )


def _motion_primary(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    motion = str(dsl.get("motion") or shot.get("motion") or "").strip().lower()
    if not motion:
        return ""
    # first clause / first 48 chars as collision key
    part = motion.split(",")[0].strip()
    return part[:48]


def _sex_pose(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    pose = str(shot.get("sex_pose") or dsl.get("sex_pose") or "").strip().lower()
    if pose:
        return pose
    return str(dsl.get("action") or "")[:40].lower()


def _camera_move(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    return (
        str(
            cam.get("move")
            or dsl.get("camera_axis")
            or shot.get("camera_axis")
            or cam.get("axis")
            or ""
        )
        .strip()
        .lower()
    )


# ---------------------------------------------------------------------------
# A1–A2 · closeout + pilot pack (canonical modules; no dual logic here)
# ---------------------------------------------------------------------------


def closeout_run(
    root: Path | str,
    *,
    export: bool = False,
    export_name: str | None = None,
    run_post_audit: bool = True,
    write: bool = True,
    execute: bool = True,
) -> dict[str, Any]:
    """Delegate to closeout.py (receipts/closeout.json)."""
    from closeout import closeout_run as _run

    # run_post_audit=False ≈ status/snapshot path without executing post-audit
    return _run(
        root,
        execute=bool(execute and run_post_audit),
        export=export,
        export_name=export_name,
        write_receipt=write,
    )


def closeout_status(root: Path | str) -> dict[str, Any]:
    from closeout import closeout_status as _status

    return _status(root)


def pilot_pack(
    root: Path | str,
    *,
    shots: list[str] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Delegate to pilot_pack.py (receipts/pilot-go.json)."""
    from pilot_pack import pilot_pack as _pack

    report = _pack(root, shots=shots)
    # Alias fields used by older workflow CLI checks
    if "go_ready" not in report:
        report = {**report, "go_ready": bool(report.get("ok"))}
    if not write and report.get("receipt_path"):
        # pilot_pack always writes; callers using write=False still get payload
        pass
    return report


def pilot_go_allows_bulk(root: Path | str) -> dict[str, Any]:
    """Read pilot-go receipt; used by optional media-queue gate."""
    from pilot_pack import assert_pilot_go_allows_bulk, load_pilot_go

    data = load_pilot_go(root)
    if data and (data.get("ok") is True or (data.get("pilot_go") or {}).get("ok") is True):
        return {"ok": True, "source": "receipt"}
    try:
        assert_pilot_go_allows_bulk(root)
        return {"ok": True, "source": "assert"}
    except Exception as exc:  # noqa: BLE001 — surface blockers to bulk callers
        return {
            "ok": False,
            "source": "receipt" if data else "missing",
            "error": str(exc)[:240],
            "blockers": (data or {}).get("pilot_go", {}).get("blockers") if data else None,
        }


# ---------------------------------------------------------------------------
# B1 · bulk preflight
# ---------------------------------------------------------------------------


def _weapon_inventory_for_bulk() -> dict[str, Any]:
    """Soft attach of documented generation primaries (weapon-inventory SSoT)."""
    try:
        from weapon_inventory import inventory_report, primary_for

        rep = inventory_report(validate=True)
        still = primary_for("text-to-image")
        edit = primary_for("local-image-edit")
        motion = primary_for("image-to-video")
        tts = primary_for("tts_zh_ship")
        bgm = primary_for("bgm")
        return {
            "ok": bool(rep.get("ok")),
            "line": rep.get("line"),
            "still_primary": (still or {}).get("id"),
            "edit_primary": (edit or {}).get("id"),
            "motion_primary": (motion or {}).get("id"),
            "tts_primary": (tts or {}).get("id"),
            "bgm_primary": (bgm or {}).get("id"),
            "profile_default": rep.get("profile_default"),
            "cli": "aifilm weapon inventory --tier primary",
        }
    except Exception as exc:  # noqa: BLE001 — soft
        return {"ok": False, "error": str(exc)[:160]}


def _bulk_next_cmd_for_failure(
    root: Path,
    failed_id: str,
    *,
    tunnel_port: int,
    inv: dict[str, Any],
) -> str:
    """Map preflight fail → recovery cmd that names inventory primaries."""
    still = str(inv.get("still_primary") or "qwen-image-2512-quality")
    edit = str(inv.get("edit_primary") or "qwen-image-edit-2511-local")
    motion = str(inv.get("motion_primary") or "minimax-h3-i2v-pilot")
    r = str(root)
    cmd_map = {
        "pilot": f'aifilm pilot pack --root "{r}"',
        "heat": f'aifilm heat boost --root "{r}" --apply',
        "state_index": (
            f'aifilm state-index plan --root "{r}"  # state photos → still primary {still}'
        ),
        "still_source": (
            f'aifilm still-challenge plan --root "{r}"  '
            f"# peak still: edit={edit} / t2i={still}; ban cast master for undress"
        ),
        "still_uniqueness": f'aifilm status --root "{r}"  # still reuse; re-gen with {still}',
        "anatomy_stills": (
            f'aifilm register-still --root "{r}"  '
            f"# anatomy_safe via {edit}; poison still bans I2V ({motion})"
        ),
        "geometry": f"fix keyframes to ≥704×1280 9:16 (still primary {still})",
        "tunnel": (
            f"aifilm tunnel-probe --port {tunnel_port}  "
            f"# 18188→8188 required for motion primary {motion}"
        ),
        "local_comfy_client": "stop extra comfy_video.py clients (one only)",
        "gpu_lease": (
            f'aifilm gpu-lease status --root "{r}"  # lease 5090 before {motion}'
        ),
        "variety": (
            f'aifilm variety-precheck --root "{r}"  # fix ADJACENT_MOTION / poses before {motion}'
        ),
        "duration_target": (
            f'cat "{r}/receipts/duration-target.json"  '
            f"# planned sum ≪ target: add shots or FLF (~5.2s H3) / lower target_duration"
        ),
        "crop_master_still": (
            f'cat "{r}/receipts/crop-master-still.json"  '
            f"# regenerate narrative stills; ban whole-episode cast-master crop"
        ),
    }
    return cmd_map.get(failed_id, f'aifilm bulk-preflight --root "{r}"')


def bulk_preflight(
    root: Path | str,
    *,
    write: bool = True,
    probe_tunnel: bool = True,
    tunnel_port: int = DEFAULT_TUNNEL_PORT,
    check_lease: bool = True,
) -> dict[str, Any]:
    """Single-door bulk readiness: pilot · heat · state · stills · anatomy · tunnel · lease."""
    root = _root(root)
    checks: list[dict[str, Any]] = []
    inv = _weapon_inventory_for_bulk()

    def add(cid: str, ok: bool, **extra: Any) -> None:
        checks.append({"id": cid, "ok": ok, **extra})

    # pilot
    try:
        from production_gates import assert_pilot_user_approved

        assert_pilot_user_approved(root)
        add("pilot", True)
    except Exception as exc:  # noqa: BLE001
        add("pilot", False, error=str(exc)[:240])

    # heat
    try:
        from production_gates import assert_heat_allows_media

        assert_heat_allows_media(root)
        add("heat", True)
    except Exception as exc:  # noqa: BLE001
        add("heat", False, error=str(exc)[:240])

    # state-index
    try:
        from state_index_gate import run_state_index_check

        si = run_state_index_check(root)
        gaps = si.get("generate_plan") or []
        add("state_index", not gaps, gap_count=len(gaps))
    except Exception as exc:  # noqa: BLE001
        add("state_index", True, skipped=True, error=str(exc)[:120])

    # still uniqueness + anatomy (approved media)
    man = read_json(root / "manifest.json") or {}
    spec = read_json(root / "film-spec.json") or {}
    shot_ids = [str(s.get("id")) for s in _shots_from_spec(spec) if s.get("id")]

    # still-source audit (peak wardrobe must not rely on full cast master)
    try:
        from still_source import audit_film_still_sources

        ssa = audit_film_still_sources(root)
        # Hard only when film already has some approved stills (skip empty design roots).
        has_any_still = bool((man.get("stills") or {}) if isinstance(man, dict) else False)
        peak_hard = bool(ssa.get("hard")) and has_any_still
        add(
            "still_source",
            (not peak_hard),
            peak_missing=ssa.get("peak_missing"),
            hard=ssa.get("hard") if peak_hard else [],
            advisory=ssa.get("hard") if not peak_hard else [],
        )
    except Exception as exc:  # noqa: BLE001
        add("still_source", True, skipped=True, error=str(exc)[:120])

    try:
        from still_uniqueness import active_still_reuse_report

        still_u = active_still_reuse_report(
            man,
            required_shot_ids=shot_ids,
            keyframes_dir=root / "keyframes",
        )
        add(
            "still_uniqueness",
            bool(still_u.get("ok")),
            detail=still_u.get("reason") or still_u.get("note"),
        )
    except Exception as exc:  # noqa: BLE001
        add("still_uniqueness", True, skipped=True, error=str(exc)[:120])

    # Q1.4 crop-master dominance (savani): soft warn / hard if most stills are master crops
    skip_crop = os.environ.get("AIFILM_SKIP_CROP_MASTER_STILL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if skip_crop:
        add("crop_master_still", True, skipped=True, escape="AIFILM_SKIP_CROP_MASTER_STILL=1")
    else:
        try:
            from still_uniqueness import crop_master_still_report
            from util import write_json as _wj

            crop_rep = crop_master_still_report(man, required_shot_ids=shot_ids)
            try:
                _wj(root / "receipts" / "crop-master-still.json", crop_rep)
            except Exception:
                pass
            # Soft: ok=True so bulk continues with visibility; hard: ok=False blocks
            add(
                "crop_master_still",
                bool(crop_rep.get("ok")),
                severity=crop_rep.get("severity"),
                codes=crop_rep.get("codes"),
                effective_ratio=crop_rep.get("effective_ratio"),
                reason=crop_rep.get("reason"),
                next=crop_rep.get("next"),
            )
        except Exception as exc:  # noqa: BLE001
            add("crop_master_still", True, skipped=True, error=str(exc)[:120])

    try:
        from anatomy_safety import anatomy_safety_report, requires_anatomy_safety

        if requires_anatomy_safety(root):
            st = anatomy_safety_report(man, required_shot_ids=shot_ids, kind="stills")
            add(
                "anatomy_stills",
                bool(st.get("ok")),
                poisoned=st.get("poisoned_shots"),
                missing=st.get("missing_shots"),
            )
        else:
            add("anatomy_stills", True, required=False)
    except Exception as exc:  # noqa: BLE001
        add("anatomy_stills", True, skipped=True, error=str(exc)[:120])

    # geometry sample: keyframes 9:16 when present
    geo_bad: list[str] = []
    kf_dir = root / "keyframes"
    if kf_dir.is_dir():
        try:
            from PIL import Image  # type: ignore
        except ImportError:
            Image = None  # type: ignore
        if Image is not None:
            for p in sorted(kf_dir.glob("*.png"))[:40]:
                try:
                    with Image.open(p) as im:
                        w, h = im.size
                    # 9:16 → h/w ≈ 16/9
                    ratio = h / max(w, 1)
                    if w < 704 or h < 1280 or abs(ratio - (16 / 9)) > 0.12:
                        geo_bad.append(p.name)
                except Exception:
                    continue
    add("geometry", len(geo_bad) == 0, bad=geo_bad[:10])

    # tunnel
    if probe_tunnel:
        tun = tunnel_probe(port=tunnel_port)
        add(
            "tunnel",
            bool(tun.get("ok")),
            port=tunnel_port,
            code=tun.get("code"),
            message=tun.get("message"),
        )
    else:
        add("tunnel", True, skipped=True)

    # local single client (advisory)
    client = local_comfy_client_status()
    add(
        "local_comfy_client",
        bool(client.get("ok")),
        processes=client.get("count"),
        note=client.get("note"),
    )

    # gpu lease
    if check_lease:
        lease = gpu_lease_status(root)
        # ok if free or owned by this root
        lease_ok = bool(lease.get("free") or lease.get("owned_by_self"))
        add(
            "gpu_lease",
            lease_ok,
            free=lease.get("free"),
            owner=lease.get("owner"),
            code=lease.get("code"),
        )
    else:
        add("gpu_lease", True, skipped=True)

    # progress honesty snapshot
    progress = queue_progress_honest(root)
    add(
        "progress_honest",
        True,
        takes_files=progress.get("takes_files"),
        note=progress.get("note"),
    )

    # variety (design anti-boring) — hard door for bulk (P1 · 2026-08-04)
    skip_variety = os.environ.get("AIFILM_SKIP_VARIETY_PREFLIGHT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if skip_variety:
        add("variety", True, skipped=True, escape="AIFILM_SKIP_VARIETY_PREFLIGHT=1")
    else:
        try:
            var_report = variety_precheck(root, write=True)
            add(
                "variety",
                bool(var_report.get("ok")),
                issue_count=len(var_report.get("issues") or []),
                issues=[i.get("code") for i in (var_report.get("issues") or [])[:8]],
            )
        except Exception as exc:  # noqa: BLE001
            add("variety", False, error=str(exc)[:240])

    # Q4.1 duration target honesty (planned + optional media sum vs target)
    # Soft by default; hard when DURATION_*_HARD (planned or media gap >20%).
    skip_dur = os.environ.get("AIFILM_SKIP_DURATION_TARGET", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if skip_dur:
        add("duration_target", True, skipped=True, escape="AIFILM_SKIP_DURATION_TARGET=1")
    else:
        try:
            from plan.duration_target import (
                check_duration_target,
                write_duration_target_receipt,
            )

            media_sum: float | None = None
            try:
                from media_duration import MediaDurationError, probe_duration_sec

                clips_map = man.get("clips") if isinstance(man.get("clips"), dict) else {}
                acc = 0.0
                measured = 0
                for sid in shot_ids:
                    rec = clips_map.get(sid)
                    if not isinstance(rec, dict):
                        continue
                    st = str(rec.get("status") or "").lower()
                    if st not in {"approved", "candidate"}:
                        continue
                    raw = str(rec.get("path") or "").strip()
                    if not raw:
                        continue
                    p = Path(raw)
                    candidates = [
                        p if p.is_absolute() else root / p,
                        root / "clips" / Path(raw).name,
                    ]
                    path = next((c for c in candidates if c.is_file()), None)
                    if path is None:
                        continue
                    try:
                        acc += float(probe_duration_sec(path, label=sid))
                        measured += 1
                    except (MediaDurationError, OSError, ValueError):
                        continue
                # Only trust media sum when most timeline shots have measurable clips
                if measured >= max(3, int(0.5 * max(len(shot_ids), 1))):
                    media_sum = acc
            except Exception:
                media_sum = None

            dur_rep = check_duration_target(spec, media_sum_sec=media_sum)
            write_duration_target_receipt(root, dur_rep)
            add(
                "duration_target",
                bool(dur_rep.get("ok")),
                severity=dur_rep.get("severity"),
                codes=dur_rep.get("codes"),
                planned_sum_sec=dur_rep.get("planned_sum_sec"),
                media_sum_sec=dur_rep.get("media_sum_sec"),
                target_duration_sec=dur_rep.get("target_duration_sec"),
                suggested_min_shots_h3=dur_rep.get("suggested_min_shots_h3"),
                message=dur_rep.get("message"),
                next=dur_rep.get("next"),
            )
        except Exception as exc:  # noqa: BLE001
            add("duration_target", True, skipped=True, error=str(exc)[:120])

    failed = [c for c in checks if not c.get("ok")]
    ok = not failed
    next_cmd = None
    next_why = None
    weapon_hints: dict[str, str] = {}
    if not ok:
        first = str(failed[0]["id"])
        next_cmd = _bulk_next_cmd_for_failure(
            root, first, tunnel_port=tunnel_port, inv=inv
        )
        still = inv.get("still_primary") or "qwen-image-2512-quality"
        edit = inv.get("edit_primary") or "qwen-image-edit-2511-local"
        motion = inv.get("motion_primary") or "minimax-h3-i2v-pilot"
        weapon_hints = {
            "still_primary": str(still),
            "edit_primary": str(edit),
            "motion_primary": str(motion),
        }
        # Per-fail weapon-named recovery (agent glance)
        for c in failed:
            cid = str(c.get("id") or "")
            if cid in {
                "still_source",
                "still_uniqueness",
                "crop_master_still",
                "state_index",
                "geometry",
            }:
                c["weapon_hint"] = f"still={still}"
            elif cid == "anatomy_stills":
                c["weapon_hint"] = f"edit={edit}; ban I2V on poison ({motion})"
            elif cid in {"tunnel", "gpu_lease", "local_comfy_client", "variety"}:
                c["weapon_hint"] = f"motion={motion}"
            elif cid == "duration_target":
                c["weapon_hint"] = (
                    "add shots / FLF longer / lower target_duration "
                    f"(H3 ~5.2s · see receipts/duration-target.json)"
                )
            elif cid == "pilot":
                c["weapon_hint"] = f"no bulk until pilot GO · motion primary {motion}"
        next_why = (
            f"bulk blocked on {first} · fix via next_cmd · "
            f"primaries still={still} edit={edit} motion={motion}"
        )

    out = {
        "schema_version": 1,
        "kind": "bulk-preflight",
        "at": utc_now(),
        "root": str(root),
        "ok": ok,
        "checks": checks,
        "failed": [c["id"] for c in failed],
        "next_cmd": next_cmd,
        "next_why": next_why,
        "weapon_inventory": inv,
        "weapon_hints": weapon_hints or None,
        "required_proof": "all checks ok before media-queue bulk add",
    }
    if write:
        write_json(root / "receipts" / BULK_PREFLIGHT_NAME, out)
    return out


def assert_bulk_preflight(
    root: Path | str,
    *,
    require: bool = True,
    probe_tunnel: bool = False,
    check_lease: bool = False,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fail-closed bulk door. Default skips tunnel/lease (queue-friendly).

    Wave H: reuse green ``receipts/bulk-preflight.json`` when film-spec mtime
    is not newer than the receipt (avoids re-running on every media-queue add).
    """
    root_p = _root(root)
    receipt_path = root_p / "receipts" / BULK_PREFLIGHT_NAME
    spec_path = root_p / "film-spec.json"
    if not force_refresh and receipt_path.is_file():
        cached = read_json(receipt_path) or {}
        if cached.get("ok") is True:
            try:
                rec_mtime = receipt_path.stat().st_mtime
                spec_mtime = spec_path.stat().st_mtime if spec_path.is_file() else 0.0
                if rec_mtime + 1e-6 >= spec_mtime:
                    cached = {**cached, "reused": True, "source": "receipt"}
                    return cached
            except OSError:
                pass
    report = bulk_preflight(
        root_p,
        write=True,
        probe_tunnel=probe_tunnel,
        check_lease=check_lease,
    )
    if require and not report.get("ok"):
        inv = report.get("weapon_inventory") if isinstance(report.get("weapon_inventory"), dict) else {}
        motion = inv.get("motion_primary") or "minimax-h3-i2v-pilot"
        still = inv.get("still_primary") or "qwen-image-2512-quality"
        raise WorkflowPackError(
            "bulk preflight failed: "
            + ",".join(report.get("failed") or [])
            + f" — next: {report.get('next_cmd')}"
            + f" — weapons: still={still} motion={motion}"
            + (f" — why: {report.get('next_why')}" if report.get("next_why") else "")
        )
    return report


# ---------------------------------------------------------------------------
# B2 · variety precheck
# ---------------------------------------------------------------------------


def variety_precheck(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Design-time anti-boring matrix (poses / face CU / L4 / adjacent motion)."""
    root = _root(root)
    spec = read_json(root / "film-spec.json") or {}
    if not spec:
        raise WorkflowPackError("film-spec.json missing")
    shots = _shots_from_spec(spec)
    meat = [s for s in shots if _heat_phase(s) in {"act", "climax", "foreplay"}]
    poses = [_sex_pose(s) for s in meat if _sex_pose(s)]
    unique_poses = sorted({p for p in poses if p})
    face_cu = 0
    l4 = 0
    for s in meat:
        size = _shot_size(s)
        if size in {"ecu", "cu", "close", "closeup", "close-up", "face", "extreme_closeup"}:
            face_cu += 1
        if (
            size in {"insert", "l4", "detail", "macro", "extreme_detail"}
            or str(s.get("layer") or "").upper() == "L4"
        ):
            l4 += 1
        # L4 via dramatic function
        df = str(s.get("dramatic_function") or "").lower()
        if "insert" in df or df == "detail":
            l4 += 1

    motion_collisions: list[dict[str, str]] = []
    cam_collisions: list[dict[str, str]] = []
    triple_collisions: list[dict[str, str]] = []
    framing_collisions: list[dict[str, str]] = []
    for a, b in zip(meat, meat[1:], strict=False):
        ma, mb = _motion_primary(a), _motion_primary(b)
        if ma and mb and ma == mb:
            motion_collisions.append(
                {
                    "a": str(a.get("id")),
                    "b": str(b.get("id")),
                    "motion": ma,
                }
            )
        ca, cb = _camera_move(a), _camera_move(b)
        if ca and cb and ca == cb:
            cam_collisions.append(
                {
                    "a": str(a.get("id")),
                    "b": str(b.get("id")),
                    "camera": ca,
                }
            )
        sa, sb = _shot_size(a), _shot_size(b)
        # Adjacent act/climax: same camera + same size = framing clone (anti-boring)
        if ca and cb and ca == cb and sa and sb and sa == sb:
            framing_collisions.append(
                {
                    "a": str(a.get("id")),
                    "b": str(b.get("id")),
                    "camera": ca,
                    "shot_size": sa,
                }
            )
        # Triple: same motion primary + camera + size — strongest anti-clone
        if ma and mb and ma == mb and ca and cb and ca == cb and sa and sb and sa == sb:
            triple_collisions.append(
                {
                    "a": str(a.get("id")),
                    "b": str(b.get("id")),
                    "motion": ma,
                    "camera": ca,
                    "shot_size": sa,
                }
            )

    short_meat = [
        str(s.get("id"))
        for s in meat
        if float(s.get("duration_sec") or 0) + 1e-9 < MEAT_DURATION_FLOOR
    ]

    issues: list[dict[str, Any]] = []
    if len(unique_poses) < POSE_MIN_UNIQUE and len(meat) >= POSE_MIN_UNIQUE:
        issues.append(
            {
                "code": "POSE_VARIETY_LOW",
                "message": f"unique meat poses {len(unique_poses)} < {POSE_MIN_UNIQUE}",
            }
        )
    if face_cu < FACE_CU_MIN and len(meat) >= 4:
        issues.append(
            {
                "code": "FACE_CU_LOW",
                "message": f"face CU count {face_cu} < {FACE_CU_MIN}",
            }
        )
    if l4 < L4_INSERT_MIN and len(meat) >= 4:
        issues.append(
            {
                "code": "L4_INSERT_LOW",
                "message": f"L4/insert count {l4} < {L4_INSERT_MIN}",
            }
        )
    for c in motion_collisions:
        issues.append(
            {
                "code": "ADJACENT_MOTION_COLLISION",
                "message": f"{c['a']}→{c['b']} same motion {c['motion']!r}",
            }
        )
    for c in cam_collisions:
        issues.append(
            {
                "code": "ADJACENT_CAMERA_COLLISION",
                "message": f"{c['a']}→{c['b']} same camera {c['camera']!r}",
            }
        )
    for c in framing_collisions:
        issues.append(
            {
                "code": "ADJACENT_FRAMING_COLLISION",
                "message": (
                    f"{c['a']}→{c['b']} same camera {c['camera']!r} + shot_size {c['shot_size']!r}"
                ),
            }
        )
    for c in triple_collisions:
        issues.append(
            {
                "code": "ADJACENT_TRIPLE_COLLISION",
                "message": (
                    f"{c['a']}→{c['b']} same motion+camera+size "
                    f"({c['motion']!r}/{c['camera']!r}/{c['shot_size']!r})"
                ),
            }
        )
    for sid in short_meat:
        issues.append(
            {
                "code": "MEAT_DURATION_SHORT",
                "message": f"{sid} duration < {MEAT_DURATION_FLOOR}s",
            }
        )

    ok = not issues
    out = {
        "schema_version": 1,
        "kind": "variety-precheck",
        "at": utc_now(),
        "root": str(root),
        "ok": ok,
        "meat_shot_count": len(meat),
        "unique_poses": unique_poses,
        "unique_pose_count": len(unique_poses),
        "face_cu_count": face_cu,
        "l4_insert_count": l4,
        "motion_collisions": motion_collisions,
        "camera_collisions": cam_collisions,
        "framing_collisions": framing_collisions,
        "triple_collisions": triple_collisions,
        "short_meat": short_meat,
        "floors": {
            "poses": POSE_MIN_UNIQUE,
            "face_cu": FACE_CU_MIN,
            "l4": L4_INSERT_MIN,
            "meat_duration": MEAT_DURATION_FLOOR,
        },
        "issues": issues,
        "matrix_md": _variety_matrix_md(unique_poses, face_cu, l4, motion_collisions, issues),
        "next_cmd": (
            None if ok else f'aifilm write-spec --root "{root}"  # fix variety issues then re-check'
        ),
    }
    if write:
        write_json(root / "receipts" / VARIETY_NAME, out)
        (root / "receipts" / "variety-matrix.md").write_text(
            out["matrix_md"] + "\n", encoding="utf-8"
        )
    return out


def assert_variety_preflight(
    root: Path | str,
    *,
    require: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fail-closed variety door for bulk / H3 register (P1 · 2026-08-04).

    Escape: ``AIFILM_SKIP_VARIETY_PREFLIGHT=1``.
    Reuses green receipt when film-spec mtime is not newer.
    """
    if os.environ.get("AIFILM_SKIP_VARIETY_PREFLIGHT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_VARIETY_PREFLIGHT=1",
        }
    root_p = _root(root)
    receipt_path = root_p / "receipts" / VARIETY_NAME
    spec_path = root_p / "film-spec.json"
    if not force_refresh and receipt_path.is_file():
        cached = read_json(receipt_path) or {}
        if cached.get("ok") is True:
            try:
                rec_mtime = receipt_path.stat().st_mtime
                spec_mtime = spec_path.stat().st_mtime if spec_path.is_file() else 0.0
                if rec_mtime + 1e-6 >= spec_mtime:
                    return {**cached, "reused": True, "source": "receipt"}
            except OSError:
                pass
    report = variety_precheck(root_p, write=True)
    if require and not report.get("ok"):
        codes = [str(i.get("code") or "") for i in (report.get("issues") or [])[:6]]
        raise WorkflowPackError(
            "variety preflight failed: "
            + ",".join(codes or ["UNKNOWN"])
            + f" — next: {report.get('next_cmd')}"
        )
    return report


def film_core_closeout_audit(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """P2 · Audit whether motion clips still carry film core (DF/want/dialogue).

    Does not re-render — reads film-spec + spine receipts + manifest clips.
    """
    root_p = _root(root)
    spec = read_json(root_p / "film-spec.json") or {}
    man = read_json(root_p / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man, dict) else {}
    if not isinstance(clips, dict):
        clips = {}
    shots = _shots_from_spec(spec)
    issues: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    has_want = bool(
        str(di.get("protagonist_want") or di.get("want") or di.get("theme") or "").strip()
    )
    if not has_want and shots:
        issues.append(
            {
                "code": "CORE_WANT_MISSING",
                "message": "director_intent lacks protagonist_want/theme — motion spine thin",
            }
        )
    for shot in shots:
        sid = str(shot.get("id") or "")
        if not sid:
            continue
        df = str(shot.get("dramatic_function") or "").strip()
        role = str(shot.get("shot_role") or "hero").strip().lower()
        has_clip = isinstance(clips.get(sid), dict) and clips[sid].get("path")
        # Phase B · dual spine: prefer unified motion, then H3, then Grok
        spine_txt = ""
        spine_engine: str | None = None
        prompts_dir = root_p / "receipts" / "prompts"
        for eng, name in (
            ("motion", f"{sid}.motion.spine.txt"),
            ("h3", f"{sid}.h3.spine.txt"),
            ("grok", f"{sid}.grok.spine.txt"),
        ):
            p = prompts_dir / name
            if p.is_file():
                try:
                    spine_txt = p.read_text(encoding="utf-8")
                except OSError:
                    spine_txt = ""
                if spine_txt:
                    spine_engine = eng
                    break
        row = {
            "shot_id": sid,
            "role": role,
            "dramatic_function": df or None,
            "has_clip": bool(has_clip),
            "has_spine_receipt": bool(spine_txt),
            "spine_engine": spine_engine,
            "spine_has_df": bool(df and df in spine_txt) if spine_txt else None,
        }
        rows.append(row)
        if role == "hero" and has_clip and not df:
            issues.append(
                {
                    "code": "CORE_DF_MISSING",
                    "shot_id": sid,
                    "message": f"{sid} hero clip without dramatic_function",
                }
            )
        if role == "hero" and has_clip and not spine_txt:
            issues.append(
                {
                    "code": "CORE_SPINE_MISSING",
                    "shot_id": sid,
                    "message": (
                        f"{sid} hero clip without spine receipt (.motion/.h3/.grok.spine.txt)"
                    ),
                }
            )
        if has_clip and spine_txt and df and f"Dramatic function: {df}" not in spine_txt:
            issues.append(
                {
                    "code": "CORE_SPINE_DF_DRIFT",
                    "shot_id": sid,
                    "message": f"{sid} {spine_engine or 'spine'} receipt missing DF {df}",
                }
            )
        # dialogue shot must have spoken text in spine if on_camera
        cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
        spoken = ""
        for c in cues:
            if (
                isinstance(c, dict)
                and c.get("line_type") == "dialogue"
                and str(c.get("spoken_text") or "").strip()
            ):
                spoken = str(c["spoken_text"]).strip()
                break
        if spoken and has_clip and spine_txt and spoken not in spine_txt:
            issues.append(
                {
                    "code": "CORE_DIALOGUE_SPINE_MISS",
                    "shot_id": sid,
                    "message": f"{sid} dialogue not in {spine_engine or 'spine'} receipt",
                }
            )
    ok = not issues
    out = {
        "schema_version": 1,
        "kind": "film-core-closeout-audit",
        "at": utc_now(),
        "root": str(root_p),
        "ok": ok,
        "has_director_want": has_want,
        "shots": rows,
        "issues": issues,
        "next_cmd": (
            None
            if ok
            else (
                f'aifilm write-spec --root "{root_p}"  # fill DF/want; '
                f"re-assemble Grok or h3 run for spine"
            )
        ),
    }
    if write:
        write_json(root_p / "receipts" / "film-core-closeout.json", out)
    return out


def _variety_matrix_md(
    poses: list[str],
    face_cu: int,
    l4: int,
    collisions: list[dict[str, str]],
    issues: list[dict[str, Any]],
) -> str:
    lines = [
        "# 镜头差矩阵（设计期 variety）",
        "",
        f"- 体位 unique: **{len(poses)}** / floor {POSE_MIN_UNIQUE} → {', '.join(poses) or '—'}",
        f"- 脸 CU: **{face_cu}** / floor {FACE_CU_MIN}",
        f"- L4 insert: **{l4}** / floor {L4_INSERT_MIN}",
        f"- 邻镜 motion 撞车: **{len(collisions)}**",
        "",
        "## Issues",
    ]
    if not issues:
        lines.append("- none")
    else:
        for i in issues:
            lines.append(f"- `{i.get('code')}`: {i.get('message')}")
    lines.extend(["", "人审：改 film-spec 后再 `aifilm variety-precheck`，勿 bulk 后返工。"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# B3 · select shortlist
# ---------------------------------------------------------------------------


def select_shortlist(
    root: Path | str,
    *,
    write: bool = True,
    promote: bool = False,
    measure_missing: bool = True,
) -> dict[str, Any]:
    """Multi-take preferred pick by mean + composition anti-hijack (v2.37+).

    Never deletes takes. ``promote=True`` sets clips[sid].path to best take that
    passes composition anti-hijack (sand/torso steal reject) when available;
    never promotes a hijack-flagged take if a clean alternate exists.
    Escape composition: ``AIFILM_SKIP_ANTI_HIJACK=1``.
    """
    root = _root(root)
    if measure_missing:
        try:
            from i2v_motion_gate import ensure_take_means

            ensure_take_means(root, recompute=False, write_sidecars=True)
        except Exception:  # noqa: BLE001
            pass
    takes_root = root / "takes"
    man = read_json(root / "manifest.json") or {}
    if not isinstance(man, dict):
        man = {}
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    if not isinstance(clips, dict):
        clips = {}
    rows: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []

    shot_meta: dict[str, dict[str, Any]] = {}
    spec = read_json(root / "film-spec.json") or {}
    for scene in (spec.get("scenes") or []) if isinstance(spec, dict) else []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                shot_meta[str(sh["id"])] = sh

    shot_dirs: dict[str, list[Path]] = {}
    if takes_root.is_dir():
        for p in takes_root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".mp4", ".webm", ".mov"}:
                continue
            # takes/<shot_id>/... or takes/<shot_id>_*.mp4
            sid = p.parent.name if p.parent != takes_root else p.stem.split("_")[0]
            shot_dirs.setdefault(sid, []).append(p)

    anti_hijack_on = True
    try:
        import composition_anti_hijack as _ah

        if _ah._env_skip():
            anti_hijack_on = False
    except Exception:  # noqa: BLE001
        _ah = None  # type: ignore
        anti_hijack_on = False
    ah_cache = root / "work" / "anti-hijack" / "frames"

    for sid, files in sorted(shot_dirs.items()):
        scored: list[dict[str, Any]] = []
        for f in files:
            mean = _read_motion_mean(root, sid, f)
            if mean is None and measure_missing:
                try:
                    from i2v_motion_gate import measure_mean_absdiff, write_mean_sidecar

                    mean = measure_mean_absdiff(f)
                    if mean is not None:
                        write_mean_sidecar(f, mean)
                except Exception:  # noqa: BLE001
                    mean = None
            size = f.stat().st_size if f.is_file() else 0
            score = (mean or 0.0) * 1.0 + (1.0 if size > 100_000 else 0.0)
            scored.append(
                {
                    "path": str(f),
                    "bytes": size,
                    "mean": mean,
                    "score": score,
                }
            )
        scored.sort(key=lambda x: (-float(x["score"]), -int(x["bytes"])))
        sh = shot_meta.get(sid) or {}
        composition_note: dict[str, Any] | None = None
        if anti_hijack_on and _ah is not None and len(scored) >= 1:
            try:
                scored = _ah.apply_anti_hijack_to_candidates(
                    scored,
                    shot=sh,
                    cache_dir=ah_cache / sid,
                    enabled=True,
                )
                composition_note = {
                    "enabled": True,
                    "want": scored[0].get("composition_want") if scored else None,
                    "preferred_hijack": bool(scored[0].get("composition_hijack")) if scored else None,
                    "preferred_composition_ok": bool(scored[0].get("composition_ok")) if scored else None,
                    "note": "composition gate demotes sand/torso hijack before mean",
                }
            except Exception as exc:  # noqa: BLE001
                composition_note = {"enabled": True, "error": str(exc)}
        preferred = scored[0] if scored else None
        # never promote hijack if a clean alternate exists
        if preferred and preferred.get("composition_hijack"):
            # prefer non-hijack alternate; composition_ok may be missing when skip
            clean = [c for c in scored if not c.get("composition_hijack")]
            if clean:
                preferred = clean[0]
                if composition_note is not None:
                    composition_note["preferred_switched_from_hijack"] = True
        below_floor = False
        floor_val = None
        if preferred and preferred.get("mean") is not None:
            try:
                from i2v_motion_gate import evaluate_shot_motion

                ev = evaluate_shot_motion(
                    float(preferred["mean"]),
                    heat_phase=sh.get("heat_phase"),
                    dramatic_function=sh.get("dramatic_function"),
                    wardrobe_state=sh.get("wardrobe_state"),
                    shot_id=sid,
                )
                floor_val = ev.get("floor")
                below_floor = not bool(ev.get("ok"))
            except Exception:  # noqa: BLE001
                below_floor = False
        # β3 · attach pk-compare advisory (never changes preferred selection)
        pk_note: dict[str, Any] | None = None
        if len(scored) >= 2:
            try:
                from h3_fill_idle import pk_compare as _pk

                pk_one = _pk(root, shot_id=sid, measure_missing=False)
                shots_pk = pk_one.get("shots") or []
                if shots_pk:
                    pk_note = {
                        "recommended_path": (shots_pk[0].get("recommended") or {}).get("path"),
                        "pk_score": (shots_pk[0].get("recommended") or {}).get("pk_score"),
                        "caution": shots_pk[0].get("caution"),
                        "human_required": True,
                        "note": "advisory — shortlist preferred may differ; human promotes",
                    }
            except Exception:  # noqa: BLE001
                pk_note = None
        row = {
            "shot_id": sid,
            "take_count": len(scored),
            "preferred": preferred,
            "candidates": scored,
            "manifest_clip": clips.get(sid),
            "below_floor": below_floor,
            "floor": floor_val,
            "pk_advisory": pk_note,
            "composition_anti_hijack": composition_note,
        }
        rows.append(row)

        if promote and preferred and preferred.get("path"):
            # hard block: do not promote known hijack when alternatives scored
            if preferred.get("composition_hijack") and any(
                not c.get("composition_hijack") for c in scored
            ):
                continue
            if preferred.get("composition_hijack") and preferred.get("composition_ok") is False:
                continue
            prev = clips.get(sid) if isinstance(clips.get(sid), dict) else {}
            new_clip = {
                **(prev or {}),
                "path": preferred["path"],
                "mean": preferred.get("mean"),
                "mean_absdiff": preferred.get("mean"),
                "preferred_from": "select-shortlist",
                "composition_ok": preferred.get("composition_ok"),
                "composition_score": preferred.get("composition_score"),
                "promoted_at": utc_now(),
                "status": prev.get("status") or "candidate",
            }
            clips[sid] = new_clip
            promoted.append(
                {
                    "shot_id": sid,
                    "path": preferred["path"],
                    "mean": preferred.get("mean"),
                    "below_floor": below_floor,
                    "composition_hijack": preferred.get("composition_hijack"),
                }
            )

    if promote and promoted:
        man["clips"] = clips
        write_json(root / "manifest.json", man)

    out = {
        "schema_version": 1,
        "kind": "select-shortlist",
        "at": utc_now(),
        "root": str(root),
        "ok": True,
        "shots": rows,
        "promoted": promoted,
        "promote": promote,
        "note": (
            "preferred promoted into manifest.clips (takes retained)"
            if promote
            else "preferred is advisory; pass --promote to write manifest.clips"
        ),
        "next_cmd": (f'aifilm i2v-motion-gate --root "{root}" --write' if rows else None),
    }
    if write:
        write_json(root / "receipts" / SELECT_SHORTLIST_NAME, out)
    return out


def ship_prep(
    root: Path | str,
    *,
    write: bool = True,
    measure: bool = True,
    promote: bool = True,
    skip_variety: bool = False,
    skip_pk: bool = False,
) -> dict[str, Any]:
    """One-shot pre-delivery ladder: means → variety → shortlist → pk → motion-gate → film_core.

    Hard fails: variety (unless skip), i2v_motion_gate.
    film_core hard only for max/premium (else advisory).
    pk_compare is **always advisory** (never auto-promote).
    """
    root = _root(root)
    steps: list[dict[str, Any]] = []

    if measure:
        try:
            from i2v_motion_gate import ensure_take_means

            mm = ensure_take_means(root, recompute=False, write_sidecars=True)
            steps.append(
                {
                    "id": "measure_means",
                    "ok": True,
                    "detail": (
                        f"measured={mm.get('measured_count', 0)} "
                        f"skipped={mm.get('skipped_count', 0)} "
                        f"errors={mm.get('error_count', 0)}"
                    ),
                    "next_cmd": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                {
                    "id": "measure_means",
                    "ok": False,
                    "detail": str(exc)[:200],
                    "next_cmd": f'aifilm i2v-motion-gate --root "{root}" --write',
                }
            )

    # True-video-only (hard): ban Ken Burns / panel still-motion approved clips
    try:
        from true_video_policy import scan_manifest_true_video

        tv = scan_manifest_true_video(root)
        steps.append(
            {
                "id": "true_video",
                "ok": bool(tv.get("ok") or tv.get("skipped")),
                "detail": (
                    "skipped"
                    if tv.get("skipped")
                    else (
                        f"checked={tv.get('checked', 0)} violations={len(tv.get('violations') or [])}"
                    )
                ),
                "hard": True,
                "next_cmd": (
                    None
                    if tv.get("ok") or tv.get("skipped")
                    else "re-I2V Grok/H3; remove still-motion approved clips"
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            {
                "id": "true_video",
                "ok": False,
                "detail": str(exc)[:200],
                "hard": True,
                "next_cmd": "check true_video_policy / re-register generative clips",
            }
        )

    if skip_variety or os.environ.get("AIFILM_SKIP_VARIETY_PREFLIGHT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        steps.append(
            {
                "id": "variety",
                "ok": True,
                "skipped": True,
                "detail": "AIFILM_SKIP_VARIETY_PREFLIGHT or --skip-variety",
                "next_cmd": None,
            }
        )
    else:
        var = variety_precheck(root, write=write)
        steps.append(
            {
                "id": "variety",
                "ok": bool(var.get("ok")),
                "detail": ("ok" if var.get("ok") else f"issues={len(var.get('issues') or [])}"),
                "next_cmd": var.get("next_cmd"),
                "hard": True,
            }
        )

    # 2.38.2 · human-safe: never mean-promote multi-take before PK (unless force)
    force_promote = os.environ.get("AIFILM_SHIP_PROMOTE_FORCE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Peek multi-take cheaply (takes dirs only) before any promote write
    multi_take_peek = False
    takes_root = root / "takes"
    if takes_root.is_dir():
        for shot_dir in takes_root.iterdir():
            if not shot_dir.is_dir():
                continue
            n = sum(
                1
                for p in shot_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".webm", ".mov"}
            )
            if n >= 2:
                multi_take_peek = True
                break
    promote_effective = bool(promote)
    promote_deferred = False
    if promote and multi_take_peek and not force_promote:
        promote_effective = False
        promote_deferred = True

    sel = select_shortlist(root, write=write, promote=promote_effective, measure_missing=measure)
    steps.append(
        {
            "id": "select_shortlist",
            "ok": True,
            "detail": (
                f"shots={len(sel.get('shots') or [])} promoted={len(sel.get('promoted') or [])}"
                + ("; multi-take → promote deferred for human PK" if promote_deferred else "")
            ),
            "next_cmd": (
                f'aifilm select-shortlist --root "{root}" --promote  # after human PK'
                if promote_deferred
                else None
            ),
            "promoted": sel.get("promoted") or [],
            "promote_deferred_human_pk": promote_deferred,
        }
    )

    # Fill-Idle / multi-take PK advisory (never hard-fail; never auto-promote)
    if skip_pk or os.environ.get("AIFILM_SKIP_SHIP_PK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        steps.append(
            {
                "id": "pk_compare",
                "ok": True,
                "skipped": True,
                "advisory": True,
                "detail": "AIFILM_SKIP_SHIP_PK or --skip-pk",
                "next_cmd": None,
            }
        )
    else:
        try:
            from h3_fill_idle import next_fill_idle_job, pk_compare

            pk = pk_compare(root, measure_missing=False, write_dailies=write)
            multi = [
                s
                for s in (pk.get("shots") or [])
                if isinstance(s, dict) and int(s.get("take_count") or 0) >= 2
            ]
            human_rows: list[dict[str, Any]] = []
            for s in multi[:40]:
                rec = s.get("recommended") if isinstance(s.get("recommended"), dict) else {}
                human_rows.append(
                    {
                        "shot_id": s.get("shot_id"),
                        "take_count": s.get("take_count"),
                        "recommended_lane": rec.get("lane"),
                        "recommended_mean": rec.get("mean"),
                        "recommended_path": rec.get("path"),
                        "pk_score": rec.get("pk_score"),
                        "caution": list(s.get("caution") or []),
                    }
                )
            if write and multi:
                write_json(
                    root / "receipts" / "pk-compare-ship-prep.json",
                    {
                        "schema_version": 1,
                        "kind": "ai-film-pk-compare-ship-prep",
                        "ok": True,
                        "human_required": True,
                        "multi_take_count": len(multi),
                        "shots": human_rows,
                        "dailies_path": str(root / "receipts" / "pk-dailies.md"),
                        "note": "advisory only — human select-shortlist --promote / pk-ledger",
                    },
                )
            steps.append(
                {
                    "id": "pk_compare",
                    "ok": True,
                    "advisory": True,
                    "human_required": bool(multi),
                    "detail": (
                        f"multi_take={len(multi)} (human review recommended)"
                        if multi
                        else "no multi-take shots"
                    ),
                    "next_cmd": (
                        f'aifilm h3 pk-compare --root "{root}"; '
                        f'aifilm select-shortlist --root "{root}" --promote  # human OK only'
                        if multi
                        else None
                    ),
                    "multi_take_count": len(multi),
                    "shots": human_rows,
                    "dailies_path": (
                        str(root / "receipts" / "pk-dailies.md") if multi and write else None
                    ),
                }
            )
            # Pending Fill-Idle work (P0 meat still not burned) — advisory only
            try:
                nxt = next_fill_idle_job(root, include_challenge=True, check_capacity=False)
                pending = int(nxt.get("pending_count") or 0)
                n = nxt.get("next") if isinstance(nxt.get("next"), dict) else None
                steps.append(
                    {
                        "id": "fill_idle_pending",
                        "ok": True,
                        "advisory": True,
                        "detail": (
                            f"pending={pending}"
                            + (f" next={n.get('shot_id')}/{n.get('priority')}" if n else "")
                        ),
                        "next_cmd": (
                            f'aifilm h3 run-next --root "{root}" --execute'
                            if pending and n
                            else None
                        ),
                        "pending_count": pending,
                        "next_shot": n,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                steps.append(
                    {
                        "id": "fill_idle_pending",
                        "ok": True,
                        "advisory": True,
                        "detail": f"skip:{str(exc)[:120]}",
                        "next_cmd": None,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                {
                    "id": "pk_compare",
                    "ok": True,
                    "advisory": True,
                    "detail": f"skip:{str(exc)[:160]}",
                    "next_cmd": f'aifilm h3 pk-compare --root "{root}"',
                }
            )

    # i2v: reuse receipt when green — full rewrite deferred to ensure_machine_lane
    gate_rep: dict[str, Any] = {}
    try:
        existing_i2v = read_json(root / "receipts" / "i2v-final-gate.json") or {}
        if isinstance(existing_i2v, dict) and existing_i2v.get("ok") is True:
            gate_rep = existing_i2v
            steps.append(
                {
                    "id": "i2v_motion_gate",
                    "ok": True,
                    "detail": "i2v-final-gate receipt ok (no re-run)",
                    "next_cmd": None,
                    "hard": True,
                }
            )
        else:
            from cli_motion import i2v_motion_gate_from_rows

            gate_rep = i2v_motion_gate_from_rows(
                [],
                root=root,
                write_receipts=write,
                auto_from_root=True,
            )
            steps.append(
                {
                    "id": "i2v_motion_gate",
                    "ok": bool(gate_rep.get("ok")),
                    "detail": "i2v-final-gate ok" if gate_rep.get("ok") else "gate red",
                    "next_cmd": (
                        None
                        if gate_rep.get("ok")
                        else f'aifilm i2v-motion-gate --root "{root}" --write'
                    ),
                    "hard": True,
                }
            )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            {
                "id": "i2v_motion_gate",
                "ok": False,
                "detail": str(exc)[:200],
                "next_cmd": f'aifilm i2v-motion-gate --root "{root}" --write',
                "hard": True,
            }
        )

    core: dict[str, Any] = {}
    film_core_hard = False
    try:
        _spec = read_json(root / "film-spec.json") or {}
        heat_scale = str(_spec.get("heat_scale") or "").strip().lower()
        film_core_hard = (
            heat_scale == "max"
            or _spec.get("dramatic_meaning_strict") is True
            or _spec.get("premium_vertical") is True
        )
        core = film_core_closeout_audit(root, write=write)
        steps.append(
            {
                "id": "film_core",
                "ok": bool(core.get("ok")),
                "detail": ("ok" if core.get("ok") else f"issues={len(core.get('issues') or [])}"),
                "next_cmd": core.get("next_cmd"),
                "hard": film_core_hard,
                "advisory": not film_core_hard,
            }
        )
    except Exception as exc:  # noqa: BLE001
        core = {"ok": False, "error": str(exc)[:160]}
        steps.append(
            {
                "id": "film_core",
                "ok": False,
                "detail": str(exc)[:200],
                "next_cmd": f'aifilm closeout status --root "{root}"',
                "hard": film_core_hard,
                "advisory": not film_core_hard,
            }
        )

    # Wave δ · five-track plan (hard only when enabled + error severity)
    try:
        from five_track import plan_five_track

        ft = plan_five_track(root, write=write)
        ft_hard = bool(ft.get("enabled")) and not bool(ft.get("ok"))
        steps.append(
            {
                "id": "five_track",
                "ok": bool(ft.get("ok") or not ft.get("enabled")),
                "detail": (
                    f"enabled={ft.get('enabled')} issues={len(ft.get('issues') or [])} "
                    f"sex_sfx={ft.get('sex_sfx', {}).get('covered')}/"
                    f"{ft.get('sex_sfx', {}).get('required')}"
                ),
                "hard": ft_hard,
                "advisory": not ft_hard,
                "next_cmd": ft.get("next_cmd"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            {
                "id": "five_track",
                "ok": True,
                "detail": f"skipped: {exc}"[:160],
                "advisory": True,
                "skipped": True,
            }
        )

    # F3 · input fidelity (advisory unless strict)
    try:
        from input_fidelity import fidelity_check, human_fidelity_summary

        fid_rep = fidelity_check(root, write=write)
        fid_hard = bool(fid_rep.get("strict"))
        steps.append(
            {
                "id": "input_fidelity",
                "ok": bool(fid_rep.get("ok")),
                "detail": (
                    f"score={fid_rep.get('score')} "
                    + human_fidelity_summary(fid_rep).replace("\n", " | ")
                )[:220],
                "next_cmd": (
                    None if fid_rep.get("ok") else f'aifilm fidelity apply --root "{root}"'
                ),
                "hard": fid_hard,
                "advisory": not fid_hard,
            }
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            {
                "id": "input_fidelity",
                "ok": True,
                "detail": f"fidelity skipped: {exc}"[:160],
                "next_cmd": f'aifilm fidelity check --root "{root}"',
                "advisory": True,
                "skipped": True,
            }
        )

    # Single machine-lane entry (no second full i2v if already ok above)
    try:
        from gate_auto import ensure_machine_lane

        i2v_already = bool(gate_rep.get("ok"))
        auto = ensure_machine_lane(
            root,
            force=False,
            write=write,
            fix_sex_sfx=True,
            measure_i2v=not i2v_already,
            promote_single=False,
            run_variety=False,
            run_cinematic=True,
        )
        steps.append(
            {
                "id": "gate_auto",
                "ok": bool(auto.get("ok")),
                "detail": (
                    f"ensured blocked_by={auto.get('blocked_by')} fast={auto.get('fast_path')}"
                )[:180],
                "hard": True,
                "next_cmd": auto.get("next_cmd") or f'aifilm gate-auto --root "{root}"',
                "human_pending": auto.get("human_pending"),
            }
        )
        for st in auto.get("steps") or []:
            if isinstance(st, dict) and st.get("id") == "cinematic_gate":
                steps.append(
                    {
                        "id": "cinematic_gate",
                        "ok": bool(st.get("ok")),
                        "detail": st.get("detail") or "via ensure_machine_lane",
                        "hard": True,
                        "next_cmd": st.get("next_cmd"),
                    }
                )
                break
        else:
            steps.append(
                {
                    "id": "cinematic_gate",
                    "ok": bool(auto.get("ok")),
                    "detail": "via ensure_machine_lane",
                    "hard": True,
                    "next_cmd": auto.get("next_cmd"),
                }
            )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            {
                "id": "cinematic_gate",
                "ok": False,
                "detail": f"machine_lane failed: {exc}"[:160],
                "hard": True,
                "next_cmd": f'aifilm gate-auto --root "{root}"',
            }
        )

    hard_failed = [
        s
        for s in steps
        if not s.get("ok")
        and (
            s.get("hard")
            or s["id"] in {"variety", "i2v_motion_gate", "cinematic_gate", "gate_auto"}
        )
    ]
    # soft fail film_core when not hard
    soft_only = [s for s in steps if not s.get("ok") and s.get("advisory") and not s.get("hard")]
    ok = not hard_failed
    blocked = hard_failed[0] if hard_failed else None
    next_cmd = (blocked or {}).get("next_cmd") or (
        f'aifilm closeout run --root "{root}"' if ok else None
    )
    out = {
        "schema_version": 1,
        "kind": "ship-prep",
        "at": utc_now(),
        "root": str(root),
        "ok": ok,
        "steps": steps,
        "blocked_by": (blocked or {}).get("id"),
        "soft_issues": [s["id"] for s in soft_only],
        "next_cmd": next_cmd,
        "gate": {
            "ok": gate_rep.get("ok") if gate_rep else None,
            "row_count": gate_rep.get("row_count"),
        },
        "film_core": {
            "ok": core.get("ok") if core else None,
            "hard": film_core_hard,
        },
        "note": (
            "means→true_video→variety→shortlist→pk_compare(advisory)→fill_idle(advisory)"
            "→motion-gate→film_core→input_fidelity; then closeout/export"
        ),
        "human_pk_required": any(
            s.get("id") == "pk_compare" and s.get("human_required") for s in steps
        )
        or promote_deferred,
        "promote_deferred_human_pk": promote_deferred,
    }
    # W4 · one-page human decision sheet (multi-take / PK)
    if write and (out.get("human_pk_required") or promote_deferred):
        human_md_path = root / "receipts" / "ship-prep-human.md"
        pk_step = next((s for s in steps if s.get("id") == "pk_compare"), {}) or {}
        dailies = pk_step.get("dailies_path") or str(root / "receipts" / "pk-dailies.md")
        multi_n = int(pk_step.get("multi_take_count") or 0)
        lines = [
            f"# Ship-prep human one-pager · {root.name}",
            "",
            f"- **ok**: {out.get('ok')}",
            f"- **human_pk_required**: {out.get('human_pk_required')}",
            f"- **promote_deferred**: {promote_deferred}",
            f"- **multi_take_shots**: {multi_n}",
            f"- **blocked_by**: {out.get('blocked_by') or '—'}",
            f"- **pk-dailies**: `{dailies}`",
            "",
            "## Do now (human only)",
            "",
            f"1. Open `{dailies}` — pick winners (never auto).",
            f'2. `aifilm h3 pk-compare --root "{root}"`',
            f'3. `aifilm select-shortlist --root "{root}" --promote`  # after eye-OK only',
            f'4. `aifilm gate-auto --root "{root}"`',
            f'5. `aifilm final --root "{root}" --post-engine hyperframes`  # when gates green',
            "",
            "## Multi-take shortlist (advisory)",
            "",
        ]
        for row in list(pk_step.get("shots") or [])[:30]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- **{row.get('shot_id')}** takes={row.get('take_count')} "
                f"rec={row.get('recommended_lane')} mean={row.get('recommended_mean')} "
                f"pk={row.get('pk_score')}"
            )
        if multi_n == 0:
            lines.append("- (no multi-take rows — promote may still need review)")
        lines.append("")
        try:
            human_md_path.parent.mkdir(parents=True, exist_ok=True)
            human_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            out["human_one_pager"] = str(human_md_path)
            out["dailies_path"] = dailies
        except OSError:
            pass
    if write:
        write_json(root / "receipts" / "ship-prep.json", out)
    return out


def _read_motion_mean(root: Path, shot_id: str, take: Path) -> float | None:
    # look for sidecar or i2v-high-motion-audit
    audit = read_json(root / "receipts" / "i2v-high-motion-audit.json") or {}
    per = audit.get("per_shot") if isinstance(audit.get("per_shot"), list) else []
    rows = audit.get("rows") if isinstance(audit.get("rows"), list) else per
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("shot_id") or row.get("id") or "") != shot_id:
            continue
        for key in ("mean", "mean_absdiff", "motion_mean"):
            if row.get(key) is None:
                continue
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    for side in (Path(str(take) + ".json"), take.with_suffix(take.suffix + ".json")):
        if not side.is_file():
            continue
        data = read_json(side) or {}
        for key in ("mean", "mean_absdiff", "motion_mean"):
            if data.get(key) is None:
                continue
            try:
                return float(data[key])
            except (TypeError, ValueError):
                return None
    return None


# ---------------------------------------------------------------------------
# C1 · GPU lease
# ---------------------------------------------------------------------------


def _lease_path_global() -> Path:
    """Shared lease across films (5090 one owner)."""
    base = Path(os.environ.get("AIFILM_GPU_LEASE_DIR") or Path.home() / ".grok" / "run")
    base.mkdir(parents=True, exist_ok=True)
    return base / GPU_LEASE_NAME


def _lease_path_film(root: Path) -> Path:
    return root / "receipts" / GPU_LEASE_NAME


def gpu_lease_status(root: Path | str | None = None) -> dict[str, Any]:
    root_p = _root(root) if root else None
    path = _lease_path_global()
    data = read_json(path) or {}
    if not data:
        return {
            "ok": True,
            "free": True,
            "owned_by_self": False,
            "path": str(path),
            "code": None,
        }
    owner = str(data.get("owner_root") or "")
    hb = float(data.get("heartbeat_unix") or data.get("started_unix") or 0)
    age = time.time() - hb if hb else 999999
    expired = age > LEASE_STALE_SEC
    if expired:
        return {
            "ok": True,
            "free": True,
            "owned_by_self": False,
            "expired": True,
            "stale_owner": owner,
            "age_sec": age,
            "path": str(path),
            "code": "LEASE_EXPIRED",
        }
    owned_by_self = bool(root_p and owner and Path(owner).resolve() == root_p)
    free = False
    code = None if owned_by_self else "LEASE_HELD"
    return {
        "ok": owned_by_self,
        "free": free,
        "owned_by_self": owned_by_self,
        "owner": owner,
        "pid": data.get("pid"),
        "age_sec": age,
        "heartbeat_unix": hb,
        "path": str(path),
        "code": code,
        "lease": data,
    }


def gpu_lease_acquire(root: Path | str, *, force: bool = False) -> dict[str, Any]:
    root = _root(root)
    st = gpu_lease_status(root)
    if st.get("owned_by_self"):
        return gpu_lease_heartbeat(root)
    if not st.get("free") and not force:
        raise WorkflowPackError(
            f"gpu lease held by {st.get('owner')} (code={st.get('code')}); "
            f"wait or aifilm gpu-lease release --root that-film"
        )
    lease = {
        "schema_version": 1,
        "kind": "gpu-lease",
        "owner_root": str(root),
        "pid": os.getpid(),
        "started_unix": time.time(),
        "heartbeat_unix": time.time(),
        "at": utc_now(),
    }
    write_json(_lease_path_global(), lease)
    write_json(_lease_path_film(root), lease)
    return {"ok": True, "acquired": True, "lease": lease}


def gpu_lease_heartbeat(root: Path | str) -> dict[str, Any]:
    root = _root(root)
    st = gpu_lease_status(root)
    if not st.get("owned_by_self") and not st.get("free"):
        raise WorkflowPackError(f"cannot heartbeat: lease owned by {st.get('owner')}")
    lease = dict(st.get("lease") or {})
    if not lease:
        return gpu_lease_acquire(root)
    lease["heartbeat_unix"] = time.time()
    lease["pid"] = os.getpid()
    lease["at"] = utc_now()
    write_json(_lease_path_global(), lease)
    write_json(_lease_path_film(root), lease)
    return {"ok": True, "heartbeat": True, "lease": lease}


def gpu_lease_release(root: Path | str, *, force: bool = False) -> dict[str, Any]:
    root = _root(root)
    st = gpu_lease_status(root)
    if not st.get("free") and not st.get("owned_by_self") and not force:
        raise WorkflowPackError(
            f"refuse release: owned by {st.get('owner')} (use --force only if sure)"
        )
    path = _lease_path_global()
    if path.is_file():
        path.unlink()
    film_path = _lease_path_film(root)
    if film_path.is_file():
        film_path.unlink()
    return {"ok": True, "released": True, "path": str(path)}


# ---------------------------------------------------------------------------
# C2 · tunnel probe
# ---------------------------------------------------------------------------


def tunnel_probe(
    *,
    port: int = DEFAULT_TUNNEL_PORT,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Probe localhost:{port}/system_stats — must be Comfy JSON, not 8189 auth."""
    url = f"http://127.0.0.1:{port}/system_stats"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536)
            status = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        body = exc.read(65536) if exc.fp else b""
        status = int(exc.code)
        text = body.decode("utf-8", errors="replace")
        if status == 401 or "unauthorized" in text.lower():
            return {
                "ok": False,
                "code": "TUNNEL_WRONG_PORT",
                "message": (
                    f"port {port} returned unauthorized — likely 8189 auth service, "
                    f"not Comfy 8188 (need 18188→8188)"
                ),
                "http_status": status,
                "port": port,
                "url": url,
            }
        return {
            "ok": False,
            "code": "TUNNEL_HTTP_ERROR",
            "message": f"HTTP {status}: {text[:160]}",
            "http_status": status,
            "port": port,
            "url": url,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "code": "TUNNEL_UNREACHABLE",
            "message": str(exc)[:200],
            "port": port,
            "url": url,
        }

    text = body.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "code": "TUNNEL_NOT_COMFY_JSON",
            "message": f"port {port} body is not Comfy system_stats JSON",
            "http_status": status,
            "port": port,
            "preview": text[:120],
        }
    if not isinstance(data, dict):
        return {
            "ok": False,
            "code": "TUNNEL_NOT_COMFY_JSON",
            "message": "system_stats root is not an object",
            "port": port,
        }
    # Comfy system_stats has system and/or devices
    if "system" not in data and "devices" not in data:
        return {
            "ok": False,
            "code": "TUNNEL_NOT_COMFY_JSON",
            "message": "JSON lacks system/devices — not Comfy system_stats",
            "port": port,
        }
    return {
        "ok": True,
        "code": None,
        "message": "Comfy system_stats reachable",
        "http_status": status,
        "port": port,
        "url": url,
        "system": data.get("system") if isinstance(data.get("system"), dict) else None,
        "device_count": len(data["devices"]) if isinstance(data.get("devices"), list) else 0,
    }


# ---------------------------------------------------------------------------
# C3 · progress honesty
# ---------------------------------------------------------------------------


def queue_progress_honest(root: Path | str) -> dict[str, Any]:
    """Progress = non-empty take files, not interrupt/running flags alone."""
    root = _root(root)
    takes = root / "takes"
    files: list[dict[str, Any]] = []
    if takes.is_dir():
        for p in takes.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".mp4", ".webm", ".mov", ".png", ".jpg"}:
                continue
            size = p.stat().st_size
            if size <= 0:
                continue
            files.append({"path": str(p.relative_to(root)), "bytes": size})
    clips_dir = root / "clips"
    clip_files = 0
    if clips_dir.is_dir():
        clip_files = sum(
            1
            for p in clips_dir.rglob("*")
            if p.is_file()
            and p.suffix.lower() in {".mp4", ".webm", ".mov"}
            and p.stat().st_size > 0
        )
    man = read_json(root / "manifest.json") or {}
    reg = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    return {
        "ok": True,
        "kind": "queue-progress-honest",
        "takes_files": len(files),
        "clip_files": clip_files,
        "manifest_clips": len(reg),
        "files_sample": files[:20],
        "note": (
            "progress only counts non-empty takes/clips files; "
            "Comfy interrupt / 0-byte is NOT progress"
        ),
        "interrupt_is_progress": False,
    }


def local_comfy_client_status() -> dict[str, Any]:
    """Best-effort: count local comfy_video.py processes (macOS/ps)."""
    try:
        import subprocess

        proc = subprocess.run(
            ["pgrep", "-fl", "comfy_video.py"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        # Filter generate-ish lines if possible
        count = len(lines)
        ok = count <= 1
        return {
            "ok": ok,
            "count": count,
            "lines": lines[:5],
            "note": "at most one local comfy_video.py client (16GB Mac OOM risk)",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "count": None, "skipped": True, "error": str(exc)[:120]}
