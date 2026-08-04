#!/usr/bin/env python3
"""Fill-Idle queue: Grok baseline + 5090 H3 challenge (P0→P1→P2).

Policy (2026-08-04 agree-all):
  - restricted / continue = primary H3 (P0*) — never starved by soft challenges
  - gate-fail takes = P1 re-challenge
  - idle fill = P2 challenge Grok (lowest mean first)
  - ship allowed with P2 incomplete; shortlist is advisory only
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from h3_mode import resolve_h3_mode, screen_mode_of, shot_size_token, spoken_text_of
from production_router import build_shot_intent
from util import read_json, utc_now

PRIORITY_RANK = {
    "P0a": 10,
    "P0b": 20,
    "P0c": 30,
    "P1": 40,
    "P2": 50,
    "P3": 90,
    "done": 100,
}

_H3_NAME_MARKERS = ("h3", "minimax", "r2v", "local_minimax", "comfy-h3", "ref2va", "fl2va")
_GROK_NAME_MARKERS = ("grok", "imagine", "media-queue", "xai")


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _iter_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                shots.append(shot)
    return shots


def _load_spec(root: Path) -> dict[str, Any]:
    data = read_json(root / "film-spec.json")
    return data if isinstance(data, dict) else {}


def guess_take_lane(path: Path) -> str:
    """Heuristic provider lane from path/name (not cryptographic)."""
    blob = str(path).lower()
    if any(m in blob for m in _H3_NAME_MARKERS):
        return "h3"
    if any(m in blob for m in _GROK_NAME_MARKERS):
        return "grok"
    # parent folder conventions takes/<sid>/h3_*.mp4
    name = path.name.lower()
    if name.startswith(("h3", "r2v", "i2v_h3", "minimax")):
        return "h3"
    if name.startswith(("grok", "cloud", "mq_")):
        return "grok"
    return "unknown"


def list_shot_takes(root: Path | str, shot_id: str) -> list[dict[str, Any]]:
    """Discover video takes under takes/ **and** manifest.clips (Grok baseline)."""
    base = _root(root)
    takes_root = base / "takes"
    files: list[Path] = []
    meta_by_path: dict[str, dict[str, Any]] = {}

    if takes_root.is_dir():
        shot_dir = takes_root / shot_id
        if shot_dir.is_dir():
            for p in shot_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".mp4", ".webm", ".mov"}:
                    files.append(p)
        for p in takes_root.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".mp4", ".webm", ".mov"}:
                continue
            stem = p.stem
            if stem == shot_id or stem.startswith(f"{shot_id}_"):
                files.append(p)

    # Baseline often lives only in manifest.clips after media-queue / register-clip
    man = read_json(base / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man, dict) else {}
    clip = clips.get(shot_id) if isinstance(clips, dict) else None
    if isinstance(clip, dict):
        raw = clip.get("path") or clip.get("file") or clip.get("video")
        if raw:
            p = Path(str(raw))
            if not p.is_absolute():
                p = base / p
            if p.is_file():
                files.append(p)
                lane_hint = str(
                    clip.get("lane")
                    or clip.get("provider")
                    or clip.get("source_endpoint")
                    or clip.get("preferred_from")
                    or ""
                ).lower()
                mean_hint = clip.get("mean_absdiff")
                if mean_hint is None:
                    mean_hint = clip.get("mean")
                meta_by_path[str(p.resolve())] = {
                    "lane_hint": lane_hint,
                    "mean_hint": mean_hint,
                    "source": "manifest.clips",
                }

    # unique
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for f in sorted(files, key=lambda x: str(x)):
        try:
            key = str(f.resolve())
        except OSError:
            key = str(f)
        if key in seen:
            continue
        seen.add(key)
        mean = _read_mean(f)
        meta = meta_by_path.get(key) or {}
        if mean is None and meta.get("mean_hint") is not None:
            try:
                mean = float(meta["mean_hint"])
            except (TypeError, ValueError):
                mean = None
        lane = guess_take_lane(f)
        hint = str(meta.get("lane_hint") or "")
        if lane == "unknown" and hint:
            if any(m in hint for m in _H3_NAME_MARKERS) or "comfy-h3" in hint:
                lane = "h3"
            elif (
                any(m in hint for m in _GROK_NAME_MARKERS)
                or "grok" in hint
                or "media-queue" in hint
                or "select-shortlist" in hint
            ):
                lane = "grok"
        out.append(
            {
                "path": str(f),
                "mean": mean,
                "lane": lane,
                "bytes": f.stat().st_size if f.is_file() else 0,
                "source": meta.get("source") or "takes",
            }
        )
    return out


def _read_mean(video: Path) -> float | None:
    side = Path(str(video) + ".json")
    if side.is_file():
        data = read_json(side)
        if isinstance(data, dict):
            for key in ("mean", "mean_absdiff", "motion_mean"):
                if data.get(key) is not None:
                    try:
                        return float(data[key])
                    except (TypeError, ValueError):
                        pass
    # sibling .json without double suffix
    alt = video.with_suffix(video.suffix + ".json")
    if alt != side and alt.is_file():
        data = read_json(alt)
        if isinstance(data, dict):
            for key in ("mean", "mean_absdiff", "motion_mean"):
                if data.get(key) is not None:
                    try:
                        return float(data[key])
                    except (TypeError, ValueError):
                        pass
    return None


def _best_mean(takes: list[dict[str, Any]]) -> float | None:
    means = [float(t["mean"]) for t in takes if t.get("mean") is not None]
    return max(means) if means else None


def _has_lane(takes: list[dict[str, Any]], lane: str) -> bool:
    return any(t.get("lane") == lane for t in takes)


def _motion_below_floor(
    shot: dict[str, Any],
    mean: float | None,
) -> tuple[bool, float | None]:
    if mean is None:
        return False, None
    try:
        from i2v_motion_gate import evaluate_shot_motion

        ev = evaluate_shot_motion(
            float(mean),
            heat_phase=shot.get("heat_phase"),
            dramatic_function=shot.get("dramatic_function"),
            wardrobe_state=shot.get("wardrobe_state"),
            shot_id=str(shot.get("id") or ""),
        )
        floor = ev.get("floor")
        return (not bool(ev.get("ok"))), (float(floor) if floor is not None else None)
    except Exception:
        return False, None


def _is_primary_h3(intent: dict[str, Any]) -> bool:
    return bool(
        intent.get("recommended_provider") == "comfy-h3"
        or intent.get("provider_lock") == "comfy-h3"
    )


def _poison_blocked(root: Path, shot_id: str) -> bool:
    """Soft check: poison receipts or rejected stills skip the queue."""
    man = read_json(root / "manifest.json") or {}
    stills = man.get("stills") if isinstance(man, dict) else {}
    still = stills.get(shot_id) if isinstance(stills, dict) else None
    if isinstance(still, dict):
        status = str(still.get("status") or "").lower()
        if status in {"poison", "rejected", "blocked"}:
            return True
        if still.get("poison") is True or still.get("anatomy_poison") is True:
            return True
    poison_dir = root / "receipts" / "poison"
    if poison_dir.is_dir():
        for p in poison_dir.glob(f"*{shot_id}*"):
            if p.is_file():
                return True
    return False


def classify_fill_idle_shot(
    root: Path | str,
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    has_still: bool = False,
    wants_continue: bool = False,
    takes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return priority + lane for one shot (Fill-Idle policy)."""
    base = _root(root)
    sid = str(shot.get("id") or "")
    intent = intent if isinstance(intent, dict) else build_shot_intent(_load_spec(base), shot)
    takes = takes if takes is not None else list_shot_takes(base, sid)
    primary = _is_primary_h3(intent)
    role = str(intent.get("shot_role") or shot.get("shot_role") or "hero").strip().lower()
    spoken = spoken_text_of(shot, intent)
    screen = screen_mode_of(shot, intent)
    size = shot_size_token(shot)
    close = (
        size
        in {
            "cu",
            "ecu",
            "close",
            "closeup",
            "close_up",
            "close-up",
            "extreme_close",
            "extreme_closeup",
            "extreme_close_up",
            "mcu",
            "l4",
            "insert_l4",
        }
        or "close" in size
    )
    on_cam = bool(spoken) and screen in {"on_camera", "on-camera", ""}
    best = _best_mean(takes)
    below, floor = _motion_below_floor(shot, best)
    has_h3 = _has_lane(takes, "h3")
    has_any = bool(takes)
    has_grok = _has_lane(takes, "grok") or (
        has_any and not has_h3 and any(t.get("lane") == "unknown" for t in takes)
    )
    poison = _poison_blocked(base, sid)

    reasons: list[str] = []
    priority = "P3"
    lane = "skip"
    status = "skip"

    if poison:
        priority, lane, status = "P3", "skip", "poison_blocked"
        reasons.append("poison_or_rejected_still")
    elif role in {"env", "bridge"} and not primary:
        # env stays out of lock-face challenge unless primary t2v path
        if not has_any:
            mode_res = resolve_h3_mode(
                shot, intent=intent, has_still=has_still, wants_continue=wants_continue
            )
            if mode_res.get("mode") == "t2v":
                priority, lane, status = "P2", "challenge_env", "pending"
                reasons.append("faceless_env_fill")
            else:
                reasons.append("env_skip")
        else:
            priority, lane, status = "done", "skip", "has_take"
            reasons.append("env_has_take")
    elif primary:
        lane = "primary_h3"
        if wants_continue:
            priority = "P0c"
            reasons.append("continue_endframe")
        elif on_cam and close:
            priority = "P0b"
            reasons.append("dialogue_close_restricted")
        else:
            priority = "P0a"
            reasons.append("restricted_primary")
        if has_h3 and not below:
            status = "done"
            reasons.append("h3_take_ok")
        elif has_h3 and below:
            priority = "P1"
            status = "retry"
            reasons.append("h3_below_floor")
        else:
            status = "pending"
            reasons.append("needs_h3_primary")
    elif below and has_any:
        priority, lane, status = "P1", "challenge_weak", "retry"
        reasons.append("take_below_floor")
    elif has_still and has_any:
        # soft challenge only after Grok/baseline take exists (main axis first)
        if has_h3 and not below:
            priority, lane, status = "done", "challenge_grok", "done"
            reasons.append("already_challenged_ok")
        elif has_h3 and below:
            priority, lane, status = "P1", "challenge_weak", "retry"
            reasons.append("challenge_below_floor")
        else:
            priority, lane, status = "P2", "challenge_grok", "pending"
            reasons.append("fill_idle_challenge")
            if has_grok or any(t.get("lane") == "unknown" for t in takes):
                reasons.append("has_baseline_take")
    elif has_still and not has_any and not primary:
        priority, lane, status = "P3", "skip", "wait_grok_baseline"
        reasons.append("wait_for_grok_baseline")
    else:
        priority, lane, status = "P3", "skip", "no_still"
        reasons.append("no_still_for_challenge")

    mode_res = resolve_h3_mode(
        shot, intent=intent, has_still=has_still, wants_continue=wants_continue
    )
    mode = str(mode_res.get("mode") or "i2v")
    # P2 soft challenges: default I2V first (policy); keep alt_mode from resolver
    if lane == "challenge_grok" and status.startswith("pending") and mode == "r2v":
        # still allow r2v if energy flags, but soft fill prefers i2v when alt exists
        if not primary and mode_res.get("alt_mode") != "i2v":
            pass  # keep r2v for true energy
        elif not primary:
            # prefer i2v for fair face PK unless dialogue-close energy
            if not (on_cam and close):
                mode = "i2v"
                reasons.append("p2_prefer_i2v_face_pk")

    cmd = (
        f'aifilm h3 run --root "{base}" --shot-id {sid} --mode {mode} --register'
        if status not in {"skip", "done", "poison_blocked"} and priority != "P3"
        else None
    )
    if status in {"pending", "retry"} and priority == "P2":
        cmd = (
            f'aifilm h3 run --root "{base}" --shot-id {sid} --mode {mode} --register --stage pilot'
        )

    return {
        "shot_id": sid,
        "priority": priority,
        "priority_rank": PRIORITY_RANK.get(priority, 99),
        "lane": lane,
        "status": status,
        "primary_h3": primary,
        "reasons": reasons,
        "mode": mode,
        "mode_reasons": list(mode_res.get("reasons") or []),
        "alt_mode": mode_res.get("alt_mode"),
        "alt_reasons": list(mode_res.get("alt_reasons") or []),
        "weapon_id": mode_res.get("weapon_id"),
        "content_class": intent.get("content_class"),
        "provider_lock": intent.get("provider_lock"),
        "has_still": bool(has_still),
        "wants_continue": bool(wants_continue),
        "spoken_text": bool(spoken),
        "motion_tier": intent.get("motion_tier"),
        "take_count": len(takes),
        "takes": takes,
        "best_mean": best,
        "below_floor": below,
        "floor": floor,
        "has_h3_take": has_h3,
        "has_baseline_take": has_any,
        "command": cmd,
        "command_alt": (
            (
                f'aifilm h3 run --root "{base}" --shot-id {sid} '
                f"--mode {mode_res.get('alt_mode')} --register"
            )
            if mode_res.get("alt_mode") and cmd
            else None
        ),
    }


