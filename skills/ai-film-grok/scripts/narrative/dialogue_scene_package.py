"""Dialogue-first scene package: one stable line key across production."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

SCREEN_MODES = frozenset({"on_camera", "off_camera", "reaction", "action_cover", "silence"})
REQUIRED_LINE_KEYS = frozenset(
    {
        "line_id",
        "speaker",
        "spoken_text",
        "caption_text",
        "emotion",
        "subtext",
        "action_while_speaking",
        "listener",
        "scene_state_id",
        "screen_mode",
        "lipsync_required",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_EVIDENCE_BYTES = 512 * 1024 * 1024
_FFPROBE_CANDIDATES = (
    Path("/opt/homebrew/bin/ffprobe"),
    Path("/usr/local/bin/ffprobe"),
    Path("/usr/bin/ffprobe"),
)


def _shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def _fd_sha256(file_fd: int) -> str | None:
    before = os.fstat(file_fd)
    digest = hashlib.sha256()
    os.lseek(file_fd, 0, os.SEEK_SET)
    while chunk := os.read(file_fd, 1024 * 1024):
        digest.update(chunk)
    after = os.fstat(file_fd)
    before_identity = (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    after_identity = (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    return digest.hexdigest() if before_identity == after_identity else None


def _ffprobe_path() -> Path | None:
    for candidate in _FFPROBE_CANDIDATES:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _probe_media_fd(file_fd: int, expected: str) -> bool:
    ffprobe = _ffprobe_path()
    if ffprobe is None or expected not in {"audio", "video"}:
        return False
    os.lseek(file_fd, 0, os.SEEK_SET)
    try:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type",
                "-of",
                "json",
                f"/dev/fd/{file_fd}",
            ],
            pass_fds=(file_fd,),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env={"LANG": "C", "PATH": os.defpath},
        )
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
        return False
    streams = payload.get("streams")
    return (
        duration > 0
        and isinstance(streams, list)
        and any(
            isinstance(stream, dict) and stream.get("codec_type") == expected for stream in streams
        )
    )


def _film_root(root: Path | str | None) -> tuple[Path, int] | None:
    if root is None or not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        return None
    raw = Path(root).expanduser()
    if raw.is_symlink():
        return None
    resolved = Path(os.path.abspath(raw))
    try:
        directory_fd = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return None
    return resolved, directory_fd


def _relative_evidence(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value).expanduser()
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else root / raw))
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return None
    return relative if relative.parts else None


def _open_evidence(root_fd: int, relative: Path) -> tuple[int, os.stat_result] | None:
    directory_fd = os.dup(root_fd)
    try:
        for component in relative.parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
    except OSError:
        os.close(directory_fd)
        return None
    os.close(directory_fd)
    metadata = os.fstat(file_fd)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _MAX_EVIDENCE_BYTES
    ):
        os.close(file_fd)
        return None
    return file_fd, metadata


def _verify_evidence(
    root: Path,
    root_fd: int,
    path_value: object,
    expected_sha256: object,
    *,
    media_type: str,
) -> bool:
    relative = _relative_evidence(root, path_value)
    expected_hash = str(expected_sha256 or "")
    if relative is None or not _SHA256.fullmatch(expected_hash):
        return False
    first = _open_evidence(root_fd, relative)
    if first is None:
        return False
    first_fd, first_stat = first
    try:
        actual_hash = _fd_sha256(first_fd)
        if (
            actual_hash is None
            or not hmac.compare_digest(actual_hash, expected_hash)
            or not _probe_media_fd(first_fd, media_type)
        ):
            return False
    finally:
        os.close(first_fd)
    second = _open_evidence(root_fd, relative)
    if second is None:
        return False
    second_fd, second_stat = second
    try:
        second_hash = _fd_sha256(second_fd)
    finally:
        os.close(second_fd)
    return (
        (first_stat.st_dev, first_stat.st_ino) == (second_stat.st_dev, second_stat.st_ino)
        and second_hash is not None
        and hmac.compare_digest(second_hash, expected_hash)
    )


def validate_audio_evidence(audio: object, *, root: Path | str) -> bool:
    """Validate one measured audio receipt against a safe film-root file."""
    if not isinstance(audio, dict) or audio.get("status") != "measured":
        return False
    try:
        duration_ok = float(audio.get("duration_sec") or 0) > 0
    except (TypeError, ValueError):
        return False
    if not duration_ok:
        return False
    film_root = _film_root(root)
    if film_root is None:
        return False
    try:
        return _verify_evidence(
            film_root[0],
            film_root[1],
            audio.get("path"),
            audio.get("sha256"),
            media_type="audio",
        )
    finally:
        os.close(film_root[1])


def build_dialogue_scene_package(
    graph: dict[str, Any], spec: dict[str, Any], rehearsal: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Project the authored ledger into an auditable, line-addressable package.

    This is intentionally a planning artifact: TTS/lipsync fields remain pending
    until real audio and human review are recorded, rather than being invented.
    """
    by_line = {
        str(shot.get("dialogue_line_id") or ""): shot
        for shot in _shots(spec)
        if str(shot.get("dialogue_line_id") or "").strip()
    }
    audio_by_shot = {
        str(row.get("shot_id") or ""): row
        for row in (rehearsal or {}).get("shots") or []
        if isinstance(row, dict)
    }
    scenes: dict[str, list[dict[str, Any]]] = {}
    for ledger in graph.get("dialogue_ledger") or []:
        if not isinstance(ledger, dict):
            continue
        line_id = str(ledger.get("line_id") or "").strip()
        if not line_id:
            continue
        shot = by_line.get(line_id, {})
        action = ledger.get("actions") if isinstance(ledger.get("actions"), dict) else {}
        shot_id = str(shot.get("id") or ledger.get("shot_ref") or "")
        audio = audio_by_shot.get(shot_id, {})
        voice = next(
            (
                cue
                for cue in shot.get("audio_cues") or []
                if isinstance(cue, dict)
                and cue.get("kind") == "voice"
                and cue.get("line_type") == "dialogue"
            ),
            {},
        )
        mode = str(ledger.get("screen_mode") or shot.get("screen_mode") or "on_camera")
        row = {
            "line_id": line_id,
            "speaker": str(ledger.get("speaker") or ""),
            "spoken_text": str(ledger.get("spoken_ja") or ledger.get("text") or ""),
            "caption_text": str(ledger.get("caption_text") or ledger.get("text") or ""),
            "emotion": str(ledger.get("emotion") or ""),
            "subtext": str(ledger.get("subtext") or ""),
            "action_while_speaking": str(action.get("during") or ""),
            "listener": str(ledger.get("addressee") or ""),
            "scene_state_id": str(
                shot.get("performance_state_id") or ledger.get("scene_state_id") or ""
            ),
            "screen_mode": mode,
            "lipsync_required": mode == "on_camera" and bool(ledger.get("lipsync_required", True)),
            "shot_id": shot_id,
            "audio": {
                "status": "measured" if audio else "pending_tts",
                "duration_sec": audio.get("measured_duration_sec"),
                "sha256": audio.get("audio_sha256"),
                "path": audio.get("path"),
                "pause_before_sec": voice.get("pause_before_sec", 0.0),
                "pause_after_sec": voice.get("pause_after_sec", 0.0),
                "emotion": voice.get("emotion") or ledger.get("emotion") or "",
            },
            "lipsync": {"status": "pending_review" if mode == "on_camera" else "not_required"},
        }
        scenes.setdefault(str(ledger.get("scene_ref") or "unassigned"), []).append(row)
    return {
        "schema_version": 1,
        "kind": "dialogue-scene-package",
        "mode": "dialogue_drama",
        "scenes": [{"scene_id": key, "lines": value} for key, value in scenes.items()],
    }


