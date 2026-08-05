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

# Empirical wall-clock minutes per H3 job on a busy 5090 (planning ETA only).
_ETA_MINUTES_BY_MODE: dict[str, float] = {
    "i2v": 8.0,
    "flf": 10.0,
    "r2v": 12.0,
    "t2v": 10.0,
}
_DEFAULT_ETA_MINUTES = 9.0
# Overnight loop safety (not an OS daemon): cycles × max_jobs_per_cycle.
_UNTIL_EMPTY_MAX_CYCLES_HARD = 80
_UNTIL_EMPTY_MAX_JOBS_PER_CYCLE = 20

# Dual second leg sorts ahead of other same-rank pending (γ2 stickiness)
_DUAL_STICKY_REASONS = frozenset(
    {
        "dual_need_r2v",
        "dual_need_i2v",
        "dual_need_second_mode",
        "dual_second_leg_r2v",
        "dual_second_leg_i2v",
    }
)

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


def h3_modes_in_takes(takes: list[dict[str, Any]]) -> set[str]:
    """Infer which H3 modes already exist from path names (_i2v_ / _flf_ / _r2v_ / _t2v_)."""
    modes: set[str] = set()
    for t in takes:
        if t.get("lane") != "h3":
            continue
        blob = str(t.get("path") or "").lower()
        name = blob.split("/")[-1]
        if "_r2v_" in blob or "r2v" in name:
            modes.add("r2v")
        elif "_flf_" in blob or "flf" in name:
            modes.add("flf")
            modes.add("i2v")  # FLF counts as identity/first-last I2V leg for dual
        elif "_t2v_" in blob or "t2v" in name:
            modes.add("t2v")
        elif "_i2v_" in blob or "i2v" in name:
            modes.add("i2v")
        else:
            modes.add("h3")
    return modes


def wants_dual_take(
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    primary: bool = False,
    on_cam_close: bool = False,
) -> bool:
    """High-value dual I2V+R2V (opt-in flag or auto for climax / dialogue CU meat)."""
    sh = shot if isinstance(shot, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    prefer = (
        str(sh.get("h3_prefer") or sh.get("h3_dual") or intent.get("h3_prefer") or "")
        .strip()
        .lower()
    )
    if prefer in {"dual", "i2v+r2v", "both", "true", "1", "yes"}:
        return True
    if sh.get("force_dual") is True or intent.get("force_dual") is True:
        return True
    if not primary:
        return False
    heat = str(intent.get("heat_phase") or sh.get("heat_phase") or "").strip().lower()
    if heat == "climax":
        return True
    if on_cam_close and heat in {"act", "climax", "foreplay"}:
        return True
    return False


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

    # First/last media pack: FLF needs end still; R2V uses last as pose ref.
    has_last = False
    last_path: Path | None = None
    try:
        from h3_media_pack import resolve_last_frame_path

        lp, _lsrc = resolve_last_frame_path(base, sid, shot=shot)
        if lp is not None and lp.is_file():
            has_last = True
            last_path = lp
    except Exception:
        has_last = False
        last_path = None

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
                shot,
                intent=intent,
                has_still=has_still,
                has_last=has_last,
                wants_continue=wants_continue,
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
        h3_modes = h3_modes_in_takes(takes)
        dual = wants_dual_take(
            shot,
            intent=intent,
            primary=True,
            on_cam_close=bool(on_cam and close),
        )
        if has_h3 and below:
            priority = "P1"
            status = "retry"
            reasons.append("h3_below_floor")
        elif has_h3 and not below and dual:
            # Dual: identity leg (I2V or FLF) + energy R2V for high-value PK
            has_i2v = (
                "i2v" in h3_modes
                or "flf" in h3_modes
                or ("h3" in h3_modes and "r2v" not in h3_modes)
            )
            has_r2v = "r2v" in h3_modes
            explicit_dual = _explicit_dual_flag(shot, intent)
            # γ3: auto-dual only — if I2V/FLF already well above floor, skip blind R2V
            i2v_strong = _i2v_mean_strong_enough(takes, floor=floor, best=best)
            if has_i2v and has_r2v:
                status = "done"
                reasons.append("h3_dual_complete")
            elif has_r2v and not has_i2v:
                status = "pending"
                reasons.append("dual_need_i2v")
                if has_last:
                    reasons.append("dual_prefer_flf")
            elif has_i2v and not has_r2v:
                if i2v_strong and not explicit_dual:
                    status = "done"
                    reasons.append("skip_r2v_i2v_strong_enough")
                else:
                    status = "pending"
                    reasons.append("dual_need_r2v")
            else:
                status = "pending"
                reasons.append("dual_need_second_mode")
                if has_last:
                    reasons.append("dual_prefer_flf")
        elif has_h3 and not below:
            status = "done"
            reasons.append("h3_take_ok")
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
            # γ3: baseline already strong → skip low-ROI P2 burn
            if floor is not None and best is not None and float(best) >= float(floor) + 6.0:
                priority, lane, status = "done", "challenge_grok", "done"
                reasons.append("skip_p2_baseline_strong")
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
        shot,
        intent=intent,
        has_still=has_still,
        has_last=has_last,
        wants_continue=wants_continue,
    )
    mode = str(mode_res.get("mode") or "i2v")
    # Dual second leg: pick the missing mode explicitly
    if primary and "dual_need_r2v" in reasons:
        mode = "r2v"
        reasons.append("dual_second_leg_r2v")
    elif primary and "dual_need_i2v" in reasons:
        # Prefer FLF identity leg when end still exists
        mode = "flf" if has_last else "i2v"
        reasons.append("dual_second_leg_flf" if has_last else "dual_second_leg_i2v")
    # P2 soft challenges: default I2V/FLF first (policy); keep alt_mode from resolver
    elif lane == "challenge_grok" and status.startswith("pending") and mode == "r2v":
        # still allow r2v if energy flags, but soft fill prefers face lock when alt exists
        if not primary and mode_res.get("alt_mode") not in {"i2v", "flf"}:
            pass  # keep r2v for true energy
        elif not primary:
            # prefer flf/i2v for fair face PK unless dialogue-close energy
            if not (on_cam and close):
                mode = "flf" if has_last else "i2v"
                reasons.append("p2_prefer_flf_face_pk" if has_last else "p2_prefer_i2v_face_pk")

    last_cli = f' --last-frame "{last_path}"' if last_path and mode in {"flf", "r2v"} else ""
    cmd = (
        f'aifilm h3 run --root "{base}" --shot-id {sid} --mode {mode}{last_cli} --register'
        if status not in {"skip", "done", "poison_blocked"} and priority != "P3"
        else None
    )
    if status in {"pending", "retry"} and priority == "P2":
        cmd = (
            f'aifilm h3 run --root "{base}" --shot-id {sid} --mode {mode}{last_cli} '
            f"--register --stage pilot"
        )
    alt_mode = mode_res.get("alt_mode")
    alt_cli = ""
    if alt_mode and last_path and str(alt_mode) in {"flf", "r2v"}:
        alt_cli = f' --last-frame "{last_path}"'

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
        "alt_mode": alt_mode,
        "alt_reasons": list(mode_res.get("alt_reasons") or []),
        "weapon_id": mode_res.get("weapon_id"),
        "content_class": intent.get("content_class"),
        "provider_lock": intent.get("provider_lock"),
        "has_still": bool(has_still),
        "has_last": bool(has_last),
        "last_path": str(last_path) if last_path else None,
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
            (f'aifilm h3 run --root "{base}" --shot-id {sid} --mode {alt_mode}{alt_cli} --register')
            if alt_mode and cmd
            else None
        ),
        "dual_sticky": bool(_DUAL_STICKY_REASONS.intersection(reasons)),
    }


