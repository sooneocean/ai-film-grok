"""Resolve the hash-bound final artifact recorded in a film manifest."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from security_policy import SecurityPolicyError, safe_existing_file
from util import read_json, sha256_file, utc_now, write_json
from util.errors import FilmError

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class FinalArtifact:
    path: Path
    sha256: str


class DeliveryArtifactError(FilmError):
    pass


def desktop_delivery_is_current(
    outputs: object,
    final_record: object,
) -> bool:
    if not isinstance(outputs, Mapping) or not isinstance(final_record, Mapping):
        return False
    record = outputs.get("desktop_delivery")
    if not isinstance(record, Mapping):
        return False
    final_hash = str(final_record.get("sha256") or "")
    if not final_hash or record.get("final_output_sha256") != final_hash:
        return False
    manifest = Path(str(record.get("path") or "")).expanduser()
    readback_path = Path(str(record.get("readback_path") or "")).expanduser()
    directory = Path(str(record.get("directory") or "")).expanduser()
    if (
        not directory.is_dir()
        or not manifest.is_file()
        or manifest.is_symlink()
        or not readback_path.is_file()
        or readback_path.is_symlink()
        or manifest.parent.parent != directory
        or readback_path.parent != directory / "成片"
    ):
        return False
    try:
        if sha256_file(manifest) != record.get("sha256") or sha256_file(
            readback_path
        ) != record.get("readback_sha256"):
            return False
        manifest_payload = read_json(manifest)
        readback = read_json(readback_path)
    except OSError:
        return False
    if (
        not isinstance(manifest_payload, dict)
        or manifest_payload.get("kind") != "desktop-delivery-manifest"
        or not isinstance(readback, dict)
        or readback.get("kind") != "desktop-delivery-readback"
        or readback.get("ok") is not True
        or manifest_payload.get("readback") != readback
    ):
        return False
    artifacts = readback.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    for item in artifacts:
        if not (
            isinstance(item, dict)
            and item.get("source_sha256") == final_hash
            and item.get("copied_sha256") == final_hash
            and item.get("hash_match") is True
            and (item.get("decode") or {}).get("ok") is True
        ):
            continue
        relative = Path(str(item.get("path") or ""))
        if relative.is_absolute() or len(relative.parts) != 1 or relative.name in {"", ".", ".."}:
            return False
        copied_final = directory / "成片" / relative
        try:
            return bool(
                copied_final.is_file()
                and not copied_final.is_symlink()
                and sha256_file(copied_final) == final_hash
            )
        except OSError:
            return False
    return False


def _run_media_readback(path: Path, *, require_audio: bool) -> dict[str, JsonValue]:
    probe_command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size:"
            "stream=index,codec_type,codec_name,width,height,sample_rate,channels"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        probe_process = subprocess.run(
            probe_command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeliveryArtifactError(f"ffprobe read-back failed for {path.name}: {exc}") from exc
    if probe_process.returncode != 0:
        raise DeliveryArtifactError(
            f"ffprobe read-back failed for {path.name}: {probe_process.stderr.strip()}"
        )
    try:
        probe = json.loads(probe_process.stdout)
    except json.JSONDecodeError as exc:
        raise DeliveryArtifactError(f"ffprobe returned invalid JSON for {path.name}") from exc
    streams = probe.get("streams") if isinstance(probe, dict) else None
    if not isinstance(streams, list) or not any(
        isinstance(item, dict) and item.get("codec_type") == "video" for item in streams
    ):
        raise DeliveryArtifactError(f"exported media has no decodable video stream: {path.name}")
    if require_audio and not any(
        isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams
    ):
        raise DeliveryArtifactError(f"exported final media has no audio stream: {path.name}")
    try:
        duration = float((probe.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise DeliveryArtifactError(f"exported media duration is invalid: {path.name}") from exc
    if duration <= 0:
        raise DeliveryArtifactError(f"exported media duration is not positive: {path.name}")

    decode_command = [
        "ffmpeg",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-f",
        "null",
        "-",
    ]
    try:
        decode_process = subprocess.run(
            decode_command,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeliveryArtifactError(f"decode read-back failed for {path.name}: {exc}") from exc
    if decode_process.returncode != 0:
        raise DeliveryArtifactError(
            f"decode read-back failed for {path.name}: {decode_process.stderr.strip()}"
        )
    return {
        "probe": probe,
        "decode": {
            "ok": True,
            "command": "ffmpeg -v error -xerror -i <exported> -map 0:v:0 -map 0:a? -f null -",
        },
    }


def _verify_exported_video(
    source: Path,
    copied: Path,
    *,
    require_audio: bool,
) -> dict[str, JsonValue]:
    source_hash = sha256_file(source)
    copied_hash = sha256_file(copied)
    if copied_hash != source_hash:
        raise DeliveryArtifactError(f"exported copy hash does not match source: {copied.name}")
    readback = _run_media_readback(copied, require_audio=require_audio)
    return {
        "path": copied.name,
        "source_sha256": source_hash,
        "copied_sha256": copied_hash,
        "hash_match": True,
        **readback,
    }


def resolve_final_artifact(root: Path, manifest: Mapping[str, JsonValue]) -> FinalArtifact:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise DeliveryArtifactError("manifest outputs are missing")
    record = outputs.get("final_film")
    if not isinstance(record, Mapping):
        raise DeliveryArtifactError("manifest final_film is missing")
    raw_path = record.get("path")
    expected_hash = record.get("sha256")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise DeliveryArtifactError("manifest final_film path is missing")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise DeliveryArtifactError("manifest final_film hash is missing")

    relative = Path(raw_path)
    try:
        if relative.is_absolute():
            path = safe_existing_file(root, relative, field="final film")
        elif len(relative.parts) == 1:
            path = safe_existing_file(root / "out", relative, field="final film")
        elif relative.parts[0] == "out":
            path = safe_existing_file(root, relative, field="final film")
        else:
            raise DeliveryArtifactError("manifest final_film path must be inside out/")
    except SecurityPolicyError as exc:
        raise DeliveryArtifactError(str(exc)) from exc

    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise DeliveryArtifactError("manifest final_film hash does not match the file")
    return FinalArtifact(path=path, sha256=actual_hash)


def export_final_artifacts(
    root: Path, manifest: Mapping[str, JsonValue], destination: Path
) -> list[Path]:
    if not destination.is_dir():
        raise DeliveryArtifactError("final export destination is missing")
    artifact = resolve_final_artifact(root, manifest)
    copied_final = Path(shutil.copy2(artifact.path, destination / artifact.path.name))
    copied = [copied_final]
    readbacks = [
        _verify_exported_video(
            artifact.path,
            copied_final,
            require_audio=True,
        )
    ]
    silent = root / "out" / "film_silent.mp4"
    if silent.is_file() and silent.resolve() != artifact.path.resolve():
        copied_silent = Path(shutil.copy2(silent, destination / silent.name))
        copied.append(copied_silent)
        readbacks.append(
            _verify_exported_video(
                silent,
                copied_silent,
                require_audio=False,
            )
        )
    write_json(
        destination / "delivery-readback.json",
        {
            "schema_version": 1,
            "kind": "desktop-delivery-readback",
            "ok": True,
            "verified_at": utc_now(),
            "artifacts": readbacks,
        },
    )
    return copied
