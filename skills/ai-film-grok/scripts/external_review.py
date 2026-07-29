"""Read-only Groq/Gemini review sidecar.

It deliberately produces candidate findings only.  No result from this module can
approve media, alter provider routing, or submit a generation task.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from media_qa import MediaQAError, analyze_media
from security_policy import safe_existing_file
from util import read_json, sha256_file, write_json

REPORT_NAME = "external-review.json"
GROQ_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
GEMINI_AUDIT_MODEL = "gemini-2.5-flash"
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_FRAME_BYTES = 20 * 1024 * 1024
MAX_SAFE_FRAMES = 5
PURPOSES = frozenset({"tts_rehearsal", "animatic", "final"})


class ExternalReviewError(ValueError):
    pass


class ExternalReviewUnavailable(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _root_file(root: Path, value: Path | str, *, label: str, max_bytes: int | None = None) -> Path:
    base = Path(root).expanduser().resolve()
    raw = Path(value).expanduser()
    unresolved = raw if raw.is_absolute() else base / raw
    if unresolved.is_symlink():
        raise ExternalReviewError(f"{label} must be a regular non-symlink file")
    candidate = unresolved.resolve()
    if base not in candidate.parents:
        raise ExternalReviewError(f"{label} must be inside the film workspace")
    try:
        safe_existing_file(base, candidate, field=label)
    except Exception as exc:
        raise ExternalReviewError(f"{label} must be a regular non-symlink file") from exc
    if max_bytes is not None and candidate.stat().st_size > max_bytes:
        raise ExternalReviewError(f"{label} exceeds the safe upload limit")
    return candidate


def _is_adult(root: Path) -> bool:
    spec = read_json(Path(root) / "film-spec.json") or {}
    return str(spec.get("heat_scale") or "").strip().lower() == "max"


def _normalize_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff]", "", value).lower()


def parse_srt(path: Path) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8-sig")
    cues: list[dict[str, Any]] = []
    for block in re.split(r"\r?\n\s*\r?\n", source.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_line = next((line for line in lines if "-->" in line), None)
        if not time_line:
            continue
        try:
            left, right = (part.strip() for part in time_line.split("-->", 1))
            start = _srt_seconds(left)
            end = _srt_seconds(right.split()[0])
        except ValueError:
            continue
        text = " ".join(line for line in lines if line != time_line and not line.isdigit())
        if text:
            cues.append({"start_sec": start, "end_sec": end, "text": text})
    return cues


def _srt_seconds(value: str) -> float:
    hms, millis = value.replace(",", ".").split(".", 1)
    hours, minutes, seconds = (int(part) for part in hms.split(":"))
    return hours * 3600 + minutes * 60 + seconds + int(millis.ljust(3, "0")[:3]) / 1000


def compare_word_timing(
    subtitles: list[dict[str, Any]], words: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return conservative candidates; linguistic disagreement never blocks delivery."""
    transcript = _normalize_text("".join(str(word.get("word") or "") for word in words))
    issues: list[dict[str, Any]] = []
    for cue in subtitles:
        text = str(cue.get("text") or "")
        normalized = _normalize_text(text)
        if normalized and normalized not in transcript:
            issues.append(
                {
                    "code": "subtitle_missing_from_transcript",
                    "severity": "candidate",
                    "timestamp_sec": cue["start_sec"],
                    "note": "字幕文本未在转录中找到；需人工确认是否为识别误差。",
                }
            )
        cue_words = [
            word
            for word in words
            if float(word.get("end") or -1) >= float(cue["start_sec"])
            and float(word.get("start") or 1e9) <= float(cue["end_sec"])
        ]
        if cue_words:
            first = float(cue_words[0]["start"])
            last = float(cue_words[-1]["end"])
            if first - float(cue["start_sec"]) > 0.35 or last - float(cue["end_sec"]) > 0.35:
                issues.append(
                    {
                        "code": "subtitle_timing_drift",
                        "severity": "candidate",
                        "timestamp_sec": cue["start_sec"],
                        "note": "逐词转录与字幕 cue 的时间窗偏离超过 350ms；需人工核对。",
                    }
                )
    return issues