def _explicit_dual_flag(shot: dict[str, Any], intent: dict[str, Any]) -> bool:
    prefer = (
        str(shot.get("h3_prefer") or shot.get("h3_dual") or intent.get("h3_prefer") or "")
        .strip()
        .lower()
    )
    if prefer in {"dual", "i2v+r2v", "both", "true", "1", "yes"}:
        return True
    return bool(shot.get("force_dual") is True or intent.get("force_dual") is True)


def _i2v_mean_strong_enough(
    takes: list[dict[str, Any]],
    *,
    floor: float | None,
    best: float | None,
) -> bool:
    """True when an I2V/FLF (or generic h3) take is comfortably above motion floor."""
    if floor is None:
        return False
    thr = float(floor) + 4.0
    for t in takes:
        if t.get("lane") != "h3":
            continue
        blob = str(t.get("path") or "").lower()
        if "r2v" in blob:
            continue
        # flf / i2v / generic h3 all count as identity legs
        m = t.get("mean")
        if m is not None and float(m) >= thr:
            return True
    if best is not None and float(best) >= thr + 2.0:
        return True
    return False


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

    # P0 dual sticky first within rank; P2 lowest mean first
    def sort_key(r: dict[str, Any]) -> tuple:
        rank = int(r.get("priority_rank") or 99)
        sticky = 0 if r.get("dual_sticky") else 1
        mean = r.get("best_mean")
        if r.get("priority") == "P2":
            mean_key = float(mean) if mean is not None else 1e9
        else:
            mean_key = 0.0
        return (rank, sticky, mean_key, str(r.get("shot_id") or ""))

    rows.sort(key=sort_key)

    pending = [r for r in rows if r.get("command")]
    next_row = pending[0] if pending else None
    priority_violations = assert_priority_order(pending, next_row)
    # Fail-closed repair: if sort ever mis-picks, force next to true best pending.
    if priority_violations and pending:
        next_row = pending[0]
        priority_violations = assert_priority_order(pending, next_row)
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
        "priority_ok": not priority_violations,
        "priority_violations": priority_violations,
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
            "Overnight: aifilm h3 cycle --until-empty --execute",
        ],
    }


_MEMORY_FLOOR_CODES = frozenset({"RAM_BELOW_FLOOR", "VRAM_BELOW_FLOOR"})
_QUEUE_BUSY_CODE = "COMFY_QUEUE_BUSY"


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


def _capacity_blocker_codes(capacity: dict[str, Any] | None) -> set[str]:
    codes: set[str] = set()
    for item in (capacity or {}).get("blockers") or []:
        if isinstance(item, dict) and item.get("code"):
            codes.add(str(item["code"]))
    return codes


def _capacity_snapshot(capacity: dict[str, Any] | None) -> dict[str, Any]:
    cap = capacity or {}
    return {
        "ready": cap.get("ready"),
        "status": cap.get("status"),
        "blockers": list(cap.get("blockers") or []),
        "vram_free_bytes": cap.get("vram_free_bytes"),
        "error": cap.get("error"),
    }


