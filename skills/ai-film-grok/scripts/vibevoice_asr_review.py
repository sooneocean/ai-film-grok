"""Local, opt-in VibeVoice-ASR review sidecar.

The configured command must write a JSON transcript to ``{out}``. This module
only turns that transcript into hash-bound candidate findings; it cannot approve
delivery, change a provider, or submit any generation work.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from external_review import compare_word_timing, parse_srt
from media_qa import MediaQAError, analyze_media
from security_policy import (
    SecurityPolicyError,
    expand_argv,
    minimal_subprocess_env,
    parse_argv_json,
    safe_existing_file,
    safe_workspace_directory,
)
from util import sha256_file, write_json

REPORT_NAME = "vibevoice-asr-review.json"
ARGV_ENV = "AIFILM_VIBEVOICE_ASR_ARGV"
REMOTE_ADAPTER_ENV_KEYS = (
    "AIFILM_VIBEVOICE_ASR_SSH_TARGET",
    "AIFILM_VIBEVOICE_ASR_SSH_KEY",
    "AIFILM_VIBEVOICE_ASR_SSH_HOSTKEY_ALIAS",
    "AIFILM_VIBEVOICE_ASR_REMOTE_ROOT",
    "AIFILM_VIBEVOICE_ASR_REMOTE_MODEL_PATH",
)


class VibeVoiceASRError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _root_file(root: Path, value: Path | str, *, label: str) -> Path:
    base = root.expanduser().resolve()
    raw = Path(value).expanduser()
    unresolved = raw if raw.is_absolute() else base / raw
    if unresolved.is_symlink():
        raise VibeVoiceASRError(
            f"{label} must be a regular non-symlink file inside the film workspace"
        )
    candidate = unresolved.resolve(strict=False)
    try:
        return safe_existing_file(base, candidate, field=label)
    except Exception as exc:
        raise VibeVoiceASRError(
            f"{label} must be a regular non-symlink file inside the film workspace"
        ) from exc


def _argv() -> list[str]:
    raw = os.environ.get(ARGV_ENV, "").strip()
    if not raw:
        raise VibeVoiceASRError(
            f"{ARGV_ENV} is not configured; use a JSON argv with {{audio}} and {{out}} placeholders"
        )
    try:
        template = parse_argv_json(raw, variable=ARGV_ENV)
    except SecurityPolicyError as exc:
        raise VibeVoiceASRError(str(exc)) from exc
    if not any("{audio}" in value for value in template) or not any(
        "{out}" in value for value in template
    ):
        raise VibeVoiceASRError(f"{ARGV_ENV} must contain both {{audio}} and {{out}} placeholders")
    return template


def capability_probe() -> dict[str, Any]:
    """Check only local configuration; never launches a model or downloads weights."""
    try:
        _argv()
        status, error = "configured", None
    except VibeVoiceASRError as exc:
        status, error = "not_configured", str(exc)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "vibevoice-asr-probe",
        "at": _utc_now(),
        "inference_started": False,
        "provider": {"name": "vibevoice-asr", "status": status, "local_only": True},
        "note": "No model download, model load, media read, or inference request is made by this probe.",
    }
    if error:
        report["failure"] = error
    return report


def _number(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) < 0:
        raise VibeVoiceASRError(f"transcript {field} must be a non-negative number")
    return float(value)


def _segments(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries = raw.get("segments") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries or len(entries) > 10_000:
        raise VibeVoiceASRError("transcript must contain 1-10000 segments")
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise VibeVoiceASRError("transcript segment must be an object")
        text = str(entry.get("text") or "").strip()
        start = _number(entry.get("start"), field="segment.start")
        end = _number(entry.get("end"), field="segment.end")
        if not text or len(text) > 2_000 or end < start:
            raise VibeVoiceASRError("transcript segment has invalid text or timing")
        speaker = str(entry.get("speaker") or "unknown").strip()[:128] or "unknown"
        segments.append({"speaker": speaker, "start": start, "end": end, "text": text})
        entry_words = entry.get("words")
        if isinstance(entry_words, list):
            for word in entry_words:
                if not isinstance(word, dict) or not str(word.get("word") or "").strip():
                    continue
                word_start = _number(word.get("start"), field="word.start")
                word_end = _number(word.get("end"), field="word.end")
                if word_end < word_start:
                    raise VibeVoiceASRError("transcript word has invalid timing")
                words.append({"word": str(word["word"]), "start": word_start, "end": word_end})
    if not words:
        words = [
            {"word": item["text"], "start": item["start"], "end": item["end"]} for item in segments
        ]
    return segments, words


def create_report(
    root: Path | str, *, audio: Path | str, subtitles: Path | str | None = None
) -> dict[str, Any]:
    """Run a declared local adapter and write a candidate-only transcript review."""
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise VibeVoiceASRError("film root must exist")
    source = _root_file(base, audio, label="audio")
    try:
        media_qa = analyze_media(source, require_audio=True, require_motion=False)
    except MediaQAError as exc:
        raise VibeVoiceASRError("audio must pass local technical media verification") from exc
    if media_qa.get("ok") is not True:
        raise VibeVoiceASRError("audio must pass local technical media verification")
    subtitle_path = _root_file(base, subtitles, label="subtitles") if subtitles else None
    template = _argv()
    try:
        receipts = safe_workspace_directory(base, "receipts", field="receipts")
    except SecurityPolicyError as exc:
        raise VibeVoiceASRError(str(exc)) from exc
    receipts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vibevoice-asr-", dir=receipts) as temp_dir:
        transcript_path = Path(temp_dir) / "transcript.json"
        try:
            command = expand_argv(
                template,
                {"audio": str(source), "out": str(transcript_path)},
                variable=ARGV_ENV,
            )
        except SecurityPolicyError as exc:
            raise VibeVoiceASRError(str(exc)) from exc
        try:
            adapter_env = minimal_subprocess_env()
            # These are connection coordinates only; credentials remain in the SSH key file.
            adapter_env.update(
                {key: os.environ[key] for key in REMOTE_ADAPTER_ENV_KEYS if os.environ.get(key)}
            )
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=1_200,
                check=False,
                env=adapter_env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VibeVoiceASRError("VibeVoice-ASR adapter did not complete") from exc
        if completed.returncode != 0:
            raise VibeVoiceASRError(f"VibeVoice-ASR adapter failed (rc={completed.returncode})")
        if not transcript_path.is_file() or transcript_path.is_symlink():
            raise VibeVoiceASRError("VibeVoice-ASR adapter did not write transcript JSON")
        try:
            raw = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VibeVoiceASRError("VibeVoice-ASR adapter wrote invalid transcript JSON") from exc
    segments, words = _segments(raw)
    cues = parse_srt(subtitle_path) if subtitle_path else []
    findings = compare_word_timing(cues, words)
    speakers = sorted({item["speaker"] for item in segments})
    report = {
        "schema_version": 1,
        "kind": "vibevoice-asr-review",
        "at": _utc_now(),
        "status": "candidate_only",
        "provider": {"name": "vibevoice-asr", "local_only": True, "status": "completed"},
        "inputs": {
            "audio": {
                "path": str(source.relative_to(base)),
                "sha256": sha256_file(source),
                "technical_qa": media_qa,
            },
            **(
                {
                    "subtitles": {
                        "path": str(subtitle_path.relative_to(base)),
                        "sha256": sha256_file(subtitle_path),
                    }
                }
                if subtitle_path
                else {}
            ),
        },
        "transcript": {
            "segment_count": len(segments),
            "word_count": len(words),
            "speakers": speakers,
            "segments": segments,
        },
        "candidate_findings": findings,
        "may_approve_production": False,
        "may_change_provider": False,
        "may_submit_generation": False,
        "human_review_required": True,
        "note": "ASR is an independent QA signal only; recognition disagreement requires human listening.",
    }
    output = receipts / REPORT_NAME
    write_json(output, report)
    report["path"] = str(output)
    return report
