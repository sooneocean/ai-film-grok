#!/usr/bin/env python3
"""Reproducibility fingerprints for the skill runtime."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env

LOCKED_PACKAGES = ("numpy", "Pillow", "edge-tts", "jsonschema")
DEFAULT_SCRIPTS = (
    "aifilm",
    "aifilm_grok.py",
    "backend-lock",
    "backend_lock.py",
    "edit_policy.py",
    "film_spec.py",
    "lipsync_backend.py",
    "lipsync_node_client.py",
    "lipsync_node_service.py",
    "make_sfx_bed.py",
    "media_qa.py",
    "media-queue",
    "media_queue.py",
    "production_gates.py",
    "production_book.py",
    "director_cli.py",
    "director_stage_gates.py",
    "creative_quality.py",
    "preflight.py",
    "post_audit.py",
    "master_delivery.py",
    "face_identity.py",
    "final_stages.py",
    "quality_check_video.py",
    "style_lock.py",
    "creative_pipeline.py",
    "dailies.py",
    "post_quality.py",
    "provider_canary.py",
    "delivery_package.py",
    "benchmark.py",
    "render_final.py",
    "runtime_policy.py",
    "security_policy.py",
    "tts_backend.py",
    "test-skill",
    "adapters/cosyvoice_infer.example.py",
)


def _default_script_paths(skill_dir: Path) -> list[Path]:
    """Fingerprint every shipped executable/module, including new split-out domains.

    The historical allow-list remains as a compatibility floor, while discovery
    prevents a newly extracted production gate from silently escaping runtime
    protection.  Tests and bytecode caches are deliberately excluded.
    """
    scripts_dir = skill_dir / "scripts"
    discovered = {
        path
        for path in scripts_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (
            path.suffix == ".py"
            or path.name in {"aifilm", "backend-lock", "media-queue", "test-skill"}
        )
    }
    discovered.update(scripts_dir / name for name in DEFAULT_SCRIPTS)
    return sorted(discovered)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"requirements lock must use exact pins: {line}")
        name, version = line.split("==", 1)
        result[name.strip()] = version.strip()
    return result


def verify_requirements_lock(path: Path) -> dict[str, Any]:
    expected = _requirements(path)
    errors: list[str] = []
    packages: dict[str, dict[str, str | None]] = {}
    for name, actual in _package_versions(expected).items():
        wanted = expected[name]
        packages[name] = {"expected": wanted, "actual": actual}
        if actual != wanted:
            errors.append(f"{name}: expected {wanted}, found {actual or 'missing'}")
    if not expected:
        errors.append(f"requirements lock is missing or empty: {path}")
    return {"ok": not errors, "path": str(path), "packages": packages, "errors": errors}


def _command_version(command: str) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        proc = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=15,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or proc.stderr).splitlines()
    return text[0].strip() if text else None


def _package_versions(names: Iterable[str]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def build_runtime_lock(
    skill_dir: Path, *, script_paths: list[Path] | None = None
) -> dict[str, Any]:
    root = skill_dir.expanduser().resolve()
    if script_paths is None:
        script_paths = _default_script_paths(root)
    scripts: list[dict[str, str]] = []
    for path in script_paths:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            continue
        try:
            key = str(resolved.relative_to(root))
        except ValueError:
            key = str(resolved)
        # Keep paths and fingerprints as separate JSON fields.  Apart from
        # being clearer to parse, this prevents secret scanners from treating
        # an OAuth-named path plus a SHA-256 integrity digest as a credential.
        scripts.append({"path": key, "sha256": sha256(resolved)})
    requirements_path = root / "requirements.lock"
    package_names = tuple(_requirements(requirements_path)) or LOCKED_PACKAGES
    return {
        "schema_version": 2,
        "python": platform.python_version(),
        "commands": {"ffmpeg": _command_version("ffmpeg"), "ffprobe": _command_version("ffprobe")},
        "packages": _package_versions(package_names),
        "scripts": scripts,
        "requirements_sha256": sha256(requirements_path) if requirements_path.is_file() else None,
    }


def verify_runtime_lock(skill_dir: Path, lock_path: Path) -> dict[str, Any]:
    root = skill_dir.expanduser().resolve()
    if not lock_path.is_file():
        return {"ok": False, "errors": [f"runtime lock missing: {lock_path}"]}
    try:
        expected = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"runtime lock unreadable: {exc}"]}
    errors: list[str] = []
    if expected.get("python") != platform.python_version():
        errors.append(
            f"python version drift: expected {expected.get('python')}, found {platform.python_version()}"
        )
    for command, wanted in (expected.get("commands") or {}).items():
        actual = _command_version(command)
        if actual != wanted:
            errors.append(f"{command} version drift")
    expected_packages = expected.get("packages") or {}
    actual_packages = _package_versions(expected_packages)
    for package, wanted in expected_packages.items():
        actual = actual_packages[package]
        if actual != wanted:
            errors.append(f"{package} version drift: expected {wanted}, found {actual}")
    raw_scripts = expected.get("scripts") or []
    if isinstance(raw_scripts, dict):
        # Read v1 locks so existing projects receive a useful drift report;
        # newly written locks always use the scanner-safe v2 record shape.
        script_entries = [{"path": path, "sha256": digest} for path, digest in raw_scripts.items()]
    elif isinstance(raw_scripts, list):
        script_entries = raw_scripts
    else:
        script_entries = []
        errors.append("runtime lock scripts must be an object or list")
    for entry in script_entries:
        if not isinstance(entry, dict):
            errors.append("runtime lock script entry is invalid")
            continue
        relative = entry.get("path")
        wanted = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(wanted, str):
            errors.append("runtime lock script entry is invalid")
            continue
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        actual = sha256(path) if path.is_file() else None
        if actual != wanted:
            errors.append(f"script fingerprint drift: {relative}")
    requirements_path = root / "requirements.lock"
    wanted_requirements = expected.get("requirements_sha256")
    actual_requirements = sha256(requirements_path) if requirements_path.is_file() else None
    if actual_requirements != wanted_requirements:
        errors.append("requirements.lock fingerprint drift")
    return {"ok": not errors, "path": str(lock_path), "errors": errors}
