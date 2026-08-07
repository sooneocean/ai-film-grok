#!/usr/bin/env python3
"""Trust-on-explicit-acknowledgement locks for local lip-sync repos and weights."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from runtime_policy import sha256
from security_policy import atomic_write_text, minimal_subprocess_env
from util import utc_now

BACKEND_FILES = {
    "wav2lip": {
        "entrypoints": ("inference.py", "aifilm_infer.py"),
        "weights": ("checkpoints/*.pth", "**/*.safetensors", "**/*.onnx"),
    },
    "musetalk": {
        "entrypoints": ("aifilm_infer.py", "scripts/aifilm_infer.py", "scripts/inference.py"),
        "weights": (
            "models/**/*.pth",
            "models/**/*.bin",
            "models/**/*.safetensors",
            "models/**/*.onnx",
        ),
    },
}


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=20,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def backend_fingerprint(kind: str, root: Path) -> dict[str, Any]:
    if kind not in BACKEND_FILES:
        raise ValueError(f"unknown backend {kind}")
    resolved = root.expanduser().resolve()
    entrypoints: dict[str, str] = {}
    for relative in BACKEND_FILES[kind]["entrypoints"]:
        path = resolved / relative
        if path.is_file() and not path.is_symlink():
            entrypoints[relative] = sha256(path)
    weights: dict[str, dict[str, Any]] = {}
    seen: set[Path] = set()
    for pattern in BACKEND_FILES[kind]["weights"]:
        for path in sorted(resolved.glob(pattern)):
            if not path.is_file() or path.is_symlink() or path in seen:
                continue
            seen.add(path)
            relative = str(path.relative_to(resolved))
            weights[relative] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    status = _git(resolved, "status", "--porcelain")
    return {
        "kind": kind,
        "git_commit": _git(resolved, "rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "entrypoints": entrypoints,
        "weights": weights,
    }


def create_lock_entry(kind: str, root: Path, *, trusted_weights: bool) -> dict[str, Any]:
    return {
        "root": str(root.expanduser().resolve()),
        "trusted_weights": bool(trusted_weights),
        "locked_at": utc_now(),
        "fingerprint": backend_fingerprint(kind, root),
    }


def verify_backend_lock(kind: str, root: Path, lock_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"backend lock missing or unreadable: {exc}"]}
    entry = (lock.get("backends") or {}).get(kind)
    if not isinstance(entry, dict):
        return {"ok": False, "errors": [f"backend {kind} is not locked"]}
    if entry.get("root") != str(root.expanduser().resolve()):
        errors.append("backend root does not match lock")
    if entry.get("trusted_weights") is not True:
        errors.append("weights are not explicitly trusted")
    current = backend_fingerprint(kind, root)
    if entry.get("fingerprint") != current:
        errors.append("backend fingerprint changed")
    if current.get("git_dirty") is True:
        errors.append("backend repository is dirty")
    if not current.get("entrypoints"):
        errors.append("backend entrypoint is missing")
    if not current.get("weights"):
        errors.append("backend weights are missing")
    return {"ok": not errors, "backend": kind, "fingerprint": current, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or explicitly trust a local lip-sync backend"
    )
    parser.add_argument("command", choices=["inspect", "lock"])
    parser.add_argument("--backend", required=True, choices=sorted(BACKEND_FILES))
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "--lock", default=str(Path(__file__).resolve().parents[2] / "backend-lock.json")
    )
    parser.add_argument("--acknowledge-trusted-weights", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "inspect":
        print(json.dumps(backend_fingerprint(args.backend, root), ensure_ascii=False, indent=2))
        return 0
    if not args.acknowledge_trusted_weights:
        parser.error("lock requires --acknowledge-trusted-weights after provenance review")
    entry = create_lock_entry(args.backend, root, trusted_weights=True)
    if entry["fingerprint"].get("git_dirty") is True:
        parser.error("refusing to trust a dirty backend repository")
    lock_path = Path(args.lock).expanduser().resolve()
    try:
        lock = (
            json.loads(lock_path.read_text(encoding="utf-8"))
            if lock_path.is_file()
            else {"schema_version": 1}
        )
    except json.JSONDecodeError as exc:
        parser.error(f"invalid existing lock: {exc}")
    lock.setdefault("backends", {})[args.backend] = entry
    atomic_write_text(lock_path, json.dumps(lock, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "lock": str(lock_path), "backend": args.backend}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