def _request_json(
    url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: int = 45
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 -- fixed provider endpoints
            raw = response.read(1_048_577)
    except urllib.error.HTTPError as exc:
        raise ExternalReviewUnavailable(
            f"HTTP_{exc.code}", f"provider returned HTTP {exc.code}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ExternalReviewUnavailable("UNREACHABLE", "provider is unreachable") from exc
    if len(raw) > 1_048_576:
        raise ExternalReviewUnavailable("RESPONSE_TOO_LARGE", "provider response exceeded 1 MiB")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalReviewUnavailable("INVALID_JSON", "provider returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ExternalReviewUnavailable("INVALID_JSON", "provider returned an invalid envelope")
    return value


def _groq_transcription(video: Path, key: str) -> list[dict[str, Any]]:
    boundary = "----aifilm-review-boundary"
    data = video.read_bytes()
    body = b"\r\n".join(
        (
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="model"',
            b"",
            GROQ_TRANSCRIPTION_MODEL.encode(),
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="response_format"',
            b"",
            b"verbose_json",
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="timestamp_granularities[]"',
            b"",
            b"word",
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.mp4"\r\nContent-Type: application/octet-stream\r\n'.encode()
            + data,
            f"--{boundary}--".encode(),
            b"",
        )
    )
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 -- fixed provider endpoint
            payload = json.loads(response.read(1_048_577))
    except urllib.error.HTTPError as exc:
        raise ExternalReviewUnavailable(
            f"GROQ_HTTP_{exc.code}", f"provider returned HTTP {exc.code}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ExternalReviewUnavailable(
            "GROQ_UNAVAILABLE", "Groq transcription unavailable"
        ) from exc
    words = payload.get("words") if isinstance(payload, dict) else None
    if not isinstance(words, list):
        raise ExternalReviewUnavailable("GROQ_INVALID_JSON", "Groq response lacks word timestamps")
    return [word for word in words if isinstance(word, dict) and isinstance(word.get("word"), str)]


def _provider_state(name: str, model: str, configured: bool) -> dict[str, Any]:
    return {
        "provider": name,
        "model": model,
        "configured": configured,
        "status": "not_configured" if not configured else "not_run",
    }


def _safe_frame_index(root: Path, value: Path | str | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    index = _root_file(root, value, label="sanitized frame index")
    try:
        raw = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalReviewError("sanitized frame index must be valid JSON") from exc
    entries = raw.get("frames") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or len(entries) > MAX_SAFE_FRAMES:
        raise ExternalReviewError(f"sanitized frame index must list 1-{MAX_SAFE_FRAMES} frames")
    result: list[dict[str, Any]] = []
    for item in entries:
        relative = item.get("path") if isinstance(item, dict) else item
        if not isinstance(relative, str):
            raise ExternalReviewError("sanitized frame index contains an invalid path")
        frame = _root_file(
            root, root / relative, label="sanitized frame", max_bytes=MAX_FRAME_BYTES
        )
        if frame.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ExternalReviewError("sanitized frame must be an image")
        result.append({"path": frame, "sha256": sha256_file(frame)})
    return result


def _json_candidate_issues(value: Any, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ExternalReviewUnavailable(
            "INVALID_JSON", f"{source} response lacks candidate issue list"
        )
    output: list[dict[str, Any]] = []
    for item in value[:20]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("code"), str)
            or not isinstance(item.get("note"), str)
        ):
            raise ExternalReviewUnavailable(
                "INVALID_JSON", f"{source} response issue schema is invalid"
            )
        output.append(
            {
                "code": item["code"][:64],
                "severity": "candidate",
                "timestamp_sec": item.get("timestamp_sec"),
                "note": item["note"][:500],
            }
        )
    return output


def _groq_vision(frames: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": "Review only these declared sanitized technical frames. Return JSON object {issues:[{code,note,timestamp_sec}]}. Flag only subtitle obstruction, black/frozen frames, obvious continuity or visual defects. Every finding is a candidate, never an approval.",
        }
    ]
    for frame in frames:
        path = frame["path"]
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    response = _request_json(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        body={
            "model": GROQ_VISION_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        },
    )
    choices = response.get("choices")
    content_value = (
        choices[0].get("message", {}).get("content")
        if isinstance(choices, list) and choices
        else None
    )
    try:
        parsed = json.loads(content_value) if isinstance(content_value, str) else None
    except json.JSONDecodeError as exc:
        raise ExternalReviewUnavailable(
            "INVALID_JSON", "Groq vision response was not JSON"
        ) from exc
    return _json_candidate_issues(
        parsed.get("issues") if isinstance(parsed, dict) else None, source="Groq vision"
    )


def _gemini_audit(context: dict[str, Any], key: str) -> list[dict[str, Any]]:
    response = _request_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_AUDIT_MODEL}:generateContent",
        headers={"x-goog-api-key": key},
        body={
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Act only as a film-review sidecar. From this metadata, return JSON {issues:[{code,note,timestamp_sec}]} for continuity, causal action, narrative beat, or subtitle-intent conflicts. Findings are candidates only; never approve, route, or generate.\\n"
                            + json.dumps(context, ensure_ascii=False)
                        }
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        },
    )
    candidates = response.get("candidates")
    text = (
        candidates[0].get("content", {}).get("parts", [{}])[0].get("text")
        if isinstance(candidates, list) and candidates
        else None
    )
    try:
        parsed = json.loads(text) if isinstance(text, str) else None
    except json.JSONDecodeError as exc:
        raise ExternalReviewUnavailable(
            "INVALID_JSON", "Gemini audit response was not JSON"
        ) from exc
    return _json_candidate_issues(
        parsed.get("issues") if isinstance(parsed, dict) else None, source="Gemini audit"
    )


