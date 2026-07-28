#!/usr/bin/env python3
"""Measure a WSL lip-sync backend instead of trusting deployment labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--adapter", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    checkpoint = Path(args.checkpoint).resolve()
    adapter = Path(args.adapter).resolve()
    if not root.is_dir() or not checkpoint.is_file() or not adapter.is_file():
        raise SystemExit("backend probe path is missing")

    import torch

    payload = {
        "repo_commit": _git(root, "rev-parse", "HEAD"),
        "repo_dirty": bool(_git(root, "status", "--porcelain")),
        "checkpoint_sha256": _sha256(checkpoint),
        "adapter_sha256": _sha256(adapter),
        "python": platform.python_version(),
        "pytorch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "compute_capability": (
            list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None
        ),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
