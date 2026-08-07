#!/usr/bin/env python3
"""TTS duration probe/rehearsal before bulk media-queue or final.

Sediment from ai-film-codex: measure real VO seconds into a receipt so timing
gates can use measured values instead of only len(nar)/4 estimates.

Supports:
  - synthesize path (edge/etc via tts_backend) when network/backends available
  - register path: bind existing audio files without network (unit-testable)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from content_channels import resolve_content_channels
from film_spec import estimate_nar_vo_sec, validate_film_spec
from media_duration import MediaDurationError, probe_duration_sec
from util import read_json, utc_now, write_json
from util import sha256_file as _sha256

SCHEMA_VERSION = 1
KIND = "ai-film-tts-rehearsal"
RECEIPT_REL = "receipts/tts-rehearsal.json"
AUDIO_DIR_REL = "receipts/tts-rehearsal-audio"


class TTSRehearsalError(RuntimeError):
    pass


def rehearsal_receipt_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / RECEIPT_REL


def load_rehearsal_receipt(root: Path) -> dict[str, Any] | None:
    path = rehearsal_receipt_path(root)
    if not path.is_file():
        return None
    from util import soft_json

    data = soft_json(path)
    return data or None


def measured_vo_by_shot(root: Path) -> dict[str, float]:
    """Map shot_id → measured_duration_sec from rehearsal receipt when present."""
    rec = load_rehearsal_receipt(root)
    if not rec or not rec.get("ok"):
        return {}
    out: dict[str, float] = {}
    for item in rec.get("shots") or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("shot_id") or "").strip()
        if not sid:
            continue
        try:
            dur = float(item.get("measured_duration_sec"))
        except (TypeError, ValueError):
            continue
        if dur > 0:
            out[sid] = dur
    return out


def _load_spec(root: Path, spec_path: Path | None) -> dict[str, Any]:
    path = Path(spec_path).expanduser().resolve() if spec_path else (root / "film-spec.json")
    if not path.is_file():
        raise TTSRehearsalError(f"film-spec missing: {path}")
    from util import require_json_as

    try:
        raw = require_json_as(path, TTSRehearsalError)
    except TTSRehearsalError:
        raise
    if not isinstance(raw, dict):
        raise TTSRehearsalError("film-spec must be a JSON object")
    return raw


def _voice_script_for_shot(shot: dict[str, Any], *, fallback_voice: str) -> dict[str, str]:
    """Resolve rehearsal speech from the executable voice cue, never captions."""
    for cue in shot.get("audio_cues") or []:
        if not isinstance(cue, dict) or cue.get("kind") != "voice":
            continue
        text = str(cue.get("spoken_text") or "").strip()
        if not text:
            continue
        language = str(cue.get("language") or "zh").strip().lower()
        if language in {"ja", "jp", "japanese"}:
            language = "zh"  # Japanese retired; Chinese-only product path
        default_voice = fallback_voice or "zh-CN-XiaoxiaoNeural"
        return {
            "text": text,
            "text_kind": str(cue.get("line_type") or "voice").strip().lower(),
            "language": language if language else "zh",
            "voice": str(cue.get("voice") or default_voice).strip() or default_voice,
        }
    voice_channel = resolve_content_channels(shot)["voice"]
    return {
        "text": str(voice_channel["text"] or "").strip(),
        "text_kind": str(voice_channel["kind"] or "voice").strip().lower(),
        "language": "",
        "voice": fallback_voice,
    }


def register_measured_durations(
    root: Path,
    measurements: list[dict[str, Any]],
    *,
    source: str = "register",
    backend: str | None = None,
) -> dict[str, Any]:
    """Write rehearsal receipt from pre-measured shot audio (no TTS network).

    Each measurement: {shot_id, path} or {shot_id, measured_duration_sec[, path]}
    Paths are probed with fail-loud media_duration when present.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise TTSRehearsalError(f"film root missing: {root}")

    shots_out: list[dict[str, Any]] = []
    for item in measurements:
        if not isinstance(item, dict):
            raise TTSRehearsalError("each measurement must be an object")
        sid = str(item.get("shot_id") or "").strip()
        if not sid:
            raise TTSRehearsalError("measurement missing shot_id")
        path_raw = item.get("path")
        dur: float | None = None
        path_str: str | None = None
        audio_sha256: str | None = None
        if path_raw:
            p = Path(str(path_raw)).expanduser()
            if not p.is_file():
                raise TTSRehearsalError(f"{sid}: audio path missing: {p}")
            try:
                dur = probe_duration_sec(p, label=f"tts-rehearsal:{sid}")
            except MediaDurationError as exc:
                raise TTSRehearsalError(str(exc)) from exc
            path_str = str(p.resolve())
            audio_sha256 = _sha256(p)
        if dur is None and item.get("measured_duration_sec") is not None:
            try:
                dur = float(item["measured_duration_sec"])
            except (TypeError, ValueError) as exc:
                raise TTSRehearsalError(f"{sid}: measured_duration_sec must be a number") from exc
        if dur is None or dur <= 0:
            raise TTSRehearsalError(f"{sid}: need path (ffprobe) or positive measured_duration_sec")
        est = item.get("est_vo_sec")
        try:
            est_f = float(est) if est is not None else None
        except (TypeError, ValueError):
            est_f = None
        plate = item.get("duration_sec")
        try:
            plate_f = float(plate) if plate is not None else None
        except (TypeError, ValueError):
            plate_f = None
        over = None
        if plate_f is not None:
            over = dur > (plate_f + 0.5)
        shots_out.append(
            {
                "shot_id": sid,
                "measured_duration_sec": round(float(dur), 3),
                "est_vo_sec": est_f,
                "duration_sec": plate_f,
                "over_plate": over,
                "path": path_str,
                "audio_sha256": audio_sha256,
                "nar": item.get("nar"),
                "text_kind": item.get("text_kind"),
                "text": item.get("text"),
                "language": item.get("language"),
                "voice": item.get("voice"),
            }
        )

    over_ids = [s["shot_id"] for s in shots_out if s.get("over_plate") is True]
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "ok": True,
        "source": source,
        "backend": backend,
        "created_at": utc_now(),
        "root": str(root),
        "shot_count": len(shots_out),
        "shots": shots_out,
        "over_plate_shots": over_ids,
        "evidence_class": "executed_audio",
        "note": (
            "Measured VO durations for timing gates. "
            "Intent (film-spec est_vo_sec) ≠ this executed probe. "
            "Does not replace pilot/human review."
        ),
    }
    out_path = rehearsal_receipt_path(root)
    write_json(out_path, receipt)
    _lock_dialogue_durations_to_rehearsal(root, receipt)
    # Keep the dialogue package synchronized with the actual rehearsal media.
    # Absence of a dialogue graph is normal for legacy narrator projects.
    graph = read_json(root / "drama-graph.json")
    spec = read_json(root / "film-spec.json")
    if isinstance(graph, dict) and isinstance(spec, dict) and graph.get("dialogue_ledger"):
        from dialogue_scene_package import build_dialogue_scene_package

        write_json(
            root / "dialogue-scene-package.json",
            build_dialogue_scene_package(graph, spec, receipt),
        )
    receipt["receipt_path"] = str(out_path)
    return receipt


