#!/usr/bin/env python3
"""Per-shot generation evidence for Material Fidelity feedback (M4).

Writes ``receipts/shot-evidence/<shot_id>.json`` after measure/register.
``prior_evidence_lines`` feeds GenerationRequest so next gen learns from weak takes.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json

EVIDENCE_DIR = Path("receipts") / "shot-evidence"


class ShotEvidenceError(ValueError):
    pass


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def evidence_path(root: Path | str, shot_id: str) -> Path:
    return _root(root) / EVIDENCE_DIR / f"{shot_id}.json"


def load_shot_evidence(root: Path | str, shot_id: str) -> dict[str, Any] | None:
    data = read_json(evidence_path(root, shot_id))
    return data if isinstance(data, dict) else None


def _infer_shot_id_from_video(root: Path, video: Path) -> str | None:
    """takes/<shot_id>/… or clips/<shot_id>.mp4"""
    try:
        rel = video.resolve().relative_to(root.resolve())
    except ValueError:
        rel = Path(video.name)
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "takes":
        return str(parts[1])
    if len(parts) >= 1 and parts[0] == "clips":
        stem = Path(parts[-1]).stem
        # strip common suffixes
        for suf in ("_h3", "_grok", "_i2v", "_r2v", "_flf"):
            if stem.endswith(suf):
                stem = stem[: -len(suf)]
        return stem or None
    return None


def write_shot_evidence(
    root: Path | str,
    shot_id: str,
    *,
    mean: float | None = None,
    video_path: Path | str | None = None,
    face_score: float | None = None,
    wardrobe_obs: str | None = None,
    poison: bool | None = None,
    identity_ok: bool | None = None,
    motion_ok: bool | None = None,
    source: str = "manual",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge evidence for one shot (latest measure wins for mean)."""
    base = _root(root)
    sid = str(shot_id).strip()
    if not sid:
        raise ShotEvidenceError("shot_id required")
    prev = load_shot_evidence(base, sid) or {}
    history = list(prev.get("history") or []) if isinstance(prev.get("history"), list) else []
    entry: dict[str, Any] = {
        "at": utc_now(),
        "source": source,
    }
    if mean is not None:
        entry["mean"] = float(mean)
    if video_path is not None:
        vp = Path(video_path).expanduser().resolve()
        entry["video_path"] = str(vp)
        if vp.is_file():
            with suppress(OSError):
                entry["video_sha256"] = sha256_file(vp)
    if face_score is not None:
        entry["face_score"] = float(face_score)
    if wardrobe_obs:
        entry["wardrobe_obs"] = str(wardrobe_obs)
    if poison is not None:
        entry["poison"] = bool(poison)
    if identity_ok is not None:
        entry["identity_ok"] = bool(identity_ok)
    if motion_ok is not None:
        entry["motion_ok"] = bool(motion_ok)
    if extra:
        entry.update({k: v for k, v in extra.items() if k not in entry})

    history.append(entry)
    history = history[-12:]  # keep last dozen

    # Aggregate current best
    means = [float(h["mean"]) for h in history if h.get("mean") is not None]
    best_mean = max(means) if means else None
    last = history[-1] if history else entry
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "shot-evidence",
        "shot_id": sid,
        "updated_at": utc_now(),
        "mean": last.get("mean") if last.get("mean") is not None else best_mean,
        "best_mean": best_mean,
        "face_score": last.get("face_score"),
        "wardrobe_obs": last.get("wardrobe_obs"),
        "poison": last.get("poison"),
        "identity_ok": last.get("identity_ok"),
        "motion_ok": last.get("motion_ok"),
        "video_path": last.get("video_path"),
        "video_sha256": last.get("video_sha256"),
        "history": history,
        "weak_motion": bool(
            best_mean is not None and best_mean < 18.0 and (last.get("identity_ok") is not False)
        ),
        "suggest_still_challenge": False,
    }
    # mean red + identity not failed → suggest still-challenge
    if payload["weak_motion"] and payload.get("poison") is not True:
        if payload.get("identity_ok") is not False:
            payload["suggest_still_challenge"] = True
    write_json(evidence_path(base, sid), payload)
    return payload


def write_shot_evidence_from_video(
    root: Path | str,
    video: Path | str,
    *,
    mean: float | None = None,
    shot_id: str | None = None,
    source: str = "mean_sidecar",
    **kwargs: Any,
) -> dict[str, Any] | None:
    base = _root(root)
    vp = Path(video).expanduser().resolve()
    sid = str(shot_id or "").strip() or _infer_shot_id_from_video(base, vp)
    if not sid:
        return None
    return write_shot_evidence(
        base,
        sid,
        mean=mean,
        video_path=vp,
        source=source,
        **kwargs,
    )


def prior_evidence_lines(
    root: Path | str,
    shot_id: str,
    *,
    max_lines: int = 3,
) -> list[str]:
    """1–3 budgeted lines for GenerationRequest prepend."""
    data = load_shot_evidence(root, shot_id)
    if not isinstance(data, dict):
        return []
    lines: list[str] = []
    mean = data.get("mean")
    best = data.get("best_mean")
    if mean is not None:
        lines.append(
            f"PRIOR_EVIDENCE: last mean_absdiff={float(mean):.1f}"
            + (f" best={float(best):.1f}" if best is not None else "")
            + (
                " — WEAK motion; increase visible body/camera change per second"
                if float(mean) < 18
                else ""
            )
        )
    if data.get("suggest_still_challenge"):
        lines.append(
            "PRIOR_EVIDENCE: prefer better still (still-challenge i2i) before re-burning same first frame"
        )
    if data.get("poison") is True:
        lines.append("PRIOR_EVIDENCE: poison anatomy on prior take — do not reuse that still/path")
    if data.get("wardrobe_obs"):
        lines.append(f"PRIOR_EVIDENCE: wardrobe_obs={data['wardrobe_obs']}")
    if data.get("identity_ok") is False:
        lines.append("PRIOR_EVIDENCE: identity drift — lock face from approved still/state photo")
    return lines[: max(1, int(max_lines))]


def list_still_challenge_suggestions(root: Path | str) -> dict[str, Any]:
    """Shots where mean was weak but identity not failed → still-challenge candidates."""
    base = _root(root)
    edir = base / EVIDENCE_DIR
    rows: list[dict[str, Any]] = []
    if not edir.is_dir():
        return {"ok": True, "suggestions": [], "count": 0}
    for path in sorted(edir.glob("*.json")):
        data = read_json(path) or {}
        if not isinstance(data, dict):
            continue
        if data.get("suggest_still_challenge"):
            rows.append(
                {
                    "shot_id": data.get("shot_id") or path.stem,
                    "mean": data.get("mean"),
                    "best_mean": data.get("best_mean"),
                    "cmd": (
                        f'aifilm still-challenge plan --root "{base}" '
                        f'&& aifilm still-challenge run --root "{base}" '
                        f"--shot-id {data.get('shot_id') or path.stem} --execute --max-submits 1"
                    ),
                }
            )
    return {
        "ok": True,
        "count": len(rows),
        "suggestions": rows,
        "next_cmd": rows[0]["cmd"] if rows else None,
    }
