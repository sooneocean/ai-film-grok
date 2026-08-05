"""Path / identity helpers for film roots."""

from __future__ import annotations

import shutil
from pathlib import Path

from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    safe_existing_file,
    safe_output_path,
    safe_workspace_directory,
    validate_identifier,
)
from util.errors import FilmError


def film_output_path(root: Path, name: str, *, field: str = "output name") -> Path:
    try:
        out_dir = safe_workspace_directory(root, "out", field="film output directory")
        return safe_output_path(out_dir, name, suffixes={".mp4"}, field=field)
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc


def valid_shot_id(value: str) -> str:
    try:
        return validate_identifier(value, field="shot id")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc


def record_file_matches(root: Path, record: object, *, field: str) -> bool:
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        return False
    try:
        path = safe_existing_file(root, record["path"], field=field)
    except SecurityPolicyError:
        return False
    expected = record.get("sha256")
    return isinstance(expected, str) and bool(expected) and sha256(path) == expected


def which_npx_safe() -> str | None:
    return shutil.which("npx")
