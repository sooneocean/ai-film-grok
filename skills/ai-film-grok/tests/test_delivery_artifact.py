from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from delivery_artifact import (
    DeliveryArtifactError,
    export_final_artifacts,
    resolve_final_artifact,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_resolve_uses_manifest_custom_final_instead_of_filename_fallback(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    custom = out / "custom-final.mp4"
    custom.write_bytes(b"reviewed-final")
    (out / "film_silent.mp4").write_bytes(b"not-reviewed")
    manifest = {
        "outputs": {
            "final_film": {
                "path": custom.name,
                "sha256": _sha256(custom),
            }
        }
    }

    artifact = resolve_final_artifact(tmp_path, manifest)

    assert artifact.path == custom
    assert artifact.sha256 == _sha256(custom)


def test_resolve_accepts_root_relative_out_path(tmp_path: Path) -> None:
    final = tmp_path / "out" / "custom-final.mp4"
    final.parent.mkdir()
    final.write_bytes(b"reviewed-final")
    manifest = {
        "outputs": {
            "final_film": {
                "path": "out/custom-final.mp4",
                "sha256": _sha256(final),
            }
        }
    }

    assert resolve_final_artifact(tmp_path, manifest).path == final


def test_resolve_rejects_tampered_final(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir()
    final.write_bytes(b"changed")
    manifest = {
        "outputs": {
            "final_film": {
                "path": final.name,
                "sha256": hashlib.sha256(b"reviewed").hexdigest(),
            }
        }
    }

    with pytest.raises(DeliveryArtifactError, match="hash"):
        resolve_final_artifact(tmp_path, manifest)


def test_export_always_copies_manifest_final_when_silent_variant_exists(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    custom = out / "custom-final.mp4"
    custom.write_bytes(b"reviewed-final")
    silent = out / "film_silent.mp4"
    silent.write_bytes(b"silent")
    manifest = {
        "outputs": {
            "final_film": {
                "path": custom.name,
                "sha256": _sha256(custom),
            }
        }
    }
    destination = tmp_path / "export"
    destination.mkdir()

    copied = export_final_artifacts(tmp_path, manifest, destination)

    assert [path.name for path in copied] == ["custom-final.mp4", "film_silent.mp4"]
    assert (destination / "custom-final.mp4").read_bytes() == b"reviewed-final"
