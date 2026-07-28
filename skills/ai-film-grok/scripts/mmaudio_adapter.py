#!/usr/bin/env python3
"""Fail-closed adapter for a pinned, offline MMAudio checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


class MMAudioAdapterError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_checkout(repo: Path) -> tuple[str, str]:
    expected_commit = os.environ.get("AIFILM_MMAUDIO_REPO_COMMIT", "").strip().lower()
    expected_checkpoint = os.environ.get("AIFILM_MMAUDIO_CHECKPOINT_SHA256", "").strip().lower()
    expected_vae = os.environ.get("AIFILM_MMAUDIO_VAE_SHA256", "").strip().lower()
    expected_synchformer = os.environ.get("AIFILM_MMAUDIO_SYNCHFORMER_SHA256", "").strip().lower()
    expected_values = (expected_checkpoint, expected_vae, expected_synchformer)
    if (
        len(expected_commit) != 40
        or any(character not in "0123456789abcdef" for character in expected_commit)
        or any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in expected_values
        )
    ):
        raise MMAudioAdapterError("MMAudio commit and every weight SHA-256 must be pinned")
    try:
        commit = (
            subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            .stdout.strip()
            .lower()
        )
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise MMAudioAdapterError("MMAudio checkout is unavailable") from exc
    if commit != expected_commit or dirty:
        raise MMAudioAdapterError("MMAudio checkout does not match the trusted clean commit")
    required = (
        (repo / "weights" / "mmaudio_large_44k_v2.pth", expected_checkpoint),
        (repo / "ext_weights" / "v1-44.pth", expected_vae),
        (repo / "ext_weights" / "synchformer_state_dict.pth", expected_synchformer),
    )
    if not all(path.is_file() and not path.is_symlink() for path, _digest in required):
        raise MMAudioAdapterError("MMAudio offline weights are incomplete")
    if any(_sha256(path) != digest for path, digest in required):
        raise MMAudioAdapterError("MMAudio weight SHA-256 mismatch")
    return commit, expected_checkpoint


def run(
    *,
    repo: Path,
    prompt: str,
    duration: float,
    seed: int,
    out: Path,
    video: Path | None,
) -> None:
    repo_input = repo.expanduser()
    if repo_input.is_symlink():
        raise MMAudioAdapterError("MMAudio checkout is missing or symlinked")
    repo = repo_input.resolve()
    if not repo.is_dir():
        raise MMAudioAdapterError("MMAudio checkout is missing or symlinked")
    text = prompt.strip()
    if not 1 <= len(text) <= 512:
        raise MMAudioAdapterError("MMAudio prompt must contain 1-512 characters")
    if not 1 <= duration <= 30:
        raise MMAudioAdapterError("MMAudio duration must be between 1 and 30 seconds")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise MMAudioAdapterError("MMAudio seed must be an integer")
    if video is not None and (video.is_symlink() or not video.resolve().is_file()):
        raise MMAudioAdapterError("MMAudio source video is unavailable")
    _require_checkout(repo)

    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    with tempfile.TemporaryDirectory(prefix="aifilm-mmaudio-", dir=out.parent) as temporary:
        output_dir = Path(temporary)
        command = [
            os.environ.get("AIFILM_MMAUDIO_PYTHON", "python"),
            str(repo / "demo.py"),
            "--variant",
            "large_44k_v2",
            "--prompt",
            text,
            "--duration",
            str(duration),
            "--seed",
            str(seed),
            "--num_steps",
            "25",
            "--output",
            str(output_dir),
            "--skip_video_composite",
        ]
        if video is not None:
            command.extend(["--video", str(video.resolve())])
        subprocess.run(
            command,
            cwd=repo,
            env=environment,
            check=True,
            capture_output=True,
            timeout=900,
        )
        generated = list(output_dir.glob("*.flac"))
        if len(generated) != 1:
            raise MMAudioAdapterError("MMAudio did not return exactly one audio artifact")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(generated[0]),
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=180,
        )
    if not out.is_file() or out.stat().st_size < 512:
        out.unlink(missing_ok=True)
        raise MMAudioAdapterError("MMAudio normalized output is missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="")
    parser.add_argument("--video", default="")
    args = parser.parse_args()
    if args.probe:
        repo_input = Path(args.repo).expanduser()
        if repo_input.is_symlink():
            raise MMAudioAdapterError("MMAudio checkout is missing or symlinked")
        repo = repo_input.resolve()
        commit, checkpoint = _require_checkout(repo)
        print(
            json.dumps(
                {
                    "ok": True,
                    "model": "hkchengrex/MMAudio-large-44k-v2",
                    "license": "CC-BY-NC-4.0",
                    "repo_commit": commit,
                    "checkpoint_sha256": checkpoint,
                },
                separators=(",", ":"),
            )
        )
        return 0
    if not args.out:
        raise MMAudioAdapterError("--out is required for rendering")
    run(
        repo=Path(args.repo),
        prompt=args.prompt,
        duration=args.duration,
        seed=args.seed,
        out=Path(args.out),
        video=Path(args.video) if args.video else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