def validate_dialogue_scene_package(
    package: object,
    *,
    production: bool = False,
    root: Path | str | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(package, dict):
        return {"ok": False, "errors": [{"code": "PACKAGE_INVALID", "message": "invalid package"}]}
    if (
        package.get("schema_version") != 1
        or package.get("kind") != "dialogue-scene-package"
        or package.get("mode") != "dialogue_drama"
        or not isinstance(package.get("scenes"), list)
    ):
        return {"ok": False, "errors": [{"code": "PACKAGE_INVALID", "message": "invalid package"}]}
    film_root = _film_root(root) if production else None
    if production and film_root is None:
        errors.append(
            {
                "code": "PRODUCTION_ROOT_REQUIRED",
                "message": "production validation requires a safe film root",
            }
        )
    for scene in package["scenes"]:
        if (
            not isinstance(scene, dict)
            or not isinstance(scene.get("scene_id"), str)
            or not isinstance(scene.get("lines"), list)
        ):
            errors.append({"code": "SCENE_INVALID", "message": "scene_id and lines are required"})
            continue
        for line in scene["lines"]:
            if not isinstance(line, dict):
                errors.append({"code": "LINE_INVALID", "message": "line must be an object"})
                continue
            lid = str(line.get("line_id") or "")
            missing = sorted(key for key in REQUIRED_LINE_KEYS if key not in line)
            if missing:
                errors.append(
                    {"code": "LINE_FIELDS_MISSING", "message": f"{lid}: {','.join(missing)}"}
                )
            if not lid or lid in seen:
                errors.append(
                    {"code": "LINE_ID_INVALID", "message": f"duplicate/empty line_id: {lid}"}
                )
            seen.add(lid)
            mode = str(line.get("screen_mode") or "")
            if mode not in SCREEN_MODES:
                errors.append({"code": "SCREEN_MODE_INVALID", "message": f"{lid}: {mode}"})
            is_spoken_dialogue = bool(str(line.get("spoken_text") or "").strip())
            if production and is_spoken_dialogue:
                audio = line.get("audio") if isinstance(line.get("audio"), dict) else {}
                try:
                    duration_ok = float(audio.get("duration_sec") or 0) > 0
                except (TypeError, ValueError):
                    duration_ok = False
                audio_evidence_ok = bool(
                    film_root
                    and _verify_evidence(
                        film_root[0],
                        film_root[1],
                        audio.get("path"),
                        audio.get("sha256"),
                        media_type="audio",
                    )
                )
                if audio.get("status") != "measured" or not duration_ok or not audio_evidence_ok:
                    errors.append({"code": "TTS_EVIDENCE_MISSING", "message": lid})
            if mode == "on_camera":
                if line.get("lipsync_required") is not True or not str(
                    line.get("scene_state_id") or ""
                ):
                    errors.append({"code": "ON_CAMERA_CONTRACT_INCOMPLETE", "message": lid})
                if production:
                    lip = line.get("lipsync") if isinstance(line.get("lipsync"), dict) else {}
                    lipsync_evidence_ok = bool(
                        film_root
                        and _verify_evidence(
                            film_root[0],
                            film_root[1],
                            lip.get("artifact_path"),
                            lip.get("artifact_sha256"),
                            media_type="video",
                        )
                    )
                    if (
                        lip.get("status") != "approved"
                        or not str(lip.get("reviewer") or "").strip()
                        or not lipsync_evidence_ok
                    ):
                        errors.append({"code": "LIPSYNC_REVIEW_MISSING", "message": lid})
    if film_root is not None:
        os.close(film_root[1])
    return {"ok": not errors, "errors": errors, "line_count": len(seen)}
