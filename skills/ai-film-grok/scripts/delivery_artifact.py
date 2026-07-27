"""Resolve the hash-bound final artifact recorded in a film manifest."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from security_policy import SecurityPolicyError, safe_existing_file
from util import sha256_file

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class FinalArtifact:
    path: Path
    sha256: str


class DeliveryArtifactError(RuntimeError):
    pass


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
    copied = [Path(shutil.copy2(artifact.path, destination / artifact.path.name))]
    silent = root / "out" / "film_silent.mp4"
    if silent.is_file() and silent.resolve() != artifact.path.resolve():
        copied.append(Path(shutil.copy2(silent, destination / silent.name)))
    return copied
