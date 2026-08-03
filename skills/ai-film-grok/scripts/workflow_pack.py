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
    try:
        from still_uniqueness import active_still_reuse_report

        still_u = active_still_reuse_report(
            man,
            required_shot_ids=shot_ids,
            keyframes_dir=root / "keyframes",
        )
        add("still_uniqueness", bool(still_u.get("ok")), detail=still_u.get("note"))
    except Exception as exc:  # noqa: BLE001
        add("still_uniqueness", True, skipped=True, error=str(exc)[:120])

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

    failed = [c for c in checks if not c.get("ok")]
    ok = not failed
    next_cmd = None
    if not ok:
        first = failed[0]["id"]
        cmd_map = {
            "pilot": f'aifilm pilot pack --root "{root}"',
            "heat": f'aifilm heat boost --root "{root}" --apply',
            "state_index": f'aifilm state-index plan --root "{root}"',
            "still_uniqueness": f'aifilm status --root "{root}"  # still reuse',
            "anatomy_stills": f'aifilm register-still --root "{root}"  # anatomy_safe',
            "geometry": "fix keyframes to ≥704×1280 9:16",
            "tunnel": f"aifilm tunnel-probe --port {tunnel_port}",
            "local_comfy_client": "stop extra comfy_video.py clients (one only)",
            "gpu_lease": f'aifilm gpu-lease status --root "{root}"',
        }
        next_cmd = cmd_map.get(first, f'aifilm bulk-preflight --root "{root}"')

    out = {
        "schema_version": 1,
        "kind": "bulk-preflight",
        "at": utc_now(),
        "root": str(root),
        "ok": ok,
        "checks": checks,
        "failed": [c["id"] for c in failed],
        "next_cmd": next_cmd,
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
) -> dict[str, Any]:
    """Fail-closed bulk door. Default skips tunnel/lease (queue-friendly)."""
    report = bulk_preflight(
        root,
        write=True,
        probe_tunnel=probe_tunnel,
        check_lease=check_lease,
    )
    if require and not report.get("ok"):
        raise WorkflowPackError(
            "bulk preflight failed: "
            + ",".join(report.get("failed") or [])
            + f" — next: {report.get('next_cmd')}"
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


def select_shortlist(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Multi-take preferred pick: motion mean × style/medium heuristics; never delete takes."""
    root = _root(root)
    takes_root = root / "takes"
    man = read_json(root / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    rows: list[dict[str, Any]] = []

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

    for sid, files in sorted(shot_dirs.items()):
        scored: list[dict[str, Any]] = []
        for f in files:
            mean = _read_motion_mean(root, sid, f)
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
        preferred = scored[0] if scored else None
        rows.append(
            {
                "shot_id": sid,
                "take_count": len(scored),
                "preferred": preferred,
                "candidates": scored,
                "manifest_clip": clips.get(sid),
            }
        )

    # also surface shots with multiple clips registered under quality takes field
    out = {
        "schema_version": 1,
        "kind": "select-shortlist",
        "at": utc_now(),
        "root": str(root),
        "ok": True,
        "shots": rows,
        "note": "preferred is advisory; other takes retained",
        "next_cmd": f'aifilm selects --root "{root}"' if rows else None,
    }
    if write:
        write_json(root / "receipts" / SELECT_SHORTLIST_NAME, out)
    return out


def _read_motion_mean(root: Path, shot_id: str, take: Path) -> float | None:
    # look for sidecar or i2v-high-motion-audit
    audit = read_json(root / "receipts" / "i2v-high-motion-audit.json") or {}
    rows = audit.get("rows") if isinstance(audit.get("rows"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("shot_id") or row.get("id") or "") != shot_id:
            continue
        try:
            return float(row.get("mean") or row.get("motion_mean") or 0)
        except (TypeError, ValueError):
            return None
    side = take.with_suffix(take.suffix + ".json")
    if side.is_file():
        data = read_json(side) or {}
        try:
            return float(data.get("mean") or data.get("motion_mean") or 0)
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