def build_fill_idle_queue(
    root: Path | str,
    *,
    include_challenge: bool = True,
    include_done: bool = False,
) -> dict[str, Any]:
    """Build sorted Fill-Idle queue for the film root."""
    base = _root(root)
    spec = _load_spec(base)
    if not spec:
        return {
            "schema_version": 1,
            "kind": "ai-film-h3-fill-idle-queue",
            "ok": False,
            "error": "film-spec.json missing or invalid",
            "shots": [],
        }

    from h3_workflow import _approved_still, resolve_continue_handoff

    rows: list[dict[str, Any]] = []
    for shot in _iter_shots(spec):
        sid = str(shot.get("id") or "")
        intent = build_shot_intent(spec, shot)
        still = _approved_still(base, sid)
        cont = resolve_continue_handoff(base, sid, shot=shot, spec=spec)
        has_still = still is not None or (
            bool(cont.get("ok"))
            and bool(cont.get("end_frame"))
            and bool(cont.get("wants_continue"))
        )
        wants_continue = bool(cont.get("wants_continue"))
        primary = _is_primary_h3(intent)
        if not include_challenge and not primary:
            continue
        row = classify_fill_idle_shot(
            base,
            shot,
            intent=intent,
            has_still=has_still,
            wants_continue=wants_continue,
        )
        if not include_done and row.get("status") in {"done", "skip", "poison_blocked"}:
            if primary and row.get("status") == "done":
                # keep primary done rows optional
                continue
            if not primary:
                continue
        # primary-only mode: skip pure challenge rows
        if not include_challenge and row.get("lane") not in {"primary_h3"}:
            continue
        rows.append(row)

    # P2 order: mean lowest first; missing mean last within P2
    def sort_key(r: dict[str, Any]) -> tuple:
        rank = int(r.get("priority_rank") or 99)
        mean = r.get("best_mean")
        if r.get("priority") == "P2":
            mean_key = float(mean) if mean is not None else 1e9
        else:
            mean_key = 0.0
        return (rank, mean_key, str(r.get("shot_id") or ""))

    rows.sort(key=sort_key)

    pending = [r for r in rows if r.get("command")]
    next_row = pending[0] if pending else None
    by_pri: dict[str, int] = {}
    for r in rows:
        p = str(r.get("priority") or "?")
        by_pri[p] = by_pri.get(p, 0) + 1

    return {
        "schema_version": 1,
        "kind": "ai-film-h3-fill-idle-queue",
        "ok": True,
        "at": utc_now(),
        "root": str(base),
        "policy": "fill_idle_v1",
        "include_challenge": include_challenge,
        "count": len(rows),
        "pending_count": len(pending),
        "by_priority": by_pri,
        "next": (
            {
                "shot_id": next_row["shot_id"],
                "priority": next_row["priority"],
                "lane": next_row["lane"],
                "mode": next_row["mode"],
                "command": next_row["command"],
                "best_mean": next_row.get("best_mean"),
                "reasons": next_row.get("reasons"),
            }
            if next_row
            else None
        ),
        "shots": rows,
        "ops_reminder": [
            "P0 never starved by P2 — run next.command in order",
            "P2 sorted lowest mean first; pilot stage for fill challenges",
            "PK: select-shortlist advisory → human --promote",
            "aifilm comfy free-memory --confirm before mode switch",
        ],
    }


