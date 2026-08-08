"""Unified, read-only post-production audit and evidence receipt."""

from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from delivery_artifact import DeliveryArtifactError, resolve_final_artifact
from director_review import open_reshoot_items
from media_qa import analyze_media
from security_policy import minimal_subprocess_env
from util import read_json, write_json

_SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})")


def _srt_end_times(path: Path) -> tuple[list[float], list[str]]:
    ends: list[float] = []
    errors: list[str] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "-->" not in line:
            continue
        parts = _SRT_TIME.findall(line)
        if len(parts) != 2:
            errors.append(f"invalid timecode line {line_no}")
            continue
        h, m, s, ms = (int(x) for x in parts[1])
        ends.append(h * 3600 + m * 60 + s + ms / 1000)
    return ends, errors


def _hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=minimal_subprocess_env(),
        )
        return {
            "ok": proc.returncode == 0 and bool(proc.stdout.strip()),
            "duration_sec": float(proc.stdout.strip()) if proc.stdout.strip() else None,
            "error": proc.stderr.strip() or None,
        }
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "duration_sec": None, "error": str(exc)}


def _first_file(root: Path, *relative: str) -> Path | None:
    return next((root / item for item in relative if (root / item).is_file()), None)


def audit_freshness(root: Path, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare a stored audit's bound hashes with the current film files."""
    stored = receipt or read_json(root / "receipts" / "post-audit.json") or {}
    ev = (stored.get("evidence") or {}) if isinstance(stored, dict) else {}
    manifest = read_json(root / "manifest.json") or {}
    final_record = (manifest.get("outputs") or {}).get("final_film")
    if isinstance(final_record, dict) and final_record:
        try:
            final = resolve_final_artifact(root, manifest).path
        except DeliveryArtifactError:
            final = None
    else:
        final = _first_file(
            root,
            "out/film_final.mp4",
            "out/film_hyperframes.mp4",
            "out/final.mp4",
            "final.mp4",
            "deliverables/final.mp4",
        )
    subtitle = _first_file(root, "out/final.srt", "final.srt")
    audio = _first_file(root, "audio/mix_report.json")
    timeline = _first_file(root, "timeline.json")
    review = _first_file(root, "out/final-review.json", "receipts/final-review.json")
    current = {
        "final": _hash(final),
        "subtitles": _hash(subtitle),
        "audio": _hash(audio),
        "timeline": _hash(timeline),
        "review": _hash(review),
    }
    bound = {
        "final": ((ev.get("final") or {}).get("sha256")),
        "subtitles": ((ev.get("subtitles") or {}).get("sha256")),
        "audio": ((ev.get("audio") or {}).get("sha256")),
        "timeline": ((ev.get("timeline") or {}).get("sha256")),
        "review": ((ev.get("review") or {}).get("sha256")),
    }
    mismatches = [
        key
        for key in current
        if bound.get(key) != current.get(key) and (bound.get(key) or current.get(key))
    ]
    return {"current": current, "bound": bound, "stale": bool(mismatches), "mismatches": mismatches}


def audit(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    manifest = read_json(root / "manifest.json") or {}
    record = (
        ((manifest.get("outputs") or {}).get("final_film") or {})
        if isinstance(manifest, dict)
        else {}
    )
    # Prefer registered final_film path (often out/film_final.mp4 or film_final.mp4
    # relative to root/out). Do NOT prefer stale out/final.mp4 over the registered file.
    candidates: list[Path] = []
    raw_path = str(record.get("path") or "").strip()
    if raw_path:
        p = Path(raw_path)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.append(root / p)
            candidates.append(root / "out" / p)
            # bare "film_final.mp4" → out/film_final.mp4
            if p.name == p.as_posix():
                candidates.append(root / "out" / p.name)
    candidates.extend(
        [
            root / "out" / "film_final.mp4",
            root / "out" / "film_hyperframes.mp4",
            root / "out" / "final.mp4",
            root / "final.mp4",
            root / "deliverables" / "final.mp4",
        ]
    )
    seen: set[str] = set()
    final_path = None
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            final_path = p
            break
    hard: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not final_path:
        hard.append({"code": "FINAL_MP4_MISSING", "message": "final MP4 is missing"})
    media = {"ok": False, "path": str(final_path) if final_path else None}
    if final_path:
        media = analyze_media(final_path, require_audio=True, require_motion=True)
        if not media.get("ok"):
            hard.append(
                {
                    "code": "MEDIA_QA_FAILED",
                    "message": "; ".join(media.get("errors") or ["media QA failed"]),
                }
            )
    final_hash = _hash(final_path) if final_path else None
    if final_hash and record.get("sha256") and final_hash != record.get("sha256"):
        hard.append(
            {
                "code": "FINAL_HASH_STALE",
                "message": "manifest final_film hash does not match current MP4",
            }
        )
    review = (
        read_json(root / "out" / "final-review.json")
        or read_json(root / "receipts" / "final-review.json")
        or {}
    )
    if not review.get("approved"):
        hard.append(
            {
                "code": "FINAL_REVIEW_MISSING",
                "message": "approved full-film review receipt is missing",
            }
        )
    editorial_review = (
        review.get("editorial_review") if isinstance(review.get("editorial_review"), dict) else {}
    )
    if review.get("approved"):
        editorial_path = root / "receipts" / "final-editorial-review.json"
        stored_editorial = read_json(editorial_path) or {}
        if not editorial_review or not stored_editorial:
            hard.append(
                {
                    "code": "FINAL_EDITORIAL_REVIEW_MISSING",
                    "message": "approved final review is missing the final editorial report",
                }
            )
        elif editorial_review.get("receipt_sha256") != _hash(editorial_path) or (
            editorial_review.get("inputs") != stored_editorial.get("inputs")
            or editorial_review.get("ok") != stored_editorial.get("ok")
        ):
            hard.append(
                {
                    "code": "FINAL_EDITORIAL_REVIEW_TAMPERED",
                    "message": "final editorial report does not match the approved review receipt",
                }
            )
        elif not stored_editorial.get("ok"):
            hard.append(
                {
                    "code": "FINAL_EDITORIAL_REVIEW_FAILED",
                    "message": "approved final review contains a failed editorial report",
                }
            )
        else:
            from final_editorial_review import is_current as editorial_review_is_current

            editorial_freshness = editorial_review_is_current(root, stored_editorial)
            if not editorial_freshness["ok"]:
                hard.append(
                    {
                        "code": "FINAL_EDITORIAL_REVIEW_STALE",
                        "message": "final editorial report no longer matches the current delivery: "
                        + ", ".join(editorial_freshness["mismatches"]),
                    }
                )
    from director_review import SCORECARD_DIMENSIONS

    scorecard_raw = review.get("scorecard") if isinstance(review.get("scorecard"), dict) else {}
    # review-final writes nested {dimensions:{…}}; older receipts may be flat
    if isinstance(scorecard_raw.get("dimensions"), dict):
        scorecard = scorecard_raw["dimensions"]
    else:
        scorecard = scorecard_raw
    screening = (
        review.get("screening_evidence")
        if isinstance(review.get("screening_evidence"), dict)
        else {}
    )
    missing_dimensions = [dim for dim in SCORECARD_DIMENSIONS if scorecard.get(dim) is not True]
    if review.get("approved") and missing_dimensions:
        hard.append(
            {
                "code": "FINAL_SCORECARD_INCOMPLETE",
                "message": "approved review is missing passing dimensions: "
                + ", ".join(missing_dimensions),
            }
        )
    missing_screening = [dim for dim in SCORECARD_DIMENSIONS if dim not in screening]
    if review.get("approved") and missing_screening:
        hard.append(
            {
                "code": "SCREENING_EVIDENCE_INCOMPLETE",
                "message": "full-film screening evidence is missing: "
                + ", ".join(missing_screening),
            }
        )
    final_duration = float(media.get("duration_sec") or 0) if isinstance(media, dict) else 0
    if final_duration:
        for dim, item in screening.items():
            if not isinstance(item, dict):
                hard.append(
                    {
                        "code": "SCREENING_TIMESTAMP_OUT_OF_RANGE",
                        "message": f"screening evidence {dim} is outside final duration",
                    }
                )
                continue
            # director_review stores timestamp_sec; accept legacy "timestamp"
            raw_ts = item.get("timestamp_sec", item.get("timestamp"))
            if raw_ts is None or float(raw_ts) < 0 or float(raw_ts) > final_duration:
                hard.append(
                    {
                        "code": "SCREENING_TIMESTAMP_OUT_OF_RANGE",
                        "message": f"screening evidence {dim} is outside final duration",
                    }
                )
    if review.get("output_sha256") and final_hash and review.get("output_sha256") != final_hash:
        hard.append(
            {
                "code": "FINAL_REVIEW_HASH_STALE",
                "message": "final review was approved against a different MP4 hash",
            }
        )
    performance_timeline = (
        review.get("performance_timeline")
        if isinstance(review, dict) and isinstance(review.get("performance_timeline"), dict)
        else {}
    )
    if performance_timeline.get("required") and not performance_timeline.get("ok"):
        hard.append(
            {
                "code": "PERFORMANCE_TIMELINE_INCOMPLETE",
                "message": "approved final review contains an incomplete performance timeline",
            }
        )
    speech_timing = (
        review.get("speech_performance_timing")
        if isinstance(review, dict) and isinstance(review.get("speech_performance_timing"), dict)
        else {}
    )
    if speech_timing.get("required") and not speech_timing.get("ok"):
        hard.append(
            {
                "code": "SPEECH_PERFORMANCE_TIMING_INCOMPLETE",
                "message": "approved final review contains incomplete dialogue-performance timing",
            }
        )
    audio_provenance = (
        review.get("audio_provenance")
        if isinstance(review, dict) and isinstance(review.get("audio_provenance"), dict)
        else {}
    )
    director_ledger = (
        review.get("director_ledger") if isinstance(review.get("director_ledger"), dict) else {}
    )
    if director_ledger.get("required"):
        from director_ledger import ledger_is_current

        if not ledger_is_current(root, director_ledger):
            hard.append(
                {
                    "code": "DIRECTOR_LEDGER_STALE",
                    "message": "human exception ledger is stale after spec, graph, or final change",
                }
            )
    if audio_provenance.get("required"):
        from audio_provenance import build_audio_provenance

        current_audio_provenance = build_audio_provenance(root, write=False)
        stored_bindings = {
            "tts": (audio_provenance.get("tts_rehearsal") or {}).get("sha256"),
            "carrier": (audio_provenance.get("voice_carrier") or {}).get("sha256"),
            "final": (audio_provenance.get("final_delivery") or {}).get("sha256"),
            "dialogue": [
                (item.get("shot_id"), item.get("audio_sha256"))
                for item in audio_provenance.get("dialogue_sources") or []
                if isinstance(item, dict)
            ],
        }
        current_bindings = {
            "tts": (current_audio_provenance.get("tts_rehearsal") or {}).get("sha256"),
            "carrier": (current_audio_provenance.get("voice_carrier") or {}).get("sha256"),
            "final": (current_audio_provenance.get("final_delivery") or {}).get("sha256"),
            "dialogue": [
                (item.get("shot_id"), item.get("audio_sha256"))
                for item in current_audio_provenance.get("dialogue_sources") or []
                if isinstance(item, dict)
            ],
        }
        if not current_audio_provenance.get("ok") or (stored_bindings != current_bindings):
            hard.append(
                {
                    "code": "AUDIO_PROVENANCE_STALE",
                    "message": "dialogue audio provenance no longer matches the approved final review",
                }
            )
    notes = read_json(root / "receipts" / "director-notes.json") or {}
    open_items = open_reshoot_items(notes)
    if open_items:
        hard.append(
            {
                "code": "OPEN_RESHOOTS",
                "message": f"{len(open_items)} open director reshoot item(s) remain",
            }
        )
    subtitle = next(
        (p for p in (root / "out" / "final.srt", root / "final.srt") if p.is_file()), None
    )
    if not subtitle:
        warnings.append(
            {"code": "SUBTITLE_MISSING", "message": "final subtitle sidecar is missing"}
        )
    subtitle_check = {"ok": True, "cue_count": 0, "max_end_sec": None, "errors": []}
    if subtitle:
        ends, subtitle_errors = _srt_end_times(subtitle)
        subtitle_check = {
            "ok": not subtitle_errors,
            "cue_count": len(ends),
            "max_end_sec": max(ends) if ends else None,
            "errors": subtitle_errors,
        }
        duration = float(media.get("duration_sec") or 0) if isinstance(media, dict) else 0
        if subtitle_errors:
            hard.append({"code": "SUBTITLE_PARSE_FAILED", "message": "; ".join(subtitle_errors)})
        if duration and ends and max(ends) > duration + 0.05:
            hard.append(
                {
                    "code": "SUBTITLE_OUT_OF_RANGE",
                    "message": f"subtitle ends at {max(ends):.3f}s beyond video duration {duration:.3f}s",
                }
            )
    mix = read_json(root / "audio" / "mix_report.json") or {}
    loudness = mix.get("loudness") or mix.get("loudness_after") or {}
    if mix and not loudness:
        warnings.append(
            {
                "code": "LOUDNESS_EVIDENCE_MISSING",
                "message": "mix_report exists but contains no loudness measurement",
            }
        )

    # P3-4 / Wave δ: LUFS hard gate — five_track cinema defaults -16±1.5
    spec_for_lufs = read_json(root / "film-spec.json") or {}
    if not isinstance(spec_for_lufs, dict):
        spec_for_lufs = {}
    try:
        from five_track import lufs_band_for_spec

        band = lufs_band_for_spec(spec_for_lufs)
        lufs_strict = bool(band.get("strict"))
        lufs_min = float(band.get("lufs_min", -17.5))
        lufs_max = float(band.get("lufs_max", -14.5))
    except Exception:  # noqa: BLE001
        lufs_strict = bool(spec_for_lufs.get("lufs_strict"))
        lufs_min = float(spec_for_lufs.get("lufs_min", -23))
        lufs_max = float(spec_for_lufs.get("lufs_max", -14))
    if loudness and isinstance(loudness, dict):
        integrated_lufs = loudness.get("integrated") or loudness.get("integrated_lufs")
        if integrated_lufs is not None:
            lufs_val = float(integrated_lufs)
            if lufs_val < lufs_min or lufs_val > lufs_max:
                msg = (
                    f"LUFS integrated={lufs_val:.1f} out of range [{lufs_min:.1f}, {lufs_max:.1f}]"
                    f" (target -16±1.5 when five_track)"
                )
                if lufs_strict:
                    hard.append(
                        {
                            "code": "LUFS_OUT_OF_RANGE",
                            "message": msg + " (lufs_strict → hard fail)",
                        }
                    )
                else:
                    warnings.append({"code": "LUFS_OUT_OF_RANGE", "message": msg})
    # Wave δ · five-track soft/hard inventory
    try:
        from five_track import plan_five_track

        ft_rep = plan_five_track(root, write=True)
        if ft_rep.get("enabled"):
            for iss in ft_rep.get("issues") or []:
                if not isinstance(iss, dict):
                    continue
                code = str(iss.get("code") or "FIVE_TRACK")
                if code == "LUFS_OUT_OF_RANGE":
                    continue  # already handled above
                row = {"code": code, "message": str(iss.get("message") or code)}
                if str(iss.get("severity") or "") == "error":
                    hard.append(row)
                else:
                    warnings.append(row)
    except Exception as exc:  # noqa: BLE001
        warnings.append({"code": "FIVE_TRACK_PROBE", "message": str(exc)[:160]})
    spec = read_json(root / "film-spec.json") or {}
    shots = [
        shot
        for scene in (spec.get("scenes") or [])
        if isinstance(scene, dict)
        for shot in (scene.get("shots") or [])
        if isinstance(shot, dict)
    ]
    safe_area = {"ok": True, "warning_count": 0, "issues": []}
    if shots:
        from framing_lint import lint_vertical_safe_area

        safe_area = lint_vertical_safe_area(shots)
        if safe_area.get("warning_count"):
            target = hard if spec.get("vertical_safe_area_strict") is True else warnings
            target.append(
                {
                    "code": "VERTICAL_SAFE_AREA",
                    "message": f"{safe_area.get('warning_count')} vertical safe-area issue(s)",
                }
            )
    delivery = next(
        (
            p
            for p in (root / "out" / "final-delivery.json", root / "final-delivery.json")
            if p.is_file()
        ),
        None,
    )
    if not delivery:
        hard.append(
            {"code": "DELIVERY_SIDECAR_MISSING", "message": "final-delivery.json is missing"}
        )
    delivery_meta = read_json(delivery) if delivery else {}
    delivery_version = int(delivery_meta.get("schema_version") or 1)
    native_audio_meta = (
        delivery_meta.get("native_audio")
        if isinstance(delivery_meta.get("native_audio"), dict)
        else {}
    )
    native_audio_evidence = {
        "role": native_audio_meta.get("role"),
        "path": native_audio_meta.get("path"),
        "sha256": native_audio_meta.get("sha256"),
        "preserved_shots": native_audio_meta.get("preserved_shots") or [],
        "available": native_audio_meta.get("role") == "primary_video_sound",
    }
    if native_audio_evidence["available"]:
        raw_native_path = str(native_audio_evidence["path"] or "").strip()
        native_path = Path(raw_native_path) if raw_native_path else None
        if native_path and not native_path.is_absolute():
            native_path = root / native_path
        native_hash = _hash(native_path) if native_path and native_path.is_file() else None
        native_audio_evidence["actual_sha256"] = native_hash
        if not native_path or not native_path.is_file():
            hard.append(
                {
                    "code": "NATIVE_AUDIO_STEM_MISSING",
                    "message": "primary I2V video sound is declared but its preserved stem is missing",
                }
            )
        elif native_audio_evidence["sha256"] != native_hash:
            hard.append(
                {
                    "code": "NATIVE_AUDIO_STEM_HASH_MISMATCH",
                    "message": "primary I2V video sound stem no longer matches final-delivery metadata",
                }
            )
        if not native_audio_evidence["preserved_shots"]:
            hard.append(
                {
                    "code": "NATIVE_AUDIO_STEM_UNBOUND",
                    "message": "primary I2V video sound declares no preserved source shots",
                }
            )
    subtitles_meta = (
        delivery_meta.get("subtitles") if isinstance(delivery_meta.get("subtitles"), dict) else {}
    )
    compose_caption_artifact = (
        root / "compose" / "remotion" / "public" / "captions.json"
    ).is_file()
    if subtitles_meta.get("burned_in") is True and compose_caption_artifact:
        hard.append(
            {
                "code": "SUBTITLE_DOUBLE_BURN_RISK",
                "message": "final delivery reports burned subtitles and compose captions artifact also exists",
            }
        )
    caption_frame_audit = None
    if subtitles_meta.get("burned_in") is True:
        from caption_frame_audit import caption_readability_evidence_status

        caption_frame_audit = caption_readability_evidence_status(root)
        if not caption_frame_audit["ok"]:
            issue = {
                "code": "BURNED_SUBTITLE_HUMAN_REVIEW_MISSING",
                "message": "burned subtitles need current sampled frames and human readability approval",
            }
            (hard if delivery_version >= 2 else warnings).append(issue)
    transition_frame_audit = None
    if delivery_version >= 2:
        from transition_frame_audit import transition_review_evidence_status

        transition_frame_audit = transition_review_evidence_status(root)
        if not transition_frame_audit["ok"]:
            hard.append(
                {
                    "code": "TRANSITION_HUMAN_REVIEW_MISSING",
                    "message": "every current transition needs sampled-frame evidence and human approval",
                }
            )
    title_spec = spec.get("title_sequence") if isinstance(spec, dict) else {}
    if (
        isinstance(title_spec, dict)
        and title_spec.get("mode") not in {None, "none"}
        and delivery_meta.get("plate_cards") == "text"
    ):
        hard.append(
            {
                "code": "TITLE_DOUBLE_BURN_RISK",
                "message": "title sequence is enabled while final delivery reports text plate cards",
            }
        )
    evidence = {
        "final": {
            "path": str(final_path) if final_path else None,
            "sha256": final_hash,
            "probe": _probe(final_path) if final_path else None,
            "media_qa": media,
        },
        "review": {
            "approved": bool(review.get("approved")),
            "path": str(root / "out" / "final-review.json") if review else None,
            "sha256": _hash(root / "out" / "final-review.json")
            if (root / "out" / "final-review.json").is_file()
            else _hash(root / "receipts" / "final-review.json"),
        },
        "subtitles": {
            "path": str(subtitle) if subtitle else None,
            "sha256": _hash(subtitle) if subtitle else None,
            "check": subtitle_check,
            "burned_in": subtitles_meta.get("burned_in"),
        },
        "audio": {
            "path": str(_first_file(root, "audio/mix_report.json"))
            if _first_file(root, "audio/mix_report.json")
            else None,
            "sha256": _hash(_first_file(root, "audio/mix_report.json"))
            if _first_file(root, "audio/mix_report.json")
            else None,
            "loudness": loudness,
        },
        "native_audio": native_audio_evidence,
        "timeline": {
            "path": str(_first_file(root, "timeline.json"))
            if _first_file(root, "timeline.json")
            else None,
            "sha256": _hash(_first_file(root, "timeline.json"))
            if _first_file(root, "timeline.json")
            else None,
        },
        "safe_area": safe_area,
        "delivery": {
            "path": str(delivery) if delivery else None,
            "sha256": _hash(delivery) if delivery else None,
            "schema_version": delivery_version if delivery else None,
        },
        "caption_frame_audit": caption_frame_audit,
        "transition_frame_audit": transition_frame_audit,
        "open_reshoot_count": len(open_items),
        "performance_timeline": {
            "required": bool(performance_timeline.get("required")),
            "ok": performance_timeline.get("ok"),
            "path": performance_timeline.get("path"),
            "sha256": performance_timeline.get("sha256"),
        },
        "speech_performance_timing": {
            "required": bool(speech_timing.get("required")),
            "ok": speech_timing.get("ok"),
            "path": speech_timing.get("path"),
            "sha256": speech_timing.get("sha256"),
        },
        "audio_provenance": {
            "required": bool(audio_provenance.get("required")),
            "ok": audio_provenance.get("ok"),
            "path": audio_provenance.get("path"),
            "sha256": audio_provenance.get("sha256"),
        },
        "editorial_review": {
            "path": str(root / "receipts" / "final-editorial-review.json"),
            "sha256": _hash(root / "receipts" / "final-editorial-review.json"),
            "ok": editorial_review.get("ok"),
        },
    }
    sidecar_expectations = {
        "final": (delivery_meta.get("output_sha256") or delivery_meta.get("final_sha256")),
        "subtitles": (subtitles_meta.get("srt_sha256")),
        "audio": (
            (delivery_meta.get("audio") or {}).get("sha256")
            if isinstance(delivery_meta.get("audio"), dict)
            else None
        ),
        "timeline": (
            (delivery_meta.get("timeline") or {}).get("sha256")
            if isinstance(delivery_meta.get("timeline"), dict)
            else None
        ),
    }
    for key, expected in sidecar_expectations.items():
        actual = (evidence.get(key) or {}).get("sha256")
        if expected and actual and expected != actual:
            hard.append(
                {
                    "code": f"SIDECAR_{key.upper()}_HASH_MISMATCH",
                    "message": f"final-delivery metadata hash for {key} does not match current file",
                }
            )
    if delivery and delivery_version < 2:
        warnings.append(
            {
                "code": "DELIVERY_PROVENANCE_LEGACY",
                "message": "final-delivery schema v1 lacks complete post provenance; re-render to v2 when practical",
            }
        )
    if delivery_version >= 2:
        required_provenance = {
            "final": delivery_meta.get("output_sha256") or delivery_meta.get("final_sha256"),
            "subtitles": subtitles_meta.get("srt_sha256") if subtitle else True,
            "audio_mix_report": (delivery_meta.get("audio_provenance") or {}).get(
                "mix_report_sha256"
            )
            if _first_file(root, "audio/mix_report.json")
            else True,
            "timeline": (delivery_meta.get("timeline") or {}).get("sha256")
            if _first_file(root, "timeline.json")
            else True,
        }
        missing_provenance = [key for key, value in required_provenance.items() if not value]
        if missing_provenance:
            hard.append(
                {
                    "code": "DELIVERY_PROVENANCE_INCOMPLETE",
                    "message": "final-delivery v2 is missing bound hashes: "
                    + ", ".join(missing_provenance),
                }
            )
    freshness = audit_freshness(root, {"evidence": evidence})
    if freshness["stale"]:
        hard.append(
            {
                "code": "POST_AUDIT_STALE",
                "message": "post-audit evidence hashes do not match current production files",
            }
        )

    # P2-1: face identity drift — pixel fingerprints in receipts/face-identity.json
    try:
        from face_identity import post_audit_face_status
    except Exception:  # noqa: BLE001
        try:
            from face_identity import post_audit_face_status  # type: ignore
        except Exception:  # noqa: BLE001
            post_audit_face_status = None  # type: ignore
    if post_audit_face_status is not None:
        face_st = post_audit_face_status(root)
        for w in face_st.get("warnings") or []:
            if isinstance(w, dict) and w.get("code"):
                warnings.append(w)
        for h in face_st.get("hard") or []:
            if isinstance(h, dict) and h.get("code"):
                hard.append(h)
    else:
        # Fallback if module missing
        bible_path = _first_file(root, "style-bible.json")
        if bible_path:
            bible = read_json(bible_path) or {}
            cast_masters = bible.get("cast_masters") or {}
            if isinstance(cast_masters, dict) and cast_masters:
                identity_receipt_path = root / "receipts" / "face-identity.json"
                if not identity_receipt_path.is_file():
                    warnings.append(
                        {
                            "code": "FACE_IDENTITY_DRIFT",
                            "message": f"cast_masters has {len(cast_masters)} character(s) but no face-identity.json",
                        }
                    )

    # P3-1: color grade check — verify grade parameters exist when strict
    spec_path = _first_file(root, "film-spec.json")
    spec = read_json(spec_path) or {} if spec_path else {}

    # Determine premium quality target (from production-book or film-spec)
    is_premium = False
    pb_path = root / "production-book.json"
    if pb_path.is_file():
        pb = read_json(pb_path) or {}
        is_premium = str(pb.get("quality_target") or "standard") == "premium_vertical"
    if not is_premium and isinstance(spec, dict):
        is_premium = str(spec.get("quality_target") or "standard") == "premium_vertical"

    # P2-6: face identity drift — premium projects elevate warnings to hard
    if post_audit_face_status is not None:
        face_st = post_audit_face_status(root)
        for w in face_st.get("warnings") or []:
            if isinstance(w, dict) and w.get("code"):
                if is_premium and w.get("code") in (
                    "FACE_IDENTITY_DRIFT",
                    "FACE_IDENTITY_ENROLL_GAP",
                ):
                    hard.append(w)
                else:
                    warnings.append(w)
        for h in face_st.get("hard") or []:
            if isinstance(h, dict) and h.get("code"):
                hard.append(h)
    else:
        # Fallback if module missing
        bible_path = _first_file(root, "style-bible.json")
        if bible_path:
            bible = read_json(bible_path) or {}
            cast_masters = bible.get("cast_masters") or {}
            if isinstance(cast_masters, dict) and cast_masters:
                identity_receipt_path = root / "receipts" / "face-identity.json"
                if not identity_receipt_path.is_file():
                    drift_msg = {
                        "code": "FACE_IDENTITY_DRIFT",
                        "message": f"cast_masters has {len(cast_masters)} character(s) but no face-identity.json",
                    }
                    if is_premium:
                        hard.append(drift_msg)
                    else:
                        warnings.append(drift_msg)

    grade = spec.get("grade") if isinstance(spec, dict) else None
    # P2-8: color grade strict — premium defaults to strict
    grade_strict = bool(spec.get("color_grade_strict")) if isinstance(spec, dict) else False
    if is_premium and not grade_strict:
        grade_strict = True
    if grade_strict:
        if not isinstance(grade, dict) or not grade.get("color_temperature"):
            hard.append(
                {
                    "code": "COLOR_GRADE_MISSING",
                    "message": "color_grade_strict is true but grade.color_temperature is missing — color grading not defined",
                }
            )
    elif not grade:
        warnings.append(
            {
                "code": "COLOR_GRADE_MISSING",
                "message": "no grade parameters in film-spec — color grading is unparameterized (from 0/10 baseline)",
            }
        )

    # P2-11: audio_bible / post_bible — premium projects elevate advisory to hard
    if is_premium:
        audio_bible_path = _first_file(root, "audio-bible.json")
        if audio_bible_path:
            try:
                from audio_bible import validate_audio_bible

                ab = read_json(audio_bible_path) or {}
                ab_report = validate_audio_bible(ab)
                for err in ab_report.get("errors") or []:
                    hard.append(
                        {
                            "code": str(err.get("code") or "AUDIO_BIBLE_VIOLATION"),
                            "message": f"audio-bible: {err.get('message', '')}",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                # A1 · premium: bible probe fail is hard (no silent skip)
                hard.append(
                    {
                        "code": "AUDIO_BIBLE_PROBE_ERROR",
                        "message": f"audio-bible probe failed: {exc}"[:200],
                    }
                )

        post_bible_path = _first_file(root, "post-bible.json")
        if post_bible_path:
            try:
                from post_bible import validate_post_bible

                pb2 = read_json(post_bible_path) or {}
                pb2_report = validate_post_bible(pb2)
                for err in pb2_report.get("errors") or []:
                    hard.append(
                        {
                            "code": str(err.get("code") or "POST_BIBLE_VIOLATION"),
                            "message": f"post-bible: {err.get('message', '')}",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                hard.append(
                    {
                        "code": "POST_BIBLE_PROBE_ERROR",
                        "message": f"post-bible probe failed: {exc}"[:200],
                    }
                )

    report = {
        "ok": True,
        "kind": "post-audit",
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "root": str(root),
        "delivery_ready": not hard,
        "hard_failures": hard,
        "warnings": warnings,
        "human_review_required": [] if review.get("approved") else ["full-film director review"],
        "freshness": freshness,
        "evidence": evidence,
    }
    if write:
        write_json(root / "receipts" / "post-audit.json", report)
        lines = (
            [
                "# Post Audit",
                "",
                f"- Delivery ready: `{report['delivery_ready']}`",
                f"- Hard failures: `{len(hard)}`",
                f"- Warnings: `{len(warnings)}`",
                "",
                "## Hard failures",
            ]
            + [f"- `{item['code']}`: {item['message']}" for item in hard]
            + ["", "## Warnings"]
            + [f"- `{item['code']}`: {item['message']}" for item in warnings]
        )
        (root / "receipts" / "post-audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
