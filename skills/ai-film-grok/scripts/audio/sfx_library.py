"""Global, signed internal non-commercial SFX armory.

The armory owns approved bytes and their review evidence.  A film stores only
``library:`` references plus its project-bound attachment receipt, so a sound
can be reused without becoming a per-project copy.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from audio_node_client import _validate_wav
from performance_candidates import receipt_is_signed, sign_receipt
from util import read_json, write_json

_ASSET_ID = re.compile(r"^mmaudio-sfx-[a-z0-9_-]{1,64}$")
_APPROVED = "approved_noncommercial"
_SCOPE = "noncommercial_internal"
_PREFIX = "sfx/approved-noncommercial/"
_PENDING_PREFIX = "sfx/pending-noncommercial/"


class SFXLibraryError(RuntimeError):
    pass


def default_library_root() -> Path:
    """Return the user-wide armory, with an explicit local override."""
    raw = os.environ.get("AIFILM_SFX_LIBRARY_ROOT", "").strip()
    return (
        Path(raw).expanduser().resolve()
        if raw
        else (Path.home() / "AI FILM SPACE" / "audio-armory").resolve()
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        raise SFXLibraryError("library path is invalid")
    root = root.expanduser().resolve()
    path = root / relative_path
    current = root
    for part in relative_path.parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise SFXLibraryError("library path must not contain symlinks")
    try:
        if not path.resolve().is_relative_to(root):
            raise SFXLibraryError("library path escapes armory")
    except OSError as exc:
        raise SFXLibraryError("library path is invalid") from exc
    return path


def _approved_relative(asset_id: str, *, receipt: bool = False) -> str:
    if not _ASSET_ID.fullmatch(asset_id):
        raise SFXLibraryError("invalid SFX asset id")
    suffix = ".receipt.json" if receipt else ".wav"
    return f"{_PREFIX}{asset_id}{suffix}"


def _review_relative(asset_id: str) -> str:
    if not _ASSET_ID.fullmatch(asset_id):
        raise SFXLibraryError("invalid SFX asset id")
    return f"sfx/reviews/{asset_id}.vibevoice-asr-review.json"


def _pending_relative(asset_id: str, *, receipt: bool = False) -> str:
    if not _ASSET_ID.fullmatch(asset_id):
        raise SFXLibraryError("invalid SFX asset id")
    suffix = ".receipt.json" if receipt else ".wav"
    return f"{_PENDING_PREFIX}{asset_id}{suffix}"


def _candidate_review_relative(asset_id: str) -> str:
    if not _ASSET_ID.fullmatch(asset_id):
        raise SFXLibraryError("invalid SFX asset id")
    return f"sfx/reviews/candidates/{asset_id}.vibevoice-asr-review.json"


def _prepare(root: Path) -> Path:
    root = root.expanduser().resolve()
    for relative in (
        "sfx",
        "sfx/approved-noncommercial",
        "sfx/pending-noncommercial",
        "sfx/reviews",
        "sfx/reviews/candidates",
    ):
        path = _safe(root, relative)
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise SFXLibraryError("library directory must not be symlinked")
    return root


def _candidate_record(project_root: Path, asset_id: str) -> tuple[Path, Path, dict[str, Any]]:
    if not _ASSET_ID.fullmatch(asset_id):
        raise SFXLibraryError("invalid SFX asset id")
    pending = project_root / "audio" / "candidates" / "sfx" / "pending"
    receipt = pending / f"{asset_id}.json"
    wav = pending / f"{asset_id}.wav"
    record = read_json(receipt)
    if (
        not isinstance(record, dict)
        or not receipt_is_signed(record)
        or record.get("asset_id") != asset_id
        or record.get("status") != "pending_human_review"
        or record.get("production_eligible") is not False
        or record.get("usage_scope") != "noncommercial_internal_research"
        or record.get("license") != "CC-BY-NC-4.0"
        or record.get("path") != str(wav.relative_to(project_root))
        or not wav.is_file()
        or wav.is_symlink()
        or _sha256(wav) != record.get("sha256")
    ):
        raise SFXLibraryError("project SFX candidate does not bind pending bytes")
    _validate_wav(wav)
    return wav, receipt, record


def stage_project_candidate(
    project_root: Path, asset_id: str, *, library_root: Path | None = None
) -> dict[str, Any]:
    """Copy a pending take to the global review vault without approving it.

    The vault is deliberately a copy, not a symlink: project cleanup must never
    invalidate the WAV offered for human listening.
    """
    project_root = project_root.expanduser().resolve()
    source_wav, source_receipt, record = _candidate_record(project_root, asset_id)
    root = _prepare(library_root or default_library_root())
    destination = _safe(root, _pending_relative(asset_id))
    _copy_once(source_wav, destination)

    canonical = dict(record)
    canonical["pending_path"] = _pending_relative(asset_id)
    canonical["library_scope"] = "global_candidate_review_vault"
    canonical["staged_at"] = datetime.now(UTC).isoformat()
    canonical["project_origin"] = {
        "project_root_sha256": hashlib.sha256(str(project_root).encode()).hexdigest(),
        "candidate_receipt_sha256": _sha256(source_receipt),
    }
    screen = canonical.get("asr_speech_screen")
    if isinstance(screen, dict):
        raw = str(screen.get("receipt") or "")
        if not raw.startswith("local:"):
            raise SFXLibraryError("project SFX candidate ASR receipt is invalid")
        screen_source = project_root / raw.removeprefix("local:")
        if not screen_source.is_file() or screen_source.is_symlink():
            raise SFXLibraryError("project SFX candidate ASR receipt is unavailable")
        review_destination = _safe(root, _candidate_review_relative(asset_id))
        _copy_once(screen_source, review_destination)
        canonical["asr_speech_screen"] = _canonical_screen(
            screen,
            report_path=review_destination,
            audio_sha256=str(canonical["sha256"]),
            asset_id=asset_id,
        )
        canonical["asr_speech_screen"]["receipt"] = (
            f"library:{_candidate_review_relative(asset_id)}"
        )
    sign_receipt(canonical)
    receipt_destination = _safe(root, _pending_relative(asset_id, receipt=True))
    write_json(receipt_destination, canonical)
    return {
        "asset_id": asset_id,
        "library_root": str(root),
        "source": f"library:{_pending_relative(asset_id)}",
        "receipt": f"library:{_pending_relative(asset_id, receipt=True)}",
        "sha256": canonical["sha256"],
        "status": "pending_human_review",
        "production_eligible": False,
    }


def _copy_once(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_symlink() or _sha256(destination) != _sha256(source):
            raise SFXLibraryError("library asset id already belongs to different bytes")
        return
    temporary = destination.with_name(f".{destination.name}.partial")
    if temporary.exists() or temporary.is_symlink():
        raise SFXLibraryError("library temporary output already exists")
    shutil.copyfile(source, temporary)
    if _sha256(temporary) != _sha256(source):
        temporary.unlink(missing_ok=True)
        raise SFXLibraryError("library copy hash mismatch")
    os.replace(temporary, destination)


def _canonical_screen(
    screen: dict[str, Any], *, report_path: Path, audio_sha256: str, asset_id: str
) -> dict[str, Any]:
    """Rebind legacy ASR evidence to the exact imported report bytes."""
    report = read_json(report_path)
    provider = report.get("provider") if isinstance(report, dict) else None
    audio = report.get("inputs", {}).get("audio") if isinstance(report, dict) else None
    segments = report.get("transcript", {}).get("segments") if isinstance(report, dict) else None
    if (
        not isinstance(provider, dict)
        or not isinstance(audio, dict)
        or not isinstance(segments, list)
        or report.get("kind") != "vibevoice-asr-review"
        or report.get("status") != "candidate_only"
        or report.get("human_review_required") is not True
        or audio.get("sha256") != audio_sha256
        or not provider.get("transcript_sha256")
    ):
        raise SFXLibraryError("legacy ASR review evidence is invalid")
    non_speech = {
        "[silence]",
        "silence",
        "[静音]",
        "静音",
        "[environmental sounds]",
        "environmental sounds",
    }
    speech_like = sum(
        1
        for entry in segments
        if isinstance(entry, dict)
        and str(entry.get("text") or "").strip()
        and str(entry.get("text") or "").strip().casefold() not in non_speech
    )
    return {
        **screen,
        "status": "completed_candidate_signal",
        "receipt": f"library:{_review_relative(asset_id)}",
        "audio_sha256": audio_sha256,
        "report_sha256": _sha256(report_path),
        "transcript_sha256": provider["transcript_sha256"],
        "segment_count": len(segments),
        "speech_like_segment_count": speech_like,
        "speech_like_flagged": speech_like > 0,
    }


def import_project_asset(
    project_root: Path, asset_id: str, *, library_root: Path | None = None
) -> dict[str, Any]:
    """Promote a legacy project-approved take into the global canonical armory."""
    if not _ASSET_ID.fullmatch(asset_id):
        raise SFXLibraryError("invalid SFX asset id")
    project_root = project_root.expanduser().resolve()
    source_receipt = project_root / _approved_relative(asset_id, receipt=True).replace(
        "sfx/approved-noncommercial/", "audio/candidates/sfx/approved-noncommercial/"
    )
    source_wav = project_root / _approved_relative(asset_id).replace(
        "sfx/approved-noncommercial/", "audio/candidates/sfx/approved-noncommercial/"
    )
    record = read_json(source_receipt)
    if not isinstance(record, dict) or not receipt_is_signed(record):
        raise SFXLibraryError("legacy approved SFX receipt is invalid")
    if (
        record.get("asset_id") != asset_id
        or record.get("status") != _APPROVED
        or record.get("production_eligible") is not False
        or record.get("delivery_eligible_scopes") != [_SCOPE]
        or record.get("license") != "CC-BY-NC-4.0"
        or not source_wav.is_file()
        or source_wav.is_symlink()
        or _sha256(source_wav) != record.get("sha256")
    ):
        raise SFXLibraryError("legacy approved SFX does not bind its bytes and NC scope")
    _validate_wav(source_wav)
    screen = record.get("asr_speech_screen")
    screen_raw = str(screen.get("receipt") or "") if isinstance(screen, dict) else ""
    if not screen_raw.startswith("local:"):
        raise SFXLibraryError("legacy approved SFX lacks an ASR review receipt")
    screen_source = project_root / screen_raw.removeprefix("local:")
    if not screen_source.is_file() or screen_source.is_symlink():
        raise SFXLibraryError("legacy ASR review receipt is unavailable")

    root = _prepare(library_root or default_library_root())
    destination = _safe(root, _approved_relative(asset_id))
    review_destination = _safe(root, _review_relative(asset_id))
    _copy_once(source_wav, destination)
    _copy_once(screen_source, review_destination)

    canonical = dict(record)
    canonical["approved_path"] = _approved_relative(asset_id)
    canonical["library_scope"] = "global_internal_noncommercial_armory"
    canonical["imported_at"] = datetime.now(UTC).isoformat()
    canonical["legacy_origin"] = {
        "project_root_sha256": hashlib.sha256(str(project_root).encode()).hexdigest(),
        "approval_receipt_sha256": _sha256(source_receipt),
    }
    canonical["asr_speech_screen"] = _canonical_screen(
        screen,
        report_path=review_destination,
        audio_sha256=str(canonical["sha256"]),
        asset_id=asset_id,
    )
    sign_receipt(canonical)
    receipt_destination = _safe(root, _approved_relative(asset_id, receipt=True))
    write_json(receipt_destination, canonical)
    return {
        "asset_id": asset_id,
        "library_root": str(root),
        "source": f"library:{_approved_relative(asset_id)}",
        "approval_receipt": f"library:{_approved_relative(asset_id, receipt=True)}",
        "sha256": canonical["sha256"],
    }


def resolve_uri(raw: str, *, library_root: Path | None = None, require_file: bool = True) -> Path:
    if not raw.startswith("library:"):
        raise SFXLibraryError("not a library URI")
    root = (library_root or default_library_root()).expanduser().resolve()
    path = _safe(root, raw.removeprefix("library:"))
    if require_file and (not path.is_file() or path.is_symlink()):
        raise SFXLibraryError("library asset is unavailable")
    return path


def approved_asset(
    asset_id: str, *, library_root: Path | None = None
) -> tuple[Path, Path, dict[str, Any]]:
    root = (library_root or default_library_root()).expanduser().resolve()
    wav = resolve_uri(f"library:{_approved_relative(asset_id)}", library_root=root)
    receipt = resolve_uri(
        f"library:{_approved_relative(asset_id, receipt=True)}", library_root=root
    )
    record = read_json(receipt)
    if not isinstance(record, dict) or not receipt_is_signed(record):
        raise SFXLibraryError("global SFX receipt is invalid")
    if (
        record.get("asset_id") != asset_id
        or record.get("status") != _APPROVED
        or record.get("approved_path") != _approved_relative(asset_id)
        or record.get("sha256") != _sha256(wav)
        or record.get("license") != "CC-BY-NC-4.0"
        or record.get("production_eligible") is not False
        or record.get("delivery_eligible_scopes") != [_SCOPE]
    ):
        raise SFXLibraryError("global SFX receipt does not bind approved bytes")
    return wav, receipt, record


def candidate_asset(
    asset_id: str, *, library_root: Path | None = None
) -> tuple[Path, Path, dict[str, Any]]:
    """Return a globally retained candidate; this never confers approval."""
    root = (library_root or default_library_root()).expanduser().resolve()
    wav = resolve_uri(f"library:{_pending_relative(asset_id)}", library_root=root)
    receipt = resolve_uri(f"library:{_pending_relative(asset_id, receipt=True)}", library_root=root)
    record = read_json(receipt)
    if (
        not isinstance(record, dict)
        or not receipt_is_signed(record)
        or record.get("asset_id") != asset_id
        or record.get("status") != "pending_human_review"
        or record.get("production_eligible") is not False
        or record.get("usage_scope") != "noncommercial_internal_research"
        or record.get("license") != "CC-BY-NC-4.0"
        or record.get("pending_path") != _pending_relative(asset_id)
        or record.get("sha256") != _sha256(wav)
    ):
        raise SFXLibraryError("global SFX candidate receipt does not bind pending bytes")
    return wav, receipt, record


def write_candidate_review_pack(name: str, *, library_root: Path | None = None) -> dict[str, Any]:
    """Write a local listening list backed only by retained global candidate bytes."""
    safe_name = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-")
    if not safe_name:
        raise SFXLibraryError("review pack name is invalid")
    root = _prepare(library_root or default_library_root())
    pending = _safe(root, "sfx/pending-noncommercial")
    rows: list[tuple[str, str, str]] = []
    for receipt in sorted(pending.glob("*.receipt.json")):
        asset_id = receipt.name.removesuffix(".receipt.json")
        try:
            _, _, record = candidate_asset(asset_id, library_root=root)
        except SFXLibraryError:
            continue
        screen = record.get("asr_speech_screen")
        if not isinstance(screen, dict) or screen.get("speech_like_flagged") is not False:
            continue
        rows.append((asset_id, str(record.get("seed") or ""), _pending_relative(asset_id)))
    pack_dir = _safe(root, "sfx/review-packs")
    pack_dir.mkdir(parents=True, exist_ok=True)
    path = _safe(root, f"sfx/review-packs/{safe_name}.md")
    lines = [
        f"# {safe_name} · ASR 通过待试听",
        "",
        "这些是 MMAudio 的非商用研究候选。ASR 未侦测到语音不代表批准；请完整试听后逐条签收。",
        "",
        "| 资产 | 种子 | 音频 |",
        "|---|---:|---|",
    ]
    lines.extend(
        f"| `{asset_id}` | {seed} | [试听]({quote(str(root / relative), safe='/')}) |"
        for asset_id, seed, relative in rows
    )
    if not rows:
        lines.append("| — | — | 暂无通过 ASR 的全局候选 |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "candidate_count": len(rows),
        "status": "pending_human_review",
        "approval": "human_listening_required",
    }


def _asr_review_valid(record: dict[str, Any], *, library_root: Path | None = None) -> bool:
    screen = record.get("asr_speech_screen")
    if not isinstance(screen, dict):
        return False
    try:
        asset_id = str(record.get("asset_id") or "")
        if screen.get("receipt") != f"library:{_review_relative(asset_id)}":
            return False
        report_path = resolve_uri(str(screen["receipt"]), library_root=library_root)
        report = read_json(report_path)
        provider = report.get("provider") if isinstance(report, dict) else None
        audio = report.get("inputs", {}).get("audio") if isinstance(report, dict) else None
        segments = (
            report.get("transcript", {}).get("segments") if isinstance(report, dict) else None
        )
        if (
            not isinstance(provider, dict)
            or not isinstance(audio, dict)
            or not isinstance(segments, list)
        ):
            return False
        non_speech = {
            "[silence]",
            "silence",
            "[静音]",
            "静音",
            "[environmental sounds]",
            "environmental sounds",
        }
        speech_like = sum(
            1
            for entry in segments
            if isinstance(entry, dict)
            and str(entry.get("text") or "").strip()
            and str(entry.get("text") or "").strip().casefold() not in non_speech
        )
        return bool(
            screen.get("status") == "completed_candidate_signal"
            and report.get("kind") == "vibevoice-asr-review"
            and report.get("status") == "candidate_only"
            and report.get("human_review_required") is True
            and audio.get("sha256") == record.get("sha256") == screen.get("audio_sha256")
            and provider.get("transcript_sha256") == screen.get("transcript_sha256")
            and _sha256(report_path) == screen.get("report_sha256")
            and len(segments) == screen.get("segment_count")
            and speech_like == screen.get("speech_like_segment_count")
        )
    except (KeyError, OSError, SFXLibraryError):
        return False


def approved_event_receipt_valid(
    event: dict[str, Any], *, library_root: Path | None = None
) -> bool:
    source = str(event.get("source") or "")
    receipt = str(event.get("approval_receipt") or "")
    if not source.startswith("library:") or not receipt.startswith("library:"):
        return False
    try:
        asset_id = Path(source.removeprefix("library:")).stem
        wav, receipt_path, record = approved_asset(asset_id, library_root=library_root)
        review = record.get("human_review")
        return bool(
            source == f"library:{record['approved_path']}"
            and receipt == f"library:{_approved_relative(asset_id, receipt=True)}"
            and receipt_path.is_file()
            and _sha256(wav) == event.get("source_sha256")
            and record.get("model") == event.get("model") == "hkchengrex/MMAudio-large-44k-v2"
            and record.get("checkpoint_fingerprint") == event.get("checkpoint_fingerprint")
            and record.get("node_job_id") == event.get("node_job_id")
            and _asr_review_valid(record, library_root=library_root)
            and isinstance(review, dict)
            and review.get("reviewer")
            and all(
                review.get(key) is True
                for key in (
                    "heard_full",
                    "sync_confirmed",
                    "no_speech_confirmed",
                    "no_music_confirmed",
                    "artifact_free_confirmed",
                    "asr_speech_reviewed",
                )
            )
        )
    except (OSError, SFXLibraryError):
        return False


def audit(*, library_root: Path | None = None) -> dict[str, Any]:
    root = (library_root or default_library_root()).expanduser().resolve()
    approved = _safe(root, "sfx/approved-noncommercial")
    asset_ids: list[str] = []
    hashes: set[str] = set()
    invalid: list[str] = []
    candidate_ids: list[str] = []
    invalid_candidates: list[str] = []
    if not approved.exists():
        return {
            "library_root": str(root),
            "approved_count": 0,
            "unique_sha256_count": 0,
            "candidate_count": 0,
            "invalid_candidates": [],
            "invalid": [],
            "target_100_ready": False,
        }
    for receipt in sorted(approved.glob("*.receipt.json")):
        asset_id = receipt.name.removesuffix(".receipt.json")
        try:
            _, _, record = approved_asset(asset_id, library_root=root)
            if not _asr_review_valid(record, library_root=root):
                raise SFXLibraryError("global SFX ASR review evidence is invalid")
            asset_ids.append(asset_id)
            hashes.add(str(record["sha256"]))
        except SFXLibraryError:
            invalid.append(asset_id)
    pending = _safe(root, "sfx/pending-noncommercial")
    if pending.exists():
        for receipt in sorted(pending.glob("*.receipt.json")):
            asset_id = receipt.name.removesuffix(".receipt.json")
            try:
                candidate_asset(asset_id, library_root=root)
                candidate_ids.append(asset_id)
            except SFXLibraryError:
                invalid_candidates.append(asset_id)
    return {
        "library_root": str(root),
        "approved_count": len(asset_ids),
        "unique_sha256_count": len(hashes),
        "candidate_count": len(candidate_ids),
        "candidate_asset_ids": candidate_ids,
        "invalid_candidates": invalid_candidates,
        "asset_ids": asset_ids,
        "invalid": invalid,
        "target_100_ready": len(asset_ids) >= 100 and not invalid,
    }