def probe_comfy_capacity_soft() -> dict[str, Any]:
    """Best-effort 5090 readiness (never raises; offline → ready=None)."""
    import os

    try:
        from comfy_video import normalize_base_url, submission_capacity

        raw = (
            os.environ.get("AIFILM_COMFYUI_BASE_URL")
            or os.environ.get("AIFILM_COMFY_BASE_URL")
            or "http://127.0.0.1:18188"
        ).strip()
        base_url = normalize_base_url(raw)
        cap = submission_capacity(base_url)
        ready = bool(cap.get("ok")) and str(cap.get("status") or "") == "ready"
        if not ready and not cap.get("blockers") and cap.get("ok"):
            ready = True
        observed = cap.get("observed") if isinstance(cap.get("observed"), dict) else {}
        device = observed.get("device") if isinstance(observed.get("device"), dict) else {}
        vram = device.get("vram_free_bytes")
        return {
            "ok": True,
            "ready": ready,
            "status": cap.get("status"),
            "vram_free_bytes": vram,
            "blockers": list(cap.get("blockers") or []),
            "base_url": base_url,
            "source": "submission_capacity",
        }
    except Exception as exc:  # noqa: BLE001 — capacity is advisory
        return {
            "ok": False,
            "ready": None,
            "error": str(exc)[:200],
            "source": "submission_capacity",
        }


