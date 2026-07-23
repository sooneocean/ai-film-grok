#!/usr/bin/env python3
"""Real-footage ingestion + transcription path (video-use bridge).

Bridges ai-film-grok to the ``video-use`` skill so the pipeline can ingest real
footage (talking heads, interviews, b-roll) for editing — the one stage that was
previously absent (the pipeline assumed only generated clips).

This module:
  1. Copies a source video into ``footage/raw/`` (immutable input).
  2. Invokes video-use's ``transcribe.py`` (local Whisper, word-level, cached) →
     ``footage/transcripts/<name>.json``.
  3. Invokes ``pack_transcripts.py`` → ``footage/takes_packed.md`` (phrase-level
     primary reading view for the editor sub-agent).
  4. Writes a receipt at ``receipts/footage-ingest/<source_id>.json``.

Hard-rule alignment with video-use:
  - Word-level verbatim ASR only (never SRT/phrase mode).
  - Cache transcripts per source (never re-transcribe unless the source changed).
  - Outputs under ``<root>/footage/`` — never inside the video-use project.

Does NOT call any cloud ASR API — local faster-whisper only.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import sha256_file, write_json


class RealFootageError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# video-use skill helpers live under this absolute path (symlinked skill root)
def video_use_dir() -> Path:
    """Resolve the video-use skill directory."""
    home = Path.home()
    candidates = [
        home / ".grok" / "skills" / "video-use",
        home / ".agents" / "skills" / "video-use",
        home / ".claude" / "skills" / "video-use",
        home / ".codex" / "skills" / "video-use",
    ]
    for c in candidates:
        if (c / "helpers" / "transcribe.py").is_file():
            return c.resolve()
    raise RealFootageError(
        "video-use skill not found (need helpers/transcribe.py). "
        "Install video-use or symlink ~/.grok/skills/video-use."
    )


def footage_dirs(root: Path | str) -> dict[str, Path]:
    """Create and return the footage subdirectories under a film root."""
    root = Path(root).expanduser().resolve()
    out: dict[str, Path] = {"root": root}
    for name in ("raw", "transcripts"):
        d = root / "footage" / name
        d.mkdir(parents=True, exist_ok=True)
        out[name] = d
    out["edit"] = root / "footage" / "edit"
    out["edit"].mkdir(parents=True, exist_ok=True)
    return out


def _source_id(source: Path) -> str:
    stem = source.stem
    # Keep it filesystem-safe
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem).strip("_")
    digest = sha256_file(source)[:8]
    return f"{safe}_{digest}"


def transcribe(source: Path, *, model: str = "base") -> Path:
    """Run video-use transcribe.py on *source* → cached word-level JSON.

    Idempotent: returns existing transcript if the source hash is unchanged.
    """
    vu = video_use_dir()
    helper = vu / "helpers" / "transcribe.py"
    out = source.parent / f"{source.stem}.json"
    # Cache check: skip if transcript exists and is newer than source
    if out.is_file() and out.stat().st_mtime >= source.stat().st_mtime:
        return out
    proc = subprocess.run(
        [shutil.which("python3") or "python3", str(helper), str(source),
         "--model", model],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if proc.returncode != 0 or not out.is_file():
        raise RealFootageError(
            f"transcribe.py failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '')[:300]}"
        )
    return out


def pack_transcripts(transcripts_dir: Path, edit_dir: Path) -> Path:
    """Run pack_transcripts.py → takes_packed.md in *edit_dir*."""
    vu = video_use_dir()
    helper = vu / "helpers" / "pack_transcripts.py"
    out = edit_dir / "takes_packed.md"
    proc = subprocess.run(
        [shutil.which("python3") or "python3", str(helper),
         "--edit-dir", str(edit_dir)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0 or not out.is_file():
        raise RealFootageError(
            f"pack_transcripts.py failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '')[:300]}"
        )
    return out


def ingest_footage(
    root: Path | str,
    source: Path | str,
    *,
    label: str | None = None,
    whisper_model: str = "base",
) -> dict[str, Any]:
    """Ingest one real-footage source: copy → transcribe → pack → receipt.

    Returns the receipt dict. Idempotent: re-running on the same source is a no-op
    except for re-packing (cheap).
    """
    root = Path(root).expanduser().resolve()
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise RealFootageError(f"footage source not found: {source}")

    dirs = footage_dirs(root)
    sid = _source_id(source)
    dest = dirs["raw"] / f"{sid}{source.suffix}"

    # Copy if missing or hash differs (immutable input)
    if not dest.is_file() or sha256_file(dest) != sha256_file(source):
        shutil.copy2(source, dest)

    # Transcribe (cached per source)
    transcript = transcribe(dest, model=whisper_model)
    # Move/copy transcript into footage/transcripts/<sid>.json (canonical name)
    canon_transcript = dirs["transcripts"] / f"{sid}.json"
    if transcript.resolve() != canon_transcript.resolve():
        shutil.copy2(transcript, canon_transcript)

    # Pack all transcripts → takes_packed.md
    packed = pack_transcripts(dirs["transcripts"], dirs["edit"])

    receipt = {
        "schema_version": 1,
        "kind": "footage-ingest",
        "ok": True,
        "source_id": sid,
        "label": label or source.stem,
        "source_path": str(dest),
        "source_sha256": sha256_file(dest),
        "transcript_path": str(canon_transcript),
        "takes_packed_path": str(packed),
        "whisper_model": whisper_model,
        "source_type": "real_footage",
        "created_at": utc_now(),
        "note": "Local Whisper word-level ASR (cached per source); no cloud API.",
    }
    out = root / "receipts" / "footage-ingest" / f"{sid}.json"
    write_json(out, receipt)
    receipt["path"] = str(out)
    return receipt


def list_ingested(root: Path | str) -> list[dict[str, Any]]:
    """List all ingested footage receipts for a film root."""
    import json

    root = Path(root).expanduser().resolve()
    receipt_dir = root / "receipts" / "footage-ingest"
    if not receipt_dir.is_dir():
        return []
    items = []
    for p in sorted(receipt_dir.glob("*.json")):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except OSError:
            continue
    return items
