"""FRW img2image still-material challenge for better I2V/R2V sources.

Policy (2026-08-04):
  - FRW image submit ≥30s (``frw_rate_limit`` shared state)
  - Default unit = 1 submit / invocation
  - Candidate stills under takes/<shot>/still_frw_*.png — never silent promote
  - Skip poison + continue-handoff chains
  - Does not steal 5090 H3 GPU time (cloud FRW i2i)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from frw_rate_limit import (
    IMAGE_MIN_INTERVAL_S,
    SubmitBudget,
    frw_rate_snapshot,
    peek_frw_rate_wait,
)
from util import read_json, utc_now, write_json

PRIORITY_RANK = {
    "S0": 10,
    "S1": 20,
    "S2": 30,
    "S3": 40,
    "skip": 90,
    "done": 100,
}

IMG2IMAGE_STEPS = 15
IMG2IMAGE_CFG = 4.5
DEFAULT_MODEL = "flux"


class StillChallengeError(RuntimeError):
    pass


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


def _approved_still(root: Path, shot_id: str) -> Path | None:
    from h3_workflow import _approved_still as _h3_still

    return _h3_still(root, shot_id)


def _is_poison(root: Path, shot_id: str, shot: dict[str, Any]) -> bool:
    tags = shot.get("tags") or shot.get("flags") or []
    if isinstance(tags, str):
        tags = [tags]
    blob = " ".join(str(t).lower() for t in tags)
    if "poison" in blob or "anatomy_poison" in blob:
        return True
    archive = root / "clips" / "_archive_anatomy_poison"
    if archive.is_dir() and any(archive.glob(f"*{shot_id}*")):
        return True
    note = str(shot.get("anatomy_status") or shot.get("poison") or "").lower()
    return "poison" in note or note in {"unsafe", "fail"}


def _wants_continue(shot: dict[str, Any]) -> bool:
    try:
        from continue_handoff import shot_wants_continue

        return bool(shot_wants_continue(shot))
    except Exception:  # noqa: BLE001
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        return str(dsl.get("chain_mode") or "").lower() == "continue" or bool(
            shot.get("parent_shot_id")
        )


def _best_mean(root: Path, shot_id: str) -> float | None:
    """Best-effort mean_absdiff from fill-idle / motion receipts."""
    candidates = [
        root / "receipts" / "motion" / f"{shot_id}.json",
        root / "receipts" / "i2v-motion" / f"{shot_id}.json",
        root / "takes" / shot_id / "motion.json",
    ]
    for path in candidates:
        data = read_json(path)
        if isinstance(data, dict) and data.get("mean_absdiff") is not None:
            try:
                return float(data["mean_absdiff"])
            except (TypeError, ValueError):
                pass
    # Scan takes for any motion sidecar
    takes_dir = root / "takes" / shot_id
    if takes_dir.is_dir():
        for p in takes_dir.glob("*.json"):
            data = read_json(p)
            if isinstance(data, dict) and data.get("mean_absdiff") is not None:
                try:
                    return float(data["mean_absdiff"])
                except (TypeError, ValueError):
                    continue
    return None


def _has_any_take(root: Path, shot_id: str) -> bool:
    try:
        from h3_fill_idle import list_shot_takes

        return bool(list_shot_takes(root, shot_id))
    except Exception:  # noqa: BLE001
        takes = root / "takes" / shot_id
        if takes.is_dir() and any(takes.glob("*.mp4")):
            return True
        man = read_json(root / "manifest.json") or {}
        clips = man.get("clips") if isinstance(man, dict) else {}
        return isinstance(clips, dict) and shot_id in clips


def list_candidates(root: Path | str, shot_id: str) -> list[dict[str, Any]]:
    base = _root(root)
    out: list[dict[str, Any]] = []
    takes = base / "takes" / shot_id
    if not takes.is_dir():
        return out
    for p in sorted(takes.glob("still_frw_*.png")) + sorted(takes.glob("still_frw_*.jpg")):
        out.append(
            {
                "path": str(p),
                "name": p.name,
                "sha256": _sha256(p) if p.is_file() else None,
                "mtime": p.stat().st_mtime if p.is_file() else None,
            }
        )
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _soft_still_heuristic(shot: dict[str, Any], intent: dict[str, Any] | None) -> bool:
    """True when still is likely soft portrait / weak energy for meat motion."""
    intent = intent or {}
    tier = str(intent.get("motion_tier") or shot.get("motion_tier") or "").lower()
    content = str(intent.get("content_class") or "").lower()
    if tier in {"high", "meat"} or content in {"act", "climax", "bare", "restricted"}:
        return True
    flags = shot.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    hard = {"deep_thrust", "creampie", "force_local_h3", "high_motion", "L4"}
    return bool(hard.intersection({str(f) for f in flags}))


def build_static_i2i_prompt(shot: dict[str, Any], intent: dict[str, Any] | None = None) -> str:
    """Static readable still prompt — not full I2V motion sentences."""
    intent = intent or {}
    parts: list[str] = [
        "single continuous cinematic still frame",
        "one shot composition only",
        "no collage",
        "no character sheet",
        "no subtitles",
        "no watermark",
    ]
    for key in (
        "shot_size",
        "framing",
        "camera_angle",
        "action",
        "visible_change",
        "wardrobe_state",
        "location",
    ):
        val = (
            shot.get(key) or (shot.get("dsl") or {}).get(key)
            if isinstance(shot.get("dsl"), dict)
            else None
        )
        if val:
            parts.append(f"{key.replace('_', ' ')}: {val}")
    for key in ("dramatic_function", "want_beat", "content_class"):
        if intent.get(key):
            parts.append(f"{key.replace('_', ' ')}: {intent[key]}")
    spoken = intent.get("spoken_text") or shot.get("dialogue")
    if spoken:
        parts.append(f"performance mouth shape for line: {str(spoken)[:80]}")
    parts.append("identity locked to reference image, same face hair body")
    parts.append("high detail, sharp focus, vertical 9:16 story frame")
    return ", ".join(parts)


def classify_still_challenge_shot(
    root: Path | str,
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _root(root)
    sid = str(shot.get("id") or "")
    still = _approved_still(base, sid)
    has_still = still is not None
    candidates = list_candidates(base, sid)
    wants_cont = _wants_continue(shot)
    poison = _is_poison(base, sid, shot)
    mean = _best_mean(base, sid)
    has_take = _has_any_take(base, sid)

    if poison:
        return _row(
            base,
            sid,
            priority="skip",
            status="poison_blocked",
            reasons=["poison_still"],
            still=still,
            candidates=candidates,
        )
    if wants_cont:
        return _row(
            base,
            sid,
            priority="skip",
            status="continue_chain",
            reasons=["continue_handoff_skip_i2i"],
            still=still,
            candidates=candidates,
        )
    if candidates and not _promoted_after(base, sid, candidates):
        # already have unreviewed candidate — don't stampede
        return _row(
            base,
            sid,
            priority="skip",
            status="awaiting_review",
            reasons=["has_unreviewed_frw_candidate"],
            still=still,
            candidates=candidates,
            command=f'aifilm still-challenge promote --root "{base}" --shot-id {sid}',
        )
    already_promoted_frw = bool(candidates) and _promoted_after(base, sid, candidates)

    if not has_still:
        # S0 only if cast-like source exists elsewhere
        cast_src = _cast_fallback_source(base, shot)
        if cast_src:
            return _row(
                base,
                sid,
                priority="S0",
                status="pending",
                reasons=["missing_still_use_cast_anchor"],
                still=None,
                source=cast_src,
                candidates=candidates,
                intent=intent,
                shot=shot,
            )
        return _row(
            base,
            sid,
            priority="skip",
            status="blocked_no_source",
            reasons=["no_still_and_no_cast_source"],
            still=None,
            candidates=candidates,
        )

    soft = _soft_still_heuristic(shot, intent)
    floor = 18.0
    if intent and intent.get("motion_tier") in {"high", "meat"}:
        floor = 20.0
    below = mean is not None and mean < floor

    if has_take and below and soft and not already_promoted_frw:
        return _row(
            base,
            sid,
            priority="S1",
            status="pending",
            reasons=["take_below_floor", "soft_or_high_energy_still"],
            still=still,
            candidates=candidates,
            mean=mean,
            floor=floor,
            intent=intent,
            shot=shot,
        )
    if already_promoted_frw and not (has_take and below):
        return _row(
            base,
            sid,
            priority="done",
            status="promoted_ok",
            reasons=["frw_candidate_already_promoted"],
            still=still,
            candidates=candidates,
            mean=mean,
        )
    if soft and (
        str((intent or {}).get("content_class") or "").lower()
        in {"act", "climax", "bare", "restricted"}
        or str(shot.get("h3_mode") or "").lower() == "r2v"
        or str(shot.get("force_r2v") or "").lower() in {"1", "true", "yes"}
    ):
        return _row(
            base,
            sid,
            priority="S2",
            status="pending",
            reasons=["r2v_or_restricted_ref_upgrade"],
            still=still,
            candidates=candidates,
            mean=mean,
            floor=floor,
            intent=intent,
            shot=shot,
        )
    if has_still and has_take and soft:
        return _row(
            base,
            sid,
            priority="S3",
            status="pending",
            reasons=["soft_fill_still_challenge"],
            still=still,
            candidates=candidates,
            mean=mean,
            floor=floor,
            intent=intent,
            shot=shot,
        )
    if has_still and not soft:
        return _row(
            base,
            sid,
            priority="done",
            status="skip_not_needed",
            reasons=["still_ok_no_challenge_signal"],
            still=still,
            candidates=candidates,
            mean=mean,
        )
    return _row(
        base,
        sid,
        priority="S3",
        status="pending",
        reasons=["optional_still_improve"],
        still=still,
        candidates=candidates,
        mean=mean,
        intent=intent,
        shot=shot,
    )


def _promoted_after(root: Path, shot_id: str, candidates: list[dict[str, Any]]) -> bool:
    """True if approved still sha matches a frw candidate (already promoted)."""
    still = _approved_still(root, shot_id)
    if still is None or not still.is_file():
        return False
    still_sha = _sha256(still)
    return any(c.get("sha256") == still_sha for c in candidates)


def _cast_fallback_source(root: Path, shot: dict[str, Any]) -> Path | None:
    for p in (
        root / "cast" / "master.png",
        root / "characters" / "hero.png",
        root / "lookbook" / "hero.png",
    ):
        if p.is_file():
            return p
    cast_dir = root / "cast"
    if cast_dir.is_dir():
        for p in sorted(cast_dir.glob("*.png")):
            return p
    return None


def _row(
    base: Path,
    sid: str,
    *,
    priority: str,
    status: str,
    reasons: list[str],
    still: Path | None,
    candidates: list[dict[str, Any]],
    source: Path | None = None,
    mean: float | None = None,
    floor: float | None = None,
    intent: dict[str, Any] | None = None,
    shot: dict[str, Any] | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    src = source or still
    prompt = build_static_i2i_prompt(shot or {"id": sid}, intent) if status == "pending" else None
    cmd = command
    if cmd is None and status == "pending" and src is not None:
        cmd = (
            f'aifilm still-challenge run --root "{base}" --shot-id {sid} '
            f'--source "{src}" --execute --max-submits 1'
        )
    return {
        "shot_id": sid,
        "priority": priority,
        "priority_rank": PRIORITY_RANK.get(priority, 99),
        "status": status,
        "reasons": reasons,
        "has_still": still is not None,
        "still_path": str(still) if still else None,
        "source_path": str(src) if src else None,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "best_mean": mean,
        "floor": floor,
        "prompt": prompt,
        "command": cmd,
        "does_not_use_gpu": True,
    }


def build_still_challenge_queue(
    root: Path | str,
    *,
    include_done: bool = False,
) -> dict[str, Any]:
    base = _root(root)
    spec = _load_spec(base)
    rows: list[dict[str, Any]] = []
    for shot in _iter_shots(spec):
        intent = None
        try:
            from production_router import build_shot_intent

            intent = build_shot_intent(spec, shot)
        except Exception:  # noqa: BLE001
            intent = {}
        row = classify_still_challenge_shot(base, shot, intent=intent)
        if (
            not include_done
            and row.get("priority") in {"done", "skip"}
            and row.get("status") not in {"awaiting_review"}
        ):
            # keep awaiting_review visible
            if row.get("status") != "awaiting_review":
                continue
        rows.append(row)
    rows.sort(key=lambda r: (int(r.get("priority_rank") or 99), str(r.get("shot_id") or "")))
    pending = [r for r in rows if r.get("status") == "pending"]
    rate = frw_rate_snapshot()
    return {
        "schema_version": 1,
        "kind": "ai-film-still-challenge-queue",
        "ok": True,
        "root": str(base),
        "pending_count": len(pending),
        "rows": rows,
        "next": pending[0] if pending else None,
        "rate": rate,
        "image_min_interval_s": IMAGE_MIN_INTERVAL_S,
        "note": "FRW i2i still challenge; unit=1; ≥30s; no silent promote; no 5090 steal",
    }


def next_still_challenge_job(root: Path | str) -> dict[str, Any]:
    q = build_still_challenge_queue(root, include_done=False)
    nxt = q.get("next")
    rate = q.get("rate") or frw_rate_snapshot()
    wait_s = float(rate.get("image_wait_s") or 0.0)
    note = "Queue empty" if not nxt else "Run command when image_ready (or wait image_wait_s)"
    if nxt and not rate.get("image_ready"):
        note = f"Rate window: wait {wait_s}s then run still-challenge unit"
    return {
        "schema_version": 1,
        "kind": "ai-film-still-challenge-next",
        "ok": True,
        "root": q.get("root"),
        "pending_count": q.get("pending_count"),
        "next": nxt,
        "command": (nxt or {}).get("command") if isinstance(nxt, dict) else None,
        "rate": rate,
        "image_ready": rate.get("image_ready"),
        "image_wait_s": wait_s,
        "max_submits_default": 1,
        "note": note,
    }


def _frw_capability(root: Path) -> str:
    receipt = read_json(root / "receipts" / "frw-key-capability.json")
    try:
        from frw_canary import frw_i2i_capability

        return frw_i2i_capability(receipt if isinstance(receipt, dict) else None)
    except Exception:  # noqa: BLE001
        return "untested"


def run_still_challenge(
    root: Path | str,
    shot_id: str,
    *,
    source: Path | str | None = None,
    execute: bool = False,
    max_submits: int = 1,
    model: str = DEFAULT_MODEL,
    seed: int = 20260804,
    prompt: str | None = None,
    width: int = 720,
    height: int = 1280,
    frw_runner: Callable[[list[str]], dict[str, Any]] | None = None,
    skip_capability_gate: bool = False,
) -> dict[str, Any]:
    """Plan or execute one FRW img2image still unit (default max_submits=1)."""
    base = _root(root)
    spec = _load_spec(base)
    shot = next((s for s in _iter_shots(spec) if str(s.get("id")) == shot_id), None)
    if shot is None:
        raise StillChallengeError(f"shot not found: {shot_id}")
    if _wants_continue(shot):
        raise StillChallengeError("continue chain stills skip FRW i2i (use endframe handoff)")
    if _is_poison(base, shot_id, shot):
        raise StillChallengeError("poison still blocked from i2i challenge")

    src_path = Path(source).expanduser().resolve() if source else _approved_still(base, shot_id)
    if src_path is None or not src_path.is_file():
        cast = _cast_fallback_source(base, shot)
        src_path = cast
    if src_path is None or not Path(src_path).is_file():
        raise StillChallengeError(f"no source still for {shot_id}")
    src_path = Path(src_path)

    intent = {}
    try:
        from production_router import build_shot_intent

        intent = build_shot_intent(spec, shot)
    except Exception:  # noqa: BLE001
        pass
    i2i_prompt = prompt or build_static_i2i_prompt(shot, intent)
    rate = frw_rate_snapshot()
    cap = "available" if skip_capability_gate else _frw_capability(base)
    budget = SubmitBudget(max(1, int(max_submits)))

    plan = {
        "schema_version": 1,
        "kind": "ai-film-still-challenge-run",
        "ok": True,
        "shot_id": shot_id,
        "execute": bool(execute),
        "source_path": str(src_path),
        "source_sha256": _sha256(src_path),
        "prompt": i2i_prompt,
        "model": model,
        "steps": IMG2IMAGE_STEPS,
        "cfg_scale": IMG2IMAGE_CFG,
        "width": width,
        "height": height,
        "seed": seed,
        "max_submits": budget.max_submits,
        "rate": rate,
        "frw_i2i_capability": cap,
        "image_wait_s": rate.get("image_wait_s"),
        "does_not_use_gpu": True,
    }

    if not execute:
        plan["status"] = "dry_run"
        plan["note"] = "Pass --execute to submit FRW img2image (pays credits; ≥30s gap)"
        plan["command"] = (
            f'aifilm still-challenge run --root "{base}" --shot-id {shot_id} '
            f'--source "{src_path}" --execute --max-submits 1'
        )
        _write_receipt(base, shot_id, plan)
        return plan

    if cap not in {"available"} and not skip_capability_gate:
        plan["ok"] = False
        plan["status"] = "blocked_capability"
        plan["error"] = f'frw_i2i_capability={cap}; run: aifilm frw canary --full --root "{base}"'
        _write_receipt(base, shot_id, plan)
        return plan

    budget.take()
    # Rate wait is enforced inside frw_dispatch on img2image submit (shared 30s).
    # Peek-only here so plan receipts show ETA without double-stamping.
    plan["rate_waited_s"] = 0.0
    plan["image_wait_before_s"] = float(peek_frw_rate_wait("image"))

    runner = frw_runner or _default_frw_runner
    # Upload (not rate-classified as image submit)
    upload_payload = runner(
        [
            "upload",
            "--file-path",
            str(src_path),
            "--category",
            "image",
        ]
    )
    img_url = _extract_url(upload_payload)
    plan["upload_ok"] = bool(img_url)
    if not img_url:
        plan["ok"] = False
        plan["status"] = "upload_failed"
        plan["error"] = "FRW upload did not return public image URL"
        plan["upload_raw_keys"] = (
            list(upload_payload.keys()) if isinstance(upload_payload, dict) else []
        )
        _write_receipt(base, shot_id, plan)
        return plan

    # img2image (rate already stamped above before upload+submit pair — acceptable;
    # wait was taken once per unit)
    i2i_payload = runner(
        [
            "img2image",
            "--img-url",
            img_url,
            "--prompt",
            i2i_prompt,
            "--model",
            model,
            "--width",
            str(width),
            "--height",
            str(height),
            "--steps",
            str(IMG2IMAGE_STEPS),
            "--cfg-scale",
            str(IMG2IMAGE_CFG),
        ]
    )
    out_url = _extract_url(i2i_payload)
    takes_dir = base / "takes" / shot_id
    takes_dir.mkdir(parents=True, exist_ok=True)
    out_path = takes_dir / f"still_frw_{seed}.png"
    # Prefer local_path for injected/mock runners (tests); else download FRW URL.
    if isinstance(i2i_payload, dict) and i2i_payload.get("local_path"):
        shutil.copy2(str(i2i_payload["local_path"]), out_path)
    elif out_url:
        _download(out_url, out_path)
    else:
        plan["ok"] = False
        plan["status"] = "i2i_failed"
        plan["error"] = "FRW img2image response missing image URL"
        _write_receipt(base, shot_id, plan)
        return plan

    plan["status"] = "candidate"
    plan["candidate_path"] = str(out_path)
    plan["candidate_sha256"] = _sha256(out_path) if out_path.is_file() else None
    plan["promote_command"] = (
        f'aifilm still-challenge promote --root "{base}" --shot-id {shot_id} '
        f'--source "{out_path}" --identity-approved --anatomy-safe '
        f'--review-note "frw-i2i challenge; id-ok"'
    )
    plan["h3_next"] = (
        f'aifilm h3 run --root "{base}" --shot-id {shot_id} --mode i2v --register --stage pilot'
    )
    _write_receipt(base, shot_id, plan)
    return plan


def _extract_url(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    try:
        from frw_upload import extract_upload_url

        return extract_upload_url(payload)
    except Exception:  # noqa: BLE001
        pass
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("image_url", "url", "file_url"):
        val = payload.get(key) or (data.get(key) if isinstance(data, dict) else None)
        if val and str(val).startswith("http"):
            return str(val)
    return None


def _download(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 — FRW CDN
        dest.write_bytes(resp.read())


def _default_frw_runner(args: list[str]) -> dict[str, Any]:
    launcher = Path(__file__).resolve().parent / "frw_dispatch.py"
    # Rate limit already applied for img2image in run_still_challenge;
    # frw_dispatch will also wait — second wait is near-zero if same second.
    env = os.environ.copy()
    # img2image poll can exceed default frw_dispatch 60s CLI timeout
    env.setdefault("FRW_DISPATCH_TIMEOUT", "600")
    proc = subprocess.run(
        [sys.executable, str(launcher), *args],
        capture_output=True,
        text=True,
        timeout=int(env.get("FRW_DISPATCH_TIMEOUT") or "600") + 30,
        check=False,
        env=env,
    )
    payload: dict[str, Any] = {}
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                payload = parsed
                break
        except json.JSONDecodeError:
            continue
    if proc.returncode not in (0, 3) and not payload:
        raise StillChallengeError(
            (proc.stderr or proc.stdout or f"frw failed rc={proc.returncode}")[:400]
        )
    payload.setdefault("returncode", proc.returncode)
    return payload


def promote_still_challenge(
    root: Path | str,
    shot_id: str,
    *,
    source: Path | str | None = None,
    identity_approved: bool = False,
    anatomy_safe: bool = False,
    review_note: str = "",
    status: str = "approved",
) -> dict[str, Any]:
    """Promote a FRW candidate still into stills/ + manifest (human gates required)."""
    base = _root(root)
    if status == "approved":
        if not identity_approved:
            raise StillChallengeError("promote approved requires --identity-approved")
        if not anatomy_safe:
            raise StillChallengeError("promote approved requires --anatomy-safe")
        if not str(review_note or "").strip():
            raise StillChallengeError("promote approved requires --review-note")

    cand = Path(source).expanduser().resolve() if source else None
    if cand is None:
        cands = list_candidates(base, shot_id)
        if not cands:
            raise StillChallengeError(f"no still_frw candidate for {shot_id}")
        cand = Path(str(cands[-1]["path"]))
    if not cand.is_file():
        raise StillChallengeError(f"candidate missing: {cand}")

    # Geometry gate (reuse media_qa when available)
    try:
        from media_qa import analyze_still_geometry, lint_still_not_character_sheet

        geo = analyze_still_geometry(cand, aspect_ratio="9:16")
        if status == "approved" and not geo.get("ok"):
            raise StillChallengeError(
                "geometry gate failed: " + "; ".join(geo.get("errors") or ["unknown"])
            )
        sheet = lint_still_not_character_sheet(cand)
        if status == "approved" and not sheet.get("ok"):
            raise StillChallengeError(
                "character-sheet gate failed: " + "; ".join(sheet.get("errors") or [])
            )
    except StillChallengeError:
        raise
    except Exception:  # noqa: BLE001 — optional gate modules
        geo = {"ok": True, "skipped": True}

    dest_dir = base / "stills"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{shot_id}.png"
    archive_dir = dest_dir / "_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = None
    if dest.is_file():
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        archived = archive_dir / f"{shot_id}_{ts}.png"
        shutil.copy2(dest, archived)

    shutil.copy2(cand, dest)
    # Update manifest stills entry lightly
    man_path = base / "manifest.json"
    man = read_json(man_path) if man_path.is_file() else {}
    if not isinstance(man, dict):
        man = {}
    stills = man.setdefault("stills", {})
    if not isinstance(stills, dict):
        stills = {}
        man["stills"] = stills
    stills[shot_id] = {
        "shot_id": shot_id,
        "path": _rel_or_abs(base, dest),
        "status": status,
        "provider": "frw_i2i",
        "source_endpoint": "frw_img2image",
        "sha256": _sha256(dest),
        "promoted_from": str(cand),
        "review_note": review_note,
        "identity_approved": bool(identity_approved),
        "anatomy_safe": bool(anatomy_safe),
        "updated_at": utc_now(),
    }
    write_json(man_path, man)

    report = {
        "schema_version": 1,
        "kind": "ai-film-still-challenge-promote",
        "ok": True,
        "shot_id": shot_id,
        "status": status,
        "still_path": str(dest),
        "candidate_path": str(cand),
        "archived_previous": str(archived) if archived else None,
        "geometry": geo,
        "h3_command": (
            f'aifilm h3 run --root "{base}" --shot-id {shot_id} --mode i2v --register --stage pilot'
        ),
        "note": "Still promoted; re-run I2V/R2V with new material",
    }
    _write_receipt(base, shot_id, report, suffix="promote")
    return report


def _rel_or_abs(base: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _write_receipt(
    root: Path,
    shot_id: str,
    payload: dict[str, Any],
    *,
    suffix: str = "run",
) -> Path:
    d = root / "receipts" / "still-challenge"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{shot_id}_{suffix}.json"
    write_json(path, payload)
    payload["receipt_path"] = str(path)
    return path


def still_challenge_hint_for_fill_idle(
    root: Path | str,
    fill_idle_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """If S1-class still challenge is better than blind R2V, surface a hint."""
    if not isinstance(fill_idle_row, dict):
        return None
    sid = str(fill_idle_row.get("shot_id") or "")
    if not sid:
        return None
    # Only hint when take is weak or P1/P2 and still is soft
    if fill_idle_row.get("priority") not in {"P1", "P2"} and not fill_idle_row.get("below_floor"):
        return None
    base = _root(root)
    spec = _load_spec(base)
    shot = next((s for s in _iter_shots(spec) if str(s.get("id")) == sid), None)
    if shot is None:
        return None
    row = classify_still_challenge_shot(base, shot)
    if row.get("status") != "pending" or row.get("priority") not in {"S0", "S1", "S2"}:
        return None
    return {
        "prefer_still_challenge_first": True,
        "still_challenge": row,
        "command": row.get("command"),
        "reason": "weak take often needs better still before more I2V/R2V",
    }