def next_fill_idle_job(
    root: Path | str,
    *,
    include_challenge: bool = True,
    check_capacity: bool = True,
) -> dict[str, Any]:
    """Return the single next H3 job (P0→P1→P2 mean-first)."""
    queue = build_fill_idle_queue(root, include_challenge=include_challenge, include_done=False)
    nxt = queue.get("next")
    capacity = probe_comfy_capacity_soft() if check_capacity else {"ok": False, "ready": None}
    cmd = (nxt or {}).get("command") if isinstance(nxt, dict) else None
    note = (
        "Queue empty — P0/P1/P2 all clear or nothing eligible"
        if not nxt
        else "Run command; free-memory on mode switch"
    )
    if nxt and capacity.get("ready") is False:
        note = (
            "Comfy capacity not ready (VRAM/queue) — free-memory or wait; "
            "command is still the next Fill-Idle job"
        )
    elif nxt and capacity.get("ready") is True:
        note = "Capacity ready — run command now"
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-fill-idle-next",
        "ok": True,
        "root": queue.get("root"),
        "pending_count": queue.get("pending_count"),
        "by_priority": queue.get("by_priority"),
        "next": nxt,
        "command": cmd,
        "capacity": capacity,
        "capacity_ready": capacity.get("ready"),
        "note": note,
    }