def prepare_capacity_free_first(
    *,
    free_first: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Optionally free Comfy models once when idle queue is blocked only by RAM/VRAM floors.

    Safety:
    - never cancels foreign prompts / never free when ``COMFY_QUEUE_BUSY``
    - free at most once per call
    - only when every observed blocker is a memory floor code
    - dry_run probes and reports ``would_free`` without calling free-memory
    """
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-capacity-free-first",
        "free_first": bool(free_first),
        "attempted": False,
        "freed": False,
        "would_free": False,
        "skipped_reason": None,
        "outcome": None,
        "before": None,
        "after": None,
        "free_result": None,
    }
    if not free_first:
        report["skipped_reason"] = "free_first_disabled"
        report["outcome"] = "skipped"
        return report

    before = probe_comfy_capacity_soft()
    report["before"] = _capacity_snapshot(before)
    if before.get("ready") is True:
        report["skipped_reason"] = "already_ready"
        report["outcome"] = "already_ready"
        return report

    codes = _capacity_blocker_codes(before)
    if not codes and before.get("ready") is None:
        report["skipped_reason"] = "capacity_probe_unavailable"
        report["outcome"] = "skipped"
        return report
    if _QUEUE_BUSY_CODE in codes:
        report["skipped_reason"] = "queue_busy_never_cancel_foreign"
        report["outcome"] = "skipped_queue_busy"
        return report
    if not (codes & _MEMORY_FLOOR_CODES):
        report["skipped_reason"] = "no_memory_floor_block"
        report["outcome"] = "skipped"
        return report
    other = codes - _MEMORY_FLOOR_CODES
    if other:
        report["skipped_reason"] = "blockers_not_only_memory"
        report["other_blockers"] = sorted(other)
        report["outcome"] = "skipped_other_blockers"
        return report

    report["would_free"] = True
    if dry_run:
        report["skipped_reason"] = "dry_run_would_free"
        report["outcome"] = "dry_run_would_free"
        return report

    report["attempted"] = True
    try:
        import os

        from comfy_video import free_memory, normalize_base_url

        raw = (
            os.environ.get("AIFILM_COMFYUI_BASE_URL")
            or os.environ.get("AIFILM_COMFY_BASE_URL")
            or "http://127.0.0.1:18188"
        ).strip()
        base_url = normalize_base_url(raw)
        free_result = free_memory(base_url)
        report["free_result"] = free_result if isinstance(free_result, dict) else {"ok": bool(free_result)}
        report["freed"] = bool((report["free_result"] or {}).get("ok"))
    except Exception as exc:  # noqa: BLE001
        report["free_result"] = {"ok": False, "error": str(exc)[:200]}
        report["freed"] = False
        report["skipped_reason"] = "free_memory_error"
        report["outcome"] = "free_error"
        return report

    after = probe_comfy_capacity_soft()
    report["after"] = _capacity_snapshot(after)
    if after.get("ready") is True:
        report["outcome"] = "ready_after_free"
    else:
        report["outcome"] = "still_blocked_after_free"
        report["skipped_reason"] = "still_blocked_after_free"
    return report


_CAPACITY_WAIT_SEC_HARD_MAX = 600.0
_CAPACITY_WAIT_POLL_DEFAULT = 5.0


def wait_for_comfy_capacity(
    *,
    max_wait_sec: float = 0.0,
    poll_sec: float = _CAPACITY_WAIT_POLL_DEFAULT,
    sleep_fn=None,
) -> dict:
    """Poll soft capacity until ready or timeout. Never cancels foreign work.

    ``max_wait_sec<=0`` returns a single probe (no sleep). ``sleep_fn`` is injectable for tests.
    """
    import time as _time

    sleeper = sleep_fn if callable(sleep_fn) else _time.sleep
    max_wait = max(0.0, min(float(max_wait_sec or 0.0), _CAPACITY_WAIT_SEC_HARD_MAX))
    poll = max(0.5, float(poll_sec or _CAPACITY_WAIT_POLL_DEFAULT))
    started = _time.monotonic()
    probes = 0
    last = probe_comfy_capacity_soft()
    probes += 1
    if last.get("ready") is True or max_wait <= 0:
        return {
            "schema_version": 1,
            "kind": "ai-film-capacity-wait",
            "ok": True,
            "ready": last.get("ready") is True,
            "waited_sec": 0.0,
            "max_wait_sec": max_wait,
            "poll_sec": poll,
            "probes": probes,
            "last": _capacity_snapshot(last),
            "outcome": "ready" if last.get("ready") is True else "not_ready_no_wait",
        }

    while (_time.monotonic() - started) < max_wait:
        remaining = max_wait - (_time.monotonic() - started)
        sleeper(min(poll, max(0.1, remaining)))
        last = probe_comfy_capacity_soft()
        probes += 1
        if last.get("ready") is True:
            return {
                "schema_version": 1,
                "kind": "ai-film-capacity-wait",
                "ok": True,
                "ready": True,
                "waited_sec": round(_time.monotonic() - started, 2),
                "max_wait_sec": max_wait,
                "poll_sec": poll,
                "probes": probes,
                "last": _capacity_snapshot(last),
                "outcome": "ready_after_wait",
            }

    return {
        "schema_version": 1,
        "kind": "ai-film-capacity-wait",
        "ok": True,
        "ready": False,
        "waited_sec": round(_time.monotonic() - started, 2),
        "max_wait_sec": max_wait,
        "poll_sec": poll,
        "probes": probes,
        "last": _capacity_snapshot(last),
        "outcome": "timeout_still_blocked",
    }


def recover_capacity_contention(
    *,
    free_first: bool = False,
    capacity_wait_sec: float = 0.0,
    poll_sec: float = _CAPACITY_WAIT_POLL_DEFAULT,
    sleep_fn=None,
) -> dict:
    """S5.3 deep: free-first once more (if safe) then optional wait. Never cancel foreign."""
    report = {
        "schema_version": 1,
        "kind": "ai-film-capacity-recover",
        "free_first": bool(free_first),
        "capacity_wait_sec": float(capacity_wait_sec or 0.0),
        "free_prep": None,
        "wait": None,
        "ready": False,
        "outcome": None,
    }
    free_prep = prepare_capacity_free_first(free_first=bool(free_first), dry_run=False)
    report["free_prep"] = free_prep
    if free_prep.get("outcome") == "ready_after_free" or (free_prep.get("after") or {}).get(
        "ready"
    ) is True:
        report["ready"] = True
        report["outcome"] = "ready_after_free"
        return report

    wait_rep = wait_for_comfy_capacity(
        max_wait_sec=float(capacity_wait_sec or 0.0),
        poll_sec=poll_sec,
        sleep_fn=sleep_fn,
    )
    report["wait"] = wait_rep
    if wait_rep.get("ready") is True:
        report["ready"] = True
        report["outcome"] = wait_rep.get("outcome") or "ready"
        return report

    final = probe_comfy_capacity_soft()
    report["final"] = _capacity_snapshot(final)
    report["ready"] = final.get("ready") is True
    report["outcome"] = "ready" if report["ready"] else "still_blocked"
    return report



def assert_priority_order(
    pending: list[dict[str, Any]],
    next_row: dict[str, Any] | None,
) -> list[str]:
    """Hard invariant: next must be the best pending rank; P2 never ahead of P0/P1.

    Returns human-readable violation codes (empty = ok).
    """
    violations: list[str] = []
    if not pending:
        return violations
    if not isinstance(next_row, dict):
        violations.append("next_missing_while_pending")
        return violations
    best = pending[0]
    if str(next_row.get("shot_id") or "") != str(best.get("shot_id") or ""):
        violations.append(
            f"next_not_first_pending:{next_row.get('shot_id')}!={best.get('shot_id')}"
        )
    next_pri = str(next_row.get("priority") or "")
    next_rank = int(PRIORITY_RANK.get(next_pri, 99))
    p0_pending = [r for r in pending if str(r.get("priority") or "").startswith("P0")]
    p1_pending = [r for r in pending if str(r.get("priority") or "") == "P1"]
    if p0_pending and next_pri.startswith("P2"):
        violations.append("P2_selected_while_P0_pending")
    if p0_pending and next_pri == "P1":
        violations.append("P1_selected_while_P0_pending")
    if p1_pending and next_pri.startswith("P2") and not p0_pending:
        violations.append("P2_selected_while_P1_pending")
    for r in pending:
        r_rank = int(PRIORITY_RANK.get(str(r.get("priority") or ""), 99))
        if r_rank < next_rank:
            violations.append(f"higher_priority_starved:{r.get('priority')}:{r.get('shot_id')}")
            break
    return violations


def eta_minutes_for_mode(mode: str | None) -> float:
    key = str(mode or "i2v").strip().lower()
    return float(_ETA_MINUTES_BY_MODE.get(key, _DEFAULT_ETA_MINUTES))


def capacity_plan(
    root: Path | str,
    *,
    include_challenge: bool = True,
) -> dict[str, Any]:
    """Read-only backlog ETA for overnight H3 scheduling (no GPU)."""
    base = _root(root)
    queue = build_fill_idle_queue(base, include_challenge=include_challenge, include_done=False)
    pending = [r for r in (queue.get("shots") or []) if r.get("command")]
    by_mode: dict[str, int] = {}
    by_pri: dict[str, int] = {}
    eta_by_mode: dict[str, float] = {}
    eta_by_pri: dict[str, float] = {}
    total_eta = 0.0
    for r in pending:
        mode = str(r.get("mode") or "i2v").lower()
        pri = str(r.get("priority") or "?")
        minutes = eta_minutes_for_mode(mode)
        by_mode[mode] = by_mode.get(mode, 0) + 1
        by_pri[pri] = by_pri.get(pri, 0) + 1
        eta_by_mode[mode] = round(eta_by_mode.get(mode, 0.0) + minutes, 1)
        eta_by_pri[pri] = round(eta_by_pri.get(pri, 0.0) + minutes, 1)
        total_eta += minutes
    p0_jobs = sum(by_pri.get(k, 0) for k in ("P0a", "P0b", "P0c"))
    p0_eta = sum(eta_by_pri.get(k, 0.0) for k in ("P0a", "P0b", "P0c"))
    groups = [
        {
            "priority": pri,
            "jobs": by_pri.get(pri, 0),
            "eta_minutes": eta_by_pri.get(pri, 0.0),
        }
        for pri in sorted(by_pri.keys(), key=lambda p: PRIORITY_RANK.get(p, 99))
    ]
    plan = {
        "schema_version": 1,
        "kind": "ai-film-h3-capacity-plan",
        "ok": bool(queue.get("ok")),
        "at": utc_now(),
        "root": str(base),
        "pending_jobs": len(pending),
        "eta_minutes_total": round(total_eta, 1),
        "eta_hours_total": round(total_eta / 60.0, 2),
        "p0_jobs": p0_jobs,
        "p0_eta_minutes": round(p0_eta, 1),
        "by_mode": by_mode,
        "eta_by_mode": eta_by_mode,
        "by_priority": by_pri,
        "eta_by_priority": eta_by_pri,
        "groups": groups,
        "next": queue.get("next"),
        "priority_ok": queue.get("priority_ok", True),
        "priority_violations": queue.get("priority_violations") or [],
        "assumptions": {
            "minutes_per_mode": dict(_ETA_MINUTES_BY_MODE),
            "default_minutes": _DEFAULT_ETA_MINUTES,
            "serial_one_5090": True,
            "note": "ETA is planning only; real wall time varies with VRAM/queue",
        },
        "ops": [
            f'aifilm h3 cycle --root "{base}" --until-empty --execute',
            f'aifilm h3 run-next --root "{base}" --execute --max 5',
            f'aifilm h3 capacity-plan --root "{base}"',
        ],
    }
    try:
        from util import write_json

        path = base / "receipts" / "h3-capacity-plan.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, plan)
        plan["path"] = str(path)
    except Exception as exc:  # noqa: BLE001
        plan["write_error"] = str(exc)[:160]
    return plan


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
    still_hint = None
    try:
        from still_challenge import still_challenge_hint_for_fill_idle

        still_hint = still_challenge_hint_for_fill_idle(
            root, nxt if isinstance(nxt, dict) else None
        )
    except Exception:  # noqa: BLE001
        still_hint = None
    if still_hint and still_hint.get("prefer_still_challenge_first"):
        note = (
            "Prefer still-challenge (FRW i2i ≥30s) before more I2V/R2V — "
            "weak take often needs better source still"
        )
        if not cmd and still_hint.get("command"):
            cmd = still_hint.get("command")
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-fill-idle-next",
        "ok": True,
        "root": queue.get("root"),
        "pending_count": queue.get("pending_count"),
        "by_priority": queue.get("by_priority"),
        "priority_ok": queue.get("priority_ok", True),
        "priority_violations": queue.get("priority_violations") or [],
        "next": nxt,
        "command": cmd,
        "capacity": capacity,
        "capacity_ready": capacity.get("ready"),
        "still_challenge_hint": still_hint,
        "note": note,
    }


def _soft_identity_penalty(
    root: Path,
    shot_id: str,
    take_path: str,
    *,
    lane: str,
) -> tuple[float, list[str]]:
    """Best-effort midframe vs still similarity (0=good, higher=worse). Never hard-fails."""
    caution: list[str] = []
    penalty = 0.0
    blob = take_path.lower()
    if "r2v" in blob or lane == "h3" and "r2v" in blob:
        penalty += 2.0
        caution.append("r2v_energy_check_identity")
    try:
        from h3_workflow import _approved_still

        still = _approved_still(root, shot_id)
        if still is None or not Path(take_path).is_file():
            return penalty, caution
        # Extract one midframe via ffmpeg when available (bounded timeout — AF1)
        import shutil
        import tempfile

        if not shutil.which("ffmpeg"):
            return penalty, caution
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / "mid.png"
            try:
                from util.subprocess import run as util_run

                util_run(
                    [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        "0.5",
                        "-i",
                        take_path,
                        "-frames:v",
                        "1",
                        str(frame),
                    ],
                    check=False,
                    timeout=30,
                )
            except Exception:
                # Hang/timeout/start fail → skip identity pixel compare (soft)
                caution.append("identity_midframe_timeout_or_fail")
                return penalty, caution
            if not frame.is_file():
                caution.append("identity_midframe_missing")
                return penalty, caution
            try:
                import numpy as np
                from PIL import Image

                a = np.asarray(Image.open(still).convert("L").resize((64, 64)), dtype=float)
                b = np.asarray(Image.open(frame).convert("L").resize((64, 64)), dtype=float)
                l1 = float(np.mean(np.abs(a - b)))
                # empirical: similar still~clip mid often <25; drift higher
                # M4.4 · heavier identity weight so high-mean drift loses shortlist
                if l1 > 45:
                    penalty += 18.0
                    caution.append("identity_l1_high")
                elif l1 > 30:
                    penalty += 8.0
                    caution.append("identity_l1_soft")
                elif l1 > 25:
                    penalty += 3.0
                    caution.append("identity_l1_watch")
            except Exception:
                pass
    except Exception:
        pass
    return penalty, caution


def score_take_for_pk(
    take: dict[str, Any],
    *,
    floor: float | None,
    root: Path,
    shot_id: str,
) -> dict[str, Any]:
    """Composite advisory score: motion minus identity penalties (β1)."""
    mean = take.get("mean")
    mean_f = float(mean) if mean is not None else 0.0
    floor_f = float(floor) if floor is not None else 18.0
    motion_pts = mean_f
    if mean is not None and mean_f + 1e-9 < floor_f:
        motion_pts -= 15.0  # below floor heavy
    elif mean is not None:
        motion_pts += min(8.0, max(0.0, mean_f - floor_f))  # bonus above floor
    lane = str(take.get("lane") or "unknown")
    lane_bonus = 0.0
    if lane == "h3":
        lane_bonus = 1.0
    elif lane == "grok":
        lane_bonus = 0.5
    id_pen, id_caut = _soft_identity_penalty(root, shot_id, str(take.get("path") or ""), lane=lane)
    score = motion_pts + lane_bonus - id_pen
    caution = list(id_caut)
    if mean is not None and mean_f + 1e-9 < floor_f:
        caution.append("below_motion_floor")
    if lane == "h3":
        caution.append("verify_same_face_before_promote")
    return {
        **take,
        "pk_score": round(score, 3),
        "pk_motion": round(motion_pts, 3),
        "pk_identity_penalty": round(id_pen, 3),
        "pk_caution": caution,
    }


def pk_compare(
    root: Path | str,
    *,
    shot_id: str | None = None,
    measure_missing: bool = False,
    write_dailies: bool = True,
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
        man = read_json(base / "manifest.json") or {}
        clips = man.get("clips") if isinstance(man, dict) else {}
        if isinstance(clips, dict):
            found.update(str(k) for k in clips)
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
        sh = shot_map.get(sid) or {}
        # floor from best mean first for scoring context
        best = _best_mean(takes)
        below_probe, floor = _motion_below_floor(sh, best)
        del below_probe
        scored = [score_take_for_pk(t, floor=floor, root=base, shot_id=sid) for t in takes]
        scored.sort(
            key=lambda x: (
                -float(x.get("pk_score") or 0.0),
                -(float(x["mean"]) if x.get("mean") is not None else -1.0),
                -int(x.get("bytes") or 0),
            )
        )
        recommended = scored[0]
        below, floor2 = _motion_below_floor(
            sh, recommended.get("mean") if recommended.get("mean") is not None else None
        )
        floor = floor2 if floor2 is not None else floor
        caution = list(recommended.get("pk_caution") or [])
        if recommended.get("lane") == "h3" and any(t.get("lane") == "grok" for t in takes):
            if "verify_same_face_before_promote" not in caution:
                caution.append("verify_same_face_before_promote")
        if below and "below_motion_floor" not in caution:
            caution.append("below_motion_floor")
        # veto recommended if identity_l1_high and another take has lower penalty
        if "identity_l1_high" in caution and len(scored) > 1:
            alt = next(
                (c for c in scored[1:] if "identity_l1_high" not in (c.get("pk_caution") or [])),
                None,
            )
            if alt is not None:
                caution.append("recommended_downgraded_identity")
                recommended = alt
                caution = list(recommended.get("pk_caution") or []) + ["identity_prefer_safer_take"]
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
                "pk_policy": "composite_motion_minus_identity_v1",
                "note": (
                    "advisory only — do not auto-promote; "
                    "run select-shortlist --promote after human OK"
                ),
            }
        )

    dailies_lines = [
        f"# PK dailies · {base.name}",
        f"shots_with_takes={len(rows)} · human_required=all · never auto-promote",
        "",
    ]
    for r in rows:
        rec = r.get("recommended") or {}
        dailies_lines.append(
            f"- {r['shot_id']}: takes={r['take_count']} "
            f"rec={rec.get('lane')} mean={rec.get('mean')} "
            f"pk_score={rec.get('pk_score')} "
            f"caution={','.join(r.get('caution') or []) or '—'}"
        )
        dailies_lines.append(f"  path: {rec.get('path')}")

    dailies_md = "\n".join(dailies_lines) + "\n"
    dailies_path = base / "receipts" / "pk-dailies.md"
    if write_dailies and rows:
        try:
            dailies_path.parent.mkdir(parents=True, exist_ok=True)
            dailies_path.write_text(dailies_md, encoding="utf-8")
        except OSError:
            pass
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-pk-compare",
        "ok": True,
        "at": utc_now(),
        "root": str(base),
        "count": len(rows),
        "shots": rows,
        "policy": "machine_suggest_human_promote",
        "dailies_md": dailies_md,
        "dailies_path": str(dailies_path) if write_dailies and rows else None,
        "next_cmd": (
            f'aifilm select-shortlist --root "{base}" --promote  # review then promote'
            if rows
            else None
        ),
    }


def fill_idle_cycle(
    root: Path | str,
    *,
    execute: bool = False,
    max_jobs: int = 5,
    include_challenge: bool = True,
    notes: str = "",
    until_empty: bool = False,
    max_cycles: int = 40,
    stop_on_capacity: bool = True,
    free_first: bool = False,
    capacity_wait_sec: float = 0.0,
) -> dict[str, Any]:
    """One agent-facing cycle: evidence → run-next → evidence → pk peek.

    free_first / capacity_wait_sec enable contention recovery (never cancel foreign).
    """
    base = _root(root)
    if until_empty:
        return fill_idle_until_empty(
            base,
            execute=bool(execute),
            max_jobs_per_cycle=int(max_jobs or 5),
            max_cycles=int(max_cycles or 40),
            include_challenge=include_challenge,
            notes=notes,
            stop_on_capacity=bool(stop_on_capacity),
            free_first=bool(free_first),
            capacity_wait_sec=float(capacity_wait_sec or 0.0),
        )
    free_prep = prepare_capacity_free_first(
        free_first=bool(free_first),
        dry_run=not bool(execute),
    )
    before = write_fill_idle_evidence(base, notes=f"cycle-before {notes}".strip())
    run_rep = run_next_fill_idle(
        base,
        include_challenge=include_challenge,
        execute=bool(execute),
        max_jobs=int(max_jobs or 5),
        free_memory_on_mode_switch=True,
    )
    capacity_recovery = None
    if (
        bool(execute)
        and str(run_rep.get("skipped_reason") or "") == "capacity_not_ready"
        and (bool(free_first) or float(capacity_wait_sec or 0.0) > 0)
    ):
        capacity_recovery = recover_capacity_contention(
            free_first=bool(free_first),
            capacity_wait_sec=float(capacity_wait_sec or 0.0),
        )
        if capacity_recovery.get("ready") is True:
            run_rep = run_next_fill_idle(
                base,
                include_challenge=include_challenge,
                execute=True,
                max_jobs=int(max_jobs or 5),
                free_memory_on_mode_switch=True,
            )
    after = write_fill_idle_evidence(base, notes=f"cycle-after {notes}".strip())
    pk = pk_compare(base, measure_missing=False, write_dailies=True)
    multi = sum(1 for s in (pk.get("shots") or []) if int(s.get("take_count") or 0) >= 2)
    return {
        "schema_version": 1,
        "kind": "ai-film-fill-idle-cycle",
        "ok": bool(run_rep.get("ok") is not False),
        "root": str(base),
        "execute": bool(execute),
        "until_empty": False,
        "free_first": bool(free_first),
        "capacity_wait_sec": float(capacity_wait_sec or 0.0),
        "free_prep": free_prep,
        "capacity_recovery": capacity_recovery,
        "before": before.get("metrics"),
        "run": {
            "jobs_ran": run_rep.get("jobs_ran"),
            "skipped_reason": run_rep.get("skipped_reason"),
            "next_after": run_rep.get("next_after"),
            "command_after": run_rep.get("command_after"),
            "capacity_ready": (run_rep.get("next_report") or {}).get("capacity_ready"),
        },
        "after": after.get("metrics"),
        "pk_multi_take": multi,
        "dailies_path": pk.get("dailies_path"),
        "human_next": (
            [
                f'aifilm h3 pk-compare --root "{base}"',
                f'aifilm select-shortlist --root "{base}" --promote  # only after human OK',
                f'aifilm ship-prep --root "{base}"',
            ]
            if multi
            else [
                f'aifilm h3 run-next --root "{base}" --execute --max {max_jobs}',
                (
                    f'aifilm h3 cycle --root "{base}" --until-empty --execute '
                    f"--free-first --capacity-wait-sec 120"
                ),
                f'aifilm ship-prep --root "{base}"',
            ]
        ),
        "note": (
            "never auto-promote; free_first never cancels foreign; "
            "capacity_wait polls ready without cancel"
        ),
    }


def fill_idle_until_empty(
    root: Path | str,
    *,
    execute: bool = False,
    max_jobs_per_cycle: int = 5,
    max_cycles: int = 40,
    include_challenge: bool = True,
    notes: str = "",
    stop_on_capacity: bool = True,
    free_first: bool = False,
    capacity_wait_sec: float = 0.0,
) -> dict[str, Any]:
    """Overnight loop until queue empty or safety stop.

    free_first and/or capacity_wait_sec recover contention then continue if ready.
    Never cancels foreign prompts; not an OS daemon.
    """
    base = _root(root)
    max_cycles = max(1, min(int(max_cycles or 40), _UNTIL_EMPTY_MAX_CYCLES_HARD))
    max_jobs_per_cycle = max(1, min(int(max_jobs_per_cycle or 5), _UNTIL_EMPTY_MAX_JOBS_PER_CYCLE))
    capacity_wait_sec = max(0.0, min(float(capacity_wait_sec or 0.0), _CAPACITY_WAIT_SEC_HARD_MAX))
    free_prep = prepare_capacity_free_first(
        free_first=bool(free_first),
        dry_run=not bool(execute),
    )
    plan_before = capacity_plan(base, include_challenge=include_challenge)
    before = write_fill_idle_evidence(base, notes=f"until-empty-before {notes}".strip())
    cycles: list[dict[str, Any]] = []
    capacity_waits: list[dict[str, Any]] = []
    total_ran = 0
    stop_reason = "max_cycles"
    ok = True

    for cycle_i in range(max_cycles):
        run_rep = run_next_fill_idle(
            base,
            include_challenge=include_challenge,
            execute=bool(execute),
            max_jobs=max_jobs_per_cycle,
            free_memory_on_mode_switch=True,
        )
        ran = int(run_rep.get("jobs_ran") or 0)
        total_ran += ran
        skipped = str(run_rep.get("skipped_reason") or "")
        cycle_row: dict[str, Any] = {
            "cycle": cycle_i + 1,
            "jobs_ran": ran,
            "skipped_reason": skipped or None,
            "ok": bool(run_rep.get("ok") is not False),
            "pending_after": run_rep.get("pending_after"),
            "next_after": run_rep.get("next_after"),
        }
        cycles.append(cycle_row)
        if not execute:
            stop_reason = "dry_run_pass_execute"
            break
        if skipped in {"queue_empty", "queue_empty_after_runs"}:
            stop_reason = "queue_empty"
            break
        if skipped == "capacity_not_ready" and stop_on_capacity:
            if bool(free_first) or capacity_wait_sec > 0:
                recover = recover_capacity_contention(
                    free_first=bool(free_first),
                    capacity_wait_sec=capacity_wait_sec,
                )
                capacity_waits.append(recover)
                cycle_row["capacity_recover"] = {
                    "outcome": recover.get("outcome"),
                    "ready": recover.get("ready"),
                    "waited_sec": (recover.get("wait") or {}).get("waited_sec"),
                }
                if recover.get("ready"):
                    continue
            stop_reason = "capacity_not_ready"
            break
        if skipped == "run_failed" or run_rep.get("ok") is False:
            stop_reason = "run_failed"
            ok = False
            break
        if ran == 0 and skipped not in {"", "None"}:
            stop_reason = skipped or "no_progress"
            break
        if ran == 0:
            stop_reason = "no_progress"
            break

    after = write_fill_idle_evidence(base, notes=f"until-empty-after {notes}".strip())
    plan_after = capacity_plan(base, include_challenge=include_challenge)
    pk = pk_compare(base, measure_missing=False, write_dailies=True)
    multi = sum(1 for s in (pk.get("shots") or []) if int(s.get("take_count") or 0) >= 2)
    report = {
        "schema_version": 1,
        "kind": "ai-film-fill-idle-until-empty",
        "ok": ok,
        "root": str(base),
        "execute": bool(execute),
        "until_empty": True,
        "free_first": bool(free_first),
        "capacity_wait_sec": capacity_wait_sec,
        "capacity_waits": capacity_waits,
        "free_prep": free_prep,
        "stop_reason": stop_reason,
        "cycles_run": len(cycles),
        "max_cycles": max_cycles,
        "max_jobs_per_cycle": max_jobs_per_cycle,
        "jobs_ran_total": total_ran,
        "plan_before": {
            "pending_jobs": plan_before.get("pending_jobs"),
            "eta_minutes_total": plan_before.get("eta_minutes_total"),
            "p0_jobs": plan_before.get("p0_jobs"),
        },
        "plan_after": {
            "pending_jobs": plan_after.get("pending_jobs"),
            "eta_minutes_total": plan_after.get("eta_minutes_total"),
            "p0_jobs": plan_after.get("p0_jobs"),
        },
        "before": before.get("metrics"),
        "after": after.get("metrics"),
        "cycles": cycles,
        "pk_multi_take": multi,
        "dailies_path": pk.get("dailies_path"),
        "human_next": (
            [
                f'aifilm h3 pk-compare --root "{base}"',
                f'aifilm select-shortlist --root "{base}" --promote  # only after human OK',
                f'aifilm ship-prep --root "{base}"',
            ]
            if multi or stop_reason == "queue_empty"
            else [
                (
                    f'aifilm h3 cycle --root "{base}" --until-empty --execute '
                    f"--free-first --capacity-wait-sec 120"
                ),
                "aifilm comfy free-memory --confirm  # manual if free_first skipped queue_busy",
                f'aifilm h3 capacity-plan --root "{base}"',
            ]
        ),
        "note": (
            "until-empty owns process until stop; never auto-promote; "
            "free_first never cancels foreign; capacity_wait polls without cancel"
        ),
    }
    try:
        from util import write_json

        path = base / "receipts" / "fill-idle-until-empty.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, report)
        report["path"] = str(path)
    except Exception as exc:  # noqa: BLE001
        report["write_error"] = str(exc)[:160]
    return report

def write_fill_idle_evidence(
    root: Path | str,
    *,
    notes: str = "",
) -> dict[str, Any]:
    """Wave α · snapshot queue + multi-take stats for film evidence (no GPU)."""
    base = _root(root)
    queue = build_fill_idle_queue(base, include_challenge=True, include_done=True)
    pk = pk_compare(base, measure_missing=False)
    multi = [s for s in (pk.get("shots") or []) if int(s.get("take_count") or 0) >= 2]
    pending = [r for r in (queue.get("shots") or []) if r.get("command")]
    by_pri = queue.get("by_priority") or {}
    eta_total = 0.0
    by_mode: dict[str, int] = {}
    for r in pending:
        mode = str(r.get("mode") or "i2v").lower()
        by_mode[mode] = by_mode.get(mode, 0) + 1
        eta_total += eta_minutes_for_mode(mode)
    evidence = {
        "schema_version": 1,
        "kind": "ai-film-fill-idle-evidence",
        "ok": True,
        "at": utc_now(),
        "root": str(base),
        "notes": notes,
        "metrics": {
            "p0_pending": sum(int(by_pri.get(k) or 0) for k in ("P0a", "P0b", "P0c")),
            "p1_pending": int(by_pri.get("P1") or 0),
            "p2_pending": int(by_pri.get("P2") or 0),
            "pending_jobs": len(pending),
            "multi_take_shots": len(multi),
            "by_priority": by_pri,
            "by_mode": by_mode,
            "priority_ok": queue.get("priority_ok", True),
            "eta_minutes_total": round(eta_total, 1),
        },
        "checklist": {
            "fill_p0_first": True,
            "human_promote_only": True,
            "final_ok_with_p2_incomplete": True,
            "film_case_path": str(base),
        },
        "next_ops": [
            f'aifilm h3 capacity-plan --root "{base}"',
            f'aifilm h3 cycle --root "{base}" --until-empty --execute',
            f'aifilm h3 run-next --root "{base}" --execute --max 5',
            f'aifilm ship-prep --root "{base}"',
            f'aifilm h3 pk-compare --root "{base}"',
        ],
        "dailies_md": pk.get("dailies_md"),
    }
    path = base / "receipts" / "fill-idle-evidence.json"
    try:
        from util import write_json

        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, evidence)
        evidence["path"] = str(path)
    except Exception as exc:
        evidence["write_error"] = str(exc)[:160]
    return evidence


def _stage_for_fill_idle_job(nxt: dict[str, Any]) -> str:
    """P2 soft challenges use pilot; primary P0/P1 stay production."""
    pri = str(nxt.get("priority") or "")
    lane = str(nxt.get("lane") or "")
    if pri == "P2" or lane in {"challenge_grok", "challenge_env", "challenge_weak"}:
        # challenge_weak / P1 may still be meat retry — keep production for P1
        if pri == "P1" and lane == "challenge_weak":
            return "production"
        if pri == "P2" or lane in {"challenge_grok", "challenge_env"}:
            return "pilot"
    return "production"


def _maybe_free_memory_for_mode_switch(
    *,
    prev_mode: str | None,
    next_mode: str,
    enabled: bool,
) -> dict[str, Any] | None:
    """γ1 · free Comfy VRAM when switching I2V/R2V/T2V (best-effort)."""
    if not enabled:
        return None
    if prev_mode and prev_mode == next_mode:
        return {"skipped": True, "reason": "same_mode"}
    try:
        import os

        from comfy_video import free_memory, normalize_base_url

        raw = (
            os.environ.get("AIFILM_COMFYUI_BASE_URL")
            or os.environ.get("AIFILM_COMFY_BASE_URL")
            or "http://127.0.0.1:18188"
        ).strip()
        base_url = normalize_base_url(raw)
        return free_memory(base_url)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def run_next_fill_idle(
    root: Path | str,
    *,
    include_challenge: bool = True,
    execute: bool = False,
    register: bool = True,
    require_capacity: bool = True,
    seed: int = 20260804,
    timeout_sec: int = 1800,
    max_jobs: int = 1,
    free_memory_on_mode_switch: bool = True,
) -> dict[str, Any]:
    """Fill-Idle worker: plan next job; optionally run when capacity ready.

    Not a daemon — ``max_jobs`` caps how many runs in one call (default 1, hard max 20).
    Never auto-promotes PK winners. P2 soft challenges use pilot stage.
    """
    base = _root(root)
    max_jobs = max(1, min(int(max_jobs or 1), 20))
    runs: list[dict[str, Any]] = []
    last_out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-h3-fill-idle-run-next",
        "ok": True,
        "root": str(base),
        "execute": bool(execute),
        "max_jobs": max_jobs,
        "jobs_attempted": 0,
        "jobs_ran": 0,
        "runs": runs,
        "ran": False,
        "skipped_reason": None,
        "run_result": None,
        "next_report": None,
        "free_memory_on_mode_switch": bool(free_memory_on_mode_switch),
    }
    prev_mode: str | None = None

    for job_i in range(max_jobs):
        nxt_rep = next_fill_idle_job(base, include_challenge=include_challenge, check_capacity=True)
        last_out["next_report"] = nxt_rep
        nxt = nxt_rep.get("next") if isinstance(nxt_rep.get("next"), dict) else None
        if not nxt:
            last_out["skipped_reason"] = "queue_empty" if job_i == 0 else "queue_empty_after_runs"
            break
        if not execute:
            last_out["skipped_reason"] = "dry_run_pass_execute"
            last_out["command"] = nxt.get("command")
            last_out["next"] = nxt
            break
        if require_capacity and nxt_rep.get("capacity_ready") is False:
            last_out["skipped_reason"] = "capacity_not_ready"
            last_out["ok"] = True  # advisory skip, not hard fail
            last_out["command"] = nxt.get("command")
            break

        sid = str(nxt.get("shot_id") or "")
        mode = str(nxt.get("mode") or "i2v")
        stage = _stage_for_fill_idle_job(nxt)
        fm = _maybe_free_memory_for_mode_switch(
            prev_mode=prev_mode,
            next_mode=mode,
            enabled=bool(free_memory_on_mode_switch) and (job_i > 0 or prev_mode is not None),
        )
        last_out["jobs_attempted"] = int(last_out["jobs_attempted"]) + 1
        try:
            from h3_workflow import run_h3_shot

            result = run_h3_shot(
                base,
                sid,
                mode=mode,
                register=bool(register),
                status="candidate",
                seed=int(seed) + job_i,
                timeout_sec=int(timeout_sec),
                enqueue_queue=False,
                production_stage=stage,
            )
            prev_mode = mode
            run_row = {
                "shot_id": sid,
                "mode": mode,
                "priority": nxt.get("priority"),
                "lane": nxt.get("lane"),
                "stage": stage,
                "ok": bool(result.get("ok")),
                "deliver_path": result.get("deliver_path"),
                "free_memory": fm,
            }
            runs.append(run_row)
            last_out["ran"] = True
            last_out["jobs_ran"] = int(last_out["jobs_ran"]) + 1
            last_out["run_result"] = {
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
            last_out["ok"] = bool(result.get("ok"))
            if not result.get("ok"):
                last_out["skipped_reason"] = "run_failed"
                break
        except Exception as exc:  # noqa: BLE001
            last_out["ok"] = False
            last_out["skipped_reason"] = "run_failed"
            last_out["error"] = str(exc)[:300]
            runs.append(
                {
                    "shot_id": sid,
                    "mode": mode,
                    "stage": stage,
                    "ok": False,
                    "error": str(exc)[:200],
                }
            )
            break

    # Chain hint after last successful/attempted job
    try:
        after = next_fill_idle_job(base, include_challenge=include_challenge, check_capacity=False)
        last_out["next_after"] = after.get("next")
        last_out["command_after"] = after.get("command")
        last_out["pending_after"] = after.get("pending_count")
    except Exception:
        last_out["next_after"] = None

    try:
        from util import write_json

        rec = base / "receipts" / "fill-idle-run-next.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        write_json(rec, last_out)
        last_out["receipt"] = str(rec)
    except Exception:
        pass
    return last_out


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