def _lock_dialogue_durations_to_rehearsal(root: Path, receipt: dict[str, Any]) -> None:
    """Replace estimated dialogue plate lengths with measured rehearsal timing.

    This is intentionally limited to dialogue voice cues.  It leaves narration
    and visual-only coverage untouched, while making any later I2V plan derive
    from real speech plus explicit pre/post pause handles.
    """
    spec_path = root / "film-spec.json"
    spec = read_json(spec_path)
    if not isinstance(spec, dict) or spec.get("vo_mode") != "dialogue_drama":
        return
    measured: dict[str, dict[str, Any]] = {}
    for item in receipt.get("shots") or []:
        if not isinstance(item, dict):
            continue
        try:
            valid = float(item.get("measured_duration_sec") or 0) > 0
        except (TypeError, ValueError):
            valid = False
        if valid:
            measured[str(item.get("shot_id") or "")] = item
    changed = False
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            sid = str(shot.get("id") or "")
            item = measured.get(sid)
            cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
            dialogue = next(
                (
                    cue
                    for cue in cues
                    if isinstance(cue, dict)
                    and cue.get("kind") == "voice"
                    and cue.get("line_type") == "dialogue"
                ),
                None,
            )
            if not item or not isinstance(dialogue, dict):
                continue
            measured_sec = round(float(item["measured_duration_sec"]), 3)
            pre = max(0.0, float(dialogue.get("pause_before_sec") or 0.0))
            post = max(0.0, float(dialogue.get("pause_after_sec") or 0.0))
            dialogue["start_offset_sec"] = round(pre, 3)
            dialogue["duration_sec"] = measured_sec
            shot["duration_sec"] = round(pre + measured_sec + post, 3)
            shot["tts_timing_lock"] = {
                "status": "locked",
                "audio_sha256": item.get("audio_sha256"),
                "speech_duration_sec": measured_sec,
                "pause_before_sec": round(pre, 3),
                "pause_after_sec": round(post, 3),
            }
            _reflow_dialogue_broll(shot)
            changed = True
    if changed:
        write_json(spec_path, spec)