def pk_compare(
    root: Path | str,
    *,
    shot_id: str | None = None,
    measure_missing: bool = False,
) -> dict[str, Any]:
    """Multi-take machine recommendation only — never writes preferred/promote."""
    base = _root(root)
    spec = _load_spec(base)
    shot_ids: list[str]
    if shot_id:
        shot_ids = [shot_id]
    else:
        # all shots that have takes
        takes_root = base / "takes"
        found: set[str] = set()
        if takes_root.is_dir():
            for p in takes_root.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".mp4", ".webm", ".mov"}:
                    sid = p.parent.name if p.parent != takes_root else p.stem.split("_")[0]
                    found.add(sid)
        shot_ids = sorted(found)

    shot_map = {str(s.get("id")): s for s in _iter_shots(spec)}
    rows: list[dict[str, Any]] = []
    for sid in shot_ids:
        takes = list_shot_takes(base, sid)
        if measure_missing:
            for t in takes:
                if t.get("mean") is None:
                    try:
                        from i2v_motion_gate import measure_mean_absdiff, write_mean_sidecar

                        p = Path(str(t["path"]))
                        m = measure_mean_absdiff(p)
                        if m is not None:
                            write_mean_sidecar(p, m)
                            t["mean"] = m
                    except Exception:
                        pass
        if not takes:
            continue
        scored = sorted(
            takes,
            key=lambda x: (
                -(float(x["mean"]) if x.get("mean") is not None else -1.0),
                -int(x.get("bytes") or 0),
            ),
        )
        recommended = scored[0]
        sh = shot_map.get(sid) or {}
        below, floor = _motion_below_floor(
            sh, recommended.get("mean") if recommended.get("mean") is not None else None
        )
        # identity caution when recommended is R2V/H3 energy and baseline is grok
        caution: list[str] = []
        if recommended.get("lane") == "h3" and any(t.get("lane") == "grok" for t in takes):
            caution.append("verify_same_face_before_promote")
        if "r2v" in str(recommended.get("path") or "").lower():
            caution.append("r2v_energy_check_identity")
        if below:
            caution.append("below_motion_floor")
        rows.append(
            {
                "shot_id": sid,
                "take_count": len(scored),
                "recommended": recommended,
                "candidates": scored,
                "below_floor": below,
                "floor": floor,
                "caution": caution,
                "human_required": True,
                "note": "advisory only — do not auto-promote; run select-shortlist --promote after human OK",
            }
        )

    return {
        "schema_version": 1,
        "kind": "ai-film-h3-pk-compare",
        "ok": True,
        "at": utc_now(),
        "root": str(base),
        "count": len(rows),
        "shots": rows,
        "policy": "machine_suggest_human_promote",
        "next_cmd": (
            f'aifilm select-shortlist --root "{base}"  # review then --promote' if rows else None
        ),
    }