def capability_probe() -> dict[str, Any]:
    """Credential-presence probe only: never sends media, prompts, or paid calls."""
    groq = bool(os.environ.get("GROQ_API_KEY"))
    gemini = bool(os.environ.get("GEMINI_API_KEY"))
    return {
        "schema_version": 1,
        "kind": "external-review-probe",
        "at": _utc_now(),
        "inference_started": False,
        "providers": {
            "groq": _provider_state("groq", GROQ_VISION_MODEL, groq),
            "gemini": _provider_state("gemini", GEMINI_AUDIT_MODEL, gemini),
        },
        "note": "No media, prompt, model-list, quota, or generation request is sent by this probe.",
    }


def create_report(
    root: Path | str,
    *,
    video: Path | str,
    subtitles: Path | str | None = None,
    director_contract: Path | str | None = None,
    sanitized_frame_index: Path | str | None = None,
    sanitized: bool = False,
    purpose: str = "final",
) -> dict[str, Any]:
    """Write one hash-bound candidate-only report; provider failures remain nonblocking."""
    if purpose not in PURPOSES:
        raise ExternalReviewError("external review purpose is invalid")
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ExternalReviewError("film root must exist")
    if _is_adult(base) and not sanitized:
        raise ExternalReviewError(
            "adult review requires explicitly declared sanitized technical inputs"
        )
    source = _root_file(base, video, label="video", max_bytes=MAX_VIDEO_BYTES)
    adult = _is_adult(base)
    if adult and source.suffix.lower() not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
        raise ExternalReviewError(
            "adult review accepts only a declared sanitized audio file, never raw video"
        )
    try:
        media_qa = analyze_media(source, require_audio=False, require_motion=False)
    except MediaQAError as exc:
        raise ExternalReviewError("video must pass local technical media verification") from exc
    if media_qa.get("ok") is not True:
        raise ExternalReviewError("video must pass local technical media verification")
    subtitle_path = _root_file(base, subtitles, label="subtitles") if subtitles else None
    contract_path = (
        _root_file(base, director_contract, label="director contract")
        if director_contract
        else None
    )
    frames = _safe_frame_index(base, sanitized_frame_index)
    if frames and not sanitized:
        raise ExternalReviewError("safe frame uploads require --sanitized declaration")
    cues = parse_srt(subtitle_path) if subtitle_path else []
    groq_key = os.environ.get("GROQ_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    providers = {
        "groq": _provider_state("groq", GROQ_TRANSCRIPTION_MODEL, bool(groq_key)),
        "gemini": _provider_state("gemini", GEMINI_AUDIT_MODEL, bool(gemini_key)),
    }
    issues: list[dict[str, Any]] = []
    if groq_key:
        try:
            words = _groq_transcription(source, groq_key)
            providers["groq"].update({"status": "completed", "word_count": len(words)})
            issues.extend(compare_word_timing(cues, words))
        except ExternalReviewUnavailable as exc:
            providers["groq"].update({"status": "unavailable", "failure_code": exc.code})
    if groq_key and frames:
        try:
            issues.extend(_groq_vision(frames, groq_key))
            providers["groq"]["vision_status"] = "completed"
        except ExternalReviewUnavailable as exc:
            providers["groq"]["vision_status"] = "unavailable"
            providers["groq"]["vision_failure_code"] = exc.code
    if gemini_key:
        try:
            audit_context = {
                "subtitles": cues,
                "director_contract": read_json(contract_path)
                if contract_path and not adult
                else None,
                "safe_frame_hashes": [item["sha256"] for item in frames],
                "groq_candidate_issues": issues,
            }
            issues.extend(_gemini_audit(audit_context, gemini_key))
            providers["gemini"]["status"] = "completed"
        except ExternalReviewUnavailable as exc:
            providers["gemini"].update({"status": "unavailable", "failure_code": exc.code})
    input_files = {
        "video": {
            "path": str(source.relative_to(base)),
            "sha256": sha256_file(source),
            "technical_qa": media_qa,
        }
    }
    if subtitle_path:
        input_files["subtitles"] = {
            "path": str(subtitle_path.relative_to(base)),
            "sha256": sha256_file(subtitle_path),
        }
    if contract_path:
        input_files["director_contract"] = {
            "path": str(contract_path.relative_to(base)),
            "sha256": sha256_file(contract_path),
        }
    if frames:
        input_files["sanitized_frames"] = [
            {"path": str(item["path"].relative_to(base)), "sha256": item["sha256"]}
            for item in frames
        ]
    report = {
        "schema_version": 1,
        "kind": "external-review",
        "at": _utc_now(),
        "purpose": purpose,
        "status": "candidate_only",
        "candidate_findings": issues,
        "providers": providers,
        "inputs": input_files,
        "sanitized_technical_inputs": bool(sanitized),
        "cost_state": "unknown",
        "may_approve_production": False,
        "may_change_provider": False,
        "may_submit_generation": False,
        "human_review_required": True,
        "note": "External findings are advisory and cannot change final review or delivery gates.",
    }
    output = base / "receipts" / REPORT_NAME
    write_json(output, report)
    report["path"] = str(output)
    return report