def _reflow_dialogue_broll(shot: dict[str, Any]) -> None:
    """Keep optional dialogue B-roll inside real TTS timing handles.

    A short spoken line may no longer have enough usable interior after its
    measured duration replaces an estimate.  In that case the optional insert
    is removed; the beat's mandatory reaction/action coverage remains a
    separate shot and therefore is not fabricated as a rushed 0.1s cut.
    """
    entries = shot.get("dialogue_broll")
    if not isinstance(entries, list) or not entries:
        return
    try:
        duration = float(shot.get("duration_sec") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    # Keep a small numerical margin inside the validator's inclusive-looking
    # 0.8s boundary; decimal JSON floats otherwise can land just outside it.
    edge_handle = 0.805
    interior = duration - 2 * edge_handle
    max_coverage = duration * 0.4 - 0.005
    if interior < 0.25 or max_coverage < 0.25:
        shot.pop("dialogue_broll", None)
        shot["dialogue_broll_reflow"] = {"status": "removed_short_tts", "duration_sec": duration}
        return
    entry = entries[0]
    if not isinstance(entry, dict):
        shot.pop("dialogue_broll", None)
        return
    try:
        requested = float(entry.get("end_sec")) - float(entry.get("start_sec"))
    except (TypeError, ValueError):
        requested = 0.0
    coverage = min(max(requested, 0.25), interior, max_coverage)
    start = edge_handle + max(0.0, (interior - coverage) / 2)
    entry["start_sec"] = round(start, 3)
    entry["end_sec"] = round(start + coverage, 3)
    shot["dialogue_broll_reflow"] = {
        "status": "reflowed_to_measured_tts",
        "duration_sec": duration,
    }


def run_rehearsal(
    root: Path,
    *,
    spec_path: Path | None = None,
    backend: str | None = None,
    voice: str = "zh-CN-XiaoxiaoNeural",
    register_map: dict[str, Path] | None = None,
    synthesize: bool = True,
) -> dict[str, Any]:
    """Run TTS rehearsal for all shots in film-spec.

    If register_map is provided (shot_id → audio path), skip TTS and probe those files.
    If synthesize is False and no register_map, raise.
    """
    root = Path(root).expanduser().resolve()
    spec = _load_spec(root, spec_path)
    try:
        shots = validate_film_spec(spec, assign_missing_ids=False)
    except Exception as exc:
        raise TTSRehearsalError(f"film-spec invalid: {exc}") from exc

    # Coverage, reaction and silence shots deliberately have no spoken track.
    # They must not turn a dialogue-first rehearsal into a failed narrator job.
    shots = [shot for shot in shots if _voice_script_for_shot(shot, fallback_voice=voice)["text"]]
    if not shots:
        raise TTSRehearsalError("film-spec has no spoken voice cues to rehearse")

    audio_dir = root / AUDIO_DIR_REL
    audio_dir.mkdir(parents=True, exist_ok=True)
    measurements: list[dict[str, Any]] = []

    used_backend = backend or str(spec.get("tts_backend") or "mimo")
    if used_backend == "auto":
        used_backend = "mimo"

    for shot in shots:
        sid = str(shot["id"])
        script = _voice_script_for_shot(shot, fallback_voice=voice)
        text_kind = script["text_kind"]
        nar = script["text"]
        cue_voice = script["voice"]
        plate = float(shot.get("duration_sec") or 6.0)
        est = float(shot.get("est_vo_sec") or estimate_nar_vo_sec(nar))
        reg_path = (register_map or {}).get(sid)
        if reg_path is not None:
            p = Path(reg_path).expanduser().resolve()
            measurements.append(
                {
                    "shot_id": sid,
                    "path": str(p),
                    "est_vo_sec": est,
                    "duration_sec": plate,
                    "nar": nar,
                    "text_kind": text_kind,
                    "text": nar,
                    "language": script["language"],
                    "voice": cue_voice,
                }
            )
            continue
        if not synthesize:
            raise TTSRehearsalError(f"{sid}: no register audio and synthesize=False")
        if not nar:
            raise TTSRehearsalError(f"{sid}: empty nar — cannot rehearse TTS")
        try:
            from tts_backend import synthesize as tts_synthesize
        except ImportError as exc:
            raise TTSRehearsalError(f"tts_backend unavailable: {exc}") from exc
        out_mp3 = audio_dir / f"{sid}.mp3"
        try:
            meta = tts_synthesize(
                nar,
                out_mp3,
                backend=used_backend,
                voice=cue_voice,
                usage_root=root,
                shot_id=sid,
            )
            used_backend = str(meta.get("backend") or used_backend)
        except Exception as exc:
            raise TTSRehearsalError(f"{sid}: TTS failed: {exc}") from exc
        measurements.append(
            {
                "shot_id": sid,
                "path": str(out_mp3),
                "est_vo_sec": est,
                "duration_sec": plate,
                "nar": nar,
                "text_kind": text_kind,
                "text": nar,
                "language": script["language"],
                "voice": cue_voice,
            }
        )

    source = "register" if register_map else "synthesize"
    return register_measured_durations(
        root,
        measurements,
        source=source,
        backend=used_backend,
    )


def effective_vo_sec(
    shot_id: str,
    nar: str = "",
    *,
    est_vo_sec: float | None = None,
    measured_by_shot: dict[str, float] | None = None,
) -> tuple[float, str]:
    """Prefer measured_duration_sec when present; else char estimate.

    Returns (seconds, source) where source is \"measured\" | \"estimate\".
    """
    sid = str(shot_id or "").strip()
    if measured_by_shot and sid in measured_by_shot:
        try:
            m = float(measured_by_shot[sid])
        except (TypeError, ValueError):
            m = 0.0
        if m > 0:
            return float(m), "measured"
    if est_vo_sec is not None:
        try:
            e = float(est_vo_sec)
            if e > 0:
                return e, "estimate"
        except (TypeError, ValueError):
            pass
    return float(estimate_nar_vo_sec(nar or "")), "estimate"


def recompute_over_plate_shots(
    shots: list[dict[str, Any]],
    measured_by_shot: dict[str, float],
    *,
    slack_sec: float | None = None,
) -> list[str]:
    """Shot ids where measured VO exceeds plate duration + slack."""
    from film_spec import DEFAULT_DURATION_SEC, VO_PACING_SLACK_SEC

    slack = VO_PACING_SLACK_SEC if slack_sec is None else float(slack_sec)
    over: list[str] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "").strip()
        if not sid or sid not in measured_by_shot:
            continue
        try:
            plate = float(shot.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            plate = float(DEFAULT_DURATION_SEC)
        try:
            m = float(measured_by_shot[sid])
        except (TypeError, ValueError):
            continue
        if m > plate + slack:
            over.append(sid)
    return over


def bind_receipt_to_spec_timing(
    root: Path,
    *,
    strict: bool = False,
    raise_on_fail: bool = False,
) -> dict[str, Any]:
    """Bind TTS rehearsal measured seconds to film-spec timing gates.

    When receipt is present:
      - measured_by_shot is preferred over len(nar)/4 estimates
      - over_plate_shots recomputed vs current film-spec duration_sec + slack
      - ok=False when any measured VO exceeds plate (always, not only strict)

    When strict=True and receipt missing → ok=False (and raise if raise_on_fail).

    Used by preflight / production_gates / final — not write-spec authoring alone.
    """
    from film_spec import DEFAULT_DURATION_SEC, VO_PACING_SLACK_SEC, estimate_nar_vo_sec

    root = Path(root).expanduser().resolve()
    rec = load_rehearsal_receipt(root)
    if not rec or rec.get("ok") is not True:
        result = {
            "ok": not strict,
            "present": False,
            "strict": strict,
            "measured": {},
            "over_plate_shots": [],
            "loop_risk_shots": [],
            "per_shot": [],
            "receipt": None,
            "evidence_class": None,
            "note": (
                f"no usable {RECEIPT_REL}; timing gates fall back to estimate_nar_vo_sec"
                + ("; strict requires rehearsal receipt" if strict else "")
            ),
        }
        if strict and raise_on_fail:
            raise TTSRehearsalError(f"strict TTS rehearsal: missing or invalid {RECEIPT_REL}")
        return result

    measured = measured_vo_by_shot(root)
    # Load shots from film-spec (best-effort validate; fall back to raw)
    shots: list[dict[str, Any]] = []
    spec_path = root / "film-spec.json"
    if spec_path.is_file():
        try:
            from util import soft_json

            raw = soft_json(spec_path)
            if isinstance(raw, dict):
                try:
                    shots = validate_film_spec(raw, assign_missing_ids=False)
                except Exception:
                    for scene in raw.get("scenes") or []:
                        if not isinstance(scene, dict):
                            continue
                        for sh in scene.get("shots") or []:
                            if isinstance(sh, dict):
                                shots.append(sh)
        except (OSError, json.JSONDecodeError):
            pass

    over = (
        recompute_over_plate_shots(shots, measured)
        if shots
        else list(rec.get("over_plate_shots") or [])
    )
    # Also honor receipt-stored over list (union)
    for sid in rec.get("over_plate_shots") or []:
        s = str(sid)
        if s and s not in over:
            over.append(s)

    from film_spec import LOOP_RISK_VO_SEC

    loop_risk: list[str] = []
    per_shot: list[dict[str, Any]] = []
    for shot in shots:
        sid = str(shot.get("id") or "")
        nar = str(shot.get("nar") or "")
        try:
            plate = float(shot.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            plate = float(DEFAULT_DURATION_SEC)
        est = float(shot.get("est_vo_sec") or estimate_nar_vo_sec(nar))
        vo, source = effective_vo_sec(sid, nar, est_vo_sec=est, measured_by_shot=measured)
        if vo > LOOP_RISK_VO_SEC and plate <= 6.5:
            loop_risk.append(sid)
        per_shot.append(
            {
                "shot_id": sid,
                "vo_sec": round(vo, 3),
                "source": source,
                "duration_sec": plate,
                "est_vo_sec": est,
                "over_plate": vo > plate + VO_PACING_SLACK_SEC,
            }
        )

    ok = rec.get("ok") is True and not over
    result = {
        "ok": ok,
        "present": True,
        "strict": strict,
        "measured": measured,
        "over_plate_shots": over,
        "loop_risk_shots": loop_risk,
        "per_shot": per_shot,
        "receipt": str(rehearsal_receipt_path(root)),
        "evidence_class": rec.get("evidence_class") or "executed_audio",
        "note": (
            "Measured VO preferred over estimate_nar_vo_sec when receipt present. "
            f"over_plate={over}; loop_risk_measured={loop_risk}"
        ),
    }
    if not ok and raise_on_fail:
        raise TTSRehearsalError(
            "TTS rehearsal timing gate failed: measured VO exceeds plate on "
            f"{over}. Shorten nar, raise duration_sec, or re-rehearse after edits."
        )
    if strict and not measured and raise_on_fail:
        raise TTSRehearsalError(
            f"strict TTS rehearsal: receipt present but no measured durations in {RECEIPT_REL}"
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TTS duration rehearsal / register")
    p.add_argument("--root", required=True)
    p.add_argument("--spec", default=None, help="Optional film-spec path")
    p.add_argument("--backend", default=None)
    p.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    p.add_argument(
        "--register-json",
        default=None,
        help="JSON list of {shot_id, path|measured_duration_sec} (no network)",
    )
    p.add_argument(
        "--no-synthesize",
        action="store_true",
        help="Only register mode; fail if --register-json omitted",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    register_map: dict[str, Path] | None = None
    if args.register_json:
        reg_path = Path(args.register_json).expanduser().resolve()
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("shots"), list):
            items = data["shots"]
        elif isinstance(data, list):
            items = data
        else:
            raise SystemExit("register-json must be a list or {shots: [...]}")
        # Prefer path-based map when paths present; else pure duration register
        if all(isinstance(x, dict) and x.get("path") for x in items):
            register_map = {str(x["shot_id"]): Path(str(x["path"])) for x in items}
            receipt = run_rehearsal(
                root,
                spec_path=Path(args.spec) if args.spec else None,
                backend=args.backend,
                voice=args.voice,
                register_map=register_map,
                synthesize=False,
            )
        else:
            receipt = register_measured_durations(
                root,
                items,
                source="register",
                backend=args.backend,
            )
    else:
        if args.no_synthesize:
            raise SystemExit("--no-synthesize requires --register-json")
        receipt = run_rehearsal(
            root,
            spec_path=Path(args.spec) if args.spec else None,
            backend=args.backend,
            voice=args.voice,
            synthesize=True,
        )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