def run_next_fill_idle(
    root: Path | str,
    *,
    include_challenge: bool = True,
    execute: bool = False,
    register: bool = True,
    require_capacity: bool = True,
    seed: int = 20260804,
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    """One-shot Fill-Idle worker: plan next job; optionally run when capacity ready.

    Not a daemon — call from cron/agent loop. Never auto-promotes PK winners.
    """
    base = _root(root)
    nxt_rep = next_fill_idle_job(base, include_challenge=include_challenge, check_capacity=True)
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-h3-fill-idle-run-next",
        "ok": True,
        "root": str(base),
        "execute": bool(execute),
        "next_report": nxt_rep,
        "ran": False,
        "skipped_reason": None,
        "run_result": None,
    }
    nxt = nxt_rep.get("next") if isinstance(nxt_rep.get("next"), dict) else None
    if not nxt:
        out["skipped_reason"] = "queue_empty"
        return out
    if not execute:
        out["skipped_reason"] = "dry_run_pass_execute"
        out["command"] = nxt.get("command")
        return out
    if require_capacity and nxt_rep.get("capacity_ready") is False:
        out["skipped_reason"] = "capacity_not_ready"
        out["ok"] = True  # advisory skip, not hard fail
        return out

    sid = str(nxt.get("shot_id") or "")
    mode = str(nxt.get("mode") or "i2v")
    try:
        from h3_workflow import run_h3_shot

        result = run_h3_shot(
            base,
            sid,
            mode=mode,
            register=bool(register),
            status="candidate",
            seed=int(seed),
            timeout_sec=int(timeout_sec),
            enqueue_queue=False,
            production_stage="production",
        )
        out["ran"] = True
        out["run_result"] = {
            k: result.get(k)
            for k in (
                "ok",
                "shot_id",
                "mode",
                "deliver_path",
                "receipt",
                "weapon_id",
            )
        }
        out["ok"] = bool(result.get("ok"))
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["skipped_reason"] = "run_failed"
        out["error"] = str(exc)[:300]
    # write receipt
    try:
        from util import write_json

        rec = base / "receipts" / "fill-idle-run-next.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        write_json(rec, out)
        out["receipt"] = str(rec)
    except Exception:
        pass
    return out


def pk_ledger_path(root: Path | str) -> Path:
    return _root(root) / "receipts" / "pk-ledger.json"


def load_pk_ledger(root: Path | str) -> dict[str, Any]:
    path = pk_ledger_path(root)
    data = read_json(path) if path.is_file() else None
    if isinstance(data, dict) and data.get("kind") == "ai-film-h3-pk-ledger":
        return data
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-pk-ledger",
        "ok": True,
        "root": str(_root(root)),
        "entries": [],
        "policy": "advisory_only_never_auto_promote_or_cross_film",
    }


def append_pk_ledger(
    root: Path | str,
    *,
    shot_id: str,
    winner_path: str,
    winner_lane: str | None = None,
    mean: float | None = None,
    note: str = "",
    human: str = "user",
) -> dict[str, Any]:
    """Append a human PK decision for dailies — never mutates manifest.clips."""
    base = _root(root)
    ledger = load_pk_ledger(base)
    entries = list(ledger.get("entries") or [])
    entry = {
        "at": utc_now(),
        "shot_id": shot_id,
        "winner_path": winner_path,
        "winner_lane": winner_lane,
        "mean": mean,
        "note": note,
        "human": human,
        "auto_applied": False,
    }
    entries.append(entry)
    ledger["entries"] = entries
    ledger["count"] = len(entries)
    ledger["updated_at"] = utc_now()
    from util import write_json

    path = pk_ledger_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, ledger)
    ledger["path"] = str(path)
    ledger["ok"] = True
    ledger["note"] = (
        "Ledger is advisory/dailies only — does not promote clips or carry "
        "win-rate into other films (agree-all 2026-08-04)."
    )
    return ledger
