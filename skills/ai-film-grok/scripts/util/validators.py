"""Input validators and path builders."""

from __future__ import annotations

import re
from pathlib import Path

from util.errors import FilmError


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[\s_/]+", "-", text)
    text = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "film"


def aspect_dims(aspect: str) -> tuple[int, int]:
    table = {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1": (1024, 1024),
        "3:4": (768, 1024),
        "4:3": (1024, 768),
    }
    if aspect not in table:
        raise FilmError(f"Unsupported aspect {aspect!r}; use one of {sorted(table)}")
    return table[aspect]


def film_output_path(root: Path, name: str, *, field: str = "output name") -> Path:
    from security_policy import SecurityPolicyError, safe_output_path, safe_workspace_directory

    try:
        out_dir = safe_workspace_directory(root, "out", field="film output directory")
        return safe_output_path(out_dir, name, suffixes={".mp4"}, field=field)
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc


def valid_shot_id(value: str) -> str:
    from security_policy import SecurityPolicyError, validate_identifier

    try:
        return validate_identifier(value, field="shot id")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
