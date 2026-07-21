#!/usr/bin/env python3
"""Shared input and process boundaries for ai-film-grok scripts."""

from __future__ import annotations

import json
import os
import re
import string
import tempfile
import unicodedata
from pathlib import Path
from typing import Mapping, Sequence


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_COMPONENT_LENGTH = 128
MAX_ARG_COUNT = 128
MAX_ARG_LENGTH = 16_384
SUBPROCESS_ENV_KEYS = frozenset(
    {
        "CONDA_DEFAULT_ENV",
        "CONDA_PREFIX",
        "CUDA_HOME",
        "CUDA_VISIBLE_DEVICES",
        "DYLD_LIBRARY_PATH",
        "HF_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LD_LIBRARY_PATH",
        "MPLCONFIGDIR",
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "TMPDIR",
        "TORCH_HOME",
        "VIRTUAL_ENV",
        "XDG_CACHE_HOME",
    }
)


class SecurityPolicyError(ValueError):
    """An input would cross a filesystem or process-execution boundary."""


def _has_control_characters(value: str) -> bool:
    return any(unicodedata.category(char).startswith("C") for char in value)


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise SecurityPolicyError(
            f"Invalid {field}: use 1-64 ASCII letters, digits, '_' or '-', starting with a letter or digit"
        )
    return value


def validate_component(value: str, *, field: str = "name") -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SecurityPolicyError(f"Invalid {field}: value must be non-empty without outer whitespace")
    if len(value) > MAX_COMPONENT_LENGTH:
        raise SecurityPolicyError(f"Invalid {field}: maximum length is {MAX_COMPONENT_LENGTH}")
    if value in {".", ".."} or os.path.isabs(value) or "/" in value or "\\" in value:
        raise SecurityPolicyError(f"Invalid {field}: a single relative path component is required")
    if _has_control_characters(value):
        raise SecurityPolicyError(f"Invalid {field}: control characters are not allowed")
    return value


def _contained_candidate(root: Path, name: str, *, field: str) -> Path:
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / name).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise SecurityPolicyError(f"Invalid {field}: path escapes {resolved_root}") from exc
    return candidate


def safe_subdirectory(root: Path, name: str, *, field: str = "directory name") -> Path:
    component = validate_component(name, field=field)
    return _contained_candidate(root, component, field=field)


def safe_workspace_directory(root: Path, name: str, *, field: str = "workspace directory") -> Path:
    component = validate_component(name, field=field)
    resolved_root = root.expanduser().resolve()
    unresolved = resolved_root / component
    if unresolved.is_symlink():
        raise SecurityPolicyError(f"Invalid {field}: symbolic-link directories are not allowed")
    return _contained_candidate(resolved_root, component, field=field)


def safe_existing_file(root: Path, path: Path | str, *, field: str = "media path") -> Path:
    resolved_root = root.expanduser().resolve()
    raw = Path(path).expanduser()
    candidate = (raw if raw.is_absolute() else resolved_root / raw).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise SecurityPolicyError(f"Invalid {field}: file escapes {resolved_root}") from exc
    if not candidate.is_file():
        raise SecurityPolicyError(f"Invalid {field}: file is missing: {candidate}")
    return candidate


# Dep trees install thousands of bin symlinks (npm/node_modules). Scanning them
# breaks export-compose after remotion npm install. Still reject symlinks outside
# these known package dirs.
_SYMLINK_SCAN_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
    }
)


def reject_symlinks(root: Path, *, field: str) -> None:
    if root.is_symlink():
        raise SecurityPolicyError(f"Invalid {field}: symbolic links are not allowed: {root}")
    if not root.exists():
        return
    for path in root.rglob("*"):
        try:
            parts = path.parts
        except (OSError, ValueError):
            continue
        if any(part in _SYMLINK_SCAN_SKIP_DIR_NAMES for part in parts):
            continue
        if path.is_symlink():
            raise SecurityPolicyError(f"Invalid {field}: symbolic links are not allowed: {path}")


def safe_output_path(
    root: Path,
    name: str,
    *,
    suffixes: set[str] | frozenset[str],
    field: str = "output name",
) -> Path:
    component = validate_component(name, field=field)
    allowed = {suffix.lower() for suffix in suffixes}
    suffix = Path(component).suffix.lower()
    if suffix not in allowed:
        raise SecurityPolicyError(f"Invalid {field}: expected one of {sorted(allowed)}")
    candidate = _contained_candidate(root, component, field=field)
    if candidate.is_symlink():
        raise SecurityPolicyError(f"Invalid {field}: symbolic-link outputs are not allowed")
    return candidate


def parse_argv_json(raw: str, *, variable: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecurityPolicyError(f"{variable} must be a JSON array of strings") from exc
    if not isinstance(value, list) or not value or len(value) > MAX_ARG_COUNT:
        raise SecurityPolicyError(f"{variable} must contain 1-{MAX_ARG_COUNT} arguments")
    if any(not isinstance(arg, str) or not arg or len(arg) > MAX_ARG_LENGTH for arg in value):
        raise SecurityPolicyError(f"{variable} arguments must be non-empty strings under {MAX_ARG_LENGTH} characters")
    if not value[0].strip() or any("\0" in arg for arg in value):
        raise SecurityPolicyError(f"{variable} contains an invalid executable or NUL byte")
    return value


def expand_argv(
    template: Sequence[str],
    values: Mapping[str, str],
    *,
    variable: str,
) -> list[str]:
    formatter = string.Formatter()
    expanded: list[str] = []
    for arg in template:
        try:
            fields = list(formatter.parse(arg))
        except ValueError as exc:
            raise SecurityPolicyError(f"{variable} contains malformed braces") from exc
        for _, field_name, format_spec, conversion in fields:
            if field_name is None:
                continue
            if field_name not in values or format_spec or conversion:
                raise SecurityPolicyError(
                    f"{variable} contains unsupported placeholder {{{field_name}}}; allowed: {sorted(values)}"
                )
        try:
            result = arg.format_map(dict(values))
        except (KeyError, ValueError) as exc:
            raise SecurityPolicyError(f"{variable} contains an invalid placeholder") from exc
        if "\0" in result or len(result) > MAX_ARG_LENGTH:
            raise SecurityPolicyError(f"{variable} expands to an invalid argument")
        expanded.append(result)
    return expanded


def minimal_subprocess_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    values = os.environ if source is None else source
    env = {key: values[key] for key in SUBPROCESS_ENV_KEYS if key in values}
    env.setdefault("PATH", os.defpath)
    return env


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding=encoding, dir=path.parent, delete=False
        ) as handle:
            handle.write(text)
            temp = Path(handle.name)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            handle.write(data)
            temp = Path(handle.name)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def load_allowed_env(path: Path, *, allowed_keys: set[str] | frozenset[str]) -> list[str]:
    """Load only documented skill-local keys without overriding the process environment."""
    ignored: list[str] = []
    if not path.is_file():
        return ignored
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed_keys:
            ignored.append(key)
            continue
        if key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
    return ignored
